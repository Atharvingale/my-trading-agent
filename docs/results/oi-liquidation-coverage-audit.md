# OI + Liquidation Data Coverage Audit (Cycle 4 pre-work, facts only)

Audit date: 2026-09-27. Method: direct queries over the actual stored data —
`data/market_data.sqlite3` (plus `api_live`, `dynamic_live`, `dynamic_live2`
for union spans; all gitignored local-collector stores) and the versioned
`research/datasets/*.json` artifacts. Nothing estimated, nothing assumed.
No hypothesis is designed here, no holdout is touched or reserved, and no
go/no-go decision is made — that call belongs to the human reviewing this file.

## 1. Symbols with any OI history at all (full list)

Exactly two: **BTCUSDT, ETHUSDT**. Every other symbol in storage has zero
open-interest history rows of any kind. (Options-OI rows exist for
BTC/ETH/BNB/SOL/DOGE/XRP/XAU/XAG — §6 — but that is a different product,
not futures OI.)

## 2. Per-symbol OI history

Two storage forms exist; both are BTCUSDT/ETHUSDT-only:

(a) `futuresOpenInterestHistory` items — true history bars. Each stored row
carries an `items[]` array of 5-minute OI snapshots
(`sumOpenInterest`, `sumOpenInterestValue`, `timestamp`, 300000 ms steps).
Union across all four `data/*.sqlite3` stores, deduplicated:

| Symbol | Start (UTC) | End (UTC) | Span | Interval | Bars | Gaps > 1 interval | Missing vs span |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 2026-09-21 21:10 | 2026-09-22 07:35 | 10.4 h | 5 m | 126 | 0 | 0.0% |
| ETHUSDT | 2026-09-21 21:10 | 2026-09-22 07:35 | 10.4 h | 5 m | 126 | 0 | 0.0% |

(b) `openInterest` snapshots — point-in-time `{"open_interest": X}` readings,
no interval (not bars): 21 × BTCUSDT + 21 × ETHUSDT in `market_data.sqlite3`
(18 + 18 in `api_live`, 3 + 3 in `dynamic_live`, 2 + 2 in `dynamic_live2`),
spanning 2026-09-22 05:30–07:42 UTC (~2.2 h).

OI history for every other symbol: **absent** (0 rows).

## 3. Per-symbol liquidation-event coverage

Source: `forceOrder` rows (Binance futures liquidation-order stream). This is
a **raw per-liquidation event feed** — each row is one liquidation order
(`side`, `order_type`, `price`, `average_price`, `orig_qty`, `executed_qty`,
`trade_time_ms`) — **not** an aggregated or bucketed feed. Union across all
four stores, deduplicated on (symbol, trade_time, side, qty, price):

- Global span (all symbols): **2026-09-22 05:56–07:42 UTC (~1.77 h)**,
  251 raw events in `market_data.sqlite3` (SELL 130 / BUY 121).
- **116 distinct symbols** have ≥ 1 event, but every symbol's events fall
  inside that same ~1.77 h window — there is no multi-day liquidation history
  for any symbol.
- Majors are thin to the point of absence: **BTCUSDT 5 events, ETHUSDT
  2 events** in the window. A symbol with OI must not be miscounted as having
  liquidation coverage: BTC/ETH have OI but effectively no liquidation depth.
- Only 10 symbols have ≥ 10 events: 1000PEPEUSDT 33, MUBARAKUSDT 51,
  ONEUSDT 45, KERNELUSDT 24, AKEUSDT 13, NEARUSDT 11, ZECUSDT 11, UAIUSDT 10,
  WIFUSDT 10, 龙虾USDT 18. The remaining 106 symbols have 1–9 events each.

Full per-symbol table (symbol, deduped event count, trade-time span UTC):

