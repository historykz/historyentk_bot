from __future__ import annotations

from types import SimpleNamespace

from app.config import settings
from app.handlers.admin.reaction import _is_trusted_admin_reaction


def _fake_event(*, chat_id: int, user_id: int | None, actor_chat_id: int | None):
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    actor_chat = SimpleNamespace(id=actor_chat_id) if actor_chat_id is not None else None
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        user=user,
        actor_chat=actor_chat,
    )


def test_named_admin_is_trusted():
    admin_id = next(iter(settings.admin_ids))
    event = _fake_event(chat_id=settings.ADMIN_CHAT_ID, user_id=admin_id, actor_chat_id=None)
    assert _is_trusted_admin_reaction(event) is True


def test_anonymous_reaction_from_the_admin_chat_itself_is_trusted():
    event = _fake_event(chat_id=settings.ADMIN_CHAT_ID, user_id=None, actor_chat_id=settings.ADMIN_CHAT_ID)
    assert _is_trusted_admin_reaction(event) is True


def test_named_non_admin_user_is_not_trusted():
    event = _fake_event(chat_id=settings.ADMIN_CHAT_ID, user_id=999999999, actor_chat_id=None)
    assert _is_trusted_admin_reaction(event) is False


def test_anonymous_reaction_from_a_different_chat_is_not_trusted():
    event = _fake_event(chat_id=settings.ADMIN_CHAT_ID, user_id=None, actor_chat_id=-123456)
    assert _is_trusted_admin_reaction(event) is False
