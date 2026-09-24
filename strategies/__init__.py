"""Strategy proposal layer. Load is fail-closed against the edge-validation gate."""

from strategies.registry import load_strategy

__all__ = ["load_strategy"]
