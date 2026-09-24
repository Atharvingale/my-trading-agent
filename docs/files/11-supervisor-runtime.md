# Module 11: Supervisor and 24/7 Runtime

## Purpose
Keep the whole system alive, healthy, and safe across restarts, crashes, and partial outages, without silently losing state or trading on stale assumptions.

## Files to implement
```
supervisor.py
monitoring/health.py
```

## Workers supervised
Market Observer, Context Builder, Strategy Engine, Decision Engine, Risk Engine, n8n Client, Trade Monitor, Learning Worker. A failure in any one worker must not silently terminate the whole system — the supervisor isolates, logs, and restarts individually where safe.

## Failure handling table (binding defaults)
| Condition | Required response |
|---|---|
| Market data stale/incomplete | HOLD / no new entry |
| Cross-exchange data contradictory beyond tolerance | Reduce confidence or HOLD |
| Risk service unavailable | No execution |
| n8n unavailable | Expire pending requests, do not queue indefinitely |
| Binance execution state unreconcilable | Freeze new entries, reconcile |
| Database persistence failing | Stop new trading rather than operate without an audit trail |
| Hermes unhealthy | Supervisor restarts it, verifies state from durable storage |
| Daily loss/drawdown limit reached | Activate kill switch |
| Strategy version validation fails | Keep existing production version |
| Strategy missing/drifted edge_validation reference | Treat as risk error, halt that strategy immediately |
| Any restart | Rebuild portfolio state from exchange reconciliation + durable local records before resuming decisions |

## Acceptance criteria
- Killing any one worker process in a test environment results in that worker restarting and the others continuing unaffected.
- A simulated stale-data condition results in HOLD decisions system-wide for the affected symbol, verified in an integration test.
- A full process restart correctly rebuilds portfolio state before any new decision is made, verified against a known pre-restart state.

## When done
Log to `docs/implementation-log.md`: the process/orchestration technology used (e.g. systemd, Docker, asyncio task supervision), restart-backoff parameters, and the restart-recovery test result.
