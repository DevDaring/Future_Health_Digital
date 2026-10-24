"""Model bundle persistence. One pickle holds the risk model + calibrator and the two
T-learner models, plus the exact feature lists they were trained on."""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.config import get_settings
from app.ml.features import build_features, with_action


@dataclass
class ModelBundle:
    version: str
    risk_model: Any  # lightgbm.LGBMClassifier (target = did NOT return within SLA)
    risk_calibrator: Any  # isotonic calibrator over raw risk scores
    m0: Any  # P(return | no outreach)
    m1: Any  # P(return | outreach, action)
    base_cols: list[str]
    action_cols: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)

    def p_dropoff(self, df: pd.DataFrame) -> np.ndarray:
        X = build_features(df)
        raw = self.risk_model.predict_proba(X[self.base_cols])[:, 1]
        return np.clip(self.risk_calibrator.predict(raw), 0.001, 0.999)

    def p_return_no(self, df: pd.DataFrame) -> np.ndarray:
        X = build_features(df)
        return self.m0.predict_proba(X[self.base_cols])[:, 1]

    def p_return_with(self, df: pd.DataFrame, channel: str, lang_matched: bool, slot: str, cost_info: bool) -> np.ndarray:
        X = build_features(with_action(df, channel, lang_matched, slot, cost_info), with_actions=True)
        return self.m1.predict_proba(X[self.base_cols + self.action_cols])[:, 1]


def artifact_path(version: str) -> Path:
    return Path(get_settings().artifacts_dir) / f"wasl_models_{version}.pkl"


def save_bundle(bundle: ModelBundle) -> Path:
    path = artifact_path(bundle.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(bundle, fh)
    (path.parent / "ACTIVE").write_text(bundle.version)
    load_active.cache_clear()
    return path


@lru_cache
def load_active() -> ModelBundle | None:
    marker = Path(get_settings().artifacts_dir) / "ACTIVE"
    if not marker.exists():
        return None
    path = artifact_path(marker.read_text().strip())
    if not path.exists():
        return None
    with path.open("rb") as fh:
        return pickle.load(fh)  # noqa: S301 - our own artifact
