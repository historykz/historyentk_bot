from __future__ import annotations

import pytest

from app.services.spam_guard import (
    BURST_LIMIT,
    InMemorySpamGuard,
    create_spam_guard,
)


def test_create_spam_guard_falls_back_to_in_memory_without_redis():
    guard = create_spam_guard(None)
    assert isinstance(guard, InMemorySpamGuard)


@pytest.mark.asyncio
async def test_in_memory_guard_throttles_bursts():
    guard = InMemorySpamGuard()
    results = [await guard.is_throttled(1) for _ in range(BURST_LIMIT + 3)]
    # The first BURST_LIMIT messages should pass, later ones should be throttled.
    assert results[:BURST_LIMIT] == [False] * BURST_LIMIT
    assert any(results[BURST_LIMIT:])


@pytest.mark.asyncio
async def test_in_memory_guard_detects_duplicate_text():
    guard = InMemorySpamGuard()
    first = await guard.is_duplicate(1, "Здравствуйте, есть вопрос")
    second = await guard.is_duplicate(1, "Здравствуйте, есть вопрос")
    different_user = await guard.is_duplicate(2, "Здравствуйте, есть вопрос")

    assert first is False
    assert second is True
    assert different_user is False
