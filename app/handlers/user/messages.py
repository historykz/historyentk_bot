from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import MessageKind, TicketStatus
from app.keyboards.admin_kb import ticket_action_keyboard
from app.keyboards.user_kb import reason_keyboard
from app.services.messages import render_new_appeal_header, save_user_message
from app.services.spam_guard import SpamGuard
from app.services.tickets import get_open_ticket, upsert_user
from app.states.user_states import UserFlow
from app.utils.formatting import detect_message_kind, extract_file_id, extract_text_or_caption

router = Router(name="user_messages")
logger = logging.getLogger(__name__)

GATE_TEXT = (
    "Перед отправкой сообщения необходимо выбрать причину обращения.\n\n"
    "Пожалуйста, выберите подходящий вариант с помощью кнопок ниже."
)

THROTTLE_TEXT = "Вы отправляете сообщения слишком часто. Пожалуйста, подождите немного."


@router.message(UserFlow.chatting)
async def relay_to_admin(message: Message, state: FSMContext, session: AsyncSession, redis: Redis) -> None:
    tg_user = message.from_user
    user = await upsert_user(session, tg_user)

    ticket = await get_open_ticket(session, tg_user.id)
    if ticket is None:
        # State says chatting but there's no open ticket (e.g. it was closed elsewhere) -> re-gate.
        await state.set_state(UserFlow.choosing_reason)
        await message.answer(GATE_TEXT, reply_markup=reason_keyboard())
        return

    guard = SpamGuard(redis)
    if await guard.is_throttled(tg_user.id):
        await message.answer(THROTTLE_TEXT)
        return

    text_or_caption = extract_text_or_caption(message)
    is_dup = await guard.is_duplicate(tg_user.id, text_or_caption)

    header = render_new_appeal_header(user, ticket, is_duplicate=is_dup)

    try:
        await message.bot.send_message(settings.ADMIN_CHAT_ID, f"<blockquote>{header}</blockquote>", parse_mode="HTML")
        forwarded = await message.copy_to(settings.ADMIN_CHAT_ID)
        await message.bot.edit_message_reply_markup(
            chat_id=settings.ADMIN_CHAT_ID,
            message_id=forwarded.message_id,
            reply_markup=ticket_action_keyboard(ticket.id, ticket.reason),
        )
    except TelegramBadRequest:
        logger.exception("Failed to relay message to admin chat")
        await message.answer(
            "Не удалось отправить сообщение администратору. Попробуйте ещё раз чуть позже."
        )
        return

    kind = detect_message_kind(message)
    file_id = extract_file_id(message)

    await save_user_message(
        session,
        ticket,
        user_telegram_id=tg_user.id,
        kind=kind,
        text=text_or_caption,
        file_id=file_id,
        user_chat_message_id=message.message_id,
        admin_chat_message_id=forwarded.message_id,
        is_duplicate_flagged=is_dup,
    )

    if ticket.status not in (TicketStatus.PAID, TicketStatus.CLOSED):
        ticket.status = TicketStatus.AWAITING_ADMIN
        await session.flush()


# Any message coming in while the user hasn't chosen a reason yet (no state, still choosing_reason,
# or still choosing_purchase_subcategory) must be gated. This handler is intentionally state-agnostic
# and registered after the more specific handlers above and after admin-only routers, so it only
# catches the "not yet in a ticket" case for private chats with the bot.
@router.message(F.chat.type == "private")
async def gate_before_reason(message: Message, state: FSMContext) -> None:
    current: str | None = await state.get_state()
    if current == UserFlow.awaiting_receipt.state:
        return  # handled by receipt router; shouldn't normally reach here due to router order
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer(GATE_TEXT, reply_markup=reason_keyboard())
    if current not in (UserFlow.choosing_reason.state, UserFlow.choosing_purchase_subcategory.state):
        await state.set_state(UserFlow.choosing_reason)
