"""Shared exponential backoff for collector reconnect and REST loops."""

from __future__ import annotations


def next_backoff_seconds(current: float, maximum: float = 60.0, factor: float = 2.0) -> float:
    """Double the delay and clamp it so reconnects cannot wait forever."""
    if current <= 0:
        current = 1.0
    nxt = current * factor
    if nxt > maximum:
        return maximum
    return nxt
