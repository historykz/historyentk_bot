from __future__ import annotations

from aiogram.types import BotCommand

USER_COMMANDS = [
    BotCommand(command="start", description="Начать обращение"),
    BotCommand(command="new", description="Создать новое обращение"),
    BotCommand(command="help", description="Список команд"),
]

# Command list Telegram shows to admins when they type "/" inside the admin chat,
# and what /help prints there.
ADMIN_COMMANDS = [
    BotCommand(command="cancel", description="Отменить текущее незавершённое действие"),
    BotCommand(command="help", description="Список всех команд"),
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
