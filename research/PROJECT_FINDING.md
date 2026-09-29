# Project Finding: Edge-Validation Research Program — Close-Out (2026-09-29)

A finding, not a proposal. This document states what was built, what was
tested, how, and what the evidence shows. It recommends nothing. Whether
anything follows, and what, belongs to a human. This is the last document
of this research program unless a human explicitly reopens it.

This supersedes `research/PROJECT_FINDING.md` as written 2026-09-24, which
covered only the first seven experiments. That version's figures are
preserved below, not rewritten.

## 1. What this project set out to do

Build an autonomous crypto-trading research pipeline with a statistically
rigorous gate between any idea and production trading: every hypothesis
pre-registered before its holdout is touched, tested on a fresh disjoint
holdout, judged net of fees/slippage/India VDA tax/TDS, with bootstrap
confidence intervals, multiple-testing correction, regime legs, doubled-cost
stress, disjoint replication, and one final append-only verdict — so that no
idea can reach production wiring without positive out-of-sample evidence.

## 2. What was built

Real, working, tested infrastructure — stated as done per the module-status
history, not aspirational. The research outcome in §4 does not diminish it:

- Market-data layer (Module 2): async persistence off the hot path, bounded
  fan-out, loopback-default + token/TLS gate, retention, authoritative
  universe, 24 hardening tests.
- Hermes observer + context builder (Module 3): deterministic
  `MarketContext`, fail-closed validity, regime classification.
- Strategy proposal scaffolding + decision engine (Modules 4–5): complete,
  tested, and correctly idle — zero wired strategies, production output
  HOLD — because the gate never produced a PASS.
- Deterministic risk engine (Module 6): sealed quantities, kill switch.
- n8n execution boundary (Module 7): signed idempotent submit, ledger,
  reconciliation.
- Order/position/trade lifecycle (Module 8), trade-intelligence + learning
  (Module 9), unified memory model (Module 10), asyncio supervisor
  (Module 11), testing harness (Module 12), security bar (Module 13).
- Candidate-generation loop (Module 15): hypothesis menu with approvals,
  Bonferroni multiple-testing guard reading the live ledger, review queue,
  env-swappable provider client.
- Paper-trading simulator: deterministic fills, long-only portfolio,
  replayable engine.
- Audit/reproducibility tooling: `scripts/verify_artifacts.py` (standing
  persistence check), SHA-256 dataset freezing, checksum-verified archive
  downloads, append-only ledgers. Full suite: 344 tests passing.

## 3. Every hypothesis tested, in one table

Costs everywhere below: 0.10% fee/side, 0.10% slippage/side, 31.2% VDA tax
on gains with no loss offset, 1% gross-proceeds TDS drag (≈1.40% fixed
round-trip before tax). Verdicts are final for their hypothesis/holdout.

| Signal class | Hypothesis id | Holdout window | Trades | Net result | Verdict |
|---|---|---|---|---|---|
| Breakout (Phase 0, seeded) | breakout | — (no holdout) | — | −27.78% | FAIL |
| Scalping (Phase 0, seeded) | scalping | — (no holdout) | — | −39.42% | FAIL |
| Breakout filter refinements ×3 (Phase 0b) | — | — | — | all NO CREDIBLE EDGE; 2 caught failing replication (regime-dependent beta, not real edge) | NO CREDIBLE EDGE ×3 |
| Trend following (hourly) | trend_following | 2024-01-01–04-01 | 66 | −5.34%, CI [−1.73%, −0.67%] | FAIL |
| Order flow (hourly) | order_flow | 2024-04-02–07-01 | 111 | −10.13%, CI [−1.64%, −1.22%] | FAIL |
| Mean reversion (hourly) | mean_reversion | 2024-07-02–10-01 | 96 | −9.49%, CI [−1.86%, −1.23%] | FAIL |
| VWAP reversion (hourly) | vwap_reversion | 2024-10-02–2025-01-01 | 16 | −1.13%, CI [−1.85%, −0.30%] | FAIL |
| Daily trend probe | daily_trend_following | 2023-01-01–2024-01-01 | 8 | −1.10%, CI [−3.27%, −0.15%] | FAIL |
| Funding carry F1–F3 | funding_carry_f1/f2/f3 | shared holdout | 0/0/0 | no qualifying trades | NULL_RESULT ×3 |
| Funding carry F4 (anomaly fade) | funding_carry_f4 | disjoint window | 24 | −38.84%, CI [−2.36%, −0.96%] | FAIL |
| Cross-exchange dislocation D1–D3 | — | — | — | paid-vendor-only data required | CLOSED_UNAVAILABLE |
| Cross-sectional relative strength (2-asset BTC/ETH) | cross_sectional_rs_001 | 2025-12-03–2026-05-02 | 121 | −99.90% compounded (see correction note) | FAIL |
| Liquidation-intensity component | — | — | — | absent from Binance public archive | CLOSED_UNAVAILABLE |
| OI positioning, 5-day hold | oi_positioning_001 | — (screen only) | 381 / 99 dates | gross +0.33%/trade vs 1.40% cost | CLOSED_PRECOST_SCREEN |
| OI positioning, 20-day hold | oi_positioning_20d_001 | — (screen only) | 169 / 70 dates | gross −0.77%/trade vs 1.40% cost | CLOSED_PRECOST_SCREEN |

