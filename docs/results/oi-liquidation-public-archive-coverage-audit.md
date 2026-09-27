# OI + Liquidation Public-Archive Coverage Audit (Binance data.binance.vision)

Audit date: 2026-09-27. Method: live HTTPS probes (HEAD for existence,
GET for samples) against `https://data.binance.vision`, plus Binance's own
`binance/binance-public-data` documentation repository (README + full file
tree via the GitHub API). ~72,000 archive probes total. No hypothesis is
designed here, no holdout is touched or reserved, no Module 1 evaluation is
performed, and no decision beyond availability/coverage is made — that call
belongs to the human reviewing this file.

## A. Source verification

- Binance documentation/repository references: `binance/binance-public-data`
  README (fetched 2026-09-27, 5144 bytes) documents spot/futures
  aggTrades, klines (all intervals incl. `1mo`-for-`1M` note), and trades,
  with `curl`/`wget` URL patterns and helper scripts (`python/`,
  `shell/`). The repository file tree (21 entries, not truncated) contains
  **no reference to `metrics/`, `liquidationSnapshot/`, or `fundingRate/`**
  — those datasets are not documented in Binance's own repo. The
  python `enums.py`/download scripts cover klines/trades only.
- Confirmed archive paths (probed live, HTTP 200):
  `data/futures/um/daily/metrics/<SYMBOL>/<SYMBOL>-metrics-<YYYY-MM-DD>.zip`
  (daily only — the `monthly/metrics/` variant 404s);
  `data/futures/um/monthly/fundingRate/<SYMBOL>/<SYMBOL>-fundingRate-<YYYY-MM>.zip`
  (monthly only — the `daily/fundingRate/` variant 404s);
  `data/futures/um/daily/klines/<SYMBOL>/1h/<SYMBOL>-1h-<YYYY-MM-DD>.zip`
  plus `markPriceKlines/`, `indexPriceKlines/`, `premiumIndexKlines/`.
- `liquidationSnapshot/` is **UNAVAILABLE**: 8 distinct path/stem variants
  probed (`daily` + `monthly`, UM + CM, stems `liquidationSnapshot`,
  `liquidation`, `liquidations`, `forceOrders`, reversed-stem and
  underscore variants) across 2024/2025/2026 dates and BTC/ETH/SOL/BNB/DOGE/XRP
  — every probe HTTP 404. It is likewise absent from Binance's own repo docs.
- Formats: ZIP-compressed CSV (one CSV per zip, `testzip()` clean on all
  samples). Metrics CSV header (identical in all 5 samples):
  `create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio`
  (8 columns). FundingRate monthly CSV header:
  `calc_time,funding_interval_hours,last_funding_rate`.
- Checksum method: per Binance's documented convention, each zip has a
  same-folder `.CHECKSUM` sidecar containing `<sha256><two spaces><filename>`
  (97 bytes for metrics, 102 for the longer MARSCOINUSDT name), verifiable
  with `sha256sum -c`. All 6 sampled sidecars verified True with hashlib.
- Timestamp/date conventions: filenames carry UTC calendar dates; daily files
  are UTC-day partitions. Metrics rows are intraday `create_time`
  (`YYYY-MM-DD HH:MM:SS`, UTC) at 5-minute steps, 288 rows/day expected.
  FundingRate `calc_time` is integer milliseconds (8 h grid, `...001` ms
  convention, interval column = 8). Kline timestamps match `/fapi/v1/klines`
  semantics per Binance's README.
- Schema/version caveats: numeric formatting changed across archive history
  (2021 sample: OI at 8 dp, ratios at 16 dp; 2025+ samples: OI at 16 dp,
  ratios at 8 dp) with an identical 8-column header — formatting only, no
  column change. The README's "Updates" log lists 2 historical replacements
  (2022-08-08 klines, 2022-04-21 aggTrades); none for metrics/fundingRate.
  Metrics intraday grid phase varies by symbol/day (samples start
  00:00/00:05/00:10/00:35) while always totaling 288 rows = full 24 h —
  phase-shifted, not truncated.
- Metrics vs liquidationSnapshot semantics (verified): metrics files hold
  5-minute state snapshots (OI levels + positioning ratios) — daily
  partitions of intraday state, not daily aggregates. liquidationSnapshot
  semantics cannot be established — the dataset is not published at any
  verifiable path.

## B. Symbol coverage

Census denominator: live `fapi/v1/exchangeInfo` USDT PERPETUAL TRADING
universe = **527 symbols** (fetched 2026-09-27; delisted contracts are not
enumerable from any Binance-owned source — stated limitation, §C).

- Total symbols in metrics: **522 of 527**. Absent (no metrics file on any
  of 3 probed dates): 哈基米USDT, 币安人生USDT, 我踏马来了USDT, 牛来USDT,
  龙虾USDT (all very recent CJK-named listings).
- Total symbols in liquidationSnapshot: **0** (UNAVAILABLE, see §A).
- Intersection: **0**. Metrics-only: all 522. Liquidation-only: none.
- FundingRate-monthly presence (supplementary, same census): 520 of 527;
  absent: MARSCOINUSDT, PONSUSDT + the same 5 CJK symbols. So
  metrics-without-funding(monthly): MARSCOINUSDT, PONSUSDT. No symbol has
  funding but lacks metrics.

Per-symbol metrics table (first/last via exact date bisection; missing days
via exhaustive daily sweep for the 29-symbol panel, month-grid + full
day-level drill-down of every flag for the rest; pre-first periods are
listing boundaries, never gaps):