| Symbol | Events | Span |
|---|---|---|
| 1000BONKUSDC | 1 | 2026-09-22 07:12–07:12 |
| 1000BONKUSDT | 8 | 2026-09-22 07:00–07:03 |
| 1000FLOKIUSDT | 2 | 2026-09-22 07:11–07:13 |
| 1000PEPEUSDC | 4 | 2026-09-22 06:00–07:42 |
| 1000PEPEUSDT | 33 | 2026-09-22 05:57–07:42 |
| 1MBABYDOGEUSDT | 1 | 2026-09-22 07:04–07:04 |
| ACEUSDT | 1 | 2026-09-22 06:53–06:53 |
| ADAUSDT | 1 | 2026-09-22 07:03–07:03 |
| AGTUSDT | 2 | 2026-09-22 05:59–07:03 |
| AKEUSDT | 13 | 2026-09-22 06:52–07:03 |
| AVAUSDT | 3 | 2026-09-22 06:00–07:13 |
| AVNTUSDT | 1 | 2026-09-22 07:38–07:38 |
| BANKUSDT | 1 | 2026-09-22 07:06–07:06 |
| BANUSDT | 1 | 2026-09-22 05:59–05:59 |
| BEATUSDT | 2 | 2026-09-22 05:59–07:02 |
| BLESSUSDT | 1 | 2026-09-22 06:02–06:02 |
| BMTUSDT | 1 | 2026-09-22 06:01–06:01 |
| BNBUSDT | 1 | 2026-09-22 07:41–07:41 |
| BOMEUSDT | 1 | 2026-09-22 07:09–07:09 |
| BREVUSDT | 3 | 2026-09-22 05:57–05:58 |
| BROCCOLI714USDT | 5 | 2026-09-22 05:57–07:05 |
| BRUSDT | 5 | 2026-09-22 05:59–06:54 |
| BTCUSDT | 5 | 2026-09-22 05:59–07:03 |
| BUSDT | 1 | 2026-09-22 07:12–07:12 |
| CARVUSDT | 1 | 2026-09-22 07:01–07:01 |
| CELRUSDT | 1 | 2026-09-22 05:58–05:58 |
| CHIPUSDT | 1 | 2026-09-22 05:56–05:56 |
| CLUSDT | 2 | 2026-09-22 07:00–07:00 |
| COOKIEUSDT | 3 | 2026-09-22 07:07–07:08 |
| COTIUSDT | 2 | 2026-09-22 05:58–07:13 |
| CSOPSKHYNIX2LUSDT | 1 | 2026-09-22 07:00–07:00 |
| CYSUSDT | 3 | 2026-09-22 07:07–07:38 |
| DOGEUSDC | 1 | 2026-09-22 07:08–07:08 |
| DOGEUSDT | 8 | 2026-09-22 05:57–07:08 |
| DOTUSDT | 1 | 2026-09-22 07:03–07:03 |
| DRAMUSDT | 1 | 2026-09-22 07:01–07:01 |
| EDGEUSDT | 2 | 2026-09-22 07:00–07:08 |
| EIGENUSDT | 1 | 2026-09-22 07:00–07:00 |
| ENAUSDT | 2 | 2026-09-22 07:10–07:41 |
| ETHUSDC | 1 | 2026-09-22 05:59–05:59 |
| ETHUSDT | 2 | 2026-09-22 06:01–07:08 |
| FARTCOINUSDT | 1 | 2026-09-22 07:04–07:04 |
| FETUSDT | 2 | 2026-09-22 07:07–07:11 |
| FORMUSDT | 9 | 2026-09-22 06:01–07:40 |
| GENIUSUSDT | 1 | 2026-09-22 07:38–07:38 |
| GRASSUSDT | 2 | 2026-09-22 05:59–07:01 |
| GUSDT | 2 | 2026-09-22 05:59–07:10 |
| HBARUSDT | 1 | 2026-09-22 05:59–05:59 |
| HYPEUSDT | 2 | 2026-09-22 07:40–07:40 |
| INJUSDT | 5 | 2026-09-22 05:57–07:05 |
| JCTUSDT | 2 | 2026-09-22 07:38–07:42 |
| KAITOUSDT | 1 | 2026-09-22 07:38–07:38 |
| KERNELUSDT | 24 | 2026-09-22 07:35–07:41 |
| KMNOUSDT | 1 | 2026-09-22 06:02–06:02 |
| LDOUSDT | 1 | 2026-09-22 05:59–05:59 |
| LSKUSDT | 1 | 2026-09-22 07:40–07:40 |
| LUNA2USDT | 1 | 2026-09-22 07:41–07:41 |
| MARSCOINUSDT | 7 | 2026-09-22 06:53–07:12 |
| MERLUSDT | 3 | 2026-09-22 07:03–07:09 |
| METAUSDT | 1 | 2026-09-22 07:04–07:04 |
| MINIMAXUSDT | 1 | 2026-09-22 07:06–07:06 |
| MUBARAKUSDT | 51 | 2026-09-22 05:57–07:40 |
| NEARUSDT | 11 | 2026-09-22 05:56–07:40 |
| NILUSDT | 2 | 2026-09-22 07:38–07:41 |
| NVOUSDT | 1 | 2026-09-22 07:06–07:06 |
| ONEUSDT | 45 | 2026-09-22 05:58–07:41 |
| ONUSDT | 1 | 2026-09-22 07:41–07:41 |
| OPUSDT | 2 | 2026-09-22 06:01–06:01 |
| PENGUUSDT | 4 | 2026-09-22 06:01–07:41 |
| PHAUSDT | 3 | 2026-09-22 05:58–07:42 |
| PLUMEUSDT | 1 | 2026-09-22 06:00–06:00 |
| PONSUSDT | 7 | 2026-09-22 06:01–07:12 |
| POPCATUSDT | 2 | 2026-09-22 05:57–05:58 |
| PORTALUSDT | 1 | 2026-09-22 07:00–07:00 |
| PTBUSDT | 2 | 2026-09-22 07:12–07:37 |
| PUMPUSDT | 2 | 2026-09-22 07:03–07:05 |
| RAYSOLUSDT | 1 | 2026-09-22 07:05–07:05 |
| RECALLUSDT | 1 | 2026-09-22 07:38–07:38 |
| SAGAUSDT | 7 | 2026-09-22 06:01–07:38 |
| SEIUSDT | 1 | 2026-09-22 07:41–07:41 |
| SKHYNIXUSDT | 2 | 2026-09-22 07:00–07:02 |
| SKLUSDT | 2 | 2026-09-22 05:59–07:01 |
| SLPUSDT | 1 | 2026-09-22 07:38–07:38 |
| SNDKUSDT | 1 | 2026-09-22 07:41–07:41 |
| SOLUSDT | 1 | 2026-09-22 05:59–05:59 |
| SOMIUSDT | 1 | 2026-09-22 07:03–07:03 |
| SONICUSDT | 3 | 2026-09-22 05:56–07:02 |
| SOPHUSDT | 5 | 2026-09-22 05:58–06:02 |
| STXUSDT | 1 | 2026-09-22 07:08–07:08 |
| SUIUSDT | 1 | 2026-09-22 06:01–06:01 |
| SUSDT | 3 | 2026-09-22 07:42–07:42 |
| TACUSDT | 1 | 2026-09-22 05:58–05:58 |
| TAOUSDT | 4 | 2026-09-22 05:57–07:40 |
| TOWNSUSDT | 1 | 2026-09-22 07:12–07:12 |
| TRUMPUSDT | 1 | 2026-09-22 06:02–06:02 |
| TUTUSDT | 2 | 2026-09-22 06:01–07:11 |
| UAIUSDT | 10 | 2026-09-22 06:01–07:38 |
| UBUSDT | 1 | 2026-09-22 07:04–07:04 |
| USDBRLUSDT | 1 | 2026-09-22 07:38–07:38 |
| USELESSUSDT | 4 | 2026-09-22 06:52–07:10 |
| VETUSDT | 2 | 2026-09-22 07:03–07:41 |
| VTHOUSDT | 2 | 2026-09-22 06:01–07:08 |
| WALUSDT | 1 | 2026-09-22 07:04–07:04 |
| WIFUSDT | 10 | 2026-09-22 06:01–07:13 |
| WLDUSDT | 1 | 2026-09-22 06:00–06:00 |
| XAGUSDT | 1 | 2026-09-22 07:06–07:06 |
| XAUTUSDT | 1 | 2026-09-22 07:07–07:07 |
| XRPUSDT | 4 | 2026-09-22 05:59–07:40 |
| YBUSDT | 1 | 2026-09-22 05:56–05:56 |
| ZAMAUSDT | 1 | 2026-09-22 07:04–07:04 |
| ZBTUSDT | 1 | 2026-09-22 05:59–05:59 |
| ZECUSDT | 11 | 2026-09-22 05:56–07:42 |
| ZETAUSDT | 7 | 2026-09-22 05:56–07:41 |
| 我踏马来了USDT | 1 | 2026-09-22 07:38–07:38 |
| 牛来USDT | 3 | 2026-09-22 05:59–07:03 |
| 龙虾USDT | 18 | 2026-09-22 05:56–07:00 |

