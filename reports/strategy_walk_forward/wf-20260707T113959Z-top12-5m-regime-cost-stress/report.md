# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1084 |
| Passed window rows | 239 |
| Unique aggregate candidates | 652 |
| Passed aggregate candidates | 15 |
| Median selected test return | -0.748975% |
| Mean selected test return | -1.641677% |
| Best aggregate return | 36.386662% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 36.38666168 | 36.38666168 | 36.38666168 | false |
| 2 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 1 | 100.0000 | 32.29465553 | 32.29465553 | 32.29465553 | false |
| 3 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 50.0000 | 36.16452259 | 17.60992164 | 2.92518775 | false |
| 4 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 4 | 75.0000 | 22.41488295 | 5.97341141 | 1.03242000 | true |
| 5 | HYPE-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 12.37870260 | 12.37870260 | 12.37870260 | false |
| 6 | HYPE-USDT-SWAP | ema_cross_atr_band | high_vol | 1 | 100.0000 | 10.59993366 | 10.59993366 | 10.59993366 | false |
| 7 | LAB-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 12.62771380 | 12.62771380 | 12.62771380 | false |
| 8 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 2 | 100.0000 | 12.09897725 | 5.88425895 | 4.62784759 | false |
| 9 | LAB-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 9.52912545 | 9.52912545 | 9.52912545 | false |
| 10 | LAB-USDT-SWAP | rsi_revert | range | 4 | 75.0000 | 11.56971589 | 2.44281006 | -0.11881552 | true |
| 11 | LAB-USDT-SWAP | rsi_revert | range_normal_vol | 4 | 75.0000 | 11.56971589 | 2.44281006 | -0.11881552 | true |
| 12 | SOXL-USDT-SWAP | ema_cross_atr_band | all | 2 | 50.0000 | 20.19232995 | 10.94741372 | -6.08477977 | false |
| 13 | XRP-USDT-SWAP | donchian_breakout | range_normal_vol | 3 | 100.0000 | 8.35066861 | 1.76189043 | 1.09238147 | true |
| 14 | SOL-USDT-SWAP | ema_cross_atr_band | normal_vol | 2 | 100.0000 | 8.74535635 | 4.28140144 | 4.00744564 | false |
| 15 | SOL-USDT-SWAP | ema_cross_atr_band | range_normal_vol | 2 | 100.0000 | 8.74535635 | 4.28140144 | 4.00744564 | false |
| 16 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 10.71710570 | 10.71710570 | 10.71710570 | false |
| 17 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 10.71710570 | 10.71710570 | 10.71710570 | false |
| 18 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 10.71710570 | 10.71710570 | 10.71710570 | false |
| 19 | HYPE-USDT-SWAP | ema_cross_atr_band | all | 1 | 100.0000 | 8.90280686 | 8.90280686 | 8.90280686 | false |
| 20 | SOL-USDT-SWAP | rsi_revert | trend_high_vol | 6 | 66.6667 | 11.96320373 | 0.68087989 | -2.75013036 | true |
| 21 | XRP-USDT-SWAP | keltner_breakout | trend_up | 1 | 100.0000 | 5.91986030 | 5.91986030 | 5.91986030 | false |
| 22 | XRP-USDT-SWAP | keltner_breakout | trend_up | 1 | 100.0000 | 5.91986030 | 5.91986030 | 5.91986030 | false |
| 23 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 3 | 66.6667 | 13.28521082 | 3.37827200 | 1.71390518 | true |
| 24 | MU-USDT-SWAP | rsi_revert | high_vol | 1 | 100.0000 | 8.39323267 | 8.39323267 | 8.39323267 | false |
| 25 | LAB-USDT-SWAP | rsi_revert | range | 2 | 100.0000 | 5.38296144 | 2.67302650 | 0.81447172 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 3 | 1 | ETH-USDT-SWAP | ema_cross | all | 3.26563705 | -2.50195284 | 0.360787 | 3.72756788 | false |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 3.26563705 | -2.50195284 | 0.360787 | 3.72756788 | false |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 3.26563705 | -2.50195284 | 0.360787 | 3.72756788 | false |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | all | 4.55887027 | 1.21021067 | 2.073651 | 1.82660693 | true |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 4.55887027 | 1.21021067 | 2.073651 | 1.82660693 | true |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 4.55887027 | 1.21021067 | 2.073651 | 1.82660693 | true |
| 5 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.06266799 | -2.24661583 | 0.395904 | 3.39161883 | false |
| 5 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 5.06266799 | -2.24661583 | 0.395904 | 3.39161883 | false |
| 5 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 5.06266799 | -2.24661583 | 0.395904 | 3.39161883 | false |
| 6 | 1 | ETH-USDT-SWAP | ema_cross | all | 0.61145516 | -2.66658471 | 0.050657 | 2.93850495 | false |
| 6 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 0.61145516 | -2.66658471 | 0.050657 | 2.93850495 | false |
| 6 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 0.61145516 | -2.66658471 | 0.050657 | 2.93850495 | false |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | all | 0.16001469 | 1.16170398 | 2.081875 | 2.18862433 | true |
| 9 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.16001469 | 1.16170398 | 2.081875 | 2.18862433 | true |
| 9 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 0.16001469 | 1.16170398 | 2.081875 | 2.18862433 | true |
| 10 | 1 | ETH-USDT-SWAP | rsi_revert | trend_down | 1.26178707 | -0.90539634 | 0.981494 | 3.55916662 | false |
| 10 | 2 | ETH-USDT-SWAP | rsi_revert | all | 1.42934254 | 0.46626728 | 17.123774 | 4.67272216 | false |
| 10 | 3 | ETH-USDT-SWAP | rsi_revert | normal_vol | 1.42934254 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 11 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 6.11897960 | 11.94437074 | 999.000000 | 3.69011945 | false |
| 11 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 3.98823473 | 8.54313027 | 3.728586 | 3.59865423 | true |
| 11 | 3 | ETH-USDT-SWAP | macd_signal | high_vol | 2.40788558 | 0.03952831 | 1.211224 | 6.34475725 | true |
| 12 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 19.21763436 | 3.68299289 | 11.448059 | 2.33978796 | false |
| 12 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 14.46905416 | 4.67595453 | 24.288998 | 2.29552481 | true |
| 12 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 13.90116046 | 0.19658496 | 1.196038 | 4.80426633 | true |
| 13 | 1 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 22.17117344 | -14.01786640 | 0.000789 | 14.80864310 | false |
