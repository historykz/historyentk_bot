from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import PaymentType, ReasonCategory
from app.keyboards.admin_kb import receipt_review_keyboard
from app.keyboards.user_kb import pay_receipt_keyboard
from app.services.payments import attach_receipt, get_latest_pending_payment
from app.services.tickets import get_open_ticket
from app.states.user_states import UserFlow
from app.utils.formatting import extract_file_id
from app.utils.time_utils import now_local

router = Router(name="user_receipt")

PAYMENT_TYPE_LABELS = {
    PaymentType.PURCHASE_TESTS: "Покупка — тест или тесты",
    PaymentType.PURCHASE_PREMIUM: "Покупка — Premium-доступ",
    PaymentType.PURCHASE_NOTES: "Покупка — конспекты",
    PaymentType.PURCHASE_ALL: "Покупка — всё вышеперечисленное",
    PaymentType.COOPERATION: "Сотрудничество",
}


@router.callback_query(F.data == "user_send_receipt")
async def ask_for_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(UserFlow.awaiting_receipt)
    await callback.message.answer("Отправьте фотографию или файл с чеком об оплате.")


@router.message(UserFlow.awaiting_receipt)
async def receive_receipt(message: Message, state: FSMContext, session: AsyncSession) -> None:
    file_id = extract_file_id(message)
    if message.document is None and message.photo is None:
        await message.answer("Пожалуйста, отправьте фотографию или файл с чеком об оплате.")
        return

    ticket = await get_open_ticket(session, message.from_user.id)
    if ticket is None:
        await message.answer("Не удалось найти ваше обращение. Напишите /start, чтобы начать заново.")
        await state.set_state(UserFlow.choosing_reason)
        return

    payment = await get_latest_pending_payment(session, ticket.id)
    if payment is None:
        await message.answer(
            "Не найдено ожидающей оплаты по вашему обращению. Обратитесь к администратору."
        )
        return

    await attach_receipt(session, payment, file_id)
    await state.set_state(UserFlow.chatting)

    label = PAYMENT_TYPE_LABELS.get(payment.payment_type, "Покупка")
    payment_kind_line = "Тип оплаты: Сотрудничество" if payment.payment_type == PaymentType.COOPERATION else f"Категория: {label.split(' — ')[-1] if ' — ' in label else '-'}"

    header = (
        "Получен чек об оплате\n\n"
        f"Пользователь: {'@' + message.from_user.username if message.from_user.username else message.from_user.first_name}\n"
        f"Telegram ID: {message.from_user.id}\n"
        f"Обращение: #{ticket.number}\n"
        f"Причина: {ticket.reason_label.split(' — ')[0]}\n"
        f"{payment_kind_line}\n"
        f"Заявленная сумма: {payment.requested_amount} ₸\n"
        f"Дата и время: {now_local().strftime('%d.%m.%Y, %H:%M')}"
    )

    await message.bot.send_message(settings.ADMIN_CHAT_ID, f"<blockquote>{header}</blockquote>", parse_mode="HTML")
    if message.photo:
        await message.bot.send_photo(
            settings.ADMIN_CHAT_ID,
            file_id,
            reply_markup=receipt_review_keyboard(payment.id),
        )
    else:
        await message.bot.send_document(
            settings.ADMIN_CHAT_ID,
            file_id,
            reply_markup=receipt_review_keyboard(payment.id),
        )

    await message.answer("Спасибо! Ваш чек отправлен администратору на проверку.")
