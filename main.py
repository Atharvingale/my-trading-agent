"""Run the Binance public market-data collector.

Usage:
    python main.py

Environment variables:
    BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
    MARKET_DATA_DB=data/market_data.sqlite3
    BINANCE_DEPTH_LEVELS=20
"""

from binance_data_layer.collector import main


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
