"""Evidence for REPORT.md (Step 6 questions, Exercises 4 and 5).

Read-only: refits the committed models on train and prints numbers. Uses
the test set, so run it only after model choices are frozen.

Run: python -m src.diagnostics
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

from src.config import METRICS, PROCESSED, TARGET
from src.features import feature_columns
from src.train import MODELS, TRANSFORMS, RelativeTarget, temporal_split

SANDY = pd.Timestamp("2012-10-29")


def _err(y, p):
    return {"r2": round(float(r2_score(y, p)), 4),
            "mae": round(float(mean_absolute_error(y, p)), 1),
            "bias": round(float(np.mean(p - y)), 1)}


def diagnostics() -> dict:
    df = pd.read_parquet(PROCESSED)
    cols = feature_columns(df)
    train, valid, test = temporal_split(df)
    out = {}

    # 1. Range of the target per split: why trees cannot extrapolate.
    tmax = train[TARGET].max()
    out["cnt_range"] = {n: [int(p[TARGET].min()), int(p[TARGET].max()), round(float(p[TARGET].mean()), 1)]
                        for n, p in [("train", train), ("valid", valid), ("test", test)]}
    out["share_above_train_max"] = {n: round(float((p[TARGET] > tmax).mean()), 3)
                                    for n, p in [("valid", valid), ("test", test)]}

    # 2. Ridge coefficients on standardised features (rides per 1 sd).
    ridge = MODELS["ridge"].fit(train[cols], train[TARGET])
    coef = ridge[-1].coef_
    out["ridge_coef_per_sd"] = {c: round(float(b), 1)
                                for c, b in sorted(zip(cols, coef), key=lambda t: -abs(t[1]))}

    # 3. Ridge vs persistence (and the Exercise 4 model) on test, sliced.
    hgb_ratio = RelativeTarget(MODELS["hgb"], **TRANSFORMS["ratio_roll7"]).fit(train[cols], train[TARGET])
    preds = {"persistence": test.cnt_lag_1.to_numpy(dtype=float),
             "ridge": ridge.predict(test[cols]),
             "hgb_ratio_roll7": hgb_ratio.predict(test[cols])}
    y = test[TARGET].to_numpy(dtype=float)
    no_sandy = ~test.dteday.between(SANDY - pd.Timedelta(days=1), SANDY + pd.Timedelta(days=2)).to_numpy()
    big_move = (np.abs(test[TARGET] - test.cnt_lag_1) > 1000).to_numpy()
    wkday_switch = (test.is_workday != test.is_workday.shift(1)).to_numpy()
    slices = {"all": np.ones(len(test), bool), "excl_sandy_4d": no_sandy,
              "big_day_to_day_move_gt1000": big_move, "workday_status_changed": wkday_switch}
    out["test_slices"] = {
        s: {"n": int(m.sum()), **{k: _err(y[m], p[m]) for k, p in preds.items()}}
        for s, m in slices.items()
    }
    abs_r, abs_p = np.abs(preds["ridge"] - y), np.abs(preds["persistence"] - y)
    out["ridge_beats_persistence_share_of_days"] = round(float((abs_r < abs_p).mean()), 3)
    out["median_abs_error"] = {k: round(float(np.median(np.abs(p - y))), 1) for k, p in preds.items()}

    # 4. Exercise 4 stability: validation halves (Q1, Q2 2012) and by month on test.
    halves = {"valid_Q1": valid[valid.dteday < "2012-04-01"], "valid_Q2": valid[valid.dteday >= "2012-04-01"]}
    out["valid_halves_r2"] = {
        h: {"ridge": round(float(r2_score(p[TARGET], ridge.predict(p[cols]))), 4),
            "hgb_ratio_roll7": round(float(r2_score(p[TARGET], hgb_ratio.predict(p[cols]))), 4),
            "persistence": round(float(r2_score(p[TARGET], p.cnt_lag_1)), 4)}
        for h, p in halves.items()
    }
    return out


if __name__ == "__main__":
    res = diagnostics()
    path = METRICS.parent / "diagnostics.json"
    path.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    print(f"OK diagnostics -> {path.name}")
