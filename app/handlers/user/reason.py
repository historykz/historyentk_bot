from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PurchaseSubcategory, ReasonCategory
from app.keyboards.user_kb import (
    PURCHASE_CB_PREFIX,
    REASON_CB_PREFIX,
    purchase_subcategory_keyboard,
    reason_keyboard,
)
from app.services.tickets import close_open_tickets, create_ticket
from app.states.user_states import ConfirmNewTicket, UserFlow

router = Router(name="user_reason")

AFTER_REASON_TEXT = (
    "Причина обращения выбрана.\n\n"
    "Теперь подробно напишите свой вопрос администратору. Вы можете отправить текст, "
    "фотографию, документ, видео, голосовое сообщение или другой файл.\n\n"
    "Администратор постарается ответить вам в течение дня.\n\n"
    "Если в течение дня вы не получили ответ, можете продублировать своё обращение ещё один раз. "
    "Пожалуйста, не отправляйте одно и то же сообщение многократно."
)


@router.callback_query(ConfirmNewTicket.confirm)
async def confirm_new_ticket(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    choice = callback.data.split(":")[1]
    await callback.answer()
    if choice == "confirm":
        await close_open_tickets(session, callback.from_user.id)
        await state.set_state(UserFlow.choosing_reason)
        await callback.message.edit_text("Выберите причину обращения:")
        await callback.message.answer("Причина обращения:", reply_markup=reason_keyboard())
    elif choice == "continue":
        await state.set_state(UserFlow.chatting)
        await callback.message.edit_text("Хорошо, продолжайте писать в своём текущем обращении.")
    else:
        await state.clear()
        await callback.message.edit_text("Действие отменено.")


@router.callback_query(UserFlow.choosing_reason)
async def choose_reason(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not callback.data.startswith(REASON_CB_PREFIX):
        await callback.answer()
        return
    value = callback.data.removeprefix(REASON_CB_PREFIX)
    await callback.answer()

    if value == "purchase":
        await state.set_state(UserFlow.choosing_purchase_subcategory)
        await callback.message.edit_text("Что вы хотите приобрести?")
        await callback.message.answer("Выберите вариант:", reply_markup=purchase_subcategory_keyboard())
        return

    reason = ReasonCategory(value)
    ticket = await create_ticket(session, callback.from_user.id, reason)
    await state.set_state(UserFlow.chatting)
    await state.update_data(ticket_id=ticket.id)
    await callback.message.edit_text("Причина обращения выбрана.")
    await callback.message.answer(AFTER_REASON_TEXT)


@router.callback_query(UserFlow.choosing_purchase_subcategory)
async def choose_purchase_subcategory(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not callback.data.startswith(PURCHASE_CB_PREFIX):
        await callback.answer()
        return
    value = callback.data.removeprefix(PURCHASE_CB_PREFIX)
    await callback.answer()

    if value == "back":
        await state.set_state(UserFlow.choosing_reason)
        await callback.message.edit_text("Выберите причину обращения:")
        await callback.message.answer("Причина обращения:", reply_markup=reason_keyboard())
        return

    subcat = PurchaseSubcategory(value)
    ticket = await create_ticket(session, callback.from_user.id, ReasonCategory.PURCHASE, subcat)
    await state.set_state(UserFlow.chatting)
    await state.update_data(ticket_id=ticket.id)
    await callback.message.edit_text("Причина обращения выбрана.")
    await callback.message.answer(AFTER_REASON_TEXT)
