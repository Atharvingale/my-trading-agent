# Edge Validation Experiment Registry

Append-only preregistration and outcome log. Hypotheses are recorded before results.

## Preregistered hypothesis — 2026-09-23T05:58:31.649053+00:00

- Record ID: `f8fe8fe2-609b-409b-bb41-cc8d49e9bb29`
- Strategy: `trend_following` (family `trend_following`)
- Hypothesis: Causal hourly EMA trend following has positive net-of-cost-and-tax return on the untouched BTCUSDT holdout.
- Holdout: 2024-01-01 through 2024-04-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Preregistered hypothesis — 2026-09-23T05:59:29.031809+00:00

- Record ID: `4223c403-c811-401a-b11d-a721d1488f68`
- Strategy: `trend_following` (family `trend_following`)
- Hypothesis: Causal hourly EMA trend following has positive net-of-cost-and-tax return on the untouched BTCUSDT holdout.
- Holdout: 2024-01-01 through 2024-04-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Preregistered hypothesis — 2026-09-23T06:00:04.270385+00:00

- Record ID: `606c92b5-6187-475c-8a79-b552c47f54ab`
- Strategy: `trend_following` (family `trend_following`)
- Hypothesis: Causal hourly EMA trend following has positive net-of-cost-and-tax return on the untouched BTCUSDT holdout.
- Holdout: 2024-01-01 through 2024-04-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Result — 2026-09-23T06:00:06.681341+00:00

- Preregistration record ID: `606c92b5-6187-475c-8a79-b552c47f54ab`
- Verdict: **FAIL**
- Evidence:

```json
{
  "acceptance_checks": {
    "fresh_holdout_for_strategy_family": true,
    "independent_replication_when_refined": false,
    "net_of_fees_slippage_and_vda_tax": true,
    "null_result_recorded_without_retries": true,
    "positive_bootstrap_confidence_interval": false,
    "preregistered_before_holdout": true,
    "two_structurally_different_regimes": true
  },
  "bootstrap_ci": [
    -0.01725408240428955,
    -0.006737639370766806
  ],
  "evidence": {
    "dataset_id": "binance-spot-BTCUSDT-1h-2024-01-01-2024-04-01",
    "dataset_sha256": "d4f54cea77b291c818d7007c28559f299f5eb0459196638c81206fd1c7fb4e44",
    "fingerprint": "cd17b35f084e4c477a96fa426f9d3fcb84586db4905ad1dd0dc86fa6853cd578",
    "net_return": -0.012254233947945682
  },
  "regime_results": {
    "range_bound": -0.053375542134956,
    "trending": 0.0
  },
  "replication_result": "FAIL"
}
```

---

## Preregistered hypothesis — 2026-09-23T06:00:34.146260+00:00

- Record ID: `fafeb983-d541-4817-8da7-e29a9129b029`
- Strategy: `trend_following` (family `trend_following`)
- Hypothesis: Causal hourly EMA trend following has positive net-of-cost-and-tax return on the untouched BTCUSDT holdout.
- Holdout: 2024-01-01 through 2024-04-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Result — 2026-09-23T06:00:36.163898+00:00

- Preregistration record ID: `fafeb983-d541-4817-8da7-e29a9129b029`
- Verdict: **FAIL**
- Evidence:

```json
{
  "acceptance_checks": {
    "fresh_holdout_for_strategy_family": true,
    "independent_replication_when_refined": false,
    "net_of_fees_slippage_and_vda_tax": true,
    "null_result_recorded_without_retries": true,
    "positive_bootstrap_confidence_interval": false,
    "preregistered_before_holdout": true,
    "two_structurally_different_regimes": true
  },
  "bootstrap_ci": [
    -0.01725408240428955,
    -0.006737639370766806
  ],
  "evidence": {
    "dataset_id": "binance-spot-BTCUSDT-1h-2024-01-01-2024-04-01",
    "dataset_sha256": "d4f54cea77b291c818d7007c28559f299f5eb0459196638c81206fd1c7fb4e44",
    "fingerprint": "cd17b35f084e4c477a96fa426f9d3fcb84586db4905ad1dd0dc86fa6853cd578",
    "net_return": -0.012254233947945682
  },
  "regime_results": {
    "range_bound": -0.053375542134956,
    "trending": 0.0
  },
  "replication_result": "FAIL"
}
```

