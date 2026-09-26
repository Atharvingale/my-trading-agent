"""Durable traceability backbone (Module 10).

Unified SQLite store that links every pipeline stage by stable IDs so any
trade can be reconstructed with one trace(trade_id) call. Append-friendly:
edge_validation_records and strategy_versions reject updates and deletes.
"""

from memory.repository import MemoryRepository

__all__ = ["MemoryRepository"]
