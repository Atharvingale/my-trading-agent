# Step 1 — Cheap Manual Probe + Paper-Trading Support (2026-09-24)

Branch: `experiments/research-track`. No LLM work, no new dependencies, no
architecture migration. Two independent parts; either is useful alone.

## Why this step exists

Six of six hourly-signal families failed the gate, and the logged stopping
rule forbids further hourly experiments without a materially new hypothesis
class. Before approving a large LLM-research build, this step buys the
cheapest possible information: one manual experiment in a new class, plus the
simulation support every future direction needs regardless.

## Part A — Daily-timeframe trend probe

**New-class justification (stopping-rule compliance).** All six failed
families are intraday/hourly signals. Daily candles qualify explicitly as a
new class: different timeframe, higher close-to-noise ratio, overnight gaps,
turnover roughly an order of magnitude lower — directly addressing the
cost-attribution finding that 1% TDS turnover drag (16–26% of notional) was
the dominant killer. Family id `daily_trend_following` is distinct from
hourly `trend_following`; the 2023 daily window was touched by no prior
experiment in any family or timeframe.

**Hypothesis (pre-registered as `252cba87-d4c2-4b37-9a7b-249902027e4b`, before
any data was fetched).** Causal daily long-only EMA(5)/EMA(20) crossover on
BTCUSDT spot has positive net-of-cost-and-tax return on untouched 2023-01-01
through 2024-01-01 daily data. Entry on completed-candle crossover, next-daily-
open execution, 2% stop-loss checked before signal exits, 25% cash sizing.
Costs: 0.10% fee/side, 31.2% VDA tax on gains without loss offset, 1% TDS
drag. PASS bar: 3/4 windows positive, aggregate > 0, bootstrap CI positive-
excluding-zero, beats-risk-free-by-CI-width, doubled-cost stress > 0, ≥20
trades, two regime legs, disjoint replication positive.

**How it was coded.** Ad-hoc runner script (same pattern as the four prior
runs): `fetch_daily_klines()` paginates `GET /api/v3/klines?interval=1d`
with SHA-256 over canonical raw rows; `backtest_trend_following()` from
`edge_validation/experiment.py` runs unchanged (timeframe-agnostic) with
default parameters — no tuning; four chronological windows (~91 daily candles
each: Q1 recovery rally, Q2–Q3 range, Q4 rally — structurally different);
`ExperimentEvidence` (seed 20260924, 2,000 samples); first-half/second-half
`check_replication`; verdict recorded append-only via
`EdgeValidationRegistry.submit_hypothesis` → `record_result`. Nothing was
added to or read from `strategies/`.

**Result: FAIL (final, not retryable).** 365 daily candles, dataset
`7618f158…`, 8 trades (below the 20 minimum). Aggregate net −1.0963%,
stress −1.2977%, bootstrap CI [−3.2749%, −0.1505%] entirely negative; windows
−1.68%, −1.44%, −1.27%, 0.00%; replication FAIL. All six acceptance items
failed. Ledger: `daily_trend_following HYPOTHESIS/PENDING → RESULT/FAIL`
(fingerprint `fa0dbbd6…`). Artifact:
`research/reports/daily_trend_experiment.json`.

**Reading against the probe bar.** The bar was: flat-or-better with a
non-entirely-negative CI, or one positive regime leg. The probe clears
neither — negative aggregate, entirely-negative CI, zero positive windows,
sub-minimum sample. No signs of life. The 2023 daily window is burned for
this family; do not retry it.

## Part B — Paper-trading / simulation support

**What was implemented** (`paper_trading/`, new package, stdlib only):
- `simulator.py` — `PaperOrder` (validated, deterministic uuid5 ids),
  `PaperFill`, `simulate_fill(order, market_snapshot)` with fee rate,
  adverse slippage in bps, depth-capped partial fills (`PARTIAL` with the
  remainder explicitly unfilled, never silently assumed), empty-book
  `REJECTED`; `execution_report()` gives expected-vs-realized slippage,
  average price, fees. Pure function: no network, no credentials, no clock
  reads inside the math (the caller passes the post-latency snapshot, which
  is how latency is modeled — honestly, by construction).
- `portfolio.py` — `PaperPortfolio`: cash, averaged positions, realized PnL,
  fee ledger; long-only v1 (oversell raises `InsufficientPositionError`
  instead of creating silent margin debt); `equity()` marks on
  caller-supplied prices, unknown symbols at cost so missing data never
  invents gains.
- `engine.py` — `PaperEngine`: `submit(order, snapshot)` → fills → portfolio;
  `replay(trail)` replays ordered (order, snapshot) pairs deterministically;
  `equity()` / `snapshot()` views.

**What it deliberately does not do.** No live orders, no exchange clients, no
margin/shorts, no market-impact modeling beyond top-of-book depth. It answers
"what would this decision trail have cost and filled like" — nothing more.

**Tests.** `tests/test_paper_trading.py`, 7 tests: exact fill math, thin-book
partial, adverse slippage both sides, expected-vs-realized report, portfolio
round-trip + oversell rejection, deterministic replay, no-network-import scan.
All pass.

## Files changed/added this step

- Added: `paper_trading/__init__.py`, `paper_trading/simulator.py`,
  `paper_trading/portfolio.py`, `paper_trading/engine.py`,
  `tests/test_paper_trading.py`,
  `research/reports/daily_trend_experiment.json`,
  `research/reports/STEP1_DAILY_PROBE_AND_PAPER.md` (this file).
- Appended: runtime gate ledger rows (daily_trend_following HYPOTHESIS +
  RESULT), `research/reports/EXPERIMENT_REGISTRY_RUNTIME.md`,
  `docs/files/implementation-log.md`, `docs/files/module-status.md` row 1.
- Touched nothing in: `strategies/`, `edge_validation/` code, `hermes/`,
  `binance_data_layer/`, Modules 4/5 status.

## Test result

Full suite **148 passed** (141 + 7 new), `compileall` clean, `git diff
--check` clean (CRLF warnings only).

## Open items

The daily probe's negative result is now evidence for the pending
project-level decision (reserved for Atharva): with a new timeframe also
failing, the "adjacent space contains edge" premise behind Step 1 did not
confirm. Paper-trading support stands ready for any direction that follows.
