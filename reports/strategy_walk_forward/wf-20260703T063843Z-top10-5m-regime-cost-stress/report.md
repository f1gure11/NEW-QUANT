# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 401 |
| Passed window rows | 64 |
| Unique aggregate candidates | 283 |
| Passed aggregate candidates | 2 |
| Median selected test return | -1.060441% |
| Mean selected test return | -1.857629% |
| Best aggregate return | 11.423798% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | macd_signal | high_vol | 2 | 100.0000 | 9.95880152 | 4.89489689 | 2.23797335 | false |
| 2 | SOXL-USDT-SWAP | rsi_revert | trend_up | 1 | 100.0000 | 5.03686372 | 5.03686372 | 5.03686372 | false |
| 3 | SOXL-USDT-SWAP | rsi_revert | trend | 2 | 100.0000 | 5.60017905 | 2.77394668 | 1.20352947 | false |
| 4 | HYPE-USDT-SWAP | rsi_revert | normal_vol | 1 | 100.0000 | 2.80752937 | 2.80752937 | 2.80752937 | false |
| 5 | HYPE-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 4.27864219 | 4.27864219 | 4.27864219 | false |
| 6 | SPCX-USDT-SWAP | trend_pullback | high_vol | 1 | 100.0000 | 1.49922278 | 1.49922278 | 1.49922278 | false |
| 7 | MU-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 2.93910138 | 2.93910138 | 2.93910138 | false |
| 8 | SOXL-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 1.55053363 | 1.55053363 | 1.55053363 | false |
| 9 | HYPE-USDT-SWAP | rsi_revert | trend_up | 1 | 100.0000 | 1.06344254 | 1.06344254 | 1.06344254 | false |
| 10 | SOXL-USDT-SWAP | rsi_revert | normal_vol | 1 | 100.0000 | 1.05966614 | 1.05966614 | 1.05966614 | false |
| 11 | SOXL-USDT-SWAP | rsi_revert | trend_down | 1 | 100.0000 | 2.15018285 | 2.15018285 | 2.15018285 | false |
| 12 | SPCX-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 0.18009658 | 0.18009658 | 0.18009658 | false |
| 13 | XAU-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 1.03813688 | 1.03813688 | 1.03813688 | false |
| 14 | XAU-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 1.03813688 | 1.03813688 | 1.03813688 | false |
| 15 | XAU-USDT-SWAP | ema_cross | range_normal_vol | 1 | 100.0000 | 1.03813688 | 1.03813688 | 1.03813688 | false |
| 16 | SOXL-USDT-SWAP | rsi_revert | mixed | 1 | 100.0000 | 0.43107043 | 0.43107043 | 0.43107043 | false |
| 17 | SOXL-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 0.70841532 | 0.70841532 | 0.70841532 | false |
| 18 | SOXL-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 0.70841532 | 0.70841532 | 0.70841532 | false |
| 19 | HYPE-USDT-SWAP | trend_pullback | mixed | 1 | 100.0000 | 0.11186804 | 0.11186804 | 0.11186804 | false |
| 20 | MU-USDT-SWAP | rsi_revert | normal_vol | 1 | 100.0000 | 0.88255982 | 0.88255982 | 0.88255982 | false |
| 21 | HYPE-USDT-SWAP | rsi_revert | range_normal_vol | 1 | 100.0000 | 0.42032855 | 0.42032855 | 0.42032855 | false |
| 22 | HYPE-USDT-SWAP | atr_vol_breakout | trend_up | 1 | 100.0000 | 0.74347850 | 0.74347850 | 0.74347850 | false |
| 23 | SKHYNIX-USDT-SWAP | volatility_squeeze_breakout | trend_up | 1 | 100.0000 | 0.43014072 | 0.43014072 | 0.43014072 | false |
| 24 | BTC-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.13981254 | 0.13981254 | 0.13981254 | false |
| 25 | SOL-USDT-SWAP | ema_cross | normal_vol | 1 | 0.0000 | 11.42379821 | 11.42379821 | 11.42379821 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 2.01116022 | -0.19355944 | 1.745385 | 1.19696004 | false |
| 1 | 2 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 1.92696838 | -0.19355944 | 1.745385 | 1.19696004 | false |
| 1 | 3 | ETH-USDT-SWAP | bollinger_revert | range_normal_vol | 1.92696838 | -0.19355944 | 1.745385 | 1.19696004 | false |
| 2 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 1.81483565 | -9.44733690 | 0.095810 | 10.43623940 | false |
| 2 | 2 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 1.73080584 | -9.44733690 | 0.095810 | 10.43623940 | false |
| 2 | 3 | ETH-USDT-SWAP | bollinger_revert | range_normal_vol | 1.73080584 | -9.44733690 | 0.095810 | 10.43623940 | false |
| 3 | 1 | ETH-USDT-SWAP | rsi_trend | trend_up | 4.04895653 | -1.34143572 | 0.311042 | 2.45305071 | false |
| 3 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.71343038 | -0.22036993 | 1.072413 | 1.58879830 | false |
| 3 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.02490249 | 0.75493130 | 6.622798 | 1.58841395 | true |
| 4 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 6.66147667 | -2.73539207 | 0.000000 | 3.17558428 | false |
| 4 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 6.66147667 | -2.73539207 | 0.000000 | 3.17558428 | false |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | trend_up | 6.43530750 | -3.21452520 | 0.000000 | 3.65254899 | false |
| 5 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.92137467 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 5 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.26028016 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 5 | 3 | ETH-USDT-SWAP | keltner_breakout | trend_up | 3.93190430 | -1.30663267 | 0.000000 | 1.30663267 | false |
| 6 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.20968795 | -1.17040757 | 0.000000 | 1.17040757 | false |
| 6 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.55307767 | -1.17040757 | 0.000000 | 1.17040757 | false |
| 6 | 3 | ETH-USDT-SWAP | keltner_breakout | all | 5.48458793 | -4.71736391 | 0.128737 | 4.80488814 | false |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | normal_vol | 1.54051468 | -0.39543864 | 1.000414 | 1.09597813 | false |
| 7 | 2 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 1.54051468 | -0.39543864 | 1.000414 | 1.09597813 | false |
| 7 | 3 | ETH-USDT-SWAP | rsi_revert | all | 1.26674062 | -0.39543864 | 1.000414 | 1.09597813 | false |
| 8 | 1 | ETH-USDT-SWAP | bollinger_revert | trend_up | 1.05984468 | -1.29108800 | 0.433431 | 1.71311899 | false |
| 8 | 2 | ETH-USDT-SWAP | bollinger_revert | trend_up | 1.18584885 | -1.29108800 | 0.433431 | 1.71311899 | false |
| 8 | 3 | ETH-USDT-SWAP | bollinger_revert | trend_up | 0.74053756 | -0.32976434 | 1.105578 | 1.42884973 | false |
| 9 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 0.09299156 | -5.47579949 | 0.316814 | 8.73018675 | false |
