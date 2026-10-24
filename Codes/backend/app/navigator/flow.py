"""Deterministic dialogue flow (spec section 8.4). The LLM is used only to understand
free text and to phrase approved messages; the flow itself is a small state machine.

    start ─(link opened)→ greeting, result, next step, barrier question → barrier
    barrier ─(answer)→ barrier template → teach-back question → teach_back
    teach_back ─pass→ UNDERSTOOD → slots → booking
               ─fail once→ simpler re-explanation → ask again
               ─fail twice→ human follow-up queued → slots → booking   (care is never blocked)
    booking ─(slot tapped)→ BOOKED → confirmation → booked
    any step: red flag → urgent-care message + escalation, AI paused until a human acks
              refusal → risk explained once → confirmed refusal → DECLINED (informed)
              "talk to a human" → hand-off + review item
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.llm.factory import get_provider
from app.llm.pii_firewall import FirewalledProvider
from app.llm.tasks import Tasks
from app.loop_engine import service
from app.models import (
    Appointment,
    CareLoop,
    ClinicSlot,
    Consent,
    Conversation,
    Message,
    ReviewItem,
    TeachBackAttempt,
)
from app.navigator import messaging as M
from app.navigator.content import templates_fixture
from app.scheduling.slots import format_slot, suggest_slots

BARRIER_TEMPLATE = {
    "time": "time_info",
    "cost": "cost_info",
    "transport": "transport_info",
    "fear": "fear_info",
    "language": "language_info",
    "family": "family_info",
    "none": "none_barrier",
}
TOKEN_DAYS = 14


class FlowError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


# --------------------------------------------------------------------- consent

def has_outreach_consent(db: Session, patient_id: uuid.UUID) -> bool:
    c = db.scalar(
        select(Consent)
        .where(Consent.patient_id == patient_id, Consent.scope == "outreach")
        .order_by(Consent.created_at.desc())
        .limit(1)
    )
    return bool(c and c.granted and c.revoked_at is None)


# ---------------------------------------------------------------- magic links

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_outreach(db: Session, loop: CareLoop, actor: str, channel: str | None = None) -> tuple[Conversation, str]:
    if not has_outreach_consent(db, loop.patient_id):
        raise FlowError(409, "No outreach consent on record: outreach blocked")
    if loop.state in {"CLOSED", "DECLINED", "ATTENDED"}:
        raise FlowError(409, f"Loop is {loop.state}; outreach not needed")
    token = secrets.token_urlsafe(24)
    now = clock.now(db)
    conv = Conversation(
        loop_id=loop.id,
        channel=channel or loop.patient.preferred_channel,
        language=loop.patient.preferred_language,
        started_at=now,
        magic_token_hash=hash_token(token),
        expires_at=now + timedelta(days=TOKEN_DAYS),
        step="start",
        context={},
    )
    db.add(conv)
    if loop.state in {"RESULT_RECEIVED", "UNREACHABLE", "BREACHED"}:
        service.transition(db, loop, "NOTIFIED", actor, f"Outreach started via {conv.channel}", {"channel": conv.channel})
    elif loop.state == "NO_SHOW":
        service.transition(db, loop, "ENGAGED", actor, "Re-engagement after no-show")
    db.flush()
    return conv, token


def conversation_for_token(db: Session, token: str) -> tuple[Conversation, CareLoop]:
    conv = db.scalar(select(Conversation).where(Conversation.magic_token_hash == hash_token(token)))
    if conv is None:
        raise FlowError(404, "Unknown link")
    if clock.as_utc(conv.expires_at) < clock.now(db):
        raise FlowError(410, "Link expired")
    loop = db.get(CareLoop, conv.loop_id)
    assert loop is not None
    return conv, loop


def _ctx(conv: Conversation) -> dict[str, Any]:
    return dict(conv.context or {})


def _save_ctx(conv: Conversation, ctx: dict[str, Any]) -> None:
    conv.context = ctx  # reassign so SQLAlchemy sees the JSON change


# ------------------------------------------------------------------- bootstrap

def open_conversation(db: Session, conv: Conversation, loop: CareLoop) -> None:
    """First open of the magic link: explain the result and ask about barriers."""
    if conv.step != "start":
        return
    if not has_outreach_consent(db, loop.patient_id):
        M.system_message(db, conv, "Outreach consent was withdrawn. The navigator will not send messages.", "consent")
        conv.step = "stopped"
        return
    if loop.state == "NOTIFIED":
        service.transition(db, loop, "ENGAGED", "patient", "Patient opened the secure link")
    M.send(db, conv, loop, ["greeting", "result_explain", "next_step", "barrier_q"])
    conv.step = "barrier"


def set_language(db: Session, conv: Conversation, loop: CareLoop, lang: str) -> None:
    conv.language = lang
    db.flush()


# -------------------------------------------------------------------- messages

def handle_message(db: Session, conv: Conversation, loop: CareLoop, text: str) -> list[Message]:
    text = text.strip()[:2000]
    if not text:
        raise FlowError(422, "Empty message")
    if conv.step == "start":
        open_conversation(db, conv, loop)
    tasks = Tasks(FirewalledProvider(get_provider(), M.firewall_for(db, loop)))
    u = tasks.understand(text, conv.language, conv.step, loop.screening.program)
    now = clock.now(db)
    pmsg = Message(
        conversation_id=conv.id, sender="patient", text=text, text_en=u["answer_en"], red_flag=bool(u["red_flag"]),
        kind="text", meta={"intent": u["intent"], "barrier": u["barrier"], "red_flag_source": u.get("red_flag_source", "")},
        created_at=now,
    )
    db.add(pmsg)
    db.flush()
    out: list[Message] = [pmsg]

    if not has_outreach_consent(db, loop.patient_id):
        out.append(M.system_message(db, conv, "Outreach consent was withdrawn. The navigator will not send messages.", "consent"))
        conv.step = "stopped"
        return out

    # 1. Red flags win over everything, every turn.
    if u["red_flag"]:
        out += M.send(db, conv, loop, ["urgent_care"], kind_for={"urgent_care": "emergency"})
        service.escalate(
            db, loop, "red_flag", "system", f"Red flag ({u.get('red_flag_reason')}): {u['answer_en'][:160]}",
            {"message_id": str(pmsg.id), "source": u.get("red_flag_source")}, pause_navigator=True,
        )
        return out
    if loop.navigator_paused:
        out += M.send(db, conv, loop, ["ai_paused"])
        return out
    if conv.step in {"stopped", "declined"}:
        return out

    ctx = _ctx(conv)
    if u["intent"] == "human":
        db.add(ReviewItem(item_type="human_request", loop_id=loop.id, reason="Patient asked to talk to a human"))
        service.record_milestone(db, loop, "human_request", "patient", "Patient asked for a human navigator")
        out += M.send(db, conv, loop, ["human_handoff"])
        return out

    # 2. Refusal: explain the risk once, then respect the decision.
    if u["intent"] == "refusal" or conv.step == "refusal_confirm":
        if conv.step != "refusal_confirm":
            ctx["step_before_refusal"] = conv.step
            conv.step = "refusal_confirm"
            _save_ctx(conv, ctx)
            out += M.send(db, conv, loop, ["refusal_risk"])
            return out
        if u["intent"] == "refusal" or u["answer_en"].strip().lower() in {"yes", "yes.", "i am sure"}:
            out += _record_refusal(db, conv, loop, u["answer_en"])
            return out
        conv.step = ctx.pop("step_before_refusal", "barrier")
        _save_ctx(conv, ctx)

    # 3. Normal flow.
    if conv.step == "barrier":
        barrier = u["barrier"] if u["intent"] in {"barrier", "other", "question", "teach_back"} else "none"
        ctx.setdefault("barriers", []).append(barrier)
        _save_ctx(conv, ctx)
        tpl = BARRIER_TEMPLATE.get(barrier, "none_barrier")
        out += M.send(db, conv, loop, [tpl, "teach_back_q"])
        service.record_milestone(db, loop, "barrier", "patient", f"Barrier identified: {barrier}", {"barrier": barrier})
        conv.step = "teach_back"
        return out

    if conv.step == "teach_back":
        out += _teach_back(db, conv, loop, tasks, text, u["answer_en"])
        return out

    if conv.step == "booking":
        out += _offer_slots(db, conv, loop, intro=True)
        return out

    out += M.send(db, conv, loop, ["human_handoff"])
    return out


def _teach_back(db: Session, conv: Conversation, loop: CareLoop, tasks: Tasks, answer: str, answer_en: str) -> list[Message]:
    program = loop.screening.program
    rubric = templates_fixture()["teach_back_rubric"][program]
    question = M.render(db, loop, "teach_back_q", "en").text_en
    grade = tasks.grade_teach_back(answer_en, program, rubric)
    attempts = int(_ctx(conv).get("teach_back_attempts", 0)) + 1
    ctx = _ctx(conv)
    ctx["teach_back_attempts"] = attempts
    _save_ctx(conv, ctx)
    db.add(
        TeachBackAttempt(
            loop_id=loop.id, question=question, patient_answer=answer, answer_en=answer_en,
            rubric={k: grade.get(k) for k in rubric} | {"method": grade.get("method")}, passed=bool(grade["passed"]),
            feedback=grade.get("feedback", ""), created_at=clock.now(db),
        )
    )
    out: list[Message] = []
    if grade["passed"]:
        if loop.state in {"ENGAGED", "NOTIFIED", "BREACHED"}:
            if loop.state != "ENGAGED":
                service.transition(db, loop, "ENGAGED", "patient", "Patient engaged in chat")
            service.transition(db, loop, "UNDERSTOOD", "patient", "Teach-back passed", {"rubric": {k: grade.get(k) for k in rubric}})
        out += M.send(db, conv, loop, ["teach_back_pass"], meta_for={"teach_back_pass": {"teach_back": "passed"}})
        conv.step = "booking"
        out += _offer_slots(db, conv, loop, intro=True)
        return out
    if attempts < 2:
        out += M.send(db, conv, loop, ["teach_back_retry", "result_simple", "teach_back_q"],
                      meta_for={"teach_back_retry": {"teach_back": "retry"}})
        return out
    db.add(ReviewItem(item_type="teach_back", loop_id=loop.id, reason=f"Teach-back failed twice: {grade.get('feedback', '')}"))
    service.record_milestone(db, loop, "teach_back", "system", "Teach-back failed twice; human follow-up queued")
    out += M.send(db, conv, loop, ["teach_back_handoff"], meta_for={"teach_back_handoff": {"teach_back": "failed"}})
    conv.step = "booking"
    out += _offer_slots(db, conv, loop, intro=True)
    return out


def _offer_slots(db: Session, conv: Conversation, loop: CareLoop, intro: bool) -> list[Message]:
    slots = [s.as_dict() for s in suggest_slots(db, loop, k=3)]
    return M.send(db, conv, loop, ["slots_intro"], kind_for={"slots_intro": "slots"}, meta_for={"slots_intro": {"slots": slots}})


def _record_refusal(db: Session, conv: Conversation, loop: CareLoop, answer_en: str) -> list[Message]:
    payload = {"informed_refusal": True, "risk_explained_in": conv.language, "patient_statement_en": answer_en[:300]}
    service.transition(db, loop, "DECLINED", "patient", "Informed refusal recorded after risk explanation", payload)
    db.add(ReviewItem(item_type="refusal", loop_id=loop.id, reason="Informed refusal recorded — clinician review"))
    conv.step = "declined"
    return M.send(db, conv, loop, ["refusal_recorded"])


# --------------------------------------------------------------------- booking

def book(db: Session, conv: Conversation, loop: CareLoop, slot_id: uuid.UUID, actor: str = "patient") -> list[Message]:
    slot = db.get(ClinicSlot, slot_id)
    if slot is None or slot.program != loop.screening.program:
        raise FlowError(404, "Slot not found")
    if slot.is_booked:
        raise FlowError(409, "That time was just taken — please pick another")
    if loop.state not in {"ENGAGED", "UNDERSTOOD", "NOTIFIED", "NO_SHOW", "BREACHED", "RESULT_RECEIVED"}:
        raise FlowError(409, f"Cannot book while loop is {loop.state}")
    reasons: list[str] = []
    for s in suggest_slots(db, loop, k=20):
        if s.slot.id == slot.id:
            reasons = s.reasons
    slot.is_booked = True
    db.add(Appointment(loop_id=loop.id, slot_id=slot.id, status="booked", match_reasons=reasons))
    if loop.state in {"NOTIFIED", "RESULT_RECEIVED", "BREACHED"}:
        if loop.state == "RESULT_RECEIVED":
            service.transition(db, loop, "NOTIFIED", actor, "Contacted for booking")
        service.transition(db, loop, "ENGAGED", actor, "Engaged for booking")
    service.transition(
        db, loop, "BOOKED", actor, f"Booked {format_slot(slot.start_at)} at {slot.clinic.name}",
        {"slot_id": str(slot.id), "match_reasons": reasons, "teach_back_passed": loop.understood_at is not None},
    )
    conv.step = "booked"
    extra = {"slot_time": format_slot(slot.start_at), "clinic_name": slot.clinic.name}
    return M.send(db, conv, loop, [("booked_confirm", extra)], meta_for={"booked_confirm": {"booked_slot": str(slot.id)}})


def send_due_reminders(db: Session) -> int:
    """Simulated 48 h / 2 h reminders (driven by the simulated clock)."""
    now = clock.now(db)
    sent = 0
    appts = db.scalars(select(Appointment).where(Appointment.status == "booked")).all()
    for ap in appts:
        start = clock.as_utc(ap.slot.start_at)
        conv = db.scalar(select(Conversation).where(Conversation.loop_id == ap.loop_id).order_by(Conversation.started_at.desc()).limit(1))
        if conv is None or start < now - timedelta(hours=1):
            continue
        loop = db.get(CareLoop, ap.loop_id)
        if loop is None or not has_outreach_consent(db, loop.patient_id):
            continue
        ctx = _ctx(conv)
        extra = {"slot_time": format_slot(ap.slot.start_at), "clinic_name": ap.slot.clinic.name}
        for key, delta in (("reminder_48h", timedelta(hours=48)), ("reminder_2h", timedelta(hours=2))):
            flag = f"{key}:{ap.id}"
            if now >= start - delta and not ctx.get(flag):
                M.send(db, conv, loop, [(key, extra)])
                ctx[flag] = True
                sent += 1
        _save_ctx(conv, ctx)
    return sent
