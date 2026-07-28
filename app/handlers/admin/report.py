from __future__ import annotations

import csv
import io
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentStatus, Payment, ReasonCategory
from app.keyboards.admin_kb import period_keyboard
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.finance import build_finance_report
from app.services.stats import build_ticket_stats
from app.states.admin_states import HistoryLookup
from app.utils.formatting import fmt_money
from app.utils.time_utils import period_bounds
from sqlalchemy import select

router = Router(name="admin_report")

PERIOD_LABELS = {"today": "сегодня", "week": "текущая неделя", "month": "текущий месяц", "all": "весь период"}


async def render_combined_report(session: AsyncSession, start: datetime, end: datetime, label: str) -> str:
    stats = await build_ticket_stats(session, start, end, label)
    finance = await build_finance_report(session, start, end, label)

    lines = [
        f"Общий отчёт за {label}",
        "",
        f"Обращений: {stats.total}",
        f"Уникальных пользователей: {stats.unique_users}",
        f"Покупки: {stats.by_reason.get(ReasonCategory.PURCHASE, 0)}",
        f"Сотрудничество: {stats.by_reason.get(ReasonCategory.COOPERATION, 0)}",
        f"Причина блокировки: {stats.by_reason.get(ReasonCategory.BLOCK, 0)}",
        f"Свой вопрос: {stats.by_reason.get(ReasonCategory.OTHER, 0)}",
        "",
        f"Подтверждённых оплат: {finance.confirmed_count}",
        f"Доход от покупок: {fmt_money(finance.purchases_total)}",
        f"Доход от сотрудничества: {fmt_money(finance.cooperation_total)}",
        f"Общий оборот: {fmt_money(finance.total_turnover)}",
    ]
    return "\n".join(lines)


@router.message(IsAdminChat(), IsAdmin(), Command("report"))
async def cmd_report(message: Message) -> None:
    await message.reply("Выберите период:", reply_markup=period_keyboard("rep"))


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("rep:"))
async def report_period_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    period = callback.data.split(":")[1]
    await callback.answer()

    if period == "custom":
        await state.set_state(HistoryLookup.awaiting_period_start)
        await state.update_data(report_kind="report")
        await callback.message.reply("Введите дату начала в формате ДД.ММ.ГГГГ")
        return

    start, end = period_bounds(period)
    text = await render_combined_report(session, start, end, PERIOD_LABELS[period])
    await callback.message.answer(text)


@router.message(IsAdminChat(), IsAdmin(), Command("export_report"))
async def cmd_export_report(message: Message) -> None:
    rows = [
        [InlineKeyboardButton(text="Сегодня (CSV)", callback_data="exp:today:csv")],
        [InlineKeyboardButton(text="Эта неделя (CSV)", callback_data="exp:week:csv")],
        [InlineKeyboardButton(text="Этот месяц (CSV)", callback_data="exp:month:csv")],
        [InlineKeyboardButton(text="Весь период (CSV)", callback_data="exp:all:csv")],
        [InlineKeyboardButton(text="Сегодня (Excel)", callback_data="exp:today:xlsx")],
        [InlineKeyboardButton(text="Эта неделя (Excel)", callback_data="exp:week:xlsx")],
        [InlineKeyboardButton(text="Этот месяц (Excel)", callback_data="exp:month:xlsx")],
        [InlineKeyboardButton(text="Весь период (Excel)", callback_data="exp:all:xlsx")],
    ]
    await message.reply("Выберите период и формат:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("exp:"))
async def do_export(callback: CallbackQuery, session: AsyncSession) -> None:
    _, period, fmt = callback.data.split(":")
    await callback.answer()
    start, end = period_bounds(period)

    result = await session.execute(
        select(Payment).where(
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.counted_in_revenue.is_(True),
            Payment.confirmed_at >= start,
            Payment.confirmed_at <= end,
        ).order_by(Payment.confirmed_at)
    )
    payments = result.scalars().all()

    headers = ["ID оплаты", "Обращение", "Telegram ID", "Тип", "Сумма", "Банк", "Подтверждена", "Администратор"]
    data_rows = [
        [
            p.id,
            p.ticket_id,
            p.user_telegram_id,
            p.payment_type.value,
            str(p.confirmed_amount),
            p.bank_name or "-",
            p.confirmed_at.strftime("%d.%m.%Y %H:%M") if p.confirmed_at else "-",
            p.confirmed_by_admin_id,
        ]
        for p in payments
    ]

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(data_rows)
        file = BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=f"report_{period}.csv")
    else:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in data_rows:
            ws.append(row)
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        file = BufferedInputFile(bio.read(), filename=f"report_{period}.xlsx")

    await callback.message.answer_document(file, caption=f"Отчёт: {period}")
