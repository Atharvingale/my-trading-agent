# Pre-registration: oi_positioning_20d_001

**hypothesis_id:** oi_positioning_20d_001
**signal_class:** open-interest-positioning-dynamics
**status:** FROZEN (immutable after commit; any design change requires a new hypothesis_id, never an edit)
**approved_by:** human, Cycle 4b task (NEW hypothesis_id, not a retry)
**source:** HUMAN (no LLM chose any parameter below)
**pre-reg commit:** TBD at commit time (must precede any holdout-period read; recorded in implementation-log after commit)

## Deviations and incidents / relationship to oi_positioning_001

- `oi_positioning_001` closed as `CLOSED_PRECOST_SCREEN` (research-only record `research/reports/oi_positioning_001_screen.json`: 381 trades, 99 entry dates, mean gross 0.003291, CI [-0.02482, 0.02905] vs 0.0140 fixed). Its holdout was never touched (Stage B never ran), so reusing the same holdout window here is allowed under gate criterion 2 within this family for a fresh id.
- This is a NEW hypothesis_id testing ONE deliberate lever: holding period 20 trading days (was 5). Nothing else changes. In particular the 90-day lookback is NOT widened "to match" the longer hold; a lookback test would be its own hypothesis_id.
- Engine parameterization (`research/oi_positioning.py`: `hold_days`/`lookback` params defaulting to 5/90; `research/oi_precost_screen.py::run` defaults) reproduces `oi_positioning_001` bit-for-bit under defaults (verified: 381 trades, mean 0.003290817094, identical CI, 99 dates). The 20-day run passes `hold_days=20`, `lookback=90`, `last_signal_day=2025-05-10` (exits ≤2025-05-31), new seed `20260929`.
- Since this task's Step 0, no holdout-period data has been read. Stage A reuse is research+embargo only (`data/oi_stage_a/`, checkpoint 111,180 jobs). Embargo data is not re-touched (ranking reused verbatim).

## Hypothesis statement

When a symbol's top-trader long/short ratio (`sum_toptrader_long_short_ratio`, size-weighted positions, per Amendment 1's resolved field) is in the bottom decile of its own trailing 90-day distribution, the symbol's subsequent 20-TRADING-DAY spot return, net of all costs, is positive. Long-only — the top-decile side is not traded. Spot trades 24/7, so trading days are calendar days: entry at D+1 spot daily OPEN, exit at D+21 spot daily OPEN (20 days after entry).

## What changed from oi_positioning_001, and nothing else

- Holding period: 20 trading days (was 5).
- Re-entry lock: a symbol cannot be re-entered until its current hold exits (unchanged rule, but now blocks re-entry for ~4x longer — expect meaningfully fewer trades per symbol per year; this is the intended trade-off, not a bug to correct).
- Lookback stays 90 days (unchanged).

## Signal, entry timing, no-look-ahead rule (identical)

Daily value for day D = last 5-minute metrics row of day D (23:55 UTC) field `sum_toptrader_long_short_ratio`. Percentile for day D = rank among strictly prior 90 days (D-90..D-1, excluding D); 90 prior days required. Fires if percentile ≤ 0.10. Known at 00:00 UTC D+1; entry at D+1 spot daily OPEN. Missing days are missing, never filled; no interpolation; UTC alignment validated.

Archive schema (as before): `create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio`.

## Universe (reused verbatim — do not re-rank)

Identical selection method and same frozen 60-symbol list from `oi_positioning_001` (rank order): ETHUSDT, BTCUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, SUIUSDT, BNBUSDT, TRXUSDT, ADAUSDT, ENAUSDT, LINKUSDT, PENGUUSDT, UNIUSDT, AVAXUSDT, LTCUSDT, WIFUSDT, HBARUSDT, TRUMPUSDT, AAVEUSDT, ARBUSDT, SEIUSDT, XLMUSDT, WLDUSDT, CRVUSDT, NEIROUSDT, BCHUSDT, VIRTUALUSDT, APTUSDT, PNUTUSDT, TAOUSDT, NEARUSDT, OPUSDT, ETHFIUSDT, DOTUSDT, CFXUSDT, LDOUSDT, SYRUPUSDT, BIOUSDT, FETUSDT, SUSDT, ONDOUSDT, BANANAS31USDT, TIAUSDT, PENDLEUSDT, CAKEUSDT, FILUSDT, ETCUSDT, INJUSDT, EIGENUSDT, HYPERUSDT, HUMAUSDT, POLUSDT, PAXGUSDT, RUNEUSDT, ALGOUSDT, GALAUSDT, RENDERUSDT, ENSUSDT, AIXBTUSDT, MEMEUSDT. If re-ranking seems warranted with time, that is out of scope — flag, do not do it.

