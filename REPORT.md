# Forecasting daily bikeshare demand: report

Reproduce every number here with `make all` (pipeline), `make test`
(24 tests), `python -m src.train --target-transform` (Exercise 4,
validation), and `python -m src.diagnostics` (Exercise 5).

## Results

Train = 2011 (348 days), validation = H1 2012 (182), test = H2 2012 (184),
split by date (`src.train.temporal_split`). R² is computed against each
split's own mean, so 0 means "as good as a constant nobody could know in
advance". Eight rows: the four entries of `reports/metrics.json`, without
and with the feature I added in Exercise 1 (`cnt_lag_2`).

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

The "before" rows are the committed `reports/metrics.json`, which `make all`
reproduces exactly; I rejected the feature (below), so the final pipeline
is the "before" pipeline. The "with" rows are `reports/metrics.json` as
committed in `ec1f189`, the commit that added the feature. The test columns
of the "with" rows were not read until the keep/reject decision had been
made on validation and committed (`da7bd6d`).

For contrast, the naive model of Step 3 (`python -m src.leakage_demo`:
linear regression on `casual`, `registered`, `temp`, `hum`) scores test
R² = 1.000000.

## Headline finding

The naive evaluation gives R² = 1.000 and is invalid: `casual + registered
== cnt` on every row, so that model learned addition. Under a temporal split
with the leaked columns removed, the mean baseline scores test R² -2.14
(ridership grew, so the 2011 average is far below every late-2012 day), ridge
reaches 0.583 against a persistence baseline of 0.510, and ridge loses to
persistence on MAE (947 vs 840 rides). Gradient boosting falls to -0.50 on
test while still beating the mean baseline, because a tree cannot predict
above the largest target it saw: the 2011 maximum is 6,043 rides, 56.5% of
test days are above it (39.0% of validation days), and the booster's
largest test prediction is 5,537. My Exercise 1 feature, `cnt_lag_2` (rides
two calendar days earlier, calendar-aligned and tested), changed ridge
validation R² by -0.0022 and hgb by +0.0296; under a keep-rule fixed before
measuring (ridge validation gain >= 0.01) I rejected it, so it stays built
and tested but out of the model (`REJECTED_COLS` in `src/config.py`).

Two findings from breaking the pipeline on purpose (`docs/SEEDED_FAULTS.md`)
change how far the starter's guarantees reach. Removing the weather
encoder's `raise` left the whole suite green, because nothing exercised it;
and overwriting the raw CSV with one extra column, a copy of `cnt` named
`rider_total`, gave ridge validation R² 0.9999 with every stage printing OK
and all 18 tests then in the suite passing. Both now fail loudly: a unit test
for the encoder, a raw-data hash check, a test that every raw column is
classified, and a least-squares test that no feature restates the target.

## Exercise 4: target transformation

The question was whether a transformation of the target lets the tree
compete. Three candidates were fixed before running anything, each applied
to ridge and hgb through `RelativeTarget` in `src/train.py` (behind
`--target-transform`; `make all` is unaffected): the ratio to the previous
7-day mean (`cnt / cnt_roll_7`), the difference from yesterday
(`cnt - cnt_lag_1`), and `log1p(cnt)` as a control that rescales without
removing the trend. Every reference column is lagged, so nothing from day d
enters. Validation only (`reports/exercise4_valid.json`):

| Target | ridge valid R² | hgb valid R² | hgb max prediction |
|---|---|---|---|
| cnt (untransformed) | 0.6475 | 0.2185 | 5,541 |
| cnt / cnt_roll_7 | 0.3881 | **0.7454** | 8,222 |
| cnt - cnt_lag_1 | 0.6475 | 0.6079 | 8,307 |
| log1p(cnt) | 0.1042 | 0.1352 | 5,556 |

Baselines on validation: persistence 0.4507, mean -0.9318. The ratio lets
the tree predict above the 2011 ceiling (8,222 against 6,043), because it
now predicts a multiplier on a level that already carries the growth. The
log control does not fix it (max 5,556), which supports that mechanism over
"any transform helps". The same ratio hurts ridge, which already
extrapolated through its lag coefficients.

