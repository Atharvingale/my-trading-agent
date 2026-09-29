# Cycle 5 — Hypothesis Candidates (Design Only)

Status: **DESIGN DOCUMENT, NOT A PREREGISTRATION.** No hypothesis is approved,
no holdout is created or consumed, no backtest was run, no Module 1 record
was written. A human must select (or reject) before anything proceeds.

## 1. Reopening context

The Hermes research program was formally closed at
`4be8e65ab37f884047f7c8574b13397d34bcf0d3` (24 Module 1 ledger rows, m = 11,
0 PASS, 0 production strategies, live trading OFF, 344 tests passing;
close-out finding `research/PROJECT_FINDING.md`) and explicitly reopened by a
human on branch `research/reopen-2026-09` (commit `50e45db`,
`research/RESEARCH_REOPENING_2026-09.md`). This document proposes the first
new hypotheses under the reopened program. Historical results are carried as
stated, not reinterpreted.

Module 1 state at the time of writing (read-only check): 24 ledger rows,
verdict split FAIL 9 / NULL_RESULT 4 / PENDING 11 (PENDING rows are the
HYPOTHESIS events; m = 11), PASS 0, menu 2 additions, review decisions 0.
A future test would be test #12 under the live Bonferroni guard
(`candidate_generation/multiple_testing.py`), i.e. required alpha ≈ 0.05/12
≈ 0.00417 — stated here for planning only; no budget is consumed by this
document.

## 2. Historical mechanisms excluded from rediscovery

Source of each row: `research/PROJECT_FINDING.md` §3, `docs/files/module-status.md`,
`docs/files/implementation-log.md`, `research/reports/*`, `research/hypotheses/*`
(the `edge_validation.sqlite3` / `review_queue.sqlite3` paths named in the task
brief do not exist under those names; the actual stores are
`research/runtime_edge_validation.sqlite3`,
`research/review_queue_funding.sqlite3`,
`research/review_queue_cross_sectional.sqlite3`, and
`research/candidates_funding_xex.sqlite3` — all read, none modified).

