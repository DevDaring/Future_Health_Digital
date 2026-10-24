"""Policy Twin API: start runs (background), poll results, compare history, sensitivity."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.db import get_db
from app.models import SimRun, User
from app.schemas import TwinRunIn
from app.security import require
from app.twin import runner
from app.twin.system_twin import NATIVE_NAVIGATOR_LANGS, POLICIES, POLICY_LABELS, SLA_WINDOW_DAYS, TwinParams

router = APIRouter(prefix="/twin", tags=["twin"])
DB = Annotated[Session, Depends(get_db)]
Runner = Annotated[User, Depends(require("run_twin"))]

ASSUMPTIONS = [
    {"name": "Ground-truth behaviour coefficients", "where": "backend/app/synth/config.yaml → behaviour", "note": "Drive who returns and how much outreach helps"},
    {"name": "Navigator call length", "value": "15 min, 7 h working day", "where": "TwinParams.call_minutes"},
    {"name": "Clinic visits per clinic per day", "value": str(TwinParams().visits_per_clinic_per_day), "where": "TwinParams.visits_per_clinic_per_day"},
    {"name": "Native navigator languages", "value": ", ".join(sorted(NATIVE_NAVIGATOR_LANGS)), "where": "system_twin.NATIVE_NAVIGATOR_LANGS",
     "note": "Other languages go through an interpreter line (60% of the language-match effect)"},
    {"name": "Evening/Friday slot availability", "value": "60% (100% with extra sessions)", "where": "system_twin.simulate"},
    {"name": "Follow-up window counted as closed", "value": f"{SLA_WINDOW_DAYS} days", "where": "system_twin.SLA_WINDOW_DAYS"},
    {"name": "Costs (AED)", "value": "SMS 0.5 · tailored contact 25 · visit 150", "where": "TwinParams.cost_*"},
    {"name": "Severity weights in ranking", "value": "routine 1.0 · high 1.25 · urgent 1.5", "where": "ml/prioritise.SEVERITY_WEIGHT"},
    {"name": "Fairness floor slack ε", "value": "0.10", "where": "TwinParams.fairness_epsilon"},
]


def run_view(r: SimRun) -> dict[str, Any]:
    return {
        "id": str(r.id), "kind": r.kind, "policies": r.policy.split(","), "params": r.params, "seed": r.seed, "status": r.status,
        "results": r.results if r.status == "done" else None, "error": r.error or None, "created_by": r.created_by,
        "created_at": clock.as_utc(r.created_at).isoformat(), "finished_at": clock.as_utc(r.finished_at).isoformat() if r.finished_at else None,
    }


@router.get("/defaults")
def defaults(user: Runner) -> dict[str, Any]:
    return {"params": TwinParams().__dict__, "policies": [{"id": p, "label": POLICY_LABELS[p]} for p in POLICIES], "assumptions": ASSUMPTIONS}


def _create(db: Session, user: User, kind: str, body: TwinRunIn) -> SimRun:
    from datetime import UTC, datetime

    run = SimRun(policy=",".join(body.policies), kind=kind, params=body.params.model_dump(), seed=body.params.seed,
                 status="queued", created_by=user.email, created_at=datetime.now(UTC))
    db.add(run)
    db.commit()
    return run


@router.post("/runs")
def create_run(body: TwinRunIn, db: DB, user: Runner) -> dict[str, Any]:
    run = _create(db, user, "compare", body)
    runner.submit(run.id)
    return run_view(run)


@router.post("/sensitivity")
def create_sensitivity(body: TwinRunIn, db: DB, user: Runner) -> dict[str, Any]:
    run = _create(db, user, "sensitivity", body)
    runner.submit(run.id)
    return run_view(run)


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require("governance_read"))]) -> dict[str, Any]:
    run = db.get(SimRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run_view(run)


@router.get("/runs")
def list_runs(db: DB, user: Annotated[User, Depends(require("governance_read"))], limit: int = 10, kind: str | None = None) -> dict[str, Any]:
    q = select(SimRun).order_by(SimRun.created_at.desc()).limit(min(limit, 50))
    if kind:
        q = q.where(SimRun.kind == kind)
    return {"items": [run_view(r) for r in db.scalars(q)]}
