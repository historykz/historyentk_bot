from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, TicketStatus
from app.utils.time_utils import now_local

logger = logging.getLogger(__name__)

# If neither the user nor an admin has sent anything for this long, the ticket is
# considered inactive and gets closed automatically. If the user writes again after
# that, the normal "no open ticket" flow re-asks them to pick a reason — see
# app/handlers/user/messages.py::relay_to_admin and app/handlers/user/start.py.
INACTIVITY_TIMEOUT_MINUTES = 30
CHECK_INTERVAL_SECONDS = 300  # check every 5 minutes


async def auto_close_inactive_tickets(session: AsyncSession) -> list[int]:
    """Closes any open ticket whose last activity (tracked via updated_at, which is
    bumped on every incoming user message and every admin reply) is older than
    INACTIVITY_TIMEOUT_MINUTES. Returns the list of closed ticket numbers."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)

    result = await session.execute(
        select(Ticket).where(
            Ticket.is_open.is_(True),
            Ticket.status.notin_([TicketStatus.CLOSED, TicketStatus.PAID]),
            Ticket.updated_at < cutoff,
        )
    )
    tickets = result.scalars().all()

    closed_numbers: list[int] = []
    for ticket in tickets:
        ticket.is_open = False
        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = now_local()
        closed_numbers.append(ticket.number)

    if closed_numbers:
        await session.flush()

    return closed_numbers


async def auto_close_loop(interval_seconds: int = CHECK_INTERVAL_SECONDS) -> None:
    """Background task: periodically closes inactive tickets. Any single failure is
    logged and does not stop the loop, same pattern as the scheduled backup task."""
    from app.db.session import async_session_maker  # lazy: avoids building the engine at import time

    while True:
        try:
            async with async_session_maker() as session:
                closed = await auto_close_inactive_tickets(session)
                await session.commit()
                if closed:
                    logger.info("Auto-closed inactive tickets: %s", closed)
        except Exception:
            logger.exception("Auto-close loop failed")
        await asyncio.sleep(interval_seconds)
