# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1076 |
| Passed window rows | 222 |
| Unique aggregate candidates | 637 |
| Passed aggregate candidates | 6 |
| Median selected test return | -0.972296% |
| Mean selected test return | -1.862408% |
| Best aggregate return | 35.698962% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 35.69896166 | 35.69896166 | 35.69896166 | false |
| 2 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 1 | 100.0000 | 31.61717728 | 31.61717728 | 31.61717728 | false |
| 3 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 2 | 0.0000 | 34.10026826 | 17.29363507 | -1.35495745 | false |
| 4 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 50.0000 | 28.30467162 | 14.55020211 | -2.51677306 | false |
| 5 | LAB-USDT-SWAP | atr_vol_breakout | trend_high_vol | 1 | 0.0000 | 32.98386530 | 32.98386530 | 32.98386530 | false |
| 6 | SOL-USDT-SWAP | rsi_revert | trend_high_vol | 6 | 83.3333 | 14.94500813 | 1.27835894 | -2.75013036 | true |
| 7 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 2 | 50.0000 | 28.53002773 | 14.04603764 | 1.65669028 | false |
| 8 | SOL-USDT-SWAP | rsi_revert | trend | 2 | 100.0000 | 10.16530166 | 5.01829563 | 1.50941397 | false |
| 9 | SOL-USDT-SWAP | rsi_revert | trend_down | 2 | 100.0000 | 10.17349495 | 5.00928800 | 1.91072832 | false |
| 10 | LAB-USDT-SWAP | rsi_revert | range | 4 | 75.0000 | 11.55469504 | 2.44281006 | -0.13226272 | true |
| 11 | LAB-USDT-SWAP | rsi_revert | range_normal_vol | 4 | 75.0000 | 11.55469504 | 2.44281006 | -0.13226272 | true |
| 12 | LAB-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 8.99934069 | 8.99934069 | 8.99934069 | false |
| 13 | SOL-USDT-SWAP | ema_cross_atr_band | normal_vol | 2 | 100.0000 | 8.75558039 | 4.29891234 | 2.65420052 | false |
| 14 | EDGE-USDT-SWAP | macd_signal | high_vol | 5 | 40.0000 | 19.73598253 | 3.11747748 | -10.66294263 | false |
| 15 | MU-USDT-SWAP | rsi_revert | high_vol | 1 | 100.0000 | 8.39323267 | 8.39323267 | 8.39323267 | false |
| 16 | EDGE-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 4.88508693 | 4.88508693 | 4.88508693 | false |
| 17 | ZEC-USDT-SWAP | bollinger_revert | trend_down | 2 | 100.0000 | 4.19239757 | 2.07975993 | 1.06111867 | false |
| 18 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 8.50958108 | 8.50958108 | 8.50958108 | false |
| 19 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 8.50958108 | 8.50958108 | 8.50958108 | false |
| 20 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 8.50958108 | 8.50958108 | 8.50958108 | false |
| 21 | DOGE-USDT-SWAP | rsi_revert | trend_high_vol | 7 | 42.8571 | 11.73600229 | 1.98880775 | -1.12690215 | false |
| 22 | ZEC-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 3.25316076 | 3.25316076 | 3.25316076 | false |
| 23 | DOGE-USDT-SWAP | rsi_revert | all | 6 | 50.0000 | 10.38833843 | 0.20782507 | -0.85853000 | false |
| 24 | EDGE-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 2.76060103 | 2.76060103 | 2.76060103 | false |
| 25 | EDGE-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 2.50788067 | 2.50788067 | 2.50788067 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | ema_cross | all | 1.10246273 | -0.97398139 | 0.586002 | 3.53926961 | false |
| 1 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 1.10246273 | -0.97398139 | 0.586002 | 3.53926961 | false |
| 1 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 1.10246273 | -0.97398139 | 0.586002 | 3.53926961 | false |
| 2 | 1 | ETH-USDT-SWAP | ema_cross | all | 2.84851368 | -2.27299222 | 0.400946 | 3.72751549 | false |
| 2 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 2.84851368 | -2.27299222 | 0.400946 | 3.72751549 | false |
| 2 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 2.84851368 | -2.27299222 | 0.400946 | 3.72751549 | false |
| 3 | 1 | ETH-USDT-SWAP | ema_cross | all | 3.95225607 | 1.26393333 | 2.150954 | 1.82660693 | true |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 3.95225607 | 1.26393333 | 2.150954 | 1.82660693 | true |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 3.95225607 | 1.26393333 | 2.150954 | 1.82660693 | true |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.24939357 | -2.43155786 | 0.389405 | 3.39161883 | false |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 5.24939357 | -2.43155786 | 0.389405 | 3.39161883 | false |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 5.24939357 | -2.43155786 | 0.389405 | 3.39161883 | false |
| 5 | 1 | ETH-USDT-SWAP | ema_cross | all | 0.50921987 | -2.61883413 | 0.053262 | 3.34402406 | false |
| 5 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 0.50921987 | -2.61883413 | 0.053262 | 3.34402406 | false |
| 5 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 0.50921987 | -2.61883413 | 0.053262 | 3.34402406 | false |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | all | 0.16001469 | 0.21982910 | 1.335746 | 2.18862433 | true |
| 8 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.16001469 | 0.21982910 | 1.335746 | 2.18862433 | true |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 0.16001469 | 0.21982910 | 1.335746 | 2.18862433 | true |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | trend_down | 1.40851060 | -1.04877198 | 0.952130 | 3.55916662 | false |
| 9 | 2 | ETH-USDT-SWAP | rsi_revert | all | 0.48497578 | 1.41045820 | 43.142276 | 4.67272216 | true |
| 9 | 3 | ETH-USDT-SWAP | rsi_revert | normal_vol | 0.48497578 | 0.93980891 | 999.000000 | 0.73639321 | false |
| 10 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 6.82662761 | 12.36295061 | 999.000000 | 3.74467499 | false |
| 10 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 4.75827844 | 5.69099700 | 2.919596 | 3.59865423 | true |
| 10 | 3 | ETH-USDT-SWAP | macd_signal | high_vol | 2.40788558 | 2.82478113 | 2.325828 | 4.31987809 | true |
| 11 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 19.75821602 | 1.95452367 | 2.247724 | 4.99697819 | false |
