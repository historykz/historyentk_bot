from __future__ import annotations

import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.middlewares.admin_only import IsAdmin, IsAdminChat

# Registered LAST of all routers in app/bot.py — reached only if literally nothing
# else (no command, no callback flow, no pending FSM state) claimed the message.
# This turns "the bot says absolutely nothing" into a visible, actionable hint, and
# logs the current FSM state so a silent failure can actually be diagnosed from the
# Deploy Logs instead of guessed at.
router = Router(name="admin_catch_all")
logger = logging.getLogger(__name__)


@router.message(IsAdminChat(), IsAdmin())
async def unhandled_admin_message(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    logger.warning(
        "Unhandled admin-chat message from %s (state=%s, text=%r) — nothing claimed it.",
        message.from_user.id,
        current_state,
        message.text,
    )
    await message.reply(
        "Не удалось понять это сообщение в текущем контексте.\n\n"
        "Если вы вводили сумму, реквизиты или другой текст по запросу бота, а бот "
        "не отреагировал — это значит, что бот \"забыл\", чего ждал (например, из-за "
        "перезапуска между вопросом и ответом). Отправьте /cancel и повторите "
        "действие заново."
    )