Symbol | Metrics start | Metrics end | Expected files | Missing days (verified) | Verification | Lifecycle | Funding overlap | Price overlap | Common full window
---|---|---|---|---|---|---|---|---|---
| 0GUSDT | 2025-09-17 | 2026-09-25 | 374 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000000BOBUSDT | 2025-06-05 | 2026-09-25 | 478 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000000MOGUSDT | 2024-11-07 | 2026-09-25 | 688 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000BONKUSDT | 2023-11-22 | 2026-09-25 | 1039 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000CATUSDT | 2024-10-21 | 2026-09-25 | 705 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000CHEEMSUSDT | 2024-11-25 | 2026-09-25 | 670 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000FLOKIUSDT | 2023-05-06 | 2026-09-25 | 1239 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000LUNCUSDT | 2022-09-09 | 2026-09-25 | 1478 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000PEPEUSDT | 2023-05-05 | 2026-09-25 | 1240 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000RATSUSDT | 2023-12-15 | 2026-09-25 | 1016 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000SATSUSDT | 2023-12-12 | 2026-09-25 | 1019 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1000SHIBUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| 1000XECUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1INCHUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 1MBABYDOGEUSDT | 2024-09-16 | 2026-09-25 | 740 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 2ZUSDT | 2025-10-02 | 2026-09-25 | 359 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| 4USDT | 2025-10-08 | 2026-09-25 | 353 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AAVEUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| ACEUSDT | 2023-12-18 | 2026-09-25 | 1013 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ACHUSDT | 2023-02-22 | 2026-09-25 | 1312 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ACTUSDT | 2024-11-11 | 2026-09-25 | 684 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ACUUSDT | 2026-01-21 | 2026-09-25 | 248 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ADAUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| AEROUSDT | 2024-12-04 | 2026-09-25 | 661 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AEVOUSDT | 2024-03-13 | 2026-09-25 | 927 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AGLDUSDT | 2023-07-29 | 2026-09-25 | 1155 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AGTUSDT | 2025-05-20 | 2026-09-25 | 494 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AIAUSDT | 2025-09-18 | 2026-09-25 | 373 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AIGENSYNUSDT | 2026-04-29 | 2026-09-25 | 150 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AINUSDT | 2025-07-10 | 2026-09-25 | 443 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AIOTUSDT | 2025-04-30 | 2026-09-25 | 514 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AIOUSDT | 2025-08-13 | 2026-09-25 | 409 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AIXBTUSDT | 2024-12-20 | 2026-09-25 | 645 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AKEUSDT | 2025-09-26 | 2026-09-25 | 365 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AKTUSDT | 2024-11-18 | 2026-09-25 | 677 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALCHUSDT | 2025-01-07 | 2026-09-25 | 627 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALGOUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALICEUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALLOUSDT | 2025-11-11 | 2026-09-25 | 319 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALLUSDT | 2025-08-06 | 2026-09-25 | 416 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALPINEUSDT | 2025-05-06 | 2026-09-25 | 508 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ALTUSDT | 2024-01-25 | 2026-09-25 | 975 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ANIMEUSDT | 2025-01-23 | 2026-09-25 | 611 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ANKRUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| APEUSDT | 2022-03-17 | 2026-09-25 | 1654 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| API3USDT | 2022-02-22 | 2026-09-25 | 1677 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| APRUSDT | 2025-10-23 | 2026-09-25 | 338 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| APTUSDT | 2022-10-19 | 2026-09-25 | 1438 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| ARBUSDT | 2023-03-23 | 2026-09-25 | 1283 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| ARCUSDT | 2025-01-17 | 2026-09-25 | 617 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ARIAUSDT | 2025-09-03 | 2026-09-25 | 388 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ARKMUSDT | 2023-07-28 | 2026-09-25 | 1156 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ARKUSDT | 2023-09-19 | 2026-09-25 | 1103 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ARPAUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ARUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ARXUSDT | 2026-06-23 | 2026-09-25 | 95 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ASRUSDT | 2025-05-06 | 2026-09-25 | 508 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ASTERUSDT | 2025-09-19 | 2026-09-25 | 372 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ASTRUSDT | 2023-02-14 | 2026-09-25 | 1320 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ATHUSDT | 2025-04-02 | 2026-09-25 | 542 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ATOMUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| ATUSDT | 2025-10-29 | 2026-09-25 | 332 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AUCTIONUSDT | 2023-12-15 | 2026-09-25 | 1016 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AUSDT | 2025-05-28 | 2026-09-25 | 486 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AVAAIUSDT | 2025-01-17 | 2026-09-25 | 617 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AVAUSDT | 2024-12-13 | 2026-09-25 | 652 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AVAXUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| AVNTUSDT | 2025-09-09 | 2026-09-25 | 382 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AWEUSDT | 2025-05-21 | 2026-09-25 | 493 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AXLUSDT | 2024-03-01 | 2026-09-25 | 939 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AXSUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| AZTECUSDT | 2026-02-11 | 2026-09-25 | 227 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| B2USDT | 2025-05-06 | 2026-09-25 | 508 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BABYUSDT | 2025-04-05 | 2026-09-25 | 539 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BANANAS31USDT | 2025-03-22 | 2026-09-25 | 553 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BANANAUSDT | 2024-08-15 | 2026-09-25 | 772 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BANDUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BANKUSDT | 2025-04-18 | 2026-09-25 | 526 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BANUSDT | 2024-11-18 | 2026-09-25 | 677 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BARDUSDT | 2025-09-18 | 2026-09-25 | 373 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BASEDUSDT | 2026-03-30 | 2026-09-25 | 180 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BASUSDT | 2025-08-26 | 2026-09-25 | 396 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BATUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BBUSDT | 2024-05-13 | 2026-09-25 | 866 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BCHUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| BEAMXUSDT | 2023-11-17 | 2026-09-25 | 1044 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BEATUSDT | 2025-11-12 | 2026-09-25 | 318 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BELUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BERAUSDT | 2025-02-06 | 2026-09-25 | 597 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BICOUSDT | 2023-09-28 | 2026-09-25 | 1094 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BIGTIMEUSDT | 2023-10-12 | 2026-09-25 | 1080 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BILLUSDT | 2026-05-07 | 2026-09-25 | 142 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BIOUSDT | 2025-01-03 | 2026-09-25 | 631 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BIRBUSDT | 2026-01-29 | 2026-09-25 | 240 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BLESSUSDT | 2025-09-23 | 2026-09-25 | 368 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BLUAIUSDT | 2025-10-21 | 2026-09-25 | 340 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BLURUSDT | 2023-04-28 | 2026-09-25 | 1247 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BMTUSDT | 2025-03-17 | 2026-09-25 | 558 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BNBUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| BNTUSDT | 2023-08-10 | 2026-09-25 | 1143 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BOMEUSDT | 2024-03-16 | 2026-09-25 | 924 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BRETTUSDT | 2024-08-20 | 2026-09-25 | 767 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BREVUSDT | 2025-12-30 | 2026-09-25 | 270 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BROCCOLI714USDT | 2025-03-21 | 2026-09-25 | 554 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BROCCOLIF3BUSDT | 2025-03-21 | 2026-09-25 | 554 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BRUSDT | 2025-03-21 | 2026-09-25 | 554 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BSBUSDT | 2026-03-25 | 2026-09-25 | 185 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BSVUSDT | 2023-10-20 | 2026-09-25 | 1072 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BTCDOMUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BTCUSDT | 2020-09-01 | 2026-09-25 | 2216 | 0 | full-daily | FULL | 2025-10-28..2026-09-26 (8h, 0 gaps) | 2024-11-29..2026-09-26 (1h) | 2025-10-28..2026-09-25, 333d (metrics+funding+price; no liq) |
| BTRUSDT | 2025-08-27 | 2026-09-25 | 395 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BTWUSDT | 2026-06-04 | 2026-09-25 | 114 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BULLAUSDT | 2025-07-04 | 2026-09-25 | 449 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| BUSDT | 2025-05-22 | 2026-09-25 | 492 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| C98USDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CAKEUSDT | 2023-11-02 | 2026-09-25 | 1059 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CAPUSDT | 2026-06-27 | 2026-09-25 | 91 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CARVUSDT | 2025-08-07 | 2026-09-25 | 415 | n/a (bounds-only) | bounds-only | UNVERIFIED | none (internal) | none (internal) | none |
| CATIUSDT | 2024-09-20 | 2026-09-25 | 736 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CCUSDT | 2025-10-31 | 2026-09-25 | 330 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CELOUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CELRUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CETUSUSDT | 2024-11-06 | 2026-09-25 | 689 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CFGUSDT | 2026-03-16 | 2026-09-25 | 194 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CFXUSDT | 2023-02-20 | 2026-09-25 | 1314 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CGPTUSDT | 2024-12-20 | 2026-09-25 | 645 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CHILLGUYUSDT | 2024-11-27 | 2026-09-25 | 668 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CHIPUSDT | 2026-04-16 | 2026-09-25 | 163 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CHRUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CHZUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CKBUSDT | 2023-02-28 | 2026-09-25 | 1306 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CLANKERUSDT | 2025-11-12 | 2026-09-25 | 318 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CLOUSDT | 2025-10-14 | 2026-09-25 | 347 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| COAIUSDT | 2025-09-25 | 2026-09-25 | 366 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| COLLECTUSDT | 2025-12-31 | 2026-09-25 | 269 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| COMPUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| COOKIEUSDT | 2025-01-07 | 2026-09-25 | 627 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| COTIUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| COWUSDT | 2024-11-06 | 2026-09-25 | 689 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CROSSUSDT | 2025-07-10 | 2026-09-25 | 443 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CRVUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CTKUSDT | 2021-12-01 | 2026-09-25 | 1760 | 301 [2024-06-26..2024-07-08; 2024-07-16..2025-04-29] | grid+drill-exact | PARTIAL | none (internal) | none (internal) | none |
| CTRUSDT | 2026-05-28 | 2026-09-25 | 121 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CTSIUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CUSDT | 2025-07-15 | 2026-09-25 | 438 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CVCUSDT | 2025-05-16 | 2026-09-25 | 498 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CVXUSDT | 2022-09-22 | 2026-09-25 | 1465 | 385 [2024-06-26..2024-07-08; 2024-07-16..2025-07-22] | grid+drill-exact | PARTIAL | none (internal) | none (internal) | none |
| CYBERUSDT | 2023-08-21 | 2026-09-25 | 1132 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| CYSUSDT | 2025-12-12 | 2026-09-25 | 288 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DASHUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DATAIPUSDT | 2026-07-03 | 2026-09-25 | 85 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DEEPUSDT | 2025-04-22 | 2026-09-25 | 522 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DEXEUSDT | 2024-12-24 | 2026-09-25 | 641 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DIAUSDT | 2024-10-02 | 2026-09-25 | 724 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DODOXUSDT | 2023-08-08 | 2026-09-25 | 1145 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DOGEUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| DOGSUSDT | 2024-08-26 | 2026-09-25 | 761 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DOLOUSDT | 2025-05-01 | 2026-09-25 | 513 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DOODUSDT | 2025-05-09 | 2026-09-25 | 505 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DOSUSDT | 2026-08-11 | 2026-09-25 | 46 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DOTUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| DRIFTUSDT | 2024-11-08 | 2026-09-25 | 687 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DUSKUSDT | 2022-01-07 | 2026-09-25 | 1723 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DYDXUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| DYMUSDT | 2024-02-07 | 2026-09-25 | 962 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EDENUSDT | 2025-09-30 | 2026-09-25 | 361 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EDGEUSDT | 2026-03-19 | 2026-09-25 | 191 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EDUUSDT | 2023-04-30 | 2026-09-25 | 1245 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EGLDUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EIGENUSDT | 2024-10-01 | 2026-09-25 | 725 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ELSAUSDT | 2026-01-22 | 2026-09-25 | 247 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ENAUSDT | 2024-04-02 | 2026-09-25 | 907 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ENJUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ENSOUSDT | 2025-10-14 | 2026-09-25 | 347 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ENSUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EPICUSDT | 2025-03-13 | 2026-09-25 | 562 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ERAUSDT | 2025-07-17 | 2026-09-25 | 436 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ESPORTSUSDT | 2025-07-29 | 2026-09-25 | 424 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ESPUSDT | 2026-02-10 | 2026-09-25 | 228 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ETCUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| ETHFIUSDT | 2024-03-18 | 2026-09-25 | 922 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ETHUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | 2025-10-28..2026-09-26 (8h, 0 gaps) | 2025-10-28..2026-09-26 (1h) | 2025-10-28..2026-09-25, 333d (metrics+funding+price; no liq) |
| ETHWUSDT | 2023-11-28 | 2026-09-25 | 1033 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EULUSDT | 2025-10-13 | 2026-09-25 | 348 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| EVAAUSDT | 2025-10-03 | 2026-09-25 | 358 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FARTCOINUSDT | 2024-12-20 | 2026-09-25 | 645 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FETUSDT | 2023-01-17 | 2026-09-25 | 1348 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FFUSDT | 2025-09-29 | 2026-09-25 | 362 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FHEUSDT | 2025-04-12 | 2026-09-25 | 532 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FIDAUSDT | 2024-09-19 | 2026-09-25 | 737 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FIGHTUSDT | 2026-01-23 | 2026-09-25 | 246 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FILUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| FLOCKUSDT | 2025-09-09 | 2026-09-25 | 382 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FLOWUSDT | 2022-02-10 | 2026-09-25 | 1689 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FLUIDUSDT | 2025-09-24 | 2026-09-25 | 367 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FLUXUSDT | 2024-09-03 | 2026-09-25 | 753 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FOGOUSDT | 2026-01-10 | 2026-09-25 | 259 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FOLKSUSDT | 2025-11-06 | 2026-09-25 | 324 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FORMUSDT | 2025-03-19 | 2026-09-25 | 556 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FRAXUSDT | 2026-01-15 | 2026-09-25 | 254 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| FUSDT | 2025-06-18 | 2026-09-25 | 465 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GALAUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GASUSDT | 2023-10-25 | 2026-09-25 | 1067 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GENIUSUSDT | 2026-04-16 | 2026-09-25 | 163 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GIGGLEUSDT | 2025-10-09 | 2026-09-25 | 352 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GLMUSDT | 2024-02-22 | 2026-09-25 | 947 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GMTUSDT | 2022-03-15 | 2026-09-25 | 1656 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GMXUSDT | 2023-02-17 | 2026-09-25 | 1317 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GOATUSDT | 2024-10-24 | 2026-09-25 | 702 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GPSUSDT | 2025-02-17 | 2026-09-25 | 586 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GRAMUSDT | 2026-07-02 | 2026-09-25 | 86 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GRASSUSDT | 2024-11-08 | 2026-09-25 | 687 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GRIFFAINUSDT | 2025-01-02 | 2026-09-25 | 632 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GRTUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GRVTUSDT | 2026-07-31 | 2026-09-25 | 57 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GTCUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GUAUSDT | 2025-12-21 | 2026-09-25 | 279 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GUNUSDT | 2025-03-31 | 2026-09-25 | 544 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GUSDT | 2024-08-15 | 2026-09-25 | 772 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| GWEIUSDT | 2026-01-29 | 2026-09-25 | 240 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HAEDALUSDT | 2025-05-01 | 2026-09-25 | 513 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HANAUSDT | 2025-09-26 | 2026-09-25 | 365 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HBARUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HEIUSDT | 2025-02-13 | 2026-09-25 | 590 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HEMIUSDT | 2025-08-29 | 2026-09-25 | 393 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HIVEUSDT | 2024-12-23 | 2026-09-25 | 642 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HMSTRUSDT | 2024-09-26 | 2026-09-25 | 730 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HOLOUSDT | 2025-09-11 | 2026-09-25 | 380 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HOMEUSDT | 2025-06-10 | 2026-09-25 | 473 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HOTUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HUMAUSDT | 2025-05-26 | 2026-09-25 | 488 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HUSDT | 2025-06-25 | 2026-09-25 | 458 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HYPERUSDT | 2025-04-22 | 2026-09-25 | 522 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| HYPEUSDT | 2025-05-30 | 2026-09-25 | 484 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ICNTUSDT | 2025-07-03 | 2026-09-25 | 450 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ICPUSDT | 2022-09-27 | 2026-09-25 | 1460 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IDOLUSDT | 2025-07-04 | 2026-09-25 | 449 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IDUSDT | 2023-03-23 | 2026-09-25 | 1283 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ILVUSDT | 2023-11-10 | 2026-09-25 | 1051 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IMXUSDT | 2022-02-11 | 2026-09-25 | 1688 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| INITUSDT | 2025-04-16 | 2026-09-25 | 528 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| INJUSDT | 2022-08-17 | 2026-09-25 | 1501 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| INUSDT | 2025-08-07 | 2026-09-25 | 415 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| INXUSDT | 2026-01-30 | 2026-09-25 | 239 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IOSTUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IOTAUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IOTXUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IOUSDT | 2024-06-11 | 2026-09-25 | 837 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| IRYSUSDT | 2025-11-26 | 2026-09-25 | 304 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JASMYUSDT | 2022-04-20 | 2026-09-25 | 1620 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JCTUSDT | 2025-11-10 | 2026-09-25 | 320 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JELLYJELLYUSDT | 2025-03-26 | 2026-09-25 | 549 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JOEUSDT | 2023-03-29 | 2026-09-25 | 1277 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JSTUSDT | 2025-04-28 | 2026-09-25 | 516 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JTOUSDT | 2023-12-08 | 2026-09-25 | 1023 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| JUPUSDT | 2024-01-31 | 2026-09-25 | 969 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KAIAUSDT | 2024-12-04 | 2026-09-25 | 661 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KAITOUSDT | 2025-02-20 | 2026-09-25 | 583 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KASUSDT | 2023-11-17 | 2026-09-25 | 1044 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KATUSDT | 2026-03-02 | 2026-09-25 | 208 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KAVAUSDT | 2021-12-01 | 2026-09-25 | 1760 | n/a (bounds-only) | bounds-only | UNVERIFIED | none (internal) | none (internal) | none |
| KERNELUSDT | 2025-04-14 | 2026-09-25 | 530 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KGENUSDT | 2025-10-07 | 2026-09-25 | 354 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KITEUSDT | 2025-10-29 | 2026-09-25 | 332 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KMNOUSDT | 2024-12-20 | 2026-09-25 | 645 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KNCUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KOMAUSDT | 2024-12-10 | 2026-09-25 | 655 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| KSMUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LABUSDT | 2025-10-17 | 2026-09-25 | 344 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LAUSDT | 2025-06-05 | 2026-09-25 | 478 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LAYERUSDT | 2025-02-11 | 2026-09-25 | 592 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LDOUSDT | 2022-09-22 | 2026-09-25 | 1465 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LIGHTUSDT | 2025-09-27 | 2026-09-25 | 364 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LINEAUSDT | 2025-09-01 | 2026-09-25 | 390 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LINKUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| LISTAUSDT | 2024-06-20 | 2026-09-25 | 828 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LITUSDT | 2021-12-01 | 2026-09-25 | 1760 | 200 [2025-06-06..2025-12-22] | grid+drill-exact | PARTIAL | none (internal) | none (internal) | none |
| LPTUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LQTYUSDT | 2023-03-10 | 2026-09-25 | 1296 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LSKUSDT | 2024-01-25 | 2026-09-25 | 975 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LTCUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| LUMIAUSDT | 2024-12-18 | 2026-09-25 | 647 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LUNA2USDT | 2022-09-10 | 2026-09-25 | 1477 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| LYNUSDT | 2025-10-06 | 2026-09-25 | 355 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MAGICUSDT | 2023-01-25 | 2026-09-25 | 1340 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MAGMAUSDT | 2025-12-31 | 2026-09-25 | 269 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MANAUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MANTAUSDT | 2024-01-18 | 2026-09-25 | 982 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MANTRAUSDT | 2026-03-04 | 2026-09-25 | 206 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MARSCOINUSDT | 2026-09-01 | 2026-09-25 | 25 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| MASKUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MAVIAUSDT | 2024-02-21 | 2026-09-25 | 948 | 15 [2025-03-11..2025-03-25] | grid+drill-exact | PARTIAL | none (internal) | none (internal) | none |
| MAVUSDT | 2023-06-29 | 2026-09-25 | 1185 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MEGAUSDT | 2026-01-30 | 2026-09-25 | 239 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MELANIAUSDT | 2025-01-20 | 2026-09-25 | 614 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MEMEUSDT | 2023-11-03 | 2026-09-25 | 1058 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MERLUSDT | 2025-05-29 | 2026-09-25 | 485 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| METISUSDT | 2024-03-12 | 2026-09-25 | 928 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| METUSDT | 2025-10-11 | 2026-09-25 | 350 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MEUSDT | 2024-12-10 | 2026-09-25 | 655 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MEWUSDT | 2024-06-17 | 2026-09-25 | 831 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MINAUSDT | 2023-02-06 | 2026-09-25 | 1328 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MIRAUSDT | 2025-09-26 | 2026-09-25 | 365 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MITOUSDT | 2025-08-28 | 2026-09-25 | 394 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MMTUSDT | 2025-11-04 | 2026-09-25 | 326 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MOCAUSDT | 2024-12-16 | 2026-09-25 | 649 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MONUSDT | 2025-10-10 | 2026-09-25 | 351 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MOODENGUSDT | 2024-10-25 | 2026-09-25 | 701 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MORPHOUSDT | 2024-11-27 | 2026-09-25 | 668 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MOVEUSDT | 2024-12-09 | 2026-09-25 | 656 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MOVRUSDT | 2023-12-26 | 2026-09-25 | 1005 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MTLUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MUBARAKUSDT | 2025-03-17 | 2026-09-25 | 558 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MUSDT | 2025-07-07 | 2026-09-25 | 446 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| MYXUSDT | 2025-06-18 | 2026-09-25 | 465 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NAORISUSDT | 2025-07-31 | 2026-09-25 | 422 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NEARUSDT | 2021-12-01 | 2026-09-25 | 1760 | 1 [2023-12-18..2023-12-18] | full-daily | PARTIAL | none (internal) | none (internal) | none |
| NEIROUSDT | 2024-09-16 | 2026-09-25 | 740 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NEOUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NEWTUSDT | 2025-06-19 | 2026-09-25 | 464 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NIGHTUSDT | 2025-12-10 | 2026-09-25 | 290 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NILUSDT | 2025-03-24 | 2026-09-25 | 551 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NMRUSDT | 2023-06-22 | 2026-09-25 | 1192 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NOMUSDT | 2025-10-01 | 2026-09-25 | 360 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NOTUSDT | 2024-05-16 | 2026-09-25 | 863 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| NXPCUSDT | 2025-05-15 | 2026-09-25 | 499 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OGNUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OGUSDT | 2025-05-12 | 2026-09-25 | 502 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ONDOUSDT | 2024-01-20 | 2026-09-25 | 980 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ONEUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ONGUSDT | 2023-11-27 | 2026-09-25 | 1034 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ONTUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ONUSDT | 2025-10-24 | 2026-09-25 | 337 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OPENUSDT | 2025-09-08 | 2026-09-25 | 383 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OPGUSDT | 2026-04-22 | 2026-09-25 | 157 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OPNUSDT | 2026-02-21 | 2026-09-25 | 217 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OPUSDT | 2022-06-01 | 2026-09-25 | 1578 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| ORCAUSDT | 2024-12-06 | 2026-09-25 | 659 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ORDERUSDT | 2025-09-26 | 2026-09-25 | 365 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ORDIUSDT | 2023-11-07 | 2026-09-25 | 1054 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| OUSDT | 2026-06-24 | 2026-09-25 | 94 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PARTIUSDT | 2025-03-25 | 2026-09-25 | 550 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PAXGUSDT | 2025-03-27 | 2026-09-25 | 548 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PENDLEUSDT | 2023-07-28 | 2026-09-25 | 1156 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PENGUUSDT | 2024-12-17 | 2026-09-25 | 648 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PEOPLEUSDT | 2021-12-23 | 2026-09-25 | 1738 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PHAROSUSDT | 2026-05-14 | 2026-09-25 | 135 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PHAUSDT | 2024-12-30 | 2026-09-25 | 635 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PIEVERSEUSDT | 2025-11-14 | 2026-09-25 | 316 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PIPPINUSDT | 2025-01-24 | 2026-09-25 | 610 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PIXELUSDT | 2024-02-19 | 2026-09-25 | 950 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PLAYUSDT | 2025-07-31 | 2026-09-25 | 422 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PLUMEUSDT | 2025-03-21 | 2026-09-25 | 554 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PNUTUSDT | 2024-11-11 | 2026-09-25 | 684 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| POLUSDT | 2024-09-13 | 2026-09-25 | 743 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| POLYXUSDT | 2023-10-25 | 2026-09-25 | 1067 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PONSUSDT | 2026-09-06 | 2026-09-25 | 20 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| POPCATUSDT | 2024-08-22 | 2026-09-25 | 765 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PORTALUSDT | 2024-02-29 | 2026-09-25 | 940 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| POWERUSDT | 2025-12-06 | 2026-09-25 | 294 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| POWRUSDT | 2023-10-27 | 2026-09-25 | 1065 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PRLUSDT | 2026-04-01 | 2026-09-25 | 178 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PROMPTUSDT | 2025-04-11 | 2026-09-25 | 533 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PROMUSDT | 2025-01-15 | 2026-09-25 | 619 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PROVEUSDT | 2025-08-05 | 2026-09-25 | 417 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PTBUSDT | 2025-09-03 | 2026-09-25 | 388 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PUMPBTCUSDT | 2025-06-13 | 2026-09-25 | 470 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PUMPUSDT | 2025-04-12 | 2026-09-25 | 532 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PUNDIXUSDT | 2025-04-30 | 2026-09-25 | 514 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| PYTHUSDT | 2023-11-22 | 2026-09-25 | 1039 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| QNTUSDT | 2022-10-20 | 2026-09-25 | 1437 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| QTUMUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| QUSDT | 2025-09-02 | 2026-09-25 | 389 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RAREUSDT | 2024-08-15 | 2026-09-25 | 772 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RAVEUSDT | 2025-12-14 | 2026-09-25 | 286 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RAYSOLUSDT | 2024-12-10 | 2026-09-25 | 655 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RECALLUSDT | 2025-10-15 | 2026-09-25 | 346 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| REDUSDT | 2025-03-06 | 2026-09-25 | 569 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RENDERUSDT | 2024-07-26 | 2026-09-25 | 792 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RESOLVUSDT | 2025-06-10 | 2026-09-25 | 473 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| REUSDT | 2026-06-18 | 2026-09-25 | 100 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| REZUSDT | 2024-04-30 | 2026-09-25 | 879 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RIFUSDT | 2023-10-21 | 2026-09-25 | 1071 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RIVERUSDT | 2025-10-17 | 2026-09-25 | 344 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RLCUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ROBOUSDT | 2026-02-27 | 2026-09-25 | 211 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RONINUSDT | 2024-02-06 | 2026-09-25 | 963 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ROSEUSDT | 2021-12-30 | 2026-09-25 | 1731 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RPLUSDT | 2024-09-09 | 2026-09-25 | 747 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RSRUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RUNEUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| RVNUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SAFEUSDT | 2024-10-25 | 2026-09-25 | 701 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SAGAUSDT | 2024-04-09 | 2026-09-25 | 900 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SAHARAUSDT | 2025-06-26 | 2026-09-25 | 457 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SANDUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SANTOSUSDT | 2024-10-28 | 2026-09-25 | 698 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SAPIENUSDT | 2025-08-20 | 2026-09-25 | 402 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SCRUSDT | 2024-10-22 | 2026-09-25 | 704 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SEIUSDT | 2023-08-17 | 2026-09-25 | 1136 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| SENTUSDT | 2025-11-14 | 2026-09-25 | 316 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SFPUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SHELLUSDT | 2025-02-17 | 2026-09-25 | 586 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SIGNUSDT | 2025-04-28 | 2026-09-25 | 516 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SIRENUSDT | 2025-03-22 | 2026-09-25 | 553 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SKLUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SKRUSDT | 2026-01-22 | 2026-09-25 | 247 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SKYAIUSDT | 2025-05-13 | 2026-09-25 | 501 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SKYUSDT | 2025-09-09 | 2026-09-25 | 382 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SLPUSDT | 2025-07-23 | 2026-09-25 | 430 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SLXUSDT | 2026-06-01 | 2026-09-25 | 117 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SNXUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SOLUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| SOLVUSDT | 2025-01-17 | 2026-09-25 | 617 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SOMIUSDT | 2025-08-25 | 2026-09-25 | 397 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SONICUSDT | 2025-01-08 | 2026-09-25 | 626 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SOONUSDT | 2025-05-23 | 2026-09-25 | 491 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SOPHUSDT | 2025-05-28 | 2026-09-25 | 486 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SPACEUSDT | 2026-01-23 | 2026-09-25 | 246 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SPELLUSDT | 2022-09-06 | 2026-09-25 | 1481 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SPKUSDT | 2025-06-17 | 2026-09-25 | 466 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SPORTFUNUSDT | 2026-01-16 | 2026-09-25 | 253 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SPXUSDT | 2024-12-10 | 2026-09-25 | 655 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SQDUSDT | 2025-06-11 | 2026-09-25 | 472 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SSVUSDT | 2023-02-24 | 2026-09-25 | 1310 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STABLEUSDT | 2025-11-06 | 2026-09-25 | 324 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STARUSDT | 2026-05-14 | 2026-09-25 | 135 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STBLUSDT | 2025-09-17 | 2026-09-25 | 374 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STEEMUSDT | 2023-11-08 | 2026-09-25 | 1053 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STOUSDT | 2025-04-12 | 2026-09-25 | 532 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STRKUSDT | 2024-02-20 | 2026-09-25 | 949 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| STXUSDT | 2023-02-21 | 2026-09-25 | 1313 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SUIUSDT | 2023-05-03 | 2026-09-25 | 1242 | 1 [2023-12-13..2023-12-13] | full-daily | PARTIAL | none (internal) | none (internal) | none |
| SUNUSDT | 2024-08-22 | 2026-09-25 | 765 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SUPERUSDT | 2023-11-26 | 2026-09-25 | 1035 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SUSDT | 2025-01-16 | 2026-09-25 | 618 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SUSHIUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SWARMSUSDT | 2025-01-07 | 2026-09-25 | 627 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SXTUSDT | 2025-05-02 | 2026-09-25 | 512 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SYNUSDT | 2024-08-16 | 2026-09-25 | 771 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| SYRUPUSDT | 2025-05-07 | 2026-09-25 | 507 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TACUSDT | 2025-07-15 | 2026-09-25 | 438 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TAGUSDT | 2025-07-25 | 2026-09-25 | 428 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TAIKOUSDT | 2025-06-11 | 2026-09-25 | 472 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TAKEUSDT | 2025-09-03 | 2026-09-25 | 388 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TAOUSDT | 2024-04-11 | 2026-09-25 | 898 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| TAUSDT | 2025-07-21 | 2026-09-25 | 432 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| THETAUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| THEUSDT | 2024-11-27 | 2026-09-25 | 668 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TIAUSDT | 2023-10-31 | 2026-09-25 | 1061 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TLMUSDT | 2023-03-24 | 2026-09-25 | 1282 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TNSRUSDT | 2024-04-08 | 2026-09-25 | 901 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TOSHIUSDT | 2025-09-17 | 2026-09-25 | 374 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TOWNSUSDT | 2025-08-05 | 2026-09-25 | 417 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TRADOORUSDT | 2025-09-19 | 2026-09-25 | 372 | n/a (bounds-only) | bounds-only | UNVERIFIED | none (internal) | none (internal) | none |
| TRBUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TREEUSDT | 2025-07-29 | 2026-09-25 | 424 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TRIAUSDT | 2026-02-06 | 2026-09-25 | 232 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TRUMPUSDT | 2025-01-18 | 2026-09-25 | 616 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TRUSTUSDT | 2025-11-05 | 2026-09-25 | 325 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TRUTHUSDT | 2025-10-01 | 2026-09-25 | 360 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TRXUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| TSTUSDT | 2025-02-09 | 2026-09-25 | 594 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TURBOUSDT | 2024-05-30 | 2026-09-25 | 849 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TURTLEUSDT | 2025-10-22 | 2026-09-25 | 339 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TUSDT | 2023-02-01 | 2026-09-25 | 1333 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TUTUSDT | 2025-03-20 | 2026-09-25 | 555 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| TWTUSDT | 2023-11-03 | 2026-09-25 | 1058 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| UAIUSDT | 2025-11-06 | 2026-09-25 | 324 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| UBUSDT | 2025-09-12 | 2026-09-25 | 379 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| UMAUSDT | 2023-05-10 | 2026-09-25 | 1235 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| UNIUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| USDCUSDT | 2023-03-12 | 2026-09-25 | 1294 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| USELESSUSDT | 2025-08-15 | 2026-09-25 | 407 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| USTCUSDT | 2023-11-27 | 2026-09-25 | 1034 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| USUALUSDT | 2024-12-18 | 2026-09-25 | 647 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| USUSDT | 2025-12-12 | 2026-09-25 | 288 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VANAUSDT | 2024-12-16 | 2026-09-25 | 649 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VELODROMEUSDT | 2024-12-13 | 2026-09-25 | 652 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VELVETUSDT | 2025-07-15 | 2026-09-25 | 438 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VETUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VIRTUALUSDT | 2024-12-10 | 2026-09-25 | 655 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VTHOUSDT | 2025-01-22 | 2026-09-25 | 612 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| VVVUSDT | 2025-01-29 | 2026-09-25 | 605 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WALUSDT | 2025-03-27 | 2026-09-25 | 548 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WAXPUSDT | 2023-10-18 | 2026-09-25 | 1074 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WCTUSDT | 2025-04-15 | 2026-09-25 | 529 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WETUSDT | 2025-12-10 | 2026-09-25 | 290 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WIFUSDT | 2024-01-18 | 2026-09-25 | 982 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WLDUSDT | 2023-07-24 | 2026-09-25 | 1160 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WLFIUSDT | 2025-08-23 | 2026-09-25 | 399 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WOOUSDT | 2022-04-08 | 2026-09-25 | 1632 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| WUSDT | 2024-04-03 | 2026-09-25 | 906 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XAIUSDT | 2024-01-09 | 2026-09-25 | 991 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XANUSDT | 2025-09-29 | 2026-09-25 | 362 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XAUTUSDT | 2026-03-26 | 2026-09-25 | 184 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XLMUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XMRUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XNYUSDT | 2025-08-13 | 2026-09-25 | 409 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XPINUSDT | 2025-09-12 | 2026-09-25 | 379 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XPLUSDT | 2025-08-22 | 2026-09-25 | 400 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XRPUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | full-daily | FULL | none (internal) | none (internal) | none |
| XTZUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XVGUSDT | 2023-07-05 | 2026-09-25 | 1179 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| XVSUSDT | 2023-04-13 | 2026-09-25 | 1262 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| YBUSDT | 2025-10-10 | 2026-09-25 | 351 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| YFIUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| YGGUSDT | 2023-08-05 | 2026-09-25 | 1148 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZAMAUSDT | 2026-01-09 | 2026-09-25 | 260 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZBTUSDT | 2025-10-17 | 2026-09-25 | 344 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZECUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZENUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZEREBROUSDT | 2025-01-02 | 2026-09-25 | 632 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZESTUSDT | 2026-06-04 | 2026-09-25 | 114 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZETAUSDT | 2024-02-02 | 2026-09-25 | 967 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZILUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZKCUSDT | 2025-09-15 | 2026-09-25 | 376 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZKPUSDT | 2025-12-21 | 2026-09-25 | 279 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZKUSDT | 2024-06-17 | 2026-09-25 | 831 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZORAUSDT | 2025-07-25 | 2026-09-25 | 428 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZROUSDT | 2024-06-20 | 2026-09-25 | 828 | 0 | month-grid | FULL | none (internal) | none (internal) | none |
| ZRXUSDT | 2021-12-01 | 2026-09-25 | 1760 | 0 | month-grid | FULL | none (internal) | none (internal) | none |

