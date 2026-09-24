# Module 4: Strategy Proposal Layer

## Purpose
Generate BUY/SELL/HOLD proposals from `MarketContext`. **This module may only load a strategy that has a `PASS` verdict in the Edge Validation Gate's registry (module 1).** It must check this at load time, not just at design time.

## Current gate status (see module 1 for full detail)
| Strategy | Status |
|---|---|
| Breakout | FALSIFIED — do not implement |
| Scalping | FALSIFIED — do not implement |
| Trend Following | Not yet gated — implement only after it passes module 1 |
| Mean Reversion | Not yet gated — implement only after it passes module 1 |
| VWAP Reversion | Not yet gated — implement only after it passes module 1 |
| Order Flow | Not yet gated — implement only after it passes module 1 |

## Files to implement
```
strategies/
├── base.py           # abstract StrategyProposal interface + gate-check on load
├── registry.py        # loads only strategies with a PASS verdict from edge_validation.registry
└── <strategy_name>.py # one file per gate-approved strategy, added only once approved
```

## Proposal contract
```python
class StrategyProposal:
    proposal_id: str
    strategy_id: str
    strategy_version: str
    edge_validation_record_id: str   # required — no default, no None
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float                # calibrated statistic, see module 5
    evidence: list[dict]             # references into MarketContext fields
    horizon: str
    invalidation_conditions: list[str]
    timestamp: datetime
```

## Hard rule
`base.py`'s loader must raise, not warn, if a strategy module is imported without a corresponding `PASS` verdict for its `strategy_id` in the edge validation registry. This should be enforced in code, not just documented, so a future contributor can't accidentally wire in an ungated strategy.

## Acceptance criteria
- Attempting to load Breakout or Scalping raises an explicit `StrategyNotGatedError`.
- Each implemented strategy's proposal includes a valid `edge_validation_record_id` that resolves to a `PASS` verdict.
- Unit tests cover: proposal generation on synthetic context, rejection of ungated strategies, and confidence calibration against historical hit rate (not a hardcoded or arbitrary number).

## When done
Log to `docs/implementation-log.md` which strategies were implemented, their gate record IDs, and the confidence calibration method used.
