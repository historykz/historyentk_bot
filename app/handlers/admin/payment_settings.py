from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequisiteKind
from app.keyboards.admin_kb import payment_settings_menu_keyboard, requisites_edit_keyboard
from app.middlewares.admin_only import IsAdmin, IsAdminChat
from app.services.payments import get_or_create_requisites, render_purchase_message
from app.states.admin_states import PaymentSettingsFlow

router = Router(name="admin_payment_settings")

FIELD_PROMPTS = {
    "bank": "Введите название банка:",
    "recipient": "Введите имя получателя:",
    "phone": "Введите номер телефона:",
    "card": "Введите номер карты:",
    "maintext": (
        "Введите основной текст сообщения с реквизитами. Доступны плейсхолдеры: "
        "{amount}, {recipient}, {bank}, {requisites}"
    ),
    "aftertext": "Введите текст, который увидит пользователь после подтверждения оплаты:",
}

STATE_BY_FIELD = {
    "bank": PaymentSettingsFlow.editing_bank,
    "recipient": PaymentSettingsFlow.editing_recipient,
    "phone": PaymentSettingsFlow.editing_phone,
    "card": PaymentSettingsFlow.editing_card,
    "maintext": PaymentSettingsFlow.editing_main_text,
    "aftertext": PaymentSettingsFlow.editing_after_text,
}


def _kind_enum(kind: str) -> RequisiteKind:
    return RequisiteKind.PURCHASE if kind == "purchase" else RequisiteKind.COOPERATION


@router.message(IsAdminChat(), IsAdmin(), Command("payment_settings"))
async def payment_settings_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentSettingsFlow.menu)
    await message.answer("Настройка реквизитов:", reply_markup=payment_settings_menu_keyboard())


@router.callback_query(F.data.startswith("psettings:"))
async def payment_settings_router(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    action = callback.data.split(":")[1]
    await callback.answer()

    if action in ("purchase", "cooperation"):
        await state.update_data(settings_kind=action)
        await callback.message.edit_text(
            f"Реквизиты для {'покупок' if action == 'purchase' else 'сотрудничества'}:",
            reply_markup=requisites_edit_keyboard(action),
        )
        return

    if action == "preview":
        data = await state.get_data()
        kind = data.get("settings_kind", "purchase")
        req = await get_or_create_requisites(session, _kind_enum(kind))
        from decimal import Decimal

        preview = render_purchase_message(Decimal("0"), req)
        await callback.message.answer(f"Предпросмотр:\n\n{preview}")
        return

    if action in ("cancel", "back"):
        await state.clear()
        await callback.message.edit_text("Настройка реквизитов завершена.")
        return


@router.callback_query(F.data.startswith("pedit:"))
async def payment_field_edit(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    _, kind, field = callback.data.split(":")
    await callback.answer()

    if field == "preview":
        from decimal import Decimal

        req = await get_or_create_requisites(session, _kind_enum(kind))
        preview = render_purchase_message(Decimal("0"), req)
        await callback.message.answer(f"Предпросмотр:\n\n{preview}")
        return

    if field == "delphoto":
        req = await get_or_create_requisites(session, _kind_enum(kind))
        req.photo_file_id = None
        await session.flush()
        await callback.message.answer("Фото удалено.")
        return

    if field == "photo":
        await state.set_state(PaymentSettingsFlow.awaiting_photo)
        await state.update_data(settings_kind=kind)
        await callback.message.answer("Отправьте фотографию с реквизитами.")
        return

    target_state = STATE_BY_FIELD[field]
    await state.set_state(target_state)
    await state.update_data(settings_kind=kind, settings_field=field)
    await callback.message.answer(FIELD_PROMPTS[field])


@router.message(PaymentSettingsFlow.awaiting_photo, F.photo)
async def save_requisites_photo(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    kind = data["settings_kind"]
    req = await get_or_create_requisites(session, _kind_enum(kind))
    req.photo_file_id = message.photo[-1].file_id
    await session.flush()
    await state.set_state(PaymentSettingsFlow.menu)
    await message.answer("Фото сохранено.", reply_markup=requisites_edit_keyboard(kind))


@router.message(
    F.text,
    PaymentSettingsFlow.editing_bank,
    PaymentSettingsFlow.editing_recipient,
    PaymentSettingsFlow.editing_phone,
    PaymentSettingsFlow.editing_card,
    PaymentSettingsFlow.editing_main_text,
    PaymentSettingsFlow.editing_after_text,
)
async def save_text_field(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    kind = data["settings_kind"]
    field = data["settings_field"]
    req = await get_or_create_requisites(session, _kind_enum(kind))

    if field == "bank":
        req.bank_name = message.text
    elif field == "recipient":
        req.recipient_name = message.text
    elif field == "phone":
        req.phone_number = message.text
    elif field == "card":
        req.card_number = message.text
    elif field == "maintext":
        req.main_text_template = message.text
    elif field == "aftertext":
        req.after_payment_text = message.text

    await session.flush()
    await state.set_state(PaymentSettingsFlow.menu)
    await message.answer("Сохранено.", reply_markup=requisites_edit_keyboard(kind))
