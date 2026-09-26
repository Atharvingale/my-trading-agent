"""End-to-end runtime wiring for Hermes (integration phase).

Connects Modules 1–13 and 15 into one restart-safe paper pipeline without
rewriting any module: market events flow through the real observer, strategy,
decision, risk, execution, lifecycle, learning, and research components under
supervisor orchestration. Live trading stays blocked without a real Module 1
PASS plus human approval plus an immutable version.
"""

from runtime.config import RuntimeConfig
from runtime.pipeline import HermesPipeline

__all__ = ["HermesPipeline", "RuntimeConfig"]
