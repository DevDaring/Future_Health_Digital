"""Phase 6: fairness, model card, FHIR, ROI, CSV export, RBAC matrix."""

from __future__ import annotations

import json

import pytest

from app.config import FIXTURES_DIR


def test_fhir_import_creates_loop_and_exports(client, tokens):
    bundle = json.loads((FIXTURES_DIR / "fhir" / "sample_bundle.json").read_text())
    r = client.post("/api/fhir/Bundle", json=bundle, headers=tokens["coordinator"])
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1  # the normal 5.4% result does not open a loop
    loop_id = r.json()["created_loops"][0]
    task = client.get(f"/api/fhir/Task/{loop_id}", headers=tokens["coordinator"]).json()
    assert task["resourceType"] == "Task" and task["status"] and task["intent"] == "order" and task["for"]["reference"].startswith("Patient/")
    sr = client.get(f"/api/fhir/ServiceRequest/{loop_id}", headers=tokens["coordinator"]).json()
    assert sr["resourceType"] == "ServiceRequest" and sr["status"] and sr["intent"] and sr["subject"]
    d = client.get(f"/api/loops/{loop_id}", headers=tokens["coordinator"]).json()
    obs = client.get(f"/api/fhir/Observation?patient={d['loop']['patient_id']}", headers=tokens["coordinator"]).json()
    o = obs["entry"][0]["resource"]
    assert o["resourceType"] == "Observation" and o["status"] == "final" and o["code"]["coding"][0]["code"] == "4548-4"
    assert o["valueQuantity"]["value"] == 8.2
    assert d["loop"]["severity"] == "high" and d["score"] is not None


def test_fhir_appointment_export(client, tokens, personas):
    d = client.get(f"/api/loops/{personas['ramesh']['loop_id']}", headers=tokens["coordinator"]).json()
    if not d["appointments"]:
        pytest.skip("Ramesh not booked in this run")
    ap = client.get(f"/api/fhir/Appointment/{d['appointments'][0]['id']}", headers=tokens["coordinator"]).json()
    assert ap["resourceType"] == "Appointment" and ap["status"] == "booked" and ap["start"] and ap["participant"]


def test_fairness_metrics(client, tokens):
    r = client.get("/api/fairness/metrics?group_by=language", headers=tokens["clinician"]).json()
    groups = {g["group"]: g for g in r["groups"]}
    assert {"ar", "en", "ml"} <= set(groups)
    assert any(g["disparity"] for g in r["groups"]) or r["best_rate"] is not None
    for g in r["groups"]:
        assert set(g["budget_share"]) == {"risk_only", "uplift", "uplift_fair"}


def test_model_card_and_calibration(client, tokens):
    mc = client.get("/api/governance/model-card", headers=tokens["coordinator"]).json()
    assert mc["risk"]["auroc"] > 0.7 and mc["intended_use"] and mc["out_of_scope"]
    cal = client.get("/api/governance/calibration", headers=tokens["coordinator"]).json()
    assert len(cal["bins"]) >= 5


def test_audit_csv_export(client, tokens):
    r = client.get("/api/governance/audit/export.csv", headers=tokens["coordinator"])
    assert r.status_code == 200 and r.text.startswith("seq,event_id")


def test_roi_from_latest_twin_run(client, tokens):
    import time

    rid = client.post("/api/twin/runs", json={"params": {"seed": 42}}, headers=tokens["admin"]).json()["id"]
    for _ in range(200):
        if client.get(f"/api/twin/runs/{rid}", headers=tokens["admin"]).json()["status"] == "done":
            break
        time.sleep(0.25)
    r = client.get("/api/roi?abnormal_per_year=20000", headers=tokens["coordinator"]).json()
    assert r["extra_loops_per_1000"] > 0
    assert r["late_stage_avoided"]["low"] <= r["late_stage_avoided"]["high"]


# ----------------------------------------------------------------- RBAC matrix
MATRIX = [
    # (method, path-template, {role: expected_status})
    ("GET", "/api/worklist", {"admin": 200, "coordinator": 200, "clinician": 200, "navigator": 200}),
    ("GET", "/api/loops/{sara}/patient-twin", {"admin": 200, "coordinator": 200, "clinician": 200, "navigator": 403}),
    ("POST", "/api/content/templates/{template}/approve", {"admin": 200, "coordinator": 403, "clinician": 200, "navigator": 403}),
    ("GET", "/api/twin/defaults", {"admin": 200, "coordinator": 200, "clinician": 200, "navigator": 403}),
    ("GET", "/api/governance/audit/verify", {"admin": 200, "coordinator": 200, "clinician": 200, "navigator": 403}),
    ("GET", "/api/governance/model-card", {"admin": 200, "coordinator": 200, "clinician": 200, "navigator": 403}),
    ("POST", "/api/demo/tamper", {"coordinator": 403, "clinician": 403, "navigator": 403}),
]


@pytest.mark.parametrize("method,path,expect", MATRIX)
def test_rbac_matrix(client, tokens, personas, method, path, expect):
    tmpl = client.get("/api/content/templates", headers=tokens["admin"]).json()["items"][0]["id"]
    url = path.format(sara=personas["sara"]["loop_id"], template=tmpl)
    for role, status in expect.items():
        r = client.request(method, url, headers=tokens[role])
        assert r.status_code == status, f"{role} {method} {url} → {r.status_code}"


def test_navigator_sees_assigned_only_and_masked_pii(client, tokens, personas):
    w = client.get("/api/worklist?budget=500", headers=tokens["navigator"]).json()
    assert w["total"] <= 160
    for item in w["items"]:
        assert " " not in item["display_name"]  # first name only
    d = client.get(f"/api/loops/{personas['ramesh']['loop_id']}", headers=tokens["navigator"]).json()
    assert d["identity"]["pii_level"] == "first_name" and d["identity"]["phone"] is None
    d = client.get(f"/api/loops/{personas['ramesh']['loop_id']}", headers=tokens["coordinator"]).json()
    assert d["identity"]["display_name"].endswith(".") and "***" in d["identity"]["phone"]
    d = client.get(f"/api/loops/{personas['ramesh']['loop_id']}", headers=tokens["admin"]).json()
    assert d["identity"]["pii_level"] == "full"


def test_unauthenticated_is_rejected(client):
    assert client.get("/api/worklist").status_code == 401
    assert client.post("/api/auth/login", json={"username": "DevTest", "password": "wrong"}).status_code == 401


def test_consent_search_finds_patients_off_the_worklist(client, tokens, db):
    from sqlalchemy import select

    from app.models import CareLoop, Patient

    booked = db.scalars(select(Patient).join(CareLoop, CareLoop.patient_id == Patient.id)
                        .where(CareLoop.state.in_(["BOOKED", "ATTENDED", "CLOSED"]))).first()
    assert booked is not None
    r = client.get(f"/api/patients/search?q={booked.code}", headers=tokens["coordinator"]).json()
    assert [i["patient_code"] for i in r["items"]] == [booked.code]
    r = client.get("/api/patients/search?q=ramesh", headers=tokens["coordinator"]).json()
    assert r["items"] and r["items"][0]["persona"] == "ramesh"
    assert client.get("/api/patients/search?q=%25%25", headers=tokens["coordinator"]).json()["items"] == []
