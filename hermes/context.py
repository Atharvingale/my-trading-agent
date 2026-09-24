"""Deterministic MarketContext builder (Module 3).

Pure producer for Module 5. No imports from strategies, risk, or execution.
Fail-closed: stale, incomplete, or contradictory upstream state yields
valid=False instead of a best-effort guess.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from hermes.models.market import (
    CrossExchangeState,
    DataQualityState,
    DerivativesState,
    LiquidityState,
    MarketContext,
    OptionsState,
    OrderFlowState,
    PortfolioState,
    RegimeState,
    StrategyState,
    TrendState,
    coerce_portfolio,
    coerce_strategy_state,
)


class ContextBuilder:
    def __init__(
        self,
        *,
        stale_after_seconds: float = 30.0,
        emit_interval_ms: int = 5000,
        max_disagreement_bps: float = 50.0,
    ) -> None:
        self.stale_after_seconds = max(1.0, float(stale_after_seconds))
        self.emit_interval_ms = max(100, int(emit_interval_ms))
        self.max_disagreement_bps = float(max_disagreement_bps)

    def build(
        self,
        *,
        symbol: str,
        feature_snapshot: Mapping[str, Any] | None,
        event_time_ms: int | None,
        breadth: Mapping[str, Any] | None,
        cross_exchange: Mapping[str, Any] | None,
        health_entries: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
        portfolio: Mapping[str, Any] | PortfolioState | None = None,
        strategy_state: Mapping[str, Any] | StrategyState | None = None,
        prior: MarketContext | None = None,
        now_ms: int | None = None,
    ) -> MarketContext:
        # Use explicit wall-clock default so tests can inject deterministic time.
        import time

        observed_ms = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        token = str(symbol).upper()
        reasons: list[str] = []
        # Step 1: freshness from the market-data event clock.
        age_seconds: float | None = None
        if event_time_ms is None:
            reasons.append("MISSING_EVENT_TIME")
        else:
            age_seconds = max(0.0, (observed_ms - int(event_time_ms)) / 1000.0)
            if age_seconds > self.stale_after_seconds:
                reasons.append("STALE")
        # Step 2: completeness of the feature snapshot itself.
        missing: list[str] = []
        snapshot: dict[str, Any] = {}
        if feature_snapshot is None:
            reasons.append("MISSING_SNAPSHOT")
            missing.append("snapshot")
        else:
            for key in feature_snapshot:
                snapshot[key] = feature_snapshot[key]
            if not snapshot.get("symbol"):
                missing.append("symbol")
            if not snapshot.get("event_time"):
                missing.append("event_time")
            for field_name in missing:
                _ = field_name
            if len(missing) > 0:
                reasons.append("INCOMPLETE")
        # Step 3: contradiction from upstream data-health signals.
        health_status = "UNKNOWN"
        sequence_status = "UNKNOWN"
        bad_components: list[str] = []
        entries: list[Mapping[str, Any]] = []
        if health_entries is not None:
            for entry in health_entries:
                entries.append(entry)
        for entry in entries:
            status = str(entry.get("status", "")).upper()
            component = str(entry.get("component", ""))
            entry_symbol = entry.get("symbol")
            # Only consider entries for this symbol or global components.
            applies = False
            if entry_symbol is None or str(entry_symbol) == "":
                applies = True
            elif str(entry_symbol).upper() == token:
                applies = True
            if applies is False:
                continue
            if status in ("BAD", "DEGRADED", "DISCONNECTED", "ERROR", "STALE"):
                bad_components.append(component + ":" + status)
            if status == "GOOD" or status == "CONNECTED" or status == "OK":
                if health_status == "UNKNOWN":
                    health_status = "GOOD"
            else:
                health_status = status
            details = entry.get("details")
            if isinstance(details, Mapping):
                reasons_list = details.get("reasons")
                if isinstance(reasons_list, (list, tuple)):
                    has_gap = False
                    for item in reasons_list:
                        if str(item) in ("SEQUENCE_GAP", "DUPLICATE", "OUT_OF_ORDER"):
                            has_gap = True
                    if has_gap:
                        sequence_status = "DEGRADED"
        if len(bad_components) > 0:
            reasons.append("UPSTREAM_UNHEALTHY")
        if sequence_status == "UNKNOWN":
            if len(bad_components) > 0:
                sequence_status = "DEGRADED"
            else:
                sequence_status = "OK"
        # Cross-exchange contradiction: CONFIRMED with wide disagreement.
        cross_state = self._build_cross_exchange(cross_exchange)
        if cross_state.status == "CONFIRMED" and cross_state.disagreement_bps is not None:
            if cross_state.disagreement_bps > self.max_disagreement_bps:
                reasons.append("CROSS_EXCHANGE_CONTRADICTION")
        # Fail-closed verdict.
        valid = len(reasons) == 0
        # Build deterministic sections even when invalid so callers can inspect.
        trend = self._build_trend(snapshot)
        order_flow = self._build_order_flow(snapshot)
        derivatives = self._build_derivatives(snapshot)
        options = self._build_options(snapshot)
        liquidity = self._build_liquidity(snapshot)
        regime = self._build_regime(trend, breadth, snapshot, prior)
        data_quality = DataQualityState(
            freshness="STALE" if "STALE" in reasons else ("MISSING" if "MISSING_SNAPSHOT" in reasons or "MISSING_EVENT_TIME" in reasons else "FRESH"),
            age_seconds=age_seconds,
            missing_fields=tuple(missing),
            sequence_status=sequence_status,
            rest_ws_health=health_status,
        )
        portfolio_state = coerce_portfolio(portfolio)
        strategy_value = coerce_strategy_state(strategy_state)
        unique_reasons: list[str] = []
        for reason in reasons:
            found = False
            for existing in unique_reasons:
                if existing == reason:
                    found = True
            if found is False:
                unique_reasons.append(reason)
        return MarketContext(
            symbol=token,
            timestamp_ms=observed_ms,
            valid=valid,
            invalid_reasons=tuple(unique_reasons),
            regime=regime,
            trend=trend,
            order_flow=order_flow,
            derivatives=derivatives,
            options=options,
            liquidity=liquidity,
            cross_exchange=cross_state,
            data_quality=data_quality,
            portfolio=portfolio_state,
            strategy=strategy_value,
            emit_reason=None,
        )

    def detect_regime_change(self, prior: MarketContext | None, current: MarketContext) -> bool:
        # A meaningful transition is a regime label change or a validity flip.
        if prior is None:
            return True
        if prior.valid != current.valid:
            return True
        if prior.regime is None or current.regime is None:
            return prior.regime != current.regime
        return prior.regime.regime != current.regime.regime

    def should_emit(
        self,
        prior: MarketContext | None,
        current: MarketContext,
        last_emit_ms: int | None,
    ) -> tuple[bool, str | None]:
        # Controlled cadence plus immediate emit on important transitions.
        if self.detect_regime_change(prior, current):
            if prior is None:
                return True, "INITIAL"
            if prior.valid != current.valid:
                return True, "VALIDITY_CHANGE"
            return True, "REGIME_CHANGE"
        if last_emit_ms is None:
            return True, "INITIAL"
        if current.timestamp_ms - int(last_emit_ms) >= self.emit_interval_ms:
            return True, "INTERVAL"
        return False, None

    def _build_trend(self, snapshot: Mapping[str, Any]) -> TrendState:
        technical = snapshot.get("technical")
        alignment_state: str | None = None
        confirmed: int | None = None
        multi = snapshot.get("multi_timeframe_alignment")
        if isinstance(multi, Mapping):
            raw_state = multi.get("state")
            if raw_state is not None:
                alignment_state = str(raw_state)
            raw_confirmed = multi.get("confirmed_timeframes")
            try:
                if raw_confirmed is not None:
                    confirmed = int(raw_confirmed)
            except (TypeError, ValueError):
                confirmed = None
        ema_fast: float | None = None
        ema_slow: float | None = None
        rsi: float | None = None
        atr: float | None = None
        vwap: float | None = None
        bandwidth: float | None = None
        returns: float | None = None
        if isinstance(technical, Mapping):
            # Prefer the 1h frame when present, else first available frame.
            chosen: Mapping[str, Any] | None = None
            if "1h" in technical and isinstance(technical["1h"], Mapping):
                chosen = technical["1h"]
            else:
                for key in technical:
                    value = technical[key]
                    if isinstance(value, Mapping):
                        chosen = value
                        break
            if chosen is not None:
                ema_fast = _safe_optional_float(chosen.get("ema_fast"))
                ema_slow = _safe_optional_float(chosen.get("ema_slow"))
                rsi = _safe_optional_float(chosen.get("rsi"))
                atr = _safe_optional_float(chosen.get("atr"))
                vwap = _safe_optional_float(chosen.get("vwap"))
                bandwidth = _safe_optional_float(chosen.get("bollinger_bandwidth"))
                returns = _safe_optional_float(chosen.get("returns"))
        last_price = _safe_optional_float(snapshot.get("last_price"))
        return TrendState(
            last_price=last_price,
            returns=returns,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            atr=atr,
            vwap=vwap,
            bollinger_bandwidth=bandwidth,
            multi_timeframe_alignment=alignment_state,
            confirmed_timeframes=confirmed,
        )

    def _build_order_flow(self, snapshot: Mapping[str, Any]) -> OrderFlowState:
        return OrderFlowState(
            cvd=_safe_optional_float(snapshot.get("trade_cvd")),
            aggressive_buy_ratio=_safe_optional_float(snapshot.get("aggressive_buy_pct")),
            large_trade_concentration=_safe_optional_float(snapshot.get("large_trade_concentration")),
            top_book_imbalance=_safe_optional_float(snapshot.get("top_book_imbalance")),
            depth_imbalance=_safe_optional_float(snapshot.get("depth_imbalance")),
            trade_volume=_safe_optional_float(snapshot.get("trade_volume")),
        )

    def _build_derivatives(self, snapshot: Mapping[str, Any]) -> DerivativesState:
        # Derivatives arrive via REST analytics payloads embedded in market events;
        # the feature snapshot carries technical/order-flow only, so this section
        # stays unavailable until a derivatives snapshot is passed through.
        funding = _safe_optional_float(snapshot.get("funding_rate"))
        open_interest = _safe_optional_float(snapshot.get("open_interest"))
        basis = _safe_optional_float(snapshot.get("basis"))
        basis_rate = _safe_optional_float(snapshot.get("basis_rate_bps"))
        available = False
        if funding is not None or open_interest is not None or basis is not None:
            available = True
        positioning: str | None = None
        if available:
            if funding is not None and funding > 0.0005:
                positioning = "LONG_CROWDED"
            elif funding is not None and funding < -0.0005:
                positioning = "SHORT_CROWDED"
            else:
                positioning = "NEUTRAL"
        return DerivativesState(
            funding_rate=funding,
            open_interest=open_interest,
            basis=basis,
            basis_rate_bps=basis_rate,
            positioning_state=positioning,
            liquidation_flag=False,
            available=available,
        )

    def _build_options(self, snapshot: Mapping[str, Any]) -> OptionsState:
        # Options data is optional; report availability explicitly when deferred.
        iv = _safe_optional_float(snapshot.get("implied_volatility"))
        delta = _safe_optional_float(snapshot.get("delta"))
        theta = _safe_optional_float(snapshot.get("theta"))
        gamma = _safe_optional_float(snapshot.get("gamma"))
        vega = _safe_optional_float(snapshot.get("vega"))
        available = False
        if iv is not None or delta is not None or gamma is not None or vega is not None:
            available = True
        return OptionsState(
            implied_volatility=iv,
            delta=delta,
            theta=theta,
            gamma=gamma,
            vega=vega,
            positioning_state=None,
            available=available,
        )

    def _build_liquidity(self, snapshot: Mapping[str, Any]) -> LiquidityState:
        spread = _safe_optional_float(snapshot.get("spread_bps"))
        spread_state: str | None = None
        if spread is None:
            spread_state = "UNKNOWN"
        elif spread <= 5.0:
            spread_state = "TIGHT"
        elif spread <= 20.0:
            spread_state = "NORMAL"
        else:
            spread_state = "WIDE"
        depth_25_bid: float | None = None
        depth_25_ask: float | None = None
        bands = snapshot.get("depth_within_bps")
        if isinstance(bands, Mapping):
            band_25 = bands.get(25)
            if band_25 is None:
                band_25 = bands.get("25")
            if isinstance(band_25, Mapping):
                depth_25_bid = _safe_optional_float(band_25.get("bid_qty"))
                depth_25_ask = _safe_optional_float(band_25.get("ask_qty"))
        impact: float | None = None
        exec_status: str | None = None
        quality = snapshot.get("execution_quality")
        if isinstance(quality, Mapping):
            buy_leg = quality.get("BUY")
            if isinstance(buy_leg, Mapping):
                impact = _safe_optional_float(buy_leg.get("price_impact_rate"))
                raw_status = buy_leg.get("status")
                if raw_status is not None:
                    exec_status = str(raw_status)
        return LiquidityState(
            spread_bps=spread,
            spread_state=spread_state,
            bid_depth=_safe_optional_float(snapshot.get("bid_depth")),
            ask_depth=_safe_optional_float(snapshot.get("ask_depth")),
            depth_within_25bps_bid=depth_25_bid,
            depth_within_25bps_ask=depth_25_ask,
            execution_impact_bps=(impact * 10000.0) if impact is not None else None,
            execution_status=exec_status,
        )

    def _build_cross_exchange(self, value: Mapping[str, Any] | None) -> CrossExchangeState:
        if value is None:
            return CrossExchangeState(
                status="UNAVAILABLE",
                reference_price=None,
                disagreement_bps=None,
                source_count=0,
                available=False,
            )
        status = str(value.get("confirmation_status", value.get("status", "UNAVAILABLE")))
        return CrossExchangeState(
            status=status,
            reference_price=_safe_optional_float(value.get("reference_price")),
            disagreement_bps=_safe_optional_float(value.get("disagreement_bps")),
            source_count=_safe_int(value.get("source_count"), 0),
            available=True,
        )

    def _build_regime(
        self,
        trend: TrendState,
        breadth: Mapping[str, Any] | None,
        snapshot: Mapping[str, Any],
        prior: MarketContext | None,
    ) -> RegimeState:
        # Deterministic rule set: EMA structure decides trend/range,
        # bandwidth decides volatility, breadth decides breadth/risk legs.
        alignment = trend.multi_timeframe_alignment
        regime = "RANGE"
        if alignment == "BULLISH":
            if trend.ema_fast is not None and trend.ema_slow is not None:
                if trend.ema_fast > trend.ema_slow:
                    regime = "TREND_UP"
        elif alignment == "BEARISH":
            if trend.ema_fast is not None and trend.ema_slow is not None:
                if trend.ema_fast < trend.ema_slow:
                    regime = "TREND_DOWN"
        volatility = "UNKNOWN"
        bandwidth = trend.bollinger_bandwidth
        if bandwidth is not None:
            if bandwidth > 0.08:
                volatility = "HIGH"
            elif bandwidth > 0.03:
                volatility = "NORMAL"
            else:
                volatility = "LOW"
        elif trend.atr is not None and trend.last_price:
            ratio = trend.atr / trend.last_price if trend.last_price else None
            if ratio is not None:
                if ratio > 0.01:
                    volatility = "HIGH"
                elif ratio > 0.003:
                    volatility = "NORMAL"
                else:
                    volatility = "LOW"
        breadth_state = "UNKNOWN"
        if isinstance(breadth, Mapping):
            advancing = breadth.get("advancing_pct")
            try:
                pct = float(advancing) if advancing is not None else None
            except (TypeError, ValueError):
                pct = None
            if pct is not None:
                if pct >= 0.6:
                    breadth_state = "BULL_BREADTH"
                elif pct <= 0.4:
                    breadth_state = "BEAR_BREADTH"
                else:
                    breadth_state = "MIXED_BREADTH"
        risk_state = "NEUTRAL"
        if volatility == "HIGH" and breadth_state == "BEAR_BREADTH":
            risk_state = "RISK_OFF"
        elif volatility == "LOW" and breadth_state == "BULL_BREADTH":
            risk_state = "RISK_ON"
        changed = False
        if prior is not None and prior.regime is not None:
            if prior.regime.regime != regime:
                changed = True
        elif prior is None:
            changed = False
        _ = snapshot
        return RegimeState(
            regime=regime,
            volatility_state=volatility,
            breadth_state=breadth_state,
            risk_state=risk_state,
            alignment_state=alignment if alignment is not None else "UNKNOWN",
            changed_since_prior=changed,
        )


def _safe_optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_event_time_ms(event_time: Any) -> int | None:
    # Feature snapshots carry ISO event_time; convert back to ms when needed.
    if event_time is None:
        return None
    if isinstance(event_time, (int, float)) and not isinstance(event_time, bool):
        return int(event_time)
    if isinstance(event_time, str):
        try:
            moment = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return int(moment.timestamp() * 1000)
        except ValueError:
            return None
    return None
