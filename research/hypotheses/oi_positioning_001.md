# Pre-registration: oi_positioning_001

**hypothesis_id:** oi_positioning_001
**signal_class:** open-interest-positioning-dynamics
**status:** FROZEN (immutable after commit; any design change requires a new hypothesis_id, never an edit)
**approved_by:** human, 2026-09-28 (menu addition `open-interest-positioning-dynamics` via `HypothesisMenu.add_with_approval`, persisted in `research/hypothesis_menu.sqlite3`; Amendment 1 rulings 2026-09-28)
**source:** HUMAN (no LLM chose any parameter below)
**pre-reg commit:** TBD at commit time (must precede any holdout-period read; recorded in implementation-log after commit)

## Deviations and incidents (Amendment 1 requirement)

- Prior session (Task 21 Step 0) fetched spot daily klines with `endTime=2025-09-01T00:00:00Z` (inclusive), pulling `2025-09-01` opens/volume (holdout day 1) for 344 symbols into a volume average. Only spot opens/volume for that one day entered an average. No returns, signals, metrics, or archive holdout files were touched. No 5-day return was computed or viewed.
- Ruling: that ranking is DISCARDED and must not be reused or used for comparison. This pre-registration uses ONLY the clean embargo-only ranking below (guard-enforced, `endTime <= 2025-08-31T23:59:59.999Z`).
- Since restart (Amendment 1): no holdout-period data (metrics or spot for `>=2025-09-01`) has been downloaded or read. Clean ranking used embargo `2025-06-01..2025-08-31` only with `assert_embargo_only` guard. Listing-date checks used `startTime=0 limit=1` (earliest kline, 2017-2025-05) only. Throughput trial used research-window metrics (`2025-01/02/03`, research only). Archive probes for size used embargo date `2025-06-15` only.

## Hypothesis statement

When a symbol's top-trader long/short ratio is in the bottom decile of its own trailing 90-day distribution (crowd unusually short), the symbol's subsequent 5-day spot return, net of all costs, is positive. Long-only. There is no short leg: execution is spot-only, and the top-decile (crowd max-long) side is simply not traded.

## Signal field (frozen per Amendment 1 — verbatim)

Freeze `sum_toptrader_long_short_ratio` (top-trader POSITIONS ratio, size-weighted). Rejected: `count_toptrader_long_short_ratio` (accounts). Say this verbatim in the pre-registration. Bottom decile = most short-heavy crowd, by position size.

Archive schema (verified `docs/results/oi-liquidation-public-archive-coverage-audit.md` §A, 5 samples identical): `create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio` (8 columns, 5-minute state rows in UTC-daily partitions, 288/day).

## Signal (no look-ahead)

- Daily value for day D = the last 5-minute metrics row of day D (23:55 UTC) field `sum_toptrader_long_short_ratio`.
- Percentile for day D = rank of D's value among the previous 90 daily values (D-90..D-1, strictly excluding D). Needs 90 prior days; earlier days are ineligible.
- Signal fires if percentile <= 0.10.
- Signal is known at 00:00 UTC on D+1. Entry at the D+1 spot daily OPEN.
- Missing days are recorded as missing, never filled. No forward-fill. No interpolation. UTC alignment between metrics day partitions and spot daily candles is validated; mismatches are missing, not filled.

## Holding rule

Exit at the spot daily OPEN 5 days after entry. A symbol already held cannot be re-entered until it is exited. No stop-loss, no discretionary exit.

## Universe (exact, frozen method + resolved list)

Start from the >=180d FULL coverage set in the audit (495 symbols, §H: 510 ≥90d, 495 ≥180d, 397 ≥365d, largest BTCUSDT 2191d).

