from binance_data_layer.collector import normalize_event


def test_normalize_depth_update_without_symbol_field():
    event = normalize_event(
        "ethusdt@depth20@100ms",
        {
            "e": "depthUpdate",
            "E": 1700000000000,
            "U": 1,
            "u": 2,
            "b": [["100.0", "2.0"]],
            "a": [["100.1", "3.0"]],
        },
    )

    assert event["event_type"] == "depthUpdate"
    assert event["symbol"] == "ETHUSDT"
    assert event["payload"]["bids"] == [(100.0, 2.0)]
