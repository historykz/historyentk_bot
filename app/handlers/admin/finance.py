from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.admin_kb import period_keyboard
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.finance import build_finance_report
from app.states.admin_states import HistoryLookup
from app.utils.time_utils import now_local, parse_ddmmyyyy, period_bounds

router = Router(name="admin_finance")

PERIOD_LABELS = {"today": "сегодня", "week": "текущая неделя", "month": "текущий месяц", "all": "весь период"}


@router.message(IsAdminChat(), IsAdmin(), Command("finance"))
async def cmd_finance(message: Message) -> None:
    await message.reply("Выберите период:", reply_markup=period_keyboard("fin"))


@router.message(IsAdminChat(), IsAdmin(), Command("finance_today"))
async def cmd_finance_today(message: Message, session: AsyncSession) -> None:
    await _send_finance(message, session, "today")


@router.message(IsAdminChat(), IsAdmin(), Command("finance_week"))
async def cmd_finance_week(message: Message, session: AsyncSession) -> None:
    await _send_finance(message, session, "week")


@router.message(IsAdminChat(), IsAdmin(), Command("finance_month"))
async def cmd_finance_month(message: Message, session: AsyncSession) -> None:
    await _send_finance(message, session, "month")


@router.message(IsAdminChat(), IsAdmin(), Command("finance_all"))
async def cmd_finance_all(message: Message, session: AsyncSession) -> None:
    await _send_finance(message, session, "all")


async def _send_finance(message: Message, session: AsyncSession, period: str) -> None:
    start, end = period_bounds(period)
    report = await build_finance_report(session, start, end, PERIOD_LABELS[period])
    await message.answer(report.render())


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("fin:"))
async def finance_period_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    period = callback.data.split(":")[1]
    await callback.answer()

    if period == "custom":
        await state.set_state(HistoryLookup.awaiting_period_start)
        await state.update_data(report_kind="finance")
        await callback.message.reply("Введите дату начала в формате ДД.ММ.ГГГГ")
        return

    start, end = period_bounds(period)
    report = await build_finance_report(session, start, end, PERIOD_LABELS[period])
    await callback.message.answer(report.render())


@router.message(HistoryLookup.awaiting_period_start)
async def period_start_input(message: Message, state: FSMContext) -> None:
    try:
        start = parse_ddmmyyyy(message.text)
    except ValueError:
        await message.reply("Неверный формат. Введите дату в формате ДД.ММ.ГГГГ")
        return
    await state.update_data(period_start=start.isoformat())
    await state.set_state(HistoryLookup.awaiting_period_end)
    await message.reply("Введите дату окончания в формате ДД.ММ.ГГГГ")


@router.message(HistoryLookup.awaiting_period_end)
async def period_end_input(message: Message, state: FSMContext, session: AsyncSession) -> None:
    from datetime import datetime

    try:
        end = parse_ddmmyyyy(message.text)
    except ValueError:
        await message.reply("Неверный формат. Введите дату в формате ДД.ММ.ГГГГ")
        return

    data = await state.get_data()
    start = datetime.fromisoformat(data["period_start"])
    kind = data.get("report_kind", "finance")
    label = f"{start.strftime('%d.%m.%Y')}–{end.strftime('%d.%m.%Y')}"
    await state.clear()

    if kind == "finance":
        report = await build_finance_report(session, start, end, label)
        await message.answer(report.render())
    elif kind == "stats":
        from app.services.stats import build_ticket_stats

        stats = await build_ticket_stats(session, start, end, label)
        await message.answer(stats.render())
    elif kind == "report":
        from app.handlers.admin.report import render_combined_report

        text = await render_combined_report(session, start, end, label)
        await message.answer(text)
