from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MessageDirection, MessageKind, TelegramUser, Ticket, TicketMessage
from app.utils.time_utils import now_local


def render_new_appeal_header(user: TelegramUser, ticket: Ticket, is_duplicate: bool = False) -> str:
    full_name = " ".join(filter(None, [user.first_name, user.last_name])) or "-"
    username = f"@{user.username}" if user.username else "отсутствует"
    reason_label = ticket.reason_label
    reason_main = reason_label.split(" — ")[0]
    lines = [
        "Повторное обращение пользователя" if is_duplicate else "Новое обращение",
        "",
        f"Пользователь: {full_name}",
        f"Username: {username}",
        f"Telegram ID: {user.telegram_id}",
        f"Причина обращения: {reason_main}",
    ]
    if ticket.purchase_subcategory:
        lines.append(f"Категория покупки: {reason_label.split(' — ')[1]}")
    now = now_local()
    lines.append(f"Дата: {now.strftime('%d.%m.%Y')}")
    lines.append(f"Время: {now.strftime('%H:%M')}")
    lines.append(f"Номер обращения: #{ticket.number}")
    if is_duplicate:
        lines.append("")
        lines.append("Повторное сообщение пользователя.")
    return "\n".join(lines)


async def save_user_message(
    session: AsyncSession,
    ticket: Ticket,
    user_telegram_id: int,
    kind: MessageKind,
    text: str | None,
    file_id: str | None,
    user_chat_message_id: int | None,
    admin_chat_message_id: int | None,
    is_duplicate_flagged: bool = False,
) -> TicketMessage:
    msg = TicketMessage(
        ticket_id=ticket.id,
        user_telegram_id=user_telegram_id,
        direction=MessageDirection.USER_TO_ADMIN,
        kind=kind,
        text=text,
        file_id=file_id,
        user_chat_message_id=user_chat_message_id,
        admin_chat_message_id=admin_chat_message_id,
        is_duplicate_flagged=is_duplicate_flagged,
    )
    session.add(msg)
    await session.flush()
    return msg


async def save_admin_message(
    session: AsyncSession,
    ticket: Ticket,
    admin_telegram_id: int,
    kind: MessageKind,
    text: str | None,
    file_id: str | None,
) -> TicketMessage:
    msg = TicketMessage(
        ticket_id=ticket.id,
        user_telegram_id=ticket.user_telegram_id,
        direction=MessageDirection.ADMIN_TO_USER,
        kind=kind,
        text=text,
        file_id=file_id,
        admin_telegram_id=admin_telegram_id,
    )
    session.add(msg)
    await session.flush()
    return msg


async def find_message_by_admin_chat_id(session: AsyncSession, admin_chat_message_id: int) -> TicketMessage | None:
    result = await session.execute(
        select(TicketMessage).where(TicketMessage.admin_chat_message_id == admin_chat_message_id)
    )
    return result.scalar_one_or_none()


async def last_user_messages_text(session: AsyncSession, ticket_id: int, limit: int = 5) -> list[str]:
    result = await session.execute(
        select(TicketMessage.text)
        .where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.direction == MessageDirection.USER_TO_ADMIN,
            TicketMessage.text.is_not(None),
        )
        .order_by(TicketMessage.id.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]
