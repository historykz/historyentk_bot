from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent
from redis.asyncio import Redis

from app.config import settings
from app.middlewares.db import DbSessionMiddleware

from app.handlers.admin import (
    backup as admin_backup,
    cancel as admin_cancel,
    finance as admin_finance,
    help as admin_help,
    history as admin_history,
    payment as admin_payment,
    payment_settings as admin_payment_settings,
    reaction as admin_reaction,
    report as admin_report,
    reply as admin_reply,
    requisites as admin_requisites,
    stats as admin_stats,
    status as admin_status,
)
from app.handlers.user import (
    help as user_help,
    messages as user_messages,
    reason as user_reason,
    receipt as user_receipt,
    start as user_start,
)

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    # A bounded request timeout keeps a single slow/stuck Telegram API call from
    # freezing the whole bot — without it, aiohttp has no default limit here.
    session = AiohttpSession(timeout=30)
    return Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    redis: Redis | None = None
    if settings.REDIS_URL:
        redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=10,
            socket_connect_timeout=10,
            health_check_interval=30,
        )
        storage = RedisStorage(redis=redis)
        logger.info("Using Redis for FSM storage and spam guard (%s)", settings.REDIS_URL)
    else:
        storage = MemoryStorage()
        logger.warning(
            "REDIS_URL is not set — falling back to in-memory FSM storage and spam guard. "
            "This is fine for a single-instance deployment, but conversation state and "
            "throttling counters will reset on every restart."
        )

    dp = Dispatcher(storage=storage)

    # Available to every handler via dependency injection. May be None — handlers that
    # need it use app.services.spam_guard.create_spam_guard(redis), which transparently
    # falls back to an in-memory guard when redis is None.
    dp["redis"] = redis

    dp.update.middleware(DbSessionMiddleware())

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        """Global safety net: log any unhandled exception from a handler and keep the
        bot running instead of letting one bad update take everything down."""
        logger.exception(
            "Unhandled error while processing update %s: %s",
            getattr(event.update, "update_id", "?"),
            event.exception,
        )
        try:
            message = event.update.message or (event.update.callback_query.message if event.update.callback_query else None)
            if message is not None:
                await message.answer(
                    "Произошла временная ошибка. Попробуйте повторить действие ещё раз."
                )
        except Exception:
            logger.exception("Failed to notify user about the error")
        return True

    # /cancel is registered first: an admin stuck in any multi-step flow must always be
    # able to escape it, without it swallowing anything else.
    dp.include_router(admin_cancel.router)

    # Admin routers: gated by IsAdminChat/IsAdmin filters, so they only ever consume
    # updates from the configured admin chat. admin_reply.router only matches genuine
    # replies to a forwarded user message (see IsTicketReply), so it never steals input
    # meant for a pending flow (entering an amount, a comment, etc.) below it.
    dp.include_router(admin_reply.router)
    dp.include_router(admin_requisites.router)
    dp.include_router(admin_payment_settings.router)
    dp.include_router(admin_payment.router)
    dp.include_router(admin_history.router)
    dp.include_router(admin_finance.router)
    dp.include_router(admin_stats.router)
    dp.include_router(admin_report.router)
    dp.include_router(admin_status.router)
    dp.include_router(admin_backup.router)
    dp.include_router(admin_help.router)
    dp.include_router(admin_reaction.router)
    # Fallback for "replied to something, but nothing above claimed it" — must stay
    # last among admin routers so it never intercepts a reply meant for a pending flow.
    dp.include_router(admin_reply.fallback_router)

    # User routers. Order matters: the broad "gate before reason chosen" catch-all in
    # user_messages must be registered last so more specific handlers get first refusal.
    dp.include_router(user_start.router)
    dp.include_router(user_help.router)
    dp.include_router(user_reason.router)
    dp.include_router(user_receipt.router)
    dp.include_router(user_messages.router)

    return dp
