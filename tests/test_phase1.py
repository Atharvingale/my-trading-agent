from datetime import datetime, timezone

from binance_data_layer.breadth import calculate_breadth, normalize_ticker_array
from binance_data_layer.execution import estimate_execution
from binance_data_layer.quality import DataQuality, quality_gate
from binance_data_layer.technical import Candle, calculate_indicators, multi_timeframe_alignment
from binance_data_layer.cross_exchange import normalize_coinbase_ticker, normalize_kraken_ticker, normalize_okx_ticker


def test_normalize_ticker_array_accepts_binance_combined_envelope():
    payload = {"stream": "!ticker@arr", "data": [{"s": "BTCUSDT", "c": "101", "o": "100", "v": "10", "q": "1000"}]}
    rows = normalize_ticker_array(payload, quote_assets={"USDT"})
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["price"] == 101.0
    assert rows[0]["open"] == 100.0
    assert rows[0]["quote_volume"] == 1000.0


def test_breadth_counts_and_concentration():
    rows = [
        {"symbol": "BTCUSDT", "price": 101, "open": 100, "quote_volume": 900},
        {"symbol": "ETHUSDT", "price": 99, "open": 100, "quote_volume": 100},
        {"symbol": "SOLUSDT", "price": 100, "open": 100, "quote_volume": 50},
    ]
    result = calculate_breadth(rows, top_n=2)
    assert result["eligible_count"] == 3
    assert result["advancing_count"] == 1
    assert result["declining_count"] == 1
    assert result["unchanged_count"] == 1
    assert result["advance_decline_ratio"] == 1.0
    assert result["aggregate_quote_volume"] == 1050.0
    assert abs(result["top_volume_concentration"] - (1000 / 1050)) < 1e-10


def test_technical_indicators_require_warmup_and_ignore_open_candle():
    candles = [Candle(i * 60_000, 100 + i, 101 + i, 99 + i, 100 + i, 10, True) for i in range(30)]
    candles.append(Candle(30 * 60_000, 130, 131, 129, 130, 10, False))
    result = calculate_indicators(candles, period=14)
    assert result["closed_candle_count"] == 30
    assert result["ema"] is not None
    assert result["rsi"] is not None
    assert result["atr"] is not None
    assert result["returns"] is not None
    assert calculate_indicators(candles[:5], period=14)["ema"] is None


def test_multi_timeframe_alignment_is_deterministic():
    data = {"1h": {"ema_fast": 110, "ema_slow": 100}, "4h": {"ema_fast": 105, "ema_slow": 100}}
    assert multi_timeframe_alignment(data) == {"state": "BULLISH", "confirmed_timeframes": 2}


def test_execution_estimate_returns_slippage_and_depth_bands():
    result = estimate_execution(
        side="BUY", quantity=3, bids=[(99, 10)], asks=[(101, 1), (102, 2), (105, 10)], fee_rate=0.001
    )
    assert result["status"] == "OK"
    assert result["filled_quantity"] == 3
    assert result["depth_within_bps"][5] == 1.0
    assert result["round_trip_cost_rate"] > 0


def test_quality_gate_fails_closed():
    quality = DataQuality(status="BAD", reasons=("STALE",))
    assert quality_gate(quality) == {"decision": "HOLD", "tradable": False, "reasons": ["STALE"]}


def test_cross_exchange_public_payload_normalizers():
    coinbase = normalize_coinbase_ticker({"product_id": "BTC-USD", "price": "100", "best_bid": "99", "best_ask": "101"})
    kraken = normalize_kraken_ticker(["ticker", {"a": ["101"], "b": ["99"], "c": ["100"], "v": ["5", "6"]}, "req"])
    okx = normalize_okx_ticker({"arg": {"channel": "tickers"}, "data": [{"instId": "BTC-USDT", "bidPx": "99", "askPx": "101", "last": "100", "vol24h": "5"}]})
    assert coinbase["mid_price"] == kraken["mid_price"] == okx["mid_price"] == 100.0
