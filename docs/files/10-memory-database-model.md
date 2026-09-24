# Module 10: Memory / Database Model

## Purpose
Durable, append-friendly persistence for every stage of the pipeline, and the traceability backbone that lets any trade be fully reconstructed.

## Files to implement
```
memory/
├── repository.py
└── schemas.py
```

## Tables
| Table | Purpose |
|---|---|
| raw_market_events | Short-retention raw event audit trail |
| candles | Normalized OHLCV history |
| feature_snapshots | Decision-ready feature state |
| breadth_snapshots | Market breadth history |
| derivatives_snapshots | Funding/OI/basis/liquidation state |
| universe_history | Dynamic universe changes |
| data_health | Freshness and integrity state |
| edge_validation_records | Every gate attempt — append-only, see module 1 |
| decisions | Every BUY/SELL/HOLD decision |
| decision_evidence | Structured evidence used by decisions |
| strategy_proposals | Individual strategy outputs |
| risk_decisions | Risk approval/rejection and exact approved parameters |
| executions | n8n execution requests and acknowledgements |
| orders | Exchange order lifecycle |
| positions | Position lifecycle |
| trades | Closed trade records |
| trade_analysis | Post-trade diagnosis |
| lessons | Candidate and validated lessons |
| strategy_versions | Immutable strategy versions; must reference `edge_validation_record_id` |
| performance_metrics | Strategy/portfolio performance aggregates |

## Traceability requirement (must be enforceable by a query, not just a convention)
```
MARKET SNAPSHOT → EDGE VALIDATION RECORD → HERMES DECISION
→ STRATEGY PROPOSALS/EVIDENCE → RISK DECISION → EXECUTION → ORDER
→ POSITION → TRADE → TRADE ANALYSIS → LESSON → STRATEGY VERSION
```
Every table in this chain carries the ID of the table before it. `repository.py` should expose a `trace(trade_id)` function that walks this chain and returns the full record set for auditing.

## Rules
- `edge_validation_records` and `strategy_versions` are append-only — no updates or deletes, only new rows.
- Every table has the stable IDs needed to join into the chain above.

## Acceptance criteria
- `trace(trade_id)` returns a complete, correctly-ordered chain for a synthetic end-to-end test trade.
- Attempting to update or delete an `edge_validation_records` row raises/fails at the repository layer.

## When done
Log to `docs/implementation-log.md`: the storage engine chosen (SQLite/Postgres/etc.), schema migration approach, and the `trace()` test result.
