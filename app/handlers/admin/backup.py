from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.backup import BackupError, create_backup, list_backups, restore_backup

router = Router(name="admin_backup")
logger = logging.getLogger(__name__)


class RestoreFlow(StatesGroup):
    awaiting_confirmation = State()


def confirm_restore_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, восстановить (перезаписать данные)", callback_data="restore:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="restore:cancel")],
        ]
    )


@router.message(IsAdminChat(), IsAdmin(), Command("backup"))
async def cmd_backup(message: Message) -> None:
    status = await message.reply("Создаю резервную копию базы данных...")
    try:
        path = await create_backup()
    except BackupError as e:
        await status.edit_text(f"Не удалось создать резервную копию: {e}")
        return
    await message.answer_document(
        FSInputFile(path, filename=path.name),
        caption=f"Резервная копия базы данных: {path.name}",
    )
    await status.delete()


@router.message(IsAdminChat(), IsAdmin(), Command("backups"))
async def cmd_backups(message: Message) -> None:
    backups = list_backups()
    if not backups:
        await message.reply(
            "Сохранённых резервных копий пока нет. Создайте первую командой /backup."
        )
        return
    lines = ["Последние резервные копии на сервере:", ""]
    for p in backups[:10]:
        lines.append(f"• {p.name}")
    lines.append("")
    lines.append(
        "Чтобы получить конкретный файл — используйте /backup для новой копии, "
        "либо скачайте файлы напрямую с сервера из папки backups/."
    )
    await message.reply("\n".join(lines))


@router.message(IsAdminChat(), IsAdmin(), Command("restore"))
async def cmd_restore(message: Message, state: FSMContext) -> None:
    replied = message.reply_to_message
    if replied is None or replied.document is None:
        await message.reply(
            "Чтобы восстановить базу данных, отправьте файл резервной копии (.sql) в этот чат "
            "и затем ответьте на него командой /restore (свайпом Reply на сообщение с файлом)."
        )
        return

    filename = replied.document.file_name or ""
    if not filename.endswith(".sql"):
        await message.reply("Файл резервной копии должен иметь расширение .sql")
        return

    await state.set_state(RestoreFlow.awaiting_confirmation)
    await state.update_data(restore_file_id=replied.document.file_id, restore_filename=filename)
    await message.reply(
        "Внимание! Восстановление из резервной копии перезапишет текущие данные "
        f"в базе данными из файла «{filename}». Это действие необратимо.\n\n"
        "Продолжить?",
        reply_markup=confirm_restore_keyboard(),
    )


@router.callback_query(IsAdminChat(), IsAdmin(), RestoreFlow.awaiting_confirmation, F.data == "restore:cancel")
async def cancel_restore(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("Восстановление отменено.")


@router.callback_query(IsAdminChat(), IsAdmin(), RestoreFlow.awaiting_confirmation, F.data == "restore:confirm")
async def do_restore(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    file_id = data.get("restore_file_id")
    filename = data.get("restore_filename", "backup.sql")
    await state.clear()

    if not file_id:
        await callback.message.edit_text("Не удалось найти файл резервной копии, попробуйте ещё раз через /restore.")
        return

    await callback.message.edit_text(f"Восстанавливаю базу данных из «{filename}»...")
    try:
        file = await callback.bot.get_file(file_id)
        buf = await callback.bot.download_file(file.file_path)
        sql_bytes = buf.read()
        await restore_backup(sql_bytes)
    except BackupError as e:
        await callback.message.answer(f"Восстановление не удалось: {e}")
        return
    except Exception:
        logger.exception("Unexpected error during restore")
        await callback.message.answer("Восстановление не удалось из-за непредвиденной ошибки. Смотрите журнал бота.")
        return

    await callback.message.answer("База данных успешно восстановлена из резервной копии.")
