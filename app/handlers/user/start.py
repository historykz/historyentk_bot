from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.keyboards.user_kb import (
    new_ticket_confirm_keyboard,
    reason_keyboard,
)
from app.services.tickets import get_open_ticket, upsert_user
from app.states.user_states import ConfirmNewTicket, UserFlow

router = Router(name="user_start")
logger = logging.getLogger(__name__)


def greeting_text(display_name: str | None) -> str:
    channel = settings.CHANNEL_USERNAME
    title = settings.CHANNEL_TITLE
    if display_name:
        header = f"Здравствуйте, {display_name}!"
    else:
        header = "Здравствуйте!"
    return (
        f"{header}\n\n"
        f'Вас приветствует администрация канала "{title}" — {channel}.\n\n'
        "Пожалуйста, выберите причину обращения:"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    tg_user = message.from_user
    await upsert_user(session, tg_user)

    open_ticket = await get_open_ticket(session, tg_user.id)
    if open_ticket is not None:
        await state.update_data(pending_new_ticket=True)
        await state.set_state(ConfirmNewTicket.confirm)
        await message.answer(
            "У вас уже есть открытое обращение. Вы хотите создать новое?",
            reply_markup=new_ticket_confirm_keyboard(),
        )
        return

    display = f"@{tg_user.username}" if tg_user.username else (tg_user.first_name or None)
    await state.set_state(UserFlow.choosing_reason)
    await message.answer(greeting_text(display), reply_markup=reason_keyboard())


@router.message(F.text == "/new")
async def cmd_new_ticket(message: Message, state: FSMContext, session: AsyncSession) -> None:
    tg_user = message.from_user
    await upsert_user(session, tg_user)

    open_ticket = await get_open_ticket(session, tg_user.id)
    if open_ticket is not None:
        await state.set_state(ConfirmNewTicket.confirm)
        await message.answer(
            "У вас уже есть открытое обращение. Вы хотите создать новое?",
            reply_markup=new_ticket_confirm_keyboard(),
        )
        return

    await state.set_state(UserFlow.choosing_reason)
    await message.answer("Выберите причину обращения:", reply_markup=reason_keyboard())