| # | Historical mechanism (exact rule tested) | Hypothesis ID(s) | Status | Why it closed | Disguised retry that is prohibited |
|---|---|---|---|---|---|
| H1 | Seeded Breakout (spec-seeded, no holdout) | breakout | FAIL (−27.78%) | Falsified | Any breakout/donchian/volatility-expansion entry on any lookback |
| H2 | Seeded Scalping (spec-seeded, no holdout) | scalping | FAIL (−39.42%) | Falsified | Any short-horizon scalping variant |
| H3 | Breakout filter refinements ×3 | — | NO CREDIBLE EDGE ×3 (2 failed replication) | Regime-dependent beta, not edge | Further filter tweaks on breakout |
| H4 | Hourly EMA(5/20) crossover, next-open execution, 2% stop, 25% sizing, BTCUSDT 1h, holdout 2024-01-01–04-01, 66 trades | trend_following | FAIL (−5.34%, CI entirely negative) | No edge net of costs | EMA/MA crossover on any period, any timeframe variant of the same rule, "trend with different lookback" |
| H5 | Hourly volume-spike breakout (volume > 2.0× prior-20 mean, next-open, 2% stop, 25% sizing), holdout 2024-04-02–07-01, 111 trades | order_flow | FAIL (−10.13%) | Flat pre-cost (−0.00%), costs consumed it | Any spot-volume-spike entry, any volume multiple/threshold |
| H6 | Hourly 1.0σ-below-trailing-20-mean reversion, 2% stop, holdout 2024-07-02–10-01, 96 trades | mean_reversion | FAIL (−9.49%) | Flat-to-negative pre-cost | Any z-score/band mean-reversion on price, any σ threshold or window |
| H7 | Hourly 2.0%-below-trailing-20-VWAP reversion, 2% stop, holdout 2024-10-02–2025-01-01, 16 trades | vwap_reversion | FAIL (−1.13%, below 20-trade minimum) | No edge + thin sample | Any VWAP-distance entry, any window or distance |
| H8 | Daily EMA(5)/EMA(20) crossover, next-daily-open, 2% stop, 25% sizing, BTCUSDT daily, holdout 2023-01-01–2024-01-01, 8 trades | daily_trend_following | FAIL (−1.10%, thin sample) | No sign of life on any probe bar | Daily/weekly timeframe transplants of H4–H7 rules |
| H9 | Funding carry F1 (short perp, trailing-3 mean funding > 0.01%, 1-period hold); F2 (+ calm-vol filter); F3 (mirror long on funding < −0.01%); shared holdout 2026-08-24–09-26 | funding_carry_f1/f2/f3 | NULL_RESULT ×3 (0 qualifying trades) | No signals under thresholds | Same absolute-rate carry with retuned threshold/persistence/period |
| H10 | Funding carry F4 (anomaly fade), disjoint window 2026-05-03–06-18, 24 trades | funding_carry_f4 | FAIL (−38.84% summed, CI entirely negative) | Falsified | Funding fade with different window or lookback |
| H11 | Cross-exchange dislocation D1 (5bps×3 confirmations), D2 (10bps), D3 (20bps×5) | candidates only, no ledger rows | CLOSED_UNAVAILABLE | Executable bid/ask/depth/fees/latency history requires paid vendor; closed, not falsified | Any cross-venue spread trade on proxy/non-executable data |
| H12 | 2-asset (BTC/ETH) daily top-1-of-2 volatility-adjusted 168h-trailing-return rotation, long-only, holdout 2025-12-03–2026-05-02, 121 rotations | cross_sectional_rs_001 | FAIL (−99.90% compounded) | Catastrophic churn + negative drift | Same 2-asset binary ranking, any lookback/rebalance variant; daily-rotation churn engines generally |
| H13 | Liquidation-intensity sub-component | — | CLOSED_UNAVAILABLE | `liquidationSnapshot` unpublished in public archive (8 paths 404); internal collector only 1.77 h / 116 symbols, BTC 5 / ETH 2 events; closed, not falsified | Any liquidation strategy on synthetic/proxy/weakly-equivalent data; any claim about liquidations from non-liquidation observables |
| H14 | OI positioning 5-day: bottom-decile own-90d `sum_toptrader_long_short_ratio` (crowd max-short) → long 5 days, top-60 universe, research screen 381 trades / 99 dates | oi_positioning_001 | CLOSED_PRECOST_SCREEN (gross +0.33%/trade vs 1.40% cost) | Real but small pre-cost signal, consumed by costs; holdout never touched | `OI ↑ → LONG` / `OI ↓ → SHORT`; price-momentum + OI confirmation; same bottom-decile contrarian entry, any lookback/hold variant (a second hold variant already closed as H15) |
| H15 | OI positioning 20-day: same signal, 20-trading-day hold, research screen 169 trades / 70 clusters | oi_positioning_20d_001 | CLOSED_PRECOST_SCREEN + LOW_SAMPLE_SCREEN (gross −0.77%/trade; CI [−0.04418, +0.08373] overlaps H14 — underpowered, not proof of a hold effect) | Screen no-go + thin sample; holdout never touched | Further holding-period variants (10-day, 40-day, …) without fresh human approval (per its own stopping rule) |

Burned holdout ranges (must be avoided by any future preregistration; overlaps
across families require at minimum explicit disclosure per the OI precedent):
2023-01-01–2024-01-01; 2024-01-01–04-01; 2024-04-02–07-01; 2024-07-02–10-01;
2024-10-02–2025-01-01; 2025-12-03–2026-05-02; 2026-05-03–06-18;
2026-06-25–08-24 (orphan, nulled); 2026-08-24–09-26. The OI research window
2021-01-01–2025-05-31 was consumed as a research-level screen and the OI
holdout 2025-09-01–2026-08-31 was never consumed.

## 3. Current data-availability summary

Method: read-only inspection of file manifests, row counts, schemas, and time
bounds. No return series computed, no signals constructed, no holdout touched.
"AVAILABLE" means evidence-grade depth (multi-month, gap-validated where
previously audited) already in the repository or freely re-downloadable from
the documented public archive path.

| Data | Location | Coverage (verified metadata) | Classification |
|---|---|---|---|
| Binance spot 1h OHLCV, BTCUSDT | `research/datasets/klines-btcusdt-1h-v1.json` + `-older-v1` | 8000 + 8000 rows; 2024-11-29–2026-09-26; previously validated 0 gaps, 0 fills | AVAILABLE |
| Binance spot 1h OHLCV, ETHUSDT | `research/datasets/klines-ethusdt-1h-v1.json` | 8000 rows; 2025-10-28–2026-09-26; 0 gaps | AVAILABLE |
| Binance futures funding 8h (rate + mark_price), BTC/ETH | `research/datasets/fund-*-v1.json` + `-older-v1` | 1000 periods each; 2025-10-28–2026-09-26; 0 gaps | AVAILABLE |
| Binance public futures-metrics archive (5-min rows, daily partitions; `sum_open_interest`, `sum_open_interest_value`, `count/sum_toptrader_long_short_ratio`, `count_long_short_ratio`, `sum_taker_long_short_vol_ratio`) | `data.binance.vision` (public); local Stage A checkpoint `data/oi_stage_a/` (research+embargo window, 111,180 jobs) | 522 symbols listed; 507 FULL spans ≥ 90 d, 491 ≥ 180 d; BTCUSDT from 2020-09-01; 6 checksum samples PASS (per `docs/results/oi-liquidation-public-archive-coverage-audit.md`) | AVAILABLE (re-download required per task; only research-window parsed locally) |
| Coinbase spot 1h, BTC/USD + ETH/USD | `research/datasets/coinbase-*-v1.json` | 10500 rows each, ending 2026-09-26; manifest span ambiguous — treat as short/uncertain depth | PARTIAL |
| Kraken spot 1h, XBT/USD + ETH/USD | `research/datasets/kraken-*-v1.json` | 723 rows (~30 d), ending 2026-09-26 | PARTIAL (short) |
| Live collector streams (aggTrade, bookTicker, depth, klines, markPrice, forceOrder, futures analytics, options, breadth, cross-exchange) | `data/market_data.sqlite3` (+ `api_live`, `dynamic_live`, `dynamic_live2`) | ~7 days only (2026-09-22–29); e.g. `forceOrder` 251 events / 116 symbols in one 1.77 h window; `breadth_snapshots` 728 rows / 7 d; feature rows (CVD, depth imbalance, spread) 7 d | INSUFFICIENT for evidence (proves pipeline capability only, not history) |
| Liquidation-event history | nowhere evidence-grade | Archive unpublished; internal 1.77 h thin (BTC 5, ETH 2 events) | UNAVAILABLE (closure H13 stands) |
| Executable cross-exchange quotes/depth/fees/latency history | nowhere | ~4.4 d aggregate disagreement only; no per-venue bid/ask | UNAVAILABLE (closure H11 stands) |
| Options IV/Greeks/positioning history; futures basis history | nowhere | `optionMarkPrice` 12 rows, `optionOpenInterest` 301 rows, `futures/data/basis` 20 rows — all ~21 h live | UNAVAILABLE |
| Altcoin spot/funding price history beyond BTC/ETH | nowhere stored | Would require fresh public-archive downloads in a future task (not done here) | UNAVAILABLE (as stored) |
| Market-breadth / BTC-dominance history | nowhere beyond 7 d live | `breadth_snapshots` 7 d only; breadth recomputation needs altcoin klines (see above) | UNAVAILABLE (as stored) |

 tradable-construction note: the tested execution path is spot long-only
(`paper_trading/portfolio.py`, `runtime/config.py` paper default); any
candidate needing a short leg is designed long-only below, with the missing
side stated as a limitation rather than assumed.

## 4. Economic/cost constraint

The inherited cost stack is fixed and is NOT redefined here: 0.10% fee/side,
0.10% slippage/side, 31.2% VDA tax on gains with no loss offset, 1%
gross-proceeds TDS drag — ≈ **1.40% fixed round-trip per closed holding**
before tax. The close-out's cost attribution showed TDS turnover drag
(16–26% of notional on high-turnover hourly systems) dominating fees/slippage,
with VDA tax small because there were few gains to tax.

Design consequences applied to every candidate below:

* Turnover is the enemy: preference for selective entry (decile/percentile
  filters), multi-day holds, re-entry locks, and hysteresis — so that the
  1.40% toll is paid a few times per year, not hundreds.
* Gross-move plausibility must come from the mechanism itself (climax
  bounces, arb-pressure drift, crash avoidance, flush recoveries are
  historically multi-% phenomena) — never from assumed backtest strength.
* The two prior positive pre-cost readings (+0.38% trend, +0.33%/trade OI-5d)
  were both consumed by the 1.40% toll; candidates target gross moves an
  order of magnitude larger per trade, at far lower frequency.

## 5. Candidate A — Taker-imbalance exhaustion reversal

