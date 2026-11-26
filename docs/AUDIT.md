# Audit (Exercise 3)

## 1. Teammate's repository: https://github.com/aarshiagupta/bikeshare-open

Audited at their commit `78f612d` (the latest when I cloned it). Before
running anything I read their `.claude/settings.json`, hook, Makefile and
their `src/` and `tests/` diff, since running an agent in someone else's repo
runs their hooks and code. Everything matched the starter apart from
ordinary pipeline changes. With the pinned `requirements.txt` (the same as
mine), `make all` reproduces their committed `reports/metrics.json` exactly
and `make test` gives 19 passed.

I ran `/leakage-auditor` in a fresh headless Claude Code session (Claude
Opus 5.5) inside their repo, on the diff from their unmodified-starter
commit. Prompt: *"Use the leakage-auditor subagent to review this
repository's diff from its unmodified starter commit to HEAD: git diff
5a3fefe..HEAD -- src/ tests/ ... print the subagent's report back to me
VERBATIM."* Report, verbatim (absolute paths shortened to repo-relative):

> All five checks pass on `git diff 5a3fefe..HEAD -- src/ tests/`. I ran the pipeline and all 19 tests pass, the outputs exactly match the committed `reports/metrics.json`, and I found nothing that changes a number or invalidates a conclusion.
>
> 1. **Target leakage:** none. The new `cnt_roll_3` (`src/features.py:79`) only uses days before the current one. The four target transforms in `src/train.py:71-76` only use `cnt_lag_1` and `cnt_roll_7`, which are both past values. I confirmed `casual + registered == cnt` on every row, and neither column is among the 15 features.
> 2. **Temporal ordering:** correct. The split is by date (348 train / 182 validation / 184 test rows). The scaler sits inside the pipeline, and it and the mean baseline are fit on training rows only. The transforms are fit on training rows only as well. Exercise 4 scores only the validation set unless `--final` is passed.
> 3. **Calendar gaps:** handled. The data is reindexed to a full calendar before any lag is built. In the final table, consecutive dates are always one day apart except one 9-day jump. That jump is the missing 2011-03-10 plus the 7 rows dropped after it.
> 4. **Silent row loss:** bounded. Of the 728 raw rows, 14 are lost: 7 for the lag warm-up and 7 after the missing day. That exactly equals the limit the test allows. The 3-day window of `cnt_roll_3` stays inside that limit, and unknown weather labels raise an error instead of being dropped.
> 5. **Baselines:** both are reported next to every model score, including in the target-transform runs. The persistence comparison is not flattering, and `REPORT.md` states it honestly: on test, ridge has a higher R^2 (0.58 vs 0.5099) but a worse MAE than persistence (946.2 vs 840.1).

### My verdict

I agree with all five of the auditor's passes. None of its points change a
number, and I checked the main ones myself: the metrics reproduce, their
`cnt_roll_3` test uses a hand-computed value from strictly earlier days, and
14 rows are dropped, which is exactly the bound. The finding that does
change a conclusion is one the auditor couldn't see, because it only
reviewed `src/` and `tests/`. It's in their `REPORT.md`, Exercise 5. They
say ridge's R² edge comes from "32 days when demand swung by more than 1,500
rides from the day before", where ridge's MAE is 1,502 against
persistence's 2,413, and they recommend "persistence with a ridge-based
alarm for weather-driven swings". But |cnt - cnt_lag_1| > 1500 is
persistence's own error, so those days are chosen using the answer and
can't be known in advance. That makes them fine as an accounting of where
the R² gap comes from, but not as evidence for an alarm. I made the same
mistake in my own repo (section 2, finding 1). Rerunning their pipeline on
days you could flag ahead of time gives:

```
all                                                                      n=184  ridge MAE   946.2  persistence MAE   840.1
their slice |cnt-cnt_lag_1|>1500 (= persistence error, outcome-selected) n= 32  ridge MAE  1502.1  persistence MAE  2413.2
ex-ante: weather category changed                                        n= 67  ridge MAE  1042.2  persistence MAE  1141.2
ex-ante: workday status changed                                          n= 59  ridge MAE   994.0  persistence MAE  1027.3
ex-ante: neither changed                                                 n= 81  ridge MAE   868.9  persistence MAE   582.2
slice identical to persistence error > 1500: True
```

