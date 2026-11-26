# Forecasting daily bikeshare demand

To reproduce the numbers below: `make all` runs the pipeline, `make test`
runs the 24 tests, `python -m src.train --target-transform` gives the
Exercise 4 validation results, and `python -m src.diagnostics` gives the
Exercise 5 numbers.

## Results

I train on 2011 (348 days), validate on the first half of 2012 (182 days)
and test on the second half (184 days), splitting by date with
`src.train.temporal_split`. R² is measured against each split's own mean, so
0 is what you'd get from predicting a constant you couldn't have known
ahead of time. The table has the four entries from `reports/metrics.json`,
first without and then with the feature I added in Exercise 1
(`cnt_lag_2`).

| Model | Features | Valid R² | Valid MAE | Test R² | Test MAE |
|---|---|---|---|---|---|
| baseline_mean | before (14) | -0.9318 | 2002.2 | -2.1441 | 2847.7 |
| baseline_persistence | before (14) | 0.4507 | 900.6 | 0.5099 | 840.1 |
| ridge | before (14) | 0.6475 | 832.9 | 0.5833 | 947.1 |
| hgb | before (14) | 0.2185 | 1296.6 | -0.4975 | 1972.6 |
| baseline_mean | with `cnt_lag_2` (15) | -0.9318 | 2002.2 | -2.1441 | 2847.7 |
| baseline_persistence | with `cnt_lag_2` (15) | 0.4507 | 900.6 | 0.5099 | 840.1 |
| ridge | with `cnt_lag_2` (15) | 0.6453 | 833.4 | 0.583 | 945.5 |
| hgb | with `cnt_lag_2` (15) | 0.2481 | 1269.8 | -0.4737 | 1947.9 |

The "before" rows are the committed `reports/metrics.json`, and `make all`
reproduces them exactly. I ended up rejecting the feature (see below), so the
final pipeline is the "before" one. The "with" rows come from
`reports/metrics.json` as it was in commit `ec1f189`, where I added the
feature. I didn't look at the test columns of those rows until after I'd
decided on validation to reject it (`da7bd6d`).

For comparison, the naive model from Step 3 (`python -m src.leakage_demo`,
a linear regression on `casual`, `registered`, `temp` and `hum`) gets a test
R² of 1.000000.

## Headline finding

The naive R² of 1.000 is meaningless. `casual + registered` equals `cnt` on
every row, so that model just learned to add. Once those columns are gone and
the split is by date, the mean baseline gets a test R² of -2.14, because
ridership grew and the 2011 average is far below every day in late 2012.
Ridge gets 0.583. Persistence (predicting yesterday's count) gets 0.510, and
it actually beats ridge on MAE, 840 rides against 947. Gradient boosting
drops to -0.50 on test, though it still beats the mean baseline. The reason
is that a tree can't predict anything higher than the largest value it was
trained on. The 2011 maximum was 6,043 rides, 56.5% of test days are above
that (39.0% of validation days), and the booster never predicts more than
5,537 on test.

My Exercise 1 feature was `cnt_lag_2`, the ride count from two calendar days
earlier, built on the gap-free calendar and tested. It moved ridge's
validation R² by -0.0022 and hgb's by +0.0296. I'd set a rule before
measuring that a feature only stays if ridge improves by at least 0.01 on
validation, so I dropped it. It's still built and tested but kept out of the
model through `REJECTED_COLS` in `src/config.py`.

Breaking the pipeline on purpose (`docs/SEEDED_FAULTS.md`) showed two gaps
in the starter's checks. When I removed the `raise` from the weather
encoder, every test still passed, because nothing ever tested it. When I
overwrote the raw CSV with a version that had one extra column (a copy of
`cnt` called `rider_total`), ridge hit a validation R² of 0.9999, every
stage printed OK, and all 18 tests in the suite at that point passed. Both
of these fail now. I added a unit test for the encoder, a hash check on the
raw data, a test that every raw column is listed in the config, and a
least-squares test that no feature is a restatement of the target.

## Exercise 4: target transformation

The question here was whether changing the target would let the tree model
compete. Before running anything I picked three options: the ratio to the
previous 7-day mean (`cnt / cnt_roll_7`), the difference from yesterday
(`cnt - cnt_lag_1`), and `log1p(cnt)`. The log one was meant as a control,
since it rescales the target but doesn't take out the trend. I applied each
one to both ridge and hgb using `RelativeTarget` in `src/train.py`, behind
the `--target-transform` flag so `make all` isn't affected. All the
reference columns are lagged, so nothing from day d gets in. These are
validation numbers only (`reports/exercise4_valid.json`):

| Target | ridge valid R² | hgb valid R² | hgb max prediction |
|---|---|---|---|
| cnt (untransformed) | 0.6475 | 0.2185 | 5,541 |
| cnt / cnt_roll_7 | 0.3881 | **0.7454** | 8,222 |
| cnt - cnt_lag_1 | 0.6475 | 0.6079 | 8,307 |
| log1p(cnt) | 0.1042 | 0.1352 | 5,556 |

For reference, persistence gets 0.4507 on validation and the mean baseline
gets -0.9318. With the ratio target the tree can finally predict above the
2011 ceiling (8,222 compared to 6,043). It's now predicting a multiplier,
and the level it multiplies already includes the growth. The log version
doesn't help (its max is 5,556), so it isn't just that any transformation
helps. The ratio actually makes ridge worse, which makes sense since ridge
could already extrapolate through its lag coefficients.

I picked hgb with the ratio target based on validation and then ran it on
the test set once (`bb00f5d`, `reports/exercise4_test.json`). It got a test
R² of 0.6416 and an MAE of 810.1. Ridge has 0.5833 / 947.1, persistence
0.5099 / 840.1 and the mean baseline -2.1441 / 2847.7. That makes it the only
model in the repo that beats persistence on both test metrics, but on MAE
it's only by 30 rides a day. (Later an audit pointed out the baselines were
missing from that file. Adding them meant reading the test split again, but
the model rows came out byte-for-byte the same.)

