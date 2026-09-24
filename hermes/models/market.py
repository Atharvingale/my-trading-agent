"""Decision-ready MarketContext contract for Hermes (Module 3).

Deterministic and statistical only. No LLM calls, no trading calls.
Every field is derived from the hardened market-data service, plus
explicitly-passed portfolio and strategy state snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RegimeState:
    regime: str
    volatility_state: str
    breadth_state: str
    risk_state: str
    alignment_state: str
    changed_since_prior: bool = False


@dataclass(frozen=True)
class TrendState:
    last_price: float | None
    returns: float | None
    ema_fast: float | None
    ema_slow: float | None
    rsi: float | None
    atr: float | None
    vwap: float | None
    bollinger_bandwidth: float | None
    multi_timeframe_alignment: str | None
    confirmed_timeframes: int | None


@dataclass(frozen=True)
class OrderFlowState:
    cvd: float | None
    aggressive_buy_ratio: float | None
    large_trade_concentration: float | None
    top_book_imbalance: float | None
    depth_imbalance: float | None
    trade_volume: float | None


@dataclass(frozen=True)
class DerivativesState:
    funding_rate: float | None
    open_interest: float | None
    basis: float | None
    basis_rate_bps: float | None
    positioning_state: str | None
    liquidation_flag: bool = False
    available: bool = False


@dataclass(frozen=True)
class OptionsState:
    implied_volatility: float | None = None
    delta: float | None = None
    theta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    positioning_state: str | None = None
    available: bool = False


@dataclass(frozen=True)
class LiquidityState:
    spread_bps: float | None
    spread_state: str | None
    bid_depth: float | None
    ask_depth: float | None
    depth_within_25bps_bid: float | None
    depth_within_25bps_ask: float | None
    execution_impact_bps: float | None
    execution_status: str | None


@dataclass(frozen=True)
class CrossExchangeState:
    status: str
    reference_price: float | None
    disagreement_bps: float | None
    source_count: int
    available: bool = False


@dataclass(frozen=True)
class DataQualityState:
    freshness: str
    age_seconds: float | None
    missing_fields: tuple[str, ...] = ()
    sequence_status: str = "UNKNOWN"
    rest_ws_health: str = "UNKNOWN"


@dataclass(frozen=True)
class PortfolioState:
    position_qty: float = 0.0
    exposure_notional: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    win_streak: int = 0
    loss_streak: int = 0
    cooldown_active: bool = False
    available: bool = False


@dataclass(frozen=True)
class StrategyState:
    production_versions: tuple[str, ...] = ()
    disabled_strategies: tuple[str, ...] = ()
    degraded_strategies: tuple[str, ...] = ()
    available: bool = False


@dataclass(frozen=True)
class MarketContext:
    symbol: str
    timestamp_ms: int
    valid: bool
    invalid_reasons: tuple[str, ...] = ()
    regime: RegimeState | None = None
    trend: TrendState | None = None
    order_flow: OrderFlowState | None = None
    derivatives: DerivativesState | None = None
    options: OptionsState | None = None
    liquidity: LiquidityState | None = None
    cross_exchange: CrossExchangeState | None = None
    data_quality: DataQualityState | None = None
    portfolio: PortfolioState = field(default_factory=PortfolioState)
    strategy: StrategyState = field(default_factory=StrategyState)
    emit_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # Plain-dict view for logging and for Module 5 consumers.
        # Built with explicit steps so the mapping stays auditable.
        result: dict[str, Any] = {}
        result["symbol"] = self.symbol
        result["timestamp_ms"] = self.timestamp_ms
        result["valid"] = self.valid
        reasons: list[str] = []
        for reason in self.invalid_reasons:
            reasons.append(reason)
        result["invalid_reasons"] = reasons
        result["emit_reason"] = self.emit_reason
        sections: dict[str, Any] = {}
        mapping: dict[str, Any] = {}
        mapping["regime"] = self.regime
        mapping["trend"] = self.trend
        mapping["order_flow"] = self.order_flow
        mapping["derivatives"] = self.derivatives
        mapping["options"] = self.options
        mapping["liquidity"] = self.liquidity
        mapping["cross_exchange"] = self.cross_exchange
        mapping["data_quality"] = self.data_quality
        mapping["portfolio"] = self.portfolio
        mapping["strategy"] = self.strategy
        for name in mapping:
            value = mapping[name]
            if value is None:
                sections[name] = None
            elif hasattr(value, "__dict__") or hasattr(value, "__dataclass_fields__"):
                item: dict[str, Any] = {}
                for attr in value.__dataclass_fields__:
                    item[attr] = getattr(value, attr)
                sections[name] = item
            else:
                sections[name] = value
        result["sections"] = sections
        return result


def empty_portfolio() -> PortfolioState:
    # Default when portfolio state is not wired yet (Module 8).
    return PortfolioState()


def empty_strategy_state() -> StrategyState:
    # Default when strategy registry state is not wired yet (Module 4).
    return StrategyState()


def coerce_portfolio(value: Mapping[str, Any] | None) -> PortfolioState:
    # Accept a plain mapping from a future portfolio module; fall back safely.
    if value is None:
        return empty_portfolio()
    if isinstance(value, PortfolioState):
        return value
    qty = _safe_float(value.get("position_qty"), 0.0)
    exposure = _safe_float(value.get("exposure_notional"), 0.0)
    unrealized = _safe_float(value.get("unrealized_pnl"), 0.0)
    realized = _safe_float(value.get("realized_pnl"), 0.0)
    win_streak = _safe_int(value.get("win_streak"), 0)
    loss_streak = _safe_int(value.get("loss_streak"), 0)
    cooldown = bool(value.get("cooldown_active", False))
    return PortfolioState(
        position_qty=qty,
        exposure_notional=exposure,
        unrealized_pnl=unrealized,
        realized_pnl=realized,
        win_streak=win_streak,
        loss_streak=loss_streak,
        cooldown_active=cooldown,
        available=True,
    )


def coerce_strategy_state(value: Mapping[str, Any] | None) -> StrategyState:
    # Accept a plain mapping from a future strategy module; fall back safely.
    if value is None:
        return empty_strategy_state()
    if isinstance(value, StrategyState):
        return value
    versions: tuple[str, ...] = ()
    raw_versions = value.get("production_versions", ())
    if isinstance(raw_versions, (list, tuple)):
        collected: list[str] = []
        for item in raw_versions:
            collected.append(str(item))
        versions = tuple(collected)
    disabled: tuple[str, ...] = ()
    raw_disabled = value.get("disabled_strategies", ())
    if isinstance(raw_disabled, (list, tuple)):
        collected_disabled: list[str] = []
        for item in raw_disabled:
            collected_disabled.append(str(item))
        disabled = tuple(collected_disabled)
    degraded: tuple[str, ...] = ()
    raw_degraded = value.get("degraded_strategies", ())
    if isinstance(raw_degraded, (list, tuple)):
        collected_degraded: list[str] = []
        for item in raw_degraded:
            collected_degraded.append(str(item))
        degraded = tuple(collected_degraded)
    return StrategyState(
        production_versions=versions,
        disabled_strategies=disabled,
        degraded_strategies=degraded,
        available=True,
    )


def _safe_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default
