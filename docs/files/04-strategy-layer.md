# Module 4: Strategy Proposal Layer

## Status
**Already implemented.** This revision clarifies its role; it is not the AI research engine.

## Purpose
Generate BUY/SELL/HOLD proposals from `MarketContext` using **immutable, gate-approved production strategy versions**.

This module is the bridge from the research/evolution plane into the deterministic production trading plane.

## What Module 4 does NOT do

- It does not invent strategies.
- It does not mutate strategy parameters.
- It does not call an LLM.
- It does not accept raw candidate hypotheses.
- It does not bypass the Edge Validation Gate.

Those responsibilities belong to Module 15.

## Existing implementation contract

Keep the existing `StrategyProposal` contract:

```python
class StrategyProposal:
    proposal_id: str
    strategy_id: str
    strategy_version: str
    edge_validation_record_id: str
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    evidence: list[dict]
    horizon: str
    invalidation_conditions: list[str]
    timestamp: datetime
```

## Strategy status

```text
Production strategy versions:
    none currently approved as of 2026-09-24

Historical failed families:
    Breakout
    Scalping
    Trend Following
    Mean Reversion
    VWAP Reversion
    Order Flow
    Daily Trend probe
```

Do not create placeholder production strategy files merely to make the Decision Engine produce BUY/SELL output.

## New integration rule

Module 15 may produce a `CandidateStrategyVersion`, but Module 4 may consume it only after:

```text
PASS edge_validation_record
+
explicit human approval
+
immutable production version created
```

At that point the version receives the same loader treatment as any other approved production strategy.

## Recommended adapter boundary

Keep existing Module 4 code intact and add only a narrow promotion adapter if needed:

```text
candidate_generation/review_queue.py
        ↓
strategy promotion adapter
        ↓
strategy_versions record
        ↓
strategies/<approved_strategy>.py or equivalent runtime registration
        ↓
existing strategies/registry.py
```

The existing gate check in `strategies/registry.py` remains authoritative.

## Acceptance criteria

- Existing Module 4 tests remain green.
- An unapproved candidate cannot be loaded.
- A PASS without human approval cannot be loaded.
- An approved immutable production version can be loaded using the existing gate-aware registry.
- No LLM call is present in the proposal path.
