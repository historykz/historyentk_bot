from __future__ import annotations

import pytest

from app.db.models import MessageKind, ReasonCategory, TelegramUser
from app.handlers.admin.reply import IsTicketReply
from app.services.messages import save_user_message
from app.services.tickets import create_ticket


class _FakeReplied:
    def __init__(self, message_id: int):
        self.message_id = message_id


class _FakeMessage:
    def __init__(self, reply_to_message):
        self.reply_to_message = reply_to_message


@pytest.mark.asyncio
async def test_ticket_reply_filter_matches_real_ticket_message(session):
    """Regression test: an admin replying to an actual forwarded user message must
    be recognized so the reply gets delivered."""
    user = TelegramUser(telegram_id=1, username="alice")
    session.add(user)
    await session.flush()

    ticket = await create_ticket(session, 1, ReasonCategory.OTHER)
    saved = await save_user_message(
        session, ticket, 1, MessageKind.TEXT, "hello", None,
        user_chat_message_id=100, admin_chat_message_id=555,
    )
    await session.commit()

    result = await IsTicketReply()(_FakeMessage(_FakeReplied(555)), session)
    assert result and result["original_message"].id == saved.id


@pytest.mark.asyncio
async def test_ticket_reply_filter_rejects_reply_to_bot_prompt(session):
    """Regression test for the bug where swipe-replying to the bot's own question
    (e.g. 'Введите сумму к оплате...') was swallowed by the reply handler instead
    of reaching the flow that was actually waiting for the answer."""
    result = await IsTicketReply()(_FakeMessage(_FakeReplied(99999)), session)
    assert result is False


@pytest.mark.asyncio
async def test_ticket_reply_filter_rejects_non_reply(session):
    result = await IsTicketReply()(_FakeMessage(None), session)
    assert result is False
