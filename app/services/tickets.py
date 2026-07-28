from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReasonCategory, Ticket, TicketCounter, TicketStatus, TelegramUser
from aiogram.types import User as TgUser


async def upsert_user(session: AsyncSession, tg_user: TgUser) -> TelegramUser:
    user = await session.get(TelegramUser, tg_user.id)
    if user is None:
        user = TelegramUser(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        session.add(user)
    else:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        user.last_name = tg_user.last_name
        user.is_blocked_bot = False
    await session.flush()
    return user


async def next_ticket_number(session: AsyncSession) -> int:
    """Atomically increments and returns the next ticket number using a row lock,
    so concurrent requests never collide."""
    counter = (
        await session.execute(select(TicketCounter).where(TicketCounter.id == 1).with_for_update())
    ).scalar_one_or_none()
    if counter is None:
        counter = TicketCounter(id=1, last_value=0)
        session.add(counter)
        await session.flush()
    counter.last_value += 1
    await session.flush()
    return counter.last_value


async def get_open_ticket(session: AsyncSession, user_telegram_id: int) -> Ticket | None:
    result = await session.execute(
        select(Ticket)
        .where(Ticket.user_telegram_id == user_telegram_id, Ticket.is_open.is_(True))
        .order_by(Ticket.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_ticket(
    session: AsyncSession,
    user_telegram_id: int,
    reason: ReasonCategory,
    purchase_subcategory=None,
) -> Ticket:
    number = await next_ticket_number(session)
    ticket = Ticket(
        number=number,
        user_telegram_id=user_telegram_id,
        reason=reason,
        purchase_subcategory=purchase_subcategory,
        status=TicketStatus.NEW,
        is_open=True,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def close_open_tickets(session: AsyncSession, user_telegram_id: int) -> None:
    await session.execute(
        update(Ticket)
        .where(Ticket.user_telegram_id == user_telegram_id, Ticket.is_open.is_(True))
        .values(is_open=False, status=TicketStatus.CLOSED)
    )


async def get_ticket_by_number(session: AsyncSession, number: int) -> Ticket | None:
    result = await session.execute(select(Ticket).where(Ticket.number == number))
    return result.scalar_one_or_none()


async def get_ticket_by_id(session: AsyncSession, ticket_id: int) -> Ticket | None:
    return await session.get(Ticket, ticket_id)
