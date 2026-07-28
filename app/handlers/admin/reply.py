from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TicketStatus
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.messages import find_message_by_admin_chat_id, save_admin_message
from app.services.queue import UserUnreachable, send_with_retry
from app.services.tickets import get_ticket_by_id
from app.utils.formatting import detect_message_kind, extract_file_id, extract_text_or_caption

router = Router(name="admin_reply")
logger = logging.getLogger(__name__)

REPLY_HEADER = "Ответ администратора:"


@router.message(IsAdminChat(), IsAdmin(), F.reply_to_message)
async def admin_reply_to_user(message: Message, session: AsyncSession) -> None:
    replied = message.reply_to_message
    original = await find_message_by_admin_chat_id(session, replied.message_id)

    if original is None:
        await message.reply(
            "Не удалось определить получателя. Ответьте свайпом на сообщение конкретного пользователя."
        )
        return

    ticket = await get_ticket_by_id(session, original.ticket_id)
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

    await message.reply("Ответ успешно отправлен пользователю.")
