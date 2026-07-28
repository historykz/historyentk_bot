from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReasonCategory(str, enum.Enum):
    BLOCK = "block"                # Причина блокировки
    PURCHASE = "purchase"          # Покупка тестов / конспектов / Premium
    COOPERATION = "cooperation"    # Сотрудничество
    OTHER = "other"                # Свой вопрос


class PurchaseSubcategory(str, enum.Enum):
    TESTS = "tests"                # тест или тесты
    PREMIUM = "premium"            # Premium-доступ
    NOTES = "notes"                # конспекты
    ALL = "all"                    # всё вышеперечисленное


PURCHASE_LABELS = {
    PurchaseSubcategory.TESTS: "тест или тесты",
    PurchaseSubcategory.PREMIUM: "Premium-доступ",
    PurchaseSubcategory.NOTES: "конспекты",
    PurchaseSubcategory.ALL: "всё вышеперечисленное",
}

REASON_LABELS = {
    ReasonCategory.BLOCK: "Причина блокировки",
    ReasonCategory.PURCHASE: "Покупка тестов / конспектов / Premium",
    ReasonCategory.COOPERATION: "Сотрудничество",
    ReasonCategory.OTHER: "Свой вопрос",
}


class TicketStatus(str, enum.Enum):
    NEW = "new"                              # Новое
    VIEWED = "viewed"                        # Просмотрено
    AWAITING_ADMIN = "awaiting_admin"        # Ожидает ответа администратора
    AWAITING_USER = "awaiting_user"          # Ожидает ответа пользователя
    ANSWERED = "answered"                    # Отвечено
    AWAITING_PAYMENT = "awaiting_payment"    # Ожидает оплаты
    PAYMENT_REVIEW = "payment_review"        # Оплата на проверке
    PAID = "paid"                            # Оплачено
    CLOSED = "closed"                        # Закрыто


TICKET_STATUS_LABELS = {
    TicketStatus.NEW: "Новое",
    TicketStatus.VIEWED: "Просмотрено",
    TicketStatus.AWAITING_ADMIN: "Ожидает ответа администратора",
    TicketStatus.AWAITING_USER: "Ожидает ответа пользователя",
    TicketStatus.ANSWERED: "Отвечено",
    TicketStatus.AWAITING_PAYMENT: "Ожидает оплаты",
    TicketStatus.PAYMENT_REVIEW: "Оплата на проверке",
    TicketStatus.PAID: "Оплачено",
    TicketStatus.CLOSED: "Закрыто",
}


class MessageDirection(str, enum.Enum):
    USER_TO_ADMIN = "user_to_admin"
    ADMIN_TO_USER = "admin_to_user"


class MessageKind(str, enum.Enum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    VOICE = "voice"
    VIDEO_NOTE = "video_note"
    AUDIO = "audio"
    STICKER = "sticker"
    OTHER = "other"


class RequisiteKind(str, enum.Enum):
    PURCHASE = "purchase"
    COOPERATION = "cooperation"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"          # реквизиты отправлены, чек не получен
    RECEIPT_SENT = "receipt_sent"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"      # отменена администратором после подтверждения


class PaymentType(str, enum.Enum):
    PURCHASE_TESTS = "purchase_tests"
    PURCHASE_PREMIUM = "purchase_premium"
    PURCHASE_NOTES = "purchase_notes"
    PURCHASE_ALL = "purchase_all"
    COOPERATION = "cooperation"


PURCHASE_SUBCATEGORY_TO_PAYMENT_TYPE = {
    PurchaseSubcategory.TESTS: PaymentType.PURCHASE_TESTS,
    PurchaseSubcategory.PREMIUM: PaymentType.PURCHASE_PREMIUM,
    PurchaseSubcategory.NOTES: PaymentType.PURCHASE_NOTES,
    PurchaseSubcategory.ALL: PaymentType.PURCHASE_ALL,
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TelegramUser(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="user")

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        name = " ".join(filter(None, [self.first_name, self.last_name]))
        return name or f"ID {self.telegram_id}"


class TicketCounter(Base):
    """Single-row table used to atomically generate sequential ticket numbers."""

    __tablename__ = "ticket_counter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    user_telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)
    user: Mapped["TelegramUser"] = relationship(back_populates="tickets")

    reason: Mapped[ReasonCategory] = mapped_column(Enum(ReasonCategory, name="reason_category"))
    purchase_subcategory: Mapped[PurchaseSubcategory | None] = mapped_column(
        Enum(PurchaseSubcategory, name="purchase_subcategory"), nullable=True
    )

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"), default=TicketStatus.NEW
    )

    is_open: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", order_by="TicketMessage.id")
    payments: Mapped[list["Payment"]] = relationship(back_populates="ticket", order_by="Payment.id")

    @property
    def reason_label(self) -> str:
        if self.reason == ReasonCategory.PURCHASE and self.purchase_subcategory:
            return f"Покупка — {PURCHASE_LABELS[self.purchase_subcategory]}"
        return REASON_LABELS[self.reason]


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        UniqueConstraint("admin_chat_message_id", name="uq_admin_chat_message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("tickets.id"), index=True)
    ticket: Mapped["Ticket"] = relationship(back_populates="messages")

    user_telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)

    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection, name="message_direction"))
    kind: Mapped[MessageKind] = mapped_column(Enum(MessageKind, name="message_kind"))

    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # ID of the message as sent to the user (their chat) — used to detect user replies (not required by Telegram
    # but kept for completeness / future features).
    user_chat_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # ID of the corresponding message inside the admin chat/group — this is the key used to resolve
    # swipe-replies from admins back to the originating user & ticket.
    admin_chat_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    admin_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_duplicate_flagged: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Requisites(Base):
    """Admin-configurable payment details. One active row per kind (purchase / cooperation)."""

    __tablename__ = "requisites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[RequisiteKind] = mapped_column(Enum(RequisiteKind, name="requisite_kind"), unique=True)

    bank_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    main_text_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_payment_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    photo_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    qr_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("tickets.id"), index=True)
    ticket: Mapped["Ticket"] = relationship(back_populates="payments")

    user_telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), index=True)

    payment_type: Mapped[PaymentType] = mapped_column(Enum(PaymentType, name="payment_type"))

    requested_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    confirmed_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    bank_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requisites_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)

    receipt_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    receipt_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING
    )

    admin_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmed_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cancelled_by_admin_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Idempotency guard: a payment can only ever be counted toward revenue once. This flag is flipped inside a
    # DB transaction guarded by a row lock (see services/payments.py) so concurrent admin taps can't double count.
    counted_in_revenue: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only log of important actions, per requirement #22."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