Filters (all binding, in order):
1. Binance SPOT USDT pair, status TRADING, `isSpotTradingAllowed`, quote USDT (via `api.binance.com/api/v3/exchangeInfo` at ranking time). 495 ∩ spot = 346.
2. Corrected leveraged-token rule (`research/oi_positioning_universe.py::is_leveraged`): UP/DOWN excluded ONLY when the stripped underlying is itself a spot symbol (keeps JUPUSDT, SYRUPUSDT). BULL/BEAR excluded. Result in this set: 0 excluded.
3. Index products excluded (`is_index_product`): BTCDOMUSDT named; none in the 346 ∩ spot set beyond the spot filter (BTCDOM has no spot pair), 0 additional.
4. Stablecoin and fiat-pegged bases excluded (`is_stable_or_fiat`): USDCUSDT, FRAXUSDT. Searched FDUSD, TUSD, USDP, DAI, USDD, LUSD, SUSD, GUSD, PYUSD, AEUR, EUR, EURI, GBP, BRL, TRY, ARS, MXN — no others in the 495 ∩ spot set. After steps 2-4: 344 candidates.
5. Listing date before 2025-06-01 AND complete daily klines for all 92 embargo days (2025-06-01..2025-08-31, `endTime=2025-08-31T23:59:59.999Z=1756684799999`, guard `assert_embargo_only` < `1756684800000`). Incomplete excluded (63): 0GUSDT, 2ZUSDT, AEROUSDT, ALLOUSDT, ASTERUSDT, ATUSDT, AVNTUSDT, BANKUSDT, BARDUSDT, BREVUSDT, CUSDT, DOLOUSDT, EDENUSDT, ENSOUSDT, ERAUSDT, ESPUSDT, EULUSDT, FFUSDT, FOGOUSDT, FUSDT, GIGGLEUSDT, HEMIUSDT, HOLOUSDT, HOMEUSDT, HYPEUSDT, KATUSDT, KITEUSDT, LAUSDT, LINEAUSDT, MANTRAUSDT, MEGAUSDT, METUSDT, MIRAUSDT, MITOUSDT, MMTUSDT, MORPHOUSDT, NEWTUSDT, NIGHTUSDT, NOMUSDT, OPENUSDT, OPNUSDT, PLUMEUSDT, PROVEUSDT, PUMPUSDT, RESOLVUSDT (82/92), ROBOUSDT, SAHARAUSDT, SAPIENUSDT, SENTUSDT, SKYUSDT, SOMIUSDT, SPKUSDT, TOWNSUSDT, TREEUSDT, TURTLEUSDT, WALUSDT, WLFIUSDT, XPLUSDT, YBUSDT, ZAMAUSDT, ZBTUSDT, ZKCUSDT, ZKPUSDT. Complete: 281.
6. Average daily spot quote volume over embargo (mean of daily `quoteVolume`, REST `klines interval=1d`, guard-enforced) >= $10,000,000/day. Survivors ≥$10M: 67.
7. Rank descending by average embargo quote volume, take top 60. If fewer than 30 survive, STOP.

Surviving universe (60, size=60, in rank order with embargo avg quote vol, n=92 each):
ETHUSDT 2114679486, BTCUSDT 1689365881, SOLUSDT 637385819, XRPUSDT 491077043, DOGEUSDT 266755380, SUIUSDT 178298979, BNBUSDT 160490731, TRXUSDT 142421414, ADAUSDT 134797758, ENAUSDT 132420208, LINKUSDT 96983498, PENGUUSDT 96122488, UNIUSDT 85133215, AVAXUSDT 59321927, LTCUSDT 58149420, WIFUSDT 57950257, HBARUSDT 53926208, TRUMPUSDT 51690893, AAVEUSDT 51585974, ARBUSDT 48581417, SEIUSDT 48165623, XLMUSDT 46892564, WLDUSDT 37919713, CRVUSDT 35647733, NEIROUSDT 34306587, BCHUSDT 32265341, VIRTUALUSDT 32216797, APTUSDT 29944927, PNUTUSDT 29903264, TAOUSDT 29067304, NEARUSDT 28431089, OPUSDT 27429546, ETHFIUSDT 27162416, DOTUSDT 26328661, CFXUSDT 26276885, LDOUSDT 25268603, SYRUPUSDT 24671722, BIOUSDT 23474601, FETUSDT 22947539, SUSDT 21819186, ONDOUSDT 19847053, BANANAS31USDT 19820886, TIAUSDT 18159221, PENDLEUSDT 17958478, CAKEUSDT 16485271, FILUSDT 15940396, ETCUSDT 15892597, INJUSDT 15007609, EIGENUSDT 14579148, HYPERUSDT 14369052, HUMAUSDT 14367804, POLUSDT 13657402, PAXGUSDT 12995688, RUNEUSDT 12843641, ALGOUSDT 12708991, GALAUSDT 12668027, RENDERUSDT 12521597, ENSUSDT 12393685, AIXBTUSDT 11703180, MEMEUSDT 11339671.

