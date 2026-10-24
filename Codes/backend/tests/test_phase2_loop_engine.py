"""Phase 2: state machine, SLA breaches with the simulated clock, audit hash chain."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app import clock
from app.loop_engine import audit
from app.loop_engine.state_machine import InvalidTransition, can_transition, validate
from app.models import CareLoop, Escalation, LoopEvent


def test_state_machine_rules():
    assert can_transition("RESULT_RECEIVED", "NOTIFIED")
    assert can_transition("ENGAGED", "UNDERSTOOD")
    assert can_transition("UNDERSTOOD", "BOOKED")
    assert not can_transition("RESULT_RECEIVED", "CLOSED")
    assert not can_transition("CLOSED", "NOTIFIED")
    assert can_transition("ESCALATED", "ENGAGED", escalated_from="ENGAGED")
    assert not can_transition("ESCALATED", "NOTIFIED", escalated_from="ENGAGED")
    with pytest.raises(InvalidTransition):
        validate("BOOKED", "RESULT_RECEIVED")


def test_invalid_transition_returns_409(client, tokens, personas):
    sara = personas["sara"]["loop_id"]
    r = client.post(f"/api/loops/{sara}/transition", json={"to_state": "CLOSED", "reason": "skip"}, headers=tokens["coordinator"])
    assert r.status_code == 409


def test_declined_requires_informed_refusal(client, tokens, personas):
    sara = personas["sara"]["loop_id"]
    r = client.post(f"/api/loops/{sara}/transition", json={"to_state": "NOTIFIED", "reason": "called"}, headers=tokens["coordinator"])
    assert r.status_code == 200
    r = client.post(f"/api/loops/{sara}/transition", json={"to_state": "DECLINED", "reason": "said no"}, headers=tokens["coordinator"])
    assert r.status_code == 422


def test_advancing_clock_past_sla_breaches_and_escalates(client, tokens, db):
    loop = db.scalar(select(CareLoop).where(CareLoop.state == "RESULT_RECEIVED", CareLoop.breached.is_(False)).order_by(CareLoop.sla_due_at).limit(1))
    assert loop is not None
    days_needed = (clock.as_utc(loop.sla_due_at) - clock.now(db)).total_seconds() / 86400 + 1
    try:
        r = client.post(f"/api/demo/advance-clock?days={max(days_needed, 0.5):.2f}", headers=tokens["admin"])
        assert r.status_code == 200
        assert r.json()["new_breaches"] >= 1
        db.expire_all()
        loop = db.get(CareLoop, loop.id)
        assert loop.state == "BREACHED" and loop.breached
        esc = db.scalar(select(Escalation).where(Escalation.loop_id == loop.id, Escalation.reason == "sla_breach"))
        assert esc is not None
    finally:
        clock.reset(db)
        db.commit()


def test_audit_chain_valid_then_detects_tampering(client, tokens, db):
    r = client.get("/api/governance/audit/verify", headers=tokens["coordinator"])
    assert r.json()["valid"] is True
    ev = db.scalar(select(LoopEvent).order_by(LoopEvent.seq).offset(25).limit(1))
    original = ev.reason
    ev.reason = original + " (edited)"
    db.commit()
    try:
        res = audit.verify_chain(db)
        assert res["valid"] is False
        assert res["broken_at"] == str(ev.id)
    finally:
        ev.reason = original
        db.commit()
    assert audit.verify_chain(db)["valid"] is True


def test_chain_hash_is_deterministic():
    from datetime import UTC, datetime

    body = {"loop_id": str(uuid.UUID(int=1)), "from_state": None, "to_state": "NOTIFIED", "actor": "system", "reason": "x", "payload": {}}
    t = datetime(2026, 1, 1, tzinfo=UTC)
    assert audit.compute_hash(audit.GENESIS, body, t) == audit.compute_hash(audit.GENESIS, dict(body), t)
    assert audit.compute_hash(audit.GENESIS, body, t) != audit.compute_hash(audit.GENESIS, {**body, "reason": "y"}, t)


def test_tamper_demo_endpoints(client, tokens):
    r = client.post("/api/demo/tamper", headers=tokens["admin"])
    assert r.json()["verify"]["valid"] is False
    r = client.post("/api/demo/untamper", headers=tokens["admin"])
    assert r.json()["verify"]["valid"] is True
