"""Patient chat through a magic link (`/c/{token}`): no login, token hashed in the DB,
expires after 14 days, scoped to one loop. Never exposes staff-only data (no risk
scores, no patient twin)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.api.loops import message_view
from app.db import get_db
from app.loop_engine import service
from app.models import Appointment, Message, ReviewItem
from app.navigator import flow
from app.navigator.content import LANG_NAMES, LANGS, RTL, phrases
from app.scheduling.slots import format_slot, suggest_slots
from app.schemas import BookIn, LanguageIn, MessageIn

router = APIRouter(prefix="/c", tags=["patient chat"])
DB = Annotated[Session, Depends(get_db)]


def _load(db: Session, token: str) -> tuple[Any, Any]:
    try:
        return flow.conversation_for_token(db, token)
    except flow.FlowError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


def _state(db: Session, conv: Any, loop: Any) -> dict[str, Any]:
    msgs = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at, Message.id)).all()
    appt = db.scalar(select(Appointment).where(Appointment.loop_id == loop.id, Appointment.status == "booked").limit(1))
    se = loop.screening
    program = se.program.lower()
    return {
        "language": conv.language,
        "language_name": LANG_NAMES.get(conv.language),
        "rtl": conv.language in RTL,
        "languages": [{"code": c, "name": LANG_NAMES[c], "rtl": c in RTL} for c in LANGS],
        "step": conv.step,
        "paused": loop.navigator_paused,
        "emergency": any(m.kind == "emergency" for m in msgs),
        "booked": None if appt is None else {"label": format_slot(appt.slot.start_at), "clinic": appt.slot.clinic.name},
        "understood": loop.understood_at is not None,
        "program": se.program,
        "phrases": phrases(conv.language),
        "quick_replies": _quick(conv.step, program),
        "messages": [message_view(m) for m in msgs],
        "expires_at": clock.as_utc(conv.expires_at).isoformat(),
    }


def _quick(step: str, program: str) -> list[str]:
    if step == "barrier":
        return ["qr_night", "qr_cost", "qr_time_off", "qr_far", "qr_scared", "qr_none", "qr_refuse"]
    if step in ("teach_back",):
        return [f"qr_tb_{program}", "qr_unsure"]
    if step == "refusal_confirm":
        return ["qr_refuse", "qr_none"]
    return []


@router.get("/{token}")
def bootstrap(token: str, db: DB) -> dict[str, Any]:
    conv, loop = _load(db, token)
    if conv.step == "start":
        flow.open_conversation(db, conv, loop)
        db.commit()
    return _state(db, conv, loop)


@router.post("/{token}/message")
def message(token: str, body: MessageIn, db: DB) -> dict[str, Any]:
    conv, loop = _load(db, token)
    try:
        flow.handle_message(db, conv, loop, body.text)
    except flow.FlowError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    db.commit()
    return _state(db, conv, loop)


@router.post("/{token}/language")
def language(token: str, body: LanguageIn, db: DB) -> dict[str, Any]:
    conv, loop = _load(db, token)
    flow.set_language(db, conv, loop, body.language)
    db.commit()
    return _state(db, conv, loop)


@router.get("/{token}/slots")
def slots(token: str, db: DB) -> dict[str, Any]:
    conv, loop = _load(db, token)
    return {"slots": [s.as_dict() for s in suggest_slots(db, loop, k=3)]}


@router.post("/{token}/book")
def book(token: str, body: BookIn, db: DB) -> dict[str, Any]:
    conv, loop = _load(db, token)
    try:
        flow.book(db, conv, loop, body.slot_id)
    except flow.FlowError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    db.commit()
    return _state(db, conv, loop)


@router.post("/{token}/human")
def human(token: str, db: DB) -> dict[str, Any]:
    conv, loop = _load(db, token)
    db.add(ReviewItem(item_type="human_request", loop_id=loop.id, reason="Patient tapped 'Talk to a human'"))
    service.record_milestone(db, loop, "human_request", "patient", "Patient tapped 'Talk to a human'")
    from app.navigator import messaging as M

    M.send(db, conv, loop, ["human_handoff"])
    db.commit()
    return _state(db, conv, loop)
