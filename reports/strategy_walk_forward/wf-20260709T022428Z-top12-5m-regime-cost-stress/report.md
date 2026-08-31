# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1069 |
| Passed window rows | 191 |
| Unique aggregate candidates | 651 |
| Passed aggregate candidates | 9 |
| Median selected test return | -1.076197% |
| Mean selected test return | -1.576585% |
| Best aggregate return | 69.776221% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | atr_vol_breakout | trend_high_vol | 1 | 0.0000 | 69.77622138 | 69.77622138 | 69.77622138 | false |
| 2 | LAB-USDT-SWAP | donchian_breakout | all | 1 | 0.0000 | 65.07072013 | 65.07072013 | 65.07072013 | false |
| 3 | LAB-USDT-SWAP | donchian_breakout | high_vol | 1 | 0.0000 | 65.07072013 | 65.07072013 | 65.07072013 | false |
| 4 | LAB-USDT-SWAP | atr_vol_breakout | high_vol | 2 | 0.0000 | 60.98396835 | 32.29874542 | -5.17873054 | false |
| 5 | LAB-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 49.78372552 | 49.78372552 | 49.78372552 | false |
| 6 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 27.43583435 | 27.43583435 | 27.43583435 | false |
| 7 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 27.43583435 | 27.43583435 | 27.43583435 | false |
| 8 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 27.43583435 | 27.43583435 | 27.43583435 | false |
| 9 | LAB-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 27.00055572 | 27.00055572 | 27.00055572 | false |
| 10 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 4 | 75.0000 | 24.42695313 | 3.93101046 | 1.03242000 | true |
| 11 | LAB-USDT-SWAP | rsi_revert | trend | 5 | 20.0000 | 40.43985238 | -3.71291086 | -7.02657958 | false |
| 12 | EDGE-USDT-SWAP | macd_signal | all | 3 | 66.6667 | 24.72718542 | 5.44497402 | -9.33642972 | false |
| 13 | EDGE-USDT-SWAP | donchian_breakout | trend_down | 1 | 0.0000 | 34.62242069 | 34.62242069 | 34.62242069 | false |
| 14 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 3 | 33.3333 | 28.49102543 | 0.73697912 | 0.46379344 | false |
| 15 | SOL-USDT-SWAP | ema_cross_atr_band | normal_vol | 2 | 100.0000 | 9.64294953 | 4.71978631 | 3.32741715 | false |
| 16 | SOXL-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 10.39306066 | 10.39306066 | 10.39306066 | false |
| 17 | SOXL-USDT-SWAP | macd_signal | trend_high_vol | 1 | 100.0000 | 10.05745933 | 10.05745933 | 10.05745933 | false |
| 18 | EDGE-USDT-SWAP | macd_signal | high_vol | 4 | 50.0000 | 17.52456147 | 1.23717252 | -12.77993070 | false |
| 19 | LAB-USDT-SWAP | rsi_revert | trend_down | 1 | 100.0000 | 8.83108073 | 8.83108073 | 8.83108073 | false |
| 20 | MU-USDT-SWAP | ema_cross | all | 2 | 100.0000 | 6.72565719 | 3.33275092 | 1.07627302 | false |
| 21 | SPCX-USDT-SWAP | bollinger_revert | trend | 2 | 100.0000 | 5.03072848 | 2.51381321 | 0.06247664 | false |
| 22 | SPCX-USDT-SWAP | macd_signal | high_vol | 5 | 60.0000 | 11.61840808 | 0.41402194 | -0.73312824 | true |
| 23 | MU-USDT-SWAP | ema_cross_atr_band | all | 2 | 100.0000 | 7.59872526 | 3.72980613 | 3.71740243 | false |
| 24 | SOXL-USDT-SWAP | rsi_revert | trend | 1 | 100.0000 | 7.16194791 | 7.16194791 | 7.16194791 | false |
| 25 | SOL-USDT-SWAP | rsi_revert | trend_high_vol | 5 | 60.0000 | 10.48787367 | 0.61127658 | -0.00002252 | true |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | ema_cross | all | 1.39505967 | -1.13945992 | 0.662514 | 1.98987084 | false |
| 1 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 1.39505967 | -1.13945992 | 0.662514 | 1.98987084 | false |
| 1 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 1.39505967 | -1.13945992 | 0.662514 | 1.98987084 | false |
| 2 | 1 | ETH-USDT-SWAP | ema_cross_atr_band | all | 4.54616075 | -3.09124980 | 0.242316 | 3.69532271 | false |
| 2 | 2 | ETH-USDT-SWAP | ema_cross_atr_band | normal_vol | 4.54616075 | -3.09124980 | 0.242316 | 3.69532271 | false |
| 2 | 3 | ETH-USDT-SWAP | ema_cross_atr_band | range_normal_vol | 4.54616075 | -3.09124980 | 0.242316 | 3.69532271 | false |
| 3 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.84811261 | 0.97940210 | 1.593101 | 2.76865147 | true |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 5.84811261 | 0.97940210 | 1.593101 | 2.76865147 | true |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 5.84811261 | 0.97940210 | 1.593101 | 2.76865147 | true |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | all | 3.97443265 | -3.75003043 | 0.000000 | 3.78624555 | false |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 3.97443265 | -3.75003043 | 0.000000 | 3.78624555 | false |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 3.97443265 | -3.75003043 | 0.000000 | 3.78624555 | false |
| 9 | 1 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 2.76393273 | -2.79292109 | 0.773231 | 7.56649051 | false |
| 9 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 1.06558453 | 0.23989303 | 999.000000 | 0.97766219 | false |
| 9 | 3 | ETH-USDT-SWAP | ema_cross | all | 3.02080100 | -2.88343809 | 0.716114 | 7.53922283 | false |
| 10 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 11.97397088 | 6.81548497 | 999.000000 | 4.28228028 | false |
| 10 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 9.21063487 | 4.87093373 | 2.671626 | 3.59865423 | true |
| 10 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 6.37900154 | 1.46883963 | 1.451582 | 3.89889548 | true |
| 11 | 1 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 15.01108867 | 0.41089896 | 1.356609 | 3.66739648 | true |
| 11 | 2 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 15.34554176 | 0.41089896 | 1.356609 | 3.66739648 | true |
| 11 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 8.94551726 | 0.34895668 | 1.328765 | 3.25906396 | true |
| 12 | 1 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 13.59937100 | -11.42074485 | 0.036453 | 12.06004221 | false |
| 12 | 2 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 13.92971880 | -11.42074485 | 0.036453 | 12.06004221 | false |
| 12 | 3 | ETH-USDT-SWAP | rsi_revert | all | 9.46023206 | 2.24584196 | 62.485248 | 1.90802416 | true |
| 13 | 1 | ETH-USDT-SWAP | rsi_revert | all | 10.72064336 | -0.49299238 | 0.000000 | 2.37910007 | false |
