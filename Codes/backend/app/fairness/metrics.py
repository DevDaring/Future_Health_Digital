"""Fairness metrics (spec section 11).

Per group (language, nationality group, insurance tier, sex):
* loop-closure rate on live loops (mature loops only: result ≥ 30 days old);
* model calibration (Brier) and true-positive rate of the high-risk flag, from the
  held-out test set stored with the active model;
* share of today's outreach budget versus share of need (open high/urgent loops);
* disparity flag when a group's closure rate is below 80% of the best group's
  (the four-fifths rule, used as a heuristic, not a legal test).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.ml.prioritise import allocate
from app.models import CareLoop, ModelRegistry, Patient, ScreeningEvent

GROUP_COLUMNS = {"language": "preferred_language", "nationality_group": "nationality_group", "insurance_tier": "insurance_tier", "sex": "sex"}
REGISTRY_KEYS = {"language": "by_language", "nationality_group": "by_nationality_group", "insurance_tier": "by_insurance_tier", "sex": "by_sex"}
FOUR_FIFTHS = 0.8


def fairness_metrics(db: Session, group_by: str = "language", budget: int = 200) -> dict[str, Any]:
    col = GROUP_COLUMNS[group_by]
    now = clock.now(db)
    rows = db.execute(
        select(CareLoop.state, getattr(Patient, col), ScreeningEvent.resulted_at)
        .join(Patient, CareLoop.patient_id == Patient.id)
        .join(ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id)
    ).all()
    closed: dict[str, list[int]] = defaultdict(list)
    for state, g, resulted in rows:
        if clock.as_utc(resulted) <= now - timedelta(days=30):
            closed[str(g)].append(int(state in ("ATTENDED", "CLOSED")))

    from app.api.worklist import candidates

    loops, cands = candidates(db)
    group_of = {str(lp.id): str(getattr(lp.patient, col)) for lp in loops}
    need: dict[str, int] = defaultdict(int)
    for c in cands:
        if c.severity in ("high", "urgent"):
            need[group_of[c.key]] += 1
    total_need = sum(need.values()) or 1
    alloc = {}
    for pol in ("risk_only", "uplift", "uplift_fair"):
        sel = allocate(cands, budget, pol)
        counts: dict[str, int] = defaultdict(int)
        for c in sel:
            counts[group_of[c.key]] += 1
        alloc[pol] = {g: round(n / max(len(sel), 1), 4) for g, n in counts.items()}

    reg = db.scalar(select(ModelRegistry).where(ModelRegistry.name == "risk", ModelRegistry.is_active.is_(True)).limit(1))
    model_groups = (reg.fairness or {}).get(REGISTRY_KEYS[group_by], {}) if reg else {}

    groups = sorted(set(closed) | set(need) | set(model_groups))
    rates = {g: (sum(closed[g]) / len(closed[g])) if closed[g] else None for g in groups}
    best = max((r for r in rates.values() if r is not None), default=None)
    out = []
    for g in groups:
        m = model_groups.get(g, {})
        r = rates[g]
        out.append(
            {
                "group": g,
                "n_loops": len(closed[g]),
                "closure_rate": round(r, 4) if r is not None else None,
                "ratio_to_best": round(r / best, 3) if (r is not None and best) else None,
                "disparity": bool(r is not None and best and r < FOUR_FIFTHS * best),
                "brier": m.get("brier"),
                "auroc": m.get("auroc"),
                "tpr_high_risk": m.get("tpr_high_risk"),
                "need_share": round(need[g] / total_need, 4),
                "budget_share": {pol: alloc[pol].get(g, 0.0) for pol in alloc},
            }
        )
    return {"group_by": group_by, "groups": out, "best_rate": best, "threshold": FOUR_FIFTHS, "budget": budget,
            "model_version": reg.version if reg else None}
