# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1765 |
| Passed window rows | 339 |
| Unique aggregate candidates | 1088 |
| Passed aggregate candidates | 9 |
| Median selected test return | -0.670180% |
| Mean selected test return | -1.233086% |
| Best aggregate return | 134.587530% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | rsi_trend | trend | 1 | 0.0000 | 134.58752955 | 134.58752955 | 134.58752955 | false |
| 2 | LAB-USDT-SWAP | rsi_trend | trend | 1 | 0.0000 | 133.62385663 | 133.62385663 | 133.62385663 | false |
| 3 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 97.02499467 | 97.02499467 | 97.02499467 | false |
| 4 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 95.44356706 | 95.44356706 | 95.44356706 | false |
| 5 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 3 | 66.6667 | 102.05262027 | 2.71190921 | 0.65197580 | true |
| 6 | EDGE-USDT-SWAP | ema_cross_atr_band | trend_up | 1 | 100.0000 | 54.59478722 | 54.59478722 | 54.59478722 | false |
| 7 | EDGE-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 54.59478722 | 54.59478722 | 54.59478722 | false |
| 8 | EDGE-USDT-SWAP | donchian_breakout | trend | 1 | 100.0000 | 54.59478722 | 54.59478722 | 54.59478722 | false |
| 9 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 0.0000 | 42.14299691 | 19.34636161 | 13.93763360 | false |
| 10 | LAB-USDT-SWAP | keltner_breakout | trend_down | 2 | 0.0000 | 39.02676283 | 17.90966370 | 17.79780894 | false |
| 11 | ZEC-USDT-SWAP | ema_cross | trend_high_vol | 1 | 0.0000 | 31.19480621 | 31.19480621 | 31.19480621 | false |
| 12 | ZEC-USDT-SWAP | ema_cross | trend_high_vol | 1 | 0.0000 | 31.19480621 | 31.19480621 | 31.19480621 | false |
| 13 | ZEC-USDT-SWAP | ema_cross_atr_band | trend_high_vol | 1 | 0.0000 | 31.19480621 | 31.19480621 | 31.19480621 | false |
| 14 | ZEC-USDT-SWAP | bollinger_revert | high_vol | 2 | 100.0000 | 17.27748395 | 8.56078209 | 0.96505876 | false |
| 15 | ZEC-USDT-SWAP | bollinger_revert | trend_high_vol | 2 | 100.0000 | 17.27748395 | 8.56078209 | 0.96505876 | false |
| 16 | ZEC-USDT-SWAP | ema_cross_atr_band | trend_up | 1 | 100.0000 | 11.06894335 | 11.06894335 | 11.06894335 | false |
| 17 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 3 | 66.6667 | 16.64167101 | 6.24335581 | 0.00000000 | true |
| 18 | SOXL-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 12.76052529 | 12.76052529 | 12.76052529 | false |
| 19 | SKHYNIX-USDT-SWAP | keltner_breakout | all | 1 | 100.0000 | 8.11009836 | 8.11009836 | 8.11009836 | false |
| 20 | ZEC-USDT-SWAP | atr_vol_breakout | all | 1 | 100.0000 | 8.17393535 | 8.17393535 | 8.17393535 | false |
| 21 | ZEC-USDT-SWAP | atr_vol_breakout | high_vol | 1 | 100.0000 | 8.17393535 | 8.17393535 | 8.17393535 | false |
| 22 | ZEC-USDT-SWAP | atr_vol_breakout | trend_high_vol | 1 | 100.0000 | 8.17393535 | 8.17393535 | 8.17393535 | false |
| 23 | SNDK-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 7.59910471 | 7.59910471 | 7.59910471 | false |
| 24 | EDGE-USDT-SWAP | bollinger_revert | all | 3 | 66.6667 | 14.53040475 | 6.73290121 | -1.63294875 | true |
| 25 | LAB-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 8.58843907 | 8.58843907 | 8.58843907 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | rsi_revert | all | 1.28441437 | -1.89789334 | 0.094262 | 2.36782658 | false |
| 1 | 2 | BTC-USDT-SWAP | rsi_revert | normal_vol | 1.28441437 | -1.89789334 | 0.094262 | 2.36782658 | false |
| 1 | 3 | BTC-USDT-SWAP | rsi_revert | range_normal_vol | 1.28441437 | -1.89789334 | 0.094262 | 2.36782658 | false |
| 2 | 1 | BTC-USDT-SWAP | ema_cross | all | 1.24210682 | -0.29335892 | 0.000000 | 1.06544992 | false |
| 2 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 1.24210682 | -0.29335892 | 0.000000 | 1.06544992 | false |
| 2 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 1.24210682 | -0.29335892 | 0.000000 | 1.06544992 | false |
| 3 | 1 | BTC-USDT-SWAP | ema_cross | all | 1.79122475 | -3.37946975 | 0.000000 | 3.65978243 | false |
| 3 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 1.79122475 | -3.37946975 | 0.000000 | 3.65978243 | false |
| 3 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 1.79122475 | -3.37946975 | 0.000000 | 3.65978243 | false |
| 4 | 1 | BTC-USDT-SWAP | ema_cross | all | 0.80526812 | -1.77838552 | 0.516562 | 4.08187628 | false |
| 4 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 0.80526812 | -1.77838552 | 0.516562 | 4.08187628 | false |
| 4 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 0.80526812 | -1.77838552 | 0.516562 | 4.08187628 | false |
| 5 | 1 | BTC-USDT-SWAP | trend_pullback | all | 1.07773347 | -2.17413193 | 0.088194 | 2.49694528 | false |
| 5 | 2 | BTC-USDT-SWAP | trend_pullback | normal_vol | 1.07773347 | -2.17413193 | 0.088194 | 2.49694528 | false |
| 5 | 3 | BTC-USDT-SWAP | trend_pullback | range_normal_vol | 1.07773347 | -2.17413193 | 0.088194 | 2.49694528 | false |
| 6 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 3.58945121 | -0.13234290 | 1.274392 | 1.38412151 | false |
| 6 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 3.58945121 | -0.13234290 | 1.274392 | 1.38412151 | false |
| 6 | 3 | BTC-USDT-SWAP | bollinger_revert | range_normal_vol | 3.58945121 | -0.13234290 | 1.274392 | 1.38412151 | false |
| 7 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 3.32518451 | 0.24866059 | 17.309049 | 0.55702588 | true |
| 7 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 3.32518451 | 0.24866059 | 17.309049 | 0.55702588 | true |
| 7 | 3 | BTC-USDT-SWAP | bollinger_revert | range_normal_vol | 3.32518451 | 0.24866059 | 17.309049 | 0.55702588 | true |
| 8 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 3.25798956 | -1.05961651 | 0.063783 | 0.94950198 | false |
| 8 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 3.25798956 | -1.05961651 | 0.063783 | 0.94950198 | false |
| 8 | 3 | BTC-USDT-SWAP | bollinger_revert | range_normal_vol | 3.25798956 | -1.05961651 | 0.063783 | 0.94950198 | false |
| 9 | 1 | BTC-USDT-SWAP | rsi_revert | all | 1.31382460 | 1.42377454 | 10.236501 | 0.62217449 | true |
