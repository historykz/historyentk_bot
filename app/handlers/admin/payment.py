from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentStatus, TicketStatus
from app.keyboards.admin_kb import confirm_amount_keyboard
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.payments import cancel_confirmed_payment, confirm_payment, get_payment, reject_receipt
from app.services.queue import UserUnreachable, send_with_retry
from app.services.tickets import get_ticket_by_id
from app.states.admin_states import CancelPaymentFlow, ConfirmPaymentFlow

router = Router(name="admin_payment")


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("payok:"))
async def review_amount(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[1])
    await callback.answer()
    payment = await get_payment(session, payment_id)
    if payment is None:
        await callback.message.reply("Оплата не найдена.")
        return
    await state.set_state(ConfirmPaymentFlow.reviewing_amount)
    await state.update_data(payment_id=payment_id)
    await callback.message.reply(
        f"Проверьте сумму перед подтверждением.\n\nЗаявленная сумма: {payment.requested_amount} ₸",
        reply_markup=confirm_amount_keyboard(payment_id),
    )


@router.callback_query(F.data.startswith("payeditamount:"))
async def ask_new_amount(callback: CallbackQuery, state: FSMContext) -> None:
    payment_id = int(callback.data.split(":")[1])
    await callback.answer()
    await state.set_state(ConfirmPaymentFlow.editing_amount)
    await state.update_data(payment_id=payment_id)
    await callback.message.reply("Введите подтверждённую сумму в тенге.")


@router.message(ConfirmPaymentFlow.editing_amount)
async def set_new_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.strip().replace(" ", "").replace(",", "."))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, AttributeError):
        await message.reply("Введите сумму числом, например: 5000")
        return

    data = await state.get_data()
    payment_id = data["payment_id"]
    await state.set_state(ConfirmPaymentFlow.reviewing_amount)
    await message.answer(
        f"Новая сумма: {amount} ₸. Подтвердить?",
        reply_markup=confirm_amount_keyboard(payment_id),
    )
    await state.update_data(pending_amount=str(amount))


@router.callback_query(F.data.startswith("paycancelflow:"))
async def cancel_confirm_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.reply("Подтверждение оплаты отменено.")


@router.callback_query(F.data.startswith("payconfirm:"))
async def do_confirm(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[1])
    await callback.answer()

    data = await state.get_data()
    payment_before = await get_payment(session, payment_id)
    if payment_before is None:
        await callback.message.reply("Оплата не найдена.")
        return
    amount = Decimal(data.get("pending_amount", str(payment_before.requested_amount)))

    payment, newly_counted = await confirm_payment(session, payment_id, amount, callback.from_user.id)

    ticket = await get_ticket_by_id(session, payment.ticket_id)
    if ticket is not None:
        ticket.status = TicketStatus.PAID
        await session.flush()

    if not newly_counted:
        await callback.message.reply("Эта оплата уже была подтверждена ранее — повторный учёт не выполнен.")
        await state.clear()
        return

    try:
        await send_with_retry(
            lambda: callback.bot.send_message(
                payment.user_telegram_id,
                "Оплата подтверждена администратором. Благодарим за обращение!",
            )
        )
    except UserUnreachable:
        pass

    await state.clear()
    await callback.message.reply("Оплата подтверждена и учтена в статистике.")


@router.callback_query(F.data.startswith("payreject:"))
async def do_reject(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[1])
    await callback.answer()
    payment = await get_payment(session, payment_id)
    if payment is None:
        await callback.message.reply("Оплата не найдена.")
        return
    await reject_receipt(session, payment)
    try:
        await send_with_retry(
            lambda: callback.bot.send_message(
                payment.user_telegram_id,
                "Администратор не смог подтвердить оплату. Проверьте чек или отправьте его повторно.",
            )
        )
    except UserUnreachable:
        pass
    await callback.message.reply("Чек отклонён, пользователь уведомлён.")


@router.callback_query(F.data.startswith("payretry:"))
async def do_retry(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[1])
    await callback.answer()
    payment = await get_payment(session, payment_id)
    if payment is None:
        await callback.message.reply("Оплата не найдена.")
        return
    try:
        await send_with_retry(
            lambda: callback.bot.send_message(
                payment.user_telegram_id,
                "Пожалуйста, отправьте фотографию или файл с чеком об оплате ещё раз.",
            )
        )
    except UserUnreachable:
        pass
    await callback.message.reply("Пользователю отправлен запрос на новый чек.")


@router.message(IsAdminChat(), IsAdmin(), Command("cancel_payment"))
async def cancel_payment_cmd(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.reply("Использование: /cancel_payment ID_оплаты")
        return
    payment_id = int(parts[1].strip())
    await state.set_state(CancelPaymentFlow.awaiting_reason)
    await state.update_data(cancel_payment_id=payment_id)
    await message.reply("Укажите причину отмены оплаты:")


@router.message(CancelPaymentFlow.awaiting_reason)
async def cancel_payment_reason(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    payment_id = data["cancel_payment_id"]
    payment = await cancel_confirmed_payment(session, payment_id, message.from_user.id, message.text)
    await state.clear()
    if payment is None:
        await message.reply("Оплата не найдена или не находится в статусе подтверждённой.")
        return
    await message.reply(
        f"Оплата #{payment_id} отменена. Сумма {payment.confirmed_amount} ₸ вычтена из статистики."
    )
