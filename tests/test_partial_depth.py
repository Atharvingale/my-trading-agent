from binance_data_layer.collector import normalize_event


def test_normalize_partial_depth_payload():
    event = normalize_event(
        "btcusdt@depth20@100ms",
        {
            "lastUpdateId": 123,
            "bids": [["100.0", "2.0"]],
            "asks": [["100.1", "3.0"]],
        },
    )

    assert event["event_type"] == "depthUpdate"
    assert event["symbol"] == "BTCUSDT"
    assert event["payload"]["final_update_id"] == 123
    assert event["payload"]["bids"] == [(100.0, 2.0)]
    assert event["payload"]["asks"] == [(100.1, 3.0)]
