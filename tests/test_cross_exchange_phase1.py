import asyncio

from binance_data_layer.cross_exchange import (
    build_confirmation,
    coinbase_subscription,
    kraken_subscription,
    normalize_coinbase_ticker,
    normalize_kraken_ticker,
    normalize_okx_ticker,
    okx_subscription,
)


def test_official_public_subscription_payloads():
    assert coinbase_subscription()["channel"] == "ticker"
    assert set(coinbase_subscription()["product_ids"]) == {"BTC-USD", "ETH-USD"}
    assert kraken_subscription()["method"] == "subscribe"
    assert kraken_subscription()["params"]["channel"] == "ticker"
    assert okx_subscription()["op"] == "subscribe"
    assert okx_subscription()["args"][0]["channel"] == "tickers"


def test_official_cross_exchange_ticker_shapes_normalize():
    coinbase = normalize_coinbase_ticker({
        "channel": "ticker", "events": [{"tickers": [{
            "product_id": "BTC-USD", "price": "100", "best_bid": "99", "best_ask": "101", "volume_24_h": "5"
        }]}]
    })
    kraken = normalize_kraken_ticker({
        "channel": "ticker", "data": [{"symbol": "BTC/USD", "bid": 99, "ask": 101, "last": 100, "volume": 5}]
    })
    okx = normalize_okx_ticker({"data": [{"instId": "BTC-USDT", "bidPx": "99", "askPx": "101", "last": "100", "vol24h": "5"}]})
    assert coinbase["mid_price"] == kraken["mid_price"] == okx["mid_price"] == 100.0


def test_cross_exchange_confirmation_requires_fresh_sources():
    snapshots = [
        {"source": "binance", "symbol": "BTCUSDT", "mid_price": 100.0, "received_time_ms": 1000},
        {"source": "coinbase", "symbol": "BTC-USD", "mid_price": 100.01, "received_time_ms": 1000},
        {"source": "kraken", "symbol": "BTC/USD", "mid_price": 99.99, "received_time_ms": 1000},
        {"source": "okx", "symbol": "BTC-USDT", "mid_price": 100.00, "received_time_ms": 1000},
    ]
    result = build_confirmation(snapshots, now_ms=1100, max_age_ms=1000)
    assert result["source_count"] == 4
    assert result["confirmation_status"] == "CONFIRMED"
    stale = build_confirmation(snapshots, now_ms=3000, max_age_ms=1000)
    assert stale["confirmation_status"] == "UNAVAILABLE"
