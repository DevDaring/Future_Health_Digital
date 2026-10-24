"""The only code path that changes a loop's state. Every change is validated by the state
machine and written to the hash-chained event log in the same transaction."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.loop_engine import audit
from app.loop_engine.state_machine import validate
from app.models import CareLoop, Escalation


def transition(
    db: Session,
    loop: CareLoop,
    to_state: str,
    actor: str,
    reason: str = "",
    payload: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> CareLoop:
    from_state = loop.state
    validate(from_state, to_state, loop.escalated_from)
    when = at or clock.now(db)
    if to_state == "ESCALATED":
        loop.escalated_from = from_state
    elif from_state == "ESCALATED":
        loop.escalated_from = None
    loop.state = to_state
    if to_state == "UNDERSTOOD":
        loop.understood_at = when
    if to_state in {"CLOSED", "DECLINED"}:
        loop.closed_at = when
    if to_state in {"NOTIFIED", "ENGAGED"}:
        loop.last_contact_at = when
    audit.append_event(db, loop.id, from_state, to_state, actor, reason, payload, when)
    db.flush()
    return loop


def record_milestone(
    db: Session, loop: CareLoop, label: str, actor: str, reason: str, payload: dict[str, Any] | None = None
) -> None:
    """Hash-chain a non-transition event (e.g. consent revoked, translation fallback)."""
    audit.append_event(db, loop.id, loop.state, loop.state, actor, f"{label}: {reason}", payload, clock.now(db))


def escalate(
    db: Session,
    loop: CareLoop,
    reason: str,
    actor: str,
    notes: str = "",
    detail: dict[str, Any] | None = None,
    pause_navigator: bool = False,
) -> Escalation:
    """Open an escalation. Red flags also move the loop to ESCALATED and pause the AI."""
    esc = Escalation(loop_id=loop.id, reason=reason, status="open", notes=notes, detail=detail or {})
    db.add(esc)
    if pause_navigator:
        loop.navigator_paused = True
    if loop.state not in {"CLOSED", "DECLINED", "ESCALATED", "ATTENDED"} and reason in {"red_flag", "sla_breach"}:
        transition(db, loop, "ESCALATED", actor, f"{reason}: {notes}"[:300], {"escalation": reason})
    else:
        record_milestone(db, loop, "escalation", actor, f"{reason} {notes}"[:300])
    db.flush()
    return esc


def resolve_escalation(db: Session, esc: Escalation, actor: str, new_status: str, notes: str = "") -> Escalation:
    esc.status = new_status
    if notes:
        esc.notes = (esc.notes + "\n" + notes).strip()
    loop = db.get(CareLoop, esc.loop_id)
    if loop is not None and new_status in {"ack", "resolved"}:
        loop.navigator_paused = False
        if loop.state == "ESCALATED":
            others = db.scalars(
                select(Escalation).where(
                    Escalation.loop_id == loop.id, Escalation.status == "open", Escalation.id != esc.id
                )
            ).first()
            if others is None and loop.escalated_from:
                transition(db, loop, loop.escalated_from, actor, f"escalation {new_status} by human")
    db.flush()
    return esc
