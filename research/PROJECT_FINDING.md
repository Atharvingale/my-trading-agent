# Project Finding: Edge-Validation Research Phase — Close-Out (2026-09-24)

A finding, not a proposal. This document states what was tested, how, and
what the evidence shows. It recommends nothing. The decision on what, if
anything, follows belongs to Atharva.

## 1. Scope

Seven experiments were run through the Edge Validation Gate
(`edge_validation/`), all on BTCUSDT spot data from Binance public klines.
Six are hourly strategy families: Breakout and Scalping (falsified
pre-existing, recorded as seeded FAIL verdicts with no holdout) plus Trend
Following, Order Flow, Mean Reversion, and VWAP Reversion (each run this
phase on its own fresh, disjoint holdout). The seventh is a daily-timeframe
trend probe (`daily_trend_following`, 2023 daily candles), permitted under
the logged stopping rule as a materially new hypothesis class (different
timeframe).

Every candidate experiment applied the same gate criteria: hypothesis and
acceptance thresholds pre-registered BEFORE the holdout was touched; a
holdout period never used by that strategy family; returns net of realistic
fees (0.10%/side), slippage (0.10%), and India VDA tax treatment (31.2% on
gains, no loss offset, 1% TDS as cash-flow drag); a bootstrap confidence
interval on mean per-trade net return (seed 20260924, 2,000 samples) that
must exclude zero on the positive side; two structurally different regime
legs; a doubled-cost stress test; a disjoint first-half/second-half
replication check; one final append-only verdict (PASS, FAIL, or
NULL_RESULT) with no retries against the same holdout.

## 2. Results

| Strategy | Holdout window | Trades | Aggregate net | Bootstrap CI | Verdict |
|---|---|---|---|---|---|
| Breakout (seeded, pre-existing) | — | — | −27.78% | entirely negative | FAIL |
| Scalping (seeded, pre-existing) | — | — | −39.42% | entirely negative | FAIL |
| Trend Following (`fafeb983…`) | 2024-01-01–04-01 | 66 | −5.34% | [−1.73%, −0.67%] | FAIL |
| Order Flow (`cc6dbcef…`) | 2024-04-02–07-01 | 111 | −10.13% | [−1.64%, −1.22%] | FAIL |
| Mean Reversion (`4b626ced…`) | 2024-07-02–10-01 | 96 | −9.49% | [−1.86%, −1.23%] | FAIL |
| VWAP Reversion (`e53a9ebf…`) | 2024-10-02–2025-01-01 | 16 | −1.13% | [−1.85%, −0.30%] | FAIL |
| Daily Trend probe (`252cba87…`) | 2023-01-01–2024-01-01 (1d) | 8 | −1.10% | [−3.27%, −0.15%] | FAIL |

Record IDs are the registry `record_id` values in
`research/runtime_edge_validation.sqlite3`; full per-window, stress, and
replication figures live in the matching `research/reports/*_experiment.json`
artifacts. Result: **7 experiments run, 0 PASS.** Every candidate CI lies
entirely below zero; every replication leg failed; VWAP and Daily Trend
additionally failed the 20-trade minimum-sample bar.

Note on statistical weight: the daily probe's n=8 is a thin sample next to
the hourly experiments' 66–111 trades (VWAP's n=16 is likewise thin). The
daily result stands as recorded — its CI is entirely negative — but it
carries less statistical weight than the hourly FAILs and must not be cited
as equal-strength evidence.

## 3. Cost-attribution finding

A same-trade diagnostic (`research/reports/cost_attribution.json`,
`cost_attribution_summary.md`) re-fetched the three high-sample holdouts,
verified identical datasets (all three SHA-256 match) and exact trade
sequences (66/111/96, aggregates match to <1e-9), then stripped costs with
timing held fixed; zero-cost reruns corroborate:

- Trend Following: net −5.34% → pre-cost +0.38%, CI [−0.23%, +1.08%].
  Mildly positive before costs — but the pre-cost CI still straddles zero.
- Order Flow: net −10.13% → pre-cost −0.00%, CI [−0.22%, +0.24%]. Flat.
- Mean Reversion: net −9.49% → pre-cost −0.11%, CI [−0.44%, +0.25%]. Flat.

Plain reading: pre-cost returns were near-zero, not positive-then-taxed-away.
The 1% TDS turnover drag was the dominant cost component (16.02% / 26.35% /
22.65% of starting notional), followed by fees and slippage (~3–5% each);
VDA tax was small (0.92–3.17%) because there were few gains to tax. Costs
drained flat signals; they did not destroy real ones. Only Trend Following
showed even a mildly positive raw signal, and it is not statistically
distinguishable from zero.

## 4. Holdout budget

Burned — must never be reused by the same family without a materially new
hypothesis (per gate criterion 2 and the project stopping rule):
- Hourly BTCUSDT: 2024-01-01–04-01 (trend_following), 2024-04-02–07-01
  (order_flow), 2024-07-02–10-01 (mean_reversion), 2024-10-02–2025-01-01
  (vwap_reversion).
- Daily BTCUSDT: 2023-01-01–2024-01-01 (daily_trend_following).

Untouched — a future session must not touch any of these without a dated,
pre-registered hypothesis and the same full gate rigor that produced the
seven results above: 2022 daily BTCUSDT, 2025 year-to-date data (hourly or
daily), and all other symbols. The remaining budget is finite; each
experiment spends part of it permanently.

## 5. Paths forward (stated, not recommended)

(a) Change the cost/tax structure. Mathematically real: at Trend Following's
+0.38% pre-cost level, a lower-drag domicile or loss-offsetting entity could
change the verdict math. Practically out of scope right now: relocation and
entity structuring carry legal, financial, and compliance weight far beyond a
backtest decision, and must not quietly become the reason research restarts
in three months without that weight being evaluated first.

(b) Test a genuinely new signal class. Funding-rate carry and cross-exchange
dislocation are the two structurally different, still-untested candidates.
If pursued, this is not justified by "one more test" momentum — it needs the
same explicit, dated pre-commitment the six-experiment stopping rule had:
named hypothesis, named fresh holdout, locked PASS bar, written before any
data is touched.

(c) Treat this document as the finding and stop the research track here.

The (a)/(b)/(c) decision belongs to Atharva and is deliberately not made
in this document.

## 6. What remains functional regardless

Independent of whether a strategy is ever wired: the Edge Validation Gate
(append-only ledger, 7-criteria enforcement, fail-closed loading), the
hardened market-data layer (async persistence, bounded fan-out, token+TLS
gate, retention, 24 hardening tests), the Observer + Context Builder
(`MarketContext`, stale→`valid=False`), the Strategy Proposal scaffolding
and Decision Engine (both complete, tested, and correctly idle — zero wired
strategies, production output HOLD), and the offline paper-trading module
(fill simulation, portfolio, deterministic replay). Full suite: 148 tests
passing. This is real, working, tested infrastructure — the research phase
ending does not diminish it.
