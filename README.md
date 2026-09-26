# Hermes — Autonomous Crypto Trading Engine

> **Edge-gated, fail-closed, fully tested — and honestly idle.**
> Hermes is a complete autonomous trading pipeline where **no strategy can trade real capital without pre-registered, out-of-sample proof of edge**. Today that proof does not exist for any strategy, so the system runs, watches, and holds — by design, not by accident.

```text
338 tests passing · 0 production strategies · 0 Module 1 PASS verdicts · live trading disabled
```

---

## What this is

Hermes turns Binance market data into trading decisions through a deterministic pipeline guarded at every step:

```text
Market Data → Observer/Context → Strategy Layer → Decision Engine
    → Risk Engine → n8n Execution Boundary → Venue (paper)
    → Order/Position/Trade Lifecycle → Trade Intelligence → Research → Edge Gate
```

Two planes keep luck and money apart:

| Plane | Role | LLM allowed? |
|---|---|---|
| **Deterministic production** (Modules 4–8) | Proposals → decisions → risk → execution | **Never** |
| **AI research / evolution** (Modules 9, 15, 1) | Hypotheses → backtests → gate → human review | Yes |

The hard rules are enforced in code, not documentation:

1. **No PASS in the Edge Validation Gate → no production strategy.** Ever.
2. **Every entry passes the deterministic Risk Engine.** No alternate path exists.
3. **Execution goes through the signed n8n boundary only.** Quantity is sealed by hash.
4. **Anything ambiguous resolves to HOLD / REJECT / FREEZE** — stale data, outages, expired instructions, kill switch.

---

## Current research verdict (honest scoreboard)

| Family | Result |
|---|---|
| Breakout, Scalping | FALSIFIED (seeded FAIL) |
| Trend / Order Flow / Mean Reversion / VWAP / Daily probe | FAIL through the gate |
| Funding carry F1–F3 | NULL_RESULT (quiet holdout, final) |
| Funding anomaly F4 | **FAIL** — 24 trades, net −38.8%, CI entirely negative |
| Cross-exchange D1–D3 | INCONCLUSIVE (no executable quote history exists publicly) |

**Production strategies approved: 0.** The infrastructure works; the edge has not been found. Failed hypotheses are preserved as evidence, not deleted.

---

## Quick start

```bash
cd /d/my-trading-app
python -m pip install -r requirements.txt

# 1. Market-data collector (read-only, loopback API on :8000)
python main.py

# 2. Full test suite (338 tests, ~30s)
python -m pytest -q

# 3. Paper pipeline (default — needs nothing but Python)
$env:PYTHONPATH="D:\my-trading-app"   # PowerShell
python -c "from runtime.config import RuntimeConfig; print(RuntimeConfig.from_environment())"
```

Requirements: Python 3.11+, dependencies from `requirements.txt` (`aiohttp`, `websockets`, `pytest` — nothing else).

---

## Repository map

```text
binance_data_layer/   Module 2 — hardened market-data service (WS/REST, SQLite, local API)
hermes/               Modules 3 + 5 — observer, context builder, decision engine
strategies/           Module 4 — gated proposal layer (PASS-only loading + promotion adapter)
risk/                 Module 6 — deterministic risk engine, sealed quantities, kill switch
execution/            Module 7 — signed n8n boundary, idempotent submit, reconciliation
models/ monitoring/   Module 8 — order/fill/position/trade lifecycle, SUBMISSION_UNKNOWN gating
learning/             Module 9 — trade diagnosis, lessons, PASS-gated promotion
memory/               Module 10 — unified audit store, end-to-end trace(trade_id)
supervisor.py         Module 11 — asyncio supervision, rebuild-before-decisions
candidate_generation/ Module 15 — hypothesis menu, Bonferroni guard, human review queue
edge_validation/      Module 1 — the gate: preregistration, bootstrap CI, regimes, replication
research/             Experiments, immutable datasets, run artifacts (F1–F4, D1–D3)
runtime/              End-to-end paper pipeline wiring all of the above
security/             Credentials, redaction, settings audit (Module 13)
paper_trading/        Offline fill simulator and portfolio
tests/                338 tests across 11 levels (see docs/files/12-testing-strategy.md)
docs/files/           Per-module specs · module-status.md · implementation-log.md
```

---

## Safety at a glance

- **Paper by default.** `HERMES_EXEC_ENV` unset means paper. Production boot refuses without explicit `HERMES_LIVE_TRADING=1` — and still idles with zero approved strategies.
- **Secrets live in the environment** (`*_PAPER` / `*_PROD` pairs, read-only scope, withdrawals attested off). Paper+production ambiguity fails loudly. Nothing secret is ever logged (`SecretFilter`).
- **Kill switch is independent** of the decision layer — verified by test with a deliberately hung decision engine.
- **Every decision, order, fill, position, and trade chains by ID** and reconstructs via `memory.trace(trade_id)`.

---

## Testing

```bash
python -m pytest -q                 # full suite
python -m compileall -q .           # bytecode check
git diff --check                    # whitespace check
```

Test levels (enforced by `tests/test_levels.py`, which fails if coverage is removed): edge validation, unit, contract, integration, execution integration, lifecycle, reconciliation, learning, soak, failure injection, backtest validation.

Conventions: stdlib preferred, no list comprehensions, no `sorted()`, explicit state transitions, deterministic reruns.

---

## Market-data API (Module 2, still included)

The collector serves a local read-only API on `http://127.0.0.1:8000` (loopback by default; token+TLS required otherwise):

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness |
| `GET /market/top-coins` | Pinned + dynamically ranked universe |
| `GET /market/{symbol}/snapshot` | Feature snapshot (price, depth, indicators, execution estimates) |
| `GET /breadth/latest` | Market breadth |
| `GET /cross-exchange/{symbol}` | Multi-venue confirmation (context only, not a signal) |
| `GET /data-health`, `GET /events` | Collector health, persisted events |
| `WS /ws` | `market_event`, `breadth`, `cross_exchange_confirmation`, `universe_update` |

---

## What this is not

- Not profitable, not a signal service, not financial advice.
- No validated strategy, no live orders, no testnet/live execution configured.
- Dynamic coins and breadth data are **candidates for analysis**, never trade instructions.
- Past research (7 FAILs, 3 NULLs, 1 FAIL, 6 INCONCLUSIVE) says hourly price-action edges do not survive Indian VDA costs — costs drain flat signals; they do not destroy real ones.

Detailed specs, status, and the full build log live in `docs/files/` (`module-status.md`, `implementation-log.md`).
