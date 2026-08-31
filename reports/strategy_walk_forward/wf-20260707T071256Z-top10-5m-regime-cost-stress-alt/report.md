# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 603 |
| Passed window rows | 117 |
| Unique aggregate candidates | 422 |
| Passed aggregate candidates | 4 |
| Median selected test return | -1.013417% |
| Mean selected test return | -0.874942% |
| Best aggregate return | 67.999691% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross | all | 4 | 50.0000 | 67.99969116 | 17.30967939 | -4.08799755 | false |
| 2 | LAB-USDT-SWAP | ema_cross | trend | 2 | 0.0000 | 61.09014959 | 50.95720762 | -30.76833046 | false |
| 3 | LAB-USDT-SWAP | ema_cross | high_vol | 2 | 50.0000 | 45.61389316 | 20.84230298 | 14.40235937 | false |
| 4 | LAB-USDT-SWAP | ema_cross | trend | 1 | 0.0000 | 53.07332193 | 53.07332193 | 53.07332193 | false |
| 5 | LAB-USDT-SWAP | ema_cross | trend | 1 | 0.0000 | 53.07332193 | 53.07332193 | 53.07332193 | false |
| 6 | LAB-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 23.59499379 | 23.59499379 | 23.59499379 | false |
| 7 | LAB-USDT-SWAP | ema_cross | trend_high_vol | 3 | 33.3333 | 40.28103290 | 14.91008991 | -4.08799755 | false |
| 8 | LAB-USDT-SWAP | macd_signal | trend_down | 3 | 66.6667 | 28.19613759 | 8.57302650 | 6.66888807 | true |
| 9 | LAB-USDT-SWAP | ema_cross | high_vol | 2 | 50.0000 | 21.82227389 | 11.53473277 | -4.52046028 | false |
| 10 | SNDK-USDT-SWAP | rsi_trend | high_vol | 1 | 100.0000 | 7.06574463 | 7.06574463 | 7.06574463 | false |
| 11 | LAB-USDT-SWAP | atr_vol_breakout | trend_up | 2 | 50.0000 | 16.59989055 | 8.18246077 | 1.59036219 | false |
| 12 | LAB-USDT-SWAP | atr_vol_breakout | trend_up | 2 | 50.0000 | 16.39601711 | 8.04034923 | 2.28575542 | false |
| 13 | SNDK-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 7.58230138 | 7.58230138 | 7.58230138 | false |
| 14 | HYPE-USDT-SWAP | bollinger_revert | range_normal_vol | 2 | 100.0000 | 2.94558193 | 1.46295386 | 1.04724638 | false |
| 15 | HYPE-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 4.05068484 | 4.05068484 | 4.05068484 | false |
| 16 | DOGE-USDT-SWAP | ema_cross | range_normal_vol | 1 | 100.0000 | 3.39119179 | 3.39119179 | 3.39119179 | false |
| 17 | HYPE-USDT-SWAP | rsi_revert | trend | 3 | 100.0000 | 2.96464154 | 1.24070068 | 0.04005773 | true |
| 18 | LAB-USDT-SWAP | ema_cross | trend_down | 2 | 50.0000 | 11.18349028 | 6.06463167 | -5.39647927 | false |
| 19 | SPCX-USDT-SWAP | rsi_trend | high_vol | 1 | 100.0000 | 2.72494021 | 2.72494021 | 2.72494021 | false |
| 20 | ETH-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 2.36961888 | 2.36961888 | 2.36961888 | false |
| 21 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 1 | 100.0000 | 2.36961888 | 2.36961888 | 2.36961888 | false |
| 22 | HYPE-USDT-SWAP | ema_cross | range_normal_vol | 1 | 100.0000 | 2.26173309 | 2.26173309 | 2.26173309 | false |
| 23 | SKHYNIX-USDT-SWAP | rsi_revert | all | 1 | 100.0000 | 2.18344247 | 2.18344247 | 2.18344247 | false |
| 24 | ETH-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 1.29083404 | 1.29083404 | 1.29083404 | false |
| 25 | ETH-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 1.29083404 | 1.29083404 | 1.29083404 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | rsi_trend | trend | 5.77189972 | -3.92696150 | 0.187962 | 4.34691334 | false |
| 1 | 2 | ETH-USDT-SWAP | rsi_trend | trend_high_vol | 5.77189972 | -3.92696150 | 0.187962 | 4.34691334 | false |
| 1 | 3 | ETH-USDT-SWAP | rsi_trend | trend_up | 5.50930648 | -1.02167411 | 0.385464 | 2.13689195 | false |
| 2 | 1 | ETH-USDT-SWAP | ema_cross | all | 10.33429924 | -6.40099909 | 0.158593 | 6.51990767 | false |
| 2 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 10.33429924 | -6.40099909 | 0.158593 | 6.51990767 | false |
| 2 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 10.33429924 | -6.40099909 | 0.158593 | 6.51990767 | false |
| 3 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.92137467 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 3 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.26028016 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 3 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 4.15958574 | -1.83602759 | 0.348427 | 3.04658452 | false |
| 4 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.36610691 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 4 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.36610691 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 4 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 2.54564774 | -1.65343156 | 0.192703 | 2.81877563 | false |
| 5 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.95603662 | 0.01473511 | 999.000000 | 0.10931659 | false |
| 5 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.84621109 | 0.84242886 | 4.029489 | 0.88322787 | true |
| 5 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 0.84621109 | 0.84242886 | 4.029489 | 0.88322787 | true |
| 6 | 1 | ETH-USDT-SWAP | bollinger_revert | trend_up | 1.05984468 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 6 | 2 | ETH-USDT-SWAP | bollinger_revert | trend_up | 1.18584885 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 6 | 3 | ETH-USDT-SWAP | bollinger_revert | trend_up | 0.74053756 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | all | 0.26401096 | -0.12531811 | 1.374499 | 1.26858509 | false |
| 7 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.26401096 | -0.12531811 | 1.374499 | 1.26858509 | false |
| 7 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 0.26401096 | -0.12531811 | 1.374499 | 1.26858509 | false |
| 8 | 1 | ETH-USDT-SWAP | bollinger_revert | trend_down | 0.32024875 | -3.57150362 | 0.025897 | 4.34063040 | false |
| 8 | 2 | ETH-USDT-SWAP | rsi_revert | all | 0.72982778 | -3.62494858 | 0.001652 | 4.43298581 | false |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.72982778 | -3.62494858 | 0.001652 | 4.43298581 | false |
| 9 | 1 | ETH-USDT-SWAP | ema_cross | all | 2.55203277 | -1.36906315 | 0.847683 | 6.80775304 | false |