Explicit thinness statement: liquidation data is **raw per-event but thin**
— 106 of 116 symbols have fewer than 10 events, all inside one 1.77 h
window; the two OI symbols (BTCUSDT 5, ETHUSDT 2) have effectively no
liquidation depth. Any symbol not listed here has **absent** liquidation
coverage (0 events), including every symbol with no forceOrder row.

## 4. Per-symbol funding coverage (cross-reference)

Versioned datasets (`research/datasets/`, 8 h grid, previously validated at
0 duplicates / 0 missing 8 h intervals):

| Symbol | Start (UTC) | End (UTC) | Span | Periods | Gaps |
|---|---|---|---|---|---|
| BTCUSDT | 2025-10-28 16:00 | 2026-09-26 16:00 | 333 d | 1000 (2 × 500) | 0 |
| ETHUSDT | 2025-10-28 16:00 | 2026-09-26 16:00 | 333 d | 1000 (2 × 500) | 0 |

No other symbol has funding history in storage. (Local-collector
`futuresFundingRate` snapshot rows for BTC/ETH cover only ~21 h on
2026-09-22 and add nothing.)

## 5. Common overlapping window (OI + liquidation + funding + price, all at once)

- OI 5 m history: 2026-09-21 21:10–2026-09-22 07:35 (BTC/ETH only).
- Liquidation events: 2026-09-22 05:56–07:42 (116 symbols, BTC 5 / ETH 2).
- Funding 8 h: 2025-10-28–2026-09-26 (BTC/ETH only).
- Price 1 h: BTC 2024-11-29–2026-09-26, ETH 2025-10-28–2026-09-26.
- Intersection across all four data types: **2026-09-22 05:56–07:35 UTC
  (~1.65 h), BTCUSDT and ETHUSDT only** — the only symbols with OI at all.

