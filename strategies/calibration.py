"""Historical hit-rate confidence calibration (Module 4).

Confidence is a calibrated statistic derived from observed outcomes, never a
hardcoded or arbitrary number. Laplace smoothing keeps small samples honest
and makes the zero-history case explicit instead of dividing by zero.
"""

from __future__ import annotations


def calibrate_confidence(
    hits: int,
    total: int,
    *,
    prior_hits: float = 1.0,
    prior_total: float = 2.0,
) -> float:
    """Return smoothed hit rate in [0, 1] from historical outcomes.

    Why smoothing: with few observations the raw fraction overfits, and with
    zero observations it is undefined. The prior acts as a skeptical default
    of 0.5 that real evidence must move.
    """
    if not isinstance(hits, int) or isinstance(hits, bool):
        raise ValueError("hits must be a non-negative int")
    if not isinstance(total, int) or isinstance(total, bool):
        raise ValueError("total must be a non-negative int")
    if hits < 0 or total < 0 or hits > total:
        raise ValueError("require 0 <= hits <= total")
    prior_h = float(prior_hits)
    prior_t = float(prior_total)
    if not prior_t > 0:
        raise ValueError("prior_total must be positive")
    if not 0.0 <= prior_h <= prior_t:
        raise ValueError("require 0 <= prior_hits <= prior_total")
    value = (hits + prior_h) / (total + prior_t)
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def confidence_from_window_returns(window_returns: tuple[float, ...] | list[float]) -> float:
    """Calibrate from per-window win/loss outcomes (positive = hit).

    Explicit loop (no comprehensions) so the count stays auditable.
    """
    hits = 0
    total = 0
    for value in window_returns:
        total += 1
        number = float(value)
        if number > 0:
            hits += 1
    return calibrate_confidence(hits, total)
