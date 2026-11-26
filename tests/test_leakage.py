"""The tests that make the agent honest.

test_no_forbidden_features is the single most valuable test in this repo:
casual + registered == cnt exactly, so any model handed those columns
scores R^2 = 1.0 and looks brilliant while having learned nothing.
"""
from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from src.config import FORBIDDEN, TARGET
from src.features import build_features, encode_weather, feature_columns
from src.ingest import load_raw


@pytest.fixture(scope="module")
def feats():
    return build_features(load_raw())


def test_leakage_identity_holds(feats):
    """Documents *why* casual and registered are forbidden."""
    assert (feats.casual + feats.registered == feats[TARGET]).all()


def test_no_forbidden_features(feats):
    """Guards the gate, not the data: feature_columns() excludes FORBIDDEN by
    construction, so this cannot discover a *new* leaky column. What it
    catches is someone editing feature_columns() or FORBIDDEN -- which is
    exactly the fault the Step 7 hook demonstrates."""
    cols = set(feature_columns(feats))
    assert not (cols & FORBIDDEN), f"forbidden columns in feature set: {cols & FORBIDDEN}"


def test_no_feature_restates_the_target(feats):
    """Checks values, not names. test_no_forbidden_features only sees names
    in FORBIDDEN, so `casual` renamed to something innocent would pass it.
    Here every feature, and every pair of features, is fit against cnt,
    casual and registered by least squares with an intercept; an exact fit
    (max residual < 1e-6) is a restatement of the target."""
    cols = feature_columns(feats)
    hits = []
    for target in ("cnt", "casual", "registered"):
        y = feats[target].to_numpy(dtype=float)
        for r in (1, 2):
            for subset in combinations(cols, r):
                X = np.column_stack([feats[list(subset)].to_numpy(dtype=float),
                                     np.ones(len(feats))])
                coef, *_ = np.linalg.lstsq(X, y, rcond=None)
                if np.abs(X @ coef - y).max() < 1e-6:
                    hits.append((target, subset))
    assert not hits, f"features that exactly restate a leaked column: {hits}"


def test_lags_are_true_calendar_lags(feats):
    """cnt_lag_1 for date d must equal cnt on d-1, in calendar days."""
    by_date = feats.set_index("dteday")[TARGET]
    checked = 0
    for date, lag in feats.set_index("dteday").cnt_lag_1.items():
        prev = date - pd.Timedelta(days=1)
        if prev in by_date.index:
            assert lag == pytest.approx(by_date[prev]), f"bad lag at {date.date()}"
            checked += 1
    assert checked > 600, "too few rows actually verified"


def test_lag_2_is_two_calendar_days_back(feats):
    """cnt_lag_2 for date d must equal cnt on d-2, in calendar days.

    2011-03-18 is the first row to survive dropna() after the missing
    2011-03-10. Its two-day lag is 2011-03-16: data/raw/bike_daily.csv
    line 73 (instant=75), cnt = 2192, hand-copied, not recomputed.
    """
    assert "cnt_lag_2" in feats.columns, "cnt_lag_2 not built by build_features"
    row = feats.set_index("dteday").loc[pd.Timestamp("2011-03-18")]
    assert row.cnt_lag_2 == 2192


def test_lag_2_is_true_calendar_lag_everywhere(feats):
    """cnt_lag_2 for date d must equal cnt on d-2, on every row where d-2 exists."""
    by_date = feats.set_index("dteday")[TARGET]
    checked = 0
    for date, lag in feats.set_index("dteday").cnt_lag_2.items():
        prev = date - pd.Timedelta(days=2)
        if prev in by_date.index:
            assert lag == pytest.approx(by_date[prev]), f"bad lag_2 at {date.date()}"
            checked += 1
    assert checked > 600, "too few rows actually verified"


@pytest.mark.parametrize("labels", [
    ["GOOD", "SNOW"],      # a label this mirror does not use
    [1, 2, 3],             # UCI's numeric codes: the original silent-NaN bug
])
def test_encode_weather_rejects_unknown_labels(labels):
    """The real CSV only has GOOD/MISTY/BAD, so nothing else exercises this
    guard: seeded fault 3 (deleting the raise) left the whole suite green.
    Lives in this file so the PostToolUse hook runs it."""
    with pytest.raises(ValueError, match="unmapped weather labels"):
        encode_weather(pd.Series(labels))


def test_lag_is_not_the_target(feats):
    assert not (feats.cnt_lag_1 == feats[TARGET]).all()


def test_rolling_mean_excludes_today(feats):
    """cnt_roll_7 must be the mean of the 7 calendar days *before* today."""
    by_date = feats.set_index("dteday")[TARGET]
    date = feats.dteday.iloc[200]
    window = [date - pd.Timedelta(days=k) for k in range(1, 8)]
    if all(d in by_date.index for d in window):
        expected = sum(by_date[d] for d in window) / 7
        assert feats.set_index("dteday").cnt_roll_7[date] == pytest.approx(expected)


def test_no_missing_values(feats):
    assert feats[feature_columns(feats)].isna().sum().sum() == 0


def test_dates_are_sorted_and_unique(feats):
    assert feats.dteday.is_monotonic_increasing
    assert feats.dteday.is_unique