*Verification levels: `full-daily` = every calendar date in [first, last] probed (29-symbol panel, 0 transport errors); `grid+drill-exact` = month-grid probes plus exhaustive day-level drill-down of every flagged span (CTK/CVX/LIT/MAVIA); `month-grid` = 1st+15th probes of every month in span with zero flags (day-level gaps inside present months cannot be excluded at this level — see intraday caveat in §C). `bounds-only`/`UNVERIFIED` (3 symbols: first/last bisected, interior not probed — excluded from all FULL counts). `Lifecycle` = FULL (continuous within verified resolution), PARTIAL (genuine gaps enumerated), or UNVERIFIED. Pre-first periods are listing starts, never gaps.*

## C. Missingness classification

Five distinct states observed (never collapsed into one number):

- **Missing archive file, genuine gap** (contract demonstrably trading via
  same-archive klines throughout): CTKUSDT 2024-06-26..07-08 (13 d) and
  2024-07-16..2025-04-29 (~288 d); CVXUSDT 2024-06-26..07-08 (13 d) and
  2024-07-16..2025-07-22 (372 d); LITUSDT 2025-06-06..2025-12-22 (200 d);
  MAVIAUSDT 2025-03-11..03-25 (15 d); NEARUSDT 2023-12-18 (1 d, re-verified
  with neighbors present); SUIUSDT 2023-12-13 (1 d, re-verified). Monthly
  klines exist for every long-gap month and daily klines for every sampled
  short-gap day, so these are metrics-publication gaps, not delistings
  (all six tradeable before, during per klines, and after; all TRADING now).
- **Present and complete**: all other probed daily files (29-symbol panel:
  2 missing of ~44,000 day-probes; month-grid: 0 missing months outside the
  four drilled symbols).
- **Present with intraday gap**: BTCUSDT-metrics-2021-12-15 holds 287 of 288
  expected 5 m rows (single missing 19:05 bar; neighbors present). File-level
  presence therefore slightly overstates intraday completeness — full
  intraday validation is required before any future use.
- **Lifecycle boundary (not a gap)**: each symbol's pre-first-file period
  (bulk first-file date 2021-12-01 = dataset launch for then-listed contracts;
  BTCUSDT 2020-09-01; newer listings dated by their listing, e.g.
  MARSCOINUSDT 2026-09-01, PONSUSDT 2026-09-06, TRADOORUSDT 2025-09-19).
  No post-delisting tail is observable (delisted contracts leave
  exchangeInfo; last file for all 522 is 2026-09-25, i.e. T+1 daily cadence).
- **Unavailable**: `liquidationSnapshot` for every symbol (no verifiable
  path); metrics for the 5 CJK-named recent listings (listed now, nothing
  published); empty-vs-events distinction for liquidation files is moot —
  there are no files to classify.

## D. Checksum verification (6 files, all PASS)

| Symbol | Dataset | Date/sample | File | Checksum sidecar | Checksum result | Parse result | Rows/events | First timestamp | Last timestamp |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | metrics | 2021-12-15 | BTCUSDT-metrics-2021-12-15.zip (14773 B) | same-folder .CHECKSUM (97 B, `sha256  filename` format) | True (hashlib sha256) | clean (`testzip()` None), 8-col header as §A | 287 data rows (1 intraday bar missing) | 2021-12-15 00:00:00 | 2021-12-15 23:55:00 |
| ETHUSDT | metrics | 2025-06-15 | ETHUSDT-metrics-2025-06-15.zip (11658 B) | .CHECKSUM (97 B) | True | clean, 8-col header | 288 data rows | 2025-06-15 00:00:00 | 2025-06-15 23:55:00 |
| SOLUSDT | metrics (large alt) | 2026-09-20 | SOLUSDT-metrics-2026-09-20.zip (11283 B) | .CHECKSUM (97 B) | True | clean, 8-col header | 288 data rows | 2026-09-20 00:10:00 | 2026-09-20 22:25:00 |
| SUIUSDT | metrics (mid) | 2026-09-20 | SUIUSDT-metrics-2026-09-20.zip (11744 B) | .CHECKSUM (97 B) | True | clean, 8-col header | 288 data rows | 2026-09-20 00:35:00 | 2026-09-20 23:45:00 |
| MARSCOINUSDT | metrics (new/short) | 2026-09-20 | MARSCOINUSDT-metrics-2026-09-20.zip (11464 B) | .CHECKSUM (102 B) | True | clean, 8-col header | 288 data rows | 2026-09-20 00:05:00 | 2026-09-20 23:45:00 |
| BTCUSDT | fundingRate | 2026-08 (monthly) | BTCUSDT-fundingRate-2026-08.zip (896 B) | .CHECKSUM | True | clean, 3-col header (`calc_time,funding_interval_hours,last_funding_rate`) | 93 rows (= 31 d × 3/day, complete) | 1785542400001 ms | 1788192000001 ms |

Sample zips were downloaded to the auditor's temp workspace (outside the
repo) — no archive data was written into the project. No directory listing
was treated as proof of integrity: every sampled file was downloaded,
checksummed, decompressed, and parsed.

## E. Common-window analysis

Four-way (OI-metrics + liquidationSnapshot + funding + price): **no symbol
has all four** — liquidationSnapshot is unpublished, so the common window is
empty for every symbol (0 continuous common days, no internal gaps to report,
no lifecycle limitation applicable).

Three-way context (archive OI-metrics ∩ internal funding ∩ internal price;
funding/price per the already-audited internal coverage — BTC/ETH only):

| Symbol | Common start | Common end | Continuous days | Internal gaps | Lifecycle limits |
|---|---|---|---|---|---|
| BTCUSDT | 2025-10-28 | 2026-09-25 | 333 | none (metrics panel-exhaustive, funding/price 0 gaps) | none in window |
| ETHUSDT | 2025-10-28 | 2026-09-25 | 333 | none (same verification) | none in window |
| all others | — | — | 0 | no internal funding/price coverage | — |

Daily alignment validation (audit check only — no signal constructed):
metrics filename dates align deterministically with internal UTC dates (5
parsed samples: every row's `create_time` falls inside its advertised daily
partition, 0 duplicated timestamps, 0 negative OI, consistent `SYMBOL` column
within each file). Archive fundingRate monthly sample: 93 rows = 31 d × 3/day
with `calc_time` spanning 2026-08-01 00:00–2026-08-31 16:00 UTC — inside the
advertised month, 8 h grid, no out-of-partition rows. No timezone/date-boundary
shift, duplicated date, or inconsistent date label was observed in any parsed
sample. Filename↔content agreement for day-level presence was verified by
download for the 6 checksum samples; presence-only (HEAD) findings assert
existence, not content.

## F. Required factual summary

