from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.commands import ADMIN_COMMANDS, USER_COMMANDS
from app.config import settings
from app.logging_conf import setup_logging
from app.services.auto_close import auto_close_loop
from app.services.backup import scheduled_backup_loop

logger = logging.getLogger(__name__)

# Retries forever with capped exponential backoff, so a transient Telegram/DB/Redis
# outage causes a retry instead of the container exiting and staying down.
MAX_BACKOFF_SECONDS = 60


async def set_commands(bot) -> None:
    await bot.set_my_commands(USER_COMMANDS)
    if settings.ADMIN_CHAT_ID:
        try:
            from aiogram.types import BotCommandScopeChat

            await bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=settings.ADMIN_CHAT_ID)
            )
        except Exception:
            logger.exception("Failed to set admin command scope (non-fatal)")


async def run_polling() -> None:
    # Built once: aiogram routers are module-level singletons and cannot be attached to a
    # second Dispatcher, so create_dispatcher() must not be called again on retry.
    dp = create_dispatcher()

    backoff = 1
    while True:
        bot = create_bot()
        try:
            await set_commands(bot)
            await bot.delete_webhook(drop_pending_updates=False)
            logger.info("Starting bot in long-polling mode")
            backoff = 1  # reset once we've successfully started
            await dp.start_polling(
                bot,
                polling_timeout=30,
                handle_signals=True,
                allowed_updates=dp.resolve_used_update_types(),
            )
            # start_polling returns on graceful shutdown (signal) — exit the loop.
            return
        except asyncio.CancelledError:
            raise
        except TelegramUnauthorizedError:
            logger.error(
                "Telegram says BOT_TOKEN is invalid (Unauthorized). This is not a bug — "
                "check the BOT_TOKEN variable: it must be copied exactly as given by "
                "@BotFather, with no missing characters and no extra spaces. The bot "
                "cannot start until this is fixed; retrying in %s seconds in case it's "
                "corrected without a redeploy.",
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
        except Exception:
            logger.exception(
                "Polling crashed, restarting in %s seconds instead of exiting", backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
        finally:
            await bot.session.close()


async def run_webhook() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    await set_commands(bot)
    await bot.set_webhook(settings.WEBHOOK_URL + settings.WEBHOOK_PATH)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.WEBAPP_HOST, settings.WEBAPP_PORT)
    logger.info("Starting bot in webhook mode on %s:%s", settings.WEBAPP_HOST, settings.WEBAPP_PORT)
    await site.start()

    # Keep the process alive
    while True:
        await asyncio.sleep(3600)


async def run_with_background_tasks(entrypoint) -> None:
    backup_task = asyncio.create_task(scheduled_backup_loop(), name="scheduled_backup")
    auto_close_task = asyncio.create_task(auto_close_loop(), name="auto_close_tickets")
    try:
        await entrypoint()
    finally:
        backup_task.cancel()
        auto_close_task.cancel()


def run_migrations() -> None:
    """Applies Alembic migrations before the bot starts.

    docker-compose has a dedicated 'migrate' service for this, but platforms like
    Railway/Render don't read docker-compose.yml at all — each service is deployed
    independently, so that step never runs there and the database ends up with no
    tables. Running migrations here, unconditionally, makes startup correct on any
    platform. It's a no-op (a few hundred ms) if the schema is already up to date,
    since Alembic tracks the applied revision in the database itself.
    """
    import subprocess

    logger.info("Applying database migrations (alembic upgrade head)...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(
            "Database migration failed — the bot cannot start without a valid schema.\n"
            "--- alembic stdout ---\n%s\n--- alembic stderr ---\n%s",
            result.stdout,
            result.stderr,
        )
        raise SystemExit(1)
    logger.info("Migrations applied successfully.")


def main() -> None:
    setup_logging()
    run_migrations()
    if settings.WEBHOOK_URL:
        asyncio.run(run_with_background_tasks(run_webhook))
    else:
        asyncio.run(run_with_background_tasks(run_polling))


if __name__ == "__main__":
    main()
