# Module 1: Edge Validation Gate

## Purpose
Certify, with pre-registered and out-of-sample evidence, that a trading strategy has a real net-of-cost-and-tax edge before it is allowed to produce live proposals. This module is a hard gate, not a formality — nothing downstream may bypass it.

## Already-falsified strategies (do not rebuild without a materially new hypothesis)
| Strategy | Result |
|---|---|
| Breakout (24/12/14 lookback, hourly) | Net −27.78%, bootstrap CI entirely negative |
| Scalping (5/3/14 lookback, 1-min) | Net −39.42%, bootstrap CI entirely negative |
| Breakout + ADX>25 filter | Improved headline but failed replication (bull-market-dependent) |
| Breakout + magnitude≥0.5×ATR filter | Improved headline but failed replication |
| Breakout + volume>20SMA filter | No credible edge |
| Corrected baseline (intrabar stop-loss fix) | −26.48% |

## Candidates still eligible for testing
Trend Following, Mean Reversion, VWAP Reversion, Order Flow — none of these have been run through this gate yet on crypto data.

## Files to implement
```
edge_validation/
├── registry.py            # CRUD for edge_validation_records (see module 10 for schema)
├── acceptance_criteria.py # defines the 7 pass/fail criteria below as a checklist object
├── replication_check.py   # runs a candidate against a second, disjoint period and compares
└── report_writer.py       # writes/updates research/reports/EXPERIMENT_REGISTRY.md
```

## The 7 gate criteria (all must pass)
1. Hypothesis and acceptance thresholds are written into the registry BEFORE the holdout is touched.
2. Backtest uses a holdout period never used in any prior experiment for this strategy family.
3. Returns are computed net of realistic fees, slippage, and India VDA tax (30% on transfer gains, no loss offset; 1% TDS as a cash-flow drag, not a permanent expense).
4. A bootstrap confidence interval is computed on the net return; it must exclude zero on the positive side to pass.
5. The strategy is tested across at least two structurally different regimes (e.g. trending vs. range-bound / bull vs. bear).
6. If any filter or refinement improves on a baseline, it must be re-tested on data outside the period it was tuned on (replication_check.py) before being credited.
7. A null result is a valid, final, recorded outcome — no unlimited retries against the same holdout for the same hypothesis.

## Interface
```python
class EdgeValidationRecord:
    record_id: str
    strategy_id: str
    hypothesis: str
    pre_registered_criteria: dict
    holdout_period: tuple[date, date]
    cost_and_tax_assumptions: dict
    bootstrap_ci: tuple[float, float]
    regime_results: dict[str, float]
    replication_result: str | None
    verdict: Literal["PASS", "FAIL", "NULL_RESULT"]
    linked_strategy_version_id: str | None
    created_at: datetime
```

`registry.py` must expose `submit_hypothesis(...)`, `record_result(...)`, and `get_verdict(strategy_id) -> str`, and must refuse to let `strategy_layer` (module 4) load any strategy whose latest verdict is not `PASS`.

## Acceptance criteria for this module itself
- Registry is append-only (no update/delete on existing records — only new attempts).
- `get_verdict()` for Breakout and Scalping returns `FAIL` by default, seeded from the table above, before any new test is run.
- A unit test proves that a strategy with no registry entry cannot be loaded by module 4.

## When done
Add an entry to `docs/implementation-log.md` describing which candidate strategies were run, their verdicts, and where the full experiment writeups live.
