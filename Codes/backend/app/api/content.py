"""Content Studio: clinician-approved templates, approval workflow, translation-check
log and a live preview of any template through the full QA pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import paginate
from app.db import get_db
from app.llm.factory import get_provider
from app.llm.pii_firewall import FirewalledProvider
from app.llm.tasks import Tasks
from app.models import ApprovedTranslation, CareLoop, ContentTemplate, Patient, TranslationCheck, User
from app.navigator import messaging as M
from app.navigator.content import safe_format
from app.schemas import PreviewIn, TemplateIn
from app.security import require

router = APIRouter(prefix="/content", tags=["content"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[User, Depends(require("worklist"))]


def template_view(t: ContentTemplate, langs: list[str]) -> dict[str, Any]:
    return {"id": str(t.id), "program": t.program, "severity": t.severity, "key": t.key, "language": t.language, "body": t.body,
            "approved_by": t.approved_by, "approved_at": clock.as_utc(t.approved_at).isoformat() if t.approved_at else None,
            "version": t.version, "status": t.status, "translations": langs}


@router.get("/templates")
def templates(db: DB, user: Reader, program: str | None = None, status: str | None = None) -> dict[str, Any]:
    q = select(ContentTemplate).order_by(ContentTemplate.program, ContentTemplate.severity, ContentTemplate.key, ContentTemplate.version.desc())
    if program:
        q = q.where(ContentTemplate.program == program)
    if status:
        q = q.where(ContentTemplate.status == status)
    trs: dict[uuid.UUID, list[str]] = {}
    for tid, lang in db.execute(select(ApprovedTranslation.template_id, ApprovedTranslation.language)):
        trs.setdefault(tid, []).append(lang)
    return {"items": [template_view(t, sorted(trs.get(t.id, []))) for t in db.scalars(q)]}


@router.post("/templates")
def create_template(body: TemplateIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    latest = db.scalar(select(func.max(ContentTemplate.version)).where(
        ContentTemplate.program == body.program, ContentTemplate.severity == body.severity, ContentTemplate.key == body.key))
    t = ContentTemplate(program=body.program, severity=body.severity, key=body.key, language="en", body=body.body,
                        version=(latest or 0) + 1, status="draft")
    db.add(t)
    db.commit()
    return template_view(t, [])


@router.post("/templates/{template_id}/approve")
def approve(template_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require("approve_templates"))]) -> dict[str, Any]:
    t = db.get(ContentTemplate, template_id)
    if t is None:
        raise HTTPException(404, "Template not found")
    for old in db.scalars(select(ContentTemplate).where(ContentTemplate.program == t.program, ContentTemplate.severity == t.severity,
                                                        ContentTemplate.key == t.key, ContentTemplate.status == "approved", ContentTemplate.id != t.id)):
        old.status = "retired"
    t.status = "approved"
    t.approved_by = user.display_name
    t.approved_at = datetime.now(UTC)
    db.commit()
    return template_view(t, [])


@router.get("/translation-checks")
def translation_checks(db: DB, user: Reader, failed: bool = False, page: int = 1, size: int = 50) -> dict[str, Any]:
    q = select(TranslationCheck).order_by(TranslationCheck.created_at.desc()).limit(1000)
    if failed:
        q = q.where(TranslationCheck.passed.is_(False))
    items = [
        {"id": str(t.id), "loop_id": str(t.loop_id) if t.loop_id else None, "template_key": t.template_key, "language": t.language,
         "source_en": t.simplified_en or t.source_en, "translated": t.translated, "back_translated": t.back_translated,
         "judge_score": t.judge_score, "entity_match": t.entity_match, "discrepancies": t.discrepancies, "passed": t.passed,
         "fell_back": t.fell_back, "final_text": t.final_text, "provider": t.provider, "created_at": clock.as_utc(t.created_at).isoformat()}
        for t in db.scalars(q)
    ]
    total = int(db.scalar(select(func.count(TranslationCheck.id))) or 0)
    failed_n = int(db.scalar(select(func.count(TranslationCheck.id)).where(TranslationCheck.passed.is_(False))) or 0)
    return {**paginate(items, page, size), "stats": {"total": total, "failed": failed_n}}


@router.post("/preview")
def preview(body: PreviewIn, db: DB, user: Reader) -> dict[str, Any]:
    """Run one template through the full pipeline for a persona (nothing is sent or stored)."""
    t = db.get(ContentTemplate, body.template_id)
    if t is None:
        raise HTTPException(404, "Template not found")
    loop = db.scalar(select(CareLoop).join(Patient, CareLoop.patient_id == Patient.id).where(Patient.persona == body.persona).limit(1))
    if loop is None:
        raise HTTPException(404, "Persona not seeded")
    variables = {**M.loop_vars(db, loop), "slot_time": "Fri 07 Nov, 18:30", "clinic_name": "Mussafah Workers' Health Centre"}
    text_en = safe_format(t.body, variables)
    tr = db.scalar(select(ApprovedTranslation).where(ApprovedTranslation.template_id == t.id, ApprovedTranslation.language == body.language))
    rendered = M.Rendered(key=t.key, template=t, text_en=text_en, fixture_text=safe_format(tr.body, variables) if tr else None)
    fw = M.firewall_for(db, loop)
    provider = FirewalledProvider(get_provider(), fw)
    tasks = Tasks(provider)
    res = M.run_pipeline(tasks, rendered, body.language, body.literacy, loop.demo_fault, variables["value"])
    return {"result": res.as_dict(), "redacted_payloads": provider.sent[-4:], "fallbacks": tasks.fallbacks, "persona": body.persona}
