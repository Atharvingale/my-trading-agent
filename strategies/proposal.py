"""Deterministic proposal factory for gate-approved strategies (Module 4).

This module is not a strategy itself. It turns a LoadedStrategy (which can
only exist after a PASS verdict) plus a MarketContext into a validated
StrategyProposal. Fail-closed: invalid, stale, or malformed context resolves
to HOLD, never to a default BUY or SELL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from strategies.base import StrategyProposal, deterministic_proposal_id
from strategies.base import LoadedStrategy


def build_proposal(
    loaded: LoadedStrategy,
    context: Any,
    *,
    action: str,
    confidence: float,
    evidence: list[dict[str, Any]],
    horizon: str = "15m",
    invalidation_conditions: list[str] | None = None,
    timestamp: datetime | None = None,
) -> StrategyProposal:
    """Validate inputs and return a gate-linked proposal.

    Why each check exists: the edge record link is what makes the proposal
    tradable downstream, so a missing or mismatched link must raise rather
    than silently produce an unlinkable proposal. An invalid context must
    still produce a proposal, but forced to HOLD, so downstream always has
    an auditable record instead of a gap.
    """
    if not isinstance(loaded, LoadedStrategy):
        raise TypeError("loaded must be a LoadedStrategy from load_strategy()")
    if not loaded.edge_validation_record_id.strip():
        raise ValueError("edge_validation_record_id is required, no default, no None")
    requested = str(action).strip().upper()
    if requested not in ("BUY", "SELL", "HOLD"):
        raise ValueError("action must be BUY, SELL, or HOLD")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        raise ValueError("confidence must be a number in [0, 1]")
    if isinstance(confidence, bool):
        raise ValueError("confidence must be a number in [0, 1]")
    if not 0.0 <= confidence_value <= 1.0:
        raise ValueError("confidence must be within [0, 1]")
    if not isinstance(evidence, list) or len(evidence) == 0:
        raise ValueError("evidence must be a non-empty list of MarketContext references")
    for entry in evidence:
        if not isinstance(entry, dict):
            raise ValueError("evidence entries must be dicts")
    symbol = getattr(context, "symbol", "")
    token = str(symbol).strip().upper()
    if not token:
        raise ValueError("context.symbol must be non-empty")
    valid = bool(getattr(context, "valid", False))
    # Fail-closed: ambiguous or invalid context never yields BUY/SELL.
    final_action = requested
    if valid is False:
        final_action = "HOLD"
    conditions: list[str] = []
    if invalidation_conditions is not None:
        for condition in invalidation_conditions:
            if not isinstance(condition, str) or not condition.strip():
                raise ValueError("invalidation_conditions must be non-empty strings")
            conditions.append(condition.strip())
    if len(conditions) == 0:
        conditions.append("context.valid == False")
        conditions.append("regime flips against entry")
    moment = timestamp
    if moment is None:
        stamp = getattr(context, "timestamp_ms", None)
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
            moment = datetime.fromtimestamp(float(stamp) / 1000.0, tz=timezone.utc)
        else:
            moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    version = str(loaded.strategy_version).strip() or "v1"
    proposal_id = deterministic_proposal_id(
        strategy_id=loaded.strategy_id,
        strategy_version=version,
        symbol=token,
        timestamp=moment,
        action=final_action,
    )
    evidence_copy: list[dict[str, Any]] = []
    for entry in evidence:
        copied: dict[str, Any] = {}
        for key in entry:
            copied[key] = entry[key]
        evidence_copy.append(copied)
    return StrategyProposal(
        proposal_id=proposal_id,
        strategy_id=loaded.strategy_id,
        strategy_version=version,
        edge_validation_record_id=loaded.edge_validation_record_id,
        symbol=token,
        action=final_action,  # type: ignore[arg-type]
        confidence=confidence_value,
        evidence=evidence_copy,
        horizon=str(horizon).strip() or "15m",
        invalidation_conditions=conditions,
        timestamp=moment,
    )


def evidence_ref(feature: str, value: Any) -> dict[str, Any]:
    """One structured pointer into a MarketContext field for audit trails."""
    name = str(feature).strip()
    if not name:
        raise ValueError("evidence feature name must be non-empty")
    return {"feature": name, "value": value}


def describe_context_evidence(context: Any) -> list[dict[str, Any]]:
    """Template evidence list derived from structured context fields only."""
    evidence: list[dict[str, Any]] = []
    regime = getattr(context, "regime", None)
    trend = getattr(context, "trend", None)
    order_flow = getattr(context, "order_flow", None)
    if regime is not None:
        evidence.append(evidence_ref("regime", getattr(regime, "regime", None)))
        evidence.append(evidence_ref("volatility_state", getattr(regime, "volatility_state", None)))
    if trend is not None:
        evidence.append(evidence_ref("ema_alignment", getattr(trend, "multi_timeframe_alignment", None)))
        evidence.append(evidence_ref("rsi", getattr(trend, "rsi", None)))
    if order_flow is not None:
        evidence.append(evidence_ref("order_flow_cvd", getattr(order_flow, "cvd", None)))
    return evidence
