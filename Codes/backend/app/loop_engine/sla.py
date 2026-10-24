"""SLA monitor. Runs every minute in demo mode (hourly otherwise) via APScheduler, and
immediately after `/demo/advance-clock`.

A loop that has not reached ATTENDED by `sla_due_at` is flagged `breached`, moved to
BREACHED and an `sla_breach` escalation is opened (once per loop).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.loop_engine import service
from app.models import CareLoop, Escalation

log = logging.getLogger("wasl.sla")

BREACHABLE = {"RESULT_RECEIVED", "NOTIFIED", "ENGAGED", "UNDERSTOOD", "NO_SHOW", "UNREACHABLE"}


def check_breaches(db: Session, limit: int = 5000) -> int:
    now = clock.now(db)
    loops = db.scalars(
        select(CareLoop)
        .where(CareLoop.breached.is_(False), CareLoop.sla_due_at < now, CareLoop.state.in_(BREACHABLE | {"BOOKED", "ESCALATED"}))
        .limit(limit)
    ).all()
    count = 0
    for loop in loops:
        if loop.state == "BOOKED":
            # Booked but SLA passes before the visit: flag only, booking stands.
            loop.breached = True
            service.record_milestone(db, loop, "sla", "system", "SLA passed while booked")
            continue
        loop.breached = True
        if loop.state in BREACHABLE:
            service.transition(db, loop, "BREACHED", "system", "SLA expired without reaching ATTENDED")
        exists = db.scalar(
            select(Escalation).where(Escalation.loop_id == loop.id, Escalation.reason == "sla_breach")
        )
        if exists is None:
            db.add(
                Escalation(
                    loop_id=loop.id,
                    reason="sla_breach",
                    status="open",
                    notes=f"SLA ({loop.screening.severity}) expired",
                    detail={"sla_due_at": loop.sla_due_at.isoformat()},
                )
            )
        count += 1
    db.flush()
    if count:
        log.info("SLA job: %d new breaches", count)
    return count


def run_job() -> None:
    from app.db import session_scope

    try:
        with session_scope() as db:
            check_breaches(db)
    except Exception:  # pragma: no cover - logged, never kills the scheduler
        log.exception("SLA job failed")
