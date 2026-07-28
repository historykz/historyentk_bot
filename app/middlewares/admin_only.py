from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.admin_ids


class IsAdminChat(BaseFilter):
    """True when the update originates from the configured admin group/chat."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
        return chat is not None and chat.id == settings.ADMIN_CHAT_ID
