"""Pure-Python synthetic population and screening-result generator (spec section 6).

`generate_population(n, seed)` returns a DataFrame of patients whose distributions are
set in `config.yaml` (ILLUSTRATIVE). Every random draw goes through one
`numpy.random.Generator` seeded by the caller, so the same seed gives the same data.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")

SOUTH_ASIAN = {"Indian", "Pakistani", "Bangladeshi"}
DEFAULT_SMS_LANGS = {"en", "ar"}  # the standard notification SMS is bilingual en/ar
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@lru_cache
def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


_CUM_CACHE: dict[tuple[tuple[str, float], ...], tuple[list[str], list[float]]] = {}


def _choice(rng: np.random.Generator, dist: dict[str, float]) -> str:
    """Draw one key with probability proportional to its weight (one uniform per draw,
    cached cumulative table: ~10x faster than rng.choice for small dicts)."""
    sig = tuple(dist.items())
    if sig not in _CUM_CACHE:
        keys = list(dist.keys())
        total = float(sum(dist.values()))
        cum, acc = [], 0.0
        for k in keys:
            acc += dist[k] / total
            cum.append(acc)
        _CUM_CACHE[sig] = (keys, cum)
    keys, cum = _CUM_CACHE[sig]
    u = rng.random()
    for k, c in zip(keys, cum, strict=True):
        if u < c:
            return k
    return keys[-1]


def _preferred_days(shift: str, no_free_weekdays: bool, rng: np.random.Generator) -> list[str]:
    if no_free_weekdays:
        return ["Fri"] if rng.random() < 0.7 else ["Sun"]
    if shift in {"night", "rotating"}:
        return ["Fri", "Sat"]
    if shift == "split":
        return ["Sat", "Sun"]
    return ["Mon", "Tue", "Wed", "Thu"]


def generate_population(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    cfg = load_config()
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        nat = str(_choice(rng, cfg["nationality_groups"]))
        lang = str(_choice(rng, cfg["language_by_nationality"][nat]))
        occ = str(_choice(rng, cfg["occupation_by_nationality"][nat]))
        shift = str(_choice(rng, cfg["shift_by_occupation"][occ]))
        male = rng.random() < cfg["male_share_by_occupation"][occ]
        sex = "M" if male else "F"
        young = occ in {"construction", "domestic", "hospitality", "driver"}
        age = int(np.clip(rng.normal(37 if young else 46, 9 if young else 11), 22, 78))
        if nat == "Emirati":
            insurance = "thiqa"
        else:
            insurance = "basic" if rng.random() < cfg["basic_insurance_by_occupation"][occ] else "enhanced"
        p1, p2 = cfg["low_literacy_by_occupation"][occ]
        u = rng.random()
        literacy = 1 if u < p1 else (2 if u < p1 + p2 else 3)
        area = cfg["home_areas"][int(rng.integers(len(cfg["home_areas"])))]
        far = area in cfg["far_areas"] or occ == "construction"
        distance = float(np.round(np.clip(rng.lognormal(np.log(20 if far else 7), 0.45), 1.0, 60.0), 1))
        nightish = shift in {"night", "rotating"}
        prior_no_shows = int(min(rng.poisson(0.35 + 0.5 * nightish + 0.2 * (literacy == 1)), 4))
        smartphone = bool(rng.random() < (0.75 if literacy == 1 else 0.95))
        channel_dist = (
            {"call": 0.45, "whatsapp": 0.25, "in_person": 0.15, "sms": 0.15}
            if literacy == 1
            else {"whatsapp": 0.55, "call": 0.2, "sms": 0.17, "in_person": 0.08}
        )
        channel = str(_choice(rng, channel_dist))
        if not smartphone and channel == "whatsapp":
            channel = "sms"
        no_free_weekdays = bool(occ == "domestic" and rng.random() < 0.8)
        rows.append(
            {
                "idx": i,
                "age": age,
                "sex": sex,
                "nationality_group": nat,
                "preferred_language": lang,
                "literacy_level": literacy,
                "occupation_type": occ,
                "shift_pattern": shift,
                "preferred_days": _preferred_days(shift, no_free_weekdays, rng),
                "home_area": area,
                "distance_km": distance,
                "insurance_tier": insurance,
                "prior_no_shows": prior_no_shows,
                "has_smartphone": smartphone,
                "preferred_channel": channel,
                "no_free_weekdays": no_free_weekdays,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Screening results
# ---------------------------------------------------------------------------

def classify(program: str, value_numeric: float | None, value_text: str | None) -> tuple[str, str] | None:
    """Apply `fixtures/screening_rules.yaml` thresholds. Returns (severity, category) or
    None when the result is normal."""
    from app.synth.rules import screening_rules

    rules = screening_rules()[program]
    if program == "DIABETES" and value_numeric is not None:
        for band in rules["bands"]:
            if band["min"] <= value_numeric < band.get("max", 99):
                return band["severity"], band["category"]
        return None
    if program == "COLORECTAL":
        return (rules["positive"]["severity"], "positive") if (value_text or "").lower() == "positive" else None
    if program == "BREAST" and value_numeric is not None:
        entry = rules["birads"].get(int(value_numeric))
        return (entry["severity"], entry["category"]) if entry else None
    return None


def draw_abnormal_results(pop: pd.DataFrame, rng: np.random.Generator) -> list[dict[str, Any]]:
    """Draw abnormal screening results for a population (about 30% get one or more)."""
    cfg = load_config()["abnormal"]
    out: list[dict[str, Any]] = []
    for row in pop.itertuples(index=False):
        p_dm = (
            cfg["diabetes_rate_base"]
            + cfg["diabetes_rate_south_asian"] * (row.nationality_group in SOUTH_ASIAN)
            + cfg["diabetes_rate_age_per_decade"] * max(0.0, (row.age - 35) / 10)
        )
        if rng.random() < p_dm:
            u = rng.random()
            value = (
                round(float(rng.uniform(5.7, 6.45)), 1)
                if u < 0.68
                else round(float(rng.uniform(6.5, 8.95)), 1)
                if u < 0.94
                else round(float(rng.uniform(9.0, 12.5)), 1)
            )
            out.append({"idx": row.idx, "program": "DIABETES", "test_code": "HBA1C", "value_numeric": value, "value_text": None})
        if row.age >= 45 and rng.random() < cfg["fit_positive_rate"]:
            out.append({"idx": row.idx, "program": "COLORECTAL", "test_code": "FIT", "value_numeric": None, "value_text": "positive"})
        if row.sex == "F" and row.age >= 40 and rng.random() < cfg["breast_abnormal_rate"]:
            u = rng.random()
            birads = 0 if u < 0.7 else (4 if u < 0.95 else 5)
            out.append({"idx": row.idx, "program": "BREAST", "test_code": "BIRADS", "value_numeric": float(birads), "value_text": f"BI-RADS {birads}"})
    for r in out:
        sev_cat = classify(r["program"], r["value_numeric"], r["value_text"])
        assert sev_cat is not None
        r["severity"], r["category"] = sev_cat
    return out


SEVERITY_LEVEL = {"routine": 0, "high": 1, "urgent": 2}
