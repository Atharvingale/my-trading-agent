# OI Positioning 20-Day Variant — Research-Level Closure Note

- Hypothesis `oi_positioning_20d_001` (new id, not a retry): bottom-decile
  `sum_toptrader_long_short_ratio`, 20-trading-day spot hold, same 60-symbol
  universe and cost stack as `oi_positioning_001`.
- Pre-cost screen (research 2021-01-01..2025-05-31, reused Stage A, seed
  20260929): 169 trades / 70 entry dates (**LOW_SAMPLE_SCREEN**, <80),
  mean gross -0.007678 vs 1.40% fixed cost, CI [-0.04418, 0.08373].
- Comparison: `oi_positioning_001` (5-day) mean gross was +0.003291; the
  20-day hold did not improve the gross edge relative to the fixed cost.
- Outcome: `CLOSED_PRECOST_SCREEN`. Holdout never consumed. No ledger row.
  `m` unchanged. Full record: `research/reports/oi_positioning_20d_001_screen.json`;
  pre-registration: `research/hypotheses/oi_positioning_20d_001.md`.
- Per the Step 6 stopping rule, no third holding-period variant without
  fresh human approval.
