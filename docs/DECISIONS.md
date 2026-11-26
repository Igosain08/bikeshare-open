# Decisions

One line per methodological decision: what you chose, why, and what it changed.
Agents append here via the `/new-feature` skill; you append here by hand.

- Exclude `casual`, `registered`: they sum to `cnt` exactly. Leaky model R^2 1.000 -> honest ridge 0.583.
- Exclude `cnt_2d_bfr`: a shipped 2-day lag we cannot test the alignment of. Build our own lags instead.
- Exclude `instant`, `yr`, `days_since_2011`: time indexes let a tree predict a flat constant past 2011 and a linear model extrapolate a trend we have no grounds for.
- Split 2011 / H1 2012 / H2 2012 by date. Test set touched once, after all feature work.
- Report mean and persistence baselines with every score. Persistence (test R^2 0.510, MAE 840) is within 0.07 R^2 of ridge and beats it on MAE; that caveat goes in the report.
- 2026-11-25 Agent: Claude Code on hosted Claude Opus 5.5 (plan written on Claude Fable 5.2), not the local qwen3.5:9b; the course allows any model if named. All agent runs are headless `claude -p` sessions inside this repo, so the project hook and skills are live.
- 2026-11-25 Keep-rule fixed before measuring: a feature stays only if ridge validation R^2 rises >= 0.01 (182 validation days; smaller is noise). Test set not consulted for this.
- 2026-11-25 Added `cnt_lag_2` (cnt on d-2, calendar-aligned). Availability: d-2 is fully recorded before d. Validation: ridge R^2 0.6475 -> 0.6453 (-0.0022), hgb 0.2185 -> 0.2481 (+0.0296). Rejected (ridge is the model that matters; hgb still far below persistence 0.4507); kept built and tested, excluded via `REJECTED_COLS` in `FORBIDDEN`. metrics.json returns to the baseline numbers.
- 2026-11-25 Finding: shipped `cnt_2d_bfr` equals our tested `cnt_lag_2` on all 714 modelled rows (a naive row shift would differ on 2011-03-11/12), so it is correctly aligned after all. Still excluded: it adds nothing `cnt_lag_2` does not, and that just failed the keep-rule.
