"""Multiple-testing correction for the research plane (Module 15).

Why this file exists: testing more ideas must make each attempt harder to
pass, not easier — otherwise lucky-looking flukes eventually pass by chance.
Bonferroni (required alpha = base alpha / total tested) is the chosen method:
simple, conservative, and auditable. The count reads from the existing
edge_validation_records table so humans and AI share one budget.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


BASE_ALPHA = 0.05
CORRECTION_METHOD = "bonferroni"


def required_significance(base_alpha: float = BASE_ALPHA, total_tested: int = 1) -> float:
    """Return the Bonferroni-adjusted alpha for m hypotheses tested so far."""
    alpha = float(base_alpha)
    if alpha <= 0.0 or alpha >= 1.0:
        raise ValueError("base_alpha must be in (0, 1)")
    total = int(total_tested)
    if total < 1:
        raise ValueError("total_tested must be at least 1")
    return alpha / float(total)


def count_hypotheses(registry: Any = None, database_path: str | Path | None = None) -> int:
    """Count preregistered attempts from the edge-validation ledger.

    Accepts a live EdgeValidationRegistry (preferred), a database file path,
    or neither (returns 0 when no ledger is reachable). Counts HYPOTHESIS rows
    only, so RESULT rows never inflate the budget.
    """
    if registry is not None:
        rows = registry.connection.execute(
            "SELECT COUNT(*) AS total FROM edge_validation_records WHERE event_type='HYPOTHESIS'"
        ).fetchone()
        return int(rows["total"])
    if database_path is not None:
        target = Path(database_path)
        if not target.exists():
            return 0
        connection = sqlite3.connect(target)
        try:
            rows = connection.execute(
                "SELECT COUNT(*) AS total FROM edge_validation_records WHERE event_type='HYPOTHESIS'"
            ).fetchone()
            return int(rows[0])
        except sqlite3.OperationalError:
            return 0
        finally:
            connection.close()
    return 0


def adjusted_threshold(
    registry: Any = None,
    database_path: str | Path | None = None,
    base_alpha: float = BASE_ALPHA,
    family: str = "all",
) -> dict[str, Any]:
    """Compute the current bar: count, method, base and required alpha.

    The family label is provenance only (per-gate-family budgets stay a manual
    decision); the count itself is global so splitting families cannot reset it.
    """
    total = count_hypotheses(registry=registry, database_path=database_path)
    effective = total + 1
    if effective < 1:
        effective = 1
    required = required_significance(base_alpha=base_alpha, total_tested=effective)
    return {
        "method": CORRECTION_METHOD,
        "family": str(family),
        "base_alpha": float(base_alpha),
        "total_tested_including_current": effective,
        "required_alpha": required,
    }


def meets_adjusted_bar(observed_alpha: float, required_alpha: float) -> bool:
    """True only when the observed significance clears the adjusted bar."""
    observed = float(observed_alpha)
    required = float(required_alpha)
    if observed <= 0.0 or observed >= 1.0:
        raise ValueError("observed_alpha must be in (0, 1)")
    if required <= 0.0 or required >= 1.0:
        raise ValueError("required_alpha must be in (0, 1)")
    return observed <= required
