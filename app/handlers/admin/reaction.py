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


def _is_trusted_admin_reaction(event: MessageReactionUpdated) -> bool:
    actor_id = event.user.id if event.user else None
    is_named_admin = actor_id is not None and actor_id in settings.admin_ids
    # Telegram sends event.actor_chat instead of event.user when a group admin reacts
    # "anonymously as the group" (a common group setting) — since only admins should
    # ever be members of the admin chat, an anonymous reaction *from that same chat*
    # is trusted the same way an anonymous admin message already is.
    is_anonymous_admin = (
        event.user is None and event.actor_chat is not None and event.actor_chat.id == event.chat.id
    )
    return is_named_admin or is_anonymous_admin


@router.message_reaction()
async def mirror_reaction_to_user(event: MessageReactionUpdated, session: AsyncSession) -> None:
    """When an admin puts a native Telegram reaction (👍, ❤️, etc. — via the normal
    long-press/tap reaction picker, not a button) on a forwarded user message inside
    the admin chat, the same reaction is mirrored onto the user's own copy of that
    message, so they see it appear on their side too — same idea as in a regular chat.
    """
    if event.chat.id != settings.ADMIN_CHAT_ID:
        return

    if not _is_trusted_admin_reaction(event):
        logger.info(
            "Ignoring message_reaction in admin chat from untrusted actor (user=%s, actor_chat=%s)",
            event.user.id if event.user else None,
            getattr(event.actor_chat, "id", None),
        )
        return

    original = await find_message_by_admin_chat_id(session, event.message_id)
    if original is None or original.user_chat_message_id is None:
        logger.info(
            "Reaction on admin-chat message %s doesn't map to any known ticket message — nothing to mirror.",
            event.message_id,
        )
        return

    logger.info(
        "Mirroring reaction %s -> user %s (message %s)",
        [r.emoji if hasattr(r, "emoji") else r.type for r in event.new_reaction],
        original.user_telegram_id,
        original.user_chat_message_id,
    )

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
    except TelegramBadRequest as e:
        # Some message types / already-deleted messages don't support reactions, or the
        # emoji requires Telegram Premium on the recipient's side — not worth surfacing
        # to the admin as an error, just log for diagnostics.
        logger.info(
            "Could not mirror reaction to user %s on message %s: %s",
            original.user_telegram_id,
            original.user_chat_message_id,
            e,
        )
    except Exception:
        logger.exception("Failed to mirror reaction to user")
