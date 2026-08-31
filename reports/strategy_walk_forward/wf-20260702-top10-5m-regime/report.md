# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 438 |
| Passed window rows | 96 |
| Unique aggregate candidates | 309 |
| Passed aggregate candidates | 2 |
| Median selected test return | -1.058702% |
| Mean selected test return | -1.958514% |
| Best aggregate return | 37.318908% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 37.31890788 | 37.31890788 | 37.31890788 | false |
| 2 | LAB-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 18.53999074 | 18.53999074 | 18.53999074 | false |
| 3 | LAB-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 14.60471742 | 14.60471742 | 14.60471742 | false |
| 4 | LAB-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 10.97219247 | 10.97219247 | 10.97219247 | false |
| 5 | SPCX-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 11.62164506 | 11.62164506 | 11.62164506 | false |
| 6 | LAB-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 100.0000 | 9.73292684 | 9.73292684 | 9.73292684 | false |
| 7 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 2 | 50.0000 | 15.42140682 | 7.71070341 | 0.00000000 | false |
| 8 | BASED-USDT-SWAP | donchian_breakout | all | 1 | 0.0000 | 20.97637837 | 20.97637837 | 20.97637837 | false |
| 9 | BASED-USDT-SWAP | rsi_revert | range_normal_vol | 2 | 100.0000 | 5.03375267 | 2.48989198 | 1.59396139 | false |
| 10 | HYPE-USDT-SWAP | bollinger_revert | range_normal_vol | 2 | 100.0000 | 5.06356348 | 2.50080003 | 2.26067661 | false |
| 11 | HYPE-USDT-SWAP | bollinger_revert | normal_vol | 2 | 100.0000 | 4.01762360 | 1.98939432 | 1.71700899 | false |
| 12 | SPCX-USDT-SWAP | bollinger_revert | trend_down | 6 | 50.0000 | 9.73740028 | 0.13232149 | -2.90313116 | false |
| 13 | MU-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 3.78960684 | 3.78960684 | 3.78960684 | false |
| 14 | BASED-USDT-SWAP | donchian_breakout | high_vol | 2 | 0.0000 | 19.85051540 | 10.02286571 | -0.93064694 | false |
| 15 | BASED-USDT-SWAP | donchian_breakout | trend_high_vol | 2 | 0.0000 | 19.85051540 | 10.02286571 | -0.93064694 | false |
| 16 | BASED-USDT-SWAP | rsi_revert | range_normal_vol | 3 | 66.6667 | 5.58319150 | 2.63943833 | 0.00000000 | true |
| 17 | LAB-USDT-SWAP | rsi_revert | range_normal_vol | 1 | 100.0000 | 1.44835479 | 1.44835479 | 1.44835479 | false |
| 18 | LAB-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 3.36497250 | 3.36497250 | 3.36497250 | false |
| 19 | MU-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 1.98619937 | 1.98619937 | 1.98619937 | false |
| 20 | SPCX-USDT-SWAP | bollinger_revert | trend_down | 2 | 100.0000 | 1.16787165 | 0.58274382 | 0.26464299 | false |
| 21 | ETH-USDT-SWAP | ema_cross | trend_up | 1 | 100.0000 | 1.07140782 | 1.07140782 | 1.07140782 | false |
| 22 | ETH-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 1.07140782 | 1.07140782 | 1.07140782 | false |
| 23 | BTC-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.43966133 | 0.43966133 | 0.43966133 | false |
| 24 | SNDK-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 1.68021415 | 1.68021415 | 1.68021415 | false |
| 25 | HYPE-USDT-SWAP | bollinger_revert | range_normal_vol | 1 | 100.0000 | 0.84077154 | 0.84077154 | 0.84077154 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 1.69748457 | -2.32970066 | 0.142011 | 2.60383998 | false |
| 1 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 1.69748457 | -2.32970066 | 0.142011 | 2.60383998 | false |
| 1 | 3 | BTC-USDT-SWAP | bollinger_revert | range_normal_vol | 1.69748457 | -2.32970066 | 0.142011 | 2.60383998 | false |
| 2 | 1 | BTC-USDT-SWAP | rsi_revert | trend_up | 0.29486307 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 2 | 2 | BTC-USDT-SWAP | bollinger_revert | trend_up | 0.61613660 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 2 | 3 | BTC-USDT-SWAP | bollinger_revert | all | 0.18609526 | -1.86107667 | 0.422526 | 1.88443113 | false |
| 3 | 1 | BTC-USDT-SWAP | rsi_revert | trend_up | 0.29486307 | -1.21208867 | 0.104210 | 1.71500311 | false |
| 3 | 2 | BTC-USDT-SWAP | rsi_revert | trend | 0.23237925 | -1.21208867 | 0.104210 | 1.71500311 | false |
| 3 | 3 | BTC-USDT-SWAP | rsi_revert | trend_high_vol | 0.23237925 | -1.21208867 | 0.104210 | 1.71500311 | false |
| 4 | 1 | BTC-USDT-SWAP | ema_cross | all | 0.33490518 | -6.13464115 | 0.175842 | 6.21247296 | false |
| 4 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 0.33490518 | -6.13464115 | 0.175842 | 6.21247296 | false |
| 4 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 0.33490518 | -6.13464115 | 0.175842 | 6.21247296 | false |
| 6 | 1 | BTC-USDT-SWAP | atr_vol_breakout | all | 3.18503097 | -3.75889425 | 0.224573 | 4.71780134 | false |
| 6 | 2 | BTC-USDT-SWAP | atr_vol_breakout | normal_vol | 3.18503097 | -3.75889425 | 0.224573 | 4.71780134 | false |
| 6 | 3 | BTC-USDT-SWAP | atr_vol_breakout | range_normal_vol | 3.18503097 | -3.75889425 | 0.224573 | 4.71780134 | false |
| 7 | 1 | BTC-USDT-SWAP | rsi_revert | trend | 0.68471114 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 7 | 2 | BTC-USDT-SWAP | rsi_revert | trend_high_vol | 0.68471114 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 7 | 3 | BTC-USDT-SWAP | rsi_revert | trend_up | 0.77192188 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 8 | 1 | BTC-USDT-SWAP | rsi_revert | trend | 1.71326439 | 0.43337534 | 999.000000 | 0.14339061 | false |
| 8 | 2 | BTC-USDT-SWAP | rsi_revert | trend_high_vol | 1.71326439 | 0.43337534 | 999.000000 | 0.14339061 | false |
| 8 | 3 | BTC-USDT-SWAP | rsi_revert | trend | 0.55294072 | -0.22437905 | 0.889972 | 0.72724911 | false |
| 9 | 1 | BTC-USDT-SWAP | rsi_revert | trend | 1.95053354 | -0.94123011 | 0.350753 | 1.72390672 | false |
| 9 | 2 | BTC-USDT-SWAP | rsi_revert | trend_high_vol | 1.95053354 | -0.94123011 | 0.350753 | 1.72390672 | false |
| 9 | 3 | BTC-USDT-SWAP | bollinger_revert | trend_up | 0.89657082 | -0.12566146 | 0.000000 | 1.08809518 | false |
| 10 | 1 | BTC-USDT-SWAP | donchian_breakout | all | 2.93027407 | -0.27621104 | 0.995431 | 4.96848522 | false |
