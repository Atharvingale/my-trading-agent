"""Fail-closed data quality decisions and event health tracking."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DataQuality:
    status: str
    reasons: Sequence[str] = ()


def quality_gate(quality: DataQuality) -> dict:
    if quality.status != "GOOD":
        return {"decision": "HOLD", "tradable": False, "reasons": list(quality.reasons) or [quality.status]}
    return {"decision": "PASS", "tradable": True, "reasons": []}


@dataclass
class _EventState:
    last_event_ms: int | None = None
    last_id: str | None = None
    last_final_update_id: int | None = None


class QualityTracker:
    def __init__(self, *, stale_after_ms: int = 30_000) -> None:
        self.stale_after_ms = stale_after_ms
        self._states: dict[tuple[str, str, str], _EventState] = {}

    def observe(
        self,
        source: str,
        symbol: str,
        event_type: str,
        event_time_ms: int,
        received_time_ms: int,
        *,
        event_id: str | int | None = None,
        first_update_id: int | None = None,
        final_update_id: int | None = None,
    ) -> DataQuality:
        key = (source, symbol, event_type)
        state = self._states.setdefault(key, _EventState())
        reasons: list[str] = []
        if state.last_id is not None and event_id is not None and str(event_id) == state.last_id:
            reasons.append("DUPLICATE")
        if state.last_event_ms is not None and event_time_ms < state.last_event_ms:
            reasons.append("OUT_OF_ORDER")
        if first_update_id is not None and final_update_id is not None and state.last_final_update_id is not None:
            if first_update_id > state.last_final_update_id + 1:
                reasons.append("SEQUENCE_GAP")
        if received_time_ms < event_time_ms:
            reasons.append("CLOCK_OR_FUTURE_EVENT")
        state.last_event_ms = max(state.last_event_ms or event_time_ms, event_time_ms)
        state.last_id = str(event_id) if event_id is not None else state.last_id
        if final_update_id is not None:
            state.last_final_update_id = max(state.last_final_update_id or final_update_id, final_update_id)
        return DataQuality("DEGRADED" if reasons else "GOOD", tuple(reasons))

    def current(self, source: str, symbol: str, event_type: str, now_ms: int) -> DataQuality:
        state = self._states.get((source, symbol, event_type))
        if state is None:
            return DataQuality("BAD", ("MISSING",))
        age = now_ms - (state.last_event_ms or now_ms)
        return DataQuality("BAD" if age > self.stale_after_ms else "GOOD", ("STALE",) if age > self.stale_after_ms else ())