```text
- N symbols have ≥90 days of full (OI-metrics + liquidationSnapshot +
  funding + price) coverage: 0 symbols have ≥90 days of full coverage: []
- N symbols have ≥180 days: 0 symbols have ≥180 days: []
- Largest common overlapping window across all covered symbols: none — no symbol has all four evidence types (liquidationSnapshot is unpublished); three-way (metrics+funding+price) max is 2025-10-28..2026-09-25 (333d, BTCUSDT + ETHUSDT only)
- Confirmed granularity: OI-metrics = daily, liquidationSnapshot =
  [verified format]
```

Correction to that template line, required by the verified schema: OI-metrics
are **not** daily aggregates — confirmed granularity is **5-minute state rows
in UTC-daily partitions (288 rows/day)**, and liquidationSnapshot has **no
verifiable format (dataset UNAVAILABLE)**. Any future hypothesis using the
metrics source would need to respect the 5-minute-row/daily-partition
information boundary. (That hypothesis is not designed here.)

- Symbols where metrics exist but liquidationSnapshot doesn't, or vice
  versa: metrics-without-liquidation = all 522 metrics symbols (listed in
  §B table); liquidation-without-metrics = none (no liquidation files exist
  anywhere verifiable).
- Threshold cross-cuts: metrics span ≥90 d but liquidation insufficient =
  516 symbols (507 FULL-verified + 6 PARTIAL with exact enumerated gaps + 3
  UNVERIFIED bounds-only; liquidation is absent for every one of them);
  liquidationSnapshot ≥90 d but metrics insufficient = none; apparent gaps
  proven lifecycle-related = none (all six PARTIAL cases are genuine
  publication gaps with the contract trading throughout; pre-listing periods
  are boundaries, not gaps).

Also include:

- Internal collector audit baseline: 0 symbols ≥90 days of full
  OI + liquidation + funding + price coverage.
- Public Binance archive result: 0 symbols ≥90 days.
- Difference: the archive radically improves three of the four legs —
  OI-metrics exist for 522 symbols (507 with FULL spans ≥90 d, 491 ≥180 d,
  10.4 h → multi-year coverage; deepest BTCUSDT 2020-09-01..2026-09-25),
  archive fundingRate (monthly, 8 h rows) and klines exist per symbol — but
  the liquidation leg is absent in both sources (internal: raw but 1.77 h
  thin; archive: unpublished), and internal funding/price cover BTC/ETH
  only. So the binding constraint moved from "everything is short" to
  "liquidation evidence is missing", with internal funding/price breadth as
  the second constraint for non-BTC/ETH symbols.

## G. Interpretation boundary

The public archive audit establishes data availability and coverage only. It does not establish predictive value, economic significance, or strategy viability.

Because OI metrics are daily-partitioned 5-minute-state data, any future hypothesis relying on this source must respect the daily information boundary. This audit does not choose the rebalance interval, holding period, signal definition, or strategy design.

## H. Archive-to-archive common window (supersedes internal-DB-limited figure in §E)

Method (same verification standard as §§A–G): for each of the 522 metrics symbols, archive `fundingRate` monthly files fully enumerated 2020-01..2026-09 (monthly files ARE the dataset, so this is exact at month resolution; September 2026 absent = incomplete month, pending, never a gap), archive `klines` 1h monthly files fully enumerated 2019-09..2026-09 (zero interior missing months across all 522 symbols) plus exact daily-file bisection for klines first/last dates, intersected with the exact metrics daily bounds and exact metrics gap catalog from §B–C. Day-level klines gaps inside present months are not exhaustively excluded (same caveat class as metrics month-grid). Common end is capped at 2026-08-31 by the funding monthly cadence (latest complete month). Pre-first periods are listing boundaries (LIFECYCLE-LIMITED context), never gaps.

Funding monthly findings: first months track listings (e.g. BTCUSDT 2020-01, ADAUSDT 2020-01, 1INCHUSDT 2020-12; newer listings dated accordingly); last complete month 2026-08 for every symbol with funding. Interior genuine funding gaps: exactly two cases — BNTUSDT 2021-05..2023-07, cross-archive-evidenced as a delist period (metrics first file 2023-08-10, klines monthly absent for sampled gap months, contract TRADING now) and classified LIFECYCLE-LIMITED; precision note: BNT funding files exist for 2021-01..04 while klines monthly for those same months are absent (archive-backfill inconsistency in early 2021, direction unknown) — the delist-period inference rests on the 2021-05..2023-07 triple-silence plus the 2023-08 resume, not on the early-2021 divergence; LITUSDT 2025-07..2025-11, genuine (klines monthly present throughout those months, contract trading) and classified PARTIAL. Klines 1h monthly: zero interior missing months for all 522 symbols.

Per-symbol common window (metrics ∩ archive-fundingRate ∩ archive-klines-1h). `Best run` = longest gap-free run; symbols with no interior gaps have a single run:

