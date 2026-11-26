# Seeded faults (Exercise 2)

Each fault was seeded by a headless Claude Code session (`claude -p`,
Claude Opus 5.5) started inside this repo, so the project's PostToolUse hook
(`.claude/hooks/check_leakage.sh`) really fired; stream-json logs were
captured with `--include-hook-events`. Each fix was made by a **fresh**
session given only: *"make test fails in this repo. Find the cause and fix
it ... Show me the failing output before you fix it, and run make test
after."* "Turns" is the SDK's `num_turns` for that fix session. Faults 2
and 3 were seeded through my `/seed-fault` skill; its verbatim records are at
the end of this file. Absolute paths are shortened to repo-relative ones.

| # | Fault | Caught by | Hook | Fix turns |
|---|---|---|---|---|
| 1 | `"casual"` appended in `feature_columns` | `test_no_forbidden_features` | exit 2 | 6 (see caveat) |
| 2 | `.shift(1)` deleted from `cnt_roll_7` | `test_rolling_mean_excludes_today` | exit 2 | 7 |
| 3 | `raise` removed from `encode_weather` | **nothing** (suite green) until I added `test_encode_weather_rejects_unknown_labels` | silent, then exit 2 | 6 |
| 4 | raw CSV overwritten from Bash | **nothing** (suite green, ridge R^2 0.9999) until the hash / classification / identity tests | never fires | n/a |

## Fault 1: a forbidden column added to `feature_columns`

Commits `9f7cf78` (red) and `0135151` (fix).

```diff
-    return [c for c in numeric if c not in FORBIDDEN]
+    return [c for c in numeric if c not in FORBIDDEN] + ["casual"]
```

Hook stderr, as it reached the agent:

```
Leakage tests failed after editing src/features.py:
feats =         dteday  instant  season  ...  cnt_lag_2 cnt_lag_7   cnt_roll_7
0   2011-01-10     10.0  WINTER  ...      959.0...    1787.0  1530.142857
713 2012-12-31    731.0  WINTER  ...     1341.0     920.0  1531.428571

[714 rows x 29 columns]

    def test_no_forbidden_features(feats):
        """Guards the gate, not the data: feature_columns() excludes FORBIDDEN by
        construction, so this cannot discover a *new* leaky column. What it
        catches is someone editing feature_columns() or FORBIDDEN -- which is
        exactly the fault the Step 7 hook demonstrates."""
        cols = set(feature_columns(feats))
>       assert not (cols & FORBIDDEN), f"forbidden columns in feature set: {cols & FORBIDDEN}"
E       AssertionError: forbidden columns in feature set: {'casual'}
E       assert not ({'atemp', 'casual', 'cnt_lag_1', 'cnt_lag_7', 'cnt_roll_7', 'dayofweek', ...} & {'casual', 'cnt', 'cnt_2d_bfr', 'cnt_lag_2', 'days_since_2011', 'instant', ...})

tests/test_leakage.py:31: AssertionError
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_no_forbidden_features - AssertionError: fo...
1 failed, 8 passed in 0.52s
```

`make test`:

```
FAILED tests/test_leakage.py::test_no_forbidden_features - AssertionError: fo...
1 failed, 15 passed in 1.59s
make: *** [test] Error 1
make test exit=2
```

What it would have done to the numbers: ridge validation R^2 0.6475 -> 0.7879
(hgb 0.2185 -> 0.3436). One leaked component, not both, already looks like a
real gain; that is why the test, not the score, has to be the judge.

Fix: 6 turns. **Caveat:** the fix session ran `git show` on the red commit,
whose message named the fault, so this count is optimistic. For faults 2 and
3 the fix prompt added "do not use git log, git show, git diff or docs/" and
the red commit messages were neutral.

## Fault 2: `.shift(1)` deleted from `cnt_roll_7`

Commits `3588fbe` (red) and `015d585` (fix).

```diff
-    out["cnt_roll_7"] = out[TARGET].shift(1).rolling(LAG_WARMUP).mean()
+    out["cnt_roll_7"] = out[TARGET].rolling(LAG_WARMUP).mean()
```

Hook stderr:

```
Leakage tests failed after editing src/features.py:
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

`make test`:

```
FAILED tests/test_leakage.py::test_rolling_mean_excludes_today - assert np.fl...
1 failed, 15 passed in 1.67s
make: *** [test] Error 1
make test exit=2
```

Effect if missed: ridge validation R^2 0.6475 -> 0.7758. Fix: 7 turns,
diagnosed from the test and code alone. Note the test checks a single date
(`iloc[200]`); it caught this fault because the fault is global, but a fault
that only shifted part of the series could slip past it.

## Fault 3: the weather encoder's `raise` removed

Commits `2e1e822` (fault, suite green), `e125522` (new test, red),
`1b239a8` (fix), `ad483a3` (re-seed through `/seed-fault`, restored).

```diff
     unknown = set(known.unique()) - set(WEATHER_ORDER)
-    if unknown:
-        raise ValueError(f"unmapped weather labels: {sorted(unknown)}")
     return series.map(WEATHER_ORDER).astype(float)
