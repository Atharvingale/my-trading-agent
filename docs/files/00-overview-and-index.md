# Hermes — Module Index & How To Use These Files

These files are **specifications**, not code. Each one describes a single module of the Hermes Autonomous Crypto Trading System (v2, edge-gated architecture) in enough detail that an AI coding agent (or a human) can implement it independently, without needing the full 30-section architecture document in context at once.

## Build order (do not reorder without updating docs/module-status.md)

| # | File | Module | Depends on |
|---|---|---|---|
| 1 | `01-edge-validation-gate.md` | Edge Validation Gate | Market data (read-only, existing) |
| 2 | `02-market-data-hardening.md` | Market Data Layer hardening | None (existing service) |
| 3 | `03-hermes-core-observer-context.md` | Observer + Context Builder | Market Data Layer |
| 4 | `04-strategy-layer.md` | Strategy Proposal Layer | Edge Validation Gate (module 1) |
| 5 | `05-decision-engine.md` | Decision Engine | Context Builder, Strategy Layer |
| 6 | `06-risk-engine.md` | Deterministic Risk Engine | Decision Engine |
| 7 | `07-execution-n8n-boundary.md` | n8n Execution Boundary | Risk Engine |
| 8 | `08-order-position-lifecycle.md` | Order/Position/Trade Lifecycle | Execution Boundary |
| 9 | `09-trade-intelligence-learning.md` | Trade Intelligence + Learning | Lifecycle module |
| 10 | `10-memory-database-model.md` | Memory / Database Model | Cross-cutting — needed by all above |
| 11 | `11-supervisor-runtime.md` | Supervisor / 24-7 Runtime | All of the above |
| 12 | `12-testing-strategy.md` | Testing Strategy | Cross-cutting |
| 13 | `13-security-requirements.md` | Security Requirements | Cross-cutting |
| 14 | `14-coding-conventions.md` | Coding Conventions | Cross-cutting — **read this once before implementing any module**, instead of restating style preferences per session |

**Hard rule that overrides everything else in these files:** modules 4 onward (Strategy Layer, Decision Engine, Risk Engine, Execution, Lifecycle, Learning) MUST NOT run against real capital, and the Strategy Layer MUST NOT accept any strategy, until module 1 (Edge Validation Gate) has produced a passing `edge_validation_records` entry for that strategy. See `01-edge-validation-gate.md` for the currently-falsified strategy list — do not reimplement those without a materially new hypothesis.

## docs/ folder

`docs/module-status.md` — one row per module, current status, updated every time work starts/finishes on a module.
`docs/implementation-log.md` — append-only log: what was actually built, when, how it differs from the spec (if it does), and what was tested. An AI agent implementing any module should add an entry here when it finishes, using the template at the top of that file.

**Before implementing any module, read `14-coding-conventions.md` once** — it holds the standing style/dependency preferences so they don't need to be repeated in every implementation session.

## Global conventions all modules follow

- Every cross-module contract (JSON shape, DB table, API endpoint) is authoritative in the module file that owns it — don't redefine it elsewhere, reference it.
- Every decision, order, position, and trade carries IDs that chain per the traceability requirement in `10-memory-database-model.md`.
- Nothing in `strategies/`, `decision.py`, or `risk/` may call an LLM at decision time. LLMs are permitted only in a read-only market-intelligence/news layer (out of scope for v1 build — not covered by these files yet).
- Fail-closed default: any ambiguous, stale, or malformed state resolves to HOLD / no new entry / halt, never to a default BUY or SELL.