Cut-off: 61st-67th ≥$10M but excluded by top-60 cap (ICPUSDT 11189319, INITUSDT 10986286, LPTUSDT 10521909, MAGICUSDT 10435874, WCTUSDT 10243264, JUPUSDT 10186944, PYTHUSDT 10084288) — not traded, listed for auditability.

All 60 listing dates verified before 2025-06-01 (earliest spot 1d: 2017-2025-05; youngest SYRUPUSDT 2025-05-06, HUMAUSDT 2025-05-26). All have n=92 embargo klines.

Survivorship disclosure: 149 futures symbols from the 495 FULL set have no currently-TRADING spot USDT pair (e.g. 1000*-type contracts, recent listings) and are excluded by the spot filter. Delisted symbols are not enumerable from any Binance-owned source (audit §C limitation). Universe is built from currently discoverable symbols. Do not claim survivorship-free.

Guard: `research/oi_positioning_universe.py` (`EMBARGO_START_MS=1748736000000`, `EMBARGO_END_MS=1756684799999`, `HOLDOUT_START_MS=1756684800000`, `assert_embargo_only`, `assert_embargo_end_bound`), called before ranking; tests `tests/test_oi_positioning_universe.py` (6 passed).

## Windows (fixed, stated before any returns computed)

- Research/screen window: 2021-01-01 .. 2025-05-31 (90-day warm-up allowed before start for percentiles, i.e. metrics from 2020-10-03).
- Embargo: 2025-06-01 .. 2025-08-31 (universe ranking only; no trades).
- Holdout: 2025-09-01 .. 2026-08-31 (latest complete archive month).
- Holdout regime legs: three equal date-thirds, as in prior runs.

Prior experiment windows consulted (overlap disclosure; gate criterion 2 requires only disjointness within this hypothesis family, which holds — first test; overlaps disclosed, not hidden):
2023-01-01..2024-01-01 daily_trend FAIL (no overlap); 2024-01-01..2024-04-01 trend FAIL (no overlap); 2024-04-02..2024-07-01 order_flow FAIL (no overlap); 2024-07-02..2024-10-01 mean_reversion FAIL (no overlap); 2024-10-02..2025-01-01 vwap FAIL (no overlap); 2025-12-03..2026-05-02 cross_sectional_rs_001 FAIL (OVERLAPS, inside); 2026-05-03..2026-06-18 funding F4 FAIL (OVERLAPS, inside); 2026-06-25..2026-08-24 funding F4 orphan NULL (OVERLAPS, inside); 2026-08-24..2026-09-26 funding F1-F3 NULL×3 (OVERLAPS 2026-08-24..2026-08-31, 8d).

## Costs (verbatim reuse, no redefinition)

Project cost stack per round trip (per closed holding, `research/funding_carry.py::apply_costs` math: fees+slippage both sides, TDS on exit notional, tax on max(0, gross-fees-slippage-TDS)):
fee_rate=0.001 per side, slippage_rate=0.001 per side, tax_rate=0.312 (31.2% VDA on gains, no loss offset), tds_rate=0.01 (1% gross-proceeds drag), loss_offset_allowed=false, tds_is_cash_flow_drag=true.
Per-round-trip fixed cost (fees+slippage+TDS) = 0.001×2+0.001×2+0.01 = **0.0140 (1.40% of notional)**. Doubled-cost stress fixed = 0.0180 (1.80%), tax/TDS unchanged. State as number: 0.0140.

