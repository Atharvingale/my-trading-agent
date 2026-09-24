# Module 9: Trade Intelligence and Continuous Learning

## Purpose
Diagnose every closed trade, extract candidate lessons and strategy changes, and route any candidate strategy change back through the Edge Validation Gate (module 1) before it can reach production — never directly.

## Files to implement
```
learning/
├── trade_analyzer.py
├── lesson_engine.py
├── backtester.py
├── paper_engine.py
└── promotion.py
```

## Post-trade analysis questions (per closed trade)
What did Hermes expect to happen? Which features supported the decision? Which strategies agreed/disagreed? What actually happened after entry? Was entry late/early/reasonable? Did liquidity deteriorate? Did order flow invalidate the thesis? Was stop/target placement consistent with the thesis? Was execution materially different from planned? Did external conditions change? Was any loss caused by strategy, execution, data, or risk-configuration error, or normal variance?

## Mistake/lesson categories
| Category | Example | Action |
|---|---|---|
| Signal error | Breakout signal on a transient volume spike | Candidate lesson |
| Regime error | Trend strategy used in a range-bound regime | Candidate regime filter |
| Execution error | Actual slippage materially exceeded estimate | Review liquidity threshold |
| Risk error | Position size inconsistent with approved risk | Block deployment, audit risk path |
| Data error | Stale/contradictory data contributed to the decision | Mark non-actionable, investigate |
| Gate error | Strategy deployed without / drifted from its gate record | Immediate halt of that strategy |
| Normal loss | Thesis was valid, outcome was adverse | Do not automatically change strategy |

## Learning pipeline (binding)
```
Closed Trade → Trade Analysis → Candidate Lesson → Candidate Strategy Version
→ EDGE VALIDATION GATE (module 1, fresh holdout, pre-registered criteria)
→ Backtest → Paper Simulation → Evaluation → Promotion → Production Strategy Version
```

`promotion.py` must refuse to promote any candidate whose `edge_validation_record_id` is missing or whose verdict is not `PASS`. Every strategy version is immutable; a strategy can be disabled without deleting its history; rollback to a prior version must be instant.

## Acceptance criteria
- `promotion.py` raises on any promotion attempt without a linked `PASS` gate record — verified by a unit test.
- A single simulated losing trade does not, by itself, alter any live strategy parameter (verified by a test that runs one bad trade through the pipeline and checks production config is untouched).
- Rollback to a previous strategy version is demonstrated in under a defined time bound (e.g. one config reload cycle).

## When done
Log to `docs/implementation-log.md`: how many candidate lessons were generated in initial testing, how many were promoted vs. rejected at the gate, and the rollback-test result.
