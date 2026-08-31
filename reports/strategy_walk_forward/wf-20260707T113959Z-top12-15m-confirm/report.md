# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1800 |
| Passed window rows | 309 |
| Unique aggregate candidates | 1038 |
| Passed aggregate candidates | 16 |
| Median selected test return | -0.608127% |
| Mean selected test return | -1.350621% |
| Best aggregate return | 102.127859% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 97.03526906 | 97.03526906 | 97.03526906 | false |
| 2 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 1 | 100.0000 | 95.45380588 | 95.45380588 | 95.45380588 | false |
| 3 | SPCX-USDT-SWAP | ema_cross_atr_band | normal_vol | 3 | 66.6667 | 102.12785941 | 2.72648075 | 0.66989953 | true |
| 4 | HYPE-USDT-SWAP | atr_vol_breakout | all | 6 | 83.3333 | 46.86990472 | 6.20714521 | -1.78841166 | true |
| 5 | LAB-USDT-SWAP | keltner_breakout | trend_high_vol | 2 | 0.0000 | 61.23225680 | 27.14793576 | 20.56220214 | false |
| 6 | LAB-USDT-SWAP | keltner_breakout | all | 3 | 0.0000 | 46.97659331 | 20.56220214 | -8.84169444 | false |
| 7 | LAB-USDT-SWAP | keltner_breakout | high_vol | 3 | 0.0000 | 46.97659331 | 20.56220214 | -8.84169444 | false |
| 8 | HYPE-USDT-SWAP | ema_cross_atr_band | trend | 1 | 100.0000 | 14.65346745 | 14.65346745 | 14.65346745 | false |
| 9 | HYPE-USDT-SWAP | atr_vol_breakout | high_vol | 5 | 80.0000 | 21.79648346 | 5.82384261 | -1.78841166 | true |
| 10 | HYPE-USDT-SWAP | atr_vol_breakout | trend_high_vol | 5 | 80.0000 | 20.47392218 | 4.67472473 | -1.78841166 | true |
| 11 | SNDK-USDT-SWAP | rsi_trend | trend_up | 1 | 100.0000 | 10.05776123 | 10.05776123 | 10.05776123 | false |
| 12 | LAB-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 12.50998489 | 12.50998489 | 12.50998489 | false |
| 13 | LAB-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 9.50749038 | 9.50749038 | 9.50749038 | false |
| 14 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 0.0000 | 28.05505987 | 17.50904498 | -14.15907250 | false |
| 15 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 3 | 66.6667 | 16.65809541 | 6.25380923 | 0.00000000 | true |
| 16 | LAB-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 9.94042719 | 9.94042719 | 9.94042719 | false |
| 17 | MU-USDT-SWAP | rsi_revert | trend_down | 3 | 66.6667 | 13.83689725 | 3.86080157 | -0.65928912 | true |
| 18 | XRP-USDT-SWAP | rsi_trend | trend_high_vol | 1 | 100.0000 | 7.22883305 | 7.22883305 | 7.22883305 | false |
| 19 | SKHYNIX-USDT-SWAP | keltner_breakout | all | 1 | 100.0000 | 8.11009836 | 8.11009836 | 8.11009836 | false |
| 20 | HYPE-USDT-SWAP | ema_cross | range_normal_vol | 3 | 100.0000 | 7.89350567 | 3.27390720 | 0.01528172 | true |
| 21 | MU-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 7.55287571 | 7.55287571 | 7.55287571 | false |
| 22 | MU-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 7.55287571 | 7.55287571 | 7.55287571 | false |
| 23 | MU-USDT-SWAP | ema_cross | trend_up | 1 | 0.0000 | 16.31779533 | 16.31779533 | 16.31779533 | false |
| 24 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 3 | 66.6667 | 12.60398012 | 6.25380923 | -3.31537942 | false |
| 25 | LAB-USDT-SWAP | donchian_breakout | mixed | 1 | 100.0000 | 4.27431566 | 4.27431566 | 4.27431566 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | bollinger_revert | range | 0.33103154 | -1.01380927 | 0.617288 | 1.01380927 | false |
| 1 | 2 | ETH-USDT-SWAP | rsi_revert | trend | 0.24793073 | -1.00346432 | 0.657321 | 2.75076541 | false |
| 1 | 3 | ETH-USDT-SWAP | rsi_revert | trend_high_vol | 0.24793073 | -1.00346432 | 0.657321 | 2.75076541 | false |
| 2 | 1 | ETH-USDT-SWAP | keltner_breakout | all | 2.41730325 | -2.85048688 | 0.000000 | 3.25108730 | false |
| 2 | 2 | ETH-USDT-SWAP | keltner_breakout | normal_vol | 2.41730325 | -1.57178453 | 0.211568 | 1.97765774 | false |
| 2 | 3 | ETH-USDT-SWAP | keltner_breakout | range_normal_vol | 2.41730325 | -1.57178453 | 0.211568 | 1.97765774 | false |
| 3 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 1.13658976 | -0.69209664 | 0.390779 | 1.07473037 | false |
| 3 | 2 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 2.29127885 | -0.68645826 | 0.603391 | 1.97169719 | false |
| 3 | 3 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 2.29127885 | -0.68645826 | 0.603391 | 1.97169719 | false |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | normal_vol | 3.61699690 | -0.77854285 | 0.475723 | 2.22736052 | false |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 3.61699690 | -0.77854285 | 0.475723 | 2.22736052 | false |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | normal_vol | 3.08959102 | -3.99166774 | 0.008271 | 4.20700300 | false |
| 5 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.65546316 | -0.97731786 | 0.275981 | 1.02230461 | false |
| 5 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | normal_vol | 1.08323967 | -2.38318104 | 0.023426 | 2.74839790 | false |
| 5 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | range_normal_vol | 1.08323967 | -2.38318104 | 0.023426 | 2.74839790 | false |
| 6 | 1 | ETH-USDT-SWAP | rsi_revert | all | 4.48877301 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 6 | 2 | ETH-USDT-SWAP | rsi_revert | all | 4.45732610 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 6 | 3 | ETH-USDT-SWAP | rsi_revert | normal_vol | 3.77534509 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.01815083 | 1.82861515 | 7.107803 | 0.88070688 | true |
| 7 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 3.01815083 | 1.82861515 | 7.107803 | 0.88070688 | true |
| 7 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 3.01815083 | 1.82861515 | 7.107803 | 0.88070688 | true |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | all | 5.21821730 | 0.53118287 | 4.185244 | 0.67393069 | true |
| 8 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 5.21821730 | 0.53118287 | 4.185244 | 0.67393069 | true |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 5.21821730 | 0.53118287 | 4.185244 | 0.67393069 | true |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | all | 5.30453548 | 0.42253690 | 999.000000 | 0.52988939 | false |
