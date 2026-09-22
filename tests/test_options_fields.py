from binance_data_layer.collector import normalize_event


def test_options_mark_price_preserves_mark_iv_and_risk_free_rate():
    event = normalize_event(
        "btc-option@markPrice",
        {
            "e": "markPrice",
            "E": 1700000000000,
            "s": "BTC-260925-100000-C",
            "mp": "1200",
            "b": "0.70",
            "a": "0.80",
            "vo": "0.75",
            "rf": "0.05",
            "bo": "1100",
            "ao": "1300",
            "i": "100000",
            "d": "0.5",
            "t": "-20",
            "g": "0.001",
            "v": "100",
        },
    )

    assert event["payload"]["mark_iv"] == 0.75
    assert event["payload"]["risk_free_interest"] == 0.05
