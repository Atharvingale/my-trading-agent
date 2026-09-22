from binance_data_layer.collector import normalize_event


def test_normalize_book_ticker_without_event_field():
    event = normalize_event(
        "btcusdt@bookTicker",
        {
            "u": 123,
            "s": "BTCUSDT",
            "b": "100.0",
            "B": "2.0",
            "a": "100.1",
            "A": "3.0",
        },
    )

    assert event["event_type"] == "bookTicker"
    assert event["symbol"] == "BTCUSDT"
    assert event["payload"]["bid_price"] == 100.0
