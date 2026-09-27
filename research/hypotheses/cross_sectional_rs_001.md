# Pre-registration: cross_sectional_rs_001

**hypothesis_id:** cross_sectional_rs_001
**signal_class:** cross-sectional-relative-strength
**status:** FROZEN (immutable after 2026-09-27T02:55:00+00:00; any design change requires a new hypothesis_id, never an edit)
**approved_by:** human, 2026-09-27 (menu addition `cross-sectional-relative-strength` via `HypothesisMenu.add_with_approval`, persisted in `research/hypothesis_menu.sqlite3`)
**source:** HUMAN (fixed by `docs/files/16-menu-addition-cross-sectional-relative-strength.md`; no LLM chose any parameter below)

## Hypothesis statement

A daily-rebalanced, long-only, top-quantile cross-sectional relative-strength rotation over a fixed two-asset spot universe has positive net-of-cost-and-tax return on the frozen holdout below, evaluated through the identical Module 1 machinery (fee/slippage/VDA-tax/TDS-adjusted bootstrap CI, pre-declared regime legs, doubled-cost stress, disjoint replication).

## Universe (exact)

Fixed symbol list: `["BTCUSDT", "ETHUSDT"]` (Binance spot, 1h closes).

Rule generating it: the full set of symbols with at least 8000 contiguous hourly closes covering the entire holdout in the stored versioned datasets `klines-btcusdt-1h v1` + `klines-ethusdt-1h v1` (`research/datasets/`). No other symbol in storage meets that coverage bar for this window.

Survivorship-bias note: both assets were continuously listed through the window (no delisting). Delisted/low-volume coins during the window are not silently excluded from a broader backtest — they were never in the eligible set because no evidence-grade stored history covers them here. This is a disclosed 2-asset limitation, not a claim of a broad-universe test. No synthetic or interpolated history is used for any missing symbol.

## Eligibility / liquidity filter (exact numbers)

At each daily rebalance, an asset is eligible only if BOTH hold over the trailing 30 days (720 hourly bars) ending at the rebalance timestamp:
- 30-day average daily notional (sum over each day of close * volume, divided by 30) >= USD 10,000,000 per day
- listing age >= 90 days (first stored 1h close at least 90 days before the rebalance timestamp)

Both BTCUSDT and ETHUSDT exceed the notional bar by orders of magnitude on every rebalance in this window (verified in Step 5 validation, not assumed). The thresholds are binding exclusion rules, not tuned parameters. An asset failing either test is excluded from ranking that day; if fewer than 1 asset is eligible on a rebalance date, the sleeve holds cash (0% return, no costs) until the next rebalance.

## Trailing-return lookback window (exact)

168 hourly bars (7 x 24h), ending at the rebalance timestamp inclusive of the last completed hourly candle. No other window is tested.

## Ranking method (exact, one formula)

Volatility-adjusted trailing return. For each eligible asset at rebalance time T (using completed hourly closes only, all known at or before T):
- trailing return R = close(T) / close(T-168h) - 1
- trailing stdev S = population standard deviation of the 168 one-hour simple returns ending at T
- score = R / S, except score = 0 when S == 0 (zero-variance window produces no signal, never a division artifact)

Rank eligible assets by score descending. Raw trailing return is NOT used. The ranking step is mandatory: the position is the top-ranked asset, even when its absolute trailing return is negative.

## Portfolio construction (exact; spot-only, long-only)

- Long leg: top 1 of 2 eligible assets (top 50%) each rebalance, 100% of the sleeve, equal-weight trivially.
- Short leg: NONE. Execution is spot-only (see below); this hypothesis is long-only top-quantile rotation vs the universe mean (equal-weight BTC+ETH buy-and-hold over each holding interval) and vs cash (0%). It is NOT long/short market-neutral.
- Sizing: full sleeve rebalanced daily; turnover costs apply only to the rotated notional (holding the same asset across a rebalance pays no entry/exit costs that day beyond the holding return).
- Execution check (from Step 0.4): `paper_trading/portfolio.py` (`PaperPortfolio`, long-only v1, oversell raises), `runtime/config.py` (paper default), and the signed n8n boundary carry no futures-short path for this sleeve. Futures shorting is NOT assumed.

## Excluded-pattern check (must pass; from the task document)

"Must NOT reduce to trend-following on a single asset. The defining mechanism is relative ranking across the universe at each rebalance point, not 'buy assets whose own price went up.' If the eventual implementation would produce similar signals to a single-asset momentum/trend filter with the cross-sectional step removed, it does not qualify and must not be tested as this class."

This design passes because: (a) there is no absolute-momentum filter — the top-ranked asset is held even when its own trailing return is negative and even when both assets are down; (b) removing the cross-sectional step leaves no signal (a single-asset 168h momentum rule on BTC alone or ETH alone is a different, already-falsified time-series class and is not what is traded here); (c) the benchmark is the contemporaneous universe mean, so outperformance requires picking the stronger of the two, not predicting the market direction.

