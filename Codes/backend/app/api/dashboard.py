"""Command Center data: KPIs, funnel (from the event log), breaches by program, live feed."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import ADDED_SOURCES
from app.db import get_db
from app.loop_engine.state_machine import FUNNEL, TERMINAL
from app.models import CareLoop, Escalation, LoopClosure, LoopEvent, Patient, ScreeningEvent
from app.security import require

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
Staff = Annotated[Any, Depends(require("worklist"))]
DB = Annotated[Session, Depends(get_db)]


def _loop_ids(db: Session, scope: str | None) -> set[Any] | None:
    """None means every loop; 'added' limits to results a reviewer or a connected system added."""
    if scope != "added":
        return None
    q = select(CareLoop.id).join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id).where(ScreeningEvent.source.in_(ADDED_SOURCES))
    return set(db.scalars(q))


@router.get("/kpis")
def kpis(db: DB, user: Staff, scope: str | None = None) -> dict[str, Any]:
    now = clock.now(db)
    ids = _loop_ids(db, scope)

    def scoped(q: Any) -> Any:
        return q if ids is None else q.where(CareLoop.id.in_(ids))

    total = int(db.scalar(scoped(select(func.count(CareLoop.id)))) or 0)
    open_n = int(db.scalar(scoped(select(func.count(CareLoop.id)).where(CareLoop.state.notin_(list(TERMINAL | {"ATTENDED"}))))) or 0)
    since = now - timedelta(days=30)
    # 30-day closure: loops whose result is 30–120 days old; share that reached ATTENDED/CLOSED.
    # Added results are new, so for them it is the share closed so far.
    cohort = db.execute(
        scoped(select(CareLoop.state, ScreeningEvent.resulted_at)
               .join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id))
    ).all()
    mature = [s for s, r in cohort if ids is not None or clock.as_utc(r) <= since]
    closure_30 = float(np.mean([s in {"ATTENDED", "CLOSED"} for s in mature])) if mature else 0.0
    # Median days result → attended, from the event log.
    attended = db.execute(
        select(LoopEvent.loop_id, LoopEvent.created_at).where(LoopEvent.to_state == "ATTENDED")
    ).all()
    resulted = dict(db.execute(scoped(select(CareLoop.id, ScreeningEvent.resulted_at).join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id))).all())
    days = [(clock.as_utc(t) - clock.as_utc(resulted[lid])).total_seconds() / 86400 for lid, t in attended if lid in resulted]
    breaches = int(db.scalar(scoped(select(func.count(CareLoop.id)).where(CareLoop.breached.is_(True), CareLoop.state.notin_(["CLOSED", "DECLINED", "ATTENDED"])))) or 0)
    esc_q = select(func.count(Escalation.id)).join(CareLoop, Escalation.loop_id == CareLoop.id).where(Escalation.status == "open")
    esc_open = int(db.scalar(scoped(esc_q)) or 0)
    red_open = int(db.scalar(scoped(esc_q.where(Escalation.reason == "red_flag"))) or 0)
    urgent_open = int(db.scalar(scoped(esc_q.where(Escalation.reason == "urgent_result"))) or 0)
    unowned = int(db.scalar(scoped(select(func.count(CareLoop.id)).where(CareLoop.assigned_to.is_(None), CareLoop.state.notin_(list(TERMINAL))))) or 0)
    awaiting_closure = int(db.scalar(scoped(select(func.count(CareLoop.id)).where(CareLoop.state == "ATTENDED"))) or 0)
    closed = int(db.scalar(scoped(select(func.count(CareLoop.id)).where(CareLoop.state == "CLOSED"))) or 0)
    documented = int(db.scalar(scoped(select(func.count(LoopClosure.id)).join(CareLoop, LoopClosure.loop_id == CareLoop.id).where(CareLoop.state == "CLOSED"))) or 0)
    never = 1 - closure_30
    return {
        "scope": scope or "all",
        "total_loops": total,
        "open_loops": open_n,
        "closure_rate_30d": round(closure_30, 4),
        "never_completed_share": round(never, 4),
        "median_days_to_followup": round(float(np.median(days)), 1) if days else None,
        "sla_breaches": breaches,
        "open_escalations": esc_open,
        "open_red_flags": red_open,
        "open_urgent_results": urgent_open,
        "unowned_open_loops": unowned,
        "awaiting_closure": awaiting_closure,
        "closed_loops": closed,
        "closed_documented": documented,
        "now": now.isoformat(),
        "clock_offset_days": round(clock.offset_seconds(db) / 86400, 2),
    }


@router.get("/funnel")
def funnel(db: DB, user: Staff, program: str | None = None, group: str | None = None, scope: str | None = None) -> dict[str, Any]:
    """Counts of loops that *reached* each funnel step (from the hash-chained event log)."""
    q = select(CareLoop.id).join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id).join(Patient, CareLoop.patient_id == Patient.id)
    if scope == "added":
        q = q.where(ScreeningEvent.source.in_(ADDED_SOURCES))
    if program:
        q = q.where(ScreeningEvent.program == program)
    if group:
        q = q.where(Patient.preferred_language == group)
    ids = set(db.scalars(q))
    reached: dict[Any, int] = defaultdict(int)
    rank = {s: i for i, s in enumerate(FUNNEL)}
    for lid, st in db.execute(select(LoopEvent.loop_id, LoopEvent.to_state)):
        if lid in ids and st in rank:
            reached[lid] = max(reached[lid], rank[st])
    for lid in ids:
        reached.setdefault(lid, 0)
    counts = [sum(1 for v in reached.values() if v >= i) for i in range(len(FUNNEL))]
    steps = []
    for i, s in enumerate(FUNNEL):
        prev = counts[i - 1] if i else counts[0]
        steps.append({"state": s, "count": counts[i], "dropoff_pct": round(100 * (1 - counts[i] / prev), 1) if i and prev else 0.0})
    # UNDERSTOOD is a WASL-only step (teach-back); legacy loops skip it, so it is reported
    # as a pass-through for the biggest-drop calculation.
    real = [s for s in steps[1:] if s["state"] != "UNDERSTOOD"]
    biggest = max(real, key=lambda s: s["dropoff_pct"]) if real else None
    return {"steps": steps, "total": len(ids), "biggest_drop": biggest, "program": program, "group": group, "scope": scope or "all"}


@router.get("/breaches")
def breaches_by_program(db: DB, user: Staff, scope: str | None = None) -> dict[str, Any]:
    q = (select(ScreeningEvent.program, ScreeningEvent.severity, func.count(CareLoop.id))
         .join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id)
         .where(CareLoop.breached.is_(True), CareLoop.state.notin_(["CLOSED", "DECLINED", "ATTENDED"])))
    if scope == "added":
        q = q.where(ScreeningEvent.source.in_(ADDED_SOURCES))
    rows = db.execute(q.group_by(ScreeningEvent.program, ScreeningEvent.severity)).all()
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"routine": 0, "high": 0, "urgent": 0})
    for prog, sev, n in rows:
        out[prog][sev] = int(n)
    return {"by_program": [{"program": p, **v} for p, v in sorted(out.items())]}


@router.get("/feed")
def feed(db: DB, user: Staff, limit: int = 15, scope: str | None = None) -> dict[str, Any]:
    """Latest loop events (live activity ticker)."""
    q = (select(LoopEvent, Patient.code, Patient.persona)
         .join(CareLoop, LoopEvent.loop_id == CareLoop.id)
         .join(Patient, CareLoop.patient_id == Patient.id))
    if scope == "added":
        q = q.join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id).where(ScreeningEvent.source.in_(ADDED_SOURCES))
    rows = db.execute(q.order_by(LoopEvent.seq.desc()).limit(min(limit, 50))).all()
    return {
        "events": [
            {"id": str(e.id), "seq": e.seq, "loop_id": str(e.loop_id), "patient_code": code, "persona": persona,
             "from_state": e.from_state, "to_state": e.to_state, "actor": e.actor, "reason": e.reason,
             "created_at": clock.as_utc(e.created_at).isoformat(), "hash": e.hash[:12]}
            for e, code, persona in rows
        ]
    }
