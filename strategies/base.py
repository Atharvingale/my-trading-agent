"""Abstract strategy proposal contract plus load-time gate check.

The gate itself lives in edge_validation.registry. This module only adds the
proposal shape validation and a single helper that strategy modules and the
registry must call at load time, so an ungated strategy raises instead of
only being documented as forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid5, NAMESPACE_URL


ACTIONS = ("BUY", "SELL", "HOLD")


@dataclass(frozen=True)
class StrategyProposal:
    proposal_id: str
    strategy_id: str
    strategy_version: str
    edge_validation_record_id: str
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    evidence: list[dict[str, Any]]
    horizon: str
    invalidation_conditions: list[str]
    timestamp: datetime

    def __post_init__(self) -> None:
        # Fail-closed validation: a malformed proposal never leaves the layer.
        if not self.proposal_id.strip():
            raise ValueError("proposal_id must be non-empty")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must be non-empty")
        if not self.edge_validation_record_id.strip():
            raise ValueError("edge_validation_record_id is required, no default, no None")
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if self.action not in ACTIONS:
            raise ValueError("action must be BUY, SELL, or HOLD")
        confidence = self.confidence
        if isinstance(confidence, bool):
            raise ValueError("confidence must be a number in [0, 1]")
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            raise ValueError("confidence must be a number in [0, 1]")
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not isinstance(self.evidence, list):
            raise ValueError("evidence must be a list of MarketContext references")
        for entry in self.evidence:
            if not isinstance(entry, dict):
                raise ValueError("evidence entries must be dicts")
        if not isinstance(self.invalidation_conditions, list):
            raise ValueError("invalidation_conditions must be a list")
        for condition in self.invalidation_conditions:
            if not isinstance(condition, str) or not condition.strip():
                raise ValueError("invalidation_conditions must be non-empty strings")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")


@dataclass(frozen=True)
class LoadedStrategy:
    """A strategy identity that has a current PASS record in the edge gate."""

    strategy_id: str
    edge_validation_record_id: str
    strategy_version: str = "ungenerated"


def require_gate(strategy_id: str, registry: Any) -> Any:
    """Load-time gate check every strategy module must call on import.

    Raises StrategyNotGatedError unless the strategy currently has PASS
    evidence. Returns the passing edge record for version wiring.
    """
    record = registry.require_pass(strategy_id)
    return record


def deterministic_proposal_id(
    *,
    strategy_id: str,
    strategy_version: str,
    symbol: str,
    timestamp: datetime,
    action: str,
) -> str:
    # Deterministic ID so repeated runs on the same inputs are byte-identical.
    moment = timestamp
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seed = "|".join(
        (
            str(strategy_id).strip().upper(),
            str(strategy_version).strip(),
            str(symbol).strip().upper(),
            moment.astimezone(timezone.utc).isoformat(),
            str(action).strip().upper(),
        )
    )
    return str(uuid5(NAMESPACE_URL, "strategy-proposal:" + seed))
