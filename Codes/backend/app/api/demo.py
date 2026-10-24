"""Demo controls (enabled only when DEMO_MODE=true): reset, simulated clock, persona
lookup, and an audit tamper/repair pair so a judge can watch the chain break."""

from __future__ import annotations

import logging
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.config import get_settings
from app.db import get_db, session_scope
from app.llm.factory import provider_name
from app.loop_engine import audit
from app.loop_engine.sla import check_breaches
from app.ml.registry import load_active
from app.models import AppSetting, CareLoop, DemoState, LoopEvent, Patient, PatientIdentity, User
from app.navigator.flow import send_due_reminders
from app.security import require

router = APIRouter(prefix="/demo", tags=["demo"])
DB = Annotated[Session, Depends(get_db)]
log = logging.getLogger("wasl.demo")
_reset_lock = threading.Lock()


def _demo_only() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(403, "Demo endpoints are disabled (DEMO_MODE=false)")


def reset_everything(db: Session, retrain: bool = False) -> dict[str, Any]:
    from app.ml.score import score_open_loops
    from app.ml.train import register, train_all
    from app.synth.seed import seed_all

    info = seed_all(db)
    bundle = load_active()
    if bundle is None or retrain:
        bundle, _ = train_all(get_settings().seed)
    register(db, bundle)
    info["scored"] = score_open_loops(db, bundle)
    info["model_version"] = bundle.version
    return info


def prewarm_personas() -> None:
    """With a real LLM, pre-compute and cache every persona's checked messages so the
    live demo is instant. No-op with the mock provider."""
    if provider_name() == "mock":
        return
    from app.navigator import messaging as M
    from app.navigator.content import templates_fixture

    try:
        with session_scope() as db:
            loops = db.scalars(select(CareLoop).join(Patient, CareLoop.patient_id == Patient.id).where(Patient.persona.is_not(None))).all()
            generic = [k for k in templates_fixture()["generic"] if k not in ("booked_confirm", "reminder_48h", "reminder_2h")]
            for loop in loops:
                keys = ["result_explain", "next_step", "result_simple", *generic]
                rendered = []
                for k in keys:
                    try:
                        rendered.append(M.render(db, loop, k, loop.patient.preferred_language))
                    except KeyError:
                        continue
                M.prepare(db, loop, rendered, loop.patient.preferred_language)
                db.commit()
                log.info("prewarmed %s (%d messages)", loop.patient.persona, len(rendered))
    except Exception:  # pragma: no cover - best effort
        log.exception("prewarm failed")


@router.post("/reset")
def reset(db: DB, user: Annotated[User, Depends(require("demo_admin"))], retrain: bool = False) -> dict[str, Any]:
    _demo_only()
    if not _reset_lock.acquire(blocking=False):
        raise HTTPException(409, "A reset is already running")
    try:
        info = reset_everything(db, retrain)
        db.commit()
    finally:
        _reset_lock.release()
    threading.Thread(target=prewarm_personas, daemon=True).start()
    return info


@router.post("/advance-clock")
def advance_clock(db: DB, user: Annotated[User, Depends(require("loop_write"))], days: float = Query(7, ge=0.01, le=120)) -> dict[str, Any]:
    _demo_only()
    now = clock.advance(db, days)
    breaches = check_breaches(db)
    reminders = send_due_reminders(db)
    db.commit()
    return {"now": now.isoformat(), "offset_days": round(clock.offset_seconds() / 86400, 2), "new_breaches": breaches, "reminders_sent": reminders}


@router.get("/state")
def state(db: DB, user: Annotated[User, Depends(require("worklist"))]) -> dict[str, Any]:
    ds = db.get(DemoState, 1)
    rows = db.execute(
        select(CareLoop, Patient, PatientIdentity.full_name)
        .join(Patient, CareLoop.patient_id == Patient.id)
        .join(PatientIdentity, PatientIdentity.patient_id == Patient.id)
        .where(Patient.persona.is_not(None))
    ).all()
    from app.api.common import mask_name
    from app.synth.personas import PERSONAS

    stories = {p["persona"]: p["story"] for p in PERSONAS}
    bundle = load_active()
    return {
        "demo_mode": get_settings().demo_mode,
        "now": clock.now(db).isoformat(),
        "offset_days": round(clock.offset_seconds(db) / 86400, 2),
        "llm_provider": provider_name(),
        "llm_live": provider_name() != "mock",
        "model_version": bundle.version if bundle else None,
        "seed": ds.seed if ds else None,
        "checksum": ds.checksum if ds else None,
        "counts": ds.counts if ds else None,
        "personas": {
            p.persona: {"loop_id": str(lp.id), "patient_id": str(p.id), "name": mask_name(name, user.role), "state": lp.state,
                        "language": p.preferred_language, "program": lp.screening.program, "story": stories.get(p.persona or "")}
            for lp, p, name in rows
        },
    }


@router.post("/tamper")
def tamper(db: DB, user: Annotated[User, Depends(require("demo_admin"))]) -> dict[str, Any]:
    """Edit one stored audit row *without* re-hashing (what an attacker would do)."""
    _demo_only()
    ev = db.scalar(select(LoopEvent).order_by(LoopEvent.seq).offset(10).limit(1))
    if ev is None:
        raise HTTPException(404, "No events")
    original = ev.reason
    db.merge(AppSetting(key="tamper_backup", value=f"{ev.id}|{original}"))
    ev.reason = original + " [edited]"
    db.commit()
    res = audit.verify_chain(db)
    return {"tampered_event": str(ev.id), "seq": ev.seq, "verify": res}


@router.post("/untamper")
def untamper(db: DB, user: Annotated[User, Depends(require("demo_admin"))]) -> dict[str, Any]:
    _demo_only()
    backup = db.get(AppSetting, "tamper_backup")
    if backup is None:
        return {"restored": False, "verify": audit.verify_chain(db)}
    ev_id, reason = backup.value.split("|", 1)
    import uuid

    ev = db.get(LoopEvent, uuid.UUID(ev_id))
    if ev is not None:
        ev.reason = reason
    db.delete(backup)
    db.commit()
    return {"restored": True, "verify": audit.verify_chain(db)}

