# Module 12: Testing Strategy (cross-cutting)

## Purpose
Define the test levels every module above must satisfy before being considered done. This file doesn't correspond to a code module — it's the acceptance bar referenced by all the others.

## Test levels
| Level | Examples |
|---|---|
| Edge Validation | Pre-registered hypothesis, fresh holdout, bootstrap CI, regime robustness, replication check (module 1) |
| Unit | Feature calculations, sizing, risk limits, strategy proposals, state machines |
| Contract | Market API, Hermes internal schemas, n8n webhook schemas |
| Integration | Market-data → context → decision → risk |
| Execution integration | n8n → Binance testnet/paper environment |
| Lifecycle | Order/fill/position/trade transitions |
| Reconciliation | Restart after missed events or partial fills |
| Learning | Trade analysis → lesson → candidate strategy → back through the gate |
| Soak | 24h/72h continuous runtime, reconnects, DB growth |
| Failure injection | API outage, WS disconnect, stale data, n8n failure, Binance rejection |
| Backtest validation | No look-ahead, deterministic reproducibility, versioned datasets |

## Rule for every module file above
No module in this set is "done" until its own Acceptance Criteria section passes AND it has at least one test at the level(s) relevant to it from this table.

## When done
Each module's own log entry in `docs/implementation-log.md` should name which test level(s) from this table were actually exercised, not just claim "tests pass."