Provenance notes, stated plainly rather than hidden:

- Phase 0b refinements: reported here as stated in the program record (three
  filter variants, none credible, two failing replication). No separate JSON
  artifact for Phase 0b was found in `research/reports/` during close-out
  verification, so this row is carried as stated, not re-verified.
- Seeded Breakout/Scalping figures (−27.78%/−39.42%): carried from the
  2026-09-24 finding; seeded from the spec with no holdout; computation
  method not re-audited.
- F4 −38.84%: the simple sum of 24 per-trade net fractions, per the shared
  gate math (`research/gate_run.py`), which sums per-trade fractions for
  every funding run. It was not re-audited for a compounding
  interpretation. The verdict does not hinge on the distinction: the CI is
  entirely negative either way.
- Cross-sectional correction: the recorded −193.76% headline was produced by
  adding three regime-leg figures and is not a valid cumulative return for
  an unlevered long-only book (which cannot go below −100%). Recomputed by
  proper chaining to **−99.90%**. The original value is preserved in its
  artifact (`research/reports/cross_sectional_rs_gate_run.json`), marked
  superseded, not deleted. Trade data, CI, legs, stress, and FAIL verdict
  are unchanged. Scope caveat from the record: the FAIL covers the 2-asset
  BTC/ETH variant only.
- Hourly-runner aggregates (trend/order-flow/mean-reversion/VWAP/daily):
  computed in code as the mean of per-window net returns
  (`edge_validation/runner.py`), a different construction from the
  cross-sectional regime-sum headline above. Verdicts are unaffected in all
  cases (CIs entirely negative, far from zero).
- Cost attribution (same-trade diagnostic, timing held fixed): pre-cost
  Trend +0.38% (CI straddles zero), Order Flow −0.00%, Mean Reversion
  −0.11%. TDS turnover drag dominated (16–26% of notional), then
  fees/slippage; VDA tax was small because there were few gains to tax.

## 4. The central finding

- Every signal class that could be evidence-gradely tested under this
  project's data constraints showed either no signal, a signal too small to
  clear transaction costs, or was closed for lack of verifiable historical
  data. Zero PASS verdicts across the program; `m = 11` tested hypotheses.
- The two tests that reached a measurable positive pre-cost edge —
  cross-sectional RS and OI-positioning 5-day (+0.33%/trade gross) — both
  showed a real but small pre-cost signal that a ~1.4% round-trip cost,
  dominated by India's 1% TDS charged per trade rather than by fees or
  slippage, fully consumed.
- The 20-day holding-period test does NOT strongly demonstrate that longer
  holding makes things worse, and must not be cited that way. Its
  date-cluster CI was **[−0.04418, +0.08373]** around a −0.77% point
  estimate, which overlaps heavily with the 5-day test's CI of
  **[−0.02482, +0.02905]** around +0.33%. Its sample — 70 entry-clusters —
  was below the pre-registered informative-sample bar of 80
  (`LOW_SAMPLE_SCREEN`). The honest reading, stated as a correction to any
  stronger claim: this test was underpowered to distinguish
  holding-period effects, not proof of a negative one.
- Net conclusion: the limiting factor found across this program is
  structural — transaction-cost/tax drag relative to the size of the
  available signals — not a shortage of tested ideas or lax methodology.

## 5. What would need to change for this to be worth revisiting

Factual list of conditions, not a plan. None of these is approved,
recommended, or underway:

- A materially lower effective transaction-cost/tax regime. Note: tax and
  domicile questions are legal questions — a tax professional should be
  consulted for anything in this category. No tax strategy is drafted here.
- A signal source not yet tested that is both structurally distinct from
  every falsified/closed class and backed by evidence-grade historical
  data. None is currently identified; if none exists, that is the answer.
- A larger, more liquid, or differently-costed venue/instrument set than
  Binance spot USDT under the current cost stack.
- Materially longer OI-positioning history (current archive depth: daily
  metrics partitions from 2021-12-01 for then-listed contracts, BTCUSDT
  from 2020-09-01; less for most altcoins) to re-run the 20-day-hold test
  with a properly powered sample instead of the underpowered 70-cluster
  result above.

## 6. What stays available regardless of this finding

The paper-trading simulator, the market-data layer, the full Module 1–13
gate infrastructure, and the audit/reproducibility tooling
(`verify_artifacts.py`, checksum-verified data pipeline, frozen
pre-registrations, append-only ledgers) are reusable for any future
direction, including non-trading ones, without rework.

## 7. Process notes (brief, factual)

- One arithmetic bug found and fixed mid-program: headline aggregates built
  by simple summation instead of compounding (cross-sectional −193.76% →
  −99.90%). Scope checked against the other experiments' figures (see §3
  provenance notes); no verdict changed.
- One data-holdout-contamination incident: an embargo-window fetch used an
  inclusive end date and pulled the first holdout day's spot opens into a
  volume average. Caught before any hypothesis was scored, the ranking was
  discarded, and a hard code guard (`assert_embargo_only`, tested) enforced
  the boundary before the clean rerun.
- One file-persistence incident: untracked report files were lost to a
  manual directory move. Root-caused (untracked files + no commit),
  resolved by committing the documentation/report/ledger layer to git and
  adding the standing `verify_artifacts.py` check run at the start of every
  subsequent task.