---

## Preregistered hypothesis — 2026-09-24T08:12:56.201018+00:00

- Record ID: `cc6dbcef-5be7-4911-943b-5c30ac4c96a7`
- Strategy: `order_flow` (family `order_flow`)
- Hypothesis: Causal hourly long-only Order Flow volume-expansion on BTCUSDT spot has positive net-of-cost-and-tax return on the untouched 2024-04-02 through 2024-07-01 holdout. Entry: a completed hourly candle whose volume exceeds 2.0x the mean of the prior 20 hourly volumes; execution at the next candle open with 0.10% adverse slippage; 25% of available cash per position. Exit priority on every held candle: 2% stop-loss first, then volume-normalization signal (current volume at or below the prior-20 mean), else hold to end of data. Costs: 0.10% fee per side, 31.2% VDA tax on positive realized gains with no loss offset, 1% gross-proceeds TDS as a cash-flow drag. PASS bar (all required): at least 3 of 4 chronological windows positive net, aggregate net above zero, bootstrap confidence interval on mean per-trade net return excluding zero on the positive side, aggregate minus zero risk-free exceeding the CI width, doubled-cost stress net above zero, at least 20 trades, two regime legs reported, disjoint replication positive.
- Holdout: 2024-04-02 through 2024-07-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Result — 2026-09-24T08:12:57.907438+00:00

- Preregistration record ID: `cc6dbcef-5be7-4911-943b-5c30ac4c96a7`
- Verdict: **FAIL**
- Evidence:

```json
{
  "acceptance_checks": {
    "fresh_holdout_for_strategy_family": true,
    "independent_replication_when_refined": false,
    "net_of_fees_slippage_and_vda_tax": true,
    "null_result_recorded_without_retries": true,
    "positive_bootstrap_confidence_interval": false,
    "preregistered_before_holdout": true,
    "two_structurally_different_regimes": true
  },
  "bootstrap_ci": [
    -0.016414192152738656,
    -0.012204430414275776
  ],
  "evidence": {
    "dataset_id": "binance-spot-BTCUSDT-1h-2024-04-02-2024-07-01",
    "dataset_sha256": "8cb531d3703c06fed5e9d15355965f916a3889892a82adf9ae11f619015f6d7d",
    "fingerprint": "148c3ba113b06b455ec986fe62b46eab53edd27fe448f72216ca3a1cc112d432",
    "net_return": -0.014355779595532423
  },
  "regime_results": {
    "range_bound": -0.10130410367669901,
    "trending": 0.0
  },
  "replication_result": "FAIL"
}
```

---

## Preregistered hypothesis — 2026-09-24T08:18:03.949353+00:00

- Record ID: `4b626ced-4ab8-490a-aab0-89a5a0f758b9`
- Strategy: `mean_reversion` (family `mean_reversion`)
- Hypothesis: Causal hourly long-only z-score mean reversion on BTCUSDT spot has positive net-of-cost-and-tax return on the untouched 2024-07-02 through 2024-10-01 holdout. Entry: a completed hourly close at least 1.0 standard deviations below the trailing-20 mean; execution at the next candle open with 0.10% adverse slippage; 25% of available cash per position. Exit priority on every held candle: 2% stop-loss first, then reversion signal (close at or above the trailing-20 mean), else hold to end of data. Costs: 0.10% fee per side, 31.2% VDA tax on positive realized gains with no loss offset, 1% gross-proceeds TDS as a cash-flow drag. PASS bar (all required): at least 3 of 4 chronological windows positive net, aggregate net above zero, bootstrap confidence interval on mean per-trade net return excluding zero on the positive side, aggregate minus zero risk-free exceeding the CI width, doubled-cost stress net above zero, at least 20 trades, two regime legs reported, disjoint replication positive.
- Holdout: 2024-07-02 through 2024-10-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Result — 2026-09-24T08:18:05.596885+00:00

- Preregistration record ID: `4b626ced-4ab8-490a-aab0-89a5a0f758b9`
- Verdict: **FAIL**
- Evidence:

