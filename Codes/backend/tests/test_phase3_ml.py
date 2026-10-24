"""Phase 3: risk model quality, uplift ranking quality, persona ranking, fairness floors."""

from __future__ import annotations

from app.ml.counterfactual import ACTION_GRID, action_complexity
from app.ml.metrics import auuc_from_curve, qini_curve
from app.ml.prioritise import Candidate, allocate, floors_for


def test_risk_auroc_above_070(seeded):
    assert seeded["bundle"].metrics["risk"]["auroc"] > 0.70


def test_uplift_auuc_beats_risk_beats_random(seeded):
    a = seeded["bundle"].metrics["uplift"]["auuc_true"]
    assert a["uplift"] > a["risk"] > a["random"]


def test_ramesh_ranks_above_sara_under_uplift(client, tokens):
    w = client.get("/api/worklist?policy=uplift&budget=200", headers=tokens["coordinator"]).json()
    p = w["personas"]
    assert p["ramesh"]["rank"] < p["sara"]["rank"]
    assert p["ramesh"]["in_budget"]


def test_counterfactuals_only_change_actionable_things(client, tokens, personas):
    d = client.get(f"/api/loops/{personas['ramesh']['loop_id']}", headers=tokens["coordinator"]).json()
    cfs = d["score"]["counterfactuals"]
    assert len(cfs) == 3
    for cf in cfs:
        assert set(cf["action"]) == {"channel", "lang_matched", "slot", "cost_info"}
        assert cf["p_return"] >= cf["p_baseline"] - 1e-9
    assert len(d["score"]["shap_top"]) == 5


def test_fairness_floors_respected():
    cands = []
    for i in range(300):
        group = "big" if i < 240 else "small"
        sev = "high"
        # the small group has systematically lower uplift, so unconstrained uplift ignores it
        cands.append(Candidate(key=f"k{i:03d}", group=group, severity=sev, p_dropoff=0.5, uplift=0.5 if group == "big" else 0.1))
    budget = 50
    plain = allocate(cands, budget, "uplift")
    assert sum(c.group == "small" for c in plain) == 0
    fair = allocate(cands, budget, "uplift_fair", epsilon=0.1)
    floors = floors_for(cands, budget, 0.1)
    assert len(fair) == budget
    for g, fl in floors.items():
        assert sum(c.group == g for c in fair) >= fl
    assert floors["small"] == 9  # floor(50 × 0.2 × 0.9)


def test_qini_random_is_near_zero():
    import numpy as np

    rng = np.random.default_rng(0)
    n = 4000
    t = rng.random(n) < 0.5
    y = (rng.random(n) < 0.5).astype(int)
    assert abs(auuc_from_curve(qini_curve(rng.random(n), t, y))) < 0.15


def test_action_grid_is_actionable():
    assert len(ACTION_GRID) == 48
    assert action_complexity({"channel": "call", "lang_matched": True, "slot": "none", "cost_info": False}) == 0
