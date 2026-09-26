"""Order/position/trade lifecycle monitoring (Module 8).

Operational state machine plus reconciliation: orders through fills into
positions and closed trades, with SUBMISSION_UNKNOWN gating new entries until
exchange truth resolves them. Lifecycle records mirror into the existing
MemoryRepository; this package never replaces the Module 7 request ledger.
"""

from monitoring.positions import LifecycleTracker

__all__ = ["LifecycleTracker"]