## Windows (same)

Research 2021-01-01..2025-05-31 (warm-up from 2020-10-03; last signal 2025-05-10 so 20-day exits land ≤2025-05-31, keeping embargo trade-free). Embargo 2025-06-01..2025-08-31 (ranking only, already guarded, not re-touched). Holdout 2025-09-01..2026-08-31. Regime legs: three equal date-thirds. Overlap disclosure applies verbatim from `oi_positioning_001` (cross-sectional 2025-12-03..2026-05-02, funding F4 2026-05-03..2026-06-18, F4 orphan 2026-06-25..2026-08-24, F1-F3 2026-08-24..2026-09-26 overlap 8d; 2023-2025-01-01 families no overlap). Gate criterion 2 holds (fresh id; `oi_positioning_001` never consumed holdout).

## Costs (identical; read carefully)

Identical stack and round-trip fixed cost **1.40%** (fee 0.001/side, slippage 0.001/side, TDS 1% drag; VDA tax 31.2% on gains, no offset). A 20-day hold does NOT change the per-trade cost formula — TDS is charged per round trip regardless of hold length, which is the entire point of this test. The lever is trade frequency (fewer round trips per year → less TDS drag per unit time), not a lower rate.

## Expected trade-count reduction (minimum decided NOW)

The 5-day version produced 381 trades / 99 entry dates over research. A 20-day hold with 90-day lookback should fire roughly 1/4 as often per symbol. Pre-register a minimum of **80 entry-clusters** over the research window for the screen to be considered informative; fewer than that → screen still reported but flagged **`LOW_SAMPLE_SCREEN`** rather than a confident no-go (20-day signals are inherently rarer; thin research count need not imply thin holdout).

## Statistic and bootstrap

Identical cluster-by-entry-date methodology (`research/oi_cluster_bootstrap.py`, reused verbatim): one observation per entry date (mean net), 10,000 samples, fixed **NEW seed 20260929** (logged here; the `oi_positioning_001` seed 20260928 is not reused, to avoid any appearance of the same draw across hypotheses). No trade-level bootstrap.

## Multiple testing (live, not hardcoded)

`candidate_generation/multiple_testing.py::adjusted_threshold` at pre-reg time: HYPOTHESIS count=11, total_including_current=12, method=bonferroni, base 0.05, **required_alpha=0.0041666667 (~0.05/12)**. Expected test #12 (the slot `oi_positioning_001` would have used).

## Minimum trades for the holdout

**60 underlying trades** (lowered from 200 because 20-day holds produce fewer trades; still enough for the cluster bootstrap over ~60 symbols × ~1 year). Below 60: `NULL_RESULT`, "below pre-registered minimum sample" (Amendment 1 mapping). PASS additionally requires gate minimums. Report both entry-date and underlying counts.

## Reused vs new (code discipline)

Reused verbatim (guard enforced, no rewrite): `research/oi_positioning_universe.py` (+ `assert_embargo_only`), `research/oi_cluster_bootstrap.py`, `research/oi_download_stage_a.py` (Stage A only), `research/oi_precost_screen.py` (parameterized, defaults preserve 001). New only by parameterization: `hold_days=20`, `lookback=90`, `last_signal_day=2025-05-10`, `seed=20260929`, `hypothesis_id=oi_positioning_20d_001`, out `research/reports/oi_positioning_20d_001_screen.json`. No embargo re-touch, no lookback widening, no universe re-rank, no trade-level bootstrap, no production path.

## Stopping rule (Step 6, restated)

Whatever THIS task's result (close/FAIL/NULL/PASS): do not propose a third holding-period variant (10-day, 40-day, …) without fresh human approval — that would be unprincipled parameter search on one mechanism. One holding-period alternative was the agreed lever. If PASS: still no promotion/wiring; human review then paper validation with real liquidity/slippage checks on the actual (often illiquid) altcoins first.

## What this file does not do

No holdout reads before this commit. Screen runs on reused Stage A only. Stage B (holdout download) runs only if the screen passes. No `strategies/`, `execution/`, `risk/`, gate-code changes on any verdict.
