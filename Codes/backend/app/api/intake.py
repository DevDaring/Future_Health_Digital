"""Add real-looking screening results: one at a time from a form, or many from a CSV.

Each abnormal result opens a care loop with a named owner, an SLA and an audit trail, is
scored by the models, and appears in the Command Center straight away. Urgent results
raise a flag for the clinician on duty; results whose SLA has already passed are flagged as
breaches. Normal results are reported back and do not open a loop.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import ADDED_SOURCES, loop_row, names_for, paginate
from app.config import get_settings
from app.db import get_db
from app.loop_engine import audit, ownership, service
from app.loop_engine.closure import closure_view
from app.loop_engine.sla import check_breaches
from app.ml.score import score_open_loops
from app.models import (
    CareLoop,
    Consent,
    Escalation,
    LoopClosure,
    Patient,
    PatientIdentity,
    RiskScore,
    ScreeningEvent,
    User,
)
from app.security import require
from app.synth.population import classify

router = APIRouter(prefix="/intake", tags=["intake"])
TZ = ZoneInfo("Asia/Dubai")
DB = Annotated[Session, Depends(get_db)]
Writer = Annotated[User, Depends(require("loop_write"))]

PROGRAM_ALIASES = {
    "diabetes": "DIABETES", "hba1c": "DIABETES", "a1c": "DIABETES",
    "colorectal": "COLORECTAL", "fit": "COLORECTAL", "bowel": "COLORECTAL",
    "breast": "BREAST", "mammogram": "BREAST", "birads": "BREAST", "bi-rads": "BREAST",
}
TEST_OF = {"DIABETES": "HBA1C", "COLORECTAL": "FIT", "BREAST": "BIRADS"}
LANGS = ("en", "ar", "hi", "ur", "ml", "bn", "tl")
MAX_ROWS = 200

SAMPLE_CSV = """name,language,sex,age,test,value,result_date,facility,phone,shift
Anil Menon,ml,M,47,HbA1c,7.8,,Mussafah Mobile Screening Van,+971 50 111 2201,night
Mariam Al Suwaidi,ar,F,58,Mammogram,BI-RADS 5,,Al Rahba Hospital Imaging,+971 50 111 2202,day
Rafiq Hossain,bn,M,39,HbA1c,5.4,,Mussafah Mobile Screening Van,+971 50 111 2203,rotating
Grace Santos,tl,F,52,FIT,positive,,Khalifa City Primary Care,+971 50 111 2204,day
Imtiaz Ahmed,ur,M,61,HbA1c,9.6,,Al Khalidiyah Healthcare Centre,+971 50 111 2205,day
Sunita Sharma,hi,F,44,HbA1c,6.1,,Mussafah Mobile Screening Van,+971 50 111 2206,rotating
John Carter,en,M,55,FIT,positive,{old},Khalifa City Primary Care,+971 50 111 2207,day
Fatma Al Hosani,ar,F,49,Mammogram,BI-RADS 1,,Al Rahba Hospital Imaging,+971 50 111 2208,day
"""


class ResultIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    language: Literal["en", "ar", "hi", "ur", "ml", "bn", "tl"] = "en"
    sex: Literal["M", "F"] = "F"
    age: int = Field(45, ge=18, le=100)
    test: str = Field(min_length=2, max_length=20, description="HbA1c, FIT or Mammogram (or the programme name)")
    value: str = Field(min_length=1, max_length=30, description="e.g. 7.8 (HbA1c %), positive (FIT), BI-RADS 4")
    result_date: date | None = None
    facility: str = Field("Reviewer upload", min_length=2, max_length=120)
    phone: str = Field("+971 50 000 0000", max_length=30)
    shift: Literal["day", "night", "rotating"] = "day"


class ResultsIn(BaseModel):
    results: list[ResultIn] = Field(min_length=1, max_length=MAX_ROWS)


class CsvIn(BaseModel):
    csv: str = Field(min_length=10, max_length=200_000)


def _parse_value(program: str, raw: str) -> tuple[float | None, str | None]:
    v = raw.strip()
    if program == "DIABETES":
        try:
            num = float(v.replace("%", "").strip())
        except ValueError as exc:
            raise ValueError(f"HbA1c value must be a number like 7.2, got '{raw}'") from exc
        if not 3 <= num <= 20:
            raise ValueError(f"HbA1c {num}% is outside the plausible range 3–20%")
        return num, None
    if program == "COLORECTAL":
        low = v.lower()
        if low in {"positive", "pos", "+", "detected", "abnormal"}:
            return None, "positive"
        if low in {"negative", "neg", "-", "not detected", "normal"}:
            return None, "negative"
        raise ValueError(f"FIT value must be 'positive' or 'negative', got '{raw}'")
    digits = "".join(c for c in v if c.isdigit())
    if not digits or int(digits[0]) > 6:
        raise ValueError(f"Mammogram value must be a BI-RADS category 0–6, got '{raw}'")
    n = int(digits[0])
    return float(n), f"BI-RADS {n}"


def _create(db: Session, r: ResultIn, source: str, user: User, staff: dict[str, list[User]]) -> dict[str, Any]:
    program = PROGRAM_ALIASES.get(r.test.strip().lower().replace(" ", ""))
    if program is None:
        raise ValueError(f"Unknown test '{r.test}' (use HbA1c, FIT or Mammogram)")
    value_num, value_text = _parse_value(program, r.value)
    sev_cat = classify(program, value_num, value_text)
    test = TEST_OF[program]
    label = {"HBA1C": f"HbA1c {value_num}%", "FIT": f"FIT {value_text}", "BIRADS": f"Mammogram {value_text}"}[test]
    if sev_cat is None:
        return {"name": r.name, "result": label, "status": "normal", "message": "Normal result: no follow-up loop needed"}
    severity, category = sev_cat
    now = clock.now(db)
    if r.result_date is not None:
        resulted = datetime.combine(r.result_date, time(9, 0), tzinfo=TZ)
        if resulted > now:
            raise ValueError("Result date cannot be in the future")
        if resulted < now - timedelta(days=365):
            raise ValueError("Result date is more than a year ago")
    else:
        resulted = now - timedelta(minutes=5)
    pid = uuid.uuid4()
    db.add(Patient(
        id=pid, code=f"WASL-U{pid.hex[:6].upper()}", age=r.age, sex=r.sex, nationality_group="Other", preferred_language=r.language,
        literacy_level=2, occupation_type="labour" if r.shift == "night" else "office", shift_pattern=r.shift,
        preferred_days=["Fri", "Sat"] if r.shift != "day" else ["Mon", "Tue", "Wed", "Thu"], home_area="Abu Dhabi", distance_km=12.0,
        insurance_tier="basic", prior_no_shows=0, has_smartphone=True, preferred_channel="whatsapp", no_free_weekdays=r.shift != "day",
    ))
    db.flush()
    db.add(PatientIdentity(patient_id=pid, full_name=r.name.strip(), phone=r.phone or "+971 50 000 0000", emirates_id_masked="784-****-*******-*"))
    for scope in ("outreach", "data_for_model", "share_with_clinic"):
        db.add(Consent(patient_id=pid, scope=scope, granted=True, granted_at=now, channel=source, note=f"Recorded at screening ({r.facility})"))
    se = ScreeningEvent(patient_id=pid, program=program, test_code=test, value_numeric=value_num, value_text=value_text, severity=severity,
                        category=category, resulted_at=resulted, source=source, facility=r.facility.strip())
    db.add(se)
    db.flush()
    loop = CareLoop(screening_event_id=se.id, patient_id=pid, state="RESULT_RECEIVED",
                    sla_due_at=resulted + timedelta(days=get_settings().sla_days(severity)))
    db.add(loop)
    db.flush()
    db.refresh(loop)
    owner = ownership.assign_default_owner(db, loop, staff)
    audit.append_event(db, loop.id, None, "RESULT_RECEIVED", f"user:{user.email}", f"{label} received from {r.facility.strip()} ({category})",
                       {"source": source, "facility": r.facility.strip()}, now)
    if owner is not None:
        service.record_milestone(db, loop, "assign", "system", f"Owner: {owner.display_name} ({owner.role}) by default rule")
    flags: list[str] = []
    if severity == "urgent":
        esc = service.escalate(db, loop, "urgent_result", "system", f"Urgent {label}: clinician review within 24 h")
        doc = ownership.clinician_on_duty(db)
        esc.assigned_to = doc.id if doc else None
        flags.append("urgent_result")
    return {"name": r.name, "result": label, "status": "loop_created", "loop_id": str(loop.id), "severity": severity, "category": category,
            "owner": owner.display_name if owner else None, "flags": flags, "message": f"Care case opened: {severity} priority, {category}"}


def _ingest(db: Session, rows: list[tuple[int, ResultIn | str]], source: str, user: User) -> dict[str, Any]:
    staff = ownership._staff(db)
    out: list[dict[str, Any]] = []
    created: list[uuid.UUID] = []
    for line, r in rows:
        if isinstance(r, str):
            out.append({"row": line, "status": "error", "message": r})
            continue
        try:
            with db.begin_nested():
                res = _create(db, r, source, user, staff)
        except ValueError as exc:
            out.append({"row": line, "name": r.name, "status": "error", "message": str(exc)})
            continue
        res["row"] = line
        out.append(res)
        if res.get("loop_id"):
            created.append(uuid.UUID(res["loop_id"]))
    if created:
        score_open_loops(db, loop_ids=created)
        breaches_before = {lid for (lid,) in db.execute(select(CareLoop.id).where(CareLoop.id.in_(created), CareLoop.breached.is_(True)))}
        check_breaches(db)
        breached = {lid for (lid,) in db.execute(select(CareLoop.id).where(CareLoop.id.in_(created), CareLoop.breached.is_(True)))} - breaches_before
        for res in out:
            if res.get("loop_id") and uuid.UUID(res["loop_id"]) in breached:
                res["flags"].append("sla_breach")
                res["message"] += "; SLA already passed: breach flagged"
    db.commit()
    summary = {k: sum(1 for x in out if x["status"] == k) for k in ("loop_created", "normal", "error")}
    return {"results": out, "summary": summary}


@router.post("/results")
def add_results(body: ResultsIn, db: DB, user: Writer) -> dict[str, Any]:
    return _ingest(db, list(enumerate(body.results, start=1)), "manual", user)


@router.post("/csv")
def upload_csv(body: CsvIn, db: DB, user: Writer) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(body.csv.lstrip("﻿")))
    if reader.fieldnames is None:
        raise HTTPException(422, "The file is empty")
    fields = {f.strip().lower() for f in reader.fieldnames if f}
    missing = {"name", "test", "value"} - fields
    if missing:
        raise HTTPException(422, f"Missing column(s): {', '.join(sorted(missing))}. Download the template for the expected columns.")
    rows: list[tuple[int, ResultIn | str]] = []
    for i, raw in enumerate(reader, start=2):
        rec = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(rec.values()):
            continue
        if len(rows) >= MAX_ROWS:
            raise HTTPException(422, f"At most {MAX_ROWS} rows per upload")
        data: dict[str, Any] = {k: rec[k] for k in ("name", "test", "value", "facility", "phone") if rec.get(k)}
        if rec.get("language"):
            data["language"] = rec["language"].lower()[:2]
        if rec.get("sex"):
            data["sex"] = rec["sex"].upper()[:1]
        if rec.get("age"):
            data["age"] = rec["age"]
        if rec.get("shift"):
            data["shift"] = rec["shift"].lower()
        if rec.get("result_date"):
            data["result_date"] = rec["result_date"]
        try:
            rows.append((i, ResultIn.model_validate(data)))
        except ValidationError as exc:
            first = exc.errors()[0]
            rows.append((i, f"{'.'.join(str(x) for x in first['loc'])}: {first['msg']}"))
    if not rows:
        raise HTTPException(422, "No data rows found")
    return _ingest(db, rows, "csv_upload", user)


@router.get("/template.csv", response_class=PlainTextResponse)
def template(db: DB, user: Annotated[User, Depends(require("worklist"))]) -> str:
    old = (clock.now(db) - timedelta(days=40)).astimezone(TZ).date().isoformat()
    return SAMPLE_CSV.replace("{old}", old)


@router.get("/recent")
def recent(db: DB, user: Annotated[User, Depends(require("worklist"))], page: int = 1, size: int = Query(50, le=200)) -> dict[str, Any]:
    """Every loop opened from added results, newest first, with its live state."""
    q = (select(CareLoop).join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id)
         .where(ScreeningEvent.source.in_(ADDED_SOURCES)).order_by(CareLoop.created_at.desc()).limit(500))
    if user.role == "navigator":
        q = q.where(CareLoop.assigned_to == user.id)
    loops = list(db.scalars(q).unique())
    now = clock.now(db)
    names = names_for(db, [lp.patient_id for lp in loops], user)
    scores = {s.loop_id: s for s in db.scalars(select(RiskScore).where(RiskScore.loop_id.in_([lp.id for lp in loops])))}
    closures = {c.loop_id: c for c in db.scalars(select(LoopClosure).where(LoopClosure.loop_id.in_([lp.id for lp in loops])))}
    open_esc: dict[uuid.UUID, list[str]] = {}
    for e in db.scalars(select(Escalation).where(Escalation.loop_id.in_([lp.id for lp in loops]), Escalation.status == "open")):
        open_esc.setdefault(e.loop_id, []).append(e.reason)
    items = []
    for lp in loops:
        row = loop_row(lp, names.get(lp.patient_id, "—"), now, scores.get(lp.id))
        row["open_flags"] = open_esc.get(lp.id, [])
        row["closure"] = closure_view(closures.get(lp.id))
        items.append(row)
    return paginate(items, page, size)
