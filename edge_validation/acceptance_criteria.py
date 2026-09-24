"""Seven auditable checks required before an edge-validation verdict can pass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


CRITERION_IDS = (
    "preregistered_before_holdout",
    "fresh_holdout_for_strategy_family",
    "net_of_fees_slippage_and_vda_tax",
    "positive_bootstrap_confidence_interval",
    "two_structurally_different_regimes",
    "independent_replication_when_refined",
    "null_result_recorded_without_retries",
)


@dataclass(frozen=True)
class AcceptanceCriteria:
    """Checklist of evidence produced by a completed validation attempt."""

    checks: Mapping[str, bool]

    def __post_init__(self) -> None:
        missing = []
        unknown = []
        for criterion_id in CRITERION_IDS:
            if criterion_id not in self.checks:
                missing.append(criterion_id)
        for criterion_id in self.checks:
            if criterion_id not in CRITERION_IDS:
                unknown.append(criterion_id)
        if missing or unknown:
            raise ValueError(
                "criteria must contain all seven known checks; "
                f"missing={missing}, unknown={unknown}"
            )
        for criterion_id in CRITERION_IDS:
            if not isinstance(self.checks[criterion_id], bool):
                raise ValueError(f"criterion {criterion_id} must be boolean")

    @property
    def all_pass(self) -> bool:
        for criterion_id in CRITERION_IDS:
            if not self.checks[criterion_id]:
                return False
        return True

    def as_dict(self) -> dict[str, bool]:
        result = {}
        for criterion_id in CRITERION_IDS:
            result[criterion_id] = self.checks[criterion_id]
        return result
