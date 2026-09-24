# Module 2: Market Data Layer — Production Hardening

## Purpose
Bring the existing market-data collector (project root `D:\my-trading-app`, SQLite at `data/market_data.sqlite3`) from "functionally complete" to "safe as an unattended 24/7 dependency." This module hardens an existing service — it does not rebuild it.

## Current service (do not re-implement — reference only)
REST API at `http://127.0.0.1:8000`: `/health`, `/market/top-coins`, `/market/{symbol}/snapshot`, `/market/{symbol}/features`, `/breadth/latest`, `/cross-exchange/{symbol}`, `/data-health`, `/events`; WS at `/ws` and `/ws?symbol=`. Tables: `market_events`, `feature_snapshots`, `breadth_snapshots`, `data_health`. 66 existing tests pass — do not break them.

## Work items, in priority order

### P0 — must fix before any unattended run
1. **Async persistence**: move SQLite writes/commits off the WebSocket ingestion hot path onto a queue; batch-write from a separate consumer.
2. **Non-blocking fan-out**: WebSocket publication to subscribers must use bounded async queues; a slow subscriber must never block ingestion.
3. **Managed background tasks**: every fire-and-forget publish task must be tracked (e.g. `asyncio.Task` registry) and its failures logged and handled, not swallowed.
4. **API access control**: keep the REST/WS API loopback-only by default; if it must be non-loopback, add authentication and TLS before that config is enabled.
5. **Lifecycle tests**: add soak tests (see module 12), reconnect tests, and restart/recovery tests — these don't exist yet.

### P1 — needed before extended unattended operation
6. Retire stale dynamic-universe symbols so tracked state doesn't grow unbounded.
7. Add a SQLite retention/maintenance policy: index review, WAL checkpointing, periodic vacuum, and a defined retention window per table.
8. Make dynamic-universe generation authoritative for all REST analytics (currently inconsistently applied).
9. Split the large collector module into ingestion / analytics / storage / quality / orchestration responsibilities.
10. Cache technical features and recompute only on meaningful candle/event boundaries, not on every tick.

### P2 — quality-of-life, do when convenient
11. Route API reads through a repository/storage abstraction instead of raw SQL in the API layer.
12. Reuse HTTP client sessions / exchange clients instead of reconstructing them repeatedly.
13. Centralize retry/backoff logic; eliminate duplicated requests on startup.

## Acceptance criteria
- All 66 existing tests still pass after each change.
- A new soak test runs the service for a configurable duration (default 24h in CI-simulated time or a real multi-hour run) with induced disconnects, and it recovers without data loss or unbounded memory growth.
- Loopback-only is the default in the shipped config; enabling non-loopback requires explicitly setting an auth token.

## When done
Log which P0/P1/P2 items were completed, in what order, and the soak-test results (duration, disconnect count, memory profile) to `docs/implementation-log.md`.
