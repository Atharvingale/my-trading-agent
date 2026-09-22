# Binance data layer

This service collects public Binance spot, futures, and options market data into SQLite. It does not place orders. Private account collection is optional and is enabled only when both `BINANCE_API_KEY` and `BINANCE_API_SECRET` are provided.

- `python main.py` starts the collector and local read-only API

This document is the maintained record of the original goals, completed work, deviations, and remaining work:

- `PROJECT_PLAN_AND_STATUS.md`

## Local realtime API

The collector exposes a local read-only API on `127.0.0.1:8000` by default. Configure `MARKET_DATA_API_HOST` and `MARKET_DATA_API_PORT` if needed.

REST endpoints:

- `GET /health`
- `GET /market/{symbol}/snapshot`
- `GET /market/{symbol}/features`
- `GET /market/top-coins`
- `GET /breadth/latest`
- `GET /cross-exchange/{symbol}`
- `GET /data-health`
- `GET /events?symbol=BTCUSDT&limit=100`

Realtime WebSocket:

```text
ws://127.0.0.1:8000/ws?symbol=BTCUSDT
```

Omit `symbol` to receive all symbols and derived updates. The WebSocket sends `market_event`, `breadth`, and `cross_exchange_confirmation` messages as the collector receives them. This is push-based; consumers do not need to poll for realtime updates.

The dynamic universe is refreshed from Binance's official all-market mini-ticker stream. It keeps configured symbols pinned, then ranks additional symbols by absolute 24-hour price change and quote volume, subject to a minimum liquidity threshold and exclusions. It is a candidate-discovery mechanism, not a profit guarantee; downstream quality, execution, and risk checks remain required.

The API is read-only and does not expose order placement, cancellation, account mutation, or withdrawal operations.

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
- Binance all-market spot breadth via the official `!miniTicker@arr` stream
- Binance all-market USD-M futures breadth via the official `!miniTicker@arr` stream
- Breadth snapshots: advancing/declining/unchanged counts, advance/decline ratio, advancing percentage, aggregate quote volume, and top-volume concentration
- Closed-candle technical features: returns, EMA, RSI, ATR, VWAP, Bollinger bandwidth, and volume ratio
- Multi-timeframe candle state for 1m, 5m, 15m, 1h, and 4h; unfinished candles are excluded from technical calculations
- Order-flow features: rolling CVD, aggressive-buy percentage, large-trade concentration, and depth within 5/10/25 bps
- Fail-closed quality tracking for duplicate events, out-of-order events, depth sequence gaps, and stale/missing data
- Public cross-exchange BTC/ETH ticker streams from Coinbase Advanced Trade, Kraken Spot WebSocket v2, and OKX public WebSocket
- Cross-exchange reference price, disagreement in basis points, source count, and confirmation status

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


