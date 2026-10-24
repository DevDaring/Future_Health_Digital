"""Impact & ROI calculator (killer feature 9), driven by the latest Policy Twin run.

All rates and costs are ILLUSTRATIVE assumptions with ranges, for a payer conversation,
not a forecast.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SimRun, User
from app.security import require

router = APIRouter(prefix="/roi", tags=["roi"])

# P(late-stage disease or complication | follow-up missed), low–high. ILLUSTRATIVE.
LATE_STAGE_RISK = {"DIABETES": (0.02, 0.06), "COLORECTAL": (0.03, 0.08), "BREAST": (0.05, 0.12)}


@router.get("")
def roi(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require("worklist"))],
    abnormal_per_year: int = 20000,
    cost_sms: float = 0.5,
    cost_call: float = 25.0,
    cost_visit: float = 150.0,
    late_stage_cost: float = 150000.0,
    policy: str = "wasl_uplift_fair",
) -> dict[str, Any]:
    run = db.scalar(select(SimRun).where(SimRun.kind == "compare", SimRun.status == "done").order_by(SimRun.created_at.desc()).limit(1))
    if run is None:
        raise HTTPException(404, "Run the Policy Twin first: ROI uses its latest results")
    res = run.results["results"]
    base = res.get("no_outreach")
    pol = res.get(policy) or res.get("wasl_uplift")
    if base is None or pol is None:
        raise HTTPException(409, "Latest twin run must include no_outreach and a WASL policy")
    n = pol["n"]
    scale = abnormal_per_year / n
    extra_rate = pol["closure_rate"] - base["closure_rate"]
    extra_per_1000 = extra_rate * 1000
    contacts_per_year = pol["contacts"] * scale
    unit = cost_sms if pol["policy"] == "sms_everyone" else cost_call
    outreach_cost = contacts_per_year * unit
    closed_per_year = pol["closure_rate"] * abnormal_per_year
    extra_per_year = extra_rate * abnormal_per_year
    # Late-stage cases avoided, weighted by the program mix of extra closures.
    prog_base = base["by_group"]["program"]
    prog_pol = pol["by_group"]["program"]
    lo = hi = 0.0
    mix = {}
    for prog, (rlo, rhi) in LATE_STAGE_RISK.items():
        d = (prog_pol.get(prog, 0) - prog_base.get(prog, 0))
        share = run.results.get("program_share", {}).get(prog)
        mix[prog] = round(d, 4)
        weight = share if share is not None else _program_share(prog)
        lo += d * weight * abnormal_per_year * rlo
        hi += d * weight * abnormal_per_year * rhi
    extra_visit_cost = extra_per_year * cost_visit
    return {
        "run_id": str(run.id),
        "policy": pol["policy"],
        "policy_label": pol["label"],
        "inputs": {"abnormal_per_year": abnormal_per_year, "cost_sms": cost_sms, "cost_call": cost_call, "cost_visit": cost_visit,
                   "late_stage_cost": late_stage_cost},
        "closure_baseline": base["closure_rate"],
        "closure_policy": pol["closure_rate"],
        "extra_loops_per_1000": round(extra_per_1000, 1),
        "extra_loops_per_year": round(extra_per_year),
        "loops_closed_per_year": round(closed_per_year),
        "outreach_cost_per_year": round(outreach_cost),
        "extra_visit_cost_per_year": round(extra_visit_cost),
        "cost_per_closed_loop": round((outreach_cost + closed_per_year * cost_visit) / max(closed_per_year, 1), 1),
        "outreach_cost_per_extra_loop": round(outreach_cost / extra_per_year, 1) if extra_per_year > 0 else None,
        "late_stage_avoided": {"low": round(lo, 1), "high": round(hi, 1)},
        "net_benefit": {"low": round(lo * late_stage_cost - outreach_cost - extra_visit_cost),
                        "high": round(hi * late_stage_cost - outreach_cost - extra_visit_cost)},
        "late_stage_risk_assumptions": {k: {"low": v[0], "high": v[1]} for k, v in LATE_STAGE_RISK.items()},
        "closure_change_by_program": mix,
        "label": "ILLUSTRATIVE — assumptions shown; not a forecast",
    }


def _program_share(prog: str) -> float:
    # Typical program mix of abnormal results in the synthetic population (DIABETES dominates).
    return {"DIABETES": 0.86, "COLORECTAL": 0.07, "BREAST": 0.07}[prog]
