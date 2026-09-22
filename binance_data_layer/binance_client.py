"""Async Binance REST client for public and optional private data."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp


class BinancePublicClient:
    def __init__(
        self,
        *,
        spot_base_url: str,
        futures_base_url: str,
        options_base_url: str = "https://eapi.binance.com",
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.spot_base_url = spot_base_url.rstrip("/")
        self.futures_base_url = futures_base_url.rstrip("/")
        self.options_base_url = options_base_url.rstrip("/")
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.api_secret = api_secret.strip() if api_secret and api_secret.strip() else None
        self.time_offset_ms = 0
        self.recv_window_ms = 5000
        self._time_synced = False
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "BinancePublicClient":
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None

    @property
    def credentials_available(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def build_signature(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_secret:
            raise RuntimeError("Binance API secret is not configured")
        query = urlencode(params)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return {**params, "signature": signature}

    async def sync_time(self) -> None:
        local_before = int(time.time() * 1000)
        result = await self._get(self.spot_base_url, "/api/v3/time")
        local_after = int(time.time() * 1000)
        midpoint = (local_before + local_after) // 2
        self.time_offset_ms = int(result["serverTime"]) - midpoint
        self._time_synced = True

    def build_signed_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        signed = dict(params or {})
        signed.setdefault("recvWindow", self.recv_window_ms)
        signed.setdefault("timestamp", int(time.time() * 1000) + self.time_offset_ms)
        return self.build_signature(signed)


    async def _get(
        self,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self.session is None:
            raise RuntimeError("BinancePublicClient must be used as an async context manager")
        async with self.session.get(f"{base_url}{path}", params=params, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

    async def _signed_get(self, base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.credentials_available:
            raise RuntimeError("Binance API credentials are not configured")
        if self.credentials_available and not self._time_synced:
            await self.sync_time()
        signed_params = self.build_signed_params(params)
        return await self._get(base_url, path, signed_params, headers={"X-MBX-APIKEY": self.api_key or ""})

    async def exchange_info(self) -> dict[str, Any]:
        return await self._get(self.spot_base_url, "/api/v3/exchangeInfo")

    async def spot_account(self) -> dict[str, Any]:
        return await self._signed_get(self.spot_base_url, "/api/v3/account")

    async def spot_open_orders(self, symbol: str | None = None) -> Any:
        return await self._signed_get(self.spot_base_url, "/api/v3/openOrders", {"symbol": symbol} if symbol else None)

    async def futures_account(self) -> dict[str, Any]:
        return await self._signed_get(self.futures_base_url, "/fapi/v2/account")

    async def futures_open_orders(self, symbol: str | None = None) -> Any:
        return await self._signed_get(self.futures_base_url, "/fapi/v1/openOrders", {"symbol": symbol} if symbol else None)

    async def _put(
        self,
        base_url: str,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self.session is None:
            raise RuntimeError("BinancePublicClient must be used as an async context manager")
        async with self.session.put(f"{base_url}{path}", params=params, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

    async def spot_user_stream_key(self) -> str:
        if not self.api_key:
            raise RuntimeError("Binance API key is not configured")
        if self.session is None:
            raise RuntimeError("BinancePublicClient must be used as an async context manager")
        async with self.session.post(
            f"{self.spot_base_url}/api/v3/userDataStream",
            headers={"X-MBX-APIKEY": self.api_key},
        ) as response:
            response.raise_for_status()
            return str((await response.json())["listenKey"])

    async def futures_user_stream_key(self) -> str:
        if not self.api_key:
            raise RuntimeError("Binance API key is not configured")
        if self.session is None:
            raise RuntimeError("BinancePublicClient must be used as an async context manager")
        async with self.session.post(
            f"{self.futures_base_url}/fapi/v1/listenKey",
            headers={"X-MBX-APIKEY": self.api_key},
        ) as response:
            response.raise_for_status()
            return str((await response.json())["listenKey"])

    async def spot_user_stream_keepalive(self, listen_key: str) -> Any:
        if not self.api_key:
            raise RuntimeError("Binance API key is not configured")
        return await self._put(
            self.spot_base_url,
            "/api/v3/userDataStream",
            {"listenKey": listen_key},
            headers={"X-MBX-APIKEY": self.api_key},
        )

    async def futures_user_stream_keepalive(self, listen_key: str) -> Any:
        if not self.api_key:
            raise RuntimeError("Binance API key is not configured")
        return await self._put(
            self.futures_base_url,
            "/fapi/v1/listenKey",
            {"listenKey": listen_key},
            headers={"X-MBX-APIKEY": self.api_key},
        )

    async def spot_24hr_ticker(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get(self.spot_base_url, "/api/v3/ticker/24hr", params)

    async def futures_24hr_ticker(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get(self.futures_base_url, "/fapi/v1/ticker/24hr", params)

    async def spot_depth(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return await self._get(self.spot_base_url, "/api/v3/depth", {"symbol": symbol, "limit": limit})

    async def spot_klines(self, symbol: str, interval: str = "1m", limit: int = 500) -> list[list[Any]]:
        return await self._get(self.spot_base_url, "/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    async def futures_mark_price(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get(self.futures_base_url, "/fapi/v1/premiumIndex", params)

    async def futures_open_interest(self, symbol: str) -> dict[str, Any]:
        return await self._get(self.futures_base_url, "/fapi/v1/openInterest", {"symbol": symbol})

    async def futures_funding_history(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self._get(self.futures_base_url, "/fapi/v1/fundingRate", {"symbol": symbol, "limit": limit})

    async def futures_klines(self, symbol: str, interval: str = "1m", limit: int = 500) -> list[list[Any]]:
        return await self._get(self.futures_base_url, "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    async def options_mark_price(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get(self.options_base_url, "/eapi/v1/mark", params)

    async def options_open_interest(self, underlying_asset: str, expiration: str | None = None) -> Any:
        params = {"underlyingAsset": underlying_asset}
        if expiration:
            params["expiration"] = expiration
        return await self._get(self.options_base_url, "/eapi/v1/openInterest", params)

    async def options_block_trades(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get(self.options_base_url, "/eapi/v1/blockTrades", params)

    async def futures_long_short_account_ratio(self, symbol: str, period: str = "5m", limit: int = 100) -> Any:
        return await self._get(
            self.futures_base_url,
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": period, "limit": limit},
        )

    async def futures_taker_volume(self, symbol: str, period: str = "5m", limit: int = 100) -> Any:
        return await self._get(
            self.futures_base_url,
            "/futures/data/takerlongshortRatio",
            {"symbol": symbol, "period": period, "limit": limit},
        )

    async def futures_basis(self, pair: str, contract_type: str = "PERPETUAL", period: str = "5m", limit: int = 100) -> Any:
        return await self._get(
            self.futures_base_url,
            "/futures/data/basis",
            {"pair": pair, "contractType": contract_type, "period": period, "limit": limit},
        )

    async def futures_open_interest_history(self, symbol: str, period: str = "5m", limit: int = 100) -> Any:
        return await self._get(
            self.futures_base_url,
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": period, "limit": limit},
        )
