# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 465 |
| Passed window rows | 104 |
| Unique aggregate candidates | 198 |
| Passed aggregate candidates | 3 |
| Median selected test return | -1.846482% |
| Mean selected test return | -1.899253% |
| Best aggregate return | 48.868946% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross | all | 5 | 40.0000 | 48.86894587 | 7.17798212 | -3.64981203 | false |
| 2 | LAB-USDT-SWAP | ema_cross | all | 3 | 0.0000 | 45.74176214 | 20.15644530 | -1.89247857 | false |
| 3 | LAB-USDT-SWAP | ema_cross | all | 4 | 25.0000 | 36.25388544 | 8.09464573 | -0.40234454 | false |
| 4 | LAB-USDT-SWAP | rsi_revert | all | 3 | 66.6667 | 21.28538115 | 6.56695032 | 2.61429748 | true |
| 5 | SPCX-USDT-SWAP | bollinger_revert | all | 2 | 100.0000 | 9.53062218 | 4.74323591 | 0.49079539 | false |
| 6 | LAB-USDT-SWAP | donchian_breakout | all | 2 | 50.0000 | 21.17507358 | 10.10970015 | 7.53313106 | false |
| 7 | HYPE-USDT-SWAP | ema_cross | all | 2 | 100.0000 | 8.21863092 | 4.03145533 | 3.20646747 | false |
| 8 | BASED-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 6.88860076 | 6.88860076 | 6.88860076 | false |
| 9 | SPCX-USDT-SWAP | bollinger_revert | all | 2 | 100.0000 | 6.32260539 | 3.14371245 | 0.62084123 | false |
| 10 | BASED-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 4.80632979 | 4.80632979 | 4.80632979 | false |
| 11 | LAB-USDT-SWAP | atr_vol_breakout | all | 2 | 50.0000 | 13.84037392 | 7.43536232 | -5.14715278 | false |
| 12 | BASED-USDT-SWAP | ema_cross | all | 7 | 28.5714 | 15.89114005 | -1.02045564 | -4.04119977 | false |
| 13 | LAB-USDT-SWAP | ema_cross | all | 2 | 0.0000 | 23.27870572 | 11.32634813 | 3.22170650 | false |
| 14 | BASED-USDT-SWAP | donchian_breakout | all | 4 | 25.0000 | 16.38459836 | 1.64516203 | -1.12717303 | false |
| 15 | HYPE-USDT-SWAP | ema_cross | all | 4 | 25.0000 | 13.46596428 | 1.96280777 | -2.38189164 | false |
| 16 | MU-USDT-SWAP | ema_cross | all | 2 | 100.0000 | 3.12023868 | 1.55741690 | 0.18444206 | false |
| 17 | LAB-USDT-SWAP | ema_cross | all | 2 | 50.0000 | 12.51644072 | 7.18058524 | -8.18280566 | false |
| 18 | HYPE-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 0.31357735 | 0.31357735 | 0.31357735 | false |
| 19 | LAB-USDT-SWAP | ema_cross | all | 2 | 50.0000 | 12.30269074 | 5.99438289 | 3.86362471 | false |
| 20 | LAB-USDT-SWAP | donchian_breakout | all | 1 | 100.0000 | 4.14826336 | 4.14826336 | 4.14826336 | false |
| 21 | BASED-USDT-SWAP | rsi_revert | all | 6 | 33.3333 | 10.98393030 | -0.00131809 | -0.66858710 | false |
| 22 | HYPE-USDT-SWAP | trend_pullback | all | 3 | 66.6667 | 2.72552821 | 0.93122505 | 0.51391112 | true |
| 23 | SPCX-USDT-SWAP | atr_vol_breakout | all | 1 | 100.0000 | 0.24464728 | 0.24464728 | 0.24464728 | false |
| 24 | SPCX-USDT-SWAP | rsi_revert | all | 5 | 40.0000 | 4.62640320 | -0.77765004 | -4.05433335 | false |
| 25 | SNDK-USDT-SWAP | ema_cross | all | 3 | 66.6667 | 2.41687036 | 1.91155041 | -2.20743137 | true |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BASED-USDT-SWAP | bollinger_revert | all | 11.24604882 | -6.24673182 | 0.423680 | 8.97923799 | false |
| 1 | 2 | BASED-USDT-SWAP | rsi_revert | all | 6.46680432 | -9.70846250 | 0.241726 | 10.16332970 | false |
| 1 | 3 | BASED-USDT-SWAP | bollinger_revert | all | 5.03151338 | -12.04507017 | 0.263428 | 12.71910209 | false |
| 2 | 1 | BASED-USDT-SWAP | ema_cross | all | 9.02694276 | -2.32584872 | 0.579613 | 8.11685274 | false |
| 2 | 2 | BASED-USDT-SWAP | ema_cross | all | 7.80045985 | -3.35510415 | 0.464089 | 8.95037184 | false |
| 3 | 1 | BASED-USDT-SWAP | ema_cross | all | 10.07733591 | -1.02045564 | 0.920589 | 9.52152865 | false |
| 3 | 2 | BASED-USDT-SWAP | ema_cross | all | 7.94193176 | -0.17693219 | 1.069424 | 9.25805365 | false |
| 3 | 3 | BASED-USDT-SWAP | keltner_breakout | all | 2.96100396 | -9.43438950 | 0.297309 | 10.59448230 | false |
| 4 | 1 | BASED-USDT-SWAP | ema_cross | all | 5.78960705 | -2.48181596 | 0.655024 | 5.89304135 | false |
| 4 | 2 | BASED-USDT-SWAP | ema_cross | all | 5.76717141 | -2.66121341 | 0.613174 | 6.20097992 | false |
| 5 | 1 | BASED-USDT-SWAP | bollinger_revert | all | 1.15281741 | -4.19802242 | 0.737942 | 14.31712073 | false |
| 5 | 2 | BASED-USDT-SWAP | ema_cross | all | 3.22617466 | 19.31714834 | 999.000000 | 5.55893118 | false |
| 5 | 3 | BASED-USDT-SWAP | ema_cross | all | 3.25390348 | 19.31714834 | 999.000000 | 5.55893118 | false |
| 6 | 1 | BASED-USDT-SWAP | ema_cross | all | 16.98516739 | 1.14451545 | 1.570025 | 7.20219267 | true |
| 6 | 2 | BASED-USDT-SWAP | ema_cross | all | 15.95725808 | 1.14451545 | 1.570025 | 7.20219267 | true |
| 6 | 3 | BASED-USDT-SWAP | ema_cross | all | 13.65835347 | 9.22647659 | 5.444608 | 5.83661696 | true |
| 7 | 1 | BASED-USDT-SWAP | ema_cross | all | 20.18495314 | -8.91341850 | 0.142400 | 12.55669523 | false |
| 7 | 2 | BASED-USDT-SWAP | ema_cross | all | 17.34653494 | -10.73706235 | 0.164563 | 12.61175804 | false |
| 7 | 3 | BASED-USDT-SWAP | ema_cross | all | 15.53449890 | -16.47286342 | 0.026353 | 18.22709612 | false |
| 8 | 1 | BASED-USDT-SWAP | ema_cross | all | 21.93037908 | -14.16486415 | 0.146490 | 15.61292753 | false |
| 8 | 2 | BASED-USDT-SWAP | atr_vol_breakout | all | 13.94218494 | -21.28037379 | 0.000000 | 21.94792686 | false |
| 8 | 3 | BASED-USDT-SWAP | ema_cross | all | 14.51170461 | -3.94653898 | 0.566771 | 10.17387265 | false |
| 9 | 1 | BASED-USDT-SWAP | bollinger_revert | all | 16.78764991 | -12.00395993 | 0.510977 | 23.35377769 | false |
| 9 | 2 | BASED-USDT-SWAP | bollinger_revert | all | 15.78332373 | -11.64677911 | 0.523873 | 23.35377769 | false |
| 9 | 3 | BASED-USDT-SWAP | ema_cross | all | 5.59433557 | 10.76165081 | 3.408097 | 24.74480383 | false |
