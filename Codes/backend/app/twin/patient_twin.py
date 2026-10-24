"""Patient twin (clinician/coordinator only, spec section 10.2).

A per-program Markov chain projects the probability of progressing to the program's
outcome state over 5 years if follow-up happens now, or is delayed 3 / 6 / 12 months.
While follow-up is delayed the `untreated` yearly rates apply; afterwards `in_care`
rates apply. Yearly probabilities are converted to monthly ones
(p_month = 1 − (1 − p_year)^(1/12)).

Uncertainty band: every rate is resampled uniformly within ±`range` and the projection
recomputed (400 draws, seeded); we report the 5th–95th percentile.

ILLUSTRATIVE, NOT FOR CLINICAL DECISIONS. Never shown to patients (RBAC-enforced).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

DELAYS = (0, 3, 6, 12)


@lru_cache
def markov_config() -> dict[str, Any]:
    return yaml.safe_load(Path(__file__).with_name("markov.yaml").read_text())


def _monthly_matrix(states: list[str], rates: dict[str, float]) -> np.ndarray:
    k = len(states)
    m = np.eye(k)
    for edge, p_year in rates.items():
        a, b = edge.split("->")
        i, j = states.index(a), states.index(b)
        p_m = 1 - (1 - min(max(p_year, 0.0), 0.999)) ** (1 / 12)
        m[i, j] += p_m
        m[i, i] -= p_m
    return m


def project(program: str, category: str, delay_months: int, rates_untreated: dict[str, float], rates_care: dict[str, float],
            horizon: int) -> np.ndarray:
    cfg = markov_config()[program]
    states = cfg["states"]
    start = np.array(cfg["start"].get(category) or next(iter(cfg["start"].values())), dtype=float)
    mu = _monthly_matrix(states, rates_untreated)
    mc = _monthly_matrix(states, rates_care)
    out_idx = states.index(cfg["outcome"])
    x = start.copy()
    traj = [x[out_idx]]
    for month in range(1, horizon + 1):
        x = x @ (mu if month <= delay_months else mc)
        traj.append(x[out_idx])
    return np.array(traj)


def patient_twin(program: str, category: str, draws: int = 400, seed: int = 7) -> dict[str, Any]:
    root = markov_config()
    cfg = root[program]
    horizon = int(root["horizon_months"])
    rng = np.random.default_rng(seed)
    spread = float(root["range"])
    results = []
    for delay in DELAYS:
        point = project(program, category, delay, cfg["untreated"], cfg["in_care"], horizon)
        samples = []
        for _ in range(draws):
            ru = {k: v * rng.uniform(1 - spread, 1 + spread) for k, v in cfg["untreated"].items()}
            rc = {k: v * rng.uniform(1 - spread, 1 + spread) for k, v in cfg["in_care"].items()}
            samples.append(project(program, category, delay, ru, rc, horizon))
        s = np.array(samples)
        step = 3
        results.append(
            {
                "delay_months": delay,
                "p_outcome_5y": round(float(point[-1]), 4),
                "lo": round(float(np.percentile(s[:, -1], 5)), 4),
                "hi": round(float(np.percentile(s[:, -1], 95)), 4),
                "trajectory": {
                    "month": list(range(0, horizon + 1, step)),
                    "p": [round(float(v), 4) for v in point[::step]],
                    "lo": [round(float(v), 4) for v in np.percentile(s, 5, axis=0)[::step]],
                    "hi": [round(float(v), 4) for v in np.percentile(s, 95, axis=0)[::step]],
                },
            }
        )
    base = results[0]["p_outcome_5y"]
    for r in results:
        r["excess_vs_now"] = round(r["p_outcome_5y"] - base, 4)
    return {
        "program": program,
        "category": category,
        "outcome_label": cfg["outcome_label"],
        "horizon_months": horizon,
        "delays": results,
        "label": "ILLUSTRATIVE — not for clinical decisions",
    }
