# Task: Cycle 4 — Class Redefinition + Archive-to-Archive Common Window

## Status: Human-approved, 2026-09-27 — menu update + audit, still no hypothesis

This task has two parts. Part A is a menu/ledger update (human already approved
the redefinition below). Part B is audit-only. Neither part designs a
hypothesis, touches a holdout, or writes a Module 1 gate row.

---

## Part A — Redefine the class and close the liquidation sub-component

### A1. Close the liquidation-intensity component as unavailable

The original class concept ("abnormal OI changes combined with liquidation
intensity") cannot be built: `research/reports/oi-liquidation-public-archive-coverage-audit.md`
confirmed `liquidationSnapshot` is not published at any verifiable path (8
path/stem variants probed, all HTTP 404, absent from Binance's own
`binance-public-data` repo docs) and your own collector's liquidation feed
is 116 symbols inside a single 1.77-hour window — not usable as evidence.

Write a closure record, same treatment and same file convention as
`d1_d3_closure.json`:

```text
research/reports/liquidation_intensity_closure.json

component:        liquidation-intensity (sub-component of proposed
                   open-interest-liquidation-dynamics class)
status:            CLOSED_UNAVAILABLE
reason:            "No evidence-grade liquidation-event history exists.
                    Binance's public archive does not publish
                    liquidationSnapshot at any verifiable path (8 variants
                    probed, all 404). Internal collector coverage is 116
                    symbols confined to a single 1.77h window — not usable
                    as evidence for any holdout. Closed rather than
                    retried on proxy/synthetic liquidation data."
interpretation:    "No statement about whether liquidation-based signals
                    work. This is a data-availability closure for this
                    specific sub-component, not a falsification, and does
                    not close the broader open-interest signal class."
closed_at:         <timestamp>
closed_by:         human-approved, 2026-09-27
```

Do not write this as a Module 1 `edge_validation_records` row — it's a
research-level closure, same as D1–D3. Do not change `m`.

### A2. Add the redefined class through the existing approval mechanism

Call `HypothesisMenu.add_with_approval()`:

```text
signal_class: open-interest-positioning-dynamics
approved_by:  human, 2026-09-27
rationale:    "Redefinition of the originally-proposed
              open-interest-liquidation-dynamics class, narrowed to what
              the data actually supports after the liquidation-intensity
              component was closed unavailable (see
              liquidation_intensity_closure.json). Uses open-interest
              level/change, top-trader long/short ratio, and taker
              buy/sell volume ratio — all confirmed available via
              Binance's public metrics archive (data.binance.vision,
              522/527 symbols, up to 6 years history, 5-minute rows in
              daily partitions) and cross-referenced against archive
              fundingRate/klines. Structurally distinct from every prior
              class: prior classes are price-time-series (breakout,
              scalping, trend, mean reversion, VWAP, order flow, daily
              trend), funding-rate arbitrage (F1-F4), or execution-basis
              arbitrage (D1-D3, closed). This class is a
              derivatives-positioning/crowding signal — it can be built
              to test contrarian positioning (fade extreme long/short
              ratios or extreme OI buildup) rather than a price-momentum
              proxy."
excluded_pattern_check: "Must NOT reduce to 'OI went up, price will go up'
              (that's a relabeled trend/momentum proxy on a different
              input series). The defining mechanism must be positioning
              extremity/crowding relative to the position's own history
              (e.g. long/short ratio or OI level in an unusual percentile
              of its trailing distribution), not simply 'OI increased,
              buy.' If the eventual implementation would produce
              near-identical signals to price-momentum with OI substituted
              for price, it does not qualify as this class."
```

Update `docs/module-status.md`'s Module 15 line to reflect the menu is now 3
classes: funding-rate carry (exhausted), cross-exchange dislocation (closed
unavailable), open-interest-positioning-dynamics (new, pre-registration
pending).

---

## Part B — Archive-to-archive common window (audit only)

The prior audit's three-way common-window figure (333 days, BTCUSDT/ETHUSDT
only) cross-referenced archive OI-metrics against your **internal**
collector's funding/price data — which only covers BTC/ETH. But the archive
itself separately publishes fundingRate (520/527 symbols, confirmed in the
prior audit) and klines broadly. Recompute the common window using
archive-to-archive cross-referencing instead, so the real multi-symbol
breadth is known before a hypothesis is designed.

### Steps

1. For the full 522-symbol metrics universe from the prior audit, determine
   which of those symbols also have archive `fundingRate` (monthly) and
   archive `klines` (choose one interval — 1h — for this pass) coverage,
   using the same verification standard as before (HEAD/GET probes,
   checksum-verify a sample, don't trust listings alone).
2. For each symbol with all three archive datasets (metrics + fundingRate +
   klines), compute: common start date, common end date, continuous-day
   count, internal gaps, lifecycle limitations — same methodology and same
   FULL/PARTIAL/LIFECYCLE-LIMITED/UNAVAILABLE classification as the prior
   audit.
3. Produce updated counts:
   - symbols with ≥90 continuous days of (OI-metrics + archive-fundingRate +
     archive-klines) coverage
   - symbols with ≥180 continuous days
   - symbols with ≥365 continuous days
   - the single largest common window across the full universe, and which
     symbol(s) achieve it
4. Explicitly reconcile against the prior figure: state plainly that the
   previous "333 days, BTC/ETH only" was constrained by internal-DB
   cross-referencing, not by the archive itself, and give the corrected
   archive-native number side by side with it.
5. Sample-verify (download + checksum, as before) 3–5 additional symbol/date
   combinations from this new cross-reference to confirm the fundingRate and
   klines archives are as reliable as the metrics archive was found to be —
   don't assume the earlier verification transfers automatically.

### Output

Update `docs/files/oi-liquidation-public-archive-coverage-audit.md` (or add
a clearly-labeled new section, `## H. Archive-to-archive common window
(supersedes internal-DB-limited figure in §E)`) with the table and the
reconciled factual summary. Do not remove or edit the original §E — append
the correction as its own section, same append-don't-overwrite discipline
used for the cross-sectional aggregate-return fix.

---

## Explicit stop conditions

- Do not design the OI-positioning hypothesis (lookback window, ranking/
  threshold rule, rebalance interval, holding period, cost model) — that is
  a separate, later pre-registration step.
- Do not reserve or touch a holdout window.
- Do not write a Module 1 `HYPOTHESIS` or `RESULT` row.
- Do not call the multiple-testing alpha calculation.
- Do not touch `strategies/`, `execution/`, or `risk/`.
- Do not evaluate any predictive relationship between OI/positioning and
  returns — this task establishes data coverage only.

## When done

Report: the liquidation-intensity closure record, the menu diff (new class,
verbatim rationale and exclusion check), the corrected archive-to-archive
common-window table and counts (≥90/180/365 days), the reconciliation
statement against the prior BTC/ETH-only figure, and the new sample
checksum-verification results. Then stop — hypothesis design requires a
separate task and separate review of this output.
