"""Simulated clock.

In demo mode `now()` is real UTC time plus an offset that `/api/demo/advance-clock`
moves forward, so a judge can watch SLA breaches and reminders happen in seconds.
The offset is stored in the `app_settings` table so it survives restarts and is shared
by the API and the scheduler. All SLA logic must call `now()`, never `datetime.now()`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

_OFFSET_KEY = "clock_offset_seconds"
_cache: dict[str, float] = {}


def utcnow_real() -> datetime:
    return datetime.now(UTC)


def offset_seconds(db: Session | None = None) -> float:
    if db is not None:
        from app.models.governance import AppSetting

        row = db.get(AppSetting, _OFFSET_KEY)
        _cache[_OFFSET_KEY] = float(row.value) if row else 0.0
    return _cache.get(_OFFSET_KEY, 0.0)


def now(db: Session | None = None) -> datetime:
    return utcnow_real() + timedelta(seconds=offset_seconds(db))


def advance(db: Session, days: float) -> datetime:
    from app.models.governance import AppSetting

    current = offset_seconds(db)
    new = current + days * 86400.0
    row = db.get(AppSetting, _OFFSET_KEY)
    if row is None:
        db.add(AppSetting(key=_OFFSET_KEY, value=str(new)))
    else:
        row.value = str(new)
    db.flush()
    _cache[_OFFSET_KEY] = new
    return now()


def reset(db: Session) -> None:
    from app.models.governance import AppSetting

    row = db.get(AppSetting, _OFFSET_KEY)
    if row is not None:
        row.value = "0"
    _cache[_OFFSET_KEY] = 0.0


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat every naive value as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
