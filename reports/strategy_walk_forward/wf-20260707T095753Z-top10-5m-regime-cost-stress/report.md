# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 890 |
| Passed window rows | 208 |
| Unique aggregate candidates | 532 |
| Passed aggregate candidates | 11 |
| Median selected test return | -0.599091% |
| Mean selected test return | -1.455261% |
| Best aggregate return | 51.308117% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | atr_vol_breakout | trend_high_vol | 1 | 0.0000 | 51.30811724 | 51.30811724 | 51.30811724 | false |
| 2 | LAB-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 29.74435510 | 29.74435510 | 29.74435510 | false |
| 3 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 1 | 100.0000 | 26.02019400 | 26.02019400 | 26.02019400 | false |
| 4 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 4 | 75.0000 | 22.22335322 | 5.89110231 | 1.03242000 | true |
| 5 | SOL-USDT-SWAP | rsi_revert | trend_high_vol | 6 | 83.3333 | 14.94500813 | 1.27835894 | -2.75013036 | true |
| 6 | HYPE-USDT-SWAP | ema_cross_atr_band | high_vol | 1 | 100.0000 | 10.51328745 | 10.51328745 | 10.51328745 | false |
| 7 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 50.0000 | 23.78525291 | 12.12335773 | -1.77347853 | false |
| 8 | SOL-USDT-SWAP | rsi_revert | trend | 2 | 100.0000 | 10.16530166 | 5.01829563 | 1.50941397 | false |
| 9 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 2 | 100.0000 | 12.09897725 | 5.88425895 | 4.62784759 | false |
| 10 | SOL-USDT-SWAP | rsi_revert | trend_down | 2 | 100.0000 | 10.17349495 | 5.00928800 | 1.91072832 | false |
| 11 | LAB-USDT-SWAP | rsi_revert | range | 4 | 75.0000 | 11.55469504 | 2.44281006 | -0.13226272 | true |
| 12 | LAB-USDT-SWAP | rsi_revert | range_normal_vol | 4 | 75.0000 | 11.55469504 | 2.44281006 | -0.13226272 | true |
| 13 | LAB-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 8.99934069 | 8.99934069 | 8.99934069 | false |
| 14 | HYPE-USDT-SWAP | ema_cross_atr_band | high_vol | 1 | 100.0000 | 8.10082676 | 8.10082676 | 8.10082676 | false |
| 15 | SOL-USDT-SWAP | ema_cross_atr_band | normal_vol | 2 | 100.0000 | 8.52818636 | 4.18537047 | 2.85391095 | false |
| 16 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 10.41597839 | 10.41597839 | 10.41597839 | false |
| 17 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 10.41597839 | 10.41597839 | 10.41597839 | false |
| 18 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 10.41597839 | 10.41597839 | 10.41597839 | false |
| 19 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 3 | 66.6667 | 13.28521082 | 3.37827200 | 1.71390518 | true |
| 20 | MU-USDT-SWAP | rsi_revert | high_vol | 1 | 100.0000 | 8.39323267 | 8.39323267 | 8.39323267 | false |
| 21 | DOGE-USDT-SWAP | rsi_revert | trend_high_vol | 7 | 57.1429 | 11.73600229 | 1.98880775 | -1.39282044 | false |
| 22 | SPCX-USDT-SWAP | macd_signal | high_vol | 4 | 75.0000 | 10.17617072 | 3.13312116 | 0.00000000 | true |
| 23 | MU-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 3.82469350 | 3.82469350 | 3.82469350 | false |
| 24 | DOGE-USDT-SWAP | rsi_revert | trend | 4 | 75.0000 | 7.33092516 | 1.58485464 | 0.23614797 | true |
| 25 | DOGE-USDT-SWAP | rsi_revert | all | 6 | 50.0000 | 10.26752262 | 0.20848863 | -0.96731542 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 3 | 1 | ETH-USDT-SWAP | ema_cross | all | 3.26952725 | -2.35911763 | 0.369750 | 3.72983570 | false |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 3.26952725 | -2.35911763 | 0.369750 | 3.72983570 | false |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 3.26952725 | -2.35911763 | 0.369750 | 3.72983570 | false |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | all | 4.02849321 | 1.22731104 | 2.101206 | 1.82660693 | true |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 4.02849321 | 1.22731104 | 2.101206 | 1.82660693 | true |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 4.02849321 | 1.22731104 | 2.101206 | 1.82660693 | true |
| 5 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.18197513 | -2.49885188 | 0.369947 | 3.39161883 | false |
| 5 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 5.18197513 | -2.49885188 | 0.369947 | 3.39161883 | false |
| 5 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 5.18197513 | -2.49885188 | 0.369947 | 3.39161883 | false |
| 6 | 1 | ETH-USDT-SWAP | ema_cross | all | 0.31994524 | -2.58972619 | 0.042853 | 3.34398810 | false |
| 6 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 0.31994524 | -2.58972619 | 0.042853 | 3.34398810 | false |
| 6 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 0.31994524 | -2.58972619 | 0.042853 | 3.34398810 | false |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | all | 0.16001469 | 0.21982910 | 1.335746 | 2.18862433 | true |
| 9 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.16001469 | 0.21982910 | 1.335746 | 2.18862433 | true |
| 9 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 0.16001469 | 0.21982910 | 1.335746 | 2.18862433 | true |
| 10 | 1 | ETH-USDT-SWAP | rsi_revert | trend_down | 1.40851060 | -1.04877198 | 0.952130 | 3.55916662 | false |
| 10 | 2 | ETH-USDT-SWAP | rsi_revert | all | 0.48497578 | 1.41045820 | 43.142276 | 4.67272216 | true |
| 10 | 3 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.48497578 | 0.93980891 | 999.000000 | 0.73639321 | false |
| 11 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 6.58888978 | 11.66575977 | 999.000000 | 3.72647709 | false |
| 11 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 4.50009327 | 4.86378149 | 2.675485 | 3.59865423 | true |
| 11 | 3 | ETH-USDT-SWAP | macd_signal | high_vol | 2.40788558 | 2.82478113 | 2.325828 | 4.31987809 | true |
| 12 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 18.70820127 | 3.24028232 | 6.472215 | 4.89638825 | false |
| 12 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 10.49225209 | 7.40766041 | 36.415952 | 2.29552481 | true |
| 12 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 9.73179402 | 2.81142109 | 1.877109 | 4.80426633 | true |
| 13 | 1 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 21.65749335 | -13.34585377 | 0.039766 | 14.80852009 | false |
