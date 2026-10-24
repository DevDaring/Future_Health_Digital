"""Care-pathway system twin (SimPy, spec section 10.1).

What is simulated
* Abnormal results arrive over the horizon (Poisson arrivals) for synthetic patients.
* Each day a policy picks whom to contact, under the same daily contact budget.
* Tailored contacts need a navigator (`simpy.Resource`, ~15 min per call, 7 h/day).
* Whether and when a person returns comes from the hidden ground-truth behaviour model
  plus the effect of the outreach package the policy used.
* People who return wait for a slot at their nearest clinic (`simpy.Resource` per
  clinic, with daily capacity), then attend; the loop closes.

Paired comparison (idea borrowed from the NemoTwins/Pratifalan particle twins): every
policy sees the *same* patients and the *same* random numbers (common random numbers):
the same uniform decides "returns or not" for a person in every policy, so differences
between policies come from the policy, not from sampling noise.

Policies rank people using the trained ML models (as they would in reality); outcomes
come from the ground truth (which the models never see).
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import simpy

from app.ml.prioritise import SEVERITY_WEIGHT
from app.synth.behaviour import SMS_DEFAULT, STANDARD_CALL, Action, baseline_logit, effect_logit, sigmoid
from app.synth.population import draw_abnormal_results, generate_population, load_config

POLICIES = ("no_outreach", "sms_everyone", "risk_ranked", "wasl_uplift", "wasl_uplift_fair")
POLICY_LABELS = {
    "no_outreach": "No outreach",
    "sms_everyone": "SMS everyone",
    "risk_ranked": "Risk-ranked calls",
    "wasl_uplift": "WASL uplift",
    "wasl_uplift_fair": "WASL uplift + fairness",
}
NATIVE_NAVIGATOR_LANGS = {"ar", "en", "hi", "ur"}  # ILLUSTRATIVE default navigator team
SLA_WINDOW_DAYS = 60
WORK_MIN_PER_DAY = 7 * 60


@dataclass
class TwinParams:
    horizon_days: int = 180
    n_patients: int = 5000
    navigators: int = 1
    daily_budget: int = 20
    clinic_capacity_multiplier: float = 1.0
    visits_per_clinic_per_day: float = 8.0  # ILLUSTRATIVE; tuned so the no-outreach twin matches history
    extra_evening_friday: bool = False
    extra_language: str | None = None
    cost_sms: float = 0.5  # AED, ILLUSTRATIVE
    cost_call: float = 25.0  # AED per tailored navigation contact, ILLUSTRATIVE
    cost_visit: float = 150.0  # AED per follow-up visit, ILLUSTRATIVE
    call_minutes: float = 15.0
    effect_scale: float = 1.0
    fairness_epsilon: float = 0.1
    seed: int = 42

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TwinParams:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Cohort:
    """Synthetic arrivals + pre-drawn common random numbers + model predictions."""

    df: pd.DataFrame
    arrival: np.ndarray
    u_return: np.ndarray
    u_time_nat: np.ndarray
    u_time_contact: np.ndarray
    clinic: np.ndarray
    p_dropoff_pred: np.ndarray
    uplift_pred: np.ndarray
    best_action: list[Action]
    base_logit: np.ndarray
    model_used: bool
    extra: dict[str, Any] = field(default_factory=dict)


_COHORT_CACHE: dict[tuple[int, int, int], Cohort] = {}


def build_cohort(p: TwinParams) -> Cohort:
    key = (p.seed, p.n_patients, p.horizon_days)
    if key in _COHORT_CACHE:
        return _COHORT_CACHE[key]
    rng = np.random.default_rng(p.seed + 5000)
    pop = generate_population(int(p.n_patients * 3.6), seed=p.seed + 5000)
    res = pd.DataFrame(draw_abnormal_results(pop, rng)).drop_duplicates("idx")
    df = res.merge(pop, on="idx", how="left").head(p.n_patients).reset_index(drop=True)
    df["days_since_result"] = 0
    n = len(df)
    arrival = np.sort(rng.uniform(0, p.horizon_days, n))
    from app.scheduling.slots import AREA_COORDS, haversine_km
    from app.synth.personas import CLINICS

    clinic_idx = []
    for area in df["home_area"]:
        home = AREA_COORDS.get(area, AREA_COORDS["Al Wahda"])
        clinic_idx.append(int(np.argmin([haversine_km(home, (c["lat"], c["lon"])) for c in CLINICS])))
    model_used = False
    try:
        from app.ml.counterfactual import ACTION_GRID, action_matrix
        from app.ml.registry import load_active

        bundle = load_active()
        if bundle is None:
            raise RuntimeError("no model")
        p_drop = bundle.p_dropoff(df)
        p0 = bundle.p_return_no(df)
        P = action_matrix(bundle, df)
        j = P.argmax(axis=1)
        uplift = np.maximum(0, P[np.arange(n), j] - p0)
        best = [Action(**ACTION_GRID[int(k)]) for k in j]
        model_used = True
    except Exception:  # no trained model yet: noisy oracle so the twin still runs
        from app.synth.behaviour import best_true_action, p_return

        p0t = p_return(df, None)
        best = best_true_action(df)
        p1t = np.array([float(p_return(df.iloc[[i]], best[i])[0]) for i in range(n)])
        noise = rng.normal(0, 0.05, n)
        p_drop = np.clip(1 - p0t + noise, 0, 1)
        uplift = np.clip(p1t - p0t + noise, 0, 1)
    cohort = Cohort(
        df=df,
        arrival=arrival,
        u_return=rng.random(n),
        u_time_nat=rng.random(n),
        u_time_contact=rng.random(n),
        clinic=np.array(clinic_idx),
        p_dropoff_pred=np.asarray(p_drop),
        uplift_pred=np.asarray(uplift),
        best_action=best,
        base_logit=baseline_logit(df),
        model_used=model_used,
    )
    _COHORT_CACHE[key] = cohort
    return cohort


def _trunc_exp(u: float, mean: float, cap: float) -> float:
    """Inverse-CDF draw from an exponential truncated at `cap` (keeps CRN monotone)."""
    return -mean * math.log(1 - u * (1 - math.exp(-cap / mean)))


def simulate(policy: str, p: TwinParams, cohort: Cohort | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    c = cohort or build_cohort(p)
    df = c.df
    n = len(df)
    beh = load_config()["behaviour"]
    env = simpy.Environment()
    nav = simpy.Resource(env, capacity=max(1, p.navigators))
    cap = p.visits_per_clinic_per_day * p.clinic_capacity_multiplier * (1.15 if p.extra_evening_friday else 1.0)
    from app.synth.personas import CLINICS

    clinics = [simpy.Resource(env, capacity=1) for _ in CLINICS]
    visit_time = 1.0 / max(cap, 0.1)  # days per visit at one clinic
    langs = df["preferred_language"].to_numpy()
    lang_cap = np.array([1.0 if (lg in NATIVE_NAVIGATOR_LANGS or lg == p.extra_language) else 0.6 for lg in langs])
    slot_avail = 1.0 if p.extra_evening_friday else 0.6

    # Return probability without outreach (ground truth) and its timing.
    p0 = sigmoid(c.base_logit)
    natural_returns = c.u_return < p0
    contacted_at = np.full(n, np.nan)
    returned_at = np.full(n, np.nan)
    attended_at = np.full(n, np.nan)
    action_used: list[Action | None] = [None] * n
    pending_return: dict[int, simpy.Event] = {}
    queue_series: list[int] = []
    cost = {"sms": 0.0, "call": 0.0, "visit": 0.0}
    nav_busy = 0.0
    contacts = 0

    # Effects of the three kinds of outreach package, vectorised once (fast lookups later).
    eff_sms = effect_logit(df, SMS_DEFAULT.channel, SMS_DEFAULT.lang_matched, SMS_DEFAULT.slot, SMS_DEFAULT.cost_info)
    eff_std = effect_logit(df, STANDARD_CALL.channel, STANDARD_CALL.lang_matched, STANDARD_CALL.slot, STANDARD_CALL.cost_info,
                           lang_capacity=lang_cap, slot_availability=slot_avail)
    eff_best = effect_logit(
        df, np.array([a.channel for a in c.best_action], dtype=object), np.array([a.lang_matched for a in c.best_action]),
        np.array([a.slot for a in c.best_action], dtype=object), np.array([a.cost_info for a in c.best_action]),
        lang_capacity=lang_cap, slot_availability=slot_avail,
    )
    p_sms = sigmoid(c.base_logit + p.effect_scale * eff_sms)
    p_std = sigmoid(c.base_logit + p.effect_scale * eff_std)
    p_best = sigmoid(c.base_logit + p.effect_scale * eff_best)

    def p_with(i: int, a: Action) -> float:
        if a is SMS_DEFAULT:
            return float(p_sms[i])
        if a is STANDARD_CALL:
            return float(p_std[i])
        return float(p_best[i])

    def visit(i: int) -> Any:
        res = clinics[int(c.clinic[i])]
        with res.request() as req:
            yield req
            yield env.timeout(visit_time)
        attended_at[i] = env.now
        cost["visit"] += p.cost_visit

    def patient(i: int) -> Any:
        yield env.timeout(c.arrival[i])
        t_nat = c.arrival[i] + 2 + _trunc_exp(c.u_time_nat[i], beh["return_time_mean_days"], SLA_WINDOW_DAYS - 2) if natural_returns[i] else math.inf
        wake = env.event()
        pending_return[i] = wake
        timeout = env.timeout(max(0.0, t_nat - env.now)) if math.isfinite(t_nat) else None
        events = [wake] + ([timeout] if timeout is not None else [])
        result = yield env.any_of(events)
        if wake in result and wake.value is not None:
            t_contact_return = wake.value
            if math.isfinite(t_contact_return):
                when = min(t_nat, t_contact_return)
                if when > env.now:
                    yield env.timeout(when - env.now)
            elif math.isfinite(t_nat):
                if t_nat > env.now:
                    yield env.timeout(t_nat - env.now)
            else:
                pending_return.pop(i, None)
                return
        pending_return.pop(i, None)
        returned_at[i] = env.now
        yield env.process(visit(i))

    def call(i: int, a: Action) -> Any:
        nonlocal nav_busy, contacts
        with nav.request() as req:
            yield req
            dur = p.call_minutes / WORK_MIN_PER_DAY
            yield env.timeout(dur)
            nav_busy += dur
        contacts += 1
        cost["call"] += p.cost_call
        contacted_at[i] = env.now
        _resolve_contact(i, a)

    def _resolve_contact(i: int, a: Action) -> None:
        action_used[i] = a
        p1 = p_with(i, a)
        ev = pending_return.get(i)
        if ev is None or ev.triggered:
            return
        if c.u_return[i] < p1:  # common random number: monotone in the return probability
            t = env.now + 1 + _trunc_exp(c.u_time_contact[i], beh["contacted_return_time_mean_days"], SLA_WINDOW_DAYS - 1)
            ev.succeed(t)
        else:
            ev.succeed(math.inf)

    quota: dict[str, dict[str, float]] = {"ent": {}, "got": {}}
    need_counts: dict[str, int] = defaultdict(int)
    contact_counts: dict[str, int] = defaultdict(int)
    for lg, sv in zip(langs, df["severity"].to_numpy(), strict=True):
        if sv in ("high", "urgent"):
            need_counts[str(lg)] += 1

    def controller() -> Any:
        day = 0
        while day < p.horizon_days + SLA_WINDOW_DAYS:
            if day < p.horizon_days + 30 and policy != "no_outreach":
                pool = [
                    i for i in list(pending_return.keys())
                    if np.isnan(contacted_at[i]) and action_used[i] is None and env.now - c.arrival[i] < SLA_WINDOW_DAYS - 5
                ]
                chosen = choose(policy, pool, p.daily_budget, c, p.fairness_epsilon, quota)
                for i in chosen:
                    contact_counts[str(langs[i])] += 1
                for i in chosen:
                    if policy == "sms_everyone":
                        cost["sms"] += p.cost_sms
                        contacted_at[i] = env.now
                        _resolve_contact(i, SMS_DEFAULT)
                    else:
                        a = STANDARD_CALL if policy == "risk_ranked" else c.best_action[i]
                        action_used[i] = a  # reserved; resolved after the call
                        env.process(call(i, a))
            queue_series.append(int(sum(len(r.queue) + r.count for r in clinics)))
            yield env.timeout(1)
            day += 1

    for i in range(n):
        env.process(patient(i))
    env.process(controller())
    env.run(until=p.horizon_days + SLA_WINDOW_DAYS + 15)

    res = _metrics(policy, p, c, contacted_at, returned_at, attended_at, cost, nav_busy, contacts, queue_series, time.perf_counter() - t0)
    total_need = sum(need_counts.values()) or 1
    total_contacts = sum(contact_counts.values())
    alloc = {
        g: {"need_share": round(need_counts[g] / total_need, 4), "budget_share": round(contact_counts[g] / total_contacts, 4) if total_contacts else 0.0}
        for g in sorted(set(need_counts) | set(contact_counts))
    }
    res["allocation"] = alloc
    # Allocation gap: the largest shortfall of budget share below need share (0 = no group under-served).
    res["allocation_gap"] = round(max((a["need_share"] - a["budget_share"] for a in alloc.values()), default=0.0), 4) if total_contacts else None
    return res


def choose(policy: str, pool: list[int], budget: int, c: Cohort, eps: float, quota: dict[str, dict[str, float]] | None = None) -> list[int]:
    if not pool or budget <= 0:
        return []
    if policy == "sms_everyone":
        return sorted(pool, key=lambda i: c.arrival[i])[:budget]
    sev = c.df["severity"].to_numpy()
    if policy == "risk_ranked":
        return sorted(pool, key=lambda i: -SEVERITY_WEIGHT[sev[i]] * c.p_dropoff_pred[i])[:budget]
    langs = c.df["preferred_language"].to_numpy()
    ranked = sorted(pool, key=lambda i: (-SEVERITY_WEIGHT[sev[i]] * c.uplift_pred[i], i))
    if policy != "wasl_uplift_fair":
        return ranked[:budget]
    # Fairness floors (spec 7.6) with carry-over: a small group's fractional daily quota
    # accumulates across days instead of being rounded down to zero every day.
    quota = quota if quota is not None else {"ent": {}, "got": {}}
    need: dict[str, float] = defaultdict(float)
    for i in pool:
        if sev[i] in ("high", "urgent"):
            need[str(langs[i])] += 1.0
    total = sum(need.values()) or 1.0
    chosen: list[int] = []
    taken: set[int] = set()
    for g, v in need.items():
        quota["ent"][g] = quota["ent"].get(g, 0.0) + budget * (v / total) * (1 - eps)
        floor = int(math.floor(quota["ent"][g] - quota["got"].get(g, 0.0)))
        for i in [i for i in ranked if langs[i] == g][: max(floor, 0)]:
            if len(chosen) < budget:
                chosen.append(i)
                taken.add(i)
    for i in ranked:
        if len(chosen) >= budget:
            break
        if i not in taken:
            chosen.append(i)
            taken.add(i)
    for i in chosen:
        quota["got"][str(langs[i])] = quota["got"].get(str(langs[i]), 0.0) + 1
    return chosen


def _rate(mask: np.ndarray, closed: np.ndarray) -> float:
    return float(closed[mask].mean()) if mask.sum() else 0.0


def _metrics(policy: str, p: TwinParams, c: Cohort, contacted_at: np.ndarray, returned_at: np.ndarray, attended_at: np.ndarray,
             cost: dict[str, float], nav_busy: float, contacts: int, queue_series: list[int], runtime: float) -> dict[str, Any]:
    df = c.df
    days_to_fu = attended_at - c.arrival
    closed = np.isfinite(days_to_fu) & (days_to_fu <= SLA_WINDOW_DAYS)
    by: dict[str, dict[str, float]] = {}
    for col, key in (("preferred_language", "language"), ("insurance_tier", "insurance_tier"), ("program", "program"), ("nationality_group", "nationality_group")):
        vals = df[col].to_numpy()
        by[key] = {str(g): round(_rate(vals == g, closed), 4) for g in sorted(set(vals))}
    lang_rates = [v for g, v in by["language"].items() if (df["preferred_language"] == g).sum() >= 30]
    n_closed = int(closed.sum())
    outreach_cost = cost["sms"] + cost["call"]
    total = outreach_cost + cost["visit"]
    fu = days_to_fu[closed]
    horizon_total = p.horizon_days + SLA_WINDOW_DAYS
    daily = np.zeros(horizon_total + 1)
    for t in attended_at[closed]:
        daily[min(int(t), horizon_total)] += 1
    cum = np.cumsum(daily)
    step = 5
    return {
        "policy": policy,
        "label": POLICY_LABELS[policy],
        "n": int(len(df)),
        "closure_rate": round(n_closed / max(len(df), 1), 4),
        "closed": n_closed,
        "contacts": int(contacts if policy != "sms_everyone" else int(np.isfinite(contacted_at).sum())),
        "median_days_to_followup": round(float(np.median(fu)), 1) if len(fu) else None,
        "p90_days_to_followup": round(float(np.percentile(fu, 90)), 1) if len(fu) else None,
        "navigator_utilisation": round(nav_busy / max(p.navigators * (p.horizon_days + 30), 1), 4),
        "outreach_cost": round(outreach_cost, 0),
        "total_cost": round(total, 0),
        "cost_per_closed_loop": round(total / max(n_closed, 1), 1),
        "outreach_cost_per_closed_loop": round(outreach_cost / max(n_closed, 1), 2),
        "fairness_gap": round(max(lang_rates) - min(lang_rates), 4) if lang_rates else 0.0,
        "by_group": by,
        "series": {
            "day": list(range(0, horizon_total + 1, step)),
            "cumulative_closed": [int(cum[d]) for d in range(0, horizon_total + 1, step)],
            "clinic_queue": [int(queue_series[min(d, len(queue_series) - 1)]) for d in range(0, horizon_total + 1, step)] if queue_series else [],
        },
        "runtime_s": round(runtime, 2),
        "model_used": c.model_used,
    }


def run_policies(policies: list[str], params: dict[str, Any]) -> dict[str, Any]:
    p = TwinParams.from_dict(params)
    cohort = build_cohort(p)
    results = {pol: simulate(pol, p, cohort) for pol in policies}
    base = results.get("no_outreach") or simulate("no_outreach", p, cohort)
    for r in results.values():
        extra = r["closed"] - base["closed"]
        r["extra_closed_vs_no_outreach"] = int(extra)
        r["incremental_cost_per_extra_loop"] = round(r["outreach_cost"] / extra, 1) if extra > 0 else None
    share = cohort.df["program"].value_counts(normalize=True)
    return {"params": p.__dict__, "results": results, "calibration": calibration(base), "model_used": cohort.model_used,
            "program_share": {str(k): round(float(v), 4) for k, v in share.items()}}


def calibration(base: dict[str, Any]) -> dict[str, Any]:
    """Twin no-outreach closure vs the synthetic historical no-outreach return rate."""
    hist = None
    try:
        from app.ml.registry import load_active

        b = load_active()
        hist = b.metrics["data"]["historical_return_rate_no_outreach"] if b else None
    except Exception:
        hist = None
    sim = base["closure_rate"]
    return {
        "simulated_no_outreach": sim,
        "historical_no_outreach": round(hist, 4) if hist is not None else None,
        "abs_diff": round(abs(sim - hist), 4) if hist is not None else None,
        "statement": (
            f"Twin calibrated: simulated {sim:.1%} vs historical {hist:.1%} (no-outreach closure)"
            if hist is not None else f"Twin no-outreach closure {sim:.1%} (no historical model registered yet)"
        ),
    }


def sensitivity(policies: list[str], params: dict[str, Any], scales: tuple[float, ...] = (0.5, 1.0, 1.5)) -> dict[str, Any]:
    """Re-run each policy with the true outreach effect scaled ×0.5 / ×1.0 / ×1.5."""
    table: dict[str, dict[str, float]] = defaultdict(dict)
    wins: list[bool] = []
    for s in scales:
        out = run_policies(policies, {**params, "effect_scale": s})["results"]
        for pol, r in out.items():
            table[pol][str(s)] = r["closure_rate"]
        wasl = max(out[k]["closure_rate"] for k in ("wasl_uplift", "wasl_uplift_fair") if k in out) if any(k in out for k in ("wasl_uplift", "wasl_uplift_fair")) else 0
        baselines = [out[k]["closure_rate"] for k in ("no_outreach", "sms_everyone", "risk_ranked") if k in out]
        wins.append(bool(baselines) and wasl > max(baselines))
    return {"scales": list(scales), "closure_by_scale": dict(table), "robust": all(wins), "wins": wins}