## Statistic and bootstrap (Amendment 1 construction)

- Trade-level net return per trade (net of full cost stack above).
- One observation per ENTRY DATE = mean net return of all trades entered that date.
- `trade_returns` in the Module 1 record = per-entry-date means, so the gate's own percentile bootstrap IS the date-cluster bootstrap. No gate edit. Same-day altcoin correlation handled by clustering; trade-level (non-clustered) bootstrap is not used.
- Bootstrap: resample entry dates with replacement, 10,000 samples, seed 20260928 (fixed, recorded). 95% percentile CI.
- Report both entry-date count and underlying trade count. PASS requires gate minimums AND ≥200 underlying trades.
- If holdout <200 underlying trades: verdict NULL_RESULT with note "below pre-registered minimum sample". Writes HYPOTHESIS+RESULT, consumes holdout (F1-F3 precedent). INCONCLUSIVE stays research-level only.
- Minimum trades in holdout: 200.
- Replication: first-half vs second-half of holdout, per prior runs.
- Regime: three equal date-thirds; doubled-cost stress; aggregate by proper compounding, not summation; gross (pre-cost) holdout mean per trade reported for information only.

## Multiple testing (live, not hardcoded)

`candidate_generation/multiple_testing.py::adjusted_threshold(database_path='research/runtime_edge_validation.sqlite3', family='open-interest-positioning-dynamics')` at pre-reg time: HYPOTHESIS count=11, total_tested_including_current=12, method=bonferroni, base_alpha=0.05, **required_alpha=0.0041666667 (~0.05/12)**. Logged from function output; m used = 12.

## Throughput and universe-size fallback (Amendment 1, decided before returns)

Measured trial (research-window metrics, 20 daily zips, sequential): 1.35 files/s, 15.0 KB/s. Projected Stage A (research+warm-up+embargo metrics, 60×1794=107,640 files): 22.1h sequential, **2.8h at 8× concurrency**, 1.4h at 16×. 8h budget holds for top-60. **Decision: top-60 retained; top-40 fallback NOT triggered.** Fallback rule (pre-authorized): only if measured Stage A projection exceeds 8h would top-40 be used, decided from throughput only without looking at any result. Spot 1d via MONTHLY archive zips or REST limit=1000 (few thousand requests), not daily zips. Metrics daily zips with 8-16 connections, backoff on 429/5xx, resumable checkpoint, CHECKSUM every file. Stage A (research+embargo) first for the screen; Stage B (holdout) ONLY after commit AND screen pass.

## Stopping rule (pre-registered; applies to every outcome)

After this task, regardless of the verdict (including PASS), do NOT propose, approve, or run any further new signal class. A human decides what happens next. If the result is FAIL, NULL_RESULT, INCONCLUSIVE, or CLOSED_PRECOST_SCREEN, this is the last new class attempted in this research program. A PASS still requires human review, then paper validation with a liquidity/slippage check on the actual altcoins involved, before anything else. No promotion, no production wiring, no strategy files.

## What this file does not do

No holdout return series was read, computed, or viewed before this freeze. Stage A (research+embargo download) and the pre-cost screen happen strictly after this commit. Stage B (holdout download) happens only if the screen passes. No `strategies/`, `execution/`, `risk/`, or Module 4-8 wiring is touched on any verdict; a PASS here is not a promotion.

## References

- Audit: `docs/results/oi-liquidation-public-archive-coverage-audit.md` (§A schema, §H 495 FULL, §C survivorship limit).
- Menu: `research/hypothesis_menu.sqlite3` (open-interest-positioning-dynamics, human 2026-09-27).
- Ledger: `research/runtime_edge_validation.sqlite3` (24 rows, m=11 pre-test).
- Guard: `research/oi_positioning_universe.py`, `tests/test_oi_positioning_universe.py`.
- Costs: `research/funding_carry.py::apply_costs`, `research/gate_run.py::COSTS`.
- Alpha: `candidate_generation/multiple_testing.py`.
