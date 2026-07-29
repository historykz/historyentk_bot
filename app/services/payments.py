from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Payment,
    PaymentStatus,
    PaymentType,
    PURCHASE_SUBCATEGORY_TO_PAYMENT_TYPE,
    PurchaseSubcategory,
    RequisiteKind,
    Requisites,
    Ticket,
)
from app.utils.time_utils import now_local


async def get_or_create_requisites(session: AsyncSession, kind: RequisiteKind) -> Requisites:
    result = await session.execute(select(Requisites).where(Requisites.kind == kind))
    req = result.scalar_one_or_none()
    if req is None:
        req = Requisites(kind=kind)
        session.add(req)
        await session.flush()
    return req


def render_purchase_message(amount: Decimal, req: Requisites) -> str:
    template = req.main_text_template or (
        "Ваша сумма к оплате составляет: {amount}\n\n"
        "Получатель: {recipient}\n"
        "Банк: {bank}\n"
        "Номер карты или телефона: {requisites}\n\n"
        "После оплаты обязательно отправьте чек об оплате в этот чат."
    )
    from app.utils.formatting import fmt_money

    card_or_phone = req.card_number or req.phone_number or "-"
    return template.format(
        amount=fmt_money(amount),
        recipient=req.recipient_name or "-",
        bank=req.bank_name or "-",
        requisites=card_or_phone,
    )


def render_cooperation_message(amount: Decimal, req: Requisites) -> str:
    template = req.main_text_template or (
        "Стоимость сотрудничества составляет: {amount}\n\n"
        "Банк: {bank}\n"
        "Получатель: {recipient}\n"
        "Номер карты или телефона: {requisites}\n\n"
        "После оплаты отправьте чек в этот чат. После проверки оплаты администрация "
        "свяжется с вами для дальнейшего обсуждения сотрудничества."
    )
    from app.utils.formatting import fmt_money

    card_or_phone = req.card_number or req.phone_number or "-"
    return template.format(
        amount=fmt_money(amount),
        recipient=req.recipient_name or "-",
        bank=req.bank_name or "-",
        requisites=card_or_phone,
    )


def payment_type_for_ticket(ticket: Ticket) -> PaymentType:
    if ticket.purchase_subcategory:
        return PURCHASE_SUBCATEGORY_TO_PAYMENT_TYPE[PurchaseSubcategory(ticket.purchase_subcategory)]
    return PaymentType.COOPERATION


async def create_pending_payment(
    session: AsyncSession,
    ticket: Ticket,
    amount: Decimal,
    payment_type: PaymentType,
    requisites: Requisites,
    admin_id: int,
) -> Payment:
    snapshot = (
        f"Банк: {requisites.bank_name or '-'}; Получатель: {requisites.recipient_name or '-'}; "
        f"Карта/телефон: {requisites.card_number or requisites.phone_number or '-'}"
    )
    payment = Payment(
        ticket_id=ticket.id,
        user_telegram_id=ticket.user_telegram_id,
        payment_type=payment_type,
        requested_amount=amount,
        bank_name=requisites.bank_name,
        requisites_snapshot=snapshot,
        status=PaymentStatus.PENDING,
        requested_by_admin_id=admin_id,
    )
    session.add(payment)
    await session.flush()
    return payment


async def get_payment(session: AsyncSession, payment_id: int) -> Payment | None:
    return await session.get(Payment, payment_id)


async def get_latest_pending_payment(session: AsyncSession, ticket_id: int) -> Payment | None:
    result = await session.execute(
        select(Payment)
        .where(Payment.ticket_id == ticket_id, Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.RECEIPT_SENT]))
        .order_by(Payment.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def attach_receipt(session: AsyncSession, payment: Payment, file_id: str) -> None:
    payment.receipt_file_id = file_id
    payment.receipt_received_at = now_local()
    payment.status = PaymentStatus.RECEIPT_SENT
    await session.flush()


async def confirm_payment(
    session: AsyncSession,
    payment_id: int,
    confirmed_amount: Decimal,
    admin_id: int,
) -> tuple[Payment, bool]:
    """Confirms a payment and marks it as counted toward revenue.

    Returns (payment, newly_counted). newly_counted is False if the payment was already
    confirmed previously — this is the idempotency guard against double-tapping the
    confirmation button or two admins confirming at once. The row lock (`with_for_update`)
    ensures only one concurrent transaction can flip `counted_in_revenue`.
    """
    result = await session.execute(select(Payment).where(Payment.id == payment_id).with_for_update())
    payment = result.scalar_one()

    if payment.counted_in_revenue:
        return payment, False

    payment.confirmed_amount = confirmed_amount
    payment.status = PaymentStatus.CONFIRMED
    payment.confirmed_by_admin_id = admin_id
    payment.confirmed_at = now_local()
    payment.counted_in_revenue = True
    await session.flush()
    return payment, True


async def cancel_confirmed_payment(
    session: AsyncSession, payment_id: int, admin_id: int, reason: str
) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.id == payment_id).with_for_update())
    payment = result.scalar_one_or_none()
    if payment is None or payment.status != PaymentStatus.CONFIRMED:
        return None
    payment.status = PaymentStatus.CANCELLED
    payment.counted_in_revenue = False
    payment.cancelled_by_admin_id = admin_id
    payment.cancel_reason = reason
    payment.cancelled_at = now_local()
    await session.flush()
    return payment


async def reject_receipt(session: AsyncSession, payment: Payment) -> None:
    payment.status = PaymentStatus.REJECTED
    await session.flush()
