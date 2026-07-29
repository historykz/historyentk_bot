from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.db.models import ReasonCategory, TelegramUser, Ticket, TicketStatus
from app.services.auto_close import auto_close_inactive_tickets
from app.services.tickets import create_ticket, get_open_ticket


@pytest.mark.asyncio
async def test_inactive_ticket_gets_closed(session):
    user = TelegramUser(telegram_id=1, username="alice")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 1, ReasonCategory.OTHER)
    await session.commit()

    # Simulate the ticket having been last touched 31 minutes ago.
    stale = datetime.now(timezone.utc) - timedelta(minutes=31)
    await session.execute(update(Ticket).where(Ticket.id == ticket.id).values(updated_at=stale))
    await session.commit()

    closed = await auto_close_inactive_tickets(session)
    await session.commit()

    assert ticket.number in closed
    assert await get_open_ticket(session, 1) is None

    refreshed = await session.get(Ticket, ticket.id)
    assert refreshed.status == TicketStatus.CLOSED
    assert refreshed.is_open is False
    assert refreshed.closed_at is not None


@pytest.mark.asyncio
async def test_recently_active_ticket_is_not_closed(session):
    user = TelegramUser(telegram_id=2, username="bob")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 2, ReasonCategory.OTHER)
    await session.commit()
    # updated_at defaults to "now" — well within the inactivity window.

    closed = await auto_close_inactive_tickets(session)
    await session.commit()

    assert ticket.number not in closed
    assert await get_open_ticket(session, 2) is not None


@pytest.mark.asyncio
async def test_already_paid_ticket_is_not_auto_closed(session):
    user = TelegramUser(telegram_id=3, username="carl")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 3, ReasonCategory.PURCHASE, purchase_subcategory="tests")
    ticket.status = TicketStatus.PAID
    await session.commit()

    stale = datetime.now(timezone.utc) - timedelta(minutes=60)
    await session.execute(update(Ticket).where(Ticket.id == ticket.id).values(updated_at=stale))
    await session.commit()

    closed = await auto_close_inactive_tickets(session)
    await session.commit()

    assert ticket.number not in closed
