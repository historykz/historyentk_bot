from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramNetworkError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


class UserUnreachable(Exception):
    """Raised when a message cannot be delivered because the user blocked the bot / deleted the account."""


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_fixed(2),
    retry=retry_if_exception_type((TelegramNetworkError,)),
)
async def send_with_retry(coro_factory):
    """coro_factory is a zero-arg callable returning a fresh coroutine (bot.send_x(...)) so retries
    actually re-issue the call rather than re-awaiting an already-consumed coroutine."""
    try:
        return await coro_factory()
    except TelegramRetryAfter as e:
        import asyncio

        logger.warning("Flood control: sleeping %s seconds", e.retry_after)
        await asyncio.sleep(e.retry_after)
        return await coro_factory()
    except TelegramForbiddenError as e:
        raise UserUnreachable(str(e)) from e