```

First seeding: **SUITE STAYED GREEN** and the hook was silent (exit 0):

```
16 passed in 1.47s
make test exit=0
```

Why: the real CSV only contains GOOD/MISTY/BAD, so the guard is never
exercised, and no test fed `encode_weather` anything else. The pipeline
output was unchanged (ridge validation R^2 0.6475), which is exactly the
problem: the guard had no observable effect, so deleting it was invisible.

I added `test_encode_weather_rejects_unknown_labels` (parametrised over an
unseen label and UCI's numeric codes 1-3, the original silent-NaN bug) to
`tests/test_leakage.py`, so the hook runs it. With the fault still in place:

```
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels0]
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels1]
2 failed, 9 passed in 0.28s
```

Fix: 6 turns. The fix session restored the raise as
`sorted(map(str, unknown))`, so mixed int/str labels raise `ValueError` rather
than a `TypeError` from `sorted`; kept. Re-seeded afterwards through
`/seed-fault` (restore mode) to capture the hook on the new test:

```
Leakage tests failed after editing src/features.py:

labels = [1, 2, 3]

    @pytest.mark.parametrize("labels", [
        ["GOOD", "SNOW"],      # a label this mirror does not use
        [1, 2, 3],             # UCI's numeric codes: the original silent-NaN bug
    ])
    def test_encode_weather_rejects_unknown_labels(labels):
        """The real CSV only has GOOD/MISTY/BAD, so nothing else exercises this
        guard: seeded fault 3 (deleting the raise) left the whole suite green.
        Lives in this file so the PostToolUse hook runs it."""
