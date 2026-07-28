from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings

TZ = ZoneInfo(settings.TIMEZONE)


def now_local() -> datetime:
    return datetime.now(TZ)


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    local = dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    return local.strftime("%d.%m.%Y, %H:%M")


def period_bounds(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) in local tz for a named period: today/week/month/all."""
    now = now_local()
    end = now
    if period == "today":
        start = datetime.combine(now.date(), time.min, tzinfo=TZ)
    elif period == "week":
        monday = now.date() - timedelta(days=now.weekday())
        start = datetime.combine(monday, time.min, tzinfo=TZ)
    elif period == "month":
        start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=TZ)
    else:  # all
        start = datetime(2000, 1, 1, tzinfo=TZ)
    return start, end


def parse_ddmmyyyy(text: str) -> datetime:
    dt = datetime.strptime(text.strip(), "%d.%m.%Y")
    return dt.replace(tzinfo=TZ)
