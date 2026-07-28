from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import MessageReactionUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.messages import find_message_by_admin_chat_id
from app.services.queue import UserUnreachable, send_with_retry

router = Router(name="admin_reaction")
logger = logging.getLogger(__name__)


@router.message_reaction()
async def mirror_reaction_to_user(event: MessageReactionUpdated, session: AsyncSession) -> None:
    """When an admin puts a native Telegram reaction (👍, ❤️, etc. — via the normal
    long-press/tap reaction picker, not a button) on a forwarded user message inside
    the admin chat, the same reaction is mirrored onto the user's own copy of that
    message, so they see it appear on their side too — same idea as in a regular chat.
    """
    if event.chat.id != settings.ADMIN_CHAT_ID:
        return

    actor_id = event.user.id if event.user else None
    if actor_id is None or actor_id not in settings.admin_ids:
        # Ignore reactions from non-admins, or anonymous-as-the-group reactions
        # (event.actor_chat set instead of event.user) — nothing reliable to mirror.
        return

    original = await find_message_by_admin_chat_id(session, event.message_id)
    if original is None or original.user_chat_message_id is None:
        return

    try:
        await send_with_retry(
            lambda: event.bot.set_message_reaction(
                chat_id=original.user_telegram_id,
                message_id=original.user_chat_message_id,
                reaction=event.new_reaction,
            )
        )
    except UserUnreachable:
        pass
    except TelegramBadRequest:
        # Some message types / already-deleted messages don't support reactions —
        # not worth surfacing to the admin, just log for diagnostics.
        logger.info(
            "Could not mirror reaction to user %s on message %s (unsupported or deleted)",
            original.user_telegram_id,
            original.user_chat_message_id,
        )
    except Exception:
        logger.exception("Failed to mirror reaction to user")
