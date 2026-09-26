# Hermes — Module Index & How To Use These Files

These files are specifications for the Hermes Autonomous Crypto Trading System. The architecture is intentionally split into an **AI research/evolution plane** and a **deterministic production trading plane**.

## Build order

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
| 9 | `09-trade-intelligence-learning.md` | Trade Intelligence + Continuous Learning | Lifecycle module |
| 10 | `10-memory-database-model.md` | Memory / Database Model | Cross-cutting — needed by all modules |
| 11 | `11-supervisor-runtime.md` | Supervisor / 24/7 Runtime | All active workers |
| 12 | `12-testing-strategy.md` | Testing Strategy | Cross-cutting |
| 13 | `13-security-requirements.md` | Security Requirements | Cross-cutting |
| 14 | `14-coding-conventions.md` | Coding Conventions | Cross-cutting |
| 15 | `15-candidate-generation-loop.md` | Candidate Research & Evolution | Modules 1, 9, 10, provider configuration |

## Existing-code compatibility rule

**Modules 1–5 are already implemented in the existing codebase. Do not rewrite them to introduce LLM decision-making.** The changes in this revision are primarily architectural additions around those modules.

- Module 4 remains the only path from a validated production strategy version to live `StrategyProposal` objects.
- Module 5 remains deterministic and does not call an LLM at decision time.
- Module 15 adds the autonomous research/evolution plane that creates and improves candidates before they become production strategies.
- Module 9 closes the learning loop by turning closed-trade analysis into new candidate hypotheses.
- Module 10 persists candidate lineage and experiment history so the research process is auditable and reproducible.
- Module 11 supervises research workers as well as the existing trading workers.

## Two-plane architecture

```text
AI RESEARCH / EVOLUTION PLANE

Initial seed ideas
      ↓
Research agents
      ↓
Candidate population
      ↓
Critique / deduplication / mutation
      ↓
Experiment scheduler
      ↓
Backtest / paper evaluation
      ↓
Module 1 Edge Validation Gate
      ↓
Human review
      ↓
Immutable production strategy version

DETERMINISTIC PRODUCTION TRADING PLANE

Production strategy versions
      ↓
Module 4 Strategy Proposal Layer
      ↓
Module 5 Decision Engine
      ↓
Module 6 Risk Engine
      ↓
Module 7 n8n boundary
      ↓
Module 8 Order / Position / Trade lifecycle
      ↓
Module 9 Trade analysis
      ↓
Candidate hypotheses / lessons
      └──────────────────────────────→ AI RESEARCH PLANE
```

## Hard rules

1. A **candidate hypothesis** may exist without a PASS gate record.
2. A **production strategy** may not exist without a current `PASS` edge-validation record and the required human approval.
3. Module 4 may load only validated production strategies.
4. Module 5 may consume only production strategy proposals and remains deterministic.
5. LLMs may operate in the research/evolution plane, but never directly turn a live `MarketContext` into a BUY/SELL instruction.
6. Fail-closed behavior remains mandatory: malformed, stale, contradictory, expired, or unauthorized state produces HOLD / no new entry / halt.

## Research loop rule

The research loop is allowed to run repeatedly, but **expensive validation experiments are budgeted and scheduled**. The system must not repeatedly tune and retest the same hypothesis on the same holdout data.

## Documentation rule

`docs/module-status.md` is the summary. `docs/implementation-log.md` is append-only and records actual implementation and test results.
