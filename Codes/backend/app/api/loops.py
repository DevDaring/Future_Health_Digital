"""Loop detail, transitions, assignment, outreach (magic link), staff booking and the
clinician-only patient twin."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import NEXT_ACTION, ensure_loop_access, identity_view, loop_row
from app.config import get_settings
from app.db import get_db
from app.loop_engine import audit, closure, service
from app.loop_engine.state_machine import InvalidTransition, can_transition
from app.ml.score import score_open_loops
from app.models import (
    Appointment,
    CareLoop,
    Consent,
    Conversation,
    Escalation,
    LoopClosure,
    LoopEvent,
    Message,
    RiskScore,
    TeachBackAttempt,
    TranslationCheck,
    User,
)
from app.navigator import flow
from app.navigator.content import LANG_NAMES, RTL
from app.scheduling.slots import format_slot, suggest_slots
from app.schemas import AssignIn, BookIn, CloseIn, OutreachIn, OutreachOut, TransitionIn
from app.security import CurrentUser, can, require
from app.twin.patient_twin import patient_twin

router = APIRouter(prefix="/loops", tags=["loops"])
DB = Annotated[Session, Depends(get_db)]


def _actor(user: User) -> str:
    return f"user:{user.email}"


def message_view(m: Message) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "sender": m.sender,
        "text": m.text,
        "text_en": m.text_en,
        "kind": m.kind,
        "red_flag": m.red_flag,
        "meta": m.meta or {},
        "translation_check_id": str(m.translation_check_id) if m.translation_check_id else None,
        "created_at": clock.as_utc(m.created_at).isoformat(),
    }


BARRIER_LABEL = {
    "time": "work hours / time off", "cost": "cost worry", "transport": "travel distance", "fear": "fear or worry",
    "language": "language", "family": "family duties", "none": "no barrier named",
}


def _source(actor: str) -> str:
    if actor == "patient":
        return "patient_chat"
    if actor.startswith("user:"):
        return "staff"
    return "system"


def case_record(events: list[LoopEvent]) -> list[dict[str, Any]]:
    """What the case record says happened, in order. Outcomes captured in the patient chat
    (barrier, teach-back, booking, red flag, refusal, request for a human) are written back
    here automatically, each linked to its hash-chained audit event."""
    out: list[dict[str, Any]] = []

    def add(kind: str, label: str, detail: str, ev: LoopEvent, source: str) -> None:
        out.append({"kind": kind, "label": label, "detail": detail, "source": source, "seq": ev.seq, "hash": ev.hash[:12],
                    "at": clock.as_utc(ev.created_at).isoformat()})

    for ev in events:
        r = ev.reason or ""
        if ev.from_state is None:
            add("result", "Result received", r.replace("HBA1C ", "HbA1c ").replace("BIRADS ", "Mammogram BI-RADS "), ev, _source(ev.actor))
        elif r.startswith("barrier:"):
            b = str((ev.payload or {}).get("barrier", ""))
            add("barrier", "Barrier recorded", BARRIER_LABEL.get(b, r.split(":", 1)[1].strip()), ev, "patient_chat")
        elif ev.to_state == "UNDERSTOOD" and ev.from_state != "UNDERSTOOD":
            add("teach_back", "Understood the result (teach-back passed)", "Patient explained the result back in their own words", ev, _source(ev.actor))
        elif r.startswith("teach_back:"):
            add("teach_back", "Teach-back not passed twice", "Human follow-up queued", ev, "patient_chat")
        elif ev.to_state == "BOOKED" and ev.from_state != "BOOKED":
            add("booked", "Visit booked", r.removeprefix("Booked ").strip(), ev, _source(ev.actor))
        elif ev.to_state == "ESCALATED" and ev.from_state != "ESCALATED":
            is_red = "red_flag" in r
            add("red_flag" if is_red else "escalation", "Red flag raised in chat" if is_red else "Escalated", r.split(":", 1)[-1].strip(), ev,
                "patient_chat" if is_red else _source(ev.actor))
        elif r.startswith("escalation:") and "urgent_result" in r:
            add("urgent", "Urgent result flagged", r.split("urgent_result", 1)[-1].strip(), ev, "system")
        elif r.startswith("human_request:"):
            add("human", "Patient asked for a human", r.split(":", 1)[1].strip(), ev, "patient_chat")
        elif ev.to_state == "DECLINED" and ev.from_state != "DECLINED":
            add("declined", "Informed refusal recorded", r, ev, _source(ev.actor))
        elif r.startswith("assign:"):
            add("owner", "Owner set", r.split(":", 1)[1].strip(), ev, _source(ev.actor))
        elif ev.to_state == "ATTENDED" and ev.from_state != "ATTENDED":
            add("attended", "Visit attended", r, ev, _source(ev.actor))
        elif ev.to_state == "NO_SHOW" and ev.from_state != "NO_SHOW":
            add("no_show", "Missed the visit", r, ev, _source(ev.actor))
        elif ev.to_state == "CLOSED" and ev.from_state != "CLOSED":
            add("closed", "Loop closed with documented outcome", r.removeprefix("Closed: "), ev, "staff")
        elif ev.to_state == "BREACHED" and ev.from_state != "BREACHED":
            add("breach", "SLA breached", r, ev, "system")
        elif ev.from_state == "ESCALATED" and ev.to_state != "ESCALATED":
            add("ack", "Escalation handled by a human", r, ev, _source(ev.actor))
    return out


@router.get("/{loop_id}")
def loop_detail(loop_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require("worklist"))]) -> dict[str, Any]:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    now = clock.now(db)
    score = db.scalar(select(RiskScore).where(RiskScore.loop_id == loop.id).order_by(RiskScore.scored_at.desc()).limit(1))
    ident = identity_view(db, loop.patient_id, user)
    events = db.scalars(select(LoopEvent).where(LoopEvent.loop_id == loop.id).order_by(LoopEvent.seq)).all()
    chain = audit.verify_chain(db, loop.id)
    convs = db.scalars(select(Conversation).where(Conversation.loop_id == loop.id).order_by(Conversation.started_at)).all()
    messages = []
    for c in convs:
        messages += [message_view(m) for m in db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created_at, Message.id))]
    checks = db.scalars(select(TranslationCheck).where(TranslationCheck.loop_id == loop.id).order_by(TranslationCheck.created_at)).all()
    tbs = db.scalars(select(TeachBackAttempt).where(TeachBackAttempt.loop_id == loop.id).order_by(TeachBackAttempt.created_at)).all()
    appts = db.scalars(select(Appointment).where(Appointment.loop_id == loop.id)).all()
    escs = db.scalars(select(Escalation).where(Escalation.loop_id == loop.id).order_by(Escalation.created_at.desc())).all()
    consents = db.scalars(select(Consent).where(Consent.patient_id == loop.patient_id).order_by(Consent.created_at)).all()
    latest_consent: dict[str, dict[str, Any]] = {}
    for c in consents:
        latest_consent[c.scope] = {"granted": c.granted and c.revoked_at is None, "at": clock.as_utc(c.revoked_at or c.granted_at or c.created_at).isoformat()}
    rec = db.scalar(select(LoopClosure).where(LoopClosure.loop_id == loop.id))
    p = loop.patient
    slots = [s.as_dict() for s in suggest_slots(db, loop, k=3)] if loop.state not in {"CLOSED", "DECLINED", "ATTENDED", "BOOKED"} else []
    return {
        "loop": loop_row(loop, ident["display_name"], now, score),
        "identity": ident,
        "patient": {
            "code": p.code, "age": p.age, "sex": p.sex, "nationality_group": p.nationality_group,
            "language": p.preferred_language, "language_name": LANG_NAMES.get(p.preferred_language), "rtl": p.preferred_language in RTL,
            "literacy_level": p.literacy_level, "occupation_type": p.occupation_type, "shift_pattern": p.shift_pattern,
            "preferred_days": p.preferred_days, "home_area": p.home_area, "distance_km": p.distance_km,
            "insurance_tier": p.insurance_tier, "prior_no_shows": p.prior_no_shows, "has_smartphone": p.has_smartphone,
            "preferred_channel": p.preferred_channel, "no_free_weekdays": p.no_free_weekdays, "persona": p.persona,
        },
        "score": None if score is None else {
            "model_version": score.model_version, "p_dropoff": score.p_dropoff, "p_return_if_not": score.p_return_if_not,
            "p_return_if_contacted": score.p_return_if_contacted, "uplift": score.uplift, "shap_top": score.shap_top,
            "counterfactuals": score.counterfactuals, "scored_at": clock.as_utc(score.scored_at).isoformat(),
        },
        "timeline": [
            {"id": str(e.id), "seq": e.seq, "from_state": e.from_state, "to_state": e.to_state, "actor": e.actor, "reason": e.reason,
             "payload": e.payload, "created_at": clock.as_utc(e.created_at).isoformat(), "hash": e.hash, "prev_hash": e.prev_hash}
            for e in events
        ],
        "chain": chain,
        "conversations": [
            {"id": str(c.id), "language": c.language, "channel": c.channel, "step": c.step,
             "started_at": clock.as_utc(c.started_at).isoformat(), "expires_at": clock.as_utc(c.expires_at).isoformat()}
            for c in convs
        ],
        "messages": messages,
        "translation_checks": [
            {"id": str(t.id), "template_key": t.template_key, "language": t.language, "source_en": t.source_en, "simplified_en": t.simplified_en,
             "translated": t.translated, "back_translated": t.back_translated, "judge_score": t.judge_score, "entity_match": t.entity_match,
             "discrepancies": t.discrepancies, "passed": t.passed, "fell_back": t.fell_back, "final_text": t.final_text, "provider": t.provider,
             "created_at": clock.as_utc(t.created_at).isoformat()}
            for t in checks
        ],
        "teach_back": [
            {"id": str(t.id), "question": t.question, "patient_answer": t.patient_answer, "answer_en": t.answer_en, "rubric": t.rubric,
             "passed": t.passed, "feedback": t.feedback, "created_at": clock.as_utc(t.created_at).isoformat()}
            for t in tbs
        ],
        "appointments": [
            {"id": str(a.id), "status": a.status, "slot_label": format_slot(a.slot.start_at), "clinic_name": a.slot.clinic.name,
             "match_reasons": a.match_reasons, "start_at": clock.as_utc(a.slot.start_at).isoformat()}
            for a in appts
        ],
        "escalations": [
            {"id": str(e.id), "reason": e.reason, "status": e.status, "notes": e.notes, "created_at": clock.as_utc(e.created_at).isoformat()}
            for e in escs
        ],
        "consents": latest_consent,
        "case_record": case_record(list(events)),
        "closure": closure.closure_view(rec),
        "closure_outcomes": closure.OUTCOMES,
        "next_action": NEXT_ACTION.get(loop.state, ""),
        "can_close": loop.state in closure.CLOSABLE_AFTER_VISIT | closure.VISIT_FROM,
        "screening_facility": loop.screening.facility,
        "slots": slots,
        "allowed_transitions": [s for s in ("NOTIFIED", "ENGAGED", "UNDERSTOOD", "BOOKED", "ATTENDED", "NO_SHOW", "UNREACHABLE", "DECLINED", "ESCALATED")
                                if can_transition(loop.state, s, loop.escalated_from)],
        "can_view_twin": can(user, "patient_twin"),
    }


@router.post("/{loop_id}/transition")
def transition(loop_id: uuid.UUID, body: TransitionIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    if body.to_state == "CLOSED":
        raise HTTPException(409, "Closing a loop needs a documented outcome: use the closure form (POST /loops/{id}/close)")
    if body.to_state == "DECLINED" and "informed" not in body.reason.lower():
        raise HTTPException(422, "DECLINED requires a recorded informed refusal (reason must state the risk was explained)")
    try:
        service.transition(db, loop, body.to_state, _actor(user), body.reason or f"Set to {body.to_state}",
                           {"informed_refusal": True} if body.to_state == "DECLINED" else None)
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc
    if body.to_state == "ATTENDED":
        for ap in db.scalars(select(Appointment).where(Appointment.loop_id == loop.id, Appointment.status == "booked")):
            ap.status = "attended"
    if body.to_state == "NO_SHOW":
        for ap in db.scalars(select(Appointment).where(Appointment.loop_id == loop.id, Appointment.status == "booked")):
            ap.status = "no_show"
    db.commit()
    return {"id": str(loop.id), "state": loop.state}


@router.post("/{loop_id}/assign")
def assign(loop_id: uuid.UUID, body: AssignIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    target = body.user_id or user.id
    if db.get(User, target) is None:
        raise HTTPException(404, "User not found")
    if user.role == "navigator" and target != user.id:
        raise HTTPException(403, "Navigators can only take ownership themselves")
    new_owner = db.get(User, target)
    if new_owner is None or new_owner.role not in {"admin", "coordinator", "clinician", "navigator"}:
        raise HTTPException(404, "User not found")
    prev = loop.owner.display_name if loop.owner else "nobody"
    loop.assigned_to = target
    note = f" — {body.note.strip()}" if body.note.strip() else ""
    service.record_milestone(db, loop, "assign", _actor(user), f"Owner changed from {prev} to {new_owner.display_name} ({new_owner.role}){note}")
    db.commit()
    return {"id": str(loop.id), "assigned_to": str(target), "owner": new_owner.display_name}


@router.post("/{loop_id}/close")
def close(loop_id: uuid.UUID, body: CloseIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    """Close the loop with a documented outcome (the only way to reach CLOSED)."""
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    try:
        rec = closure.close_loop(db, loop, user, outcome=body.outcome, seen_by=body.seen_by, visit_date=body.visit_date,
                                 summary=body.summary, next_step=body.next_step, patient_informed=body.patient_informed,
                                 report_shared_with=body.report_shared_with)
    except closure.ClosureError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    db.commit()
    return {"id": str(loop.id), "state": loop.state, "closure": closure.closure_view(rec)}


@router.post("/{loop_id}/outreach", response_model=OutreachOut)
def outreach(loop_id: uuid.UUID, body: OutreachIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> OutreachOut:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    try:
        conv, token = flow.start_outreach(db, loop, _actor(user), body.channel)
    except flow.FlowError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    db.commit()
    link = f"{get_settings().public_url.rstrip('/')}/c/{token}"
    return OutreachOut(conversation_id=str(conv.id), token=token, link=link, language=conv.language, state=loop.state)


@router.post("/outreach/bulk")
def bulk_outreach(loop_ids: list[uuid.UUID], db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    started, skipped = [], []
    for lid in loop_ids[:200]:
        loop = db.get(CareLoop, lid)
        if loop is None or (user.role == "navigator" and loop.assigned_to != user.id):
            skipped.append({"id": str(lid), "reason": "not found / not assigned"})
            continue
        try:
            flow.start_outreach(db, loop, _actor(user))
            started.append(str(lid))
        except flow.FlowError as exc:
            skipped.append({"id": str(lid), "reason": exc.detail})
    db.commit()
    return {"started": started, "skipped": skipped}


@router.post("/{loop_id}/book")
def staff_book(loop_id: uuid.UUID, body: BookIn, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    conv = db.scalar(select(Conversation).where(Conversation.loop_id == loop.id).order_by(Conversation.started_at.desc()).limit(1))
    if conv is None:
        conv, _ = flow.start_outreach(db, loop, _actor(user), "call")
    try:
        flow.book(db, conv, loop, body.slot_id, actor=_actor(user))
    except flow.FlowError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    db.commit()
    return {"id": str(loop.id), "state": loop.state}


@router.post("/{loop_id}/rescore")
def rescore(loop_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require("loop_write"))]) -> dict[str, Any]:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    n = score_open_loops(db, loop_ids=[loop.id])
    db.commit()
    return {"scored": n}


@router.get("/{loop_id}/patient-twin")
def loop_patient_twin(loop_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require("patient_twin"))]) -> dict[str, Any]:
    loop = db.get(CareLoop, loop_id)
    if loop is None:
        raise HTTPException(404, "Loop not found")
    return patient_twin(loop.screening.program, loop.screening.category)


@router.get("/{loop_id}/slots")
def loop_slots(loop_id: uuid.UUID, db: DB, user: CurrentUser) -> dict[str, Any]:
    loop = ensure_loop_access(db.get(CareLoop, loop_id), user)
    return {"slots": [s.as_dict() for s in suggest_slots(db, loop, k=5)]}
