"""Escalations: red flags, SLA breaches, translation failures, LLM refusals."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import names_for, paginate
from app.db import get_db
from app.loop_engine import service
from app.models import CareLoop, Escalation, User
from app.schemas import NoteIn
from app.security import require

router = APIRouter(prefix="/escalations", tags=["escalations"])
DB = Annotated[Session, Depends(get_db)]
PRIORITY = {"red_flag": 0, "llm_refusal": 1, "translation_fail": 2, "refusal_review": 3, "sla_breach": 4}


@router.get("")
def list_escalations(db: DB, user: Annotated[User, Depends(require("worklist"))], status: str | None = "open",
                     reason: str | None = None, page: int = 1, size: int = 50) -> dict[str, Any]:
    q = select(Escalation, CareLoop).join(CareLoop, Escalation.loop_id == CareLoop.id)
    if status:
        q = q.where(Escalation.status == status)
    if reason:
        q = q.where(Escalation.reason == reason)
    if user.role == "navigator":
        q = q.where(CareLoop.assigned_to == user.id)
    rows = db.execute(q.order_by(Escalation.created_at.desc()).limit(2000)).all()
    names = names_for(db, [lp.patient_id for _, lp in rows], user)
    items = [
        {
            "id": str(e.id), "loop_id": str(lp.id), "reason": e.reason, "status": e.status, "notes": e.notes,
            "detail": e.detail, "created_at": clock.as_utc(e.created_at).isoformat(), "display_name": names.get(lp.patient_id, "—"),
            "patient_code": lp.patient.code, "persona": lp.patient.persona, "program": lp.screening.program,
            "severity": lp.screening.severity, "loop_state": lp.state,
        }
        for e, lp in rows
    ]
    # Newest first, then (stable sort) red flags before everything else.
    items.sort(key=lambda x: x["created_at"], reverse=True)
    items.sort(key=lambda x: PRIORITY.get(x["reason"], 9))
    counts: dict[str, int] = {}
    for it in items:
        counts[it["reason"]] = counts.get(it["reason"], 0) + 1
    return {**paginate(items, page, size), "counts": counts}


def _act(esc_id: uuid.UUID, db: Session, user: User, status: str, notes: str) -> dict[str, Any]:
    esc = db.get(Escalation, esc_id)
    if esc is None:
        raise HTTPException(404, "Escalation not found")
    esc.assigned_to = user.id
    service.resolve_escalation(db, esc, f"user:{user.email}", status, notes)
    db.commit()
    return {"id": str(esc.id), "status": esc.status}


@router.post("/{esc_id}/ack")
def ack(esc_id: uuid.UUID, body: NoteIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    return _act(esc_id, db, user, "ack", body.notes or "Acknowledged by human")


@router.post("/{esc_id}/resolve")
def resolve(esc_id: uuid.UUID, body: NoteIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    return _act(esc_id, db, user, "resolved", body.notes or "Resolved")
