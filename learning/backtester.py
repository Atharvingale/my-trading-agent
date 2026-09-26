"""Candidate evaluation reusing proven Module 1 machinery (Module 9).

Why an adapter, not a new simulator: causal backtesters with fee, slippage,
VDA-tax, and bootstrap evidence already exist and are tested. This module
dispatches known signal families to them and scores trade-return streams with
the same evidence primitives the gate uses. Unknown families return
INCONCLUSIVE — never an invented simulator — and go through the full Module 1
experiment externally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class BacktestReport:
    signal_class: str
    method: str
    trade_count: int
    net_return: float
    bootstrap_ci: tuple[float, float] | None
    hint: str
    reason: str


def run_family_backtest(
    signal_class: str,
    candles: Sequence[Any],
    *,
    fee_rate: float = 0.001,
    slippage_rate: float = 0.001,
) -> BacktestReport:
    """Run the existing causal backtester for a known family.

    Returns a hint only — the gate alone delivers verdicts. Unknown signal
    classes yield INCONCLUSIVE with the reason recorded.
    """
    from edge_validation import experiment as exp

    key = str(signal_class).strip().casefold()
    if "trend" in key and "daily" not in key:
        result = exp.backtest_trend_following(
            candles, fee_rate=fee_rate, slippage_rate=slippage_rate
        )
        family = "trend_following"
    elif "mean" in key:
        result = exp.backtest_mean_reversion(
            candles, fee_rate=fee_rate, slippage_rate=slippage_rate
        )
        family = "mean_reversion"
    elif "vwap" in key:
        result = exp.backtest_vwap_reversion(
            candles, fee_rate=fee_rate, slippage_rate=slippage_rate
        )
        family = "vwap_reversion"
    elif "order" in key or "flow" in key:
        result = exp.backtest_order_flow(
            candles, fee_rate=fee_rate, slippage_rate=slippage_rate
        )
        family = "order_flow"
    else:
        return BacktestReport(
            signal_class=str(signal_class),
            method="none",
            trade_count=0,
            net_return=0.0,
            bootstrap_ci=None,
            hint="INCONCLUSIVE",
            reason="no proven backtester for '%s'; use a full Module 1 experiment" % signal_class,
        )
    trades = 0
    for _trade in result.trades:
        trades = trades + 1
    hint = "FAIL_HINT"
    if result.net_return > 0:
        hint = "PASS_HINT"
    return BacktestReport(
        signal_class=family,
        method="edge_validation.experiment",
        trade_count=trades,
        net_return=result.net_return,
        bootstrap_ci=None,
        hint=hint,
        reason="hint only; the gate computes the binding bootstrap CI",
    )


def evaluate_trade_returns(
    trade_returns: Sequence[float],
    regime_returns: Mapping[str, float],
    *,
    dataset_id: str,
    dataset_sha256: str,
    bootstrap_seed: int = 0,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    """Score a return stream with gate-grade evidence primitives.

    Builds ExperimentEvidence (net-of-costs trade returns required) and
    returns net return plus the reproducible bootstrap CI for gate use.
    """
    from edge_validation.evidence import ExperimentEvidence

    returns: list[float] = []
    for value in trade_returns:
        returns.append(float(value))
    regimes: dict[str, float] = {}
    for name in regime_returns:
        regimes[str(name)] = float(regime_returns[name])
    evidence = ExperimentEvidence(
        dataset_id=dataset_id,
        dataset_sha256=dataset_sha256,
        trade_returns=tuple(returns),
        regime_returns=regimes,
        net_of_costs_and_tax=True,
        bootstrap_seed=bootstrap_seed,
        bootstrap_samples=bootstrap_samples,
    )
    return {
        "net_return": evidence.net_return,
        "bootstrap_ci": evidence.bootstrap_ci,
        "fingerprint": evidence.fingerprint(),
        "evidence": evidence,
    }