I think the transformation is defensible and not just a trick to win the
comparison. The reference value is known at prediction time, and dividing
out a recent level is a normal way to deal with a trend when your model
can't extrapolate. I chose the candidates beforehand and picked on
validation. It also holds up on data I didn't select on: on test, and in
both halves of validation (Q1 2012: 0.582 vs ridge's 0.562, Q2: 0.488 vs
0.093). The caveat is that choosing 1 out of 6 model and transform pairs on
182 days is still some selection, and I didn't give ridge its best
transform (the difference target ties its untransformed score). So I'm not
putting it in the headline. The committed `reports/metrics.json` is still
the untransformed pipeline.

## Exercise 5: ridge vs persistence

I don't think ridge is worth deploying over "yesterday again" as it is. It
does have the higher test R² (0.583 vs 0.510), but R² is mostly driven by a
few large misses, and on an ordinary day ridge does worse. It's closer than
persistence on only 38.6% of test days. Its median absolute error is 904
rides against 506, and its MAE is 947 against 840. That isn't noise; the
problem is the level. Ridge under-predicts by 555 rides a day on average on
test (persistence is off by +16), because it was fit on 2011, when ridership
was lower. Looking at the coefficients (`ridge_coef_per_sd`, in rides per
standard deviation), `cnt_roll_7` is +567 and `cnt_lag_1` is +362, followed
by weather severity at -280 and temperature at +200. So ridge is mostly
"recent demand, scaled down, adjusted for weather".

Ridge does help on days where you could see the change coming. When the
weather category is different from yesterday's, it beats persistence (MAE
1048 vs 1141, n = 67). When workday status changes, the two are about even
(1010 vs 1027, n = 59). When neither changes, ridge loses by a lot (860 vs
582, n = 81). Taking out the four days around Hurricane Sandy doesn't change
the ranking (MAE 915 vs 784). So what's useful in ridge is how it responds
to weather and the calendar, and what hurts is the outdated level. A model
you'd actually deploy needs to fix the level first. The detrended booster
from Exercise 4 does that (bias -283) and beats persistence on both metrics.
But I picked it after one look at test, so it would need to be checked on
2013 data before anyone relied on it.

My first draft of this section used a slice of "big-move days", defined as
|cnt - cnt_lag_1| > 1000. The leakage-auditor caught that this is exactly
persistence's error, so ridge was guaranteed to win on those days. I
relabelled that slice as outcome-selected in `src/diagnostics.py` and
rewrote the argument using only slices you can know in advance (see
`docs/AUDIT.md`).

## Attribution

**Model:** I did this assignment in Claude Code 2.1.332 using hosted
Anthropic models, not the local open-weight model the lesson uses by
default. I wrote the plan with **Claude Fable 5.2** and then switched the
session to **Claude Opus 5.5**, which did everything after that. That
includes every nested headless `claude -p` session (the feature, the seeded
faults and their fixes, `/leakage-auditor`) and both `agent/audit.py` runs
(`AUDIT_MODEL=claude-opus-5-5`). I only used the local `bikeshare-coder`
(qwen3.5:9b through Ollama, 64k context) for the comparison at the end.

One limitation: the main session was running from the folder above this
repo, so the project's PostToolUse hook didn't fire on code it wrote
directly (the tests, `config.py`, `ingest.py`, `train.py`,
`diagnostics.py`). It ran `make test` after each change instead. The hook
was working in every nested session that edited `src/` (the feature, the
seeded faults and their fixes), and the logs show it firing.

