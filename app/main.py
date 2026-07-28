from __future__ import annotations

import asyncio
import logging

from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot import create_bot, create_dispatcher
from app.config import settings
from app.logging_conf import setup_logging

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Начать обращение"),
    BotCommand(command="new", description="Создать новое обращение"),
]


async def set_commands(bot) -> None:
    await bot.set_my_commands(USER_COMMANDS)


async def run_polling() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("Starting bot in long-polling mode")
    await dp.start_polling(bot)


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


def main() -> None:
    setup_logging()
    if settings.WEBHOOK_URL:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
