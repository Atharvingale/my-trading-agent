"""Configuration for the Binance public market-data collector."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    spot_rest_url: str = "https://api.binance.com"
    spot_ws_url: str = "wss://stream.binance.com:9443/stream"
    futures_rest_url: str = "https://fapi.binance.com"
    futures_ws_url: str = "wss://fstream.binance.com/market/stream"
    options_rest_url: str = "https://eapi.binance.com"
    api_key: str | None = None
    api_secret: str | None = None
    database_path: str = "data/market_data.sqlite3"
    symbols: tuple[str, ...] = field(default_factory=lambda: ("BTCUSDT", "ETHUSDT"))
    depth_levels: int = 20
    trade_buffer_size: int = 500
    snapshot_interval_seconds: float = 5.0
    stale_after_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> "Settings":
        symbols = tuple(
            item.strip().upper()
            for item in os.getenv("BINANCE_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
            if item.strip()
        )
        return cls(
            spot_rest_url=os.getenv("BINANCE_SPOT_REST_URL", cls.spot_rest_url),
            spot_ws_url=os.getenv("BINANCE_SPOT_WS_URL", cls.spot_ws_url),
            futures_rest_url=os.getenv("BINANCE_FUTURES_REST_URL", cls.futures_rest_url),
            futures_ws_url=os.getenv("BINANCE_FUTURES_WS_URL", cls.futures_ws_url),
            options_rest_url=os.getenv("BINANCE_OPTIONS_REST_URL", cls.options_rest_url),
            api_key=os.getenv("BINANCE_API_KEY") or None,
            api_secret=os.getenv("BINANCE_API_SECRET") or None,
            database_path=os.getenv("MARKET_DATA_DB", cls.database_path),
            symbols=symbols or cls().symbols,
            depth_levels=max(5, int(os.getenv("BINANCE_DEPTH_LEVELS", cls.depth_levels))),
            trade_buffer_size=max(10, int(os.getenv("TRADE_BUFFER_SIZE", cls.trade_buffer_size))),
            snapshot_interval_seconds=max(1.0, float(os.getenv("SNAPSHOT_INTERVAL", cls.snapshot_interval_seconds))),
            stale_after_seconds=max(5.0, float(os.getenv("STALE_AFTER_SECONDS", cls.stale_after_seconds))),
        )