>       with pytest.raises(ValueError, match="unmapped weather labels"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE ValueError

tests/test_leakage.py:78: Failed
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels0]
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels1]
2 failed, 9 passed in 0.50s
```

## Fault 4: raw data overwritten from Bash (the one the hook cannot see)

The tampered file was the real CSV plus one column, `rider_total`, an exact
copy of `cnt`: a leaked column with an innocent name. It was never
committed; each time it was restored with `git checkout -- data/raw/` and the
sha256 re-checked (`a6bed1577f6e4de5...`).

**What happened, three attempts by a headless agent:**

1. Write tool onto `data/raw/bike_daily.csv`: blocked by the deny rule.
   ```
   <tool_use_error>File is in a directory that is denied by your permission settings.</tool_use_error>
   ```
2. Plain `cp $SCRATCH/tamper/bike_daily.csv data/raw/bike_daily.csv`, with
   `Bash(cp:*)` allowed and the scratch dir added: **also blocked**.
   ```
   Permission to use Bash with command cp $SCRATCH/tamper/bike_daily.csv data/raw/bike_daily.csv has been denied.
   ```
   Control: the identical `cp` into `data/processed/` succeeded. So in Claude
   Code 2.1.332 the `Edit(./data/raw/**)` deny rule is also applied to the
   destination of a recognisable shell copy. The lesson's statement that it
   "does not stop cp inside a Bash command" is out of date for this version.
3. `python -c "import shutil; shutil.copy('$SCRATCH/tamper/bike_daily.csv', 'data/raw/bike_daily.csv')"`
   with `Bash(python -c:*)` allowed: **succeeded**. No permission rule fired
   and no hook ran (PostToolUse matches Edit|Write on `src/*.py` only).
   ```
   (Bash completed with no output)
   ```

The harness cannot see inside an interpreter, so a path-based rule cannot bind
it. Then, on the tampered data, with the starter's defences only:

```
$ make all
OK ingest: 728 rows, 2011-01-03 -> 2012-12-31
OK features: 714 rows, 15 features -> features.parquet
  temp, atemp, hum, windspeed, rider_total, dayofweek, is_weekend, is_holiday, is_workday, month_sin, month_cos, weather_severity, cnt_lag_1, cnt_lag_7, cnt_roll_7
      "r2": -0.9318,
      "r2": -2.1441,
      "r2": 0.4507,
      "r2": 0.5099,
      "r2": 0.9999,
      "r2": 0.9999,
      "r2": 0.694,
      "r2": 0.3963,
features: ['cnt_lag_1', 'cnt_lag_7', 'cnt_roll_7']
ridge {'r2': 0.9999, 'mae': 11.6}
hgb {'r2': 0.694, 'mae': 591.4}
$ make test
..................                                                       [100%]
18 passed in 1.06s
```

Every stage printed OK, every test passed, and ridge reported validation
R^2 0.9999. `feature_columns()` is a denylist: an unforeseen numeric column
enters the model silently.

**What would have caught it, and what I implemented** (commit `ab1f4f0`):

- *Implemented:* a hash check. `RAW_SHA256` in `src/config.py`;
  `src.ingest.verify_raw()` makes `make data` fail; `test_raw_data_is_unmodified`
  makes `make test` fail. It binds the file, so it does not care which tool
  wrote it.
- *Implemented:* `test_every_raw_column_is_classified`: every raw column must
  be in `FORBIDDEN`, `RAW_FEATURE_COLS`, `RAW_SOURCE_COLS` or `RAW_UNUSED_COLS`.
  This is the specific guard against "a new column cannot enter silently".
- *Implemented:* `test_no_feature_restates_the_target`: least squares of `cnt`,
  `casual` and `registered` on every feature and feature pair. It judges
  values, not names, so a renamed leak fails even when it arrives through
  code rather than data.
- *Not implemented, would also help:* a Stop hook running `make test` (makes
  "done" conditional on green, but only as good as the tests); a PreToolUse
  hook on Bash that rejects commands mentioning `data/raw` (brittle: paths can
  be built at runtime); `chmod -w data/raw` (the strongest against the agent,
  but a filesystem setting is not in the repo, so a fresh clone loses it).

Re-running fault 4 against the defences:

```
$ make data
ValueError: data/raw/bike_daily.csv has changed (sha256 37e80cecb02595a3..., expected a6bed1577f6e4de5...). Raw data is immutable: restore it with `git checkout -- data/raw/`.
make: *** [data] Error 1
$ make test
FAILED tests/test_contract.py::test_every_raw_column_is_classified - Assertio...
FAILED tests/test_contract.py::test_raw_data_is_unmodified - AssertionError: ...
FAILED tests/test_leakage.py::test_no_feature_restates_the_target - Assertion...
3 failed, 18 passed in 1.45s
```

Two more checks of the new tests, applied and reverted by hand:

- Leak renamed in code, `out["bike_index"] = out.casual` in `build_features`:
  ```
  FAILED tests/test_leakage.py::test_no_feature_restates_the_target - Assertion...
  1 failed, 20 passed in 1.22s
  ```
  The hook also exits 2 on it, since the identity test is in `test_leakage.py`.
- Leak renamed in the CSV header, `casual` -> `guest_rides`:
  ```
  FAILED tests/test_contract.py::test_raw_data_is_unmodified - AssertionError: ...
  1 failed, 3 passed, 17 errors in 1.13s
  ```
  (the 17 errors are `load_raw` refusing a CSV without its required `casual` column).

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
[${CLAUDE_PROJECT_DIR}/.claude/hooks/check_leakage.sh]: Leakage tests failed after editing src/features.py:
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

### Seeded: remove the raise ValueError from encode_weather in src/features.py again, now that test_encode_weather_rejects_unknown_labels exists (re-run of fault 3)

Claim attacked: an unknown weather label fails loudly instead of silently
becoming NaN.

Prediction (written before the edit): both parametrized cases of
`tests/test_leakage.py::test_encode_weather_rejects_unknown_labels` fail with
`DID NOT RAISE` (2 failed, 16 passed); the PostToolUse hook also fails, since
the test lives in `test_leakage.py`.

`git diff`:

```diff
diff --git a/src/features.py b/src/features.py
index 5576891..7dcfdb8 100644
--- a/src/features.py
+++ b/src/features.py
@@ -26,8 +26,6 @@ def encode_weather(series: pd.Series) -> pd.Series:
     """
     known = series.dropna()
     unknown = set(known.unique()) - set(WEATHER_ORDER)
-    if unknown:
-        raise ValueError(f"unmapped weather labels: {sorted(map(str, unknown))}")
     return series.map(WEATHER_ORDER).astype(float)
 
 
```

Hook stderr:

```
[${CLAUDE_PROJECT_DIR}/.claude/hooks/check_leakage.sh]: Leakage tests failed after editing src/features.py:

labels = [1, 2, 3]

    @pytest.mark.parametrize("labels", [
        ["GOOD", "SNOW"],      # a label this mirror does not use
        [1, 2, 3],             # UCI's numeric codes: the original silent-NaN bug
    ])
    def test_encode_weather_rejects_unknown_labels(labels):
        """The real CSV only has GOOD/MISTY/BAD, so nothing else exercises this
        guard: seeded fault 3 (deleting the raise) left the whole suite green.
        Lives in this file so the PostToolUse hook runs it."""
>       with pytest.raises(ValueError, match="unmapped weather labels"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE ValueError

tests/test_leakage.py:78: Failed
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels0]
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels1]
2 failed, 9 passed in 0.50s
```

`make test 2>&1 | tail -15`:

```
    ])
    def test_encode_weather_rejects_unknown_labels(labels):
        """The real CSV only has GOOD/MISTY/BAD, so nothing else exercises this
        guard: seeded fault 3 (deleting the raise) left the whole suite green.
        Lives in this file so the PostToolUse hook runs it."""
>       with pytest.raises(ValueError, match="unmapped weather labels"):
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       Failed: DID NOT RAISE ValueError

tests/test_leakage.py:78: Failed
=========================== short test summary info ============================
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels0]
FAILED tests/test_leakage.py::test_encode_weather_rejects_unknown_labels[labels1]
2 failed, 16 passed in 1.36s
make: *** [test] Error 1
```

Prediction held: exactly the predicted test failed (both parametrizations),
and the hook caught it at edit time. The gap found by the first run of
fault 3 is closed.
