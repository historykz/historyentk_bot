from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TicketMessage, TicketStatus
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.messages import find_message_by_admin_chat_id, save_admin_message
from app.services.queue import UserUnreachable, send_with_retry
from app.services.tickets import get_ticket_by_id
from app.utils.formatting import detect_message_kind, extract_file_id, extract_text_or_caption

router = Router(name="admin_reply")
fallback_router = Router(name="admin_reply_fallback")
logger = logging.getLogger(__name__)

REPLY_HEADER = "Ответ администратора:"
CONFIRMATION_AUTO_DELETE_SECONDS = 5

# Keeps references to fire-and-forget auto-delete tasks so asyncio can't garbage-collect
# them mid-sleep (a well-known gotcha with asyncio.create_task on a task nothing holds).
_background_tasks: set[asyncio.Task] = set()


class IsTicketReply(BaseFilter):
    """Matches only when the admin replied to a message that is actually a forwarded
    user message (recorded in ticket_messages) — NOT to some other bot message like
    "Введите сумму к оплате...". This is what lets an admin swipe-reply to the bot's
    own prompts (amount, comment, custom period dates, etc.) without that reply being
    swallowed here before it reaches the flow that's actually waiting for it.
    """

    async def __call__(self, message: Message, session: AsyncSession) -> bool | dict:
        if message.reply_to_message is None:
            return False
        original = await find_message_by_admin_chat_id(session, message.reply_to_message.message_id)
        if original is None:
            return False
        return {"original_message": original}


async def _delete_after_delay(message: Message, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.message(IsAdminChat(), IsAdmin(), IsTicketReply())
async def admin_reply_to_user(message: Message, session: AsyncSession, original_message: TicketMessage) -> None:
    ticket = await get_ticket_by_id(session, original_message.ticket_id)
    if ticket is None:
        await message.reply(
            "Не удалось определить получателя. Ответьте свайпом на сообщение конкретного пользователя."
        )
        return

    text = extract_text_or_caption(message)
    kind = detect_message_kind(message)
    file_id = extract_file_id(message)

    outgoing_text = f"{REPLY_HEADER}\n\n{text}" if text else REPLY_HEADER

    try:
        if kind.value == "text":
            await send_with_retry(
                lambda: message.bot.send_message(ticket.user_telegram_id, outgoing_text)
            )
        elif message.photo:
            await send_with_retry(
                lambda: message.bot.send_photo(ticket.user_telegram_id, file_id, caption=outgoing_text)
            )
        elif message.video:
            await send_with_retry(
                lambda: message.bot.send_video(ticket.user_telegram_id, file_id, caption=outgoing_text)
            )
        elif message.document:
            await send_with_retry(
                lambda: message.bot.send_document(ticket.user_telegram_id, file_id, caption=outgoing_text)
            )
        elif message.voice:
            await message.bot.send_message(ticket.user_telegram_id, REPLY_HEADER)
            await send_with_retry(lambda: message.bot.send_voice(ticket.user_telegram_id, file_id))
        elif message.video_note:
            await message.bot.send_message(ticket.user_telegram_id, REPLY_HEADER)
            await send_with_retry(lambda: message.bot.send_video_note(ticket.user_telegram_id, file_id))
        elif message.audio:
            await send_with_retry(
                lambda: message.bot.send_audio(ticket.user_telegram_id, file_id, caption=outgoing_text)
            )
        else:
            await send_with_retry(
                lambda: message.bot.send_message(ticket.user_telegram_id, outgoing_text)
            )
    except UserUnreachable:
        await message.reply(
            "Сообщение не доставлено. Возможно, пользователь заблокировал бота или удалил аккаунт."
        )
        return
    except Exception:
        logger.exception("Failed to deliver admin reply")
        await message.reply(
            "Сообщение не доставлено. Возможно, пользователь заблокировал бота или удалил аккаунт."
        )
        return

    await save_admin_message(
        session,
        ticket,
        admin_telegram_id=message.from_user.id,
        kind=kind,
        text=text,
        file_id=file_id,
    )

    if ticket.status in (TicketStatus.NEW, TicketStatus.VIEWED, TicketStatus.AWAITING_ADMIN):
        ticket.status = TicketStatus.ANSWERED
        await session.flush()

    confirmation = await message.reply("Ответ успешно отправлен пользователю.")
    # Auto-deletes after a few seconds so the admin chat doesn't fill up with these —
    # scheduled as a background task so it doesn't block processing further messages.
    task = asyncio.create_task(_delete_after_delay(confirmation, CONFIRMATION_AUTO_DELETE_SECONDS))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@fallback_router.message(IsAdminChat(), IsAdmin(), F.reply_to_message)
async def admin_reply_to_unknown_message(message: Message) -> None:
    """Fallback: reached only when nothing else (not the ticket-reply handler above,
    not any pending admin flow waiting for free text) claimed this reply. Genuinely
    orphaned replies — e.g. replying to some unrelated old message — land here.
    Registered as a separate router placed LAST in app/bot.py, after every admin flow
    that might be waiting for a plain-text answer, so it never steals their input.
    """
    await message.reply(
        "Не удалось определить получателя. Ответьте свайпом на сообщение конкретного пользователя."
    )