On days when the weather category changed, which is what their alarm would
fire on, ridge still wins, but by 99 rides of MAE (1042 vs 1141), not 911.
On days when nothing changed it loses by 287. So their verdict (keep
persistence, don't swap in ridge) holds, and the alarm idea has some real
support, but the effect is about a ninth of what their slice suggests. I'd
suggest they report the weather-changed slice instead. Smaller points that
don't change any number: their `test_beats_the_mean_baseline` still checks
test-set R² on every `make test` (the starter's version; I moved mine to
validation after my own audit), and `test_no_feature_reconstructs_the_target`
only checks exact sums of two features, so a rescaled sum like
`0.5 * (casual + registered)` would get past its pair check. Their
correlation check would still catch it, because it's a near-copy of `cnt`.

## 2. `/leakage-auditor` on my own diff (self-audit)

Run 2026-11-25 in a fresh headless Claude Code session inside this repo
(Claude Opus 5.5), so the project's subagent definition
(`.claude/agents/leakage-auditor.md`) was used and the subagent saw only the
diff and the criteria, not the conversation that produced the code. Prompt:
*"Use the leakage-auditor subagent to review the diff from the unmodified
starter commit to HEAD: git diff 220b118..HEAD -- src/ tests/ ... print the
subagent's report back to me VERBATIM."* Report, verbatim (absolute paths
shortened to repo-relative):

> I found three problems, all in `src/diagnostics.py`. The pipeline behind `metrics.json` and the Exercise 4 outputs passes all five checks.
>
> **What I checked:** I read the full diff (`220b118..HEAD`) and then ran the code. `make test` passes (24 tests). Rebuilding the features from scratch gives exactly the stored parquet: 714 rows, 14 features, no forbidden column. Rerunning in memory reproduces `metrics.json`, `exercise4_valid.json`, `exercise4_test.json` and `diagnostics.json` exactly.
>
> **Passed:**
> - **Leakage:** `cnt_lag_2` is excluded through `REJECTED_COLS`. The new value-based least-squares test looks at features one at a time and in pairs. The ratio and difference transforms only use lagged reference columns.
> - **Time order:** every fit, including the scaler inside the ridge pipeline and the `RelativeTarget` models, sees training rows only. The transform was chosen on validation.
> - **Missing days:** `cnt_lag_2` is built after `reindex_to_calendar`. The 14 dropped rows exactly match the allowed limit (7 warm-up days plus 7 rows after the missing day), so no rows are silently lost.
>
> ## Findings
>
> **1. `src/diagnostics.py:53`: the "big move" slice is picked using the answer, so the Exercise 5 conclusion doesn't hold up (check 1).**
> ```python
> big_move = (np.abs(test[TARGET] - test.cnt_lag_1) > 1000).to_numpy()
> ```
> `|cnt - cnt_lag_1|` is exactly persistence's error. I confirmed the mask is identical to "persistence error > 1000" on every test row. So this slice contains only the days where persistence is already known to have missed by more than 1,000 rides, and it uses today's count to say so.
>
> - The result "ridge earns its keep only on big-move days (MAE 1219 vs 1977, n=52)" in `docs/DECISIONS.md:18` is true by construction. It doesn't support deploying ridge, because nobody can know in advance which days will be big-move days.
> - On the other 132 days the gap reverses: ridge MAE 840.0 against persistence MAE 392.3.
> - The only slice you can know in advance, `workday_status_changed`, gives roughly a tie (ridge 1010.5 vs persistence 1027.3 after the fix in finding 2).
>
> **Fix:** report the 52-day slice together with its 132-day complement, and say it is selected on the outcome. Base the "where ridge helps" claim on a slice you can know ahead of time, such as workday changes, holidays or the weather forecast.
>
> **2. `src/diagnostics.py:54`: the first test day is wrongly counted as a workday change (check 3).**
> ```python
> wkday_switch = (test.is_workday != test.is_workday.shift(1)).to_numpy()
> ```
> This compares each row to the row above it, but only within the test split. On 2012-07-01 the previous row is missing, `NaN != 0` counts as true, and the day is flagged. In fact 2012-06-30 and 2012-07-01 are both non-workdays, so nothing changed.
>
> - As written: n=60, ridge R^2 0.6531 / MAE 1005.4, persistence R^2 0.6111 / MAE 1012.7.
> - Corrected: n=59, ridge R^2 0.6550 / MAE 1010.5, persistence R^2 0.6112 / MAE 1027.3.
>
> **Fix:** compute the shift on the full date-indexed frame, then select the test dates:
> ```python
> prev = df.set_index("dteday").is_workday.shift(1).reindex(test.dteday).to_numpy()
> wkday_switch = test.is_workday.to_numpy() != prev
> ```
>
> **3. `src/diagnostics.py:48-63` and `:67-72`: the mean baseline is missing from `test_slices` and `valid_halves_r2` (check 5).**
> Both blocks report ridge and `hgb_ratio_roll7` next to persistence only. They break the "both baselines next to every model score" rule, which last round's fix applied only to `score_transforms`. This doesn't overturn a conclusion, since the claims in this file are about ridge against persistence. But `diagnostics.json` is a set of scored model results that doesn't meet the reporting rule.
>
> **Fix:** add `"mean": np.full(len(test), train[TARGET].mean())` to `preds`, and a matching entry for each validation half.
>
> Files:
> - `src/diagnostics.py`
> - `docs/DECISIONS.md` (line 18, the Exercise 5 verdict)
> - `reports/diagnostics.json`

