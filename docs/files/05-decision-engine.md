# Module 5: Decision Engine

## Purpose
Combine strategy proposals, evidence, historical performance, and current portfolio/risk state into one structured, auditable, deterministic decision per symbol per cycle.

## Files to implement
```
decision.py
models/decision.py
```

## Decision object
```json
{
  "decision_id": "uuid",
  "timestamp": "...",
  "symbol": "BTCUSDT",
  "action": "BUY|SELL|HOLD",
  "confidence": 0.81,
  "entry": {},
  "position": {},
  "risk": { "stop_loss": 0.0, "take_profit": 0.0, "risk_amount": 0.0 },
  "time_horizon": "15m",
  "thesis": [],
  "strategy_version_id": "...",
  "expiry_seconds": 120
}
```

`confidence` = a calibrated statistic (e.g. proposal-agreement rate weighted by each strategy's historical hit rate from its edge validation record), not a self-reported model score. `thesis` is template-generated from the evidence list — a fixed function of structured inputs, reproducible given the same inputs. No LLM call happens inside this module.

## Decision evidence record (audit storage)
```json
{
  "decision_id": "dec_123",
  "market_snapshot_id": "snap_891",
  "action": "BUY",
  "confidence": 0.81,
  "evidence": [{"feature": "ema_alignment", "value": true}],
  "strategy_votes": {"momentum": "BUY", "trend": "HOLD"},
  "decision_rationale": "template-generated string",
  "risk_assessment": "Acceptable",
  "decision": "BUY"
}
```

## Rules
- A decision must carry `expiry_seconds`; anything consuming a decision after expiry must treat it as void, never as a current instruction.
- BUY/SELL decisions are passed to the Risk Engine (module 6) for approval; HOLD decisions are persisted but not passed downstream.
- If proposals conflict or no gated strategy has a live proposal for a symbol, default to HOLD.
- Malformed or partial proposal input fails closed to HOLD — never to a default BUY.

## Acceptance criteria
- Given the same `MarketContext` and proposal set, the decision engine produces byte-identical output on repeated runs (determinism test).
- A decision past its expiry is rejected by a downstream consumer in a unit test.
- Conflicting proposals resolve to HOLD unless an explicit, documented tie-break rule says otherwise.

## When done
Log to `docs/implementation-log.md`: the confidence-calibration formula used, the tie-break rule for conflicting proposals, and the determinism test result.
