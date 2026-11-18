"""Documented closure: the only way a care loop reaches CLOSED.

A loop is closed by its owner (or a clinician / coordinator) with a closure record that
says who saw the patient, when, what happened, what comes next, that the patient was told,
and which provider received the report. The record and the CLOSED transition are written
in the same transaction and the transition is hash-chained in the audit log.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.loop_engine import service
from app.models import Appointment, CareLoop, Escalation, LoopClosure, User

OUTCOMES: dict[str, str] = {
    "referral_completed": "Seen — follow-up test or consultation completed",
    "treatment_started": "Seen — treatment or care plan started",
    "no_further_action": "Seen — clinician confirmed no further action needed",
    "seen_elsewhere": "Seen at another provider — outcome received",
}

# Loops in these states can be closed once the visit is documented. A visit at another
# provider can be recorded from any open state (the patient may self-present elsewhere).
CLOSABLE_AFTER_VISIT = {"ATTENDED"}
VISIT_FROM = {"BOOKED", "NOTIFIED", "ENGAGED", "UNDERSTOOD", "NO_SHOW", "UNREACHABLE", "BREACHED", "ESCALATED", "RESULT_RECEIVED"}


class ClosureError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def closure_view(c: LoopClosure | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {
        "id": str(c.id),
        "outcome": c.outcome,
        "outcome_label": OUTCOMES.get(c.outcome, c.outcome),
        "seen_by": c.seen_by,
        "visit_date": clock.as_utc(c.visit_date).isoformat() if c.visit_date else None,
        "summary": c.summary,
        "next_step": c.next_step,
        "patient_informed": c.patient_informed,
        "report_shared_with": c.report_shared_with,
        "closed_by_name": c.closed_by_name,
        "closed_at": clock.as_utc(c.closed_at).isoformat(),
    }


def close_loop(
    db: Session,
    loop: CareLoop,
    user: User,
    *,
    outcome: str,
    seen_by: str,
    visit_date: datetime,
    summary: str,
    next_step: str,
    patient_informed: bool,
    report_shared_with: str,
) -> LoopClosure:
    if loop.state == "CLOSED":
        raise ClosureError(409, "This loop is already closed")
    if outcome not in OUTCOMES:
        raise ClosureError(422, f"Unknown outcome '{outcome}'")
    if not patient_informed:
        raise ClosureError(422, "Tell the patient the outcome before closing the loop (patient informed must be confirmed)")
    if not seen_by.strip() or len(summary.strip()) < 10:
        raise ClosureError(422, "Record who saw the patient and a short outcome summary (10+ characters)")
    if not report_shared_with.strip():
        raise ClosureError(422, "Record which provider received the outcome report")
    now = clock.now(db)
    if clock.as_utc(visit_date) > now:
        raise ClosureError(422, "The visit date cannot be in the future")
    if clock.as_utc(visit_date) < clock.as_utc(loop.screening.resulted_at):
        raise ClosureError(422, "The visit date cannot be before the screening result")
    actor = f"user:{user.email}"
    if loop.state not in CLOSABLE_AFTER_VISIT:
        if loop.state not in VISIT_FROM:
            raise ClosureError(409, f"A {loop.state} loop cannot be closed")
        if loop.state != "BOOKED" and outcome != "seen_elsewhere":
            raise ClosureError(409, "No visit is on record yet. Mark the visit attended first, or choose 'Seen at another provider'.")
        service.transition(db, loop, "ATTENDED", actor, f"Visit documented: seen by {seen_by.strip()[:120]}",
                           {"seen_by": seen_by.strip()[:160], "visit_date": clock.as_utc(visit_date).isoformat()}, at=now)
    for ap in db.scalars(select(Appointment).where(Appointment.loop_id == loop.id, Appointment.status == "booked")):
        ap.status = "attended"
    rec = LoopClosure(
        loop_id=loop.id, outcome=outcome, seen_by=seen_by.strip()[:160], visit_date=visit_date, summary=summary.strip()[:2000],
        next_step=next_step.strip()[:200], patient_informed=True, report_shared_with=report_shared_with.strip()[:160],
        closed_by=user.id, closed_by_name=user.display_name, closed_at=now,
    )
    db.add(rec)
    db.flush()
    service.transition(
        db, loop, "CLOSED", actor, f"Closed: {OUTCOMES[outcome]}",
        {"closure_id": str(rec.id), "outcome": outcome, "seen_by": rec.seen_by, "report_shared_with": rec.report_shared_with,
         "patient_informed": True},
        at=now,
    )
    for esc in db.scalars(select(Escalation).where(Escalation.loop_id == loop.id, Escalation.status == "open")):
        esc.status = "resolved"
        esc.notes = (esc.notes + "\nResolved by documented loop closure").strip()
    db.flush()
    return rec
