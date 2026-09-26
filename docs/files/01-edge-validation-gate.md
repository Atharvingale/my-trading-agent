# Module 1: Edge Validation Gate

## Status
Done — the gate machinery is implemented. Current recorded research contains 7 completed experiments and 0 PASS verdicts as of 2026-09-24.

## Purpose
Certify, with pre-registered and out-of-sample evidence, that a **candidate strategy hypothesis** has a real net-of-cost-and-tax edge before it is allowed to become a production strategy.

The gate is a boundary between the AI research plane and the deterministic production plane.

## Candidate sources
A hypothesis may enter this gate from either:

1. a human researcher, or
2. Module 15 Candidate Research & Evolution.

The source does not change the statistical requirements.

## Important distinction

The gate does **not** require an idea to have a PASS merely to exist in the candidate population.

```text
Candidate hypothesis
        ↓
Module 1 validation
        ↓
FAIL / NULL_RESULT / PASS

Only PASS can proceed toward production
```

## Current research state

The existing research record contains 7/7 failed experiments and zero PASS verdicts. Previously tested price-action families remain closed unless a materially new hypothesis class is registered. The currently identified structurally different research directions are the previously documented funding-rate carry and cross-exchange dislocation classes.

## Gate criteria

All existing seven criteria remain binding:

1. Hypothesis and thresholds are registered before the holdout is touched.
2. Holdout data is disjoint from data already used for that hypothesis family.
3. Returns include the project's configured fee, slippage, tax and TDS assumptions.
4. Bootstrap evidence must support a positive net result.
5. Multiple materially different market regimes are tested.
6. Refinements are replicated outside the tuning period.
7. A null result is recorded as final for that hypothesis/holdout rather than retried indefinitely.

When Module 15 is active, the gate also receives the multiple-testing-adjusted acceptance threshold calculated for the current research family/budget.

## New fields to preserve from Module 15

Where available, the edge-validation record should retain:

```text
candidate_id
parent_candidate_id
hypothesis_id
signal_class
source = HUMAN | AI_RESEARCH | TRADE_LEARNING
provider_used
multiple_testing_family
```

These fields are research provenance only. They do not weaken the gate.

## Production promotion boundary

A PASS is necessary but not sufficient for production.

```text
PASS
  ↓
human review / approval
  ↓
immutable StrategyVersion
  ↓
Module 4
```

## Acceptance criteria

- Module 4 still refuses candidates without PASS.
- A Module 15-generated hypothesis can be submitted exactly like a human-generated hypothesis.
- The gate retains complete provenance back to the originating candidate and parent candidate where applicable.
- Previously failed hypotheses cannot be silently retried against the same holdout.
