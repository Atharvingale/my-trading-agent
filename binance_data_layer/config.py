"""Configuration for the Binance public market-data collector."""

from __future__ import annotations

import ipaddress
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
    enable_market_breadth: bool = True
    breadth_quote_assets: tuple[str, ...] = ("USDT", "USDC", "FDUSD")
    breadth_top_n: int = 10
    breadth_exclude_stablecoin_base: bool = True
    enable_cross_exchange: bool = True
    cross_exchange_max_age_seconds: float = 10.0
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_token: str | None = None
    api_tls_certfile: str | None = None
    api_tls_keyfile: str | None = None
    api_allow_insecure_remote: bool = False
    subscriber_queue_size: int = 64
    persist_queue_size: int = 10_000
    persist_batch_size: int = 50
    event_retention_days: int = 7
    feature_retention_days: int = 7
    breadth_retention_days: int = 7
    health_retention_days: int = 7
    maintenance_interval_seconds: float = 3600.0
    dynamic_universe_enabled: bool = True
    dynamic_universe_size: int = 20
    dynamic_min_quote_volume: float = 5_000_000.0
    dynamic_refresh_seconds: float = 300.0
    dynamic_excluded_symbols: tuple[str, ...] = ()
    dynamic_symbol_pattern: str = r"^[A-Z0-9]{5,20}$"

    @classmethod
    def from_environment(cls) -> "Settings":
        symbols = tuple(
            item.strip().upper()
            for item in os.getenv("BINANCE_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
            if item.strip()
        )
        settings = cls(
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
            enable_market_breadth=os.getenv("ENABLE_MARKET_BREADTH", "1").lower() not in {"0", "false", "no"},
            breadth_quote_assets=tuple(item.strip().upper() for item in os.getenv("BREADTH_QUOTE_ASSETS", ",".join(cls.breadth_quote_assets)).split(",") if item.strip()),
            breadth_top_n=max(1, int(os.getenv("BREADTH_TOP_N", cls.breadth_top_n))),
            breadth_exclude_stablecoin_base=os.getenv("BREADTH_EXCLUDE_STABLECOIN_BASE", "1").lower() not in {"0", "false", "no"},
            enable_cross_exchange=os.getenv("ENABLE_CROSS_EXCHANGE", "1").lower() not in {"0", "false", "no"},
            cross_exchange_max_age_seconds=max(1.0, float(os.getenv("CROSS_EXCHANGE_MAX_AGE_SECONDS", cls.cross_exchange_max_age_seconds))),
            api_host=os.getenv("MARKET_DATA_API_HOST", cls.api_host),
            api_port=max(1, int(os.getenv("MARKET_DATA_API_PORT", cls.api_port))),
            api_token=os.getenv("MARKET_DATA_API_TOKEN") or None,
            api_tls_certfile=os.getenv("MARKET_DATA_API_TLS_CERTFILE") or None,
            api_tls_keyfile=os.getenv("MARKET_DATA_API_TLS_KEYFILE") or None,
            api_allow_insecure_remote=os.getenv("MARKET_DATA_API_ALLOW_INSECURE_REMOTE", "0").lower() not in {"0", "false", "no", ""} if os.getenv("MARKET_DATA_API_ALLOW_INSECURE_REMOTE") else False,
            subscriber_queue_size=max(1, int(os.getenv("MARKET_DATA_SUBSCRIBER_QUEUE_SIZE", cls.subscriber_queue_size))),
            persist_queue_size=max(1, int(os.getenv("MARKET_DATA_PERSIST_QUEUE_SIZE", cls.persist_queue_size))),
            persist_batch_size=max(1, int(os.getenv("MARKET_DATA_PERSIST_BATCH_SIZE", cls.persist_batch_size))),
            event_retention_days=max(1, int(os.getenv("MARKET_DATA_EVENT_RETENTION_DAYS", cls.event_retention_days))),
            feature_retention_days=max(1, int(os.getenv("MARKET_DATA_FEATURE_RETENTION_DAYS", cls.feature_retention_days))),
            breadth_retention_days=max(1, int(os.getenv("MARKET_DATA_BREADTH_RETENTION_DAYS", cls.breadth_retention_days))),
            health_retention_days=max(1, int(os.getenv("MARKET_DATA_HEALTH_RETENTION_DAYS", cls.health_retention_days))),
            maintenance_interval_seconds=max(30.0, float(os.getenv("MARKET_DATA_MAINTENANCE_SECONDS", cls.maintenance_interval_seconds))),
            dynamic_universe_enabled=os.getenv("DYNAMIC_UNIVERSE_ENABLED", "1").lower() not in {"0", "false", "no"},
            dynamic_universe_size=max(1, int(os.getenv("DYNAMIC_UNIVERSE_SIZE", cls.dynamic_universe_size))),
            dynamic_min_quote_volume=max(0.0, float(os.getenv("DYNAMIC_MIN_QUOTE_VOLUME", cls.dynamic_min_quote_volume))),
            dynamic_refresh_seconds=max(30.0, float(os.getenv("DYNAMIC_REFRESH_SECONDS", cls.dynamic_refresh_seconds))),
            dynamic_excluded_symbols=tuple(item.strip().upper() for item in os.getenv("DYNAMIC_EXCLUDED_SYMBOLS", "").split(",") if item.strip()),
        )
        settings.validate_bind()
        return settings

    def is_loopback_bind(self) -> bool:
        try:
            return ipaddress.ip_address(self.api_host).is_loopback
        except ValueError:
            return self.api_host in {"localhost", ""}

    def build_ssl_context(self):  # type: ignore[no-untyped-def]
        """Return an SSLContext when TLS cert/key are configured, else None."""
        import ssl

        if not self.api_tls_certfile or not self.api_tls_keyfile:
            return None
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.api_tls_certfile, self.api_tls_keyfile)
        return context

    def validate_bind(self) -> None:
        """Non-loopback binds require an explicit auth token and TLS before they are enabled."""
        if self.is_loopback_bind():
            return
        # Non-loopback / hostname binds are remote-facing.
        if not (self.api_token or "").strip():
            raise ValueError("non-loopback MARKET_DATA_API_HOST requires MARKET_DATA_API_TOKEN auth token")
        has_tls = bool(self.api_tls_certfile and self.api_tls_keyfile)
        if not has_tls and not self.api_allow_insecure_remote:
            raise ValueError(
                "non-loopback MARKET_DATA_API_HOST requires TLS (MARKET_DATA_API_TLS_CERTFILE/KEYFILE) "
                "or explicit MARKET_DATA_API_ALLOW_INSECURE_REMOTE=1"
            )
