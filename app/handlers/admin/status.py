from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TICKET_STATUS_LABELS, TicketStatus
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.tickets import get_ticket_by_id
from app.utils.time_utils import now_local

router = Router(name="admin_status")


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("status:"))
async def show_status_menu(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":")[1])
    await callback.answer()
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"setstatus:{ticket_id}:{status.value}")]
        for status, label in TICKET_STATUS_LABELS.items()
    ]
    await callback.message.reply("Выберите новый статус обращения:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("setstatus:"))
async def set_status(callback: CallbackQuery, session: AsyncSession) -> None:
    _, ticket_id, status_value = callback.data.split(":")
    await callback.answer()
    ticket = await get_ticket_by_id(session, int(ticket_id))
    if ticket is None:
        await callback.message.reply("Обращение не найдено.")
        return
    ticket.status = TicketStatus(status_value)
    await session.flush()
    await callback.message.reply(f"Статус обращения #{ticket.number} изменён на «{TICKET_STATUS_LABELS[ticket.status]}».")


@router.callback_query(IsAdminChat(), IsAdmin(), F.data.startswith("close:"))
async def close_ticket(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[1])
    await callback.answer()
    ticket = await get_ticket_by_id(session, ticket_id)
    if ticket is None:
        await callback.message.reply("Обращение не найдено.")
        return
    ticket.status = TicketStatus.CLOSED
    ticket.is_open = False
    ticket.closed_at = now_local()
    await session.flush()
    await callback.message.reply(f"Обращение #{ticket.number} закрыто.")
