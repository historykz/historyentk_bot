from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.config import settings
from app.middlewares.db import DbSessionMiddleware

from app.handlers.admin import (
    finance as admin_finance,
    history as admin_history,
    payment as admin_payment,
    payment_settings as admin_payment_settings,
    report as admin_report,
    reply as admin_reply,
    requisites as admin_requisites,
    stats as admin_stats,
    status as admin_status,
)
from app.handlers.user import (
    messages as user_messages,
    reason as user_reason,
    receipt as user_receipt,
    start as user_start,
)


def create_bot() -> Bot:
    return Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher() -> Dispatcher:
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis=redis)
    dp = Dispatcher(storage=storage)

    # Available to every handler via dependency injection.
    dp["redis"] = redis

    dp.update.middleware(DbSessionMiddleware())

    # Admin routers first: they are gated by IsAdminChat/IsAdmin filters, so they only ever
    # consume updates from the configured admin chat.
    dp.include_router(admin_reply.router)
    dp.include_router(admin_requisites.router)
    dp.include_router(admin_payment_settings.router)
    dp.include_router(admin_payment.router)
    dp.include_router(admin_history.router)
    dp.include_router(admin_finance.router)
    dp.include_router(admin_stats.router)
    dp.include_router(admin_report.router)
    dp.include_router(admin_status.router)

    # User routers. Order matters: the broad "gate before reason chosen" catch-all in
    # user_messages must be registered last so more specific handlers get first refusal.
    dp.include_router(user_start.router)
    dp.include_router(user_reason.router)
    dp.include_router(user_receipt.router)
    dp.include_router(user_messages.router)

    return dp