## 6. Counts of symbols with long full (OI+liquidation+price) coverage

- **≥ 90 days: 0 symbols.**
- **≥ 180 days: 0 symbols.**

Adjacent-but-excluded data (not counted above): `optionOpenInterest` rows
for BTC/ETH/BNB/SOL/DOGE/XRP/XAU/XAG (~21 h on 2026-09-22) are options OI,
not futures OI; `futuresLongShortRatio` / `futuresTakerVolume` rows
(BTC/ETH, ~21 h) are positioning/volume ratios, not OI or liquidations;
`feature_snapshots` (214,066 rows) carry price/spread/depth/volume/CVD
features only — 0 rows mention OI or liquidation fields.

## 7. Missingness summary (% of expected bars missing, per symbol per type)

- OI 5 m grid (BTC/ETH): 0 gaps, **0.0% missing within its 10.4 h span**;
  **~99.5% missing against any 90-day requirement** (10.4 of 2160 h).
- OI snapshots: point readings, no bar grid — not applicable; span 2.2 h.
- Liquidation event feed: no bar grid exists (events, not bars), so a
  missing-bar % is not definable; coverage is 1.77 h of raw events with the
  per-symbol counts in §3 (106/116 symbols < 10 events; BTC 5, ETH 2).
- Funding 8 h grid (BTC/ETH): **0.0% missing** over 2025-10-28–2026-09-26.
- Price 1 h grid (BTC/ETH): **0.0% missing** over each dataset's span
  (previously validated: no silent gaps, no forward fills).

---

## Factual summary (not a decision)

```text
- N symbols have ≥90 days of full coverage: 0 symbols have ≥90 days of full coverage: []
- N symbols have ≥180 days of full coverage: 0 symbols have ≥180 days of full coverage: []
- Largest common overlapping window across all covered symbols: 2026-09-22 05:56–07:35 UTC (~1.65 h), BTCUSDT + ETHUSDT only
- Liquidation data type: raw event feed (per-liquidation forceOrder rows: side/price/qty/trade_time) — raw but thin (BTC 5 events, ETH 2 events in the window; 106/116 symbols < 10 events); absent (0 events) for every symbol not listed in §3
```
