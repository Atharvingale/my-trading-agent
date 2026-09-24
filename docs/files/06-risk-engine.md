# Module 6: Deterministic Risk Engine

## Purpose
The hard safety boundary. Hermes cannot bypass it. This is the one module where "deterministic" is non-negotiable — no statistical judgment calls, only fixed rules.

## Files to implement
```
risk/
├── engine.py
├── position_sizing.py
└── limits.py
```

## Checks this module must perform on every BUY/SELL decision
- Maximum position exposure (per symbol and portfolio-wide)
- Daily loss limit and drawdown controls
- Leverage and margin constraints
- Stop-loss distance validation
- Exact position-size calculation
- Existing-position and duplicate-order checks
- Cooldown rules (e.g. after a stop-out)
- Liquidity and depth requirements (won't approve a size the book can't absorb)
- Data freshness and completeness requirements (reject decisions built on stale context)
- Kill switch / emergency halt state
- Maximum concurrent positions and total notional limits

## Critical invariant
**The exact quantity approved by `engine.py` must be the exact quantity sent to `execution/` (module 7).** No downstream layer may recalculate or round it independently. Enforce this by making the approved quantity part of a signed/hashed `RiskDecision` object that execution verifies rather than trusts blindly.

## RiskDecision contract
```python
class RiskDecision:
    risk_decision_id: str
    decision_id: str
    status: Literal["APPROVED", "REJECTED"]
    approved_quantity: float
    stop: float
    target: float
    exposure_after: dict
    rejection_reason: str | None
```

## Acceptance criteria
- A decision built on stale/incomplete context (per module 3's staleness flag) is rejected regardless of confidence.
- A unit test proves `approved_quantity` cannot be altered between `RiskDecision` creation and the execution module reading it (e.g. via an immutability check or hash verification).
- Kill-switch activation immediately rejects all pending and future decisions until manually cleared.
- All limits are configuration-driven, not hardcoded, and covered by tests for both the pass and reject path of each check.

## When done
Log to `docs/implementation-log.md`: the exact limit values used at launch, how the kill switch is triggered/cleared, and the quantity-integrity test result.
