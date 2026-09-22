from datetime import datetime, timezone

from binance_data_layer.collector import MarketState, normalize_event


def test_normalize_trade_event():
    event = normalize_event(
        "btcusdt@aggTrade",
        {
            "e": "aggTrade",
            "E": 1700000000123,
            "s": "BTCUSDT",
            "a": 123,
            "p": "100.5",
            "q": "2.0",
            "f": 1,
            "l": 2,
            "T": 1700000000000,
            "m": False,
        },
    )
    assert event["event_type"] == "aggTrade"
    assert event["symbol"] == "BTCUSDT"
    assert event["payload"]["price"] == 100.5
    assert event["payload"]["qty"] == 2.0
    assert event["payload"]["is_buyer_maker"] is False


def test_market_state_updates_book_and_trade():
    state = MarketState("BTCUSDT", trade_buffer_size=10)
    state.apply_trade({"price": 100.0, "qty": 2.0, "is_buyer_maker": False})
    state.apply_book_ticker({"bid_price": 99.9, "bid_qty": 3.0, "ask_price": 100.1, "ask_qty": 4.0})
    state.apply_depth({"bids": [[99.9, 3.0], [99.8, 2.0]], "asks": [[100.1, 4.0]]})

    assert state.last_price == 100.0
    assert state.bid_price == 99.9
    assert state.ask_price == 100.1
    assert state.recent_trades[0]["qty"] == 2.0
    assert state.bids == [(99.9, 3.0), (99.8, 2.0)]


def test_normalize_mark_price_event():
    event = normalize_event(
        "btcusdt@markPrice@1s",
        {
            "e": "markPriceUpdate",
            "E": 1700000000123,
            "s": "BTCUSDT",
            "p": "100.0",
            "i": "99.8",
            "r": "0.0001",
            "T": 1700003600000,
        },
    )
    assert event["event_type"] == "markPriceUpdate"
    assert event["payload"]["mark_price"] == 100.0
    assert event["payload"]["funding_rate"] == 0.0001
