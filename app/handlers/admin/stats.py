from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.admin_kb import period_keyboard
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.stats import build_ticket_stats
from app.states.admin_states import HistoryLookup
from app.utils.time_utils import period_bounds

router = Router(name="admin_stats")

PERIOD_LABELS = {"today": "сегодня", "week": "текущая неделя", "month": "текущий месяц", "all": "весь период"}


@router.message(IsAdminChat(), IsAdmin(), Command("stats"))
async def cmd_stats(message: Message) -> None:
    await message.reply("Выберите период:", reply_markup=period_keyboard("st"))


@router.message(IsAdminChat(), IsAdmin(), Command("stats_today"))
async def cmd_stats_today(message: Message, session: AsyncSession) -> None:
    await _send_stats(message, session, "today")


@router.message(IsAdminChat(), IsAdmin(), Command("stats_week"))
async def cmd_stats_week(message: Message, session: AsyncSession) -> None:
    await _send_stats(message, session, "week")


@router.message(IsAdminChat(), IsAdmin(), Command("stats_month"))
async def cmd_stats_month(message: Message, session: AsyncSession) -> None:
    await _send_stats(message, session, "month")


@router.message(IsAdminChat(), IsAdmin(), Command("stats_all"))
async def cmd_stats_all(message: Message, session: AsyncSession) -> None:
    await _send_stats(message, session, "all")


async def _send_stats(message: Message, session: AsyncSession, period: str) -> None:
    start, end = period_bounds(period)
    stats = await build_ticket_stats(session, start, end, PERIOD_LABELS[period])
    await message.answer(stats.render())


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("st:"))
async def stats_period_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    period = callback.data.split(":")[1]
    await callback.answer()

    if period == "custom":
        await state.set_state(HistoryLookup.awaiting_period_start)
        await state.update_data(report_kind="stats")
        await callback.message.reply("Введите дату начала в формате ДД.ММ.ГГГГ")
        return

    start, end = period_bounds(period)
    stats = await build_ticket_stats(session, start, end, PERIOD_LABELS[period])
    await callback.message.answer(stats.render())
