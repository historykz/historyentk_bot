from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequisiteKind, TicketStatus
from app.keyboards.admin_kb import requisites_preview_keyboard
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.payments import (
    create_pending_payment,
    get_or_create_requisites,
    payment_type_for_ticket,
    render_cooperation_message,
    render_purchase_message,
)
from app.services.queue import UserUnreachable, send_with_retry
from app.services.tickets import get_ticket_by_id
from app.keyboards.user_kb import pay_receipt_keyboard
from app.states.admin_states import RequisitesFlow

router = Router(name="admin_requisites")


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("req:"))
async def start_requisites_flow(callback: CallbackQuery, state: FSMContext) -> None:
    _, kind, ticket_id = callback.data.split(":")
    await callback.answer()
    await state.set_state(RequisitesFlow.entering_amount)
    await state.update_data(req_kind=kind, ticket_id=int(ticket_id))
    label = "покупку" if kind == "purchase" else "сотрудничество"
    await callback.message.reply(f"Введите сумму к оплате за {label} в тенге.")


@router.message(RequisitesFlow.entering_amount)
async def enter_amount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        amount = Decimal(message.text.strip().replace(" ", "").replace(",", "."))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, AttributeError):
        await message.reply("Пожалуйста, введите сумму числом, например: 5000")
        return

    data = await state.get_data()
    kind = data["req_kind"]
    ticket_id = data["ticket_id"]

    requisites = await get_or_create_requisites(
        session, RequisiteKind.PURCHASE if kind == "purchase" else RequisiteKind.COOPERATION
    )
    preview_text = (
        render_purchase_message(amount, requisites)
        if kind == "purchase"
        else render_cooperation_message(amount, requisites)
    )

    await state.update_data(amount=str(amount))
    await state.set_state(RequisitesFlow.preview)
    await message.answer(preview_text, reply_markup=requisites_preview_keyboard(kind, ticket_id))


@router.callback_query(F.data.startswith("reqamount:"))
async def edit_amount(callback: CallbackQuery, state: FSMContext) -> None:
    _, kind, ticket_id = callback.data.split(":")
    await callback.answer()
    await state.set_state(RequisitesFlow.entering_amount)
    await state.update_data(req_kind=kind, ticket_id=int(ticket_id))
    await callback.message.reply("Введите новую сумму к оплате в тенге.")


@router.callback_query(F.data.startswith("reqcomment:"))
async def add_comment_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(RequisitesFlow.editing_comment)
    await callback.message.reply("Введите комментарий (он будет сохранён вместе с оплатой).")


@router.message(RequisitesFlow.editing_comment)
async def save_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text)
    data = await state.get_data()
    kind = data["req_kind"]
    ticket_id = data["ticket_id"]
    await state.set_state(RequisitesFlow.preview)
    await message.answer("Комментарий сохранён.", reply_markup=requisites_preview_keyboard(kind, ticket_id))


@router.callback_query(F.data.startswith("reqcancel:"))
async def cancel_requisites_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.reply("Отправка реквизитов отменена.")


@router.callback_query(F.data.startswith("reqsend:"))
async def send_requisites_to_user(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    _, kind, ticket_id = callback.data.split(":")
    ticket_id = int(ticket_id)
    await callback.answer()

    data = await state.get_data()
    amount = Decimal(data.get("amount", "0"))
    comment = data.get("comment")

    ticket = await get_ticket_by_id(session, ticket_id)
    if ticket is None:
        await callback.message.reply("Обращение не найдено.")
        return

    requisites = await get_or_create_requisites(
        session, RequisiteKind.PURCHASE if kind == "purchase" else RequisiteKind.COOPERATION
    )
    payment_type = payment_type_for_ticket(ticket)
    payment = await create_pending_payment(
        session, ticket, amount, payment_type, requisites, admin_id=callback.from_user.id
    )
    if comment:
        payment.admin_comment = comment
        await session.flush()

    text = (
        render_purchase_message(amount, requisites)
        if kind == "purchase"
        else render_cooperation_message(amount, requisites)
    )

    try:
        if requisites.photo_file_id:
            await send_with_retry(
                lambda: callback.bot.send_photo(
                    ticket.user_telegram_id, requisites.photo_file_id, caption=text,
                    reply_markup=pay_receipt_keyboard(),
                )
            )
        else:
            await send_with_retry(
                lambda: callback.bot.send_message(
                    ticket.user_telegram_id, text, reply_markup=pay_receipt_keyboard()
                )
            )
        if requisites.qr_file_id:
            await send_with_retry(
                lambda: callback.bot.send_photo(ticket.user_telegram_id, requisites.qr_file_id)
            )
    except UserUnreachable:
        await callback.message.reply(
            "Сообщение не доставлено. Возможно, пользователь заблокировал бота или удалил аккаунт."
        )
        return

    ticket.status = TicketStatus.AWAITING_PAYMENT
    await session.flush()

    await state.clear()
    await callback.message.reply("Реквизиты отправлены пользователю.")
