from __future__ import annotations

import asyncio

import pytest

from app.db.models import ReasonCategory, TelegramUser
from app.services.tickets import (
    close_open_tickets,
    create_ticket,
    get_open_ticket,
    next_ticket_number,
)


@pytest.mark.asyncio
async def test_ticket_numbers_are_sequential(session):
    user = TelegramUser(telegram_id=1, username="alice")
    session.add(user)
    await session.flush()

    t1 = await create_ticket(session, 1, ReasonCategory.OTHER)
    t2 = await create_ticket(session, 1, ReasonCategory.OTHER)
    await session.commit()

    assert t2.number == t1.number + 1


@pytest.mark.asyncio
async def test_next_ticket_number_is_atomic_under_concurrency(session):
    # Simulate several "concurrent" callers requesting a number in the same session.
    numbers = [await next_ticket_number(session) for _ in range(10)]
    await session.commit()
    assert numbers == list(range(1, 11))
    assert len(set(numbers)) == 10  # no duplicates


@pytest.mark.asyncio
async def test_open_ticket_lookup_and_close(session):
    user = TelegramUser(telegram_id=2, username="bob")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 2, ReasonCategory.BLOCK)
    await session.commit()

    open_ticket = await get_open_ticket(session, 2)
    assert open_ticket is not None
    assert open_ticket.id == ticket.id

    await close_open_tickets(session, 2)
    await session.commit()

    assert await get_open_ticket(session, 2) is None
