from __future__ import annotations

import pytest
from aiogram.filters import StateFilter

from app.handlers.admin.payment_settings import router
from app.states.admin_states import PaymentSettingsFlow


def _find_save_text_field_handler():
    for handler in router.message.handlers:
        if handler.callback.__name__ == "save_text_field":
            return handler
    raise AssertionError("save_text_field handler not found")


@pytest.mark.asyncio
async def test_save_text_field_matches_each_editing_state():
    """Regression test for a bug where multiple bare State objects passed to
    @router.message(...) were combined with AND instead of OR, so the handler
    that saves requisites text fields (bank/recipient/phone/card/texts) never
    matched any state and admins got stuck unable to save settings.
    """
    handler = _find_save_text_field_handler()

    state_filters = [f for f in handler.filters if isinstance(f.callback, StateFilter)]
    assert len(state_filters) == 1, "expected exactly one StateFilter on the handler"
    state_filter = state_filters[0].callback

    for state in [
        PaymentSettingsFlow.editing_bank,
        PaymentSettingsFlow.editing_recipient,
        PaymentSettingsFlow.editing_phone,
        PaymentSettingsFlow.editing_card,
        PaymentSettingsFlow.editing_main_text,
        PaymentSettingsFlow.editing_after_text,
    ]:
        matched = await state_filter(obj=None, raw_state=state.state)
        assert matched, f"handler should match state {state.state!r}"

    # A completely unrelated state must not match.
    not_matched = await state_filter(obj=None, raw_state=PaymentSettingsFlow.menu.state)
    assert not not_matched
