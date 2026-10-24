"""Counterfactual "what would help" (spec section 7.5).

For each loop we score the uplift model under a small set of *actionable* changes only:
contact channel, language-matched outreach, offered slot type, and cost information.
Immutable attributes (age, sex, nationality, ...) are never changed. We return the top 3
packages by predicted return probability, preferring simpler packages when two are
within one percentage point of each other.
"""

from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from app.ml.registry import ModelBundle

LANG_NAMES = {"en": "English", "ar": "Arabic", "hi": "Hindi", "ur": "Urdu", "ml": "Malayalam", "bn": "Bengali", "tl": "Tagalog"}
CHANNEL_LABEL = {"whatsapp": "WhatsApp message", "call": "Phone call", "in_person": "In-person visit", "sms": "SMS"}
SLOT_LABEL = {"evening": "evening slot", "friday": "Friday slot", "near_home": "slot near home", "none": ""}

ACTION_GRID = [
    {"channel": c, "lang_matched": lm, "slot": s, "cost_info": ci}
    for c, lm, s, ci in product(("whatsapp", "call", "in_person"), (True, False), ("none", "evening", "friday", "near_home"), (False, True))
]


def action_complexity(a: dict[str, Any]) -> int:
    return int(a["slot"] != "none") + int(a["cost_info"]) + int(a["channel"] == "in_person") + int(not a["lang_matched"])


def describe(a: dict[str, Any], lang: str) -> list[str]:
    parts = [CHANNEL_LABEL[a["channel"]] + (f" in {LANG_NAMES.get(lang, lang)}" if a["lang_matched"] else " in English/Arabic")]
    if a["slot"] != "none":
        parts.append(f"Offer {SLOT_LABEL[a['slot']]}")
    if a["cost_info"]:
        parts.append("Send cost information")
    return parts


def action_matrix(bundle: ModelBundle, df: pd.DataFrame) -> np.ndarray:
    """P(return) for every row × every action in ACTION_GRID, shape (n, len(grid))."""
    return np.column_stack([bundle.p_return_with(df, **a) for a in ACTION_GRID])


def top_counterfactuals(
    bundle: ModelBundle, df: pd.DataFrame, k: int = 3, p_matrix: np.ndarray | None = None, p0: np.ndarray | None = None
) -> list[list[dict[str, Any]]]:
    P = action_matrix(bundle, df) if p_matrix is None else p_matrix
    base = bundle.p_return_no(df) if p0 is None else p0
    complexity = np.array([action_complexity(a) for a in ACTION_GRID])
    out: list[list[dict[str, Any]]] = []
    langs = df["preferred_language"].tolist()
    for i in range(len(df)):
        # sort by probability rounded to 1 pp (desc), then simpler first
        order = sorted(range(len(ACTION_GRID)), key=lambda j: (-round(float(P[i, j]), 2), complexity[j]))
        row = []
        for j in order[:k]:
            a = ACTION_GRID[j]
            row.append(
                {
                    "actions": describe(a, langs[i]),
                    "action": a,
                    "p_return": round(float(P[i, j]), 3),
                    "p_baseline": round(float(base[i]), 3),
                    "delta": round(float(P[i, j] - base[i]), 3),
                }
            )
        out.append(row)
    return out