Symbol | Common start | Common end | Days | State | Gaps / notes
---|---|---|---|---|---
| 0GUSDT | 2025-09-17 | 2026-08-31 | 349 | FULL | none |
| 1000000BOBUSDT | 2025-06-05 | 2026-08-31 | 453 | FULL | none |
| 1000000MOGUSDT | 2024-11-07 | 2026-08-31 | 663 | FULL | none |
| 1000BONKUSDT | 2023-11-22 | 2026-08-31 | 1014 | FULL | none |
| 1000CATUSDT | 2024-10-21 | 2026-08-31 | 680 | FULL | none |
| 1000CHEEMSUSDT | 2024-11-25 | 2026-08-31 | 645 | FULL | none |
| 1000FLOKIUSDT | 2023-05-06 | 2026-08-31 | 1214 | FULL | none |
| 1000LUNCUSDT | 2022-09-09 | 2026-08-31 | 1453 | FULL | none |
| 1000PEPEUSDT | 2023-05-05 | 2026-08-31 | 1215 | FULL | none |
| 1000RATSUSDT | 2023-12-15 | 2026-08-31 | 991 | FULL | none |
| 1000SATSUSDT | 2023-12-12 | 2026-08-31 | 994 | FULL | none |
| 1000SHIBUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| 1000XECUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| 1INCHUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| 1MBABYDOGEUSDT | 2024-09-16 | 2026-08-31 | 715 | FULL | none |
| 2ZUSDT | 2025-10-02 | 2026-08-31 | 334 | FULL | none |
| 4USDT | 2025-10-08 | 2026-08-31 | 328 | FULL | none |
| AAVEUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ACEUSDT | 2023-12-18 | 2026-08-31 | 988 | FULL | none |
| ACHUSDT | 2023-02-22 | 2026-08-31 | 1287 | FULL | none |
| ACTUSDT | 2024-11-11 | 2026-08-31 | 659 | FULL | none |
| ACUUSDT | 2026-01-21 | 2026-08-31 | 223 | FULL | none |
| ADAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| AEROUSDT | 2024-12-04 | 2026-08-31 | 636 | FULL | none |
| AEVOUSDT | 2024-03-13 | 2026-08-31 | 902 | FULL | none |
| AGLDUSDT | 2023-07-29 | 2026-08-31 | 1130 | FULL | none |
| AGTUSDT | 2025-05-20 | 2026-08-31 | 469 | FULL | none |
| AIAUSDT | 2025-09-18 | 2026-08-31 | 348 | FULL | none |
| AIGENSYNUSDT | 2026-04-29 | 2026-08-31 | 125 | FULL | none |
| AINUSDT | 2025-07-10 | 2026-08-31 | 418 | FULL | none |
| AIOTUSDT | 2025-04-30 | 2026-08-31 | 489 | FULL | none |
| AIOUSDT | 2025-08-13 | 2026-08-31 | 384 | FULL | none |
| AIXBTUSDT | 2024-12-20 | 2026-08-31 | 620 | FULL | none |
| AKEUSDT | 2025-09-26 | 2026-08-31 | 340 | FULL | none |
| AKTUSDT | 2024-11-18 | 2026-08-31 | 652 | FULL | none |
| ALCHUSDT | 2025-01-07 | 2026-08-31 | 602 | FULL | none |
| ALGOUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ALICEUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ALLOUSDT | 2025-11-11 | 2026-08-31 | 294 | FULL | none |
| ALLUSDT | 2025-08-06 | 2026-08-31 | 391 | FULL | none |
| ALPINEUSDT | 2025-05-06 | 2026-08-31 | 483 | FULL | none |
| ALTUSDT | 2024-01-25 | 2026-08-31 | 950 | FULL | none |
| ANIMEUSDT | 2025-01-23 | 2026-08-31 | 586 | FULL | none |
| ANKRUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| APEUSDT | 2022-03-17 | 2026-08-31 | 1629 | FULL | none |
| API3USDT | 2022-02-22 | 2026-08-31 | 1652 | FULL | none |
| APRUSDT | 2025-10-23 | 2026-08-31 | 313 | FULL | none |
| APTUSDT | 2022-10-19 | 2026-08-31 | 1413 | FULL | none |
| ARBUSDT | 2023-03-23 | 2026-08-31 | 1258 | FULL | none |
| ARCUSDT | 2025-01-17 | 2026-08-31 | 592 | FULL | none |
| ARIAUSDT | 2025-09-03 | 2026-08-31 | 363 | FULL | none |
| ARKMUSDT | 2023-07-28 | 2026-08-31 | 1131 | FULL | none |
| ARKUSDT | 2023-09-19 | 2026-08-31 | 1078 | FULL | none |
| ARPAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ARUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ARXUSDT | 2026-06-23 | 2026-08-31 | 70 | FULL | none |
| ASRUSDT | 2025-05-06 | 2026-08-31 | 483 | FULL | none |
| ASTERUSDT | 2025-09-19 | 2026-08-31 | 347 | FULL | none |
| ASTRUSDT | 2023-02-14 | 2026-08-31 | 1295 | FULL | none |
| ATHUSDT | 2025-04-02 | 2026-08-31 | 517 | FULL | none |
| ATOMUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ATUSDT | 2025-10-29 | 2026-08-31 | 307 | FULL | none |
| AUCTIONUSDT | 2023-12-15 | 2026-08-31 | 991 | FULL | none |
| AUSDT | 2025-05-28 | 2026-08-31 | 461 | FULL | none |
| AVAAIUSDT | 2025-01-17 | 2026-08-31 | 592 | FULL | none |
| AVAUSDT | 2024-12-13 | 2026-08-31 | 627 | FULL | none |
| AVAXUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| AVNTUSDT | 2025-09-09 | 2026-08-31 | 357 | FULL | none |
| AWEUSDT | 2025-05-21 | 2026-08-31 | 468 | FULL | none |
| AXLUSDT | 2024-03-01 | 2026-08-31 | 914 | FULL | none |
| AXSUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| AZTECUSDT | 2026-02-11 | 2026-08-31 | 202 | FULL | none |
| B2USDT | 2025-05-06 | 2026-08-31 | 483 | FULL | none |
| BABYUSDT | 2025-04-05 | 2026-08-31 | 514 | FULL | none |
| BANANAS31USDT | 2025-03-22 | 2026-08-31 | 528 | FULL | none |
| BANANAUSDT | 2024-08-15 | 2026-08-31 | 747 | FULL | none |
| BANDUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| BANKUSDT | 2025-04-18 | 2026-08-31 | 501 | FULL | none |
| BANUSDT | 2024-11-18 | 2026-08-31 | 652 | FULL | none |
| BARDUSDT | 2025-09-18 | 2026-08-31 | 348 | FULL | none |
| BASEDUSDT | 2026-03-30 | 2026-08-31 | 155 | FULL | none |
| BASUSDT | 2025-08-26 | 2026-08-31 | 371 | FULL | none |
| BATUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| BBUSDT | 2024-05-13 | 2026-08-31 | 841 | FULL | none |
| BCHUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| BEAMXUSDT | 2023-11-17 | 2026-08-31 | 1019 | FULL | none |
| BEATUSDT | 2025-11-12 | 2026-08-31 | 293 | FULL | none |
| BELUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| BERAUSDT | 2025-02-06 | 2026-08-31 | 572 | FULL | none |
| BICOUSDT | 2023-09-28 | 2026-08-31 | 1069 | FULL | none |
| BIGTIMEUSDT | 2023-10-12 | 2026-08-31 | 1055 | FULL | none |
| BILLUSDT | 2026-05-07 | 2026-08-31 | 117 | FULL | none |
| BIOUSDT | 2025-01-03 | 2026-08-31 | 606 | FULL | none |
| BIRBUSDT | 2026-01-29 | 2026-08-31 | 215 | FULL | none |
| BLESSUSDT | 2025-09-23 | 2026-08-31 | 343 | FULL | none |
| BLUAIUSDT | 2025-10-21 | 2026-08-31 | 315 | FULL | none |
| BLURUSDT | 2023-04-28 | 2026-08-31 | 1222 | FULL | none |
| BMTUSDT | 2025-03-17 | 2026-08-31 | 533 | FULL | none |
| BNBUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| BNTUSDT | 2023-08-10 | 2026-08-31 | 1118 | FULL | none |
| BOMEUSDT | 2024-03-16 | 2026-08-31 | 899 | FULL | none |
| BRETTUSDT | 2024-08-20 | 2026-08-31 | 742 | FULL | none |
| BREVUSDT | 2025-12-30 | 2026-08-31 | 245 | FULL | none |
| BROCCOLI714USDT | 2025-03-21 | 2026-08-31 | 529 | FULL | none |
| BROCCOLIF3BUSDT | 2025-03-21 | 2026-08-31 | 529 | FULL | none |
| BRUSDT | 2025-03-21 | 2026-08-31 | 529 | FULL | none |
| BSBUSDT | 2026-03-25 | 2026-08-31 | 160 | FULL | none |
| BSVUSDT | 2023-10-20 | 2026-08-31 | 1047 | FULL | none |
| BTCDOMUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| BTCUSDT | 2020-09-01 | 2026-08-31 | 2191 | FULL | none |
| BTRUSDT | 2025-08-27 | 2026-08-31 | 370 | FULL | none |
| BTWUSDT | 2026-06-04 | 2026-08-31 | 89 | FULL | none |
| BULLAUSDT | 2025-07-04 | 2026-08-31 | 424 | FULL | none |
| BUSDT | 2025-05-22 | 2026-08-31 | 467 | FULL | none |
| C98USDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CAKEUSDT | 2023-11-02 | 2026-08-31 | 1034 | FULL | none |
| CAPUSDT | 2026-06-27 | 2026-08-31 | 66 | FULL | none |
| CARVUSDT | 2025-08-07 | 2026-08-31 | 390 | FULL | none |
| CATIUSDT | 2024-09-20 | 2026-08-31 | 711 | FULL | none |
| CCUSDT | 2025-10-31 | 2026-08-31 | 305 | FULL | none |
| CELOUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CELRUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CETUSUSDT | 2024-11-06 | 2026-08-31 | 664 | FULL | none |
| CFGUSDT | 2026-03-16 | 2026-08-31 | 169 | FULL | none |
| CFXUSDT | 2023-02-20 | 2026-08-31 | 1289 | FULL | none |
| CGPTUSDT | 2024-12-20 | 2026-08-31 | 620 | FULL | none |
| CHILLGUYUSDT | 2024-11-27 | 2026-08-31 | 643 | FULL | none |
| CHIPUSDT | 2026-04-16 | 2026-08-31 | 138 | FULL | none |
| CHRUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CHZUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CKBUSDT | 2023-02-28 | 2026-08-31 | 1281 | FULL | none |
| CLANKERUSDT | 2025-11-12 | 2026-08-31 | 293 | FULL | none |
| CLOUSDT | 2025-10-14 | 2026-08-31 | 322 | FULL | none |
| COAIUSDT | 2025-09-25 | 2026-08-31 | 341 | FULL | none |
| COLLECTUSDT | 2025-12-31 | 2026-08-31 | 244 | FULL | none |
| COMPUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| COOKIEUSDT | 2025-01-07 | 2026-08-31 | 602 | FULL | none |
| COTIUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| COWUSDT | 2024-11-06 | 2026-08-31 | 664 | FULL | none |
| CROSSUSDT | 2025-07-10 | 2026-08-31 | 418 | FULL | none |
| CRVUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CTKUSDT | 2021-12-01 | 2024-06-25 | 938 | PARTIAL | PARTIAL gaps: 2024-06-26..2024-07-08; 2024-07-16..2025-04-29 |
| CTRUSDT | 2026-05-28 | 2026-08-31 | 96 | FULL | none |
| CTSIUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| CUSDT | 2025-07-15 | 2026-08-31 | 413 | FULL | none |
| CVCUSDT | 2025-05-16 | 2026-08-31 | 473 | FULL | none |
| CVXUSDT | 2022-09-22 | 2024-06-25 | 643 | PARTIAL | PARTIAL gaps: 2024-06-26..2024-07-08; 2024-07-16..2025-07-22 |
| CYBERUSDT | 2023-08-21 | 2026-08-31 | 1107 | FULL | none |
| CYSUSDT | 2025-12-12 | 2026-08-31 | 263 | FULL | none |
| DASHUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| DATAIPUSDT | 2026-07-03 | 2026-08-31 | 60 | FULL | none |
| DEEPUSDT | 2025-04-22 | 2026-08-31 | 497 | FULL | none |
| DEXEUSDT | 2024-12-24 | 2026-08-31 | 616 | FULL | none |
| DIAUSDT | 2024-10-02 | 2026-08-31 | 699 | FULL | none |
| DODOXUSDT | 2023-08-08 | 2026-08-31 | 1120 | FULL | none |
| DOGEUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| DOGSUSDT | 2024-08-26 | 2026-08-31 | 736 | FULL | none |
| DOLOUSDT | 2025-05-01 | 2026-08-31 | 488 | FULL | none |
| DOODUSDT | 2025-05-09 | 2026-08-31 | 480 | FULL | none |
| DOSUSDT | 2026-08-11 | 2026-08-31 | 21 | FULL | none |
| DOTUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| DRIFTUSDT | 2024-11-08 | 2026-08-31 | 662 | FULL | none |
| DUSKUSDT | 2022-01-07 | 2026-08-31 | 1698 | FULL | none |
| DYDXUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| DYMUSDT | 2024-02-07 | 2026-08-31 | 937 | FULL | none |
| EDENUSDT | 2025-09-30 | 2026-08-31 | 336 | FULL | none |
| EDGEUSDT | 2026-03-19 | 2026-08-31 | 166 | FULL | none |
| EDUUSDT | 2023-04-30 | 2026-08-31 | 1220 | FULL | none |
| EGLDUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| EIGENUSDT | 2024-10-01 | 2026-08-31 | 700 | FULL | none |
| ELSAUSDT | 2026-01-22 | 2026-08-31 | 222 | FULL | none |
| ENAUSDT | 2024-04-02 | 2026-08-31 | 882 | FULL | none |
| ENJUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ENSOUSDT | 2025-10-14 | 2026-08-31 | 322 | FULL | none |
| ENSUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| EPICUSDT | 2025-03-13 | 2026-08-31 | 537 | FULL | none |
| ERAUSDT | 2025-07-17 | 2026-08-31 | 411 | FULL | none |
| ESPORTSUSDT | 2025-07-29 | 2026-08-31 | 399 | FULL | none |
| ESPUSDT | 2026-02-10 | 2026-08-31 | 203 | FULL | none |
| ETCUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ETHFIUSDT | 2024-03-18 | 2026-08-31 | 897 | FULL | none |
| ETHUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ETHWUSDT | 2023-11-28 | 2026-08-31 | 1008 | FULL | none |
| EULUSDT | 2025-10-13 | 2026-08-31 | 323 | FULL | none |
| EVAAUSDT | 2025-10-03 | 2026-08-31 | 333 | FULL | none |
| FARTCOINUSDT | 2024-12-20 | 2026-08-31 | 620 | FULL | none |
| FETUSDT | 2023-01-17 | 2026-08-31 | 1323 | FULL | none |
| FFUSDT | 2025-09-29 | 2026-08-31 | 337 | FULL | none |
| FHEUSDT | 2025-04-12 | 2026-08-31 | 507 | FULL | none |
| FIDAUSDT | 2024-09-19 | 2026-08-31 | 712 | FULL | none |
| FIGHTUSDT | 2026-01-23 | 2026-08-31 | 221 | FULL | none |
| FILUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| FLOCKUSDT | 2025-09-09 | 2026-08-31 | 357 | FULL | none |
| FLOWUSDT | 2022-02-10 | 2026-08-31 | 1664 | FULL | none |
| FLUIDUSDT | 2025-09-24 | 2026-08-31 | 342 | FULL | none |
| FLUXUSDT | 2024-09-03 | 2026-08-31 | 728 | FULL | none |
| FOGOUSDT | 2026-01-10 | 2026-08-31 | 234 | FULL | none |
| FOLKSUSDT | 2025-11-06 | 2026-08-31 | 299 | FULL | none |
| FORMUSDT | 2025-03-19 | 2026-08-31 | 531 | FULL | none |
| FRAXUSDT | 2026-01-15 | 2026-08-31 | 229 | FULL | none |
| FUSDT | 2025-06-18 | 2026-08-31 | 440 | FULL | none |
| GALAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| GASUSDT | 2023-10-25 | 2026-08-31 | 1042 | FULL | none |
| GENIUSUSDT | 2026-04-16 | 2026-08-31 | 138 | FULL | none |
| GIGGLEUSDT | 2025-10-09 | 2026-08-31 | 327 | FULL | none |
| GLMUSDT | 2024-02-22 | 2026-08-31 | 922 | FULL | none |
| GMTUSDT | 2022-03-15 | 2026-08-31 | 1631 | FULL | none |
| GMXUSDT | 2023-02-17 | 2026-08-31 | 1292 | FULL | none |
| GOATUSDT | 2024-10-24 | 2026-08-31 | 677 | FULL | none |
| GPSUSDT | 2025-02-17 | 2026-08-31 | 561 | FULL | none |
| GRAMUSDT | 2026-07-02 | 2026-08-31 | 61 | FULL | none |
| GRASSUSDT | 2024-11-08 | 2026-08-31 | 662 | FULL | none |
| GRIFFAINUSDT | 2025-01-02 | 2026-08-31 | 607 | FULL | none |
| GRTUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| GRVTUSDT | 2026-07-31 | 2026-08-31 | 32 | FULL | none |
| GTCUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| GUAUSDT | 2025-12-21 | 2026-08-31 | 254 | FULL | none |
| GUNUSDT | 2025-03-31 | 2026-08-31 | 519 | FULL | none |
| GUSDT | 2024-08-15 | 2026-08-31 | 747 | FULL | none |
| GWEIUSDT | 2026-01-29 | 2026-08-31 | 215 | FULL | none |
| HAEDALUSDT | 2025-05-01 | 2026-08-31 | 488 | FULL | none |
| HANAUSDT | 2025-09-26 | 2026-08-31 | 340 | FULL | none |
| HBARUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| HEIUSDT | 2025-02-13 | 2026-08-31 | 565 | FULL | none |
| HEMIUSDT | 2025-08-29 | 2026-08-31 | 368 | FULL | none |
| HIVEUSDT | 2024-12-23 | 2026-08-31 | 617 | FULL | none |
| HMSTRUSDT | 2024-09-26 | 2026-08-31 | 705 | FULL | none |
| HOLOUSDT | 2025-09-11 | 2026-08-31 | 355 | FULL | none |
| HOMEUSDT | 2025-06-10 | 2026-08-31 | 448 | FULL | none |
| HOTUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| HUMAUSDT | 2025-05-26 | 2026-08-31 | 463 | FULL | none |
| HUSDT | 2025-06-25 | 2026-08-31 | 433 | FULL | none |
| HYPERUSDT | 2025-04-22 | 2026-08-31 | 497 | FULL | none |
| HYPEUSDT | 2025-05-30 | 2026-08-31 | 459 | FULL | none |
| ICNTUSDT | 2025-07-03 | 2026-08-31 | 425 | FULL | none |
| ICPUSDT | 2022-09-27 | 2026-08-31 | 1435 | FULL | none |
| IDOLUSDT | 2025-07-04 | 2026-08-31 | 424 | FULL | none |
| IDUSDT | 2023-03-23 | 2026-08-31 | 1258 | FULL | none |
| ILVUSDT | 2023-11-10 | 2026-08-31 | 1026 | FULL | none |
| IMXUSDT | 2022-02-11 | 2026-08-31 | 1663 | FULL | none |
| INITUSDT | 2025-04-16 | 2026-08-31 | 503 | FULL | none |
| INJUSDT | 2022-08-17 | 2026-08-31 | 1476 | FULL | none |
| INUSDT | 2025-08-07 | 2026-08-31 | 390 | FULL | none |
| INXUSDT | 2026-01-30 | 2026-08-31 | 214 | FULL | none |
| IOSTUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| IOTAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| IOTXUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| IOUSDT | 2024-06-11 | 2026-08-31 | 812 | FULL | none |
| IRYSUSDT | 2025-11-26 | 2026-08-31 | 279 | FULL | none |
| JASMYUSDT | 2022-04-20 | 2026-08-31 | 1595 | FULL | none |
| JCTUSDT | 2025-11-10 | 2026-08-31 | 295 | FULL | none |
| JELLYJELLYUSDT | 2025-03-26 | 2026-08-31 | 524 | FULL | none |
| JOEUSDT | 2023-03-29 | 2026-08-31 | 1252 | FULL | none |
| JSTUSDT | 2025-04-28 | 2026-08-31 | 491 | FULL | none |
| JTOUSDT | 2023-12-08 | 2026-08-31 | 998 | FULL | none |
| JUPUSDT | 2024-02-01 | 2026-08-31 | 943 | FULL | none |
| KAIAUSDT | 2024-12-04 | 2026-08-31 | 636 | FULL | none |
| KAITOUSDT | 2025-02-20 | 2026-08-31 | 558 | FULL | none |
| KASUSDT | 2023-11-17 | 2026-08-31 | 1019 | FULL | none |
| KATUSDT | 2026-03-02 | 2026-08-31 | 183 | FULL | none |
| KAVAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| KERNELUSDT | 2025-04-14 | 2026-08-31 | 505 | FULL | none |
| KGENUSDT | 2025-10-07 | 2026-08-31 | 329 | FULL | none |
| KITEUSDT | 2025-10-29 | 2026-08-31 | 307 | FULL | none |
| KMNOUSDT | 2024-12-20 | 2026-08-31 | 620 | FULL | none |
| KNCUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| KOMAUSDT | 2024-12-10 | 2026-08-31 | 630 | FULL | none |
| KSMUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| LABUSDT | 2025-10-17 | 2026-08-31 | 319 | FULL | none |
| LAUSDT | 2025-06-05 | 2026-08-31 | 453 | FULL | none |
| LAYERUSDT | 2025-02-11 | 2026-08-31 | 567 | FULL | none |
| LDOUSDT | 2022-09-22 | 2026-08-31 | 1440 | FULL | none |
| LIGHTUSDT | 2025-09-27 | 2026-08-31 | 339 | FULL | none |
| LINEAUSDT | 2025-09-01 | 2026-08-31 | 365 | FULL | none |
| LINKUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| LISTAUSDT | 2024-06-20 | 2026-08-31 | 803 | FULL | none |
| LITUSDT | 2021-12-01 | 2025-06-05 | 1283 | PARTIAL | PARTIAL gaps: 2025-06-06..2025-12-22; 2025-07-01..2025-11-30 |
| LPTUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| LQTYUSDT | 2023-03-10 | 2026-08-31 | 1271 | FULL | none |
| LSKUSDT | 2024-01-25 | 2026-08-31 | 950 | FULL | none |
| LTCUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| LUMIAUSDT | 2024-12-18 | 2026-08-31 | 622 | FULL | none |
| LUNA2USDT | 2022-09-10 | 2026-08-31 | 1452 | FULL | none |
| LYNUSDT | 2025-10-06 | 2026-08-31 | 330 | FULL | none |
| MAGICUSDT | 2023-01-25 | 2026-08-31 | 1315 | FULL | none |
| MAGMAUSDT | 2025-12-31 | 2026-08-31 | 244 | FULL | none |
| MANAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| MANTAUSDT | 2024-01-18 | 2026-08-31 | 957 | FULL | none |
| MANTRAUSDT | 2026-03-04 | 2026-08-31 | 181 | FULL | none |
| MARSCOINUSDT | — | — | 0 | UNAVAILABLE | no fundingRate months at all |
| MASKUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| MAVIAUSDT | 2025-03-26 | 2026-08-31 | 524 | PARTIAL | PARTIAL gaps: 2025-03-11..2025-03-25 |
| MAVUSDT | 2023-06-29 | 2026-08-31 | 1160 | FULL | none |
| MEGAUSDT | 2026-01-30 | 2026-08-31 | 214 | FULL | none |
| MELANIAUSDT | 2025-01-20 | 2026-08-31 | 589 | FULL | none |
| MEMEUSDT | 2023-11-03 | 2026-08-31 | 1033 | FULL | none |
| MERLUSDT | 2025-05-29 | 2026-08-31 | 460 | FULL | none |
| METISUSDT | 2024-03-12 | 2026-08-31 | 903 | FULL | none |
| METUSDT | 2025-10-11 | 2026-08-31 | 325 | FULL | none |
| MEUSDT | 2024-12-10 | 2026-08-31 | 630 | FULL | none |
| MEWUSDT | 2024-06-17 | 2026-08-31 | 806 | FULL | none |
| MINAUSDT | 2023-02-06 | 2026-08-31 | 1303 | FULL | none |
| MIRAUSDT | 2025-09-26 | 2026-08-31 | 340 | FULL | none |
| MITOUSDT | 2025-08-28 | 2026-08-31 | 369 | FULL | none |
| MMTUSDT | 2025-11-04 | 2026-08-31 | 301 | FULL | none |
| MOCAUSDT | 2024-12-16 | 2026-08-31 | 624 | FULL | none |
| MONUSDT | 2025-10-10 | 2026-08-31 | 326 | FULL | none |
| MOODENGUSDT | 2024-10-25 | 2026-08-31 | 676 | FULL | none |
| MORPHOUSDT | 2024-11-27 | 2026-08-31 | 643 | FULL | none |
| MOVEUSDT | 2024-12-09 | 2026-08-31 | 631 | FULL | none |
| MOVRUSDT | 2023-12-26 | 2026-08-31 | 980 | FULL | none |
| MTLUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| MUBARAKUSDT | 2025-03-17 | 2026-08-31 | 533 | FULL | none |
| MUSDT | 2025-07-07 | 2026-08-31 | 421 | FULL | none |
| MYXUSDT | 2025-06-18 | 2026-08-31 | 440 | FULL | none |
| NAORISUSDT | 2025-07-31 | 2026-08-31 | 397 | FULL | none |
| NEARUSDT | 2023-12-19 | 2026-08-31 | 987 | PARTIAL | PARTIAL gaps: 2023-12-18..2023-12-18 |
| NEIROUSDT | 2024-09-16 | 2026-08-31 | 715 | FULL | none |
| NEOUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| NEWTUSDT | 2025-06-19 | 2026-08-31 | 439 | FULL | none |
| NIGHTUSDT | 2025-12-10 | 2026-08-31 | 265 | FULL | none |
| NILUSDT | 2025-03-24 | 2026-08-31 | 526 | FULL | none |
| NMRUSDT | 2023-06-22 | 2026-08-31 | 1167 | FULL | none |
| NOMUSDT | 2025-10-01 | 2026-08-31 | 335 | FULL | none |
| NOTUSDT | 2024-05-16 | 2026-08-31 | 838 | FULL | none |
| NXPCUSDT | 2025-05-15 | 2026-08-31 | 474 | FULL | none |
| OGNUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| OGUSDT | 2025-05-12 | 2026-08-31 | 477 | FULL | none |
| ONDOUSDT | 2024-01-20 | 2026-08-31 | 955 | FULL | none |
| ONEUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ONGUSDT | 2023-11-27 | 2026-08-31 | 1009 | FULL | none |
| ONTUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ONUSDT | 2025-10-24 | 2026-08-31 | 312 | FULL | none |
| OPENUSDT | 2025-09-08 | 2026-08-31 | 358 | FULL | none |
| OPGUSDT | 2026-04-22 | 2026-08-31 | 132 | FULL | none |
| OPNUSDT | 2026-02-21 | 2026-08-31 | 192 | FULL | none |
| OPUSDT | 2022-06-01 | 2026-08-31 | 1553 | FULL | none |
| ORCAUSDT | 2024-12-06 | 2026-08-31 | 634 | FULL | none |
| ORDERUSDT | 2025-09-26 | 2026-08-31 | 340 | FULL | none |
| ORDIUSDT | 2023-11-07 | 2026-08-31 | 1029 | FULL | none |
| OUSDT | 2026-06-24 | 2026-08-31 | 69 | FULL | none |
| PARTIUSDT | 2025-03-25 | 2026-08-31 | 525 | FULL | none |
| PAXGUSDT | 2025-03-27 | 2026-08-31 | 523 | FULL | none |
| PENDLEUSDT | 2023-07-28 | 2026-08-31 | 1131 | FULL | none |
| PENGUUSDT | 2024-12-17 | 2026-08-31 | 623 | FULL | none |
| PEOPLEUSDT | 2021-12-24 | 2026-08-31 | 1712 | FULL | none |
| PHAROSUSDT | 2026-05-14 | 2026-08-31 | 110 | FULL | none |
| PHAUSDT | 2024-12-30 | 2026-08-31 | 610 | FULL | none |
| PIEVERSEUSDT | 2025-11-14 | 2026-08-31 | 291 | FULL | none |
| PIPPINUSDT | 2025-01-24 | 2026-08-31 | 585 | FULL | none |
| PIXELUSDT | 2024-02-19 | 2026-08-31 | 925 | FULL | none |
| PLAYUSDT | 2025-07-31 | 2026-08-31 | 397 | FULL | none |
| PLUMEUSDT | 2025-03-21 | 2026-08-31 | 529 | FULL | none |
| PNUTUSDT | 2024-11-11 | 2026-08-31 | 659 | FULL | none |
| POLUSDT | 2024-09-13 | 2026-08-31 | 718 | FULL | none |
| POLYXUSDT | 2023-10-25 | 2026-08-31 | 1042 | FULL | none |
| PONSUSDT | — | — | 0 | UNAVAILABLE | no fundingRate months at all |
| POPCATUSDT | 2024-08-22 | 2026-08-31 | 740 | FULL | none |
| PORTALUSDT | 2024-02-29 | 2026-08-31 | 915 | FULL | none |
| POWERUSDT | 2025-12-06 | 2026-08-31 | 269 | FULL | none |
| POWRUSDT | 2023-10-27 | 2026-08-31 | 1040 | FULL | none |
| PRLUSDT | 2026-04-01 | 2026-08-31 | 153 | FULL | none |
| PROMPTUSDT | 2025-04-11 | 2026-08-31 | 508 | FULL | none |
| PROMUSDT | 2025-01-15 | 2026-08-31 | 594 | FULL | none |
| PROVEUSDT | 2025-08-05 | 2026-08-31 | 392 | FULL | none |
| PTBUSDT | 2025-09-03 | 2026-08-31 | 363 | FULL | none |
| PUMPBTCUSDT | 2025-06-13 | 2026-08-31 | 445 | FULL | none |
| PUMPUSDT | 2025-04-12 | 2026-08-31 | 507 | FULL | none |
| PUNDIXUSDT | 2025-04-30 | 2026-08-31 | 489 | FULL | none |
| PYTHUSDT | 2023-11-22 | 2026-08-31 | 1014 | FULL | none |
| QNTUSDT | 2022-10-20 | 2026-08-31 | 1412 | FULL | none |
| QTUMUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| QUSDT | 2025-09-02 | 2026-08-31 | 364 | FULL | none |
| RAREUSDT | 2024-08-15 | 2026-08-31 | 747 | FULL | none |
| RAVEUSDT | 2025-12-14 | 2026-08-31 | 261 | FULL | none |
| RAYSOLUSDT | 2024-12-10 | 2026-08-31 | 630 | FULL | none |
| RECALLUSDT | 2025-10-15 | 2026-08-31 | 321 | FULL | none |
| REDUSDT | 2025-03-06 | 2026-08-31 | 544 | FULL | none |
| RENDERUSDT | 2024-07-26 | 2026-08-31 | 767 | FULL | none |
| RESOLVUSDT | 2025-06-10 | 2026-08-31 | 448 | FULL | none |
| REUSDT | 2026-06-18 | 2026-08-31 | 75 | FULL | none |
| REZUSDT | 2024-04-30 | 2026-08-31 | 854 | FULL | none |
| RIFUSDT | 2023-10-21 | 2026-08-31 | 1046 | FULL | none |
| RIVERUSDT | 2025-10-17 | 2026-08-31 | 319 | FULL | none |
| RLCUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ROBOUSDT | 2026-02-27 | 2026-08-31 | 186 | FULL | none |
| RONINUSDT | 2024-02-06 | 2026-08-31 | 938 | FULL | none |
| ROSEUSDT | 2021-12-31 | 2026-08-31 | 1705 | FULL | none |
| RPLUSDT | 2024-09-09 | 2026-08-31 | 722 | FULL | none |
| RSRUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| RUNEUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| RVNUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SAFEUSDT | 2024-10-25 | 2026-08-31 | 676 | FULL | none |
| SAGAUSDT | 2024-04-09 | 2026-08-31 | 875 | FULL | none |
| SAHARAUSDT | 2025-06-26 | 2026-08-31 | 432 | FULL | none |
| SANDUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SANTOSUSDT | 2024-10-28 | 2026-08-31 | 673 | FULL | none |
| SAPIENUSDT | 2025-08-20 | 2026-08-31 | 377 | FULL | none |
| SCRUSDT | 2024-10-22 | 2026-08-31 | 679 | FULL | none |
| SEIUSDT | 2023-08-17 | 2026-08-31 | 1111 | FULL | none |
| SENTUSDT | 2025-11-14 | 2026-08-31 | 291 | FULL | none |
| SFPUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SHELLUSDT | 2025-02-17 | 2026-08-31 | 561 | FULL | none |
| SIGNUSDT | 2025-04-28 | 2026-08-31 | 491 | FULL | none |
| SIRENUSDT | 2025-03-22 | 2026-08-31 | 528 | FULL | none |
| SKLUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SKRUSDT | 2026-01-22 | 2026-08-31 | 222 | FULL | none |
| SKYAIUSDT | 2025-05-13 | 2026-08-31 | 476 | FULL | none |
| SKYUSDT | 2025-09-09 | 2026-08-31 | 357 | FULL | none |
| SLPUSDT | 2025-07-23 | 2026-08-31 | 405 | FULL | none |
| SLXUSDT | 2026-06-01 | 2026-08-31 | 92 | FULL | none |
| SNXUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SOLUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SOLVUSDT | 2025-01-17 | 2026-08-31 | 592 | FULL | none |
| SOMIUSDT | 2025-08-25 | 2026-08-31 | 372 | FULL | none |
| SONICUSDT | 2025-01-08 | 2026-08-31 | 601 | FULL | none |
| SOONUSDT | 2025-05-23 | 2026-08-31 | 466 | FULL | none |
| SOPHUSDT | 2025-05-28 | 2026-08-31 | 461 | FULL | none |
| SPACEUSDT | 2026-01-23 | 2026-08-31 | 221 | FULL | none |
| SPELLUSDT | 2022-09-06 | 2026-08-31 | 1456 | FULL | none |
| SPKUSDT | 2025-06-17 | 2026-08-31 | 441 | FULL | none |
| SPORTFUNUSDT | 2026-01-16 | 2026-08-31 | 228 | FULL | none |
| SPXUSDT | 2024-12-10 | 2026-08-31 | 630 | FULL | none |
| SQDUSDT | 2025-06-11 | 2026-08-31 | 447 | FULL | none |
| SSVUSDT | 2023-02-24 | 2026-08-31 | 1285 | FULL | none |
| STABLEUSDT | 2025-11-06 | 2026-08-31 | 299 | FULL | none |
| STARUSDT | 2026-05-14 | 2026-08-31 | 110 | FULL | none |
| STBLUSDT | 2025-09-17 | 2026-08-31 | 349 | FULL | none |
| STEEMUSDT | 2023-11-08 | 2026-08-31 | 1028 | FULL | none |
| STOUSDT | 2025-04-12 | 2026-08-31 | 507 | FULL | none |
| STRKUSDT | 2024-02-20 | 2026-08-31 | 924 | FULL | none |
| STXUSDT | 2023-02-21 | 2026-08-31 | 1288 | FULL | none |
| SUIUSDT | 2023-12-14 | 2026-08-31 | 992 | PARTIAL | PARTIAL gaps: 2023-12-13..2023-12-13 |
| SUNUSDT | 2024-08-22 | 2026-08-31 | 740 | FULL | none |
| SUPERUSDT | 2023-11-26 | 2026-08-31 | 1010 | FULL | none |
| SUSDT | 2025-01-16 | 2026-08-31 | 593 | FULL | none |
| SUSHIUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| SWARMSUSDT | 2025-01-07 | 2026-08-31 | 602 | FULL | none |
| SXTUSDT | 2025-05-02 | 2026-08-31 | 487 | FULL | none |
| SYNUSDT | 2024-08-16 | 2026-08-31 | 746 | FULL | none |
| SYRUPUSDT | 2025-05-07 | 2026-08-31 | 482 | FULL | none |
| TACUSDT | 2025-07-15 | 2026-08-31 | 413 | FULL | none |
| TAGUSDT | 2025-07-25 | 2026-08-31 | 403 | FULL | none |
| TAIKOUSDT | 2025-06-11 | 2026-08-31 | 447 | FULL | none |
| TAKEUSDT | 2025-09-03 | 2026-08-31 | 363 | FULL | none |
| TAOUSDT | 2024-04-11 | 2026-08-31 | 873 | FULL | none |
| TAUSDT | 2025-07-21 | 2026-08-31 | 407 | FULL | none |
| THETAUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| THEUSDT | 2024-11-27 | 2026-08-31 | 643 | FULL | none |
| TIAUSDT | 2023-10-31 | 2026-08-31 | 1036 | FULL | none |
| TLMUSDT | 2023-03-24 | 2026-08-31 | 1257 | FULL | none |
| TNSRUSDT | 2024-04-08 | 2026-08-31 | 876 | FULL | none |
| TOSHIUSDT | 2025-09-17 | 2026-08-31 | 349 | FULL | none |
| TOWNSUSDT | 2025-08-05 | 2026-08-31 | 392 | FULL | none |
| TRADOORUSDT | 2025-09-19 | 2026-08-31 | 347 | FULL | none |
| TRBUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| TREEUSDT | 2025-07-29 | 2026-08-31 | 399 | FULL | none |
| TRIAUSDT | 2026-02-06 | 2026-08-31 | 207 | FULL | none |
| TRUMPUSDT | 2025-01-18 | 2026-08-31 | 591 | FULL | none |
| TRUSTUSDT | 2025-11-05 | 2026-08-31 | 300 | FULL | none |
| TRUTHUSDT | 2025-10-01 | 2026-08-31 | 335 | FULL | none |
| TRXUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| TSTUSDT | 2025-02-09 | 2026-08-31 | 569 | FULL | none |
| TURBOUSDT | 2024-05-30 | 2026-08-31 | 824 | FULL | none |
| TURTLEUSDT | 2025-10-22 | 2026-08-31 | 314 | FULL | none |
| TUSDT | 2023-02-01 | 2026-08-31 | 1308 | FULL | none |
| TUTUSDT | 2025-03-20 | 2026-08-31 | 530 | FULL | none |
| TWTUSDT | 2023-11-03 | 2026-08-31 | 1033 | FULL | none |
| UAIUSDT | 2025-11-06 | 2026-08-31 | 299 | FULL | none |
| UBUSDT | 2025-09-12 | 2026-08-31 | 354 | FULL | none |
| UMAUSDT | 2023-05-10 | 2026-08-31 | 1210 | FULL | none |
| UNIUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| USDCUSDT | 2023-03-12 | 2026-08-31 | 1269 | FULL | none |
| USELESSUSDT | 2025-08-15 | 2026-08-31 | 382 | FULL | none |
| USTCUSDT | 2023-11-27 | 2026-08-31 | 1009 | FULL | none |
| USUALUSDT | 2024-12-18 | 2026-08-31 | 622 | FULL | none |
| USUSDT | 2025-12-12 | 2026-08-31 | 263 | FULL | none |
| VANAUSDT | 2024-12-16 | 2026-08-31 | 624 | FULL | none |
| VELODROMEUSDT | 2024-12-13 | 2026-08-31 | 627 | FULL | none |
| VELVETUSDT | 2025-07-15 | 2026-08-31 | 413 | FULL | none |
| VETUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| VIRTUALUSDT | 2024-12-10 | 2026-08-31 | 630 | FULL | none |
| VTHOUSDT | 2025-01-22 | 2026-08-31 | 587 | FULL | none |
| VVVUSDT | 2025-01-29 | 2026-08-31 | 580 | FULL | none |
| WALUSDT | 2025-03-27 | 2026-08-31 | 523 | FULL | none |
| WAXPUSDT | 2023-10-18 | 2026-08-31 | 1049 | FULL | none |
| WCTUSDT | 2025-04-15 | 2026-08-31 | 504 | FULL | none |
| WETUSDT | 2025-12-10 | 2026-08-31 | 265 | FULL | none |
| WIFUSDT | 2024-01-18 | 2026-08-31 | 957 | FULL | none |
| WLDUSDT | 2023-07-24 | 2026-08-31 | 1135 | FULL | none |
| WLFIUSDT | 2025-08-23 | 2026-08-31 | 374 | FULL | none |
| WOOUSDT | 2022-04-08 | 2026-08-31 | 1607 | FULL | none |
| WUSDT | 2024-04-03 | 2026-08-31 | 881 | FULL | none |
| XAIUSDT | 2024-01-09 | 2026-08-31 | 966 | FULL | none |
| XANUSDT | 2025-09-29 | 2026-08-31 | 337 | FULL | none |
| XAUTUSDT | 2026-03-26 | 2026-08-31 | 159 | FULL | none |
| XLMUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| XMRUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| XNYUSDT | 2025-08-13 | 2026-08-31 | 384 | FULL | none |
| XPINUSDT | 2025-09-12 | 2026-08-31 | 354 | FULL | none |
| XPLUSDT | 2025-08-22 | 2026-08-31 | 375 | FULL | none |
| XRPUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| XTZUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| XVGUSDT | 2023-07-05 | 2026-08-31 | 1154 | FULL | none |
| XVSUSDT | 2023-04-13 | 2026-08-31 | 1237 | FULL | none |
| YBUSDT | 2025-10-10 | 2026-08-31 | 326 | FULL | none |
| YFIUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| YGGUSDT | 2023-08-05 | 2026-08-31 | 1123 | FULL | none |
| ZAMAUSDT | 2026-01-09 | 2026-08-31 | 235 | FULL | none |
| ZBTUSDT | 2025-10-17 | 2026-08-31 | 319 | FULL | none |
| ZECUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ZENUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ZEREBROUSDT | 2025-01-02 | 2026-08-31 | 607 | FULL | none |
| ZESTUSDT | 2026-06-04 | 2026-08-31 | 89 | FULL | none |
| ZETAUSDT | 2024-02-02 | 2026-08-31 | 942 | FULL | none |
| ZILUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |
| ZKCUSDT | 2025-09-15 | 2026-08-31 | 351 | FULL | none |
| ZKPUSDT | 2025-12-21 | 2026-08-31 | 254 | FULL | none |
| ZKUSDT | 2024-06-17 | 2026-08-31 | 806 | FULL | none |
| ZORAUSDT | 2025-07-25 | 2026-08-31 | 403 | FULL | none |
| ZROUSDT | 2024-06-20 | 2026-08-31 | 803 | FULL | none |
| ZRXUSDT | 2021-12-01 | 2026-08-31 | 1735 | FULL | none |