**What the agent generated.** I reviewed and ran all of it, and checked it
against printed numbers before committing:
- `tests/test_leakage.py`: `test_lag_2_is_two_calendar_days_back` and
  `test_lag_2_is_true_calendar_lag_everywhere` (from nested `/new-feature`
  runs; the agent cited the wrong CSV line for the expected value, which I
  corrected), `test_encode_weather_rejects_unknown_labels`, and
  `test_no_feature_restates_the_target`.
- `tests/test_contract.py`: `test_every_raw_column_is_classified`,
  `test_raw_data_is_unmodified`, `test_target_transforms_round_trip`, and
  the rewrite of `test_beats_the_mean_baseline` so it uses validation.
- `src/features.py`: `cnt_lag_2`, and the fixes for seeded faults 1-3, each
  made by a fresh session. The fault 3 fix also made the error message
  sturdier.
- `src/config.py`: `REJECTED_COLS`, `RAW_*_COLS`, `RAW_SHA256`.
  `src/ingest.py`: `verify_raw`. `src/train.py`: `RelativeTarget`,
  `TRANSFORMS`, `score_transforms`, and the `--target-transform` flag. Also
  `src/diagnostics.py` and the `Makefile` fix for `make model`.
- `.claude/skills/seed-fault/SKILL.md`, `docs/SEEDED_FAULTS.md`,
  `docs/AUDIT.md`, the dated lines in `docs/DECISIONS.md`, this report, and
  the `CLAUDE.md` edits. The agent drafted all of these; the decisions they
  record are listed below.

**Decisions that were mine** (each one has a line in `docs/DECISIONS.md`):
- What to predict (daily `cnt`), what counts as leakage (`casual`,
  `registered`, and any column that restates them), how to split (2011 /
  H1 2012 / H2 2012) and which baselines to use (mean and persistence). I
  kept these from the starter, where they're the first five lines.
- Which model ran the agent (hosted, named above).
- Which feature to try (`cnt_lag_2`), and the rule for keeping it, which I
  set before measuring. Rejecting it followed from that rule.
- That the Exercise 4 transformation is defensible, with the caveat above.
- That ridge isn't worth deploying over persistence as it is.
- Whether the result is believable. I accept the headline (the leaky 1.000
  is invalid, ridge is only 0.07 R² better than persistence and worse on
  MAE, and the tree fails because it can't extrapolate), because every part
  of it is a printed number that `make all` and `python -m src.diagnostics`
  reproduce.

For the Exercise 4 and 5 verdicts, the agent laid out the options with the
numbers and a recommendation, and I picked one. In both cases I went with
its recommendation. When an auditor disagreed with the agent's work
(`docs/AUDIT.md`), I made the correction and recorded it. The one exception
is that `agent/audit.py` flagged a starter line in DECISIONS.md for quoting
ridge's 0.583 without a baseline next to it. I left that line alone because
the assignment says to keep the five starter lines as they were. The
baselines are in the starter's own line 10, and next to every score in this
report.

### Changing the model, not the method (Exercise 6)

I gave both models the same two prompts, each in a fresh clone of the
unmodified starter with its `CLAUDE.md`. The first was the Step 3 prompt
("Build a model to predict cnt from the other columns. Report R-squared.").
The second was the Step 6 question with the "show me the evidence, compare
the range" part removed, to see if the model would show the evidence
without being asked.

Claude Opus 5.5 (hosted) finished both in under two minutes (30 s and
85 s). On Step 3 it didn't fall for the trap. It read `CLAUDE.md` and
`src/config.py`, ran `make all` and `make test`, said it had left out
`casual` and `registered` because they add up to `cnt`, and reported ridge's
0.583 next to both baselines along with the "0.07 R² over persistence,
worse MAE" caveat, all without being asked. So with a strong model and
`CLAUDE.md` loaded, the naive question doesn't produce the R² = 1.000 the
lesson is built around. That only happens if the standing rules aren't
there. On Step 6 it refit the models and printed the target range for each
split and each model's largest prediction (hgb tops out around 5,540 while
the test maximum is 8,714), again without being asked.

The local `bikeshare-coder` (qwen3.5:9b, 64k context, on an 18 GB laptop)
made five tool calls in about nine minutes. All of them were just looking at
the CSV, and one was a Read on a wrong absolute path (`~/data/raw/...`) that
it fixed on the next call. It still hadn't built a model or produced a
number when I stopped it, and it never got to the Step 6 question. I don't
know whether it would have found the identity or used the leaked columns, so
I'm not claiming anything about that. The hook didn't fire in either run,
because neither one edited `src/`. The method was the same both times and
only the model changed, and with this setup the 9B model couldn't get
through the first prompt in the time I gave it.
