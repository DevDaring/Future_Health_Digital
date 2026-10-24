"""Training pipeline (spec section 7.7).

    python -m app.ml.train --seed 42

1. Simulate the historical randomised outreach trial (synthetic, seeded).
2. Drop-off risk model: LightGBM on the no-outreach arm (target = did NOT return within
   SLA), isotonic-calibrated on the validation split. (Isotonic regression on the frozen
   model's validation scores is exactly sklearn's prefit isotonic calibration.)
3. T-learner uplift: m0 on no-outreach loops, m1 on outreach loops with the action
   package as extra features.
4. Evaluate on the test split: AUROC/AUPRC/Brier/calibration overall and per language
   group and insurance tier; Qini/AUUC for uplift vs risk vs random, both on observed
   outcomes and on the known true effect.
5. Save artifacts, register versions, score all open loops, write the model card.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from app.ml import metrics as M
from app.ml.features import action_columns, base_columns, build_features
from app.ml.registry import ModelBundle, save_bundle
from app.synth.behaviour import STANDARD_CALL, simulate_history

log = logging.getLogger("wasl.train")


def _lgbm(seed: int) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        # Strong regularisation: the T-learner subtracts two models, so variance in
        # either one becomes noise in the uplift. Shallow trees ranked true uplift best.
        n_estimators=500,
        learning_rate=0.03,
        num_leaves=8,
        min_child_samples=150,
        subsample=0.85,
        subsample_freq=1,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        random_state=seed,
        deterministic=True,
        force_row_wise=True,
        n_jobs=2,
        verbose=-1,
    )


def train_all(seed: int = 42) -> tuple[ModelBundle, pd.DataFrame]:
    hist = simulate_history(seed)
    tr, va, te = (hist[hist.split == s] for s in ("train", "val", "test"))
    cols = base_columns()
    acols = action_columns()

    # --- risk model (no-outreach arm = natural course) ---------------------------------
    ctrl_tr, ctrl_va, ctrl_te = (d[d.treated == 0] for d in (tr, va, te))
    risk = _lgbm(seed)
    risk.fit(build_features(ctrl_tr)[cols], 1 - ctrl_tr["returned"])
    raw_va = risk.predict_proba(build_features(ctrl_va)[cols])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(raw_va, 1 - ctrl_va["returned"].to_numpy())

    # --- T-learner ----------------------------------------------------------------------
    trt_tr = tr[tr.treated == 1]
    m0 = _lgbm(seed + 1)
    m0.fit(build_features(ctrl_tr)[cols], ctrl_tr["returned"])
    m1 = _lgbm(seed + 2)
    m1.fit(build_features(trt_tr, with_actions=True)[cols + acols], trt_tr["returned"])

    version = f"v{datetime.now(UTC).strftime('%Y%m%d')}-s{seed}-" + hashlib.sha1(
        json.dumps([len(hist), float(hist.returned.mean())]).encode()
    ).hexdigest()[:6]
    bundle = ModelBundle(version=version, risk_model=risk, risk_calibrator=iso, m0=m0, m1=m1, base_cols=cols, action_cols=acols)

    # --- evaluation -----------------------------------------------------------------------
    y_drop = 1 - ctrl_te["returned"].to_numpy()
    p_drop = bundle.p_dropoff(ctrl_te)
    risk_metrics = M.classification_metrics(y_drop, p_drop)
    risk_metrics["calibration"] = M.calibration_bins(y_drop, p_drop)
    risk_metrics["by_language"] = M.group_metrics(y_drop, p_drop, ctrl_te["preferred_language"].to_numpy())
    risk_metrics["by_insurance_tier"] = M.group_metrics(y_drop, p_drop, ctrl_te["insurance_tier"].to_numpy())
    risk_metrics["by_nationality_group"] = M.group_metrics(y_drop, p_drop, ctrl_te["nationality_group"].to_numpy())
    risk_metrics["by_sex"] = M.group_metrics(y_drop, p_drop, ctrl_te["sex"].to_numpy())

    uplift_std = bundle.p_return_with(te, **STANDARD_CALL.as_dict()) - bundle.p_return_no(te)
    risk_score = bundle.p_dropoff(te)
    rng = np.random.default_rng(seed + 7)
    rand_score = rng.random(len(te))
    t = te["treated"].to_numpy()
    y = te["returned"].to_numpy()
    tau = te["tau_true_standard"].to_numpy()
    # Observed Qini: the trial's treated arm got *random* action packages, so score each
    # person by the uplift expected under that same package mix (the matching estimand).
    uplift_trial = _expected_trial_uplift(bundle, te)
    curves = {name: M.qini_curve(s, t, y) for name, s in (("uplift", uplift_trial), ("risk", risk_score), ("random", rand_score))}
    true_curves = {name: M.true_gain_curve(s, tau) for name, s in (("uplift", uplift_std), ("risk", risk_score), ("random", rand_score))}
    uplift_metrics = {
        "qini_auuc_observed": {k: M.auuc_from_curve(v) for k, v in curves.items()},
        "auuc_true": {k: M.true_auuc(s, tau) for k, s in (("uplift", uplift_std), ("risk", risk_score), ("random", rand_score))},
        "qini_curves": curves,
        "true_gain_curves": true_curves,
        "corr_with_true_tau": float(np.corrcoef(uplift_std, tau)[0, 1]),
        "mean_true_tau": float(tau.mean()),
        "mean_pred_tau": float(uplift_std.mean()),
        "n_test": int(len(te)),
    }
    m0_metrics = M.classification_metrics(ctrl_te["returned"].to_numpy(), bundle.p_return_no(ctrl_te))
    trt_te = te[te.treated == 1]
    p1_te = m1.predict_proba(build_features(trt_te, with_actions=True)[cols + acols])[:, 1]
    m1_metrics = M.classification_metrics(trt_te["returned"].to_numpy(), p1_te)

    bundle.metrics = {
        "risk": risk_metrics,
        "uplift": uplift_metrics,
        "uplift_t0": m0_metrics,
        "uplift_t1": m1_metrics,
        "data": {
            "n_history": int(len(hist)),
            "n_train": int(len(tr)),
            "n_val": int(len(va)),
            "n_test": int(len(te)),
            "historical_return_rate_no_outreach": float(hist[hist.treated == 0].returned.mean()),
            "historical_return_rate_outreach": float(hist[hist.treated == 1].returned.mean()),
            "seed": seed,
        },
        "feature_importance": _importance(risk, cols),
    }
    return bundle, hist


def _expected_trial_uplift(bundle: ModelBundle, df: pd.DataFrame) -> np.ndarray:
    from itertools import product

    from app.synth.behaviour import CHANNELS, SLOTS

    total = np.zeros(len(df))
    weight_sum = 0.0
    for ch, lm, sl, ci in product(CHANNELS, (True, False), SLOTS, (True, False)):
        w = (0.6 if lm else 0.4) * 0.5
        total += w * bundle.p_return_with(df, ch, lm, sl, ci)
        weight_sum += w
    return total / weight_sum - bundle.p_return_no(df)


def _importance(model: Any, cols: list[str]) -> list[dict[str, Any]]:
    imp = model.booster_.feature_importance(importance_type="gain")
    order = np.argsort(-imp)[:15]
    total = float(imp.sum()) or 1.0
    return [{"feature": cols[i], "gain_share": float(imp[i] / total)} for i in order]


def register(db: Any, bundle: ModelBundle) -> None:
    from sqlalchemy import update

    from app.models import ModelRegistry

    now = datetime.now(UTC)
    path = str(save_bundle(bundle))
    db.execute(update(ModelRegistry).values(is_active=False))
    risk = bundle.metrics["risk"]
    fairness = {k: risk[k] for k in ("by_language", "by_insurance_tier", "by_nationality_group", "by_sex")}
    db.add(ModelRegistry(name="risk", version=bundle.version, metrics={k: v for k, v in risk.items() if not k.startswith("by_") and k != "calibration"}, calibration={"bins": risk["calibration"]}, fairness=fairness, trained_at=now, artifact_path=path, is_active=True))
    db.add(ModelRegistry(name="uplift_t0", version=bundle.version, metrics=bundle.metrics["uplift_t0"], calibration={}, fairness={}, trained_at=now, artifact_path=path, is_active=True))
    db.add(ModelRegistry(name="uplift_t1", version=bundle.version, metrics={**bundle.metrics["uplift_t1"], "uplift": bundle.metrics["uplift"]}, calibration={}, fairness={}, trained_at=now, artifact_path=path, is_active=True))
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-score", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from app.db import session_scope
    from app.ml.model_card import write_model_card
    from app.ml.score import score_open_loops

    bundle, _ = train_all(args.seed)
    r = bundle.metrics["risk"]
    u = bundle.metrics["uplift"]["auuc_true"]
    log.info("risk AUROC %.3f  AUPRC %.3f  Brier %.3f", r["auroc"], r["auprc"], r["brier"])
    log.info("AUUC (true effect): uplift %.3f > risk %.3f > random %.3f", u["uplift"], u["risk"], u["random"])
    with session_scope() as db:
        register(db, bundle)
        if not args.no_score:
            n = score_open_loops(db, bundle)
            log.info("scored %d open loops", n)
    write_model_card(bundle)
    log.info("model version %s saved", bundle.version)


if __name__ == "__main__":
    main()
