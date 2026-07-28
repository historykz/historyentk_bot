from aiogram.fsm.state import State, StatesGroup


class UserFlow(StatesGroup):
    choosing_reason = State()
    choosing_purchase_subcategory = State()
    chatting = State()          # reason chosen, free messaging allowed
    awaiting_receipt = State()  # user asked to send a payment receipt


class ConfirmNewTicket(StatesGroup):
    confirm = State()
