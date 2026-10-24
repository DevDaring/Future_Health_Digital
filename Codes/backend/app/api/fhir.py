"""FHIR R4 endpoints (JSON)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.fhir import mappers
from app.ml.score import score_open_loops
from app.models import Appointment, CareLoop, Patient, ScreeningEvent, User
from app.security import require

router = APIRouter(prefix="/fhir", tags=["fhir"])
DB = Annotated[Session, Depends(get_db)]
Staff = Annotated[User, Depends(require("worklist"))]


@router.get("/Observation")
def observations(db: DB, user: Staff, patient: uuid.UUID) -> dict[str, Any]:
    p = db.get(Patient, patient)
    if p is None:
        raise HTTPException(404, "Patient not found")
    obs = [mappers.observation(se, p) for se in db.scalars(select(ScreeningEvent).where(ScreeningEvent.patient_id == patient))]
    return {"resourceType": "Bundle", "type": "searchset", "total": len(obs), "entry": [{"resource": o} for o in obs]}


@router.get("/Task/{loop_id}")
def task(loop_id: uuid.UUID, db: DB, user: Staff) -> dict[str, Any]:
    loop = db.get(CareLoop, loop_id)
    if loop is None:
        raise HTTPException(404, "Loop not found")
    return mappers.task(loop)


@router.get("/ServiceRequest/{loop_id}")
def service_request(loop_id: uuid.UUID, db: DB, user: Staff) -> dict[str, Any]:
    loop = db.get(CareLoop, loop_id)
    if loop is None:
        raise HTTPException(404, "Loop not found")
    return mappers.service_request(loop)


@router.get("/Appointment/{appointment_id}")
def appointment(appointment_id: uuid.UUID, db: DB, user: Staff) -> dict[str, Any]:
    ap = db.get(Appointment, appointment_id)
    if ap is None:
        raise HTTPException(404, "Appointment not found")
    loop = db.get(CareLoop, ap.loop_id)
    assert loop is not None
    return mappers.appointment(ap, loop)


@router.post("/Bundle")
def import_bundle(db: DB, user: Annotated[User, Depends(require("loop_write"))], bundle: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        loops = mappers.import_bundle(db, bundle)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, f"Invalid bundle: {exc}") from exc
    score_open_loops(db, loop_ids=[lp.id for lp in loops])
    db.commit()
    return {"created_loops": [str(lp.id) for lp in loops], "count": len(loops)}


@router.get("/sample-bundle")
def sample_bundle(user: Staff) -> dict[str, Any]:
    import json

    from app.config import FIXTURES_DIR

    return json.loads((FIXTURES_DIR / "fhir" / "sample_bundle.json").read_text())
