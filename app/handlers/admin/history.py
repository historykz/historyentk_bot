from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PaymentStatus, TICKET_STATUS_LABELS, Ticket, TicketMessage, MessageDirection, TelegramUser
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.tickets import get_ticket_by_number
from app.utils.formatting import fmt_money
from app.utils.time_utils import fmt_dt

router = Router(name="admin_history")

PAGE_SIZE = 5


def render_ticket_summary(ticket: Ticket) -> str:
    last_user_msg = next(
        (m for m in reversed(ticket.messages) if m.direction == MessageDirection.USER_TO_ADMIN and m.text), None
    )
    last_admin_msg = next(
        (m for m in reversed(ticket.messages) if m.direction == MessageDirection.ADMIN_TO_USER and m.text), None
    )
    last_payment = ticket.payments[-1] if ticket.payments else None

    lines = [
        f"Обращение #{ticket.number}",
        "",
        f"Дата: {fmt_dt(ticket.created_at)}",
        f"Причина: {ticket.reason_label}",
        "",
    ]
    if last_user_msg:
        lines += ["Сообщение пользователя:", "", f'"{last_user_msg.text}"', ""]
    if last_admin_msg:
        lines += ["Ответ администратора:", "", f'"{last_admin_msg.text}"', ""]
    if last_payment:
        lines.append(f"Сумма: {fmt_money(last_payment.requested_amount)}")
        status = "подтверждена" if last_payment.status == PaymentStatus.CONFIRMED else last_payment.status.value
        lines.append(f"Оплата: {status}")
        if last_payment.confirmed_at:
            lines.append(f"Оплата подтверждена: {fmt_dt(last_payment.confirmed_at)}")
    lines.append(f"Статус: {TICKET_STATUS_LABELS[ticket.status]}")
    return "\n".join(lines)


@router.message(IsAdminChat(), IsAdmin(), Command("ticket"))
async def cmd_ticket(message: Message, session: AsyncSession) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.reply("Использование: /ticket номер")
        return
    ticket = await get_ticket_by_number(session, int(parts[1].strip()))
    if ticket is None:
        await message.reply("Обращение не найдено.")
        return
    await session.refresh(ticket, attribute_names=["messages", "payments"])
    await message.reply(render_ticket_summary(ticket))


@router.message(IsAdminChat(), IsAdmin(), Command("history"))
async def cmd_history(message: Message, session: AsyncSession) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Использование: /history ID или /history @username")
        return
    arg = parts[1].strip()

    if arg.startswith("@"):
        result = await session.execute(select(TelegramUser).where(TelegramUser.username == arg[1:]))
        user = result.scalar_one_or_none()
        if user is None:
            await message.reply("Пользователь не найден.")
            return
        telegram_id = user.telegram_id
    elif arg.isdigit():
        telegram_id = int(arg)
    else:
        await message.reply("Использование: /history ID или /history @username")
        return

    result = await session.execute(
        select(Ticket).where(Ticket.user_telegram_id == telegram_id).order_by(Ticket.id.desc()).limit(PAGE_SIZE)
    )
    tickets = result.scalars().all()
    if not tickets:
        await message.reply("Обращений не найдено.")
        return

    for t in tickets:
        await session.refresh(t, attribute_names=["messages", "payments"])
        await message.answer(render_ticket_summary(t))


@router.message(IsAdminChat(), IsAdmin(), Command("open"))
async def cmd_open(message: Message, session: AsyncSession) -> None:
    result = await session.execute(
        select(Ticket)
        .where(Ticket.status.notin_(["answered", "paid", "closed"]))
        .order_by(Ticket.created_at.desc())
        .limit(PAGE_SIZE)
    )
    tickets = result.scalars().all()
    if not tickets:
        await message.reply("Открытых обращений без ответа нет.")
        return
    lines = ["Последние открытые обращения без ответа:", ""]
    for t in tickets:
        lines.append(f"#{t.number} — {t.reason_label} — {fmt_dt(t.created_at)}")
    await message.reply("\n".join(lines))


@router.message(IsAdminChat(), IsAdmin(), Command("answered"))
async def cmd_answered(message: Message, session: AsyncSession) -> None:
    result = await session.execute(
        select(Ticket).where(Ticket.status == "answered").order_by(Ticket.updated_at.desc()).limit(PAGE_SIZE)
    )
    tickets = result.scalars().all()
    if not tickets:
        await message.reply("Отвеченных обращений пока нет.")
        return
    lines = ["Последние отвеченные обращения:", ""]
    for t in tickets:
        lines.append(f"#{t.number} — {t.reason_label} — {fmt_dt(t.updated_at)}")
    await message.reply("\n".join(lines))


@router.message(IsAdminChat(), IsAdmin(), Command("user"))
async def cmd_user_card(message: Message, session: AsyncSession) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.reply("Использование: /user Telegram_ID")
        return
    telegram_id = int(parts[1].strip())

    user = await session.get(TelegramUser, telegram_id)
    if user is None:
        await message.reply("Пользователь не найден.")
        return

    tickets_result = await session.execute(
        select(Ticket).where(Ticket.user_telegram_id == telegram_id).order_by(Ticket.created_at)
    )
    tickets = tickets_result.scalars().all()

    payments_result = await session.execute(
        select(func.count(Payment.id), func.coalesce(func.sum(Payment.confirmed_amount), 0)).where(
            Payment.user_telegram_id == telegram_id,
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.counted_in_revenue.is_(True),
        )
    )
    payments_count, total_paid = payments_result.one()

    first_dt = tickets[0].created_at if tickets else None
    last_dt = tickets[-1].created_at if tickets else None

    lines = [
        "Карточка пользователя",
        "",
        f"Имя: {user.first_name or '-'}",
        f"Фамилия: {user.last_name or '-'}",
        f"Username: {'@' + user.username if user.username else '-'}",
        f"Telegram ID: {user.telegram_id}",
        f"Дата первого обращения: {fmt_dt(first_dt)}",
        f"Дата последнего обращения: {fmt_dt(last_dt)}",
        f"Количество обращений: {len(tickets)}",
        f"Количество покупок: {payments_count}",
        f"Общая сумма подтверждённых оплат: {fmt_money(total_paid)}",
        "",
        "Последние обращения:",
    ]
    for t in tickets[-5:]:
        lines.append(f"#{t.number} — {t.reason_label} — {fmt_dt(t.created_at)}")

    await message.reply("\n".join(lines))
