# Binance data layer

This service collects public Binance spot, futures, and options market data into SQLite. It does not place orders. Private account collection is optional and is enabled only when both `BINANCE_API_KEY` and `BINANCE_API_SECRET` are provided.

## Run

```text
python main.py
```

Default symbols are `BTCUSDT,ETHUSDT`. Set more symbols before starting:

```bash
export BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
python main.py
```

For Windows Command Prompt, use `set BINANCE_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT` instead.

The database defaults to `data/market_data.sqlite3`; override it with `MARKET_DATA_DB`.

## Collected from Binance

- Spot aggregate trades: executed price, quantity, and aggressor side
- Spot best bid/ask: spread and top-of-book liquidity
- Spot depth stream: order-book depth and imbalance inputs
- Spot candles: 1m, 5m, 15m, 1h, and 4h
- Spot 24-hour ticker: price change, volume, high/low, and trade count
- Spot exchange metadata: active symbols and trading filters
- USD-M futures mark price: mark/index price and funding rate
- USD-M futures liquidation stream: forced-order events
- USD-M futures open interest and open-interest history
- USD-M futures funding-rate history
- USD-M futures global long/short account ratio
- USD-M futures taker buy/sell volume ratio
- USD-M futures basis and basis rate
- USD-M futures candles and 24-hour ticker data
- Binance options mark price, bid/ask IV, mark IV, and Greeks
- Binance options open interest by underlying and expiration
- Binance options recent block trades
- REST bootstrap and periodic analytics snapshots
- SQLite event, feature, and data-health records

The analytics collector runs every five minutes and stores its records in `market_events`. The high-frequency spot/futures streams remain continuous. Options open interest is queried by valid underlying base asset and expiration discovered from Binance option-mark symbols.

## Optional private Binance data

Set both variables before starting the service:

```text
set BINANCE_API_KEY=your_key_here
set BINANCE_API_SECRET=your_secret_here
python main.py
```

When both are present, the service fetches and stores:

- Spot account balances
- Spot open orders
- USD-M futures wallet/account state
- USD-M futures positions
- Futures open orders
- Spot and futures user-data stream events such as account updates, order updates, and execution reports
- Periodic reconciliation snapshots

When either variable is missing, no authenticated Binance request or private WebSocket connection is attempted. The database receives an explicit record with:

```json
{"status":"N/A","reason":"BINANCE_API_CREDENTIALS_NOT_PROVIDED"}
```

The private layer is read-only in this implementation. It does not place, cancel, or modify orders. Do not commit API credentials to source control. Use Binance API keys with withdrawals disabled and the narrowest permissions possible.

## Not provided by Binance's exchange API

Binance does not provide macroeconomic releases, general news, X/Twitter or Reddit sentiment, blockchain-wide on-chain activity, token-unlock calendars, wallet identity/concentration analytics, BTC dominance, or total crypto-market capitalization. These require separate provider adapters.


