"""Rule-based post-trade diagnosis (Module 9).

Why fixed rules, not judgment: the analyzer answers the twelve post-trade
questions from recorded evidence only, in a fixed priority order, so the same
trade always yields the same category. GATE/DATA/RISK errors outrank outcome
analysis because a broken pipe invalidates any reading of the result. A lone
adverse outcome with valid plumbing is NORMAL variance — never an auto-edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4


CATEGORIES = ("SIGNAL", "REGIME", "EXECUTION", "RISK", "DATA", "GATE", "NORMAL")

ACTIONS = {
    "SIGNAL": "candidate lesson",
    "REGIME": "candidate regime filter",
    "EXECUTION": "review liquidity threshold",
    "RISK": "block deployment, audit risk path",
    "DATA": "mark non-actionable, investigate",
    "GATE": "immediate halt of that strategy",
    "NORMAL": "no change",
}

QUESTIONS = (
    "expected_move",
    "supporting_features",
    "strategy_agreement",
    "actual_move",
    "entry_timing",
    "liquidity_drift",
    "order_flow_thesis",
    "stop_target_consistency",
    "execution_vs_plan",
    "external_change",
    "loss_attribution",
    "actionable",
)


@dataclass(frozen=True)
class TradeAnalysis:
    analysis_id: str
    trade_id: str
    answers: dict[str, Any]
    category: str
    actionable: bool
    candidate_hypothesis: str | None
    recommended_action: str


def analyze_trade(
    closed_trade: Mapping[str, Any],
    *,
    context_valid: bool | None = None,
    gate_record_ok: bool | None = None,
    approved_quantity: float | None = None,
    estimated_slippage_bps: float = 10.0,
    regime_fit: bool | None = None,
    external_change: bool = False,
) -> TradeAnalysis:
    """Diagnose one closed trade; deterministic for identical inputs.

    Evidence flags are explicit caller inputs (no hidden inference):
    context_valid (Module 3 flag), gate_record_ok (PASS-linked and current),
    approved_quantity (Module 6 sealed size), regime_fit (strategy suited to
    the entry regime). Unknown plumbing fails toward DATA, never NORMAL.
    """
    trade = dict(closed_trade)
    trade_id = str(trade.get("trade_id", "")).strip()
    if not trade_id:
        raise ValueError("closed_trade must carry a trade_id")
    answers: dict[str, Any] = {}
    answers["expected_move"] = trade.get("thesis")
    answers["supporting_features"] = trade.get("evidence")
    answers["strategy_agreement"] = trade.get("strategy_votes")
    answers["actual_move"] = trade.get("realized_pnl")
    answers["entry_timing"] = _entry_timing(trade)
    answers["liquidity_drift"] = trade.get("avg_slippage")
    answers["order_flow_thesis"] = trade.get("order_flow_note")
    answers["stop_target_consistency"] = _stop_target_note(trade)
    answers["execution_vs_plan"] = _execution_gap(trade, approved_quantity)
    answers["external_change"] = bool(external_change)
    # Fixed priority: broken pipe first, outcome analysis last.
    if gate_record_ok is False:
        answers["loss_attribution"] = "gate"
        answers["actionable"] = True
        return _verdict(trade_id, answers, "GATE", True, None)
    if gate_record_ok is None or context_valid is None:
        answers["loss_attribution"] = "data"
        answers["actionable"] = True
        return _verdict(
            trade_id, answers, "DATA", True,
            "plumbing evidence incomplete; investigate before reading the outcome",
        )
    if context_valid is False:
        answers["loss_attribution"] = "data"
        answers["actionable"] = True
        return _verdict(
            trade_id, answers, "DATA", True,
            "stale or contradictory context contributed; mark non-actionable",
        )
    if approved_quantity is not None:
        executed = _executed_quantity(trade)
        if executed is not None and abs(executed - float(approved_quantity)) > 1e-9:
            answers["loss_attribution"] = "risk"
            answers["actionable"] = True
            return _verdict(
                trade_id, answers, "RISK", True,
                "executed %.6f differs from approved %.6f; block deployment" % (
                    executed, float(approved_quantity)),
            )
    actual_slip = _number(trade.get("avg_slippage"))
    estimate = float(estimated_slippage_bps)
    if actual_slip is not None and actual_slip > max(2.0 * estimate, 25.0):
        answers["loss_attribution"] = "execution"
        answers["actionable"] = True
        return _verdict(
            trade_id, answers, "EXECUTION", True,
            "slippage %.1f bps materially exceeded %.1f bps estimate; review threshold" % (
                actual_slip, estimate),
        )
    if regime_fit is False:
        answers["loss_attribution"] = "regime"
        answers["actionable"] = True
        return _verdict(
            trade_id, answers, "REGIME", True,
            "strategy ran outside its favorable regime; candidate filter",
        )
    pnl = _number(trade.get("realized_pnl"))
    mfe = _number(trade.get("mfe")) or 0.0
    mae = _number(trade.get("mae")) or 0.0
    if pnl is not None and pnl < 0 and mae > 2.0 * max(mfe, 1e-9):
        answers["loss_attribution"] = "signal"
        answers["actionable"] = True
        return _verdict(
            trade_id, answers, "SIGNAL", True,
            "adverse excursion dominated; candidate signal lesson",
        )
    answers["loss_attribution"] = "normal"
    answers["actionable"] = False
    return _verdict(trade_id, answers, "NORMAL", False, None)


def _verdict(
    trade_id: str, answers: dict[str, Any], category: str,
    actionable: bool, hypothesis: str | None,
) -> TradeAnalysis:
    copied: dict[str, Any] = {}
    for key in answers:
        copied[key] = answers[key]
    return TradeAnalysis(
        analysis_id="ana_" + str(uuid4()).replace("-", "")[:16],
        trade_id=trade_id,
        answers=copied,
        category=category,
        actionable=actionable,
        candidate_hypothesis=hypothesis,
        recommended_action=ACTIONS[category],
    )


def _entry_timing(trade: dict[str, Any]) -> str:
    mfe = _number(trade.get("mfe")) or 0.0
    mae = _number(trade.get("mae")) or 0.0
    pnl = _number(trade.get("realized_pnl"))
    if pnl is not None and pnl >= 0:
        return "reasonable"
    if mae > 3.0 * max(mfe, 1e-9):
        return "early-or-wrong"
    return "reasonable"


def _stop_target_note(trade: dict[str, Any]) -> str:
    if trade.get("stop") is None and trade.get("target") is None:
        return "no levels recorded"
    return "levels recorded"


def _execution_gap(trade: dict[str, Any], approved_quantity: float | None) -> str:
    if approved_quantity is None:
        return "no approved baseline provided"
    executed = _executed_quantity(trade)
    if executed is None:
        return "no executed quantity recorded"
    if abs(executed - float(approved_quantity)) > 1e-9:
        return "materially different from plan"
    return "as planned"


def _executed_quantity(trade: dict[str, Any]) -> float | None:
    for field in ("quantity", "filled_quantity", "executed_quantity"):
        value = _number(trade.get(field))
        if value is not None and value > 0:
            return value
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
