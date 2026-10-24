"""Shared API helpers: role-masked identity, loop serializers, pagination."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import CareLoop, PatientIdentity, RiskScore, User
from app.security import can


def mask_name(full: str, role: str) -> str:
    parts = full.split()
    if role == "admin":
        return full
    if role == "navigator":
        return parts[0]
    return parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")


def mask_phone(phone: str, role: str) -> str:
    if role == "admin":
        return phone
    digits = phone.replace(" ", "")
    return digits[:6] + " *** **" + digits[-2:] if len(digits) > 8 else "***"


def identity_view(db: Session, patient_id: uuid.UUID, user: User) -> dict[str, Any]:
    ident = db.scalar(select(PatientIdentity).where(PatientIdentity.patient_id == patient_id))
    if ident is None:
        return {"display_name": "Unknown"}
    out: dict[str, Any] = {"display_name": mask_name(ident.full_name, user.role)}
    if user.role != "navigator":
        out["phone"] = mask_phone(ident.phone, user.role)
        out["emirates_id"] = ident.emirates_id_masked if can(user, "pii_full") else "784-****-*******-*"
    else:
        out["phone"] = None
    out["pii_level"] = {"admin": "full", "coordinator": "masked", "clinician": "masked", "navigator": "first_name"}[user.role]
    return out


def names_for(db: Session, patient_ids: list[uuid.UUID], user: User) -> dict[uuid.UUID, str]:
    rows = db.execute(select(PatientIdentity.patient_id, PatientIdentity.full_name).where(PatientIdentity.patient_id.in_(patient_ids)))
    return {pid: mask_name(name, user.role) for pid, name in rows}


def ensure_loop_access(loop: CareLoop | None, user: User) -> CareLoop:
    if loop is None:
        raise HTTPException(404, "Loop not found")
    if user.role == "navigator" and loop.assigned_to != user.id:
        raise HTTPException(403, "Navigators can open assigned loops only")
    return loop


def sla_days_left(loop: CareLoop, now: Any) -> float:
    return round((clock.as_utc(loop.sla_due_at) - now).total_seconds() / 86400, 1)


def loop_row(loop: CareLoop, name: str, now: Any, score: RiskScore | None = None) -> dict[str, Any]:
    se = loop.screening
    p = loop.patient
    top = (score.shap_top[0]["label"] if score and score.shap_top else None) if score else None
    return {
        "id": str(loop.id),
        "patient_id": str(p.id),
        "patient_code": p.code,
        "display_name": name,
        "persona": p.persona,
        "language": p.preferred_language,
        "program": se.program,
        "test_code": se.test_code,
        "value": se.value_numeric,
        "value_text": se.value_text,
        "severity": se.severity,
        "category": se.category,
        "state": loop.state,
        "escalated_from": loop.escalated_from,
        "breached": loop.breached,
        "understood": loop.understood_at is not None,
        "sla_due_at": clock.as_utc(loop.sla_due_at).isoformat(),
        "sla_days_left": sla_days_left(loop, now),
        "p_dropoff": loop.risk_dropoff,
        "uplift": loop.uplift,
        "priority": loop.priority_score,
        "top_reason": top,
        "assigned_to": str(loop.assigned_to) if loop.assigned_to else None,
        "navigator_paused": loop.navigator_paused,
        "resulted_at": clock.as_utc(se.resulted_at).isoformat(),
    }


def paginate(items: list[Any], page: int, size: int) -> dict[str, Any]:
    page = max(page, 1)
    size = max(1, min(size, 500))
    start = (page - 1) * size
    return {"items": items[start : start + size], "total": len(items), "page": page, "size": size}
