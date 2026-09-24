"""Hermes observer loop (Module 3).

Subscribes to REST snapshots and WS events from the hardened market-data
service and produces decision-ready MarketContext objects via ContextBuilder.
Analysis-only: no trading calls, no imports from strategies, risk, execution,
or decision code. Module 5 subscribes to context-ready events through
subscribe() instead of this module calling outward.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Mapping

from hermes.context import ContextBuilder
from hermes.models.market import MarketContext

logger = logging.getLogger(__name__)


class HermesObserver:
    def __init__(
        self,
        store: Any | None = None,
        builder: ContextBuilder | None = None,
        *,
        symbols: list[str] | tuple[str, ...] | None = None,
        emit_interval_ms: int = 5000,
        stale_after_seconds: float = 30.0,
    ) -> None:
        self.store = store
        self.builder = builder or ContextBuilder(
            stale_after_seconds=stale_after_seconds,
            emit_interval_ms=emit_interval_ms,
        )
        self.symbols: tuple[str, ...] = ()
        if symbols is not None:
            collected: list[str] = []
            for item in symbols:
                token = str(item).upper()
                found = False
                for existing in collected:
                    if existing == token:
                        found = True
                if found is False:
                    collected.append(token)
            self.symbols = tuple(collected)
        self._contexts: dict[str, MarketContext] = {}
        self._last_emit_ms: dict[str, int] = {}
        self._ready_events: list[MarketContext] = []
        self._subscribers: list[Callable[[MarketContext], None]] = []
        self._live_event_time: dict[str, int] = {}
        self._live_features: dict[str, dict[str, Any]] = {}
        self._live_breadth: dict[str, Any] | None = None
        self._live_cross: dict[str, dict[str, Any]] = {}
        self._stop = asyncio.Event()

    def subscribe(self, callback: Callable[[MarketContext], None]) -> None:
        # Module 5 hook: notified on every context-ready emit, never called inward.
        self._subscribers.append(callback)

    def tracked_symbols(self) -> tuple[str, ...]:
        return tuple(self.symbols)

    def latest_context(self, symbol: str) -> MarketContext | None:
        return self._contexts.get(str(symbol).upper())

    def pending_ready_events(self) -> list[MarketContext]:
        # Drainable copy so callers can assert without mutating internals.
        drained: list[MarketContext] = []
        for item in self._ready_events:
            drained.append(item)
        return drained

    def clear_ready_events(self) -> None:
        self._ready_events = []

    def handle_market_event(self, message: Mapping[str, Any]) -> None:
        # WS market_event: {type, symbol, event_time_ms, payload}.
        symbol = message.get("symbol")
        if symbol is None:
            return
        token = str(symbol).upper()
        event_time = message.get("event_time_ms")
        try:
            if event_time is not None:
                self._live_event_time[token] = int(event_time)
        except (TypeError, ValueError):
            pass
        self._ensure_tracked(token)

    def handle_breadth(self, message: Mapping[str, Any]) -> None:
        # WS breadth: {type, event_time_ms, payload}.
        payload = message.get("payload", message)
        if isinstance(payload, Mapping):
            stored: dict[str, Any] = {}
            for key in payload:
                stored[key] = payload[key]
            self._live_breadth = stored

    def handle_cross_exchange(self, message: Mapping[str, Any]) -> None:
        # WS cross_exchange_confirmation: {symbol, payload}.
        symbol = message.get("symbol")
        payload = message.get("payload", message)
        if symbol is None or not isinstance(payload, Mapping):
            return
        token = str(symbol).upper()
        stored: dict[str, Any] = {}
        for key in payload:
            stored[key] = payload[key]
        self._live_cross[token] = stored
        self._ensure_tracked(token)

    def handle_universe_update(self, message: Mapping[str, Any]) -> None:
        # WS universe_update: {symbols, ...} becomes the tracked set.
        raw_symbols = message.get("symbols", ())
        if not isinstance(raw_symbols, (list, tuple)):
            return
        collected: list[str] = []
        for item in raw_symbols:
            token = str(item).upper()
            found = False
            for existing in collected:
                if existing == token:
                    found = True
            if found is False:
                collected.append(token)
        self.symbols = tuple(collected)
        for token in collected:
            self._ensure_tracked(token)

    def refresh_once(
        self,
        snapshots: Mapping[str, Mapping[str, Any] | None],
        event_times: Mapping[str, int | None],
        *,
        breadth: Mapping[str, Any] | None = None,
        cross_by_symbol: Mapping[str, Mapping[str, Any] | None] | None = None,
        health_entries: list[Mapping[str, Any]] | None = None,
        portfolio_by_symbol: Mapping[str, Mapping[str, Any] | None] | None = None,
        strategy_state: Mapping[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> list[MarketContext]:
        # Deterministic single pass used by tests and by refresh_from_store.
        observed = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        emitted: list[MarketContext] = []
        for symbol in snapshots:
            token = str(symbol).upper()
            self._ensure_tracked(token)
            snapshot = snapshots[symbol]
            event_time = event_times.get(symbol)
            cross_value: Mapping[str, Any] | None = None
            if cross_by_symbol is not None and symbol in cross_by_symbol:
                cross_value = cross_by_symbol[symbol]
            elif token in self._live_cross:
                cross_value = self._live_cross[token]
            portfolio_value: Mapping[str, Any] | None = None
            if portfolio_by_symbol is not None and symbol in portfolio_by_symbol:
                portfolio_value = portfolio_by_symbol[symbol]
            prior = self._contexts.get(token)
            current = self.builder.build(
                symbol=token,
                feature_snapshot=snapshot,
                event_time_ms=event_time,
                breadth=breadth if breadth is not None else self._live_breadth,
                cross_exchange=cross_value,
                health_entries=health_entries,
                portfolio=portfolio_value,
                strategy_state=strategy_state,
                prior=prior,
                now_ms=observed,
            )
            self._contexts[token] = current
            last_emit = self._last_emit_ms.get(token)
            decision, reason = self.builder.should_emit(prior, current, last_emit)
            if decision:
                emitted_context = MarketContext(
                    symbol=current.symbol,
                    timestamp_ms=current.timestamp_ms,
                    valid=current.valid,
                    invalid_reasons=current.invalid_reasons,
                    regime=current.regime,
                    trend=current.trend,
                    order_flow=current.order_flow,
                    derivatives=current.derivatives,
                    options=current.options,
                    liquidity=current.liquidity,
                    cross_exchange=current.cross_exchange,
                    data_quality=current.data_quality,
                    portfolio=current.portfolio,
                    strategy=current.strategy,
                    emit_reason=reason,
                )
                self._contexts[token] = emitted_context
                self._ready_events.append(emitted_context)
                self._last_emit_ms[token] = observed
                emitted.append(emitted_context)
                for callback in self._subscribers:
                    try:
                        callback(emitted_context)
                    except Exception as exc:
                        logger.warning("Context subscriber failed: %s", exc)
        return emitted

    def refresh_from_store(
        self,
        collector: Any | None = None,
        *,
        now_ms: int | None = None,
    ) -> list[MarketContext]:
        # Read-only pull from the hardened service: collector states when
        # available, otherwise MarketStore REST readers. Never writes.
        observed = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        snapshots: dict[str, Mapping[str, Any] | None] = {}
        event_times: dict[str, int | None] = {}
        symbols_to_read: list[str] = []
        for token in self.symbols:
            symbols_to_read.append(token)
        if len(symbols_to_read) == 0 and collector is not None:
            states = getattr(collector, "states", {})
            if isinstance(states, Mapping):
                for key in states:
                    symbols_to_read.append(str(key).upper())
        if collector is not None:
            states = getattr(collector, "states", {})
            for token in symbols_to_read:
                state = None
                if isinstance(states, Mapping):
                    if token in states:
                        state = states[token]
                    elif token.lower() in states:
                        state = states[token.lower()]
                if state is not None:
                    try:
                        snapshot_value = state.features()
                    except Exception:
                        snapshot_value = None
                    snapshots[token] = snapshot_value
                    live_override = self._live_event_time.get(token)
                    if live_override is not None:
                        event_times[token] = live_override
                    else:
                        event_times[token] = getattr(state, "last_event_time_ms", None)
                else:
                    snapshots[token] = None
                    event_times[token] = self._live_event_time.get(token)
        else:
            for token in symbols_to_read:
                snapshots[token] = None
                event_times[token] = self._live_event_time.get(token)
        breadth_value: Mapping[str, Any] | None = self._live_breadth
        cross_map: dict[str, Mapping[str, Any] | None] = {}
        for token in symbols_to_read:
            if token in self._live_cross:
                cross_map[token] = self._live_cross[token]
        health_list: list[Mapping[str, Any]] = []
        store = self.store
        if store is None and collector is not None:
            store = getattr(collector, "store", None)
        if store is not None:
            try:
                if breadth_value is None and hasattr(store, "latest_breadth"):
                    breadth_value = store.latest_breadth()
            except Exception:
                pass
            try:
                if hasattr(store, "recent_health"):
                    for entry in store.recent_health(limit=100):
                        health_list.append(entry)
            except Exception:
                pass
            if hasattr(store, "latest_cross_exchange"):
                for token in symbols_to_read:
                    if token not in cross_map:
                        try:
                            cross_map[token] = store.latest_cross_exchange(token)
                        except Exception:
                            cross_map[token] = None
        return self.refresh_once(
            snapshots,
            event_times,
            breadth=breadth_value,
            cross_by_symbol=cross_map,
            health_entries=health_list,
            now_ms=observed,
        )

    async def run_forever(self, interval_seconds: float = 1.0) -> None:
        # Continuous analysis-only loop; stop() halts it for shutdown tests.
        pause = max(0.05, float(interval_seconds))
        while not self._stop.is_set():
            try:
                self.refresh_from_store()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Observer refresh failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=pause)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()

    def _ensure_tracked(self, token: str) -> None:
        found = False
        for existing in self.symbols:
            if existing == token:
                found = True
        if found is False:
            self.symbols = self.symbols + (token,)
