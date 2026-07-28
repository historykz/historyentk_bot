from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import ReasonCategory


def ticket_action_keyboard(ticket_id: int, reason: ReasonCategory) -> InlineKeyboardMarkup:
    """Keyboard shown under a forwarded user message inside the admin chat."""
    rows = []
    if reason == ReasonCategory.PURCHASE:
        rows.append([InlineKeyboardButton(text="Отправить реквизиты", callback_data=f"req:purchase:{ticket_id}")])
    elif reason == ReasonCategory.COOPERATION:
        rows.append(
            [InlineKeyboardButton(
                text="Отправить реквизиты для сотрудничества",
                callback_data=f"req:cooperation:{ticket_id}",
            )]
        )
    rows.append([
        InlineKeyboardButton(text="Изменить статус", callback_data=f"status:{ticket_id}"),
        InlineKeyboardButton(text="Закрыть обращение", callback_data=f"close:{ticket_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def requisites_preview_keyboard(kind: str, ticket_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Отправить пользователю", callback_data=f"reqsend:{kind}:{ticket_id}")],
        [InlineKeyboardButton(text="Изменить сумму", callback_data=f"reqamount:{kind}:{ticket_id}")],
        [InlineKeyboardButton(text="Добавить комментарий", callback_data=f"reqcomment:{kind}:{ticket_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"reqcancel:{kind}:{ticket_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def receipt_review_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Оплата подтверждена", callback_data=f"payok:{payment_id}")],
        [InlineKeyboardButton(text="Отклонить чек", callback_data=f"payreject:{payment_id}")],
        [InlineKeyboardButton(text="Запросить новый чек", callback_data=f"payretry:{payment_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_amount_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Подтвердить сумму и оплату", callback_data=f"payconfirm:{payment_id}")],
        [InlineKeyboardButton(text="Изменить сумму", callback_data=f"payeditamount:{payment_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"paycancelflow:{payment_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def period_keyboard(prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Сегодня", callback_data=f"{prefix}:today")],
        [InlineKeyboardButton(text="Эта неделя", callback_data=f"{prefix}:week")],
        [InlineKeyboardButton(text="Этот месяц", callback_data=f"{prefix}:month")],
        [InlineKeyboardButton(text="Весь период", callback_data=f"{prefix}:all")],
        [InlineKeyboardButton(text="Выбрать период", callback_data=f"{prefix}:custom")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_settings_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Реквизиты для покупок", callback_data="psettings:purchase")],
        [InlineKeyboardButton(text="Реквизиты для сотрудничества", callback_data="psettings:cooperation")],
        [InlineKeyboardButton(text="Предпросмотр", callback_data="psettings:preview")],
        [InlineKeyboardButton(text="Отмена", callback_data="psettings:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def requisites_edit_keyboard(kind: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Изменить банк", callback_data=f"pedit:{kind}:bank")],
        [InlineKeyboardButton(text="Изменить получателя", callback_data=f"pedit:{kind}:recipient")],
        [InlineKeyboardButton(text="Изменить номер телефона", callback_data=f"pedit:{kind}:phone")],
        [InlineKeyboardButton(text="Изменить номер карты", callback_data=f"pedit:{kind}:card")],
        [InlineKeyboardButton(text="Изменить основной текст", callback_data=f"pedit:{kind}:maintext")],
        [InlineKeyboardButton(text="Изменить текст после оплаты", callback_data=f"pedit:{kind}:aftertext")],
        [InlineKeyboardButton(text="Добавить/изменить фото", callback_data=f"pedit:{kind}:photo")],
        [InlineKeyboardButton(text="Удалить фото", callback_data=f"pedit:{kind}:delphoto")],
        [InlineKeyboardButton(text="Предпросмотр", callback_data=f"pedit:{kind}:preview")],
        [InlineKeyboardButton(text="Назад", callback_data="psettings:back")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
