"""Binance REST analytics collection (ingestion/analysis responsibility).

Separated from orchestration (collector.py) per Module 2 P1.9: collector owns
WebSocket orchestration, state, and scheduling; this module owns the REST
analytics payload shapes and persistence calls. All functions are read-only
(no orders) and iterate over the authoritative dynamic universe passed in.
"""

from __future__ import annotations

import time
from typing import Any, Mapping


def _number(value: Any) -> float:
    return float(value)


async def collect_binance_analytics(
    store: Any,
    client: Any,
    active_symbols: tuple[str, ...],
    now_ms: int | None = None,
) -> None:
    """Persist exchangeInfo, options marks, per-symbol tickers and futures analytics."""
    observed = int(now_ms if now_ms is not None else time.time() * 1000)

    def persist(
        symbol: str,
        event_type: str,
        payload: Any,
        event_time_ms: int | None = None,
        stream: str = "rest",
    ) -> None:
        event_payload = payload if isinstance(payload, dict) else {"items": payload}
        store.save_event(
            stream=stream,
            symbol=symbol,
            event_type=event_type,
            event_time_ms=int(event_time_ms or observed),
            received_time_ms=observed,
            payload=event_payload,
        )

    persist("", "exchangeInfo", await client.exchange_info(), stream="rest:/api/v3/exchangeInfo")
    option_marks = await client.options_mark_price()
    persist("", "optionMarkPrice", option_marks, stream="rest:/eapi/v1/mark")
    for symbol in active_symbols:
        ticker = await client.spot_24hr_ticker(symbol)
        persist(symbol, "spot24hrTicker", ticker, stream="rest:/api/v3/ticker/24hr")
        for method, event_type in (
            (client.futures_long_short_account_ratio, "futuresLongShortRatio"),
            (client.futures_taker_volume, "futuresTakerVolume"),
            (client.futures_open_interest_history, "futuresOpenInterestHistory"),
            (client.futures_funding_history, "futuresFundingRate"),
        ):
            items = await method(symbol)
            persist(symbol, event_type, items, stream=f"rest:{event_type}")
        basis = await client.futures_basis(symbol)
        persist(symbol, "futuresBasis", basis, stream="rest:/futures/data/basis")

    option_bases = sorted(
        {
            str(item["symbol"]).split("-")[0]
            for item in (option_marks if isinstance(option_marks, list) else [])
            if isinstance(item, dict) and "symbol" in item and len(str(item["symbol"]).split("-")) >= 4
        }
    )
    expirations_by_base = {
        base: sorted(
            {
                str(item["symbol"]).split("-")[1]
                for item in (option_marks if isinstance(option_marks, list) else [])
                if isinstance(item, dict)
                and str(item.get("symbol", "")).startswith(f"{base}-")
                and len(str(item["symbol"]).split("-")) >= 4
            }
        )
        for base in option_bases
    }
    for base in option_bases:
        for expiration in expirations_by_base[base]:
            option_oi = await client.options_open_interest(base, expiration)
            persist(
                base,
                "optionOpenInterest",
                {"expiration": expiration, "items": option_oi},
                stream="rest:/eapi/v1/openInterest",
            )
        option_blocks = await client.options_block_trades()
        persist(base, "optionBlockTrade", option_blocks, stream="rest:/eapi/v1/blockTrades")


async def collect_futures_metrics(
    store: Any,
    save_normalized: Any,
    client: Any,
    active_symbols: tuple[str, ...],
) -> None:
    """Persist mark-price and open-interest snapshots for the active universe."""
    from .ingestion import normalize_event as ingest_normalize

    for symbol in active_symbols:
        mark = await client.futures_mark_price(symbol)
        if isinstance(mark, dict):
            event = ingest_normalize(
                "rest:/fapi/v1/premiumIndex",
                {
                    "e": "markPriceUpdate",
                    "E": int(mark.get("time", time.time() * 1000)),
                    "s": mark["symbol"],
                    "p": mark["markPrice"],
                    "i": mark["indexPrice"],
                    "r": mark["lastFundingRate"],
                    "T": mark["nextFundingTime"],
                },
            )
            save_normalized(event)
        interest = await client.futures_open_interest(symbol)
        store.save_event(
            stream="rest:/fapi/v1/openInterest",
            symbol=symbol,
            event_type="openInterest",
            event_time_ms=int(interest.get("time", time.time() * 1000)),
            received_time_ms=int(time.time() * 1000),
            payload={"open_interest": _number(interest["openInterest"])},
        )


async def collect_private_account(
    store: Any,
    client: Any,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Persist private account snapshots; caller guarantees credentials exist."""
    observed = int(now_ms if now_ms is not None else time.time() * 1000)
    records = (
        ("privateSpotAccount", "", client.spot_account),
        ("privateSpotOpenOrders", "", client.spot_open_orders),
        ("privateFuturesAccount", "", client.futures_account),
        ("privateFuturesOpenOrders", "", client.futures_open_orders),
    )
    for event_type, symbol, method in records:
        payload = await method()
        store.save_event(
            stream="private:binance",
            symbol=symbol,
            event_type=event_type,
            event_time_ms=observed,
            received_time_ms=int(time.time() * 1000),
            payload=payload if isinstance(payload, dict) else {"items": payload},
        )
    return {"status": "ok"}


def build_depth_snapshot_payload(depth: Mapping[str, Any]) -> Mapping[str, Any]:
    return dict(depth)
