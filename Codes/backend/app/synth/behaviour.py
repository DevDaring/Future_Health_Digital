"""Ground-truth behaviour model (hidden from the ML models).

It creates training labels and drives the digital twin. Coefficients live in
`config.yaml` (ILLUSTRATIVE). The treatment effect is heterogeneous on purpose:
outreach helps most when it removes the person's actual barrier (language, shift,
distance, cost), and helps little for people who would return anyway or whose cost
barrier is not addressed.

An *action* is the outreach package: channel, language-matched or not, offered slot
type, and whether cost information is sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.synth.population import DEFAULT_SMS_LANGS, SEVERITY_LEVEL, load_config

CHANNELS = ("sms", "whatsapp", "call", "in_person")
SLOTS = ("none", "evening", "friday", "near_home")


@dataclass(frozen=True)
class Action:
    channel: str = "call"
    lang_matched: bool = True
    slot: str = "none"
    cost_info: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "lang_matched": self.lang_matched, "slot": self.slot, "cost_info": self.cost_info}


NO_ACTION = None
SMS_DEFAULT = Action(channel="sms", lang_matched=False, slot="none", cost_info=False)
STANDARD_CALL = Action(channel="call", lang_matched=True, slot="none", cost_info=False)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _flags(df: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        "mismatch": (~df["preferred_language"].isin(DEFAULT_SMS_LANGS)).to_numpy(dtype=float),
        "nightish": df["shift_pattern"].isin(["night", "rotating"]).to_numpy(dtype=float),
        "basic": (df["insurance_tier"] == "basic").to_numpy(dtype=float),
        "lowlit": (df["literacy_level"] == 1).to_numpy(dtype=float),
        "nofree": df["no_free_weekdays"].astype(bool).to_numpy(dtype=float),
        "far": (df["distance_km"] > 15).to_numpy(dtype=float),
        "very_far": (df["distance_km"] > 30).to_numpy(dtype=float),
        "smartphone": df["has_smartphone"].astype(bool).to_numpy(dtype=float),
    }


def baseline_logit(df: pd.DataFrame) -> np.ndarray:
    """logit P(return within SLA | no outreach)."""
    b = load_config()["behaviour"]
    f = _flags(df)
    sev = df["severity"].map(SEVERITY_LEVEL).to_numpy(dtype=float) if "severity" in df else 0.0
    days = df["days_since_result"].to_numpy(dtype=float) if "days_since_result" in df else 0.0
    return (
        b["b0"]
        - b["a1_lang_mismatch"] * f["mismatch"]
        - b["a2_night_or_rotating"] * f["nightish"]
        - b["a3_distance_per_10km"] * df["distance_km"].to_numpy(dtype=float) / 10.0
        - b["a4_prior_no_show"] * df["prior_no_shows"].to_numpy(dtype=float)
        - b["a5_basic_insurance"] * f["basic"]
        + b["a6_severity_level"] * sev
        - b["a7_low_literacy"] * f["lowlit"]
        - b["a8_no_free_weekdays"] * f["nofree"]
        - b["days_since_result_decay"] * days
    )


def effect_logit(
    df: pd.DataFrame,
    channel: np.ndarray | str,
    lang_matched: np.ndarray | bool,
    slot: np.ndarray | str,
    cost_info: np.ndarray | bool,
    lang_capacity: np.ndarray | float = 1.0,
    slot_availability: np.ndarray | float = 1.0,
) -> np.ndarray:
    """Treatment effect on the logit scale for given actions (scalars or per-row arrays).

    `lang_capacity` < 1 models language-matched outreach delivered through an interpreter
    line instead of a native-speaking navigator (used by the twin). `slot_availability`
    < 1 models fewer evening/Friday sessions than needed.
    """
    b = load_config()["behaviour"]
    f = _flags(df)
    n = len(df)
    ch = np.broadcast_to(np.asarray(channel, dtype=object), (n,))
    lm = np.broadcast_to(np.asarray(lang_matched, dtype=float), (n,))
    sl = np.broadcast_to(np.asarray(slot, dtype=object), (n,))
    ci = np.broadcast_to(np.asarray(cost_info, dtype=float), (n,))
    is_sms = (ch == "sms").astype(float)
    personal = 1.0 - is_sms
    shift_slot = np.isin(sl, ["evening", "friday"]).astype(float) * slot_availability
    friday = (sl == "friday").astype(float) * slot_availability
    near = (sl == "near_home").astype(float)
    call_like = np.isin(ch, ["call", "in_person"]).astype(float)
    whatsapp = (ch == "whatsapp").astype(float)

    tau = (
        b["e_sms"] * is_sms
        + b["e_base"] * personal
        + b["e_lang_match"] * f["mismatch"] * lm * lang_capacity
        + b["e_shift_slot"] * f["nightish"] * shift_slot
        + b["e_friday_no_free_weekdays"] * f["nofree"] * friday
        + b["e_near_home"] * f["far"] * near
        + b["e_cost_info"] * f["basic"] * ci
        + b["e_call_low_literacy"] * f["lowlit"] * call_like
        + b["e_channel_other"] * (1 - f["lowlit"]) * (call_like + whatsapp * f["smartphone"])
    )
    # Wrong-language messages are mostly not understood.
    damp_lang = np.where((f["mismatch"] > 0) & (lm < 0.5), b["unmatched_language_damp"], 1.0)
    # Very high cost barrier that is not addressed: outreach barely moves the needle.
    damp_cost = np.where((f["basic"] > 0) & (f["very_far"] > 0) & (ci < 0.5), b["high_cost_barrier_damp"], 1.0)
    # Chronic non-attenders: a single contact rarely changes long-standing behaviour.
    chronic = df["prior_no_shows"].to_numpy(dtype=float) >= b["chronic_no_show_threshold"]
    damp_chronic = np.where(chronic, b["chronic_no_show_damp"], 1.0)
    return tau * damp_lang * damp_cost * damp_chronic


def p_return(df: pd.DataFrame, action: Action | None, **kw: Any) -> np.ndarray:
    base = baseline_logit(df)
    if action is None:
        return sigmoid(base)
    return sigmoid(base + effect_logit(df, action.channel, action.lang_matched, action.slot, action.cost_info, **kw))


def best_true_action(df: pd.DataFrame) -> list[Action]:
    """Oracle best action per row (used only for evaluation, never by the product)."""
    best_p = np.full(len(df), -1.0)
    best: list[Action] = [STANDARD_CALL] * len(df)
    for a in all_actions():
        p = p_return(df, a)
        better = p > best_p
        best_p = np.where(better, p, best_p)
        for i in np.flatnonzero(better):
            best[i] = a
    return best


def all_actions() -> list[Action]:
    return [
        Action(channel=c, lang_matched=lm, slot=s, cost_info=ci)
        for c in CHANNELS
        for lm in (True, False)
        for s in SLOTS
        for ci in (False, True)
    ]


def simulate_history(seed: int = 42, n: int | None = None) -> pd.DataFrame:
    """Simulated historical randomised outreach trial (spec section 6).

    50% of past loops got outreach with a *random* action package, so the uplift model
    can learn which actions help whom, and because the true effect is known here,
    Qini/AUUC can be evaluated honestly against ground truth.
    """
    from app.synth.population import draw_abnormal_results, generate_population

    cfg = load_config()
    n = n or cfg["history"]["n_loops"]
    rng = np.random.default_rng(seed + 1000)
    pop = generate_population(int(n * 3.3), seed=seed + 1000)
    results = draw_abnormal_results(pop, rng)
    res = pd.DataFrame(results).drop_duplicates("idx").head(n)
    df = res.merge(pop, on="idx", how="left").reset_index(drop=True)
    df["days_since_result"] = rng.integers(0, 15, len(df))
    treated = rng.random(len(df)) < cfg["history"]["treat_share"]
    df["treated"] = treated.astype(int)
    df["act_channel"] = np.where(treated, rng.choice(CHANNELS, len(df)), "none")
    df["act_lang_matched"] = np.where(treated, rng.random(len(df)) < 0.6, False).astype(int)
    df["act_slot"] = np.where(treated, rng.choice(SLOTS, len(df)), "none")
    df["act_cost_info"] = np.where(treated, rng.random(len(df)) < 0.5, False).astype(int)

    base = baseline_logit(df)
    eff = effect_logit(df, df["act_channel"].to_numpy(), df["act_lang_matched"].to_numpy(), df["act_slot"].to_numpy(), df["act_cost_info"].to_numpy())
    eff = np.where(treated, eff, 0.0)
    p0 = sigmoid(base)
    p_obs = sigmoid(base + eff)
    df["p0_true"] = p0
    df["p_obs_true"] = p_obs
    # True uplift of the *standard* WASL contact (language-matched call), for evaluation.
    df["tau_true_standard"] = p_return(df, STANDARD_CALL) - p0
    df["returned"] = (rng.random(len(df)) < p_obs).astype(int)
    split_u = rng.random(len(df))
    df["split"] = np.where(split_u < 0.6, "train", np.where(split_u < 0.8, "val", "test"))
    return df
