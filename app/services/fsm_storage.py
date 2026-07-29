from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import FsmStorageEntry

logger = logging.getLogger(__name__)


class PostgresStorage(BaseStorage):
    """FSM storage backed by a PostgreSQL table instead of Redis or process memory.

    Why this exists: with in-memory storage, any bot restart — a deploy, a crash, a
    hosting platform recycling the container — silently wipes whatever an admin or
    user was in the middle of doing (e.g. "Введите название банка:" — the prompt is
    still on screen, but the bot no longer remembers it asked). The reply then goes
    nowhere, which looks exactly like "the bot doesn't react at all". This storage
    makes that impossible without requiring a separate Redis service: the state and
    data live in the same PostgreSQL database the bot already needs.
    """

    def __init__(self, session_maker: async_sessionmaker):
        self._session_maker = session_maker

    @staticmethod
    def _key(key: StorageKey) -> str:
        return (
            f"{key.bot_id}:{key.chat_id}:{key.user_id}:"
            f"{key.thread_id or 0}:{key.business_connection_id or ''}:{key.destiny}"
        )

    async def set_state(self, key: StorageKey, state: Optional[str | State] = None) -> None:
        state_str = state.state if isinstance(state, State) else state
        k = self._key(key)
        async with self._session_maker() as session:
            row = await session.get(FsmStorageEntry, k)
            if row is None:
                if state_str is None:
                    return
                row = FsmStorageEntry(key=k, state=state_str, data="{}")
                session.add(row)
            else:
                row.state = state_str
            await session.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        k = self._key(key)
        async with self._session_maker() as session:
            row = await session.get(FsmStorageEntry, k)
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        k = self._key(key)
        payload = json.dumps(data, default=str)
        async with self._session_maker() as session:
            row = await session.get(FsmStorageEntry, k)
            if row is None:
                row = FsmStorageEntry(key=k, state=None, data=payload)
                session.add(row)
            else:
                row.data = payload
            await session.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        k = self._key(key)
        async with self._session_maker() as session:
            row = await session.get(FsmStorageEntry, k)
            if row is None or not row.data:
                return {}
            try:
                return json.loads(row.data)
            except (TypeError, ValueError):
                logger.warning("Corrupt FSM data for key %s, resetting to empty", k)
                return {}

    async def close(self) -> None:
        pass
