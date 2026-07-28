from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.commands import ADMIN_COMMANDS
from app.middlewares.admin_only import IsAdmin, IsAdminChat

router = Router(name="admin_help")


@router.message(IsAdminChat(), IsAdmin(), Command("help"))
async def cmd_help(message: Message) -> None:
    lines = ["Список команд администратора:", ""]
    for cmd in ADMIN_COMMANDS:
        lines.append(f"/{cmd.command} — {cmd.description}")
    lines += [
        "",
        "Ответ пользователю: свайпом (Reply) на его сообщение в этом чате.",
    ]
    await message.answer("\n".join(lines))
