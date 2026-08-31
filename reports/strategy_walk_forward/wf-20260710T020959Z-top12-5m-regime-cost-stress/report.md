# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1108 |
| Passed window rows | 217 |
| Unique aggregate candidates | 665 |
| Passed aggregate candidates | 7 |
| Median selected test return | -1.017080% |
| Mean selected test return | -1.911266% |
| Best aggregate return | 42.260093% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 15.62133216 | 15.62133216 | 15.62133216 | false |
| 2 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 15.62133216 | 15.62133216 | 15.62133216 | false |
| 3 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 15.62133216 | 15.62133216 | 15.62133216 | false |
| 4 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 2 | 0.0000 | 34.10026826 | 17.37045703 | -1.75537255 | false |
| 5 | EDGE-USDT-SWAP | donchian_breakout | trend_down | 1 | 0.0000 | 34.95488274 | 34.95488274 | 34.95488274 | false |
| 6 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 4 | 50.0000 | 21.13909597 | 3.30807225 | 1.03041923 | false |
| 7 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 3 | 33.3333 | 29.20165782 | 1.23491025 | 0.52254722 | false |
| 8 | EDGE-USDT-SWAP | ema_cross_atr_band | high_vol | 1 | 0.0000 | 37.25476646 | 37.25476646 | 37.25476646 | false |
| 9 | EDGE-USDT-SWAP | macd_signal | high_vol | 5 | 20.0000 | 25.21747054 | -2.22308208 | -12.02661341 | false |
| 10 | LAB-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 11.71058536 | 11.71058536 | 11.71058536 | false |
| 11 | SOL-USDT-SWAP | ema_cross_atr_band | normal_vol | 2 | 100.0000 | 9.26080112 | 4.52805666 | 4.34226779 | false |
| 12 | SOL-USDT-SWAP | ema_cross_atr_band | range_normal_vol | 2 | 100.0000 | 9.26080112 | 4.52805666 | 4.34226779 | false |
| 13 | LAB-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 26.82716259 | 26.82716259 | 26.82716259 | false |
| 14 | SPCX-USDT-SWAP | macd_signal | high_vol | 5 | 80.0000 | 10.81483405 | 2.93950268 | 0.00000000 | true |
| 15 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 100.0000 | 8.40862621 | 8.40862621 | 8.40862621 | false |
| 16 | SOL-USDT-SWAP | rsi_revert | trend_high_vol | 6 | 66.6667 | 12.21180408 | 0.68103162 | -2.74996585 | true |
| 17 | SOXL-USDT-SWAP | donchian_breakout | all | 6 | 0.0000 | 24.90432461 | 1.96604164 | -1.30500465 | false |
| 18 | LAB-USDT-SWAP | donchian_breakout | all | 2 | 0.0000 | 42.26009282 | 19.74932069 | 9.07737038 | false |
| 19 | LAB-USDT-SWAP | donchian_breakout | high_vol | 2 | 0.0000 | 42.26009282 | 19.74932069 | 9.07737038 | false |
| 20 | LAB-USDT-SWAP | donchian_breakout | trend_high_vol | 2 | 0.0000 | 42.26009282 | 19.74932069 | 9.07737038 | false |
| 21 | SOXL-USDT-SWAP | rsi_revert | trend | 2 | 100.0000 | 6.63725625 | 3.29721341 | 0.73037229 | false |
| 22 | LAB-USDT-SWAP | rsi_revert | range | 2 | 100.0000 | 4.86300561 | 2.41030118 | 1.15761338 | false |
| 23 | SPCX-USDT-SWAP | bollinger_revert | trend | 2 | 100.0000 | 4.79989988 | 2.37796386 | 1.25658250 | false |
| 24 | LAB-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 24.55284868 | 24.55284868 | 24.55284868 | false |
| 25 | LAB-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 23.89462176 | 23.89462176 | 23.89462176 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | ema_cross | all | 3.30793260 | -1.37644278 | 0.455421 | 2.28123620 | false |
| 1 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 3.30793260 | -1.37644278 | 0.455421 | 2.28123620 | false |
| 1 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 3.30793260 | -1.37644278 | 0.455421 | 2.28123620 | false |
| 2 | 1 | BTC-USDT-SWAP | ema_cross | all | 4.57455401 | -2.84032965 | 0.367783 | 2.90384576 | false |
| 2 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 4.57455401 | -2.84032965 | 0.367783 | 2.90384576 | false |
| 2 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 4.57455401 | -2.84032965 | 0.367783 | 2.90384576 | false |
| 3 | 1 | BTC-USDT-SWAP | ema_cross | all | 4.48586407 | -3.63242274 | 0.011956 | 4.42654379 | false |
| 3 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 4.48586407 | -3.63242274 | 0.011956 | 4.42654379 | false |
| 3 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 4.48586407 | -3.63242274 | 0.011956 | 4.42654379 | false |
| 7 | 1 | BTC-USDT-SWAP | donchian_breakout | all | 0.28012268 | -4.36729865 | 0.397161 | 9.01764760 | false |
| 7 | 2 | BTC-USDT-SWAP | donchian_breakout | normal_vol | 0.28012268 | -4.36729865 | 0.397161 | 9.01764760 | false |
| 7 | 3 | BTC-USDT-SWAP | donchian_breakout | range_normal_vol | 0.28012268 | -4.36729865 | 0.397161 | 9.01764760 | false |
| 8 | 1 | BTC-USDT-SWAP | donchian_breakout | all | 5.53242185 | -0.47452553 | 0.890598 | 6.78455701 | false |
| 8 | 2 | BTC-USDT-SWAP | donchian_breakout | normal_vol | 5.53242185 | 1.87548734 | 2.028732 | 6.27503688 | true |
| 8 | 3 | BTC-USDT-SWAP | donchian_breakout | range_normal_vol | 5.53242185 | 1.07968370 | 1.603181 | 6.27503688 | true |
| 9 | 1 | BTC-USDT-SWAP | donchian_breakout | normal_vol | 8.92053688 | -0.98232670 | 0.931111 | 6.41642785 | false |
| 9 | 2 | BTC-USDT-SWAP | donchian_breakout | range_normal_vol | 8.06970061 | -3.35443349 | 0.710433 | 7.73633636 | false |
| 9 | 3 | BTC-USDT-SWAP | ema_cross_atr_band | range_normal_vol | 6.70965603 | -1.99853933 | 0.867258 | 6.59547359 | false |
| 10 | 1 | BTC-USDT-SWAP | donchian_breakout | normal_vol | 9.38027001 | -0.11074765 | 1.090136 | 2.74485271 | false |
| 10 | 2 | BTC-USDT-SWAP | bollinger_revert | high_vol | 4.75968083 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 10 | 3 | BTC-USDT-SWAP | rsi_revert | high_vol | 3.99658773 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 11 | 1 | BTC-USDT-SWAP | bollinger_revert | high_vol | 4.75968083 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 11 | 2 | BTC-USDT-SWAP | rsi_revert | high_vol | 3.99658773 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 11 | 3 | BTC-USDT-SWAP | bollinger_revert | high_vol | 3.41670557 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 12 | 1 | BTC-USDT-SWAP | bollinger_revert | high_vol | 4.75968083 | 0.00000000 | 0.000000 | 0.00000000 | false |
