# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 321 |
| Passed window rows | 65 |
| Unique aggregate candidates | 151 |
| Passed aggregate candidates | 3 |
| Median selected test return | -2.086391% |
| Mean selected test return | -2.373139% |
| Best aggregate return | 39.018878% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | rsi_revert | all | 2 | 100.0000 | 26.09746920 | 12.29931090 | 11.12104584 | false |
| 2 | BASED-USDT-SWAP | donchian_breakout | all | 4 | 0.0000 | 39.01887781 | 9.21678685 | -2.53275653 | false |
| 3 | SOL-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 8.16605050 | 8.16605050 | 8.16605050 | false |
| 4 | HYPE-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 7.86156500 | 7.86156500 | 7.86156500 | false |
| 5 | SNDK-USDT-SWAP | donchian_breakout | all | 1 | 100.0000 | 6.56591605 | 6.56591605 | 6.56591605 | false |
| 6 | HYPE-USDT-SWAP | rsi_revert | all | 4 | 75.0000 | 8.03632453 | 1.80124223 | -0.33939802 | true |
| 7 | LAB-USDT-SWAP | bollinger_revert | all | 4 | 50.0000 | 18.25543149 | 0.86806915 | -13.34830263 | false |
| 8 | LAB-USDT-SWAP | rsi_revert | all | 2 | 50.0000 | 14.93868908 | 7.31235070 | 2.61429748 | false |
| 9 | MU-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 3.54887170 | 3.54887170 | 3.54887170 | false |
| 10 | HYPE-USDT-SWAP | macd_signal | all | 1 | 100.0000 | 2.72117341 | 2.72117341 | 2.72117341 | false |
| 11 | SPCX-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 0.64488158 | 0.64488158 | 0.64488158 | false |
| 12 | SNDK-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 0.66994854 | 0.66994854 | 0.66994854 | false |
| 13 | SNDK-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 0.28875115 | 0.28875115 | 0.28875115 | false |
| 14 | SOL-USDT-SWAP | ema_cross | all | 2 | 50.0000 | 5.82070677 | 3.11014805 | -3.93484690 | false |
| 15 | HYPE-USDT-SWAP | ema_cross | all | 3 | 66.6667 | 5.10430894 | 2.20507813 | -2.98188151 | true |
| 16 | HYPE-USDT-SWAP | ema_cross | all | 2 | 50.0000 | 5.55245601 | 2.79367435 | -0.56696334 | false |
| 17 | HYPE-USDT-SWAP | ema_cross | all | 3 | 66.6667 | 4.40263983 | 1.47338418 | -3.76737944 | false |
| 18 | SPCX-USDT-SWAP | donchian_breakout | all | 4 | 25.0000 | 8.38671766 | 0.56305641 | -1.15396645 | false |
| 19 | HYPE-USDT-SWAP | rsi_revert | all | 5 | 60.0000 | 1.84586870 | 0.24265593 | -1.28676617 | true |
| 20 | LAB-USDT-SWAP | trend_pullback | all | 5 | 40.0000 | 0.58749117 | -0.06053571 | -2.59897794 | false |
| 21 | LAB-USDT-SWAP | atr_vol_breakout | all | 4 | 25.0000 | 11.20503353 | -1.40527359 | -16.11626700 | false |
| 22 | SPCX-USDT-SWAP | bollinger_revert | all | 3 | 66.6667 | -0.17058289 | 0.75485820 | -14.81692128 | false |
| 23 | HYPE-USDT-SWAP | trend_pullback | all | 2 | 50.0000 | -0.75340348 | -0.37503407 | -1.06364548 | false |
| 24 | HYPE-USDT-SWAP | bollinger_revert | all | 3 | 33.3333 | -0.33678059 | -1.17152871 | -2.70180778 | false |
| 25 | BASED-USDT-SWAP | bollinger_revert | all | 2 | 50.0000 | -0.25717866 | -0.05735466 | -3.83230157 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BASED-USDT-SWAP | rsi_revert | all | 2.44163086 | -8.47970161 | 0.000000 | 9.72842238 | false |
| 1 | 2 | BASED-USDT-SWAP | bollinger_revert | all | 3.73436453 | -1.31892124 | 0.953553 | 7.77216909 | false |
| 1 | 3 | BASED-USDT-SWAP | rsi_revert | all | 2.21009519 | -5.88148252 | 0.604542 | 9.49245271 | false |
| 2 | 1 | BASED-USDT-SWAP | ema_cross | all | 10.35780166 | -6.30155540 | 0.381134 | 7.82177285 | false |
| 2 | 2 | BASED-USDT-SWAP | ema_cross | all | 9.73691102 | -6.35964450 | 0.401287 | 7.87891947 | false |
| 3 | 1 | BASED-USDT-SWAP | ema_cross | all | 5.44037366 | 19.26219641 | 999.000000 | 9.53935220 | false |
| 3 | 2 | BASED-USDT-SWAP | ema_cross | all | 5.23205239 | 19.26219641 | 999.000000 | 9.53935220 | false |
| 4 | 1 | BASED-USDT-SWAP | ema_cross | all | 22.65882433 | -2.15918938 | 0.536629 | 7.20219267 | false |
| 4 | 2 | BASED-USDT-SWAP | ema_cross | all | 22.69177318 | -5.11229767 | 0.349305 | 9.25503514 | false |
| 4 | 3 | BASED-USDT-SWAP | ema_cross | all | 18.43108980 | -8.29639585 | 0.517492 | 13.68884216 | false |
| 5 | 1 | BASED-USDT-SWAP | ema_cross | all | 15.90360451 | -13.25111655 | 0.128785 | 19.41231229 | false |
| 5 | 2 | BASED-USDT-SWAP | ema_cross | all | 14.80362715 | -5.35592983 | 0.311420 | 12.07699009 | false |
| 5 | 3 | BASED-USDT-SWAP | ema_cross | all | 10.36023955 | -8.88302766 | 0.212467 | 15.35445968 | false |
| 6 | 1 | BASED-USDT-SWAP | ema_cross | all | 17.24417093 | -13.12940650 | 0.576671 | 31.74206726 | false |
| 6 | 2 | BASED-USDT-SWAP | bollinger_revert | all | 10.66555162 | -2.05157528 | 0.961280 | 23.61028416 | false |
| 6 | 3 | BASED-USDT-SWAP | atr_vol_breakout | all | 7.63433698 | -13.45174444 | 0.625122 | 28.26846812 | false |
| 7 | 1 | BASED-USDT-SWAP | ema_cross | all | 27.10828428 | -19.75579713 | 0.223104 | 24.53082449 | false |
| 7 | 2 | BASED-USDT-SWAP | ema_cross | all | 24.77359972 | -15.57991216 | 0.282756 | 23.61689258 | false |
| 7 | 3 | BASED-USDT-SWAP | ema_cross | all | 26.27288831 | -5.02396694 | 0.628915 | 14.39636834 | false |
| 8 | 1 | BASED-USDT-SWAP | rsi_revert | all | 13.75867671 | 1.25278611 | 1.319239 | 4.51459879 | true |
| 8 | 2 | BASED-USDT-SWAP | rsi_revert | all | 6.49800986 | 0.57466656 | 2.386673 | 2.81343447 | true |
| 8 | 3 | BASED-USDT-SWAP | bollinger_revert | all | 8.87604920 | 14.54271292 | 3.895495 | 5.18948264 | true |
| 9 | 1 | BASED-USDT-SWAP | rsi_revert | all | 20.44934392 | -7.44546623 | 0.167162 | 9.11660974 | false |
| 9 | 2 | BASED-USDT-SWAP | rsi_revert | all | 13.92051033 | 10.48435363 | 5.952898 | 5.57479790 | true |
| 9 | 3 | BASED-USDT-SWAP | bollinger_revert | all | 18.96841368 | -15.92280155 | 0.212363 | 18.38967774 | false |
