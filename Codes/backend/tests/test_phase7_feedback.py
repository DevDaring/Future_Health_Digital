"""Phase 7 (review feedback): reviewer-added results, case ownership, chat outcomes written
to the case record, and documented closure as the only way to close a loop."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app import clock
from app.models import CareLoop, Escalation, LoopClosure


def _add(client, tokens, **kw):  # noqa: ANN001, ANN003
    row = {"name": "Test Patient", "language": "ml", "sex": "M", "age": 50, "test": "HbA1c", "value": "7.4", "facility": "Test Van"} | kw
    r = client.post("/api/intake/results", json={"results": [row]}, headers=tokens["jury"])
    assert r.status_code == 200, r.text
    return r.json()["results"][0]


def test_every_loop_has_an_owner_and_every_closed_loop_a_documented_outcome(client, tokens):
    k = client.get("/api/dashboard/kpis", headers=tokens["coordinator"]).json()
    assert k["unowned_open_loops"] == 0
    assert k["closed_loops"] > 0 and k["closed_documented"] == k["closed_loops"]


def test_manual_result_opens_owned_scored_loop_and_moves_the_added_funnel(client, tokens, db):
    before = client.get("/api/dashboard/funnel?scope=added", headers=tokens["coordinator"]).json()["total"]
    res = _add(client, tokens, name="Anil Menon")
    assert res["status"] == "loop_created" and res["severity"] == "high" and res["owner"] == "Priya Nair"  # speaks Malayalam
    loop = db.get(CareLoop, __import__("uuid").UUID(res["loop_id"]))
    assert loop.uplift is not None and loop.screening.source == "manual" and loop.screening.facility == "Test Van"
    after = client.get("/api/dashboard/funnel?scope=added", headers=tokens["coordinator"]).json()
    assert after["total"] == before + 1 and after["scope"] == "added"
    recent = client.get("/api/intake/recent", headers=tokens["coordinator"]).json()["items"]
    assert recent[0]["id"] == res["loop_id"] and recent[0]["owner"]["name"] == "Priya Nair"


def test_normal_result_does_not_open_a_loop(client, tokens):
    assert _add(client, tokens, value="5.2")["status"] == "normal"


def test_urgent_result_raises_flag_for_clinician(client, tokens, db):
    res = _add(client, tokens, value="11.2", language="ar")
    assert "urgent_result" in res["flags"] and res["owner"] == "Dr. Layla Haddad"
    esc = db.scalar(select(Escalation).where(Escalation.loop_id == __import__("uuid").UUID(res["loop_id"])))
    assert esc.reason == "urgent_result" and esc.status == "open" and esc.assigned_to is not None
    k = client.get("/api/dashboard/kpis?scope=added", headers=tokens["coordinator"]).json()
    assert k["open_urgent_results"] >= 1


def test_csv_upload_mixed_rows_and_overdue_result_flags_breach(client, tokens, db):
    old = (clock.now(db) - timedelta(days=30)).date().isoformat()
    csv = ("name,language,sex,age,test,value,result_date,facility\n"
           "A One,en,F,50,FIT,positive,,Clinic A\n"
           f"B Two,en,M,60,HbA1c,7.0,{old},Clinic B\n"
           "C Three,hi,F,40,Mammogram,BI-RADS 1,,Clinic C\n"
           "D Four,xx,F,40,HbA1c,abc,,Clinic D\n")
    r = client.post("/api/intake/csv", json={"csv": csv}, headers=tokens["coordinator"]).json()
    assert r["summary"] == {"loop_created": 2, "normal": 1, "error": 1}
    b = next(x for x in r["results"] if x["name"] == "B Two")
    assert "sla_breach" in b["flags"]  # high severity: 21-day SLA already passed
    assert client.get("/api/intake/template.csv", headers=tokens["coordinator"]).text.startswith("name,language")
    bad = client.post("/api/intake/csv", json={"csv": "foo,bar\n1,2\n"}, headers=tokens["coordinator"])
    assert bad.status_code == 422


def test_closed_needs_documented_outcome(client, tokens, db):
    res = _add(client, tokens, name="Close Me")
    lid = res["loop_id"]
    r = client.post(f"/api/loops/{lid}/transition", json={"to_state": "CLOSED", "reason": "done"}, headers=tokens["coordinator"])
    assert r.status_code == 409
    body = {"outcome": "referral_completed", "seen_by": "Al Khalidiyah Healthcare Centre", "visit_date": clock.now(db).isoformat(),
            "summary": "Seen by GP; started on lifestyle programme", "next_step": "Repeat HbA1c in 3 months",
            "patient_informed": False, "report_shared_with": "Test Van"}
    assert client.post(f"/api/loops/{lid}/close", json=body, headers=tokens["coordinator"]).status_code == 422  # patient not told
    body["patient_informed"] = True
    r = client.post(f"/api/loops/{lid}/close", json=body, headers=tokens["coordinator"])
    assert r.status_code == 409  # no visit on record yet
    body["outcome"] = "seen_elsewhere"
    r = client.post(f"/api/loops/{lid}/close", json=body, headers=tokens["coordinator"])
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "CLOSED" and r.json()["closure"]["patient_informed"] is True
    d = client.get(f"/api/loops/{lid}", headers=tokens["coordinator"]).json()
    kinds = [c["kind"] for c in d["case_record"]]
    assert kinds[0] == "result" and "attended" in kinds and kinds[-1] == "closed"
    assert d["closure"]["seen_by"] == "Al Khalidiyah Healthcare Centre" and d["chain"]["valid"]
    task = client.get(f"/api/fhir/Task/{lid}", headers=tokens["coordinator"]).json()
    assert task["status"] == "completed" and task["owner"]["display"].startswith("Priya Nair")
    assert {o["type"]["text"] for o in task["output"]} >= {"outcome", "seen-by", "patient-informed", "report-shared-with"}
    assert client.post(f"/api/loops/{lid}/close", json=body, headers=tokens["coordinator"]).status_code == 409
    assert db.scalar(select(func.count(LoopClosure.id)).where(LoopClosure.loop_id == __import__("uuid").UUID(lid))) == 1


def test_chat_outcomes_flow_into_case_record(client, tokens):
    res = _add(client, tokens, name="Chat Person", language="en")
    lid = res["loop_id"]
    tok = client.post(f"/api/loops/{lid}/outreach", json={}, headers=tokens["coordinator"]).json()["token"]
    s = client.get(f"/api/c/{tok}").json()
    q = s["phrases"]["quick"]
    client.post(f"/api/c/{tok}/message", json={"text": q["qr_night"]})
    s = client.post(f"/api/c/{tok}/message", json={"text": q["qr_tb_diabetes"]}).json()
    slot = s["messages"][-1]["meta"]["slots"][0]["slot_id"]
    client.post(f"/api/c/{tok}/book", json={"slot_id": slot})
    client.post(f"/api/c/{tok}/message", json={"text": "I have severe chest pain right now"})
    d = client.get(f"/api/loops/{lid}", headers=tokens["coordinator"]).json()
    rec = {c["kind"]: c for c in d["case_record"]}
    for kind in ("barrier", "teach_back", "booked", "red_flag"):
        assert kind in rec, kind
        assert rec[kind]["source"] == "patient_chat" and rec[kind]["hash"]
    assert d["loop"]["state"] == "ESCALATED" and d["next_action"]
    esc = next(e for e in client.get("/api/escalations?reason=red_flag", headers=tokens["coordinator"]).json()["items"] if e["loop_id"] == lid)
    assert esc["owner"] == "Dr. Layla Haddad"


def test_reassign_owner_is_audited(client, tokens):
    res = _add(client, tokens, name="Owner Change", language="ar")
    lid = res["loop_id"]
    users = client.get("/api/users/staff", headers=tokens["coordinator"]).json()["items"]
    doc = next(u for u in users if u["role"] == "clinician")
    r = client.post(f"/api/loops/{lid}/assign", json={"user_id": doc["id"], "note": "needs a doctor"}, headers=tokens["coordinator"])
    assert r.status_code == 200 and r.json()["owner"] == doc["name"]
    d = client.get(f"/api/loops/{lid}", headers=tokens["coordinator"]).json()
    assert d["loop"]["owner"]["name"] == doc["name"]
    assert any("needs a doctor" in c["detail"] for c in d["case_record"] if c["kind"] == "owner")
    r = client.post(f"/api/loops/{lid}/assign", json={"user_id": doc["id"]}, headers=tokens["navigator"])
    assert r.status_code in (403,)


def test_red_flag_fast_path_needs_no_model_call():
    from app.llm.tasks import Tasks

    class LiveButBroken:
        name = "relay"

        def complete_json(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
            raise AssertionError("a known danger phrase must not wait for a model call")

        complete = complete_json

    u = Tasks(LiveButBroken()).understand("وجدت كتلة تنزف", "ar", "barrier", "BREAST")
    assert u["red_flag"] is True and u["red_flag_source"] == "lexicon" and u["intent"] == "red_flag"


def test_emergency_message_uses_clinician_approved_text(db):
    from app.models import ContentTemplate
    from app.navigator.messaging import Rendered, _approved

    tmpl = db.scalar(select(ContentTemplate).where(ContentTemplate.key == "urgent_care").limit(1))
    r = Rendered(key="urgent_care", template=tmpl, text_en="Call 999 now.", fixture_text="اتصل بالرقم 999 الآن.")
    res = _approved(r, "ar")
    assert res is not None and res.final_text == "اتصل بالرقم 999 الآن." and res.final_source == "approved_translation" and res.passed
    assert _approved(Rendered(key="greeting", template=tmpl, text_en="Hi", fixture_text="مرحبا"), "ar") is None
