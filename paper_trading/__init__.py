"""Paper-trading simulation support (Step 1B).

Deterministic, offline, credential-free. Simulates hypothetical fills against
caller-supplied market snapshots so research can measure expected-vs-realized
execution without touching any exchange. Never places real orders.
"""

from paper_trading.engine import PaperEngine
from paper_trading.portfolio import PaperPortfolio
from paper_trading.simulator import (
    InsufficientPositionError,
    PaperFill,
    PaperOrder,
    execution_report,
    simulate_fill,
)

__all__ = [
    "InsufficientPositionError",
    "PaperEngine",
    "PaperFill",
    "PaperOrder",
    "PaperPortfolio",
    "execution_report",
    "simulate_fill",
]
