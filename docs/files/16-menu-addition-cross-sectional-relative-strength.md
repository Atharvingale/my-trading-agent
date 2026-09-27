# Task: Close D1–D3, Add Cross-Sectional Relative Strength, Run Module 1

## Status: Human-approved, not yet executed (2026-09-27)

## Read this whole file before touching any code, data, or the ledger.

This is not a general "explore new strategies" prompt. It is a narrow, sequenced
task with hard stop conditions. Every step below has an explicit order. Do not
reorder, skip, merge, or "helpfully" extend scope. If any step's precondition
isn't met, stop and report — do not improvise a workaround.

---

## Step 0 — Inspect before acting

Before changing anything:

1. Read the current `edge_validation_records` table (or its file-backed equivalent) in full. Confirm the current state matches: 
   - F1–F3 funding: `NULL_RESULT`
   - F4 funding anomaly fade: `FAIL`
   - D1–D3 cross-exchange: `INCONCLUSIVE`
   - Ledger count `m = 10`
   - 0 `PASS` records, 0 approved production strategies
2. Read `candidate_generation/hypothesis_menu.py` in full. Confirm the current approved list is exactly `funding-rate carry` and `cross-exchange dislocation`, both already exhausted per (1).
3. Read `docs/EXPERIMENT_REGISTRY.md` (or wherever prior experiment date ranges are logged) and list every date range already used as a holdout or tuning period in ANY prior experiment, crypto or NSE. You will need this list in Step 4.
4. Confirm what multi-symbol market data actually exists in storage right now (table name, symbols covered, date range, bar interval, gaps). Do not assume — query it.

If any of (1)–(4) don't match what's expected, stop and report the
discrepancy before proceeding. Do not "fix" the ledger yourself.

---

## Step 1 — Close D1–D3 as unavailable (not FAIL)

`edge_validation_records` is append-only — do not edit or delete the existing
D1–D3 row. Add a new closing record that supersedes it:

```text
candidate_id:      <existing D1-D3 candidate id>
signal_class:      cross-exchange-dislocation
status:            CLOSED_UNAVAILABLE
superseded_status: INCONCLUSIVE
reason:            "Required historical executable bid/ask/depth/fees/latency
                    evidence is not available without a paid vendor feed
                    (e.g. Tardis, CoinMetrics, Amberdata). No existing project
                    credential or budget covers this. Closed rather than
                    retried on proxy/synthetic data."
interpretation:    "No statement about whether the underlying strategy works.
                    This is a data-availability closure, not a falsification."
closed_at:         <timestamp>
closed_by:         human-approved, 2026-09-27

```

Do this closure regardless of what happens in the rest of this task — it does
not depend on the new hypothesis's outcome. Update `docs/module-status.md`'s
Module 1 row to reflect the closure. Do not change `m` for this step; closing
an already-counted INCONCLUSIVE record is not a new hypothesis test.

---

## Step 2 — Add the new class through the existing approval mechanism

Call the existing `HypothesisMenu.add_with_approval()` (or equivalent) to add:

```text
signal_class: cross-sectional-relative-strength
approved_by:  human, 2026-09-27
rationale:    "Structurally distinct from every previously tested class.
              Prior classes (breakout, scalping, trend following, mean
              reversion, VWAP reversion, order flow, daily trend, funding
              carry, cross-exchange basis) are all single-asset time-series
              tests: one asset's own historical behavior. This class ranks
              many assets against each other, contemporaneously, at each
              rebalance point — a cross-sectional design, not a time-series
              one."
excluded_pattern_check: "Must NOT reduce to trend-following on a single
              asset. The defining mechanism is relative ranking across the
              universe at each rebalance point, not 'buy assets whose own
              price went up.' If the eventual implementation would produce
              similar signals to a single-asset momentum/trend filter with
              the cross-sectional step removed, it does not qualify and must
              not be tested as this class."

```

Do not let the candidate generator (or any LLM call) pick the exact
hypothesis parameters. The class is approved as a category only. Step 3 below
is a fixed, human-reviewed pre-registration — not an LLM draft.

---

## Step 3 — Pre-register exactly one hypothesis (before touching holdout data)

Freeze every one of the following before any holdout data is read for this
hypothesis. Write it to `research/hypotheses/cross_sectional_rs_001.md` (or
equivalent) as a standalone, timestamped, immutable file — this file must
exist and be committed/logged before Step 5 acquires or touches the holdout.

Required fixed fields:

- **Universe**: exact symbol list or exact rule generating it (e.g. "top N Binance USDT perpetuals by 30-day average notional volume, recomputed at each rebalance, survivorship-bias-free — a coin delisted mid-period stays in the historical ranking for the periods it was actually tradeable").
- **Eligibility / liquidity filter**: exact minimum volume/listing-age threshold, stated as a number, not "sufficiently liquid."
- **Trailing-return lookback window**: exact bar count/duration (e.g. "72 hourly bars," not "recent performance").
- **Ranking method**: exact formula (e.g. raw trailing return, or volatility-adjusted trailing return — pick one and state which).
- **Portfolio construction**: exact quantile/count for the long group, and explicitly resolve whether the short leg is implemented at all. Spot-only execution cannot short — if the account/execution layer is spot, state this hypothesis as long-only top-quantile rotation vs. the universe mean or vs. cash, not long/short market-neutral. Do not silently assume futures shorting is available; check the actual execution config from Step 0.4.
- **Rebalance interval**: exact frequency (e.g. daily at 00:00 UTC).
- **Holding period**: exact rule for when a position is closed/rotated.
- **Cost model**: the project's existing fee/slippage/VDA-tax/TDS assumptions, applied per rebalance turnover — reuse the existing cost model from prior experiments verbatim, do not redefine it.
- **Hold-out window**: see Step 4 — must be filled in only after Step 4's disjointness check, then frozen here before Step 5.

