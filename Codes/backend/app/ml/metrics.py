"""Evaluation metrics written by hand where the spec asks (Qini / AUUC), so the maths is
visible to reviewers.

Qini curve (randomised data): sort by score, and at each cut-off k
    Q(k) = Y_t(k) − Y_c(k) · N_t(k) / N_c(k)
i.e. extra positive outcomes among the top-k treated, versus what the top-k controls
predict. AUUC here is the mean of the normalised curve over k (0..1 of the population),
minus the random-targeting diagonal, so random ≈ 0 and higher is better.

Because the data are synthetic, we also know each person's *true* uplift; the
"true-gain" curve ranks people by score and sums their true uplift. That gives an
honest check that the model ranks the right people first.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def qini_curve(score: np.ndarray, treated: np.ndarray, y: np.ndarray, points: int = 50) -> dict[str, list[float]]:
    order = np.argsort(-score, kind="stable")
    t = treated[order].astype(float)
    yy = y[order].astype(float)
    n = len(score)
    cum_t = np.cumsum(t)
    cum_c = np.cumsum(1 - t)
    cum_yt = np.cumsum(yy * t)
    cum_yc = np.cumsum(yy * (1 - t))
    with np.errstate(divide="ignore", invalid="ignore"):
        q = cum_yt - np.where(cum_c > 0, cum_yc * cum_t / cum_c, 0.0)
    idx = np.unique(np.linspace(0, n - 1, points).astype(int))
    total = q[-1] if q[-1] != 0 else 1.0
    return {"frac": [float((i + 1) / n) for i in idx], "qini": [float(q[i] / abs(total)) for i in idx]}


def auuc_from_curve(curve: dict[str, list[float]]) -> float:
    frac = np.array([0.0] + curve["frac"])
    q = np.array([0.0] + curve["qini"])
    area = float(np.trapezoid(q, frac)) if hasattr(np, "trapezoid") else float(np.trapz(q, frac))
    return area - 0.5  # subtract random-targeting diagonal (area 0.5 when normalised to end at 1)


def true_gain_curve(score: np.ndarray, tau_true: np.ndarray, points: int = 50) -> dict[str, list[float]]:
    order = np.argsort(-score, kind="stable")
    g = np.cumsum(tau_true[order])
    n = len(score)
    idx = np.unique(np.linspace(0, n - 1, points).astype(int))
    total = g[-1] if g[-1] != 0 else 1.0
    return {"frac": [float((i + 1) / n) for i in idx], "gain": [float(g[i] / total) for i in idx]}


def true_auuc(score: np.ndarray, tau_true: np.ndarray) -> float:
    c = true_gain_curve(score, tau_true, points=200)
    return auuc_from_curve({"frac": c["frac"], "qini": c["gain"]})


def calibration_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict[str, float]]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() == 0:
            continue
        out.append({"bin": float((lo + hi) / 2), "pred": float(p[m].mean()), "obs": float(y[m].mean()), "n": int(m.sum())})
    return out


def classification_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    if len(np.unique(y)) < 2:
        return {"auroc": None, "auprc": None, "brier": float(brier_score_loss(y, p)), "n": int(len(y))}
    return {
        "auroc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "n": int(len(y)),
        "base_rate": float(np.mean(y)),
    }


def group_metrics(y: np.ndarray, p: np.ndarray, groups: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for g in sorted(set(groups.tolist())):
        m = groups == g
        if m.sum() < 20:
            continue
        met = classification_metrics(y[m], p[m])
        pos = y[m] == 1
        met["tpr_high_risk"] = float(((p[m] >= threshold) & pos).sum() / max(pos.sum(), 1))
        out[str(g)] = met
    return out
