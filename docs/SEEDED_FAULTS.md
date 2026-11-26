# Seeded faults (Exercise 2)

Raw records appended by the `/seed-fault` skill land at the end of this
file under "Raw skill records"; the curated write-up is above them.

## Raw skill records

### Seeded: delete the .shift(1) from cnt_roll_7 in src/features.py, so the 7-day rolling mean includes today's count --keep

Claim attacked: "cnt_roll_7 is built only from past days, so today's `cnt`
never reaches its own feature row."
Predicted (before the edit): `tests/test_leakage.py::test_rolling_mean_excludes_today`
red; possibly also `tests/test_contract.py::test_only_expected_rows_are_dropped`
(the NaN window around the 2011-03-10 gap moves from m+1..m+7 to m..m+6).

Diff:

```diff
diff --git a/src/features.py b/src/features.py
index 02e93ca..a03a88d 100644
--- a/src/features.py
+++ b/src/features.py
@@ -74,7 +74,7 @@ def build_features(df: pd.DataFrame) -> pd.DataFrame:
     out["cnt_lag_1"] = out[TARGET].shift(1)
     out["cnt_lag_2"] = out[TARGET].shift(2)
     out["cnt_lag_7"] = out[TARGET].shift(LAG_WARMUP)
-    out["cnt_roll_7"] = out[TARGET].shift(1).rolling(LAG_WARMUP).mean()
+    out["cnt_roll_7"] = out[TARGET].rolling(LAG_WARMUP).mean()
 
     return out.dropna().reset_index(drop=True)
 
```

Hook stderr (PostToolUse:Edit, blocking, as it reached the agent):

```
[${CLAUDE_PROJECT_DIR}/.claude/hooks/check_leakage.sh]: Leakage tests failed after editing /Users/ishaangosain/Desktop/dsc-180-MA-all/DSC180A-Methodology-6/bikeshare-open/src/features.py:
[714 rows x 29 columns]

    def test_rolling_mean_excludes_today(feats):
        """cnt_roll_7 must be the mean of the 7 calendar days *before* today."""
        by_date = feats.set_index("dteday")[TARGET]
        date = feats.dteday.iloc[200]
        window = [date - pd.Timedelta(days=k) for k in range(1, 8)]
        if all(d in by_date.index for d in window):
            expected = sum(by_date[d] for d in window) / 7
>           assert feats.set_index("dteday").cnt_roll_7[date] == pytest.approx(expected)
E           assert np.float64(4389.0) == 4414.857142857143 ± 0.00441486
E             
E             comparison failed
E             Obtained: 4389.0
E             Expected: 4414.857142857143 ± 0.00441486

tests/test_leakage.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_rolling_mean_excludes_today - assert np.fl...
1 failed, 8 passed in 0.46s
```

`make test 2>&1 | tail -15`:

```
        window = [date - pd.Timedelta(days=k) for k in range(1, 8)]
        if all(d in by_date.index for d in window):
            expected = sum(by_date[d] for d in window) / 7
>           assert feats.set_index("dteday").cnt_roll_7[date] == pytest.approx(expected)
E           assert np.float64(4389.0) == 4414.857142857143 ± 0.00441486
E             
E             comparison failed
E             Obtained: 4389.0
E             Expected: 4414.857142857143 ± 0.00441486

tests/test_leakage.py:81: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_rolling_mean_excludes_today - assert np.fl...
1 failed, 15 passed in 1.35s
make: *** [test] Error 1
```

Predicted test went red: YES (`test_rolling_mean_excludes_today`, the only failure).
Secondary guess `test_only_expected_rows_are_dropped` stayed green: the row-drop
count does not distinguish a shifted from an unshifted 7-day window.

Restore: NOT restored (`--keep`); the fault is left in place for a timed fix.

### Seeded: remove the raise ValueError from encode_weather in src/features.py, so unknown weather labels silently become NaN --keep

Claim attacked: an unknown weather label fails loudly; it is never silently
mapped to NaN (and later dropped). Predicted before the edit: no test goes red,
because no file under `tests/` references `weather`, `encode_weather` or `ValueError`.

`git diff`:

```
diff --git a/src/features.py b/src/features.py
index 02e93ca..7dcfdb8 100644
--- a/src/features.py
+++ b/src/features.py
@@ -26,8 +26,6 @@ def encode_weather(series: pd.Series) -> pd.Series:
     """
     known = series.dropna()
     unknown = set(known.unique()) - set(WEATHER_ORDER)
-    if unknown:
-        raise ValueError(f"unmapped weather labels: {sorted(unknown)}")
     return series.map(WEATHER_ORDER).astype(float)
 
 
```

Hook stderr:

```
hook stayed silent
```

`make test 2>&1 | tail -15`:

```
python -m pytest tests/ -q
................                                                         [100%]
16 passed in 1.34s
```

**SUITE STAYED GREEN.** Prediction held. Missing test: nothing asserts that
`encode_weather` raises on an unseen label (e.g. `pytest.raises(ValueError)` on
`pd.Series(["GOOD", "SNOW"])`). The real CSV only contains GOOD/MISTY/BAD, so
neither the pipeline nor the suite exercises this path.

Restore: NOT restored (`--keep`); the fault is left in place for a timed fix.