Once written, this file does not change. If the design turns out to be
unworkable (e.g. required data doesn't exist), abandon this hypothesis_id and
pre-register a new one — never edit a registered hypothesis after the fact.

---

## Step 4 — Fresh, untouched holdout

1. From the list gathered in Step 0.3, identify a candidate holdout window that does not overlap any previously-touched date range for ANY prior experiment (single-asset overlap still matters here for intellectual honesty even though the gate's minimum requirement is only family-disjointness).
2. Select the window by a pre-stated rule, not by inspecting how the hypothesis performs in candidate windows first (that would be exactly the snooping pattern already caught once in this project's 5c reward-tuning round). A reasonable rule: "the most recent contiguous period of at least N months for which full universe data exists and which has not been used as a holdout in any prior experiment." State the rule and the resulting date range in the pre-registration file from Step 3 before any return series from that window is computed or viewed.
3. Confirm the window spans more than one volatility/trend regime if possible; if it can't (e.g. only one regime's worth of clean data exists), say so explicitly rather than silently testing on a single regime.

---

## Step 5 — Acquire and validate data (reuse, don't rebuild)

- Reuse the existing stored multi-symbol OHLCV/candle data confirmed in Step 0.4. Do not build a new acquisition/provider module for this — the whole point of this class is that your existing data layer already covers it.
- Validate coverage for the exact universe and window from Steps 3–4: no silent gaps, no forward-filled prices standing in for missing bars, survivorship bias explicitly checked (delisted/low-volume coins during the window are not silently excluded from the historical universe).
- If validation finds the existing stored data doesn't actually cover what Step 3 assumed, stop, revise the pre-registration (as a new hypothesis_id, per Step 3's rule), and re-check disjointness — do not patch around a data gap with synthetic or interpolated values.

---

## Step 6 — Dynamically compute the multiple-testing threshold

Read the current `m` from the live ledger (post Step 1's closure — closing
D1–D3 does not increment `m`, so this should still read the pre-existing
count plus this being test #11). Compute the required significance level via
the project's existing Bonferroni method in `multiple_testing.py` — do not
hardcode 0.05/11; call the actual function so the value is verifiably derived
from the real ledger state at run time. Log the computed alpha and the `m`
it was computed from.

---

## Step 7 — Run Module 1

Run the existing Module 1 pipeline unchanged: pre-registered thresholds
(from Step 3/6), the frozen holdout (Step 4/5), fee/slippage/tax-adjusted
bootstrap CI, regime check across whatever regimes the window contains,
stress test, replication check. Do not add new gate logic for this
hypothesis — it goes through the identical machinery every prior hypothesis
went through.

Record the result as exactly one of `PASS`, `FAIL`, `NULL_RESULT`,
`INCONCLUSIVE`, with the same evidentiary detail (trade count, aggregate
return, bootstrap CI bounds) as every prior ledger entry.

---

## Step 8 — Preserve everything else

- Do not modify, delete, or renumber any existing `edge_validation_records` row (F1–F4, D1–D3, or the D1–D3 closure record from Step 1).
- Do not touch `strategies/`, `execution/`, `risk/`, or any Module 4–8 wiring, regardless of the Step 7 result. A PASS here is not sufficient for promotion — it still requires separate human review and an explicit promotion step this task does not include.
- Update `docs/module-status.md` and append to `docs/implementation-log.md`: what was closed (D1–D3), what was added to the menu, the pre-registration file path, the computed alpha and `m`, and the final verdict.

---

## Step 9 — Full verification before declaring done

- Run the complete existing test suite; report the pass count against the last known baseline (currently 338 passing per the current repository baseline) — any drop is a stop condition, not something to silently patch.
- Run a diff of everything touched in this task against the pre-task state. The diff should show: one new closure record, one menu addition, one new pre-registration file, one new ledger entry, and doc updates. If the diff shows changes to `strategies/`, `execution/`, `risk/`, or any prior ledger row, stop — that is out of scope and must be reverted.
- Confirm no new external dependency was added without being logged as a decision per the coding-conventions file.

---

## Explicit prohibitions (violating any of these invalidates the run)

- No fabricated, synthetic, or interpolated data standing in for a genuine gap.
- No silently reusing OHLCV as a proxy for the cross-exchange execution data that blocked D1–D3 — that closure stands as unavailable, full stop.
- No LLM-in-the-loop decision on the hypothesis's exact parameters — Step 3 is fixed by this document.
- No re-labeling a single-asset momentum signal as "cross-sectional" by adding a thin ranking wrapper around it — see the exclusion check in Step 2.
- No promotion, wiring, or production-path change on any verdict, including PASS.
- No retrying this same hypothesis_id against a different holdout if it fails — a new holdout requires a new hypothesis_id and a fresh disjointness check.

## When done

Report back: the D1–D3 closure record, the menu diff, the pre-registration
file content, the computed alpha and `m`, the holdout window and why it was
chosen, the Step 7 verdict with full evidentiary detail, the test-suite
result, and the full diff from Step 9.