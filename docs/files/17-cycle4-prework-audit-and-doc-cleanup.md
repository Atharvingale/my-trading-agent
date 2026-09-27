# Task: Cycle 4 Pre-Work — Documentation Cleanup + OI/Liquidation Data Audit

## Status: Human-approved, audit only — no hypothesis, no holdout, no new ledger test

This task does NOT design, pre-register, or run a new hypothesis. It produces
two things only: (1) corrected/clarified documentation on the existing
record, and (2) a factual coverage report that a human will use to decide
whether OI/liquidation dynamics is even viable as Cycle 4's hypothesis. If at
any point you find yourself writing a hypothesis, touching a holdout, or
computing a bootstrap CI — stop, that is out of scope for this task.

---

## Part A — Fix the cross-sectional-relative-strength record

### A1. Recompute the aggregate return correctly

The recorded Step 7 result for `cross_sectional_rs_001` reported a regime
breakdown of -29.65% / -99.58% / -64.53% and an "aggregate" of -193.76% — that
aggregate was produced by simple addition of the three regime returns. For an
unlevered long-only book this is not a valid cumulative return (true
cumulative return cannot go below -100%). Recompute the aggregate by proper
chaining: `(1 + r_regime1) * (1 + r_regime2) * (1 + r_regime3) - 1`, using the
actual per-regime decimal returns already computed (not re-deriving them).

- Do not touch the underlying trade-level data, the bootstrap CI, or the
  FAIL verdict itself — the verdict stands. Only the headline aggregate
  figure is being corrected.
- Update `research/reports/` and the ledger's RESULT row's aggregate-return
  field with the corrected value, and add a note field:
  `aggregate_return_corrected: true, method: "compounded, not summed",
  original_reported_value: -193.76%`. Do not delete the original value —
  append the correction, since `edge_validation_records` is append-only for
  RESULT rows too (add a superseding annotation, don't rewrite history).

### A2. Check whether the same bug affected prior aggregate figures

Check how the aggregate-return figure was computed for F4 (-38.84%), the
Phase 0 breakout/scalping results (-27.78% / -39.42%), and the VWAP reversion
and daily-trend-probe results. For each: state whether the aggregate was
computed by proper compounding or simple summation across trades/regimes. If
any used simple summation, do NOT recompute the verdict retroactively as part
of this task — a wrong-but-still-clearly-negative headline number doesn't
change any of those FAILs. Just report which ones (if any) have the same
issue, so a human can decide whether those records also need a correction
note. Do not modify those records without separate approval.

### A3. Add the universe-size caveat

Add an explicit note field to the `cross_sectional_rs_001` RESULT record and
to `docs/module-status.md`'s relevant line:

```text
scope_caveat: "This FAIL applies to the 2-asset (BTC, ETH) variant of
cross-sectional-relative-strength only. With only 2 symbols, ranking
collapses to a binary switch and is a weak instance of the general
cross-sectional class. A future attempt with a broader universe (10+ symbols)
is a new, distinct pre-registration requiring its own fresh disjoint
holdout — not a forbidden retry of this same hypothesis_id or family."
```

---

## Part B — Document the D1–D3 discrepancy

Write `docs/files/D1-D3-NOTE.md` (or append to `implementation-log.md` if
that's the project's convention) stating plainly, for future agents:

```text
D1-D3 (cross-exchange dislocation) never existed as rows in
edge_validation_records. They were research-level findings only
(candidates DB + dislocation.evaluate_sufficiency), never promoted to a
Module 1 gate record, because the gate correctly refused to accept an
INCONCLUSIVE-for-missing-data verdict as a valid gate row type. The
CLOSED_UNAVAILABLE closure (research/reports/d1_d3_closure.json,
2026-09-27) is the authoritative and only record of this. Do not search
edge_validation_records for D1-D3 rows — they are not there and this is
expected, not a data-loss bug.
```

---

## Part C — Audit OI + liquidation data coverage (facts only, no judgment call baked in)

Query the actual stored data — do not estimate or assume. Produce
`docs/files/oi-liquidation-coverage-audit.md` with, at minimum:

1. **Symbols with any OI history at all** — full list.
2. **Per symbol**: OI history start date, end date, bar interval(s)
   available (5m/1h/etc.), number of gaps >1 interval, total bar count.
3. **Per symbol**: liquidation-event coverage — start date, end date, event
   count, and whether this is raw per-liquidation event data or an
   aggregated/bucketed feed. State explicitly if liquidation data is thin,
   proxy-derived, or actually absent for a symbol despite OI being present —
   don't let a symbol with OI-only get miscounted as having liquidation
   coverage.
4. **Per symbol**: funding coverage start/end date (for cross-referencing
   with existing funding work).
5. **Common overlapping window**: the largest contiguous date range for
   which OI + liquidation + funding + price data ALL exist simultaneously,
   across however many symbols overlap in that window.
6. **Count of symbols with ≥90 days of full (OI+liquidation+price) coverage**,
   and separately **≥180 days**.
7. **Missingness summary**: % of expected bars missing per symbol per data
   type, not just "some gaps exist."

### Explicit output at the end of the audit file

State plainly, as a factual summary (not a go/no-go decision — that's the
human's call):

```text
- N symbols have ≥90 days of full coverage: [list]
- N symbols have ≥180 days of full coverage: [list]
- Largest common overlapping window across all covered symbols: [dates]
- Liquidation data type: [raw event feed | aggregated/bucketed | absent for
  some symbols]
```

---

## Explicit stop conditions for this task

- Do not design a hypothesis for OI/liquidation dynamics.
- Do not touch, define, or reserve a holdout window.
- Do not write a new HYPOTHESIS or RESULT row to `edge_validation_records`.
- Do not call `multiple_testing.py`'s alpha calculation — there is no test
  being run yet.
- Do not add anything to `hypothesis_menu.py` — OI/liquidation dynamics is
  not approved as a menu class yet; that approval (Step 2 of the Cycle 4
  sequence) happens only after the human reviews this audit.
- Do not touch `strategies/`, `execution/`, or `risk/`.

## When done

Report: the corrected cross-sectional aggregate figure (Part A1), which
prior experiments (if any) share the same aggregate-computation issue
(A2, findings only, no changes made), confirmation that A3's scope caveat
and Part B's D1-D3 note are written, and the full coverage audit table from
Part C with its factual summary. Then stop — do not proceed to hypothesis
design without separate approval on this audit.
