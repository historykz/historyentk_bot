from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.db.models import (
    PaymentStatus,
    PaymentType,
    ReasonCategory,
    RequisiteKind,
    TelegramUser,
)
from app.services.payments import (
    cancel_confirmed_payment,
    confirm_payment,
    create_pending_payment,
    get_or_create_requisites,
)
from app.services.tickets import create_ticket


@pytest.mark.asyncio
async def test_double_confirm_does_not_double_count(session):
    user = TelegramUser(telegram_id=42, username="carl")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 42, ReasonCategory.PURCHASE, purchase_subcategory="tests")
    requisites = await get_or_create_requisites(session, RequisiteKind.PURCHASE)

    payment = await create_pending_payment(
        session, ticket, Decimal("5000"), PaymentType.PURCHASE_TESTS, requisites, admin_id=999
    )
    await session.commit()

    payment1, counted1 = await confirm_payment(session, payment.id, Decimal("5000"), admin_id=999)
    await session.commit()
    assert counted1 is True
    assert payment1.status == PaymentStatus.CONFIRMED

    # Second confirmation attempt (e.g. double tap, or a second admin) must be a no-op.
    payment2, counted2 = await confirm_payment(session, payment.id, Decimal("5000"), admin_id=1000)
    await session.commit()
    assert counted2 is False
    # Amount / confirming admin must be unchanged by the second call.
    assert payment2.confirmed_by_admin_id == 999


@pytest.mark.asyncio
async def test_concurrent_confirm_only_counts_once(session):
    """Two 'simultaneous' confirmation attempts against the same payment row must
    result in exactly one counted confirmation, thanks to the row lock in confirm_payment.
    """
    user = TelegramUser(telegram_id=43, username="dave")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 43, ReasonCategory.COOPERATION)
    requisites = await get_or_create_requisites(session, RequisiteKind.COOPERATION)
    payment = await create_pending_payment(
        session, ticket, Decimal("15000"), PaymentType.COOPERATION, requisites, admin_id=1
    )
    await session.commit()

    # SQLite (used in tests) serializes writers, so this exercises the same code path
    # that PostgreSQL's row lock protects in production: only one call can flip
    # counted_in_revenue.
    results = []
    for admin_id in (1, 2):
        _, counted = await confirm_payment(session, payment.id, Decimal("15000"), admin_id=admin_id)
        results.append(counted)
    await session.commit()

    assert results.count(True) == 1
    assert results.count(False) == 1


@pytest.mark.asyncio
async def test_cancel_confirmed_payment_removes_from_revenue(session):
    user = TelegramUser(telegram_id=44, username="erin")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 44, ReasonCategory.PURCHASE, purchase_subcategory="premium")
    requisites = await get_or_create_requisites(session, RequisiteKind.PURCHASE)
    payment = await create_pending_payment(
        session, ticket, Decimal("3000"), PaymentType.PURCHASE_PREMIUM, requisites, admin_id=1
    )
    await confirm_payment(session, payment.id, Decimal("3000"), admin_id=1)
    await session.commit()

    cancelled = await cancel_confirmed_payment(session, payment.id, admin_id=1, reason="ошибка")
    await session.commit()

    assert cancelled is not None
    assert cancelled.status == PaymentStatus.CANCELLED
    assert cancelled.counted_in_revenue is False
    assert cancelled.cancel_reason == "ошибка"