Threshold counts (longest continuous gap-free run per symbol):

- 510 symbols with ≥90 continuous days of (OI-metrics + archive-fundingRate + archive-klines) coverage
- 495 symbols with ≥180 continuous days of (OI-metrics + archive-fundingRate + archive-klines) coverage
- 397 symbols with ≥365 continuous days of (OI-metrics + archive-fundingRate + archive-klines) coverage

≥90-day list: 0GUSDT, 1000000BOBUSDT, 1000000MOGUSDT, 1000BONKUSDT, 1000CATUSDT, 1000CHEEMSUSDT, 1000FLOKIUSDT, 1000LUNCUSDT, 1000PEPEUSDT, 1000RATSUSDT, 1000SATSUSDT, 1000SHIBUSDT, 1000XECUSDT, 1INCHUSDT, 1MBABYDOGEUSDT, 2ZUSDT, 4USDT, AAVEUSDT, ACEUSDT, ACHUSDT, ACTUSDT, ACUUSDT, ADAUSDT, AEROUSDT, AEVOUSDT, AGLDUSDT, AGTUSDT, AIAUSDT, AIGENSYNUSDT, AINUSDT, AIOTUSDT, AIOUSDT, AIXBTUSDT, AKEUSDT, AKTUSDT, ALCHUSDT, ALGOUSDT, ALICEUSDT, ALLOUSDT, ALLUSDT, ALPINEUSDT, ALTUSDT, ANIMEUSDT, ANKRUSDT, APEUSDT, API3USDT, APRUSDT, APTUSDT, ARBUSDT, ARCUSDT, ARIAUSDT, ARKMUSDT, ARKUSDT, ARPAUSDT, ARUSDT, ASRUSDT, ASTERUSDT, ASTRUSDT, ATHUSDT, ATOMUSDT, ATUSDT, AUCTIONUSDT, AUSDT, AVAAIUSDT, AVAUSDT, AVAXUSDT, AVNTUSDT, AWEUSDT, AXLUSDT, AXSUSDT, AZTECUSDT, B2USDT, BABYUSDT, BANANAS31USDT, BANANAUSDT, BANDUSDT, BANKUSDT, BANUSDT, BARDUSDT, BASEDUSDT, BASUSDT, BATUSDT, BBUSDT, BCHUSDT, BEAMXUSDT, BEATUSDT, BELUSDT, BERAUSDT, BICOUSDT, BIGTIMEUSDT, BILLUSDT, BIOUSDT, BIRBUSDT, BLESSUSDT, BLUAIUSDT, BLURUSDT, BMTUSDT, BNBUSDT, BNTUSDT, BOMEUSDT, BRETTUSDT, BREVUSDT, BROCCOLI714USDT, BROCCOLIF3BUSDT, BRUSDT, BSBUSDT, BSVUSDT, BTCDOMUSDT, BTCUSDT, BTRUSDT, BULLAUSDT, BUSDT, C98USDT, CAKEUSDT, CARVUSDT, CATIUSDT, CCUSDT, CELOUSDT, CELRUSDT, CETUSUSDT, CFGUSDT, CFXUSDT, CGPTUSDT, CHILLGUYUSDT, CHIPUSDT, CHRUSDT, CHZUSDT, CKBUSDT, CLANKERUSDT, CLOUSDT, COAIUSDT, COLLECTUSDT, COMPUSDT, COOKIEUSDT, COTIUSDT, COWUSDT, CROSSUSDT, CRVUSDT, CTKUSDT, CTRUSDT, CTSIUSDT, CUSDT, CVCUSDT, CVXUSDT, CYBERUSDT, CYSUSDT, DASHUSDT, DEEPUSDT, DEXEUSDT, DIAUSDT, DODOXUSDT, DOGEUSDT, DOGSUSDT, DOLOUSDT, DOODUSDT, DOTUSDT, DRIFTUSDT, DUSKUSDT, DYDXUSDT, DYMUSDT, EDENUSDT, EDGEUSDT, EDUUSDT, EGLDUSDT, EIGENUSDT, ELSAUSDT, ENAUSDT, ENJUSDT, ENSOUSDT, ENSUSDT, EPICUSDT, ERAUSDT, ESPORTSUSDT, ESPUSDT, ETCUSDT, ETHFIUSDT, ETHUSDT, ETHWUSDT, EULUSDT, EVAAUSDT, FARTCOINUSDT, FETUSDT, FFUSDT, FHEUSDT, FIDAUSDT, FIGHTUSDT, FILUSDT, FLOCKUSDT, FLOWUSDT, FLUIDUSDT, FLUXUSDT, FOGOUSDT, FOLKSUSDT, FORMUSDT, FRAXUSDT, FUSDT, GALAUSDT, GASUSDT, GENIUSUSDT, GIGGLEUSDT, GLMUSDT, GMTUSDT, GMXUSDT, GOATUSDT, GPSUSDT, GRASSUSDT, GRIFFAINUSDT, GRTUSDT, GTCUSDT, GUAUSDT, GUNUSDT, GUSDT, GWEIUSDT, HAEDALUSDT, HANAUSDT, HBARUSDT, HEIUSDT, HEMIUSDT, HIVEUSDT, HMSTRUSDT, HOLOUSDT, HOMEUSDT, HOTUSDT, HUMAUSDT, HUSDT, HYPERUSDT, HYPEUSDT, ICNTUSDT, ICPUSDT, IDOLUSDT, IDUSDT, ILVUSDT, IMXUSDT, INITUSDT, INJUSDT, INUSDT, INXUSDT, IOSTUSDT, IOTAUSDT, IOTXUSDT, IOUSDT, IRYSUSDT, JASMYUSDT, JCTUSDT, JELLYJELLYUSDT, JOEUSDT, JSTUSDT, JTOUSDT, JUPUSDT, KAIAUSDT, KAITOUSDT, KASUSDT, KATUSDT, KAVAUSDT, KERNELUSDT, KGENUSDT, KITEUSDT, KMNOUSDT, KNCUSDT, KOMAUSDT, KSMUSDT, LABUSDT, LAUSDT, LAYERUSDT, LDOUSDT, LIGHTUSDT, LINEAUSDT, LINKUSDT, LISTAUSDT, LITUSDT, LPTUSDT, LQTYUSDT, LSKUSDT, LTCUSDT, LUMIAUSDT, LUNA2USDT, LYNUSDT, MAGICUSDT, MAGMAUSDT, MANAUSDT, MANTAUSDT, MANTRAUSDT, MASKUSDT, MAVIAUSDT, MAVUSDT, MEGAUSDT, MELANIAUSDT, MEMEUSDT, MERLUSDT, METISUSDT, METUSDT, MEUSDT, MEWUSDT, MINAUSDT, MIRAUSDT, MITOUSDT, MMTUSDT, MOCAUSDT, MONUSDT, MOODENGUSDT, MORPHOUSDT, MOVEUSDT, MOVRUSDT, MTLUSDT, MUBARAKUSDT, MUSDT, MYXUSDT, NAORISUSDT, NEARUSDT, NEIROUSDT, NEOUSDT, NEWTUSDT, NIGHTUSDT, NILUSDT, NMRUSDT, NOMUSDT, NOTUSDT, NXPCUSDT, OGNUSDT, OGUSDT, ONDOUSDT, ONEUSDT, ONGUSDT, ONTUSDT, ONUSDT, OPENUSDT, OPGUSDT, OPNUSDT, OPUSDT, ORCAUSDT, ORDERUSDT, ORDIUSDT, PARTIUSDT, PAXGUSDT, PENDLEUSDT, PENGUUSDT, PEOPLEUSDT, PHAROSUSDT, PHAUSDT, PIEVERSEUSDT, PIPPINUSDT, PIXELUSDT, PLAYUSDT, PLUMEUSDT, PNUTUSDT, POLUSDT, POLYXUSDT, POPCATUSDT, PORTALUSDT, POWERUSDT, POWRUSDT, PRLUSDT, PROMPTUSDT, PROMUSDT, PROVEUSDT, PTBUSDT, PUMPBTCUSDT, PUMPUSDT, PUNDIXUSDT, PYTHUSDT, QNTUSDT, QTUMUSDT, QUSDT, RAREUSDT, RAVEUSDT, RAYSOLUSDT, RECALLUSDT, REDUSDT, RENDERUSDT, RESOLVUSDT, REZUSDT, RIFUSDT, RIVERUSDT, RLCUSDT, ROBOUSDT, RONINUSDT, ROSEUSDT, RPLUSDT, RSRUSDT, RUNEUSDT, RVNUSDT, SAFEUSDT, SAGAUSDT, SAHARAUSDT, SANDUSDT, SANTOSUSDT, SAPIENUSDT, SCRUSDT, SEIUSDT, SENTUSDT, SFPUSDT, SHELLUSDT, SIGNUSDT, SIRENUSDT, SKLUSDT, SKRUSDT, SKYAIUSDT, SKYUSDT, SLPUSDT, SLXUSDT, SNXUSDT, SOLUSDT, SOLVUSDT, SOMIUSDT, SONICUSDT, SOONUSDT, SOPHUSDT, SPACEUSDT, SPELLUSDT, SPKUSDT, SPORTFUNUSDT, SPXUSDT, SQDUSDT, SSVUSDT, STABLEUSDT, STARUSDT, STBLUSDT, STEEMUSDT, STOUSDT, STRKUSDT, STXUSDT, SUIUSDT, SUNUSDT, SUPERUSDT, SUSDT, SUSHIUSDT, SWARMSUSDT, SXTUSDT, SYNUSDT, SYRUPUSDT, TACUSDT, TAGUSDT, TAIKOUSDT, TAKEUSDT, TAOUSDT, TAUSDT, THETAUSDT, THEUSDT, TIAUSDT, TLMUSDT, TNSRUSDT, TOSHIUSDT, TOWNSUSDT, TRADOORUSDT, TRBUSDT, TREEUSDT, TRIAUSDT, TRUMPUSDT, TRUSTUSDT, TRUTHUSDT, TRXUSDT, TSTUSDT, TURBOUSDT, TURTLEUSDT, TUSDT, TUTUSDT, TWTUSDT, UAIUSDT, UBUSDT, UMAUSDT, UNIUSDT, USDCUSDT, USELESSUSDT, USTCUSDT, USUALUSDT, USUSDT, VANAUSDT, VELODROMEUSDT, VELVETUSDT, VETUSDT, VIRTUALUSDT, VTHOUSDT, VVVUSDT, WALUSDT, WAXPUSDT, WCTUSDT, WETUSDT, WIFUSDT, WLDUSDT, WLFIUSDT, WOOUSDT, WUSDT, XAIUSDT, XANUSDT, XAUTUSDT, XLMUSDT, XMRUSDT, XNYUSDT, XPINUSDT, XPLUSDT, XRPUSDT, XTZUSDT, XVGUSDT, XVSUSDT, YBUSDT, YFIUSDT, YGGUSDT, ZAMAUSDT, ZBTUSDT, ZECUSDT, ZENUSDT, ZEREBROUSDT, ZETAUSDT, ZILUSDT, ZKCUSDT, ZKPUSDT, ZKUSDT, ZORAUSDT, ZROUSDT, ZRXUSDT