```json
{
  "acceptance_checks": {
    "fresh_holdout_for_strategy_family": true,
    "independent_replication_when_refined": false,
    "net_of_fees_slippage_and_vda_tax": true,
    "null_result_recorded_without_retries": true,
    "positive_bootstrap_confidence_interval": false,
    "preregistered_before_holdout": true,
    "two_structurally_different_regimes": true
  },
  "bootstrap_ci": [
    -0.01862820599370702,
    -0.012315123116352772
  ],
  "evidence": {
    "dataset_id": "binance-spot-BTCUSDT-1h-2024-07-02-2024-10-01",
    "dataset_sha256": "a933bf7cb84b59eac79bf724626d70a82e6d7a97fc6fc905d25df13f17ca44a8",
    "fingerprint": "51fdaf7594b3b23c77d9808a5e8a14bca2794fe29926826f153d52ad850d51f5",
    "net_return": -0.015618735985205504
  },
  "regime_results": {
    "range_bound": -0.09487515796387674,
    "trending": 0.0
  },
  "replication_result": "FAIL"
}
```

---

## Preregistered hypothesis — 2026-09-24T09:36:57.888451+00:00

- Record ID: `e53a9ebf-2201-479a-b15a-35f37d51a5e1`
- Strategy: `vwap_reversion` (family `vwap_reversion`)
- Hypothesis: Causal hourly long-only VWAP reversion on BTCUSDT spot has positive net-of-cost-and-tax return on the untouched 2024-10-02 through 2025-01-01 holdout. Entry: a completed hourly close at least 2.0% below the trailing 20-candle volume-weighted average price; execution at the next candle open with 0.10% adverse slippage; 25% of available cash per position. Exit priority on every held candle: 2% stop-loss first, then reversion signal (close at or above trailing-20 VWAP), else hold to end of data. Costs: 0.10% fee per side, 31.2% VDA tax on positive realized gains with no loss offset, 1% gross-proceeds TDS as a cash-flow drag. PASS bar (all required): at least 3 of 4 chronological windows positive net, aggregate net above zero, bootstrap confidence interval on mean per-trade net return excluding zero on the positive side, aggregate minus zero risk-free exceeding the CI width, doubled-cost stress net above zero, at least 20 trades, two regime legs reported, disjoint replication positive.
- Holdout: 2024-10-02 through 2025-01-01
- Requires independent replication: False
- Materially new rationale: None
- Pre-registered thresholds:

```json
{
  "bootstrap_confidence": 0.9,
  "minimum_trades": 20,
  "risk_free_benchmark": "quote_hold",
  "stress_multiplier": 2.0,
  "windows": 4
}
```
- Cost and tax assumptions:

```json
{
  "fee_rate": 0.001,
  "loss_offset_allowed": false,
  "slippage_rate": 0.001,
  "tax_rate": 0.312,
  "tds_is_cash_flow_drag": true,
  "tds_rate": 0.01
}
```

Outcome: PENDING — no results recorded yet.

---

## Result — 2026-09-24T09:36:59.821848+00:00

- Preregistration record ID: `e53a9ebf-2201-479a-b15a-35f37d51a5e1`
- Verdict: **FAIL**
- Evidence:

```json
{
  "acceptance_checks": {
    "fresh_holdout_for_strategy_family": true,
    "independent_replication_when_refined": false,
    "net_of_fees_slippage_and_vda_tax": true,
    "null_result_recorded_without_retries": true,
    "positive_bootstrap_confidence_interval": false,
    "preregistered_before_holdout": true,
    "two_structurally_different_regimes": true
  },
  "bootstrap_ci": [
    -0.018474911186976528,
    -0.0029951220298954804
  ],
  "evidence": {
    "dataset_id": "binance-spot-BTCUSDT-1h-2024-10-02-2025-01-01",
    "dataset_sha256": "c7a4a8695dfc775911de8a9300597c275d1cff471fe70d422684f14aed91a235",
    "fingerprint": "e55e9600fd8c50e9c973e9ed89825c0a6ea7252909c574a03b19c54ac8b65f57",
    "net_return": -0.010342220534173323
  },
  "regime_results": {
    "range_bound": -0.011270997162628192,
    "trending": 0.0
  },
  "replication_result": "FAIL"
}
```

---

