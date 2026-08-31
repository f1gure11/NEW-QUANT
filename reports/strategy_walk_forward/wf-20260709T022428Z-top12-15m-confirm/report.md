# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1764 |
| Passed window rows | 305 |
| Unique aggregate candidates | 1033 |
| Passed aggregate candidates | 15 |
| Median selected test return | -0.540803% |
| Mean selected test return | -1.425540% |
| Best aggregate return | 102.127859% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 97.03526906 | 97.03526906 | 97.03526906 | false |
| 2 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 95.45380588 | 95.45380588 | 95.45380588 | false |
| 3 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 3 | 66.6667 | 102.12785941 | 2.72648075 | 0.66989953 | true |
| 4 | EDGE-USDT-SWAP | ema_cross_atr_band | trend_up | 1 | 100.0000 | 50.82761059 | 50.82761059 | 50.82761059 | false |
| 5 | EDGE-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 50.82761059 | 50.82761059 | 50.82761059 | false |
| 6 | EDGE-USDT-SWAP | ema_cross_atr_band | trend_up | 1 | 100.0000 | 50.82761059 | 50.82761059 | 50.82761059 | false |
| 7 | LAB-USDT-SWAP | rsi_trend | trend | 1 | 0.0000 | 49.60746344 | 49.60746344 | 49.60746344 | false |
| 8 | LAB-USDT-SWAP | keltner_breakout | trend | 1 | 0.0000 | 39.74464109 | 39.74464109 | 39.74464109 | false |
| 9 | LAB-USDT-SWAP | keltner_breakout | trend_high_vol | 2 | 0.0000 | 41.31198323 | 26.91849206 | -17.54616024 | false |
| 10 | EDGE-USDT-SWAP | donchian_breakout | trend_down | 1 | 0.0000 | 36.27392513 | 36.27392513 | 36.27392513 | false |
| 11 | MU-USDT-SWAP | rsi_revert | all | 7 | 57.1429 | 20.23496712 | 1.68599708 | -0.89633796 | false |
| 12 | MU-USDT-SWAP | rsi_revert | trend_down | 3 | 66.6667 | 18.47692097 | 3.38894302 | 0.17922580 | true |
| 13 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 3 | 66.6667 | 16.65809541 | 6.25380923 | 0.00000000 | true |
| 14 | SOXL-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 12.76052529 | 12.76052529 | 12.76052529 | false |
| 15 | SKHYNIX-USDT-SWAP | keltner_breakout | all | 1 | 100.0000 | 8.11009836 | 8.11009836 | 8.11009836 | false |
| 16 | EDGE-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 100.0000 | 10.38248777 | 5.08047729 | 3.16790561 | false |
| 17 | SNDK-USDT-SWAP | atr_vol_breakout | high_vol | 1 | 100.0000 | 8.78830857 | 8.78830857 | 8.78830857 | false |
| 18 | LAB-USDT-SWAP | donchian_breakout | mixed | 1 | 100.0000 | 6.32627644 | 6.32627644 | 6.32627644 | false |
| 19 | MU-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 17.97185794 | 17.97185794 | 17.97185794 | false |
| 20 | MU-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 17.97185794 | 17.97185794 | 17.97185794 | false |
| 21 | MU-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 17.97185794 | 17.97185794 | 17.97185794 | false |
| 22 | SOXL-USDT-SWAP | ema_cross_atr_band | trend_down | 2 | 50.0000 | 14.93414779 | 7.48555533 | -0.24295198 | false |
| 23 | MU-USDT-SWAP | rsi_revert | trend_high_vol | 7 | 57.1429 | 12.07303818 | 0.36001391 | -1.02169225 | false |
| 24 | SOXL-USDT-SWAP | rsi_revert | trend | 3 | 66.6667 | 12.56134120 | 4.74272657 | 0.00000000 | true |
| 25 | SOXL-USDT-SWAP | atr_vol_breakout | all | 4 | 50.0000 | 15.50758577 | 2.36255525 | -1.72836839 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 2.67436673 | -2.15783031 | 0.151389 | 3.11889057 | false |
| 1 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 2.67436673 | -2.15783031 | 0.151389 | 3.11889057 | false |
| 1 | 3 | ETH-USDT-SWAP | ema_cross | normal_vol | 2.67040431 | -0.55174813 | 0.756479 | 2.41892256 | false |
| 2 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.84713825 | -0.04736469 | 8.729302 | 0.52714589 | false |
| 2 | 2 | ETH-USDT-SWAP | keltner_breakout | normal_vol | 2.68515541 | -1.37405297 | 0.311051 | 2.98832608 | false |
| 2 | 3 | ETH-USDT-SWAP | keltner_breakout | range_normal_vol | 2.68515541 | -1.37405297 | 0.311051 | 2.98832608 | false |
| 3 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.65546316 | -0.16843565 | 0.000000 | 0.23991028 | false |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 1.93362076 | -1.12128472 | 0.209213 | 2.22735883 | false |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 1.93362076 | -1.12128472 | 0.209213 | 2.22735883 | false |
| 4 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.48592347 | -1.40318366 | 0.180610 | 1.32077408 | false |
| 4 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | normal_vol | 1.89423041 | -1.88736814 | 0.247180 | 2.54829090 | false |
| 4 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | range_normal_vol | 1.89423041 | -1.88736814 | 0.247180 | 2.54829090 | false |
| 5 | 1 | ETH-USDT-SWAP | rsi_revert | all | 2.79431732 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 5 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 2.79431732 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 5 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 2.79431732 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 6 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.24358470 | 2.25580415 | 6.310934 | 0.88070688 | true |
| 6 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 3.24358470 | 2.25580415 | 6.310934 | 0.88070688 | true |
| 6 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 3.24358470 | 2.25580415 | 6.310934 | 0.88070688 | true |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | all | 5.65962629 | 0.25534862 | 3.214547 | 0.62810775 | true |
| 7 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 5.65962629 | 0.25534862 | 3.214547 | 0.62810775 | true |
| 7 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 5.65962629 | 0.25534862 | 3.214547 | 0.62810775 | true |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | all | 5.66290328 | -0.22371419 | 0.678838 | 0.44268532 | false |
| 8 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 5.66290328 | -0.22371419 | 0.678838 | 0.44268532 | false |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 5.66290328 | -0.22371419 | 0.678838 | 0.44268532 | false |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | all | 2.82043541 | 0.09974683 | 2.359121 | 1.21927417 | false |
