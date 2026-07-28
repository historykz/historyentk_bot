from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.middlewares.admin_only import IsAdmin, IsAdminChat

router = Router(name="admin_cancel")


@router.message(IsAdminChat(), IsAdmin(), Command("cancel"))
async def cancel_any_flow(message: Message, state: FSMContext) -> None:
    """Escape hatch: clears whatever multi-step flow (requisites, payment settings,
    payment confirmation, custom period, etc.) the admin might be stuck in, so they
    are never blocked from using any other command or from replying to a user."""
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.reply("Активных незавершённых действий не было.")
    else:
        await message.reply("Текущее действие отменено. Можно продолжать как обычно.")
