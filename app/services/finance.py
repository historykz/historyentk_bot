from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, PaymentStatus, PaymentType
from app.utils.formatting import fmt_money


@dataclass
class FinanceReport:
    period_label: str
    confirmed_count: int = 0
    by_type: dict[PaymentType, Decimal] = field(default_factory=dict)

    @property
    def purchases_total(self) -> Decimal:
        return sum(
            (v for k, v in self.by_type.items() if k != PaymentType.COOPERATION),
            Decimal("0"),
        )

    @property
    def cooperation_total(self) -> Decimal:
        return self.by_type.get(PaymentType.COOPERATION, Decimal("0"))

    @property
    def total_turnover(self) -> Decimal:
        return self.purchases_total + self.cooperation_total

    def render(self) -> str:
        labels = {
            PaymentType.PURCHASE_TESTS: "Тесты",
            PaymentType.PURCHASE_PREMIUM: "Premium",
            PaymentType.PURCHASE_NOTES: "Конспекты",
            PaymentType.PURCHASE_ALL: "Всё вышеперечисленное",
            PaymentType.COOPERATION: "Сотрудничество",
        }
        lines = [
            "Финансовая статистика",
            f"Период: {self.period_label}",
            "",
            f"Подтверждённых оплат: {self.confirmed_count}",
            "",
        ]
        for t in [
            PaymentType.PURCHASE_TESTS,
            PaymentType.PURCHASE_PREMIUM,
            PaymentType.PURCHASE_NOTES,
            PaymentType.PURCHASE_ALL,
        ]:
            lines.append(f"{labels[t]}: {fmt_money(self.by_type.get(t, Decimal('0')))}")
        lines.append(f"Сотрудничество: {fmt_money(self.cooperation_total)}")
        lines += [
            "",
            f"Покупки всего: {fmt_money(self.purchases_total)}",
            f"Сотрудничество всего: {fmt_money(self.cooperation_total)}",
            "",
            f"Общий оборот: {fmt_money(self.total_turnover)}",
        ]
        return "\n".join(lines)


async def build_finance_report(
    session: AsyncSession, start: datetime, end: datetime, period_label: str
) -> FinanceReport:
    result = await session.execute(
        select(Payment).where(
            Payment.status == PaymentStatus.CONFIRMED,
            Payment.counted_in_revenue.is_(True),
            Payment.confirmed_at >= start,
            Payment.confirmed_at <= end,
        )
    )
    payments = result.scalars().all()

    report = FinanceReport(period_label=period_label)
    report.confirmed_count = len(payments)
    for p in payments:
        amt = Decimal(p.confirmed_amount or 0)
        report.by_type[p.payment_type] = report.by_type.get(p.payment_type, Decimal("0")) + amt
    return report
