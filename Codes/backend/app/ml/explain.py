"""SHAP explanations of the drop-off risk model (spec section 7.4).

Uses `shap.TreeExplainer` on the LightGBM risk model. If the shap package is not
importable we fall back to LightGBM's built-in TreeSHAP (`pred_contrib=True`), which
computes the same exact Shapley values for tree ensembles.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from app.ml.features import NUMERIC


@lru_cache
def feature_labels() -> dict[str, str]:
    with (Path(__file__).with_name("feature_labels.yaml")).open() as fh:
        return yaml.safe_load(fh)


def shap_values(model: Any, X: pd.DataFrame) -> np.ndarray:
    try:
        import shap

        explainer = shap.TreeExplainer(model)
        vals = explainer.shap_values(X)
        if isinstance(vals, list):  # older shap: one array per class
            vals = vals[1]
        vals = np.asarray(vals)
        if vals.ndim == 3:
            vals = vals[:, :, 1]
        return vals
    except Exception:  # pragma: no cover - fallback path
        contrib = model.booster_.predict(X, pred_contrib=True)
        return np.asarray(contrib)[:, :-1]


SEVERITY_WORDS = {0: "Routine result", 1: "High-severity result", 2: "Urgent result"}


def _format_value(col: str, v: float) -> str:
    if col in {"distance_km"}:
        return f"{v:.0f}"
    if col in {"age", "prior_no_shows", "days_since_result", "literacy_level", "severity_level"}:
        return f"{int(round(v))}"
    return f"{v:g}"


def top_reasons(X: pd.DataFrame, values: np.ndarray, k: int = 5) -> list[list[dict[str, Any]]]:
    """Top-k contributions per row, labelled in plain English. Positive = raises risk."""
    labels = feature_labels()
    cols = list(X.columns)
    out: list[list[dict[str, Any]]] = []
    Xv = X.to_numpy()
    for i in range(len(X)):
        cand = []
        for j, col in enumerate(cols):
            v = Xv[i, j]
            is_binary = col not in NUMERIC or col in {"lang_mismatch", "has_smartphone", "no_free_weekdays", "sex_male", "weekday_available", "weekend_available"}
            if is_binary and v < 0.5:
                continue  # explain what *is* true about the person, not absences
            cand.append((abs(values[i, j]), j))
        cand.sort(reverse=True)
        row = []
        for _, j in cand[:k]:
            col = cols[j]
            if col == "severity_level":
                label = SEVERITY_WORDS.get(int(round(Xv[i, j])), "Result severity")
            else:
                label = labels.get(col, col).replace("{v}", _format_value(col, float(Xv[i, j])))
            row.append({"feature": col, "label": label, "value": float(Xv[i, j]), "shap": float(values[i, j])})
        out.append(row)
    return out
