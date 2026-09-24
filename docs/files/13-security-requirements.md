# Module 13: Security Requirements (cross-cutting)

## Requirements
- Binance API keys: withdrawals disabled, minimum required permissions only.
- Never log API secrets, signed URLs, or authentication headers, in any module.
- Market-data API (module 2): loopback-only by default; authenticated + TLS if made non-loopback.
- n8n webhooks (module 7): authenticated/signed with replay protection.
- Execution requests (module 7): idempotency keys required.
- Every execution boundary validates symbol, side, quantity, order type, and expiry independently — don't trust an upstream module's validation alone.
- Paper/testnet credentials must be fully separate from production credentials, enforced by config, not just convention.
- The kill switch (module 6/11) must be independent of the decision layer — it must be triggerable even if Hermes itself is malfunctioning.
- Secrets live in environment/secret-management facilities, never in source control.

## Acceptance criteria
- A grep/lint check confirms no secret-shaped strings appear in logs during a test run.
- A test confirms the kill switch halts trading even when the decision-engine process is deliberately hung/unresponsive.
- Config loading fails loudly if paper and production credentials are both present and ambiguous, rather than silently picking one.

## When done
Log to `docs/implementation-log.md`: the secret-management mechanism used and the kill-switch independence test result.