I chose hgb with the ratio target on validation and touched the test set
once for it (`bb00f5d`, `reports/exercise4_test.json`): **test R² 0.6416,
MAE 810.1**, against ridge 0.5833 / 947.1, persistence 0.5099 / 840.1 and
mean -2.1441 / 2847.7. It is the only model in this repo that beats
persistence on both test metrics, though on MAE only by 30 rides a day.
(Adding the baselines to that file later, after an audit finding, re-read
the test split; the model rows were byte-identical.)

**Is it defensible?** I judge it defensible, not a way to win the
comparison. The reference is known at prediction time; detrending by a
recent level is a standard way to make a model that cannot extrapolate
handle a trend; the candidates were fixed in advance and chosen on
validation; and the result holds where I did not select it: on test, and in
both halves of validation (Q1 2012: 0.582 vs ridge 0.562; Q2: 0.488 vs
0.093). The caveat that keeps it out of the headline: picking 1 of 6
model-transform pairs on 182 validation days is mild selection, and ridge
was not offered its best transform (the difference target ties its
untransformed score). The committed `reports/metrics.json` remains the
untransformed pipeline.

## Exercise 5: ridge vs persistence

Ridge is **not** worth deploying over "yesterday again" as it stands. Its
test R² is higher (0.583 vs 0.510), but R² is driven by a minority of large
misses; on a typical day ridge is worse: it is closer than persistence on
only 38.6% of test days, its median absolute error is 904 rides against
506, and its MAE is 947 against 840. The reason is a level bias, not noise:
ridge under-predicts by 555 rides a day on average on test (persistence: +16),
because its intercept and coefficients were fit on 2011's lower level
(`ridge_coef_per_sd`: `cnt_roll_7` +567, `cnt_lag_1` +362 rides per standard
deviation, then weather severity -280 and temperature +200; ridge is mostly
"recent demand, scaled down, corrected for weather"). Where ridge does add
something is on days whose change can be known in advance: when the weather
category changed from yesterday it beats persistence (MAE 1048 vs 1141,
n = 67); when workday status changed it roughly ties (1010 vs 1027, n = 59);
when neither changed it loses badly (860 vs 582, n = 81). Removing the four
days around Hurricane Sandy does not change the ranking (MAE 915 vs 784). So
the useful part of ridge is its weather and calendar response, and the
harmful part is the stale level. A deployable model has to fix the level
first; the detrended booster of Exercise 4 does that (bias -283) and beats
persistence on both metrics, but it was chosen after one look at test and
should be confirmed on 2013 data before anyone relies on it.

(An earlier draft supported this paragraph with a slice of "big-move days",
defined as |cnt - cnt_lag_1| > 1000. The leakage-auditor pointed out that
this is persistence's own error, so ridge winning there was guaranteed; the
slice is now labelled outcome-selected in `src/diagnostics.py` and the
argument above uses only slices knowable in advance. See `docs/AUDIT.md`.)

## Attribution

**Model:** this repository was produced in Claude Code 2.1.332 driving
hosted Anthropic models, not the local open-weight model the lesson
defaults to. The plan was written on **Claude Fable 5.2**; I then switched
the session to **Claude Opus 5.5**, which did all execution, including every
nested headless `claude -p` session (feature, seeded faults and fixes,
`/leakage-auditor`) and both `agent/audit.py` runs
(`AUDIT_MODEL=claude-opus-5-5`). The local `bikeshare-coder` (qwen3.5:9b
via Ollama, 64k context) was used only for the comparison below. One
limitation to be clear about: the main session ran from the directory
above this repo, so the project's PostToolUse hook did not fire on the
code it wrote directly (the tests, `config.py`, `ingest.py`, `train.py`,
`diagnostics.py`); it ran `make test` after each change instead. The hook
was live, and is evidenced firing, in every nested session that edited
`src/`: the feature, the seeded faults and their fixes.

**Generated by the agent** (all reviewed, run and checked against printed
numbers before committing):
- `tests/test_leakage.py`: `test_lag_2_is_two_calendar_days_back` and
  `test_lag_2_is_true_calendar_lag_everywhere` (nested `/new-feature` runs;
  the agent cited the wrong CSV line for the expected value, corrected by
  hand), `test_encode_weather_rejects_unknown_labels`,
  `test_no_feature_restates_the_target`.
