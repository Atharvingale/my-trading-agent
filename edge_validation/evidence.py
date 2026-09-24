"""Verifiable, dependency-free evidence primitives for edge-validation results."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import random
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ExperimentEvidence:
    """Immutable summary of a completed, reproducible holdout experiment.

    ``trade_returns`` must already include fees, slippage, VDA tax, and TDS
    treatment described by the registered assumptions.  The object records the
    provenance needed to distinguish computed evidence from caller assertions.
    """

    dataset_id: str
    dataset_sha256: str
    trade_returns: tuple[float, ...]
    regime_returns: Mapping[str, float]
    net_of_costs_and_tax: bool
    bootstrap_seed: int = 0
    bootstrap_samples: int = 10_000

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ValueError("dataset_id must not be empty")
        if not _is_sha256(self.dataset_sha256):
            raise ValueError("dataset_sha256 must be a 64-character hexadecimal SHA-256")
        if not self.trade_returns:
            raise ValueError("trade_returns must contain at least one observation")
        if any(not _finite_number(value) for value in self.trade_returns):
            raise ValueError("trade_returns must contain only finite numbers")
        if not self.net_of_costs_and_tax:
            raise ValueError("evidence must be net of costs and tax")
        if self.bootstrap_samples < 1_000:
            raise ValueError("bootstrap_samples must be at least 1000")
        for name, value in self.regime_returns.items():
            if not isinstance(name, str) or not name.strip() or not _finite_number(value):
                raise ValueError("regime_returns must map names to finite numbers")

    @property
    def net_return(self) -> float:
        """Arithmetic mean of per-trade net returns, with no hidden compounding."""
        return sum(self.trade_returns) / len(self.trade_returns)

    @property
    def bootstrap_ci(self) -> tuple[float, float]:
        """Return a reproducible percentile bootstrap CI for mean net return."""
        rng = random.Random(self.bootstrap_seed)
        observations = self.trade_returns
        means = []
        for _ in range(self.bootstrap_samples):
            total = 0.0
            for _ in observations:
                total += observations[rng.randrange(len(observations))]
            means.append(total / len(observations))
        means.sort()
        return (_percentile(means, 0.025), _percentile(means, 0.975))

    def fingerprint(self) -> str:
        """Hash the evidence metadata and observations for audit logging."""
        payload = {
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "trade_returns": list(self.trade_returns),
            "regime_returns": dict(sorted(self.regime_returns.items())),
            "net_of_costs_and_tax": self.net_of_costs_and_tax,
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_sha256(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _percentile(values: Sequence[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] + (values[upper] - values[lower]) * weight)
