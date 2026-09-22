from binance_data_layer.breadth import rank_trending_symbols


def test_dynamic_selector_rejects_non_exchange_symbol_names():
    selected = rank_trending_symbols(
        [{"symbol": "龙虾USDT", "change_pct": 99, "quote_volume": 999999999}],
        pinned=(), top_n=5, min_quote_volume=1,
    )
    assert selected == ()
