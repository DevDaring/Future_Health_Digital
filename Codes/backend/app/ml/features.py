"""Feature construction (spec section 7.1).

One row per care loop. Nationality is deliberately *not* a model feature: it is used
only to audit fairness. Categorical features are one-hot encoded against a fixed
vocabulary, so the column list is identical at train and score time and is saved with
the model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.synth.population import DEFAULT_SMS_LANGS, SEVERITY_LEVEL

VOCAB: dict[str, list[str]] = {
    "preferred_language": ["en", "ar", "hi", "ur", "ml", "bn", "tl"],
    "occupation_type": ["office", "construction", "domestic", "retail", "driver", "healthcare", "hospitality"],
    "shift_pattern": ["day", "night", "rotating", "split"],
    "insurance_tier": ["thiqa", "enhanced", "basic"],
    "preferred_channel": ["whatsapp", "sms", "call", "in_person"],
    "program": ["DIABETES", "COLORECTAL", "BREAST"],
}
ACTION_VOCAB: dict[str, list[str]] = {
    "act_channel": ["sms", "whatsapp", "call", "in_person"],
    "act_slot": ["none", "evening", "friday", "near_home"],
}
NUMERIC = [
    "age",
    "literacy_level",
    "distance_km",
    "prior_no_shows",
    "days_since_result",
    "severity_level",
    "lang_mismatch",
    "has_smartphone",
    "no_free_weekdays",
    "sex_male",
    "weekday_available",
    "weekend_available",
]
ACTION_NUMERIC = ["act_lang_matched", "act_cost_info"]


def base_columns() -> list[str]:
    cols = list(NUMERIC)
    for k, vals in VOCAB.items():
        cols += [f"{k}={v}" for v in vals]
    return cols


def action_columns() -> list[str]:
    cols = list(ACTION_NUMERIC)
    for k, vals in ACTION_VOCAB.items():
        cols += [f"{k}={v}" for v in vals]
    return cols


def _weekday_flags(days: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    wk = np.array([any(d in ("Mon", "Tue", "Wed", "Thu") for d in (x or [])) for x in days], dtype=float)
    we = np.array([any(d in ("Fri", "Sat", "Sun") for d in (x or [])) for x in days], dtype=float)
    return wk, we


def build_features(df: pd.DataFrame, with_actions: bool = False) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["age"] = df["age"].astype(float)
    out["literacy_level"] = df["literacy_level"].astype(float)
    out["distance_km"] = df["distance_km"].astype(float)
    out["prior_no_shows"] = df["prior_no_shows"].astype(float)
    out["days_since_result"] = df.get("days_since_result", pd.Series(0, index=df.index)).astype(float)
    out["severity_level"] = df["severity"].map(SEVERITY_LEVEL).astype(float)
    out["lang_mismatch"] = (~df["preferred_language"].isin(DEFAULT_SMS_LANGS)).astype(float)
    out["has_smartphone"] = df["has_smartphone"].astype(float)
    out["no_free_weekdays"] = df["no_free_weekdays"].astype(float)
    out["sex_male"] = (df["sex"] == "M").astype(float)
    wk, we = _weekday_flags(df["preferred_days"])
    out["weekday_available"] = wk
    out["weekend_available"] = we
    for k, vals in VOCAB.items():
        for v in vals:
            out[f"{k}={v}"] = (df[k] == v).astype(float)
    if with_actions:
        out["act_lang_matched"] = df["act_lang_matched"].astype(float)
        out["act_cost_info"] = df["act_cost_info"].astype(float)
        for k, vals in ACTION_VOCAB.items():
            for v in vals:
                out[f"{k}={v}"] = (df[k] == v).astype(float)
        return out[base_columns() + action_columns()]
    return out[base_columns()]


def with_action(df: pd.DataFrame, channel: str, lang_matched: bool, slot: str, cost_info: bool) -> pd.DataFrame:
    d = df.copy()
    d["act_channel"] = channel
    d["act_lang_matched"] = int(lang_matched)
    d["act_slot"] = slot
    d["act_cost_info"] = int(cost_info)
    return d
