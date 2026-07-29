from __future__ import annotations

import pytest
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.fsm_storage import PostgresStorage


def _session_maker_from(session: AsyncSession) -> async_sessionmaker:
    """Wraps the test session's underlying engine into a fresh sessionmaker, since
    PostgresStorage opens its own short-lived sessions per operation (matching how
    it's used in production against the real engine)."""
    return async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_state_survives_a_new_storage_instance(session):
    """Regression test for the core bug: state must not depend on any in-process
    object surviving — a brand new PostgresStorage instance (simulating a bot
    restart) must still see state written by a previous instance."""
    maker = _session_maker_from(session)
    key = StorageKey(bot_id=1, chat_id=100, user_id=200)

    storage1 = PostgresStorage(maker)
    await storage1.set_state(key, "PaymentSettingsFlow:editing_bank")
    await storage1.set_data(key, {"settings_kind": "purchase", "settings_field": "bank"})

    # Simulate a full process restart: brand new storage instance, no shared memory.
    storage2 = PostgresStorage(maker)
    state = await storage2.get_state(key)
    data = await storage2.get_data(key)

    assert state == "PaymentSettingsFlow:editing_bank"
    assert data == {"settings_kind": "purchase", "settings_field": "bank"}


@pytest.mark.asyncio
async def test_different_chats_are_isolated(session):
    maker = _session_maker_from(session)
    storage = PostgresStorage(maker)

    key_admin_chat = StorageKey(bot_id=1, chat_id=-999, user_id=42)
    key_private_chat = StorageKey(bot_id=1, chat_id=42, user_id=42)

    await storage.set_state(key_admin_chat, "PaymentSettingsFlow:editing_bank")
    await storage.set_state(key_private_chat, "UserFlow:chatting")

    assert await storage.get_state(key_admin_chat) == "PaymentSettingsFlow:editing_bank"
    assert await storage.get_state(key_private_chat) == "UserFlow:chatting"


@pytest.mark.asyncio
async def test_clearing_state_with_none(session):
    maker = _session_maker_from(session)
    storage = PostgresStorage(maker)
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)

    await storage.set_state(key, "SomeFlow:step")
    assert await storage.get_state(key) == "SomeFlow:step"

    await storage.set_state(key, None)
    assert await storage.get_state(key) is None


@pytest.mark.asyncio
async def test_update_data_merges(session):
    maker = _session_maker_from(session)
    storage = PostgresStorage(maker)
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)

    await storage.set_data(key, {"a": 1})
    result = await storage.update_data(key, {"b": 2})

    assert result == {"a": 1, "b": 2}
    assert await storage.get_data(key) == {"a": 1, "b": 2}
