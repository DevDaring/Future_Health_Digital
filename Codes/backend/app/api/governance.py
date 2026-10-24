"""Trust & governance: fairness, model card, calibration, audit chain, review queue,
consent center."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import paginate
from app.db import get_db
from app.fairness.metrics import GROUP_COLUMNS, fairness_metrics
from app.llm.factory import provider_name
from app.loop_engine import audit, service
from app.ml.registry import load_active
from app.models import CareLoop, Consent, LoopEvent, ModelRegistry, Patient, ReviewItem, User
from app.schemas import ConsentIn, DecideIn
from app.security import require

router = APIRouter(tags=["governance"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("governance_read"))]


@router.get("/fairness/metrics")
def fairness(db: DB, user: Reader, group_by: str = Query("language", pattern="^(language|nationality_group|insurance_tier|sex)$"),
             budget: int = 200) -> dict[str, Any]:
    if group_by not in GROUP_COLUMNS:
        raise HTTPException(422, "bad group_by")
    return fairness_metrics(db, group_by, budget)


@router.get("/governance/model-card")
def model_card(db: DB, user: Reader) -> dict[str, Any]:
    regs = db.scalars(select(ModelRegistry).where(ModelRegistry.is_active.is_(True))).all()
    bundle = load_active()
    m = bundle.metrics if bundle else {}
    return {
        "name": "WASL drop-off risk + T-learner uplift",
        "version": bundle.version if bundle else None,
        "owner": "WASL clinical AI team (demo)",
        "intended_use": "Rank people with an abnormal screening result for human-led outreach under a daily budget, and suggest which "
                        "actionable outreach package (channel, language, slot type, cost information) may help. Decision support for "
                        "care coordinators.",
        "out_of_scope": ["Diagnosis or treatment decisions", "Denying or delaying care to anyone", "Use on real patients without local "
                         "validation, ethics approval and DoH data approvals", "Patient-facing display of risk scores"],
        "training_data": "Synthetic only: a seeded generator of a Gulf-city population and a simulated randomised outreach trial "
                         "(see DATA_CARD.md). No real patient data.",
        "features_excluded": ["nationality (used only to audit fairness)", "names and any identifiers"],
        "limitations": ["Synthetic ground truth: real behaviour will differ", "Uplift is only identifiable because the simulated history "
                        "randomised outreach", "Calibrated on a synthetic validation split", "Counterfactual suggestions are model "
                        "predictions, not causal guarantees"],
        "registry": [{"name": r.name, "version": r.version, "metrics": r.metrics, "trained_at": clock.as_utc(r.trained_at).isoformat()} for r in regs],
        "risk": {k: v for k, v in (m.get("risk") or {}).items() if k in ("auroc", "auprc", "brier", "n", "base_rate")},
        "uplift": {k: v for k, v in (m.get("uplift") or {}).items() if k in ("qini_auuc_observed", "auuc_true", "corr_with_true_tau", "mean_true_tau", "mean_pred_tau", "true_gain_curves", "qini_curves")},
        "data": m.get("data"),
        "feature_importance": m.get("feature_importance"),
        "llm_provider": provider_name(),
    }


@router.get("/governance/calibration")
def calibration(db: DB, user: Reader) -> dict[str, Any]:
    bundle = load_active()
    if bundle is None:
        return {"bins": [], "groups": {}}
    r = bundle.metrics["risk"]
    return {"bins": r["calibration"], "brier": r["brier"],
            "groups": {k: {g: {"brier": v.get("brier"), "n": v.get("n")} for g, v in r[k].items()} for k in ("by_language", "by_insurance_tier")}}


@router.get("/governance/audit/verify")
def verify(db: DB, user: Reader, loop_id: uuid.UUID | None = None) -> dict[str, Any]:
    res = audit.verify_chain(db, loop_id)
    res["verified_at"] = datetime.now(UTC).isoformat()
    return res


@router.get("/governance/audit/export.csv")
def export_csv(db: DB, user: Reader) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "event_id", "loop_id", "from_state", "to_state", "actor", "reason", "created_at", "prev_hash", "hash", "global_hash"])
    for e in db.scalars(select(LoopEvent).order_by(LoopEvent.seq)).yield_per(2000):
        w.writerow([e.seq, e.id, e.loop_id, e.from_state or "", e.to_state, e.actor, e.reason, clock.as_utc(e.created_at).isoformat(), e.prev_hash, e.hash, e.global_hash])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=wasl_audit_log.csv"})


# ---------------------------------------------------------------- review queue

@router.get("/review-queue")
def review_queue(db: DB, user: Reader, status: str = "open", page: int = 1, size: int = 50) -> dict[str, Any]:
    rows = db.execute(
        select(ReviewItem, CareLoop, Patient.code, Patient.persona)
        .join(CareLoop, ReviewItem.loop_id == CareLoop.id, isouter=True)
        .join(Patient, CareLoop.patient_id == Patient.id, isouter=True)
        .where(ReviewItem.status == status)
        .order_by(ReviewItem.created_at.desc())
    ).all()
    items = [
        {"id": str(r.id), "item_type": r.item_type, "item_id": str(r.item_id) if r.item_id else None, "loop_id": str(r.loop_id) if r.loop_id else None,
         "reason": r.reason, "status": r.status, "patient_code": code, "persona": persona, "created_at": clock.as_utc(r.created_at).isoformat(),
         "decision_note": r.decision_note}
        for r, _, code, persona in rows
    ]
    return paginate(items, page, size)


@router.post("/review-queue/{item_id}/decide")
def decide(item_id: uuid.UUID, body: DecideIn, db: DB, user: Annotated[User, Depends(require("approve_templates"))]) -> dict[str, Any]:
    item = db.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(404, "Review item not found")
    item.status = body.decision
    item.reviewer_id = user.id
    item.decision_note = body.note
    if item.loop_id:
        loop = db.get(CareLoop, item.loop_id)
        if loop is not None:
            service.record_milestone(db, loop, "review", f"user:{user.email}", f"{item.item_type} {body.decision}: {body.note}"[:300])
    db.commit()
    return {"id": str(item.id), "status": item.status}


# --------------------------------------------------------------------- consent

@router.get("/consents/{patient_id}")
def get_consents(patient_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require("worklist"))]) -> dict[str, Any]:
    rows = db.scalars(select(Consent).where(Consent.patient_id == patient_id).order_by(Consent.created_at)).all()
    latest: dict[str, Consent] = {}
    for c in rows:
        latest[c.scope] = c
    return {
        "patient_id": str(patient_id),
        "current": {s: {"granted": c.granted and c.revoked_at is None, "granted_at": clock.as_utc(c.granted_at).isoformat() if c.granted_at else None,
                        "revoked_at": clock.as_utc(c.revoked_at).isoformat() if c.revoked_at else None, "channel": c.channel}
                    for s, c in latest.items()},
        "history": [{"scope": c.scope, "granted": c.granted, "revoked_at": clock.as_utc(c.revoked_at).isoformat() if c.revoked_at else None,
                     "created_at": clock.as_utc(c.created_at).isoformat(), "note": c.note} for c in rows],
    }


@router.post("/consents/{patient_id}")
def set_consent(patient_id: uuid.UUID, body: ConsentIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    if db.get(Patient, patient_id) is None:
        raise HTTPException(404, "Patient not found")
    now = clock.now(db)
    prev = db.scalars(select(Consent).where(Consent.patient_id == patient_id, Consent.scope == body.scope, Consent.revoked_at.is_(None))).all()
    for c in prev:
        c.revoked_at = now if not body.granted else c.revoked_at
    db.add(Consent(patient_id=patient_id, scope=body.scope, granted=body.granted, granted_at=now if body.granted else None,
                   revoked_at=None if body.granted else now, channel="staff", note=body.note or f"set by {user.email}"))
    for loop in db.scalars(select(CareLoop).where(CareLoop.patient_id == patient_id)):
        service.record_milestone(db, loop, "consent", f"user:{user.email}", f"{body.scope} {'granted' if body.granted else 'revoked'}")
    db.commit()
    return get_consents(patient_id, db, user)