≥180-day list: 0GUSDT, 1000000BOBUSDT, 1000000MOGUSDT, 1000BONKUSDT, 1000CATUSDT, 1000CHEEMSUSDT, 1000FLOKIUSDT, 1000LUNCUSDT, 1000PEPEUSDT, 1000RATSUSDT, 1000SATSUSDT, 1000SHIBUSDT, 1000XECUSDT, 1INCHUSDT, 1MBABYDOGEUSDT, 2ZUSDT, 4USDT, AAVEUSDT, ACEUSDT, ACHUSDT, ACTUSDT, ACUUSDT, ADAUSDT, AEROUSDT, AEVOUSDT, AGLDUSDT, AGTUSDT, AIAUSDT, AINUSDT, AIOTUSDT, AIOUSDT, AIXBTUSDT, AKEUSDT, AKTUSDT, ALCHUSDT, ALGOUSDT, ALICEUSDT, ALLOUSDT, ALLUSDT, ALPINEUSDT, ALTUSDT, ANIMEUSDT, ANKRUSDT, APEUSDT, API3USDT, APRUSDT, APTUSDT, ARBUSDT, ARCUSDT, ARIAUSDT, ARKMUSDT, ARKUSDT, ARPAUSDT, ARUSDT, ASRUSDT, ASTERUSDT, ASTRUSDT, ATHUSDT, ATOMUSDT, ATUSDT, AUCTIONUSDT, AUSDT, AVAAIUSDT, AVAUSDT, AVAXUSDT, AVNTUSDT, AWEUSDT, AXLUSDT, AXSUSDT, AZTECUSDT, B2USDT, BABYUSDT, BANANAS31USDT, BANANAUSDT, BANDUSDT, BANKUSDT, BANUSDT, BARDUSDT, BASUSDT, BATUSDT, BBUSDT, BCHUSDT, BEAMXUSDT, BEATUSDT, BELUSDT, BERAUSDT, BICOUSDT, BIGTIMEUSDT, BIOUSDT, BIRBUSDT, BLESSUSDT, BLUAIUSDT, BLURUSDT, BMTUSDT, BNBUSDT, BNTUSDT, BOMEUSDT, BRETTUSDT, BREVUSDT, BROCCOLI714USDT, BROCCOLIF3BUSDT, BRUSDT, BSVUSDT, BTCDOMUSDT, BTCUSDT, BTRUSDT, BULLAUSDT, BUSDT, C98USDT, CAKEUSDT, CARVUSDT, CATIUSDT, CCUSDT, CELOUSDT, CELRUSDT, CETUSUSDT, CFXUSDT, CGPTUSDT, CHILLGUYUSDT, CHRUSDT, CHZUSDT, CKBUSDT, CLANKERUSDT, CLOUSDT, COAIUSDT, COLLECTUSDT, COMPUSDT, COOKIEUSDT, COTIUSDT, COWUSDT, CROSSUSDT, CRVUSDT, CTKUSDT, CTSIUSDT, CUSDT, CVCUSDT, CVXUSDT, CYBERUSDT, CYSUSDT, DASHUSDT, DEEPUSDT, DEXEUSDT, DIAUSDT, DODOXUSDT, DOGEUSDT, DOGSUSDT, DOLOUSDT, DOODUSDT, DOTUSDT, DRIFTUSDT, DUSKUSDT, DYDXUSDT, DYMUSDT, EDENUSDT, EDUUSDT, EGLDUSDT, EIGENUSDT, ELSAUSDT, ENAUSDT, ENJUSDT, ENSOUSDT, ENSUSDT, EPICUSDT, ERAUSDT, ESPORTSUSDT, ESPUSDT, ETCUSDT, ETHFIUSDT, ETHUSDT, ETHWUSDT, EULUSDT, EVAAUSDT, FARTCOINUSDT, FETUSDT, FFUSDT, FHEUSDT, FIDAUSDT, FIGHTUSDT, FILUSDT, FLOCKUSDT, FLOWUSDT, FLUIDUSDT, FLUXUSDT, FOGOUSDT, FOLKSUSDT, FORMUSDT, FRAXUSDT, FUSDT, GALAUSDT, GASUSDT, GIGGLEUSDT, GLMUSDT, GMTUSDT, GMXUSDT, GOATUSDT, GPSUSDT, GRASSUSDT, GRIFFAINUSDT, GRTUSDT, GTCUSDT, GUAUSDT, GUNUSDT, GUSDT, GWEIUSDT, HAEDALUSDT, HANAUSDT, HBARUSDT, HEIUSDT, HEMIUSDT, HIVEUSDT, HMSTRUSDT, HOLOUSDT, HOMEUSDT, HOTUSDT, HUMAUSDT, HUSDT, HYPERUSDT, HYPEUSDT, ICNTUSDT, ICPUSDT, IDOLUSDT, IDUSDT, ILVUSDT, IMXUSDT, INITUSDT, INJUSDT, INUSDT, INXUSDT, IOSTUSDT, IOTAUSDT, IOTXUSDT, IOUSDT, IRYSUSDT, JASMYUSDT, JCTUSDT, JELLYJELLYUSDT, JOEUSDT, JSTUSDT, JTOUSDT, JUPUSDT, KAIAUSDT, KAITOUSDT, KASUSDT, KATUSDT, KAVAUSDT, KERNELUSDT, KGENUSDT, KITEUSDT, KMNOUSDT, KNCUSDT, KOMAUSDT, KSMUSDT, LABUSDT, LAUSDT, LAYERUSDT, LDOUSDT, LIGHTUSDT, LINEAUSDT, LINKUSDT, LISTAUSDT, LITUSDT, LPTUSDT, LQTYUSDT, LSKUSDT, LTCUSDT, LUMIAUSDT, LUNA2USDT, LYNUSDT, MAGICUSDT, MAGMAUSDT, MANAUSDT, MANTAUSDT, MANTRAUSDT, MASKUSDT, MAVIAUSDT, MAVUSDT, MEGAUSDT, MELANIAUSDT, MEMEUSDT, MERLUSDT, METISUSDT, METUSDT, MEUSDT, MEWUSDT, MINAUSDT, MIRAUSDT, MITOUSDT, MMTUSDT, MOCAUSDT, MONUSDT, MOODENGUSDT, MORPHOUSDT, MOVEUSDT, MOVRUSDT, MTLUSDT, MUBARAKUSDT, MUSDT, MYXUSDT, NAORISUSDT, NEARUSDT, NEIROUSDT, NEOUSDT, NEWTUSDT, NIGHTUSDT, NILUSDT, NMRUSDT, NOMUSDT, NOTUSDT, NXPCUSDT, OGNUSDT, OGUSDT, ONDOUSDT, ONEUSDT, ONGUSDT, ONTUSDT, ONUSDT, OPENUSDT, OPNUSDT, OPUSDT, ORCAUSDT, ORDERUSDT, ORDIUSDT, PARTIUSDT, PAXGUSDT, PENDLEUSDT, PENGUUSDT, PEOPLEUSDT, PHAUSDT, PIEVERSEUSDT, PIPPINUSDT, PIXELUSDT, PLAYUSDT, PLUMEUSDT, PNUTUSDT, POLUSDT, POLYXUSDT, POPCATUSDT, PORTALUSDT, POWERUSDT, POWRUSDT, PROMPTUSDT, PROMUSDT, PROVEUSDT, PTBUSDT, PUMPBTCUSDT, PUMPUSDT, PUNDIXUSDT, PYTHUSDT, QNTUSDT, QTUMUSDT, QUSDT, RAREUSDT, RAVEUSDT, RAYSOLUSDT, RECALLUSDT, REDUSDT, RENDERUSDT, RESOLVUSDT, REZUSDT, RIFUSDT, RIVERUSDT, RLCUSDT, ROBOUSDT, RONINUSDT, ROSEUSDT, RPLUSDT, RSRUSDT, RUNEUSDT, RVNUSDT, SAFEUSDT, SAGAUSDT, SAHARAUSDT, SANDUSDT, SANTOSUSDT, SAPIENUSDT, SCRUSDT, SEIUSDT, SENTUSDT, SFPUSDT, SHELLUSDT, SIGNUSDT, SIRENUSDT, SKLUSDT, SKRUSDT, SKYAIUSDT, SKYUSDT, SLPUSDT, SNXUSDT, SOLUSDT, SOLVUSDT, SOMIUSDT, SONICUSDT, SOONUSDT, SOPHUSDT, SPACEUSDT, SPELLUSDT, SPKUSDT, SPORTFUNUSDT, SPXUSDT, SQDUSDT, SSVUSDT, STABLEUSDT, STBLUSDT, STEEMUSDT, STOUSDT, STRKUSDT, STXUSDT, SUIUSDT, SUNUSDT, SUPERUSDT, SUSDT, SUSHIUSDT, SWARMSUSDT, SXTUSDT, SYNUSDT, SYRUPUSDT, TACUSDT, TAGUSDT, TAIKOUSDT, TAKEUSDT, TAOUSDT, TAUSDT, THETAUSDT, THEUSDT, TIAUSDT, TLMUSDT, TNSRUSDT, TOSHIUSDT, TOWNSUSDT, TRADOORUSDT, TRBUSDT, TREEUSDT, TRIAUSDT, TRUMPUSDT, TRUSTUSDT, TRUTHUSDT, TRXUSDT, TSTUSDT, TURBOUSDT, TURTLEUSDT, TUSDT, TUTUSDT, TWTUSDT, UAIUSDT, UBUSDT, UMAUSDT, UNIUSDT, USDCUSDT, USELESSUSDT, USTCUSDT, USUALUSDT, USUSDT, VANAUSDT, VELODROMEUSDT, VELVETUSDT, VETUSDT, VIRTUALUSDT, VTHOUSDT, VVVUSDT, WALUSDT, WAXPUSDT, WCTUSDT, WETUSDT, WIFUSDT, WLDUSDT, WLFIUSDT, WOOUSDT, WUSDT, XAIUSDT, XANUSDT, XLMUSDT, XMRUSDT, XNYUSDT, XPINUSDT, XPLUSDT, XRPUSDT, XTZUSDT, XVGUSDT, XVSUSDT, YBUSDT, YFIUSDT, YGGUSDT, ZAMAUSDT, ZBTUSDT, ZECUSDT, ZENUSDT, ZEREBROUSDT, ZETAUSDT, ZILUSDT, ZKCUSDT, ZKPUSDT, ZKUSDT, ZORAUSDT, ZROUSDT, ZRXUSDT

