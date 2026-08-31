# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1509 |
| Passed window rows | 277 |
| Unique aggregate candidates | 883 |
| Passed aggregate candidates | 16 |
| Median selected test return | -0.616470% |
| Mean selected test return | -1.380739% |
| Best aggregate return | 102.127859% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 97.03526906 | 97.03526906 | 97.03526906 | false |
| 2 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 95.45380588 | 95.45380588 | 95.45380588 | false |
| 3 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 3 | 66.6667 | 102.12785941 | 2.72648075 | 0.66989953 | true |
| 4 | HYPE-USDT-SWAP | atr_vol_breakout | all | 5 | 100.0000 | 47.94842320 | 7.19605500 | 2.10648927 | true |
| 5 | HYPE-USDT-SWAP | atr_vol_breakout | trend_high_vol | 5 | 100.0000 | 47.94842320 | 7.19605500 | 2.10648927 | true |
| 6 | HYPE-USDT-SWAP | atr_vol_breakout | high_vol | 4 | 100.0000 | 38.91664021 | 9.57864594 | 2.10648927 | true |
| 7 | LAB-USDT-SWAP | keltner_breakout | trend_high_vol | 2 | 0.0000 | 56.67872383 | 26.24498421 | 9.81563073 | false |
| 8 | LAB-USDT-SWAP | keltner_breakout | all | 3 | 0.0000 | 40.51033188 | 9.81563073 | -10.31945599 | false |
| 9 | LAB-USDT-SWAP | keltner_breakout | high_vol | 3 | 0.0000 | 40.51033188 | 9.81563073 | -10.31945599 | false |
| 10 | LAB-USDT-SWAP | keltner_breakout | trend_down | 2 | 0.0000 | 31.86105343 | 17.05380321 | -5.65054667 | false |
| 11 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 0.0000 | 32.44599869 | 18.72803275 | -10.45665318 | false |
| 12 | MU-USDT-SWAP | rsi_revert | trend_high_vol | 6 | 66.6667 | 18.31880137 | 2.84587374 | -0.75678992 | true |
| 13 | LAB-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 11.81653177 | 11.81653177 | 11.81653177 | false |
| 14 | MU-USDT-SWAP | rsi_revert | all | 6 | 50.0000 | 18.84525558 | 2.89435065 | -0.87152577 | false |
| 15 | MU-USDT-SWAP | rsi_revert | trend_down | 3 | 66.6667 | 14.88755662 | 6.28590131 | 0.48850317 | true |
| 16 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 3 | 66.6667 | 16.65809541 | 6.25380923 | 0.00000000 | true |
| 17 | HYPE-USDT-SWAP | ema_cross | range_normal_vol | 3 | 100.0000 | 8.90242065 | 2.98043456 | 0.47715117 | true |
| 18 | MU-USDT-SWAP | ema_cross_atr_band | trend_up | 4 | 50.0000 | 16.19399757 | 1.85114048 | -2.69949681 | false |
| 19 | SKHYNIX-USDT-SWAP | keltner_breakout | all | 1 | 100.0000 | 8.11009836 | 8.11009836 | 8.11009836 | false |
| 20 | DOGE-USDT-SWAP | donchian_breakout | trend_down | 2 | 100.0000 | 8.99216538 | 4.43680933 | 1.63848749 | false |
| 21 | MU-USDT-SWAP | bollinger_revert | all | 3 | 100.0000 | 7.72973065 | 2.72371710 | 0.70793265 | true |
| 22 | HYPE-USDT-SWAP | ema_cross | range_normal_vol | 2 | 100.0000 | 5.67776982 | 2.82817925 | 0.40795905 | false |
| 23 | SNDK-USDT-SWAP | ema_cross | trend_up | 1 | 100.0000 | 4.57830343 | 4.57830343 | 4.57830343 | false |
| 24 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 3 | 66.6667 | 12.60398012 | 6.25380923 | -3.31537942 | false |
| 25 | HYPE-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 4.21866132 | 4.21866132 | 4.21866132 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | bollinger_revert | range | 0.63637857 | -1.53217599 | 0.426727 | 1.53217599 | false |
| 1 | 2 | ETH-USDT-SWAP | rsi_revert | all | 2.07968359 | -0.61647022 | 0.694665 | 1.32737857 | false |
| 1 | 3 | ETH-USDT-SWAP | rsi_revert | normal_vol | 2.07968359 | -0.61647022 | 0.694665 | 1.32737857 | false |
| 2 | 1 | ETH-USDT-SWAP | rsi_revert | trend | 0.80673534 | -1.31791842 | 0.593951 | 2.75035914 | false |
| 2 | 2 | ETH-USDT-SWAP | rsi_revert | trend_high_vol | 0.80673534 | -1.02671480 | 0.596279 | 2.75035914 | false |
| 2 | 3 | ETH-USDT-SWAP | macd_signal | trend_up | 0.57534778 | -0.45272749 | 0.000000 | 0.45272749 | false |
| 3 | 1 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 2.69454342 | -1.12223662 | 0.390483 | 2.23394566 | false |
| 3 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 2.69454342 | -1.12223662 | 0.390483 | 2.23394566 | false |
| 3 | 3 | ETH-USDT-SWAP | rsi_revert | trend_up | 1.13658976 | -0.69209664 | 0.390779 | 1.07473037 | false |
| 4 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.65546316 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 4 | 2 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.01638239 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 4 | 3 | ETH-USDT-SWAP | rsi_revert | all | 1.02810996 | 0.62363304 | 999.000000 | 0.35871476 | false |
| 5 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.65546316 | -0.97731786 | 0.275981 | 1.02230461 | false |
| 5 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | normal_vol | 0.45432062 | -1.77203898 | 0.307238 | 2.74828329 | false |
| 5 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | range_normal_vol | 0.45432062 | -1.77203898 | 0.307238 | 2.74828329 | false |
| 6 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.09430957 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 6 | 2 | ETH-USDT-SWAP | rsi_revert | all | 3.06328233 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 6 | 3 | ETH-USDT-SWAP | bollinger_revert | all | 2.32152931 | 0.68461211 | 6.359065 | 0.91893272 | true |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.01815083 | 1.43152516 | 5.936290 | 0.88070688 | true |
| 7 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 3.01815083 | 1.43152516 | 5.936290 | 0.88070688 | true |
| 7 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 3.01815083 | 1.43152516 | 5.936290 | 0.88070688 | true |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | all | 4.80790925 | 0.50400304 | 4.070945 | 0.67393069 | true |
| 8 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 4.80790925 | 0.50400304 | 4.070945 | 0.67393069 | true |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 4.80790925 | 0.50400304 | 4.070945 | 0.67393069 | true |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | all | 4.91399855 | 0.84032193 | 999.000000 | 0.52988939 | false |
