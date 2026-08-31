# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 59 |
| Passed window rows | 17 |
| Unique aggregate candidates | 36 |
| Passed aggregate candidates | 2 |
| Median selected test return | -0.561071% |
| Mean selected test return | -0.488820% |
| Best aggregate return | 3.001995% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | HYPE-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 2.44099979 | 2.44099979 | 2.44099979 | false |
| 2 | SOL-USDT-SWAP | rsi_trend | all | 1 | 100.0000 | 1.40555924 | 1.40555924 | 1.40555924 | false |
| 3 | SOL-USDT-SWAP | volatility_squeeze_breakout | all | 1 | 100.0000 | 0.49544311 | 0.49544311 | 0.49544311 | false |
| 4 | SOL-USDT-SWAP | macd_signal | all | 1 | 100.0000 | 0.87320263 | 0.87320263 | 0.87320263 | false |
| 5 | HYPE-USDT-SWAP | bollinger_revert | all | 4 | 75.0000 | 3.00199465 | 0.96027933 | -0.62090321 | true |
| 6 | HYPE-USDT-SWAP | rsi_revert | all | 1 | 100.0000 | 0.11624867 | 0.11624867 | 0.11624867 | false |
| 7 | SOL-USDT-SWAP | bollinger_revert | all | 3 | 66.6667 | 0.05687132 | 0.25085888 | -0.74837065 | true |
| 8 | SOL-USDT-SWAP | rsi_trend | all | 2 | 50.0000 | 1.62941881 | 0.81631552 | -0.17746224 | false |
| 9 | HYPE-USDT-SWAP | donchian_breakout | all | 2 | 50.0000 | 2.30068674 | 1.18450042 | -1.68507283 | false |
| 10 | SOL-USDT-SWAP | rsi_revert | all | 2 | 50.0000 | -0.25674951 | -0.12821989 | -0.34596697 | false |
| 11 | HYPE-USDT-SWAP | atr_vol_breakout | all | 3 | 33.3333 | 2.55378925 | -0.55421445 | -0.89256377 | false |
| 12 | HYPE-USDT-SWAP | bollinger_revert | all | 3 | 33.3333 | 0.35915031 | -0.37103010 | -0.90878470 | false |
| 13 | HYPE-USDT-SWAP | rsi_revert | all | 5 | 40.0000 | -0.54002184 | -0.26350305 | -1.31206339 | false |
| 14 | SOL-USDT-SWAP | ema_cross | all | 1 | 0.0000 | -0.05324820 | -0.05324820 | -0.05324820 | false |
| 15 | SOL-USDT-SWAP | volatility_squeeze_breakout | all | 1 | 0.0000 | -0.23328636 | -0.23328636 | -0.23328636 | false |
| 16 | HYPE-USDT-SWAP | rsi_revert | all | 1 | 0.0000 | -0.04017710 | -0.04017710 | -0.04017710 | false |
| 17 | HYPE-USDT-SWAP | trend_pullback | all | 1 | 0.0000 | -0.96627300 | -0.96627300 | -0.96627300 | false |
| 18 | SOL-USDT-SWAP | rsi_trend | all | 1 | 0.0000 | -1.40705018 | -1.40705018 | -1.40705018 | false |
| 19 | SOL-USDT-SWAP | rsi_revert | all | 1 | 0.0000 | -1.49692051 | -1.49692051 | -1.49692051 | false |
| 20 | HYPE-USDT-SWAP | ema_cross | all | 1 | 0.0000 | -0.89199197 | -0.89199197 | -0.89199197 | false |
| 21 | SOL-USDT-SWAP | volatility_squeeze_breakout | all | 2 | 0.0000 | -2.33474239 | -1.17237505 | -1.78367872 | false |
| 22 | SOL-USDT-SWAP | atr_vol_breakout | all | 1 | 0.0000 | -0.33082706 | -0.33082706 | -0.33082706 | false |
| 23 | SOL-USDT-SWAP | atr_vol_breakout | all | 1 | 0.0000 | -1.55469331 | -1.55469331 | -1.55469331 | false |
| 24 | SOL-USDT-SWAP | bollinger_revert | all | 1 | 0.0000 | -1.48424418 | -1.48424418 | -1.48424418 | false |
| 25 | SOL-USDT-SWAP | bollinger_revert | all | 3 | 0.0000 | -2.55298042 | -0.88732273 | -1.48424418 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | HYPE-USDT-SWAP | donchian_breakout | all | 3.10144274 | -1.68507283 | 0.000000 | 2.70771919 | false |
| 1 | 2 | HYPE-USDT-SWAP | rsi_revert | all | 0.83012159 | -0.04017710 | 999.000000 | 1.91963550 | false |
| 2 | 1 | HYPE-USDT-SWAP | bollinger_revert | all | 5.30536762 | 0.43888504 | 12.739395 | 0.71548407 | true |
| 2 | 2 | HYPE-USDT-SWAP | rsi_revert | all | 5.02879935 | 0.98694559 | 999.000000 | 0.60226090 | true |
| 3 | 1 | HYPE-USDT-SWAP | rsi_trend | all | 6.34312072 | -2.38648499 | 0.168898 | 2.93493488 | false |
| 3 | 2 | HYPE-USDT-SWAP | rsi_trend | all | 6.34312072 | -2.11463895 | 0.407604 | 3.04651033 | false |
| 4 | 1 | HYPE-USDT-SWAP | macd_signal | all | 4.24520144 | -0.01632148 | 1.122010 | 3.33371422 | false |
| 4 | 2 | HYPE-USDT-SWAP | rsi_trend | all | 3.04254352 | -3.53231068 | 0.061513 | 3.57489676 | false |
| 5 | 1 | HYPE-USDT-SWAP | bollinger_revert | all | 1.14385834 | -0.37103010 | 0.608264 | 1.92409661 | false |
| 5 | 2 | HYPE-USDT-SWAP | bollinger_revert | all | 1.10522753 | -0.62090321 | 0.000000 | 1.92409661 | false |
| 6 | 1 | HYPE-USDT-SWAP | rsi_revert | all | 3.14257614 | 0.11624867 | 1.739345 | 1.46722502 | true |
| 6 | 2 | HYPE-USDT-SWAP | rsi_revert | all | 1.67762699 | -1.31206339 | 0.291422 | 2.56149050 | false |
| 7 | 1 | HYPE-USDT-SWAP | atr_vol_breakout | all | 6.00980175 | 4.05407367 | 999.000000 | 4.36216273 | true |
| 7 | 2 | HYPE-USDT-SWAP | donchian_breakout | all | 6.71964563 | 4.05407367 | 999.000000 | 4.36216273 | true |
| 8 | 1 | HYPE-USDT-SWAP | bollinger_revert | all | 6.56094287 | 1.68598170 | 999.000000 | 0.58293146 | true |
| 8 | 2 | HYPE-USDT-SWAP | bollinger_revert | all | 5.20854231 | 1.65674059 | 999.000000 | 0.58293146 | true |
| 9 | 1 | HYPE-USDT-SWAP | macd_signal | all | 3.85574906 | -3.10313965 | 0.041437 | 3.09030167 | false |
| 9 | 2 | HYPE-USDT-SWAP | rsi_trend | all | 0.52148768 | -1.09725188 | 0.492273 | 1.87111603 | false |
| 10 | 1 | HYPE-USDT-SWAP | atr_vol_breakout | all | 2.28728302 | -0.55421445 | 0.477569 | 2.97441923 | false |
| 10 | 2 | HYPE-USDT-SWAP | ema_cross | all | 1.73647623 | -0.89199197 | 0.203965 | 3.18719029 | false |
| 11 | 1 | HYPE-USDT-SWAP | macd_signal | all | 1.61598492 | -3.82422621 | 0.000000 | 3.96908863 | false |
| 11 | 2 | HYPE-USDT-SWAP | bollinger_revert | all | 1.02481183 | 2.44099979 | 999.000000 | 0.71036171 | true |
| 12 | 1 | HYPE-USDT-SWAP | rsi_revert | all | 5.86829322 | -1.09491600 | 0.697390 | 4.19927359 | false |
| 12 | 2 | HYPE-USDT-SWAP | trend_pullback | all | 3.47614940 | -2.16735339 | 0.000000 | 2.16735339 | false |
| 13 | 1 | HYPE-USDT-SWAP | atr_vol_breakout | all | 1.80551712 | -0.89256377 | 0.776066 | 2.42040654 | false |
