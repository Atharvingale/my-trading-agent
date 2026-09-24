"""Load only strategies whose latest edge-validation verdict is PASS.

Raises, never warns, on ungated loads. Falsified families are rejected with
an explicit message so a future contributor cannot wire them in by accident.
"""

from __future__ import annotations

from edge_validation.registry import EdgeValidationRegistry, StrategyNotGatedError
from strategies.base import LoadedStrategy, require_gate


FALSIFIED_IDS = ("breakout", "scalping")


def _is_falsified(strategy_id: str) -> bool:
    token = str(strategy_id).strip().casefold()
    for falsified in FALSIFIED_IDS:
        if token == falsified or token.startswith(falsified + "_") or token.startswith(falsified + "-"):
            return True
        if falsified == "scalping" and (token == "scalp" or token.startswith("scalp_")):
            return True
    return False


def load_strategy(strategy_id: str, registry: EdgeValidationRegistry) -> LoadedStrategy:
    """Raise StrategyNotGatedError unless the strategy currently has PASS evidence."""
    if _is_falsified(strategy_id):
        raise StrategyNotGatedError(
            "strategy %r is FALSIFIED per 01-edge-validation-gate.md and cannot be loaded" % (strategy_id,)
        )
    record = require_gate(strategy_id, registry)
    version = record.linked_strategy_version_id
    if version is None or not str(version).strip():
        version = "v1"
    else:
        version = str(version).strip()
    return LoadedStrategy(
        strategy_id=record.strategy_id,
        edge_validation_record_id=record.record_id,
        strategy_version=version,
    )
