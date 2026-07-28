from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

REASON_CB_PREFIX = "reason:"
PURCHASE_CB_PREFIX = "purch:"


def reason_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="1. Причина блокировки", callback_data=f"{REASON_CB_PREFIX}block")],
        [InlineKeyboardButton(
            text="2. Покупка тестов / конспектов / Premium",
            callback_data=f"{REASON_CB_PREFIX}purchase",
        )],
        [InlineKeyboardButton(text="3. Сотрудничество", callback_data=f"{REASON_CB_PREFIX}cooperation")],
        [InlineKeyboardButton(text="4. Свой вопрос", callback_data=f"{REASON_CB_PREFIX}other")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def purchase_subcategory_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="1. Тест или тесты", callback_data=f"{PURCHASE_CB_PREFIX}tests")],
        [InlineKeyboardButton(text="2. Premium-доступ", callback_data=f"{PURCHASE_CB_PREFIX}premium")],
        [InlineKeyboardButton(text="3. Конспекты", callback_data=f"{PURCHASE_CB_PREFIX}notes")],
        [InlineKeyboardButton(text="4. Всё вышеперечисленное", callback_data=f"{PURCHASE_CB_PREFIX}all")],
        [InlineKeyboardButton(text="5. Назад", callback_data=f"{PURCHASE_CB_PREFIX}back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_receipt_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Я оплатил — отправить чек", callback_data="user_send_receipt")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_ticket_confirm_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Да, создать новое", callback_data="newticket:confirm")],
        [InlineKeyboardButton(text="Продолжить текущее", callback_data="newticket:continue")],
        [InlineKeyboardButton(text="Отмена", callback_data="newticket:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
