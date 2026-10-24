"""Ranked worklist under a daily outreach budget, with the policy switch."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.api.common import loop_row, names_for, paginate
from app.config import get_settings
from app.db import get_db
from app.loop_engine.state_machine import TERMINAL
from app.ml.prioritise import Candidate, allocate, floors_for, need_shares
from app.models import CareLoop, RiskScore, User
from app.security import require

router = APIRouter(prefix="/worklist", tags=["worklist"])
WORKABLE_EXCLUDE = list(TERMINAL | {"ATTENDED", "BOOKED"})


def candidates(db: Session, user: User | None = None) -> tuple[list[CareLoop], list[Candidate]]:
    q = select(CareLoop).where(CareLoop.state.notin_(WORKABLE_EXCLUDE), CareLoop.uplift.is_not(None))
    if user is not None and user.role == "navigator":
        q = q.where(CareLoop.assigned_to == user.id)
    loops = list(db.scalars(q).unique())
    cands = [
        Candidate(key=str(lp.id), group=lp.patient.preferred_language, severity=lp.screening.severity,
                  p_dropoff=float(lp.risk_dropoff or 0), uplift=float(lp.uplift or 0))
        for lp in loops
    ]
    return loops, cands


@router.get("")
def worklist(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require("worklist"))],
    policy: str = Query("uplift", pattern="^(uplift|risk_only|uplift_fair)$"),
    budget: int | None = Query(None, ge=1, le=2000),
    page: int = 1,
    size: int = 50,
    program: str | None = None,
    q: str | None = None,
    show_all: bool = False,
) -> dict[str, Any]:
    budget = budget or get_settings().daily_outreach_budget
    loops, cands = candidates(db, user)
    by_id = {str(lp.id): lp for lp in loops}
    ranked_all = sorted(cands, key=lambda c: (-c.priority(policy if policy != "uplift_fair" else "uplift"), c.key))
    selected = allocate(cands, budget, policy)
    selected_keys = [c.key for c in selected]
    rank_of = {k: i + 1 for i, k in enumerate(selected_keys)}
    order = selected_keys + ([c.key for c in ranked_all if c.key not in rank_of] if show_all else [])
    now = clock.now(db)
    scores = {s.loop_id: s for s in db.scalars(select(RiskScore).where(RiskScore.loop_id.in_([by_id[k].id for k in order])))}
    names = names_for(db, [by_id[k].patient_id for k in order], user)
    items = []
    for k in order:
        lp = by_id[k]
        row = loop_row(lp, names.get(lp.patient_id, "—"), now, scores.get(lp.id))
        row["rank"] = rank_of.get(k)
        row["in_budget"] = k in rank_of
        row["policy_score"] = round(next(c for c in cands if c.key == k).priority(policy if policy != "uplift_fair" else "uplift"), 4)
        items.append(row)
    if program:
        items = [i for i in items if i["program"] == program]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in i["display_name"].lower() or ql in i["patient_code"].lower()]

    # Persona tracker + what changed versus risk-only ranking (for the demo / Judge Mode).
    full_rank = {c.key: i + 1 for i, c in enumerate(ranked_all)}
    personas = {lp.patient.persona: {"loop_id": str(lp.id), "rank": full_rank.get(str(lp.id)), "in_budget": str(lp.id) in rank_of}
                for lp in loops if lp.patient.persona}
    risk_sel = {c.key for c in allocate(cands, budget, "risk_only")}
    sel = set(selected_keys)
    swapped_in = [by_id[k] for k in sel - risk_sel]
    swapped_out = [by_id[k] for k in risk_sel - sel]

    def avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 3) if xs else None

    shares = need_shares(cands)
    sel_groups: dict[str, int] = {}
    for c in selected:
        sel_groups[c.group] = sel_groups.get(c.group, 0) + 1
    return {
        **paginate(items, page, size),
        "policy": policy,
        "budget": budget,
        "eligible": len(cands),
        "personas": personas,
        "vs_risk_only": {
            "swapped_in": len(swapped_in),
            "swapped_out": len(swapped_out),
            "avg_uplift_in": avg([float(x.uplift or 0) for x in swapped_in]),
            "avg_uplift_out": avg([float(x.uplift or 0) for x in swapped_out]),
            "avg_prior_no_shows_out": avg([float(x.patient.prior_no_shows) for x in swapped_out]),
            "expected_extra_returns": round(sum(c.uplift for c in selected) - sum(c.uplift for c in cands if c.key in risk_sel), 1),
        },
        "expected_returns_from_outreach": round(sum(c.uplift for c in selected), 1),
        "allocation": {
            g: {"need_share": round(s, 4), "budget_share": round(sel_groups.get(g, 0) / max(len(selected), 1), 4),
                "floor": floors_for(cands, budget).get(g, 0) if policy == "uplift_fair" else None}
            for g, s in sorted(shares.items())
        },
    }
