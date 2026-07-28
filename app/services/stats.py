from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Payment,
    PaymentStatus,
    PurchaseSubcategory,
    ReasonCategory,
    Ticket,
    TicketStatus,
)


@dataclass
class TicketStats:
    period_label: str
    total: int = 0
    unique_users: int = 0
    new_users: int = 0
    repeat: int = 0
    answered: int = 0
    unanswered: int = 0
    closed: int = 0
    by_reason: dict[ReasonCategory, int] = field(default_factory=dict)
    by_purchase_sub: dict[PurchaseSubcategory, int] = field(default_factory=dict)
    confirmed_payments: int = 0
    turnover: float = 0.0

    @property
    def conversion(self) -> str:
        purchases = self.by_reason.get(ReasonCategory.PURCHASE, 0)
        if not purchases:
            return "0%"
        return f"{round(100 * self.confirmed_payments / purchases)}%"

    def render(self) -> str:
        from app.utils.formatting import fmt_money

        lines = [
            "Статистика обращений",
            f"Период: {self.period_label}",
            "",
            f"Всего обращений: {self.total}",
            f"Уникальных пользователей: {self.unique_users}",
            f"Повторных обращений: {self.repeat}",
            f"Отвечено: {self.answered}",
            f"Без ответа: {self.unanswered}",
            f"Закрыто: {self.closed}",
            "",
            "По причинам:",
            "",
            f"Причина блокировки: {self.by_reason.get(ReasonCategory.BLOCK, 0)}",
            f"Покупки: {self.by_reason.get(ReasonCategory.PURCHASE, 0)}",
            f"Сотрудничество: {self.by_reason.get(ReasonCategory.COOPERATION, 0)}",
            f"Свой вопрос: {self.by_reason.get(ReasonCategory.OTHER, 0)}",
            "",
            "Категории покупок:",
            "",
            f"Тесты: {self.by_purchase_sub.get(PurchaseSubcategory.TESTS, 0)}",
            f"Premium: {self.by_purchase_sub.get(PurchaseSubcategory.PREMIUM, 0)}",
            f"Конспекты: {self.by_purchase_sub.get(PurchaseSubcategory.NOTES, 0)}",
            f"Всё вышеперечисленное: {self.by_purchase_sub.get(PurchaseSubcategory.ALL, 0)}",
            "",
            f"Подтверждённых оплат: {self.confirmed_payments}",
            f"Конверсия покупок в оплату: {self.conversion}",
            f"Общий оборот: {fmt_money(self.turnover)}",
        ]
        return "\n".join(lines)


async def build_ticket_stats(session: AsyncSession, start: datetime, end: datetime, period_label: str) -> TicketStats:
    tickets_result = await session.execute(
        select(Ticket).where(Ticket.created_at >= start, Ticket.created_at <= end)
    )
    tickets = tickets_result.scalars().all()

    stats = TicketStats(period_label=period_label)
    stats.total = len(tickets)

    user_ids = [t.user_telegram_id for t in tickets]
    stats.unique_users = len(set(user_ids))

    seen: set[int] = set()
    for t in tickets:
        if t.user_telegram_id in seen:
            stats.repeat += 1
        seen.add(t.user_telegram_id)

        stats.by_reason[t.reason] = stats.by_reason.get(t.reason, 0) + 1
        if t.reason == ReasonCategory.PURCHASE and t.purchase_subcategory:
            stats.by_purchase_sub[t.purchase_subcategory] = (
                stats.by_purchase_sub.get(t.purchase_subcategory, 0) + 1
            )

        if t.status in (TicketStatus.ANSWERED, TicketStatus.PAID, TicketStatus.CLOSED):
            stats.answered += 1
        else:
            stats.unanswered += 1

        if t.status == TicketStatus.CLOSED:
            stats.closed += 1

    payments_result = await session.execute(
        select(Payment).where(
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.counted_in_revenue.is_(True),
            Payment.confirmed_at >= start,
            Payment.confirmed_at <= end,
        )
    )
    payments = payments_result.scalars().all()
    stats.confirmed_payments = len(payments)
    stats.turnover = float(sum(float(p.confirmed_amount or 0) for p in payments))

    # "new users" = users whose very first ticket ever falls inside this period
    new_users = 0
    for uid in set(user_ids):
        first_ticket = await session.execute(
            select(func.min(Ticket.created_at)).where(Ticket.user_telegram_id == uid)
        )
        first_dt = first_ticket.scalar_one()
        if first_dt is not None and start <= first_dt <= end:
            new_users += 1
    stats.new_users = new_users

    return stats