≥365-day list: 1000000BOBUSDT, 1000000MOGUSDT, 1000BONKUSDT, 1000CATUSDT, 1000CHEEMSUSDT, 1000FLOKIUSDT, 1000LUNCUSDT, 1000PEPEUSDT, 1000RATSUSDT, 1000SATSUSDT, 1000SHIBUSDT, 1000XECUSDT, 1INCHUSDT, 1MBABYDOGEUSDT, AAVEUSDT, ACEUSDT, ACHUSDT, ACTUSDT, ADAUSDT, AEROUSDT, AEVOUSDT, AGLDUSDT, AGTUSDT, AINUSDT, AIOTUSDT, AIOUSDT, AIXBTUSDT, AKTUSDT, ALCHUSDT, ALGOUSDT, ALICEUSDT, ALLUSDT, ALPINEUSDT, ALTUSDT, ANIMEUSDT, ANKRUSDT, APEUSDT, API3USDT, APTUSDT, ARBUSDT, ARCUSDT, ARKMUSDT, ARKUSDT, ARPAUSDT, ARUSDT, ASRUSDT, ASTRUSDT, ATHUSDT, ATOMUSDT, AUCTIONUSDT, AUSDT, AVAAIUSDT, AVAUSDT, AVAXUSDT, AWEUSDT, AXLUSDT, AXSUSDT, B2USDT, BABYUSDT, BANANAS31USDT, BANANAUSDT, BANDUSDT, BANKUSDT, BANUSDT, BASUSDT, BATUSDT, BBUSDT, BCHUSDT, BEAMXUSDT, BELUSDT, BERAUSDT, BICOUSDT, BIGTIMEUSDT, BIOUSDT, BLURUSDT, BMTUSDT, BNBUSDT, BNTUSDT, BOMEUSDT, BRETTUSDT, BROCCOLI714USDT, BROCCOLIF3BUSDT, BRUSDT, BSVUSDT, BTCDOMUSDT, BTCUSDT, BTRUSDT, BULLAUSDT, BUSDT, C98USDT, CAKEUSDT, CARVUSDT, CATIUSDT, CELOUSDT, CELRUSDT, CETUSUSDT, CFXUSDT, CGPTUSDT, CHILLGUYUSDT, CHRUSDT, CHZUSDT, CKBUSDT, COMPUSDT, COOKIEUSDT, COTIUSDT, COWUSDT, CROSSUSDT, CRVUSDT, CTKUSDT, CTSIUSDT, CUSDT, CVCUSDT, CVXUSDT, CYBERUSDT, DASHUSDT, DEEPUSDT, DEXEUSDT, DIAUSDT, DODOXUSDT, DOGEUSDT, DOGSUSDT, DOLOUSDT, DOODUSDT, DOTUSDT, DRIFTUSDT, DUSKUSDT, DYDXUSDT, DYMUSDT, EDUUSDT, EGLDUSDT, EIGENUSDT, ENAUSDT, ENJUSDT, ENSUSDT, EPICUSDT, ERAUSDT, ESPORTSUSDT, ETCUSDT, ETHFIUSDT, ETHUSDT, ETHWUSDT, FARTCOINUSDT, FETUSDT, FHEUSDT, FIDAUSDT, FILUSDT, FLOWUSDT, FLUXUSDT, FORMUSDT, FUSDT, GALAUSDT, GASUSDT, GLMUSDT, GMTUSDT, GMXUSDT, GOATUSDT, GPSUSDT, GRASSUSDT, GRIFFAINUSDT, GRTUSDT, GTCUSDT, GUNUSDT, GUSDT, HAEDALUSDT, HBARUSDT, HEIUSDT, HEMIUSDT, HIVEUSDT, HMSTRUSDT, HOMEUSDT, HOTUSDT, HUMAUSDT, HUSDT, HYPERUSDT, HYPEUSDT, ICNTUSDT, ICPUSDT, IDOLUSDT, IDUSDT, ILVUSDT, IMXUSDT, INITUSDT, INJUSDT, INUSDT, IOSTUSDT, IOTAUSDT, IOTXUSDT, IOUSDT, JASMYUSDT, JELLYJELLYUSDT, JOEUSDT, JSTUSDT, JTOUSDT, JUPUSDT, KAIAUSDT, KAITOUSDT, KASUSDT, KAVAUSDT, KERNELUSDT, KMNOUSDT, KNCUSDT, KOMAUSDT, KSMUSDT, LAUSDT, LAYERUSDT, LDOUSDT, LINEAUSDT, LINKUSDT, LISTAUSDT, LITUSDT, LPTUSDT, LQTYUSDT, LSKUSDT, LTCUSDT, LUMIAUSDT, LUNA2USDT, MAGICUSDT, MANAUSDT, MANTAUSDT, MASKUSDT, MAVIAUSDT, MAVUSDT, MELANIAUSDT, MEMEUSDT, MERLUSDT, METISUSDT, MEUSDT, MEWUSDT, MINAUSDT, MITOUSDT, MOCAUSDT, MOODENGUSDT, MORPHOUSDT, MOVEUSDT, MOVRUSDT, MTLUSDT, MUBARAKUSDT, MUSDT, MYXUSDT, NAORISUSDT, NEARUSDT, NEIROUSDT, NEOUSDT, NEWTUSDT, NILUSDT, NMRUSDT, NOTUSDT, NXPCUSDT, OGNUSDT, OGUSDT, ONDOUSDT, ONEUSDT, ONGUSDT, ONTUSDT, OPUSDT, ORCAUSDT, ORDIUSDT, PARTIUSDT, PAXGUSDT, PENDLEUSDT, PENGUUSDT, PEOPLEUSDT, PHAUSDT, PIPPINUSDT, PIXELUSDT, PLAYUSDT, PLUMEUSDT, PNUTUSDT, POLUSDT, POLYXUSDT, POPCATUSDT, PORTALUSDT, POWRUSDT, PROMPTUSDT, PROMUSDT, PROVEUSDT, PUMPBTCUSDT, PUMPUSDT, PUNDIXUSDT, PYTHUSDT, QNTUSDT, QTUMUSDT, RAREUSDT, RAYSOLUSDT, REDUSDT, RENDERUSDT, RESOLVUSDT, REZUSDT, RIFUSDT, RLCUSDT, RONINUSDT, ROSEUSDT, RPLUSDT, RSRUSDT, RUNEUSDT, RVNUSDT, SAFEUSDT, SAGAUSDT, SAHARAUSDT, SANDUSDT, SANTOSUSDT, SAPIENUSDT, SCRUSDT, SEIUSDT, SFPUSDT, SHELLUSDT, SIGNUSDT, SIRENUSDT, SKLUSDT, SKYAIUSDT, SLPUSDT, SNXUSDT, SOLUSDT, SOLVUSDT, SOMIUSDT, SONICUSDT, SOONUSDT, SOPHUSDT, SPELLUSDT, SPKUSDT, SPXUSDT, SQDUSDT, SSVUSDT, STEEMUSDT, STOUSDT, STRKUSDT, STXUSDT, SUIUSDT, SUNUSDT, SUPERUSDT, SUSDT, SUSHIUSDT, SWARMSUSDT, SXTUSDT, SYNUSDT, SYRUPUSDT, TACUSDT, TAGUSDT, TAIKOUSDT, TAOUSDT, TAUSDT, THETAUSDT, THEUSDT, TIAUSDT, TLMUSDT, TNSRUSDT, TOWNSUSDT, TRBUSDT, TREEUSDT, TRUMPUSDT, TRXUSDT, TSTUSDT, TURBOUSDT, TUSDT, TUTUSDT, TWTUSDT, UMAUSDT, UNIUSDT, USDCUSDT, USELESSUSDT, USTCUSDT, USUALUSDT, VANAUSDT, VELODROMEUSDT, VELVETUSDT, VETUSDT, VIRTUALUSDT, VTHOUSDT, VVVUSDT, WALUSDT, WAXPUSDT, WCTUSDT, WIFUSDT, WLDUSDT, WLFIUSDT, WOOUSDT, WUSDT, XAIUSDT, XLMUSDT, XMRUSDT, XNYUSDT, XPLUSDT, XRPUSDT, XTZUSDT, XVGUSDT, XVSUSDT, YFIUSDT, YGGUSDT, ZECUSDT, ZENUSDT, ZEREBROUSDT, ZETAUSDT, ZILUSDT, ZKUSDT, ZORAUSDT, ZROUSDT, ZRXUSDT

Largest common window across the full universe: **BTCUSDT 2020-09-01..2026-08-31 (2191 days, FULL, no interior gaps)**. Next tier: 1735 days (2021-12-01..2026-08-31) for the full 2021-12-01 metrics cohort (e.g. XRPUSDT, ZECUSDT, YFIUSDT, XTZUSDT, ZILUSDT, ZENUSDT, ZRXUSDT and ~400 others in the ≥365 list).

Reconciliation against the prior figure: the §E "333 days, BTCUSDT/ETHUSDT only" three-way window was constrained by cross-referencing archive OI-metrics against the **internal** collector funding/price DBs, which cover BTC/ETH only — not by the archive itself. Archive-native cross-referencing (metrics ∩ fundingRate ∩ klines, all from data.binance.vision) gives **510 symbols ≥90 d, 495 ≥180 d, 397 ≥365 d**, largest 2191 d (BTCUSDT). Side by side: internal-DB-limited = 2 symbols / 333 d max; archive-native = 510 symbols ≥90 d / 2191 d max. The four-way figure (with liquidationSnapshot) remains 0/0 in both views because the liquidation leg is unpublished.

New sample verifications (download + checksum + parse, same standard as §D; zips kept outside the repo):

| Symbol | Dataset | Sample | Checksum | Parse |
|---|---|---|---|---|
| SOLUSDT | fundingRate monthly | 2025-06 (939 B) | True | clean, 3-col header, 90 rows = 30 d × 3/day (8 h grid), calc 2025-06-01..06-30 |
| SOLUSDT | klines 1h daily | 2025-06-15 (1508 B) | True | clean, 12-col header + 24 unique hourly rows 00:00–23:00 UTC, no gaps/dups |
| BNBUSDT | klines 1h daily | 2024-03-10, older date (1510 B) | True | clean, header + 24 unique hourly rows 00:00–23:00 UTC |
| SUIUSDT | fundingRate monthly | 2026-08 (919 B) | True | clean, 93 rows = 31 d × 3/day |
| ARBUSDT | klines 1h daily | 2026-09-20, recent (1567 B) | True | clean, header + 24 unique hourly rows 00:00–23:00 UTC |

Confirmed granularity for this cross-reference: OI-metrics = 5-minute rows in UTC-daily partitions (per §A/D); fundingRate = 8-hourly rows in monthly partitions; klines = 1-hourly rows in daily partitions (24/day + header). Any future hypothesis using these sources must respect the daily-partition information boundary at minimum. This audit does not choose the rebalance interval, holding period, signal definition, or strategy design. Interpretation boundary in §G applies unchanged: coverage only, no predictive or viability claim.
