# Module Status Tracker

**Project status (2026-09-29): Research concluded — no production strategy approved; infrastructure complete and reusable. See `research/PROJECT_FINDING.md`.**

Update this table whenever work starts or finishes on a module. Keep it in sync with `implementation-log.md` — this file is the at-a-glance summary, the log is the detailed record.

| # | Module | File | Status | Last updated |
|---|---|---|---|---|
| 1 | Edge Validation Gate | 01-edge-validation-gate.md | Done — 7/7 prior FAIL + F1–F3 NULL + F4 FAIL (24 trades, CI entirely negative, final) + orphan NULL (infra crash, disclosed) + D1–D3 CLOSED_UNAVAILABLE 2026-09-27 (research-level closure, ledger untouched, not a falsification) + RS-001 cross-sectional FAIL (121 trades, aggregate -99.90% compounded — correction 2026-09-27 of reported -193.76% sum — CI [-2.07%, -1.16%] entirely negative, final; scope_caveat: FAIL covers the 2-asset BTC/ETH variant only, broader universe is a new pre-registration); ledger m=11; 0 PASS; 0 approved + OI-positioning 5d (001) & 20d (20d_001) CLOSED_PRECOST_SCREEN 2026-09-29 (research-level closures, ledger untouched, holdout never consumed) | 2026-09-29 |
| 2 | Market Data Hardening | 02-market-data-hardening.md | Done — P0/P1/P2 fully closed; 24 hardening tests passing (wired async writer, tracked fan-out, token+TLS gate, 24h simulated soak, restart/recovery, periodic retention, authoritative universe, analytics split, feature cache, repo reads, shared client, centralized backoff); 116 total tests passing | 2026-09-24 |
| 3 | Observer + Context Builder | 03-hermes-core-observer-context.md | Done — MarketContext + builder + observer live; 8 acceptance tests passing; 124 total tests passing | 2026-09-24 |
| 4 | Strategy Proposal Layer | 04-strategy-layer.md | Blocked (no approved production version — PASS-only loader preserved, production loader requires PASS + human approval + immutable version; promotion adapter ready, zero versions approved) | 2026-09-26 |
| 5 | Decision Engine | 05-decision-engine.md | Blocked (machinery complete and tested on synthetic proposals; production behavior verified as idle-HOLD pending Module 1 PASS — cannot be Done per hard rule) | 2026-09-24 |
| 6 | Deterministic Risk Engine | 06-risk-engine.md | Done — engine + limits + sizing, SHA-256 quantity seal, kill switch, 23 tests passing; full suite 195 passing | 2026-09-26 |
| 7 | n8n Execution Boundary | 07-execution-n8n-boundary.md | Done — verified/signed/idempotent submit, state ledger, reconciliation, 20 tests passing; full suite 215 passing | 2026-09-26 |
| 8 | Order/Position/Trade Lifecycle | 08-order-position-lifecycle.md | Done — state machine + fills/positions/trades, unknown-gating, reconcile, memory mirror, 12 tests passing; full suite 227 passing | 2026-09-26 |
| 9 | Trade Intelligence + Learning | 09-trade-intelligence-learning.md | Done — analyzer + lessons + backtest/paper adapters + PASS-gated promotion, 11 tests passing; full suite 238 passing | 2026-09-26 |
| 10 | Memory / Database Model | 10-memory-database-model.md | Done — SQLite unified store, 20/20 tables, trace(trade_id) 13-stage ordered chain, append-only edge+versions, 7 tests passing; full suite 161 passing | 2026-09-26 |
| 11 | Supervisor / 24-7 Runtime | 11-supervisor-runtime.md | Done — asyncio supervision, health probes + failure table, rebuild-gated decisions, 10 tests passing; full suite 248 passing | 2026-09-26 |
| 12 | Testing Strategy | 12-testing-strategy.md | Done (harness, not a service) — level registry + soak/failure/backtest/venue suites, 14 tests passing; full suite 262 passing | 2026-09-26 |
| 13 | Security Requirements | 13-security-requirements.md | Done (bar, not a service) — credentials loader + redaction + settings audit, 12 tests passing; full suite 274 passing | 2026-09-26 |
| 15 | Candidate Generation Loop | 15-candidate-generation-loop.md | Done — all 5 files (generator/menu/multiple_testing/review_queue/provider_client), 11 tests passing; full suite 172 passing; menu now funding-rate carry (exhausted) + cross-exchange dislocation (closed unavailable) + cross-sectional-relative-strength (tested FAIL 2026-09-27) + open-interest-positioning-dynamics (new 2026-09-27, pre-registration pending; persisted in research/hypothesis_menu.sqlite3) | 2026-09-27 |

| — | Runtime Integration (paper pipeline) | runtime/ | Done — market→context→strategy→decision→risk→n8n→paper→lifecycle→learning→research wired, supervisor workers real, 16 integration tests passing; full suite 290 passing | 2026-09-26 |

Status values to use: `Not started`, `In progress`, `Blocked (reason)`, `Done`.

**Reminder:** Module 4 (and anything downstream of it) cannot move to `Done` — or even meaningfully `In progress` beyond scaffolding — until Module 1 has produced at least one `PASS` verdict, per the hard rule in `00-overview-and-index.md`.