**Mechanism.** On Binance futures, the signed taker-volume ratio measures
which side is aggressively crossing the spread. Sustained extreme one-sided
taker flow indicates the aggressive side is consuming available liquidity; a
selling climax (extreme taker-sell dominance vs the symbol's own history)
marks capitulation — after which the absence of further sellers allows a
multi-day bounce. Participant chain: late momentum shorts/margin sellers →
aggressor exhaustion → liquidity vacuum upward → spot bounce.

**Economic rationale.** Capitulation-then-bounce is a documented futures-market
pattern: forced and emotional selling clusters in time, while buying is
patient. Fading only the most extreme selling climaxes (not every dip) is
selective by construction.

**Exact observable inputs.** Daily `sum_taker_long_short_vol_ratio` per symbol
= last 5-minute archive row of day D (23:55 UTC), identical dailyization
convention to the frozen OI work (no new timing invention).

**Signal definition.** `pctile(D)` = rank of D's value among strictly prior 90
daily values (D−90..D−1, D excluded; 90 prior days required). Fire when
`pctile(D) ≤ 0.10` (extreme taker-sell dominance). No price condition is
combined with the trigger (keeps it a flow signal, not momentum confirmation).

**Entry rule.** LONG spot at the D+1 daily OPEN of each firing symbol.
Re-entry lock: a symbol already held cannot be re-entered until exited.

**Exit rule.** Exit at the D+6 daily OPEN (5-day hold). No stop-loss, no
discretionary exit (matches the frozen OI timing frame so results are
comparable across classes; a stop would be its own hypothesis).

**Direction.** LONG only.

**Universe.** Top-60 liquid spot-USDT symbols re-derived with the frozen
`research/oi_positioning_universe.py` embargo-ranking method on archive data
in the future preregistration task (method reused, ranking re-run — the H14
60-list is NOT reused blindly).

**Expected turnover.** ~10% of symbol-days fire; with the 5-day re-entry lock,
roughly 5–8 round trips per symbol per year across 60 symbols (a few hundred
trades/year universe-wide, clustered by entry date as in the OI methodology).

**Cost sensitivity.** 5-day climax bounces are multi-% phenomena; a 3–5% gross
bounce clears the 1.40% toll with margin, unlike the +0.33%/trade H14 signal.
Frequency is ~1/4 of H14's per-symbol rate, cutting TDS drag per unit time.

**Required data.** Futures-metrics archive (`sum_taker_long_short_vol_ratio`,
deep history) + spot daily opens for execution. AVAILABLE.

**Look-ahead risks.** Percentile uses strictly prior days; entry at D+1 open
after the D 23:55 row is known; missing days recorded missing, never filled;
UTC alignment validated between metrics partitions and spot candles.

**Historical overlap.** H5 (hourly spot-volume-spike breakout): different
observable (signed futures taker flow vs spot volume level), opposite trade
(reversal vs breakout/continuation), different timeframe (daily vs hourly),
different universe (60-symbol vs BTC-only). H14/H15 (positioning-decile
contrarian): different archive field (taker flow vs top-trader positions),
different mechanism (aggressor exhaustion vs crowded-short bounce).

**Distinctness argument.** No prior hypothesis used any taker-flow field; the
trade is defined by who is crossing the spread, not by price shape, volume
level, or positioning stock. It is not a parameter variation of any H-row.

**Failure modes.** Taker extremes can persist for weeks in strong trends
(climax-first-in-trend whipsaw); futures-taker flow may not transmit to spot;
ratio may be BTC-dominated with thin altcoin signal; 5-day bounces may average
below 1.40% even if directionally right.

**Evaluation design (future task, not this one).** Fresh disjoint holdout;
preregistered 90d/10%/5-day parameters; cluster-by-entry-date bootstrap;
regime thirds; doubled-cost stress; disjoint replication; ≥200-trade minimum
per the H14 precedent. Not executed here.

## 6. Candidate B — Perp–spot basis-pressure timing (BTC/ETH)

**Mechanism.** When the Binance perp trades at an extreme premium to spot,
cash-and-carry arbitrageurs sell perp and buy spot, creating real spot buying
pressure that persists for days; when the premium normalizes, the pressure
ebbs. The trade rides the arb-induced spot drift, not the funding payment.

**Economic rationale.** Cash-and-carry is one of the largest persistent
participant flows in crypto; its spot leg is directional and mechanical, not
sentiment-based.

**Exact observable inputs.** `basis(t)` = `mark_price(t)` / `spot_close(t)` − 1
at each 8 h funding timestamp, for BTCUSDT and ETHUSDT (mark from the funding
datasets, spot from the 1 h klines; both AVAILABLE, gap-free over
2025-10-28–2026-09-26).

**Signal definition.** `z(t)` = (`basis(t)` − trailing-90d median) / trailing-90d
IQR (robust z; strictly prior prints only). Fire LONG the symbol when
`z(t) ≥ 2` (extreme premium).

**Entry rule.** LONG spot at the next hourly open after the firing print.
Re-entry lock while held.

**Exit rule.** Exit at the first hourly open where trailing-print `z < 0.5`
(premium normalized) or after 5 days, whichever comes first. No stop-loss.

**Direction.** LONG only (the discount side would need a short leg; stated as
limitation — the premium side is traded, the discount side is not).

**Universe.** BTCUSDT, ETHUSDT (the only symbols with both mark and spot
history; disclosed 2-asset limitation as in H12).

**Expected turnover.** ~2–5% of 8 h prints exceed z ≥ 2; with the re-entry
lock, roughly 20–40 round trips per symbol per year.

**Cost sensitivity.** Arb-pressure drifts play out over days with gross moves
typically 1–3%; marginal against 1.40% — the weakest gross-vs-cost margin of
the five, stated plainly. Selectivity (z ≥ 2 only) is the compensating lever.

**Required data.** Funding datasets (mark_price) + spot 1 h klines.
AVAILABLE for BTC/ETH only.

**Look-ahead risks.** Basis uses the print-time mark and the contemporaneous
spot close, both known before the next-hour execution; trailing stats exclude
the current print; no interpolated marks.

**Historical overlap.** H9/H10 (funding carry): those collect funding payments
across holding periods keyed to the rate level; this trades spot-price drift
keyed to the perp–spot price spread — different P&L source, different
observable. H11 (cross-exchange dislocation): that is spot-vs-spot across
venues requiring executable multi-venue data (closed unavailable); this is
perp-vs-spot on one venue using stored data.

**Distinctness argument.** No prior hypothesis used basis or mark_price; the
mechanism (arb-flow pressure) was never tested; the P&L comes from spot drift,
not carry.

**Failure modes.** Basis may reflect rate expectations rather than arb
pressure; spot may not follow within 5 days; 8 h grid is coarse; premium
extremes cluster (correlated entries); discount-side edge (if any) is
unharvestable long-only; 2-asset ceiling on sample.

**Evaluation design (future task).** Fresh disjoint holdout within mark+spot
overlap; preregistered z ≥ 2 / 0.5 / 5-day parameters; standard Module 1
machinery (bootstrap CI, regime legs, doubled-cost stress, replication).
Not executed here.

## 7. Candidate C — Cross-asset funding-spread rotation

**Mechanism.** Relative funding heat measures relative speculative crowding:
when BTC funding runs far hotter than ETH funding, BTC longs are relatively
more crowded (and vice versa). The relatively colder asset has less
crowding-induced downside and a funding tailwind; rotate the sleeve to it.

**Economic rationale.** Crowding is relative — capital rotates between majors;
positioning extremes are better measured cross-sectionally (BTC vs ETH) than
against absolute thresholds (which H9 showed produce zero qualifying trades).

**Exact observable inputs.** Per-8h-print funding rates for BTCUSDT and ETHUSDT
(funding datasets, AVAILABLE). `spread(t)` = `rate_BTC(t) − rate_ETH(t)`;
`z(t)` vs trailing-90d median/IQR of the spread (strictly prior prints).

**Signal definition.** Hold the colder asset: BTC when `spread < 0`, ETH when
`spread > 0`, evaluated at 00:00 UTC using the latest print; rotate ONLY when
leadership flips AND `|z| > 1` (selectivity gate against churn — the direct
lesson of H12's 121 rotations).

**Entry rule.** Rotate the full sleeve at the next hourly open after a
qualifying flip.

**Exit rule.** Positions exit only via rotation into the other asset or at
holdout end; plus a hysteresis band (`|z|` must fall below 0.5 before the next
flip can qualify) to suppress whipsaw. No stop-loss.

**Direction.** LONG only (spot sleeve, always in one of the two assets).

**Universe.** BTCUSDT + ETHUSDT (disclosed 2-asset limitation).

**Expected turnover.** Leadership flips with the |z| > 1 gate are infrequent:
order of 10–20 rotations per year — the lowest churn of any rotation design
in this program (H12 did 121 in 150 days).

**Cost sensitivity.** Excellent turnover profile: a handful of 1.40% tolls per
year needs only modest per-rotation drift to clear. The risk is flipped: too
few, too-small relative moves rather than churn.

**Required data.** Funding 8 h histories, BTC + ETH. AVAILABLE.

**Look-ahead risks.** Uses only published prints strictly before evaluation
time; rotation executes at the next hourly open; no print is revised
(mark/funding prints are final).

**Historical overlap.** H9/H10 (absolute-rate carry, single-asset, payment
P&L): this never collects funding — P&L is relative price drift, keyed to the
spread, not the level. H12 (2-asset price-momentum rotation): this ranks
funding spread, not trailing return — the ranking observable and the story
(relative crowding vs momentum) differ entirely, and the |z| > 1 gate exists
specifically to avoid H12's churn failure.

**Distinctness argument.** Relative-funding ranking was never tested; it is not
a threshold/period variation of carry (no payment thesis) nor a lookback
variation of RS (no price input at all).

**Failure modes.** The spread may carry no information about subsequent drift;
one asset may lead persistently (degenerating to buy-and-hold plus churn);
8 h grid misses intra-print dynamics; 2-asset ceiling; absolute funding
extremes (both hot) leave the design agnostic by construction.

**Evaluation design (future task).** Fresh disjoint holdout; preregistered
|z| > 1 / 0.5-hysteresis rules; rotation-level net returns through the standard
gate machinery. Not executed here.

## 8. Candidate D — Crowding-extremity defensive timing (cash when the boat is full)

**Mechanism.** The largest fast drawdowns follow crowded-long unwinds: when
aggregate positioning across the market sits at multi-month extremes with the
crowd max-long, the marginal buyer is exhausted and the path of least
resistance is down. The edge is drawdown avoidance — the sleeve steps to cash
during rare crowded extremes and otherwise holds.

**Economic rationale.** Unwinds are forced and clustered (margin calls beget
margin calls); sidestepping even one major unwind per year dominates the
return arithmetic of an always-in sleeve, at near-zero turnover cost.

**Exact observable inputs.** Per-dayumble: for each of the archive top-60
liquid symbols, `oi_value_pctile(D)` (90d, `sum_open_interest_value`) and
`toptrader_pctile(D)` (90d, `sum_toptrader_long_short_ratio`); gauge
`G(D)` = cross-symbol median of their mean. All archive-native, deep history.

**Signal definition.** Defensive state ON when `G(D) ≥ 0.90` (market-wide
crowding extreme); OFF when `G(D) < 0.75` (hysteresis against whipsaw).
Evaluated at 00:00 UTC on completed daily rows.

**Entry rule.** When defense turns OFF, hold BTCUSDT spot (bought at next
hourly open). When defense turns ON, liquidate to cash at next hourly open.

**Exit rule.** Cash↔BTC transitions ARE the entries/exits (binary timing
sleeve). No stop-loss (the cash state is the stop).

**Direction.** LONG-or-CASH (never short).

**Universe.** Gauge: archive top-60 (re-derived per the frozen method);
sleeve: BTCUSDT spot (the only deep-history price leg; altcoin spot histories
are unavailable as stored — §3).

**Expected turnover.** `G ≥ 0.90` occurs ~10% of days in clusters → a few
round trips per year. Best turnover profile in this document.

**Cost sensitivity.** A handful of 1.40% tolls per year against avoided
drawdowns that are historically 5–20%: the gross-vs-cost arithmetic is the
strongest here IF extremes precede unwinds reliably — which is the stated
main uncertainty, not an assumption.

**Required data.** Archive OI value + top-trader ratios (gauge) + BTC spot 1h
(sleeve). AVAILABLE.

**Look-ahead risks.** Percentiles strictly trailing; state evaluated on
completed rows; transitions execute next open; no gauge revision (archive
partitions are final).

**Historical overlap.** H14/H15 (bottom-decile contrarian entries, always-in,
fade the max-short crowd): this is the opposite tail (top-decile max-long),
opposite action (leave to cash vs enter long), opposite thesis (unwind
avoidance vs bounce harvest), and opposite exposure profile (mostly invested
with rare cash vs always invested). The task brief explicitly permits
"positioning extremity/crowding relative to its own history" as a materially
different OI mechanism; this is that case. It is NOT `OI ↑ → LONG`, NOT
`OI ↓ → SHORT`, and NOT price-momentum-plus-OI-confirmation.

**Distinctness argument.** No prior design used aggregate cross-symbol
crowding, hysteresis timing, or a cash state; the P&L source (avoided loss vs
harvested bounce) differs fundamentally from H14/H15.

**Failure modes.** Extremes may resolve by sideways digestion rather than
unwind (cash drag in bull runs); BTC may not draw down with altcoin crowding;
gauge construction (median-of-means) is a choice the preregistration must
freeze; unwinds are rare → low event count → power concerns (the H15
LOW_SAMPLE lesson applies).

**Evaluation design (future task).** Multi-year archive gauge history gives the
sample that H15 lacked; fresh disjoint holdout; preregistered 0.90/0.75 levels;
event-cluster bootstrap; regime thirds; doubled-cost stress. Not executed here.

## 9. Candidate E — OI-flush recovery participation

**Mechanism.** Sharp aggregate OI-value contractions (deleveraging flushes)
followed by stabilization indicate forced sellers are exhausted and funding
has reset; spot then recovers over days-to-weeks as patient capital re-enters.
The trade enters AFTER the flush is confirmed, harvesting the recovery, never
predicting the flush.

**Economic rationale.** Post-flush V-recoveries are among the largest
short-horizon spot moves in crypto (forced selling is price-insensitive;
its absence is the signal), giving the best per-trade gross-vs-cost ratio
available to a long-only sleeve.

**Exact observable inputs.** Weekly `ΔOI(D)` = 7-day change in aggregate
top-60 `sum_open_interest_value` (archive, deep history incl. BTCUSDT from
2020-09-01); BTC spot daily closes for price confirmation.

**Signal definition.** Flush confirmed when weekly `ΔOI` ≤ 5th percentile of
its trailing-365d distribution AND BTC 7-day return < 0 (price confirms the
flush was real selling, not a data artifact). Both strictly trailing.

**Entry rule.** LONG BTCUSDT at the next daily open after confirmation.
Re-entry lock: one position per flush; new entries require a new confirmation
after exit.

**Exit rule.** Exit 10 trading days after entry at the daily open, or earlier
if weekly `ΔOI` fully retraces the flush (re-leveraging complete). No
stop-loss (the flush already happened; a stop is a separate hypothesis).

**Direction.** LONG only.

**Universe.** BTCUSDT sleeve; gauge over archive top-60.

**Expected turnover.** ~5% of weeks confirm → roughly 2–4 round trips per year.
Ultra-selective.

**Cost sensitivity.** Flush recoveries are historically multi-% to double-digit
over 10 days; even a 5% gross recovery clears 1.40% several times over. The
binding risk is sample size, not cost.

**Required data.** Archive OI value (deep) + BTC spot. AVAILABLE.

**Look-ahead risks.** Weekly ΔOI uses completed partitions only; price
confirmation uses completed closes; entry next open; no revision of archive
partitions.

**Historical overlap and integrity boundary.** H13 closed liquidation-intensity
as UNAVAILABLE and forbade proxy/synthetic liquidation data. This candidate
uses NO liquidation data, makes NO claim about liquidations, and must never be
described as a liquidation strategy: its observables are OI-value change and
price only, both genuine archive/spot data. It differs from H14/H15 (level
percentile entries, always-on universe screening) by trading only post-flush
events (change-based, ~3/year) with price confirmation. The human gate (§12)
should weigh this boundary explicitly.

**Distinctness argument.** Event-driven deleveraging-recovery with price
confirmation was never tested; the trigger (aggregate OI change extreme) is a
different construction from any level-decile signal.

**Failure modes.** Some flushes precede further downside (falling-knife legs);
~2–4 events/year gives a thin sample even over 5 years (~10–20 events — power
must be addressed in preregistration, learning from H15); altcoin-gauge/BTC-
sleeve mismatch; recovery may complete within days (10-day hold gives back
gains — the hold length is a frozen choice, not tunable post hoc).

**Evaluation design (future task).** Multi-year holdout (archive depth allows
it); preregistered 5th-percentile/365d/10-day parameters; event-level
bootstrap with small-sample disclosure; regime legs; stress. Not executed here.

## 10. Candidate comparison matrix

| Candidate | Distinct mechanism | Required data | Historical coverage | Expected turnover | Cost constraint | Look-ahead risk | Main uncertainty |
|---|---|---|---|---|---|---|---|
| A — Taker-imbalance exhaustion reversal | Aggressor-side capitulation fade; signed futures taker flow, reversal, daily, 60-symbol | Archive taker ratio + spot opens | AVAILABLE (deep, 500+ symbols) | ~5–8 round trips/symbol/yr, entry-date clustered | 5-day climax bounces multi-% vs 1.40%; frequency ~1/4 of H14 | Strictly prior 90d; D+1 open; missing never filled | Extremes persist in trends; futures→spot transmission |
| B — Perp–spot basis-pressure timing | Cash-and-carry arb spot-leg drift; spread, not payment | Funding mark_price 8h + spot 1h, BTC/ETH | AVAILABLE (BTC/ETH, 333 d) | ~20–40 round trips/symbol/yr | Weakest margin: 1–3% drifts vs 1.40%; selectivity is the lever | Print-time values only; next-hour execution | Spot may not follow basis; discount side unusable |
| C — Funding-spread rotation | Relative crowding rotation on BTC−ETH funding spread; \|z\|>1 churn gate | Funding 8h, BTC+ETH | AVAILABLE (333 d) | ~10–20 rotations/yr | Excellent: few tolls/yr; risk is too-small moves, not churn | Published prints only; next-hour execution | Spread may be uninformative; persistent leadership |
| D — Crowding-extremity defense | Drawdown avoidance: cash when aggregate crowding ≥ 0.90, hysteresis 0.75 | Archive OI value + top-trader ratios + BTC spot | AVAILABLE (multi-year) | A few round trips/yr — lowest | Strongest arithmetic IF extremes precede unwinds | Strictly trailing percentiles; next-open transitions | Extremes may digest sideways; cash drag; rare events |
| E — OI-flush recovery | Post-deleveraging bounce after confirmed flush + price confirmation | Archive OI value (deep) + BTC spot | AVAILABLE (BTC OI from 2020-09-01) | ~2–4 round trips/yr — most selective | Best per-trade gross (multi-% recoveries vs 1.40%) | Completed partitions/closes; next-open entry | Thin sample (~10–20 events/5y); falling-knife legs |

No score. No ranking. The human decides.

## 11. Rejection / infeasibility reasons

Considered and rejected during design (do not re-propose without new evidence
or new data):

* RSI/MACD/Bollinger/indicator combinations — no market mechanism; indicator
  soup, not a hypothesis.
* Breakout/donchian/volatility-expansion entries — H1–H3 falsified; any
  lookback is a disguised retry.
* Timeframe transplants of H4–H7 (daily/weekly mean-reversion, VWAP, volume
  spikes) — barred by the project-level stopping rule (§2, H8 precedent).
* Broad-universe daily cross-sectional RS — H12 failed at −99.90% with 121
  rotations; widening N keeps the daily-churn engine the cost finding
  indicts. Rejected on mechanism, not just data.
* Retail-herd fade via all-accounts `count_long_short_ratio` — same
  contrarian-decile structure as H14 with a different field; fails the
  materially-different bar. Recorded so it is not mistaken for new.
* OI-level momentum (`OI ↑ → LONG`) and price-momentum + OI confirmation —
  explicitly prohibited disguised retries (H14 ruling).
* Further holding-period variants of H14 (10-day, 40-day, …) — barred by
  H15's own stopping rule without fresh human approval.
* Calm-regime-gated funding carry (F2-style vol filters on carry) — H9
  already tested the calm-filter variant to NULL; no new mechanism.
* Weekend/seasonality/time-of-day effects without participant mechanism —
  data-mining risk, no causal story.
* Options-informed spot timing — options history UNAVAILABLE (12 mark rows,
  301 OI rows, all ~21 h live).
* Liquidation-cascade entries — UNAVAILABLE (closure H13); no proxy data.
* Cross-venue latency arbitrage — UNAVAILABLE (closure H11); no proxy data.
* BTC-dominance / market-breadth rotation — breadth history is 7 d live only;
  recomputation needs altcoin klines not stored. INFEASIBLE as stored.
* Multi-asset funding carry expansion — funding history exists for BTC/ETH
  only. INFEASIBLE as stored.
* Discount-side basis shorts or any short-perp leg — no tested short
  execution path; candidates are long-only by construction, limitation stated.

## 12. Human decision gate

Exactly one of the following may happen next, and only by explicit human
decision:

1. Select at most one candidate (A–E) to formalize into a full
   preregistration (new hypothesis ID, frozen parameters, fresh disjoint
   holdout, data requirements, multiple-testing treatment at m = 11 + 1)
   before any Module 1 evaluation.
2. Request revisions to a candidate's design (which must be re-frozen under
   version control, never edited in place after freezing).
3. Reject all candidates and keep the program in REOPENED-without-hypothesis
   state.

Constraints carried forward: no Module 1 row without preregistration; no
holdout reuse without meeting the gate's disjointness criterion; no menu
change without human approval; no production or live-trading change under any
candidate outcome; the cost stack and Bonferroni discipline are unchanged.

> Human review is required before any candidate becomes a preregistered
> Module 1 hypothesis.
