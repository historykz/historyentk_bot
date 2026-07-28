from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import settings
from app.logging_conf import setup_logging
from app.services.backup import scheduled_backup_loop

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Начать обращение"),
    BotCommand(command="new", description="Создать новое обращение"),
]

# Command list Telegram shows to admins when they type "/" inside the admin chat.
ADMIN_COMMANDS = [
    BotCommand(command="cancel", description="Отменить текущее незавершённое действие"),
    BotCommand(command="history", description="История обращений пользователя"),
    BotCommand(command="ticket", description="Показать обращение по номеру"),
    BotCommand(command="open", description="Открытые обращения без ответа"),
    BotCommand(command="answered", description="Отвеченные обращения"),
    BotCommand(command="user", description="Карточка пользователя"),
    BotCommand(command="finance", description="Финансовая статистика"),
    BotCommand(command="stats", description="Статистика обращений"),
    BotCommand(command="report", description="Общий отчёт"),
    BotCommand(command="export_report", description="Выгрузить отчёт (CSV/Excel)"),
    BotCommand(command="payment_settings", description="Настроить реквизиты"),
    BotCommand(command="cancel_payment", description="Отменить подтверждённую оплату"),
    BotCommand(command="backup", description="Создать резервную копию БД"),
    BotCommand(command="backups", description="Список резервных копий"),
    BotCommand(command="restore", description="Восстановить БД из резервной копии"),
]

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
    try:
        await entrypoint()
    finally:
        backup_task.cancel()


def main() -> None:
    setup_logging()
    if settings.WEBHOOK_URL:
        asyncio.run(run_with_background_tasks(run_webhook))
    else:
        asyncio.run(run_with_background_tasks(run_polling))


if __name__ == "__main__":
    main()
