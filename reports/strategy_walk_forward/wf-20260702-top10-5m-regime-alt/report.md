# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 606 |
| Passed window rows | 126 |
| Unique aggregate candidates | 434 |
| Passed aggregate candidates | 5 |
| Median selected test return | -0.926896% |
| Mean selected test return | -1.492315% |
| Best aggregate return | 29.402282% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross | trend | 1 | 100.0000 | 21.56584998 | 21.56584998 | 21.56584998 | false |
| 2 | LAB-USDT-SWAP | macd_signal | trend_down | 3 | 66.6667 | 29.40228222 | 9.72995681 | 6.92897658 | true |
| 3 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 1 | 100.0000 | 20.21033258 | 20.21033258 | 20.21033258 | false |
| 4 | LAB-USDT-SWAP | bollinger_revert | all | 2 | 100.0000 | 16.61873790 | 7.99058897 | 7.68478573 | false |
| 5 | BASED-USDT-SWAP | ema_cross | trend_up | 1 | 100.0000 | 15.18910637 | 15.18910637 | 15.18910637 | false |
| 6 | SPCX-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 13.38995730 | 13.38995730 | 13.38995730 | false |
| 7 | LAB-USDT-SWAP | atr_vol_breakout | trend_up | 2 | 100.0000 | 15.95347103 | 7.74954273 | 3.92634300 | false |
| 8 | LAB-USDT-SWAP | atr_vol_breakout | trend_up | 2 | 100.0000 | 15.95347103 | 7.74954273 | 3.92634300 | false |
| 9 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 2 | 100.0000 | 12.35162162 | 6.10457408 | 1.30681653 | false |
| 10 | LAB-USDT-SWAP | ema_cross | all | 3 | 33.3333 | 27.49989446 | 8.59658757 | 0.05267350 | false |
| 11 | LAB-USDT-SWAP | ema_cross | all | 3 | 33.3333 | 22.48948465 | 7.74156333 | 5.02654552 | false |
| 12 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 100.0000 | 6.22247264 | 6.22247264 | 6.22247264 | false |
| 13 | LAB-USDT-SWAP | ema_cross | trend_up | 1 | 100.0000 | 4.87939945 | 4.87939945 | 4.87939945 | false |
| 14 | LAB-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 4.87939945 | 4.87939945 | 4.87939945 | false |
| 15 | LAB-USDT-SWAP | ema_cross | trend_up | 1 | 100.0000 | 4.87939945 | 4.87939945 | 4.87939945 | false |
| 16 | HYPE-USDT-SWAP | rsi_revert | all | 2 | 100.0000 | 3.23234049 | 1.60786652 | 0.64636304 | false |
| 17 | HYPE-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 2.23764561 | 2.23764561 | 2.23764561 | false |
| 18 | LAB-USDT-SWAP | ema_cross | trend_high_vol | 3 | 33.3333 | 20.06524780 | 7.74156333 | 2.94792447 | false |
| 19 | HYPE-USDT-SWAP | rsi_revert | trend | 2 | 100.0000 | 2.23019391 | 1.11112740 | 0.44728036 | false |
| 20 | BASED-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 2.17974701 | 2.17974701 | 2.17974701 | false |
| 21 | BASED-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 1.93190902 | 1.93190902 | 1.93190902 | false |
| 22 | HYPE-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 1.53283411 | 1.53283411 | 1.53283411 | false |
| 23 | MU-USDT-SWAP | ema_cross | all | 2 | 100.0000 | 3.90241379 | 1.93994593 | 0.71063848 | false |
| 24 | BTC-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 0.87778745 | 0.87778745 | 0.87778745 | false |
| 25 | HYPE-USDT-SWAP | bollinger_revert | range_normal_vol | 1 | 100.0000 | 1.45512221 | 1.45512221 | 1.45512221 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | rsi_revert | trend_up | 1.44782523 | -0.42320998 | 0.760263 | 1.16553538 | false |
| 1 | 2 | BTC-USDT-SWAP | bollinger_revert | all | 2.58564431 | -0.01918738 | 1.152944 | 2.20123053 | false |
| 1 | 3 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 2.58564431 | -0.01918738 | 1.152944 | 2.20123053 | false |
| 2 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 2.52799106 | -1.30615662 | 0.570063 | 2.68771766 | false |
| 2 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 2.52799106 | -1.30615662 | 0.570063 | 2.68771766 | false |
| 2 | 3 | BTC-USDT-SWAP | bollinger_revert | range_normal_vol | 2.52799106 | -1.30615662 | 0.570063 | 2.68771766 | false |
| 3 | 1 | BTC-USDT-SWAP | rsi_revert | trend_up | 0.29486307 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 3 | 2 | BTC-USDT-SWAP | bollinger_revert | trend_up | 0.47466511 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 3 | 3 | BTC-USDT-SWAP | rsi_revert | trend_up | 0.27523602 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 4 | 1 | BTC-USDT-SWAP | bollinger_revert | trend | 0.88533006 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 4 | 2 | BTC-USDT-SWAP | bollinger_revert | trend_high_vol | 0.88533006 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 4 | 3 | BTC-USDT-SWAP | bollinger_revert | trend_up | 1.04160751 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 5 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 0.92309396 | -3.60705359 | 0.173971 | 4.30741256 | false |
| 5 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 0.92309396 | -3.60705359 | 0.173971 | 4.30741256 | false |
| 5 | 3 | BTC-USDT-SWAP | bollinger_revert | range_normal_vol | 0.92309396 | -3.60705359 | 0.173971 | 4.30741256 | false |
| 6 | 1 | BTC-USDT-SWAP | ema_cross | all | 3.47189975 | -0.91563011 | 0.827366 | 2.61930549 | false |
| 6 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 3.47189975 | -0.91563011 | 0.827366 | 2.61930549 | false |
| 6 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 3.47189975 | -0.91563011 | 0.827366 | 2.61930549 | false |
| 7 | 1 | BTC-USDT-SWAP | ema_cross | all | 3.95506918 | -3.43762903 | 0.450911 | 5.69794326 | false |
| 7 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 3.95506918 | -3.43762903 | 0.450911 | 5.69794326 | false |
| 7 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 3.95506918 | -3.43762903 | 0.450911 | 5.69794326 | false |
| 8 | 1 | BTC-USDT-SWAP | ema_cross | all | 3.85706457 | -3.66715678 | 0.363347 | 5.88923102 | false |
| 8 | 2 | BTC-USDT-SWAP | ema_cross | normal_vol | 3.85706457 | -3.66715678 | 0.363347 | 5.88923102 | false |
| 8 | 3 | BTC-USDT-SWAP | ema_cross | range_normal_vol | 3.85706457 | -3.66715678 | 0.363347 | 5.88923102 | false |
| 9 | 1 | BTC-USDT-SWAP | rsi_revert | trend | 1.85190979 | 0.00000000 | 0.000000 | 0.00000000 | false |
