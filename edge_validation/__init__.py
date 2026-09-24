"""Pre-registered, fail-closed strategy edge validation gate."""

from edge_validation.acceptance_criteria import AcceptanceCriteria, CRITERION_IDS
from edge_validation.evidence import ExperimentEvidence
from edge_validation.registry import (
    EdgeValidationRecord,
    EdgeValidationRegistry,
    StrategyNotGatedError,
)

__all__ = [
    "AcceptanceCriteria",
    "CRITERION_IDS",
    "ExperimentEvidence",
    "EdgeValidationRecord",
    "EdgeValidationRegistry",
    "StrategyNotGatedError",
]
