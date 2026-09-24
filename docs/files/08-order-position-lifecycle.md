# Module 8: Order, Position, and Trade Lifecycle

## Purpose
Track an order from submission through fill to closed trade, and keep local state reconciled with exchange truth.

## Files to implement
```
monitoring/positions.py
models/execution.py
models/trade.py
```

## Order state machine
`NEW → PARTIALLY_FILLED → FILLED / CANCELED / REJECTED`

Add an explicit `SUBMISSION_UNKNOWN` state for ambiguous exchange responses (e.g. timeout with no confirmation) — do not assume either FILLED or REJECTED in this case; it must be actively reconciled before the position is trusted.

## ID chain (must be preserved end to end)
`Decision ID → Execution ID → Order ID → Position ID → Exit Order ID → Trade ID`

## What to track per position/trade
Entry price, exit price, current mark price, quantity, notional exposure, realized/unrealized PnL, fees and funding costs, stop-loss/take-profit state, trade duration, Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE), expected vs. actual slippage, execution latency and fill quality, partial fills/amendments, exchange reconciliation state.

## Reconciliation rule
On any restart, missed WebSocket event, or n8n failure, rebuild local order/position state from exchange truth (Binance API) before resuming any new decisions for the affected symbol. A position in `SUBMISSION_UNKNOWN` blocks new entries on that symbol until resolved.

## Acceptance criteria
- A simulated missed-fill-event scenario is correctly recovered by reconciliation without manual intervention.
- `SUBMISSION_UNKNOWN` correctly blocks new entries on the affected symbol until resolved, verified in a test.
- MFE/MAE and slippage are computed correctly against a synthetic price path in a unit test.

## When done
Log to `docs/implementation-log.md`: how reconciliation is triggered (polling interval, on-restart, on-gap-detection), and the recovery-test result.
