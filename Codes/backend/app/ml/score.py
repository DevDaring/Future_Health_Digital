"""Score open care loops: risk, uplift (T-learner), SHAP reasons, counterfactuals, priority.

`uplift` stored on a loop is the predicted gain from WASL's *best* actionable outreach
package (from the counterfactual search) over no outreach. `p_return_if_contacted` is the
probability under that package.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import clock
from app.loop_engine.state_machine import TERMINAL
from app.ml.counterfactual import ACTION_GRID, action_matrix, top_counterfactuals
from app.ml.explain import shap_values, top_reasons
from app.ml.features import build_features
from app.ml.prioritise import SEVERITY_WEIGHT
from app.ml.registry import ModelBundle, load_active
from app.models import CareLoop, Patient, RiskScore, ScreeningEvent

PATIENT_COLS = [
    "age", "sex", "nationality_group", "preferred_language", "literacy_level", "occupation_type",
    "shift_pattern", "preferred_days", "home_area", "distance_km", "insurance_tier", "prior_no_shows",
    "has_smartphone", "preferred_channel", "no_free_weekdays",
]


def loops_frame(db: Session, loop_ids: list[uuid.UUID] | None = None, open_only: bool = True) -> pd.DataFrame:
    q = select(CareLoop, Patient, ScreeningEvent).join(Patient, CareLoop.patient_id == Patient.id).join(
        ScreeningEvent, CareLoop.screening_event_id == ScreeningEvent.id
    )
    if loop_ids is not None:
        q = q.where(CareLoop.id.in_(loop_ids))
    elif open_only:
        q = q.where(CareLoop.state.notin_(list(TERMINAL | {"ATTENDED"})))
    now = clock.now(db)
    rows: list[dict[str, Any]] = []
    for loop, p, se in db.execute(q).unique():
        resulted = clock.as_utc(se.resulted_at)
        row = {c: getattr(p, c) for c in PATIENT_COLS}
        row.update(
            loop_id=loop.id,
            patient_id=p.id,
            state=loop.state,
            program=se.program,
            severity=se.severity,
            days_since_result=max(0, (now - resulted).days),
        )
        rows.append(row)
    return pd.DataFrame(rows)


def score_frame(bundle: ModelBundle, df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    p_drop = bundle.p_dropoff(df)
    p0 = bundle.p_return_no(df)
    P = action_matrix(bundle, df)
    best_j = P.argmax(axis=1)
    p1 = P[np.arange(len(df)), best_j]
    X = build_features(df)[bundle.base_cols]
    reasons = top_reasons(X, shap_values(bundle.risk_model, X), k=5)
    cfs = top_counterfactuals(bundle, df, k=3, p_matrix=P, p0=p0)
    out = []
    for i in range(len(df)):
        uplift = float(max(0.0, p1[i] - p0[i]))
        sev = df["severity"].iloc[i]
        out.append(
            {
                "loop_id": df["loop_id"].iloc[i],
                "p_dropoff": float(p_drop[i]),
                "p_return_if_not": float(p0[i]),
                "p_return_if_contacted": float(p1[i]),
                "uplift": uplift,
                "best_action": ACTION_GRID[int(best_j[i])],
                "shap_top": reasons[i],
                "counterfactuals": cfs[i],
                "priority": SEVERITY_WEIGHT.get(sev, 1.0) * uplift,
            }
        )
    return out


def score_open_loops(db: Session, bundle: ModelBundle | None = None, loop_ids: list[uuid.UUID] | None = None) -> int:
    bundle = bundle or load_active()
    if bundle is None:
        return 0
    df = loops_frame(db, loop_ids=loop_ids)
    scores = score_frame(bundle, df)
    if not scores:
        return 0
    ids = [s["loop_id"] for s in scores]
    for chunk in range(0, len(ids), 500):
        db.execute(delete(RiskScore).where(RiskScore.loop_id.in_(ids[chunk : chunk + 500])))
    now = datetime.now(UTC)
    loops = {lp.id: lp for lp in db.scalars(select(CareLoop).where(CareLoop.id.in_(ids)))}
    for s in scores:
        db.add(
            RiskScore(
                loop_id=s["loop_id"],
                model_version=bundle.version,
                p_dropoff=s["p_dropoff"],
                p_return_if_contacted=s["p_return_if_contacted"],
                p_return_if_not=s["p_return_if_not"],
                uplift=s["uplift"],
                shap_top=s["shap_top"],
                counterfactuals=s["counterfactuals"],
                scored_at=now,
            )
        )
        lp = loops[s["loop_id"]]
        lp.risk_dropoff = s["p_dropoff"]
        lp.uplift = s["uplift"]
        lp.priority_score = s["priority"]
    db.flush()
    return len(scores)
