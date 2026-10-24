"""Phase 5: system twin speed, determinism, policy ordering, sensitivity; patient twin."""

from __future__ import annotations

import time

from app.twin.patient_twin import patient_twin
from app.twin.system_twin import _COHORT_CACHE, POLICIES, run_policies, sensitivity


def test_twin_speed_determinism_and_ordering(seeded):
    _COHORT_CACHE.clear()
    t0 = time.perf_counter()
    a = run_policies(list(POLICIES), {"seed": 42})
    elapsed = time.perf_counter() - t0
    assert elapsed < 20, f"twin took {elapsed:.1f}s"
    assert a["results"]["wasl_uplift"]["n"] == 5000
    b = run_policies(list(POLICIES), {"seed": 42})
    for pol in POLICIES:
        assert a["results"][pol]["closure_rate"] == b["results"][pol]["closure_rate"]
        assert a["results"][pol]["series"] == b["results"][pol]["series"]
    r = {k: v["closure_rate"] for k, v in a["results"].items()}
    assert r["wasl_uplift"] > r["risk_ranked"] > r["sms_everyone"] > r["no_outreach"]
    # the fairness-constrained policy narrows the budget-share vs need-share gap
    assert a["results"]["wasl_uplift_fair"]["allocation_gap"] < a["results"]["wasl_uplift"]["allocation_gap"]
    assert abs(a["calibration"]["abs_diff"]) < 0.03


def test_sensitivity_robustness_badge(seeded):
    s = sensitivity(["no_outreach", "sms_everyone", "risk_ranked", "wasl_uplift"], {"seed": 42})
    assert s["scales"] == [0.5, 1.0, 1.5]
    assert isinstance(s["robust"], bool)
    assert s["robust"] is True


def test_twin_run_api_background(client, tokens):
    import time as _t

    r = client.post("/api/twin/runs", json={"policies": ["no_outreach", "wasl_uplift"], "params": {"seed": 42}}, headers=tokens["coordinator"])
    assert r.status_code == 200
    rid = r.json()["id"]
    for _ in range(120):
        run = client.get(f"/api/twin/runs/{rid}", headers=tokens["coordinator"]).json()
        if run["status"] in ("done", "error"):
            break
        _t.sleep(0.25)
    assert run["status"] == "done", run.get("error")
    assert "wasl_uplift" in run["results"]["results"]
    assert client.post("/api/twin/runs", json={}, headers=tokens["navigator"]).status_code == 403


def test_patient_twin_delay_increases_risk():
    out = patient_twin("DIABETES", "diabetes range")
    p = [d["p_outcome_5y"] for d in out["delays"]]
    assert p == sorted(p) and p[-1] > p[0]
    for d in out["delays"]:
        assert d["lo"] <= d["p_outcome_5y"] <= d["hi"]
    assert "ILLUSTRATIVE" in out["label"]


def test_patient_twin_rbac(client, tokens, personas):
    lid = personas["sara"]["loop_id"]
    assert client.get(f"/api/loops/{lid}/patient-twin", headers=tokens["navigator"]).status_code == 403
    assert client.get(f"/api/loops/{lid}/patient-twin", headers=tokens["clinician"]).status_code == 200
    assert client.get(f"/api/loops/{lid}/patient-twin", headers=tokens["coordinator"]).status_code == 200
