from aiogram.fsm.state import State, StatesGroup


class RequisitesFlow(StatesGroup):
    entering_amount = State()
    preview = State()
    editing_amount = State()
    editing_comment = State()


class PaymentSettingsFlow(StatesGroup):
    menu = State()
    editing_bank = State()
    editing_recipient = State()
    editing_phone = State()
    editing_card = State()
    editing_main_text = State()
    editing_after_text = State()
    awaiting_photo = State()


class ConfirmPaymentFlow(StatesGroup):
    reviewing_amount = State()
    editing_amount = State()


class CancelPaymentFlow(StatesGroup):
    awaiting_reason = State()


class HistoryLookup(StatesGroup):
    awaiting_period_start = State()
    awaiting_period_end = State()
