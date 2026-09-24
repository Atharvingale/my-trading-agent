# Module 7: n8n Execution Boundary

## Purpose
Turn a risk-approved decision into an actual exchange order, through n8n as an orchestration boundary — never directly from Hermes to Binance.

## Flow
```
Hermes → Risk-approved ExecutionRequest → n8n webhook → schema validation
→ execution logging → exchange/order-rule validation → Binance
→ order status/fills → Hermes monitoring
```

## Files to implement
```
execution/
├── n8n_client.py      # builds and sends ExecutionRequest to the n8n webhook
├── order_manager.py   # tracks request → order → fill state
└── reconciliation.py  # reconciles local state against exchange truth
```

## ExecutionRequest contract
```python
class ExecutionRequest:
    execution_id: str
    risk_decision_id: str   # must resolve to an APPROVED RiskDecision
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float          # must exactly equal RiskDecision.approved_quantity
    order_type: str
    protection: dict          # stop/target
    expiry: datetime
```

## Rules
- n8n is an orchestration boundary, not a safety layer — it does not re-derive risk parameters, only validates schema and submits.
- Webhook calls must be authenticated/signed with replay protection.
- Every `ExecutionRequest` carries an idempotency key so a retried webhook call cannot double-submit.
- If n8n is unreachable, the request expires rather than queuing indefinitely — an expired trading instruction must never execute late.

## Acceptance criteria
- A request whose `quantity` doesn't exactly match its `RiskDecision.approved_quantity` is rejected before submission (defense in depth alongside module 6's invariant).
- A duplicate webhook delivery (simulated) does not produce a duplicate order, verified via the idempotency key.
- An expired `ExecutionRequest` is never submitted, verified with a time-travel/clock-injection test.

## When done
Log to `docs/implementation-log.md`: the webhook auth/signing scheme used, the idempotency key format, and the expiry-enforcement test result.