- `tests/test_contract.py`: `test_every_raw_column_is_classified`,
  `test_raw_data_is_unmodified`, `test_target_transforms_round_trip`, and
  the validation-based rewrite of `test_beats_the_mean_baseline`.
- `src/features.py`: `cnt_lag_2`; the fixes for seeded faults 1-3 (each by a
  fresh session; the fault 3 fix also hardened the error message).
- `src/config.py`: `REJECTED_COLS`, `RAW_*_COLS`, `RAW_SHA256`;
  `src/ingest.py`: `verify_raw`; `src/train.py`: `RelativeTarget`,
  `TRANSFORMS`, `score_transforms`, the `--target-transform` flag;
  `src/diagnostics.py`; the `Makefile` fix for `make model`.
- `.claude/skills/seed-fault/SKILL.md`; `docs/SEEDED_FAULTS.md`,
  `docs/AUDIT.md`, the dated lines in `docs/DECISIONS.md`, this report, and
  the `CLAUDE.md` edits, all drafted by the agent; the decisions they record
  are listed below.

**Decisions that were mine** (each traces to a line in `docs/DECISIONS.md`):
- What to predict (`cnt`, daily), what counts as leakage (`casual`,
  `registered`, and any column that restates them), how to split
  (2011 / H1 2012 / H2 2012), and which baselines (mean and persistence):
  adopted from the starter, recorded in its five lines.
- Which model ran the agent (hosted, named above).
- Which feature to try (`cnt_lag_2`), and the rule for keeping it, fixed
  before measuring; rejecting it followed from that rule.
- That the Exercise 4 transformation is defensible, with the stated caveat.
- That ridge is not worth deploying over persistence as it stands.
- Whether the answer is believable: I accept the headline (the leaky 1.000 is
  invalid; ridge is a modest 0.07 R² over persistence and worse on MAE; the
  tree fails because it cannot extrapolate), because every part of it is a
  printed number that `make all` and `python -m src.diagnostics` reproduce.

The Exercise 4 and 5 verdicts were mine, chosen from options the agent laid
out with the numbers and a recommendation; I took its recommendation in
both cases. Where an auditor contradicted the agent (`docs/AUDIT.md`), the
correction was made and recorded rather than argued away, with one
exception: `agent/audit.py` flagged a starter line in DECISIONS.md for
quoting ridge's 0.583 without a baseline beside it. That line is unchanged
because the assignment requires the five starter lines kept as shipped; the
baselines are on the starter's own line 10 and beside every score in this
report.

### Changing the model, not the method (Exercise 6)

I gave both models the same two prompts, each in a fresh clone of the
**unmodified starter** with its `CLAUDE.md`: the Step 3 prompt ("Build a
model to predict cnt from the other columns. Report R-squared.") and the
Step 6 question *without* the "show me the evidence, compare the range"
clause, to see whether the evidence comes unasked. Claude Opus 5.5 (hosted)
finished both in under two minutes (30 s and 85 s). On Step 3 it did not
take the bait: it read `CLAUDE.md` and `src/config.py`, ran `make all` and
`make test`, said it had excluded `casual`/`registered` because they sum to
`cnt`, and reported ridge's 0.583 beside both baselines and the
"0.07 R² over persistence, worse MAE" caveat, all unprompted. So on a
strong model with `CLAUDE.md` loaded, the naive question no longer produces
the R² = 1.000 the lesson relies on; the trap only springs if the standing
rules are absent. On Step 6 it refit the models and printed the per-split
target range and each model's maximum prediction (hgb capped near 5,540
against a test maximum of 8,714) without being asked. The local
`bikeshare-coder` (qwen3.5:9b, 64k context, on an 18 GB laptop) made five
tool calls in about nine minutes, all exploring the CSV, one of them a Read
on a wrong absolute path (`~/data/raw/...`) that it then corrected, and had
produced no model and no number when I stopped it. It never reached the
Step 6 question. I have no evidence on whether it would have found the
identity or used the leaked columns, so I make no claim about that. The
hook did not fire in either run, because neither edited `src/`. The
methodology was the same in both runs; the difference was the model, and
with this setup the 9B model could not finish the first prompt in the time
I allowed.
