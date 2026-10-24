"""Phase 4: navigator, LLM layer, PII firewall, translation QA, red flags, consent."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.llm.mock import MockProvider
from app.llm.pii_firewall import FirewalledProvider, PIIFirewall
from app.llm.tasks import Tasks, keyword_grade, mock_understand
from app.llm.translation_qa import apply_demo_fault, entity_check, extract_numbers, normalise_digits
from app.models import CareLoop, Escalation, PatientIdentity, TranslationCheck


def _start(client, tokens, loop_id):
    r = client.post(f"/api/loops/{loop_id}/outreach", json={}, headers=tokens["coordinator"])
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_ramesh_end_to_end_malayalam(client, tokens, personas, db):
    loop_id = personas["ramesh"]["loop_id"]
    tok = _start(client, tokens, loop_id)
    s = client.get(f"/api/c/{tok}").json()
    assert s["language"] == "ml" and s["step"] == "barrier"
    assert len(s["messages"]) == 4
    assert all(m["meta"]["qa"]["passed"] for m in s["messages"])
    q = s["phrases"]["quick"]
    s = client.post(f"/api/c/{tok}/message", json={"text": q["qr_night"]}).json()
    assert s["step"] == "teach_back"
    s = client.post(f"/api/c/{tok}/message", json={"text": q["qr_tb_diabetes"]}).json()
    assert s["understood"] is True and s["step"] == "booking"
    slots = s["messages"][-1]["meta"]["slots"]
    assert slots and any("night shift" in r for r in slots[0]["match_reasons"])
    s = client.post(f"/api/c/{tok}/book", json={"slot_id": slots[0]["slot_id"]}).json()
    assert s["booked"] is not None
    d = client.get(f"/api/loops/{loop_id}", headers=tokens["coordinator"]).json()
    assert d["loop"]["state"] == "BOOKED"
    assert d["loop"]["understood"] is True
    states = [e["to_state"] for e in d["timeline"]]
    assert states.index("UNDERSTOOD") < states.index("BOOKED")
    assert d["chain"]["valid"]


def test_fatima_red_flag_escalates_in_one_request(client, tokens, personas, db):
    loop_id = personas["fatima"]["loop_id"]
    tok = _start(client, tokens, loop_id)
    s = client.get(f"/api/c/{tok}").json()
    s = client.post(f"/api/c/{tok}/message", json={"text": "I found a lump that is bleeding"}).json()
    assert s["emergency"] is True and s["paused"] is True
    esc = db.scalar(select(Escalation).where(Escalation.reason == "red_flag", Escalation.loop_id == uuid.UUID(loop_id)))
    assert esc is not None
    # AI stays paused until a human acknowledges
    s = client.post(f"/api/c/{tok}/message", json={"text": "hello?"}).json()
    assert s["messages"][-1]["meta"]["template_key"] == "ai_paused"
    r = client.post(f"/api/escalations/{esc.id}/ack", json={"notes": "nurse called"}, headers=tokens["clinician"])
    assert r.status_code == 200
    db.expire_all()
    assert db.get(CareLoop, esc.loop_id).navigator_paused is False


def test_red_flag_in_arabic_lexicon(client, tokens, personas):
    from app.llm.tasks import red_flag_lexicon_match

    assert red_flag_lexicon_match("أشعر بألم في صدري") or red_flag_lexicon_match("ألم في صدري")


def test_imran_translation_check_fails_and_falls_back(client, tokens, personas, db):
    loop_id = personas["imran"]["loop_id"]
    tok = _start(client, tokens, loop_id)
    s = client.get(f"/api/c/{tok}").json()
    explain = next(m for m in s["messages"] if m["meta"]["template_key"] == "result_explain")
    assert explain["meta"]["qa"]["passed"] is False
    assert explain["meta"]["qa"]["source"] == "approved_translation"
    assert "7.4" in explain["text"]  # the patient receives the correct number
    chk = db.get(TranslationCheck, uuid.UUID(explain["translation_check_id"]))
    assert chk.fell_back and not chk.entity_match
    q = client.get("/api/review-queue", headers=tokens["clinician"]).json()
    assert any(i["item_type"] == "translation_check" for i in q["items"])


def test_pii_firewall_never_leaks_identity(db, personas):
    loop = db.get(CareLoop, uuid.UUID(personas["ramesh"]["loop_id"]))
    ident = db.scalar(select(PatientIdentity).where(PatientIdentity.patient_id == loop.patient_id))
    from app.navigator.messaging import firewall_for

    fw = firewall_for(db, loop)
    spy = MockProvider()
    prov = FirewalledProvider(spy, fw)
    text = f"Hello {ident.full_name}, phone {ident.phone}, id {ident.emirates_id_masked}, code {loop.patient.code}, email a.b@x.com, dob 03/04/1985."
    out = prov.complete_text("system for " + ident.full_name.split()[0], text)
    payload = " ".join(c["system"] + " " + c["user"] for c in spy.calls)
    for secret in (ident.full_name, ident.full_name.split()[0], ident.phone, ident.emirates_id_masked, loop.patient.code, "a.b@x.com", "03/04/1985"):
        assert secret not in payload
    assert "⟦NAME_1⟧" in payload
    assert ident.full_name in out  # restored afterwards


def test_revoked_consent_blocks_outreach(client, tokens, personas):
    joy = personas["joy"]
    r = client.post(f"/api/consents/{joy['patient_id']}", json={"scope": "outreach", "granted": False}, headers=tokens["coordinator"])
    assert r.json()["current"]["outreach"]["granted"] is False
    r = client.post(f"/api/loops/{joy['loop_id']}/outreach", json={}, headers=tokens["coordinator"])
    assert r.status_code == 409
    client.post(f"/api/consents/{joy['patient_id']}", json={"scope": "outreach", "granted": True}, headers=tokens["coordinator"])


def test_revoking_consent_mid_conversation_stops_messages(client, tokens, personas):
    joy = personas["joy"]
    tok = _start(client, tokens, joy["loop_id"])
    client.get(f"/api/c/{tok}")
    client.post(f"/api/consents/{joy['patient_id']}", json={"scope": "outreach", "granted": False}, headers=tokens["coordinator"])
    s = client.post(f"/api/c/{tok}/message", json={"text": "I am worried about the cost"}).json()
    assert s["messages"][-1]["kind"] == "consent"
    assert s["messages"][-1]["sender"] == "system"
    client.post(f"/api/consents/{joy['patient_id']}", json={"scope": "outreach", "granted": True}, headers=tokens["coordinator"])


def test_entity_check_and_digits():
    assert normalise_digits("٧٫٤") == "7.4"
    assert extract_numbers("HbA1c ۷.۴% and 6,5") == ["6.5", "7.4"]
    ok, issues = entity_check("HbA1c is 7.4%", "HbA1c ہے 4.7%", "HbA1c is 4.7%")
    assert not ok and issues
    assert entity_check("Times that fit you best", "...", "Times that fit you best")[0]
    assert not entity_check("Your FIT result is positive", "نتيجة الفحص إيجابية", "Your test is positive")[0]
    assert apply_demo_fault("نتیجہ 7.4% ہے", "mt_number_swap", "7.4") == "نتیجہ 4.7% ہے"


def test_mock_tasks():
    assert mock_understand("I work night shifts")["barrier"] == "time"
    assert mock_understand("I am worried about the cost")["barrier"] == "cost"
    assert mock_understand("I don't want the follow-up")["intent"] == "refusal"
    rubric = {"understands_result": ["sugar"], "knows_next_step": ["doctor"], "knows_when": ["weeks"]}
    assert keyword_grade("My sugar is high, I will see the doctor in two weeks", rubric)["passed"]
    assert not keyword_grade("I don't know", rubric)["passed"]
    t = Tasks(MockProvider())
    assert t.translate("x", "en", None) == "x"
    assert t.judge("value 7.4", "value 4.7", "value 4.7", "ur")["score"] < 0.85


def test_refusal_needs_risk_explanation_first(client, tokens, db):
    loop = db.scalar(select(CareLoop).where(CareLoop.state == "RESULT_RECEIVED", CareLoop.patient.has(persona=None)).limit(1))
    tok = _start(client, tokens, str(loop.id))
    s = client.get(f"/api/c/{tok}").json()
    s = client.post(f"/api/c/{tok}/message", json={"text": "I don't want the follow-up"}).json()
    assert s["step"] == "refusal_confirm"
    s = client.post(f"/api/c/{tok}/message", json={"text": "I don't want the follow-up"}).json()
    assert s["step"] == "declined"
    db.expire_all()
    assert db.get(CareLoop, loop.id).state == "DECLINED"


def test_firewall_regexes():
    fw = PIIFirewall({})
    red, r = fw.redact("call +971 50 123 4567 or 784-1985-4417820-3")
    assert "+971" not in red and "784-1985" not in red
    assert PIIFirewall.restore(red, r) == "call +971 50 123 4567 or 784-1985-4417820-3"