## Rebalance interval (exact)

Daily at 00:00 UTC. Rebalance timestamps are the 00:00 UTC hourly close boundaries inside the holdout. Signals use completed candles only; execution is at the rebalance open (the 00:00 UTC open print).

## Holding period (exact)

Hold until the next 00:00 UTC rebalance. Rotate when the rank changes; otherwise hold the same asset (no turnover costs that day). A position opened at rebalance T is closed/rolled at T+24h at that day's open. End of holdout: any open sleeve is closed at the last available daily open inside the window (endpoint inclusive, no look-ahead).

## Cost model (verbatim reuse, applied per rebalance turnover)

Project cost stack, identical to all prior experiments (no redefinition):
- fee_rate = 0.001 per side
- slippage_rate = 0.001 per side
- tax_rate = 0.312 (31.2% VDA tax on positive realized gains, no loss offset)
- tds_rate = 0.01 (1% gross-proceeds TDS as cash-flow drag)
- loss_offset_allowed = false
- tds_is_cash_flow_drag = true

Applied per holding interval on the traded notional using the same closed-holding math as `research/funding_carry.py::apply_costs` (fees+slippage both sides, TDS on exit notional, tax on max(0, gross - fees - slippage - TDS)). Stress leg doubles fee and slippage (0.002 each), tax/TDS unchanged — same stress definition as every prior Module 1 run.

## Prior holdout/tuning ranges consulted (Step 0.3 / Step 4 disjointness input)

Every date range used as a holdout in any prior experiment (crypto; no NSE ranges exist in this repo):
1. 2023-01-01 through 2024-01-01 — daily_trend_following (daily holdout, FAIL)
2. 2024-01-01 through 2024-04-01 — trend_following (FAIL)
3. 2024-04-02 through 2024-07-01 — order_flow (FAIL)
4. 2024-07-02 through 2024-10-01 — mean_reversion (FAIL)
5. 2024-10-02 through 2025-01-01 — vwap_reversion (FAIL)
6. 2026-08-24 through 2026-09-26 — funding F1/F2/F3 shared holdout (NULL_RESULT x3)
7. 2026-06-25 through 2026-08-24 — funding F4 first submission (orphan PENDING, honestly nulled after infra crash before any evaluation; listed as touched)
8. 2026-05-03 through 2026-06-18 — funding F4 second attempt (FAIL)

Research/validation splits inside the funding datasets were definition-only (engines ran on the holdout slices above); no tuning period was consumed (no parameter was tuned on any window).

## Hold-out window (frozen here after the Step 4 check, before Step 5)

Selection rule (pre-stated, performance-blind): "the most recent contiguous period of at least 150 days for which full 2-asset 1h universe data exists in the stored versioned datasets and which does not overlap any holdout range in (1)-(8) above."

Result: **2025-12-03 through 2026-05-02** (150 days inclusive, day granularity for the gate ledger).

Why this window: the stored 2-asset 1h coverage runs 2025-10-28 through 2026-09-26; everything from 2026-05-03 onward is burned by (6)-(8); the latest 150-day block ending on or before 2026-05-02 is 2025-12-03 through 2026-05-02; it starts after (5) ends (2025-01-01) with an 11-month gap, so it is disjoint from all eight ranges. No return series from this window was computed or viewed before this freeze.

Regime note (Step 4.3): a 150-day span is expected to cover more than one volatility/trend regime, but this is confirmed only in the Step 7 artifact via pre-declared direction-thirds legs on BTC closes (same leg method as the F4 run). If the window yields only one regime leg, that will be stated explicitly rather than silently testing on a single regime.

## Gate metadata (frozen)

- strategy_id / strategy_family: `cross_sectional_rs_001` (new family; no prior holdout for this family, so the gate-level fresh-holdout check passes in addition to the honesty-level disjointness above)
- multiple_testing_family (provenance only): `cross-sectional`
- bootstrap: seed 20260927, samples 10000 (same order as the funding battery)
- minimum_trades: 20 (a NULL_RESULT is recorded if fewer than 20 daily holding intervals materialize; verdicts are exactly one of PASS / FAIL / NULL_RESULT / INCONCLUSIVE with trade count, aggregate return, and bootstrap CI bounds like every prior entry)
- dataset identity: `spot-1h-BTCUSDT-ETHUSDT-2025-12-03-2026-05-02` with SHA-256 over the canonical frozen holdout rows, recorded in the gate-run artifact

## What this file does not do

No holdout return series was read, computed, or viewed before this freeze. Step 5 (coverage validation: no silent gaps, no forward-filled bars, survivorship check above) and Step 7 (Module 1 run: thresholds from Step 6, frozen holdout, bootstrap CI, regime legs, doubled-cost stress, disjoint replication) happen strictly after this file exists. No `strategies/`, `execution/`, `risk/`, or Module 4-8 wiring is touched on any verdict; a PASS here is not a promotion.