### My verdict on these findings

Finding 1 changes a conclusion, and it is right. I sliced the test set by
"|cnt - cnt_lag_1| > 1000" to show where ridge helps, but that quantity is
persistence's own error, so the slice was chosen with today's count, and
ridge winning on it was guaranteed. I wrote "ridge earns its keep on
big-move days" in docs/DECISIONS.md on the strength of it. Fixed in
src/diagnostics.py: the slice is now labelled OUTCOME_SELECTED and reported
with its complement, where persistence wins outright (MAE 392 vs 840, n=132),
and the claim now rests on slices knowable in advance: ridge beats
persistence when the weather changed (MAE 1048 vs 1141, n=67), roughly ties
when workday status changed (1010 vs 1027, n=59), and loses when neither
did (860 vs 582, n=81). The Exercise 5 verdict (not worth deploying as-is)
survives and is better supported; the sentence behind it was wrong and is
corrected in DECISIONS.md. Finding 2 is right and changes a number only in
the second decimal (n 60 -> 59, ridge MAE 1005.4 -> 1010.5); fixed. Finding 3
is right but changes no number or conclusion; fixed anyway because it is the
repo's own rule. None of the three touches `reports/metrics.json` or the
headline result, which the auditor reproduced independently.

## 3. `agent/audit.py` on my own repo (Part 4)

    AUDIT_MODEL=claude-opus-5-5 python agent/audit.py . --out reports/audit.jsonl

Run 1 (commit `222a7ca`), verbatim (absolute path shortened to `.`):

```json
{
  "repo": ".",
  "leakage": "none",
  "temporal_ok": true,
  "baseline_reported": true,
  "reproducible": true,
  "findings": [
    {
      "file": "src/train.py",
      "line": 153,
      "issue": "The Exercise 4 runner (`score_transforms`, used by `python -m src.train --target-transform [--final ratio_roll7]`) writes reports/exercise4_valid.json and reports/exercise4_test.json with only the ridge and hgb rows. Neither the mean baseline nor the persistence baseline appears in them. DECISIONS.md line 17 then quotes the selected model's test score (R^2 0.6416, MAE 810.1) without persistence beside it. Persistence on test is R^2 0.5099, MAE 840.1, which only appears in metrics.json.",
      "why_it_matters": "The rule is that every model score is reported next to the mean and persistence baselines. The headline Exercise 4 test number is the one place that rule breaks. On MAE the chosen model beats 'yesterday again' by only about 30 rides a day, and you can't see that from the artefact that reports the number."
    },
    {
      "file": "tests/test_contract.py",
      "line": 60,
      "issue": "`test_beats_the_mean_baseline` fits ridge and checks its R^2 on the test split (> 0.4) every time `make test` runs. Despite its name, it never compares against the mean baseline. It checks a fixed threshold, and the value 0.4 was presumably picked after seeing the test score (0.5833).",
      "why_it_matters": "Nothing is tuned on test, so this is not leakage. But running a pass/fail gate on test-set R^2 means the test split gets looked at over and over during development, and a red result invites changing the features until it turns green, which is tuning on test by another route. The gate should run on validation, or it should compare against the baseline it is named after."
    }
  ],
  "confidence": "high"
}
```

### My verdict on these findings

Both right; both changed what the repo reports, neither changed a number in
metrics.json. (1) My Exercise 4 headline (hgb + ratio target, test R^2
0.6416, MAE 810.1) was written without persistence beside it (0.5099,
840.1); on MAE the margin is only 30 rides/day, which the report must show.
Fixed: score_transforms now writes both baselines. (2) The starter's
`test_beats_the_mean_baseline` gated on test-set R^2 > 0.4 on every
`make test` and never compared to the mean baseline it is named after.
Moved to validation and made to compare against `baseline_mean`. The final
`reports/audit.jsonl` is a re-run on the finished repo; see section 4.

## 4. `agent/audit.py`, final run on the finished repo

`reports/audit.jsonl` (commit `03eabcd`) is this run: leakage `none`,
`temporal_ok`, `baseline_reported` and `reproducible` all true, confidence
high, two findings, both about baselines missing from written claims in
docs/DECISIONS.md, not about the pipeline.

- Line 17 (my Exercise 4 line quoted 0.6416 / 810.1 with no baselines):
  correct, fixed; the line now carries persistence and mean, and says the
  MAE gain over persistence is 30 rides/day.
- Line 6 (starter line, "leaky 1.000 -> honest ridge 0.583" with no
  baseline): correct as an observation, not changed, because the assignment
  requires the five starter lines kept as shipped; the starter's own line 10
  gives persistence, and REPORT.md states every score beside both baselines.
