from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.commands import USER_COMMANDS

router = Router(name="user_help")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    lines = ["Доступные команды:", ""]
    for cmd in USER_COMMANDS:
        lines.append(f"/{cmd.command} — {cmd.description}")
    await message.answer("\n".join(lines))
