"""Deterministic closed-candle technical indicators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    closed: bool = True


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for item in values[period:]:
        value = alpha * item + (1 - alpha) * value
    return value


def calculate_indicators(candles: Sequence[Candle], *, period: int = 14) -> dict[str, Any]:
    closed = [c for c in candles if c.closed]
    result: dict[str, Any] = {"closed_candle_count": len(closed)}
    closes = [c.close for c in closed]
    result["returns"] = (closes[-1] / closes[-2] - 1) if len(closes) >= 2 and closes[-2] else None
    result["ema"] = _ema(closes, period)
    result["ema_fast"] = _ema(closes, 12)
    result["ema_slow"] = _ema(closes, 26)
    if len(closes) >= period + 1:
        gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        result["rsi"] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        trs = [max(c.high - c.low, abs(c.high - closed[i - 1].close), abs(c.low - closed[i - 1].close)) for i, c in enumerate(closed[1:], 1)]
        result["atr"] = sum(trs[-period:]) / period if len(trs) >= period else None
    else:
        result["rsi"] = None
        result["atr"] = None
    if len(closes) >= 20:
        window = closes[-20:]
        mean = sum(window) / 20
        variance = sum((x - mean) ** 2 for x in window) / 20
        std = variance ** 0.5
        result["bollinger_bandwidth"] = (4 * std / mean) if mean else None
    else:
        result["bollinger_bandwidth"] = None
    if len(closed) >= period:
        selected = closed[-period:]
        volume = sum(c.volume for c in selected)
        result["vwap"] = sum(((c.high + c.low + c.close) / 3) * c.volume for c in selected) / volume if volume else None
        prior = closed[-period * 2:-period]
        prior_volume = sum(c.volume for c in prior)
        result["volume_ratio"] = volume / prior_volume if prior_volume else None
    else:
        result["vwap"] = None
        result["volume_ratio"] = None
    return result


def multi_timeframe_alignment(frames: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    usable = [frame for frame in frames.values() if frame.get("ema_fast") is not None and frame.get("ema_slow") is not None]
    bullish = sum(frame["ema_fast"] > frame["ema_slow"] for frame in usable)
    bearish = sum(frame["ema_fast"] < frame["ema_slow"] for frame in usable)
    state = "BULLISH" if bullish == len(usable) and usable else "BEARISH" if bearish == len(usable) and usable else "MIXED"
    return {"state": state, "confirmed_timeframes": max(bullish, bearish)}
