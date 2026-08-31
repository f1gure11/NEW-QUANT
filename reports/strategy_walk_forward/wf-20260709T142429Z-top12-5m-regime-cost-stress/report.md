# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1118 |
| Passed window rows | 213 |
| Unique aggregate candidates | 665 |
| Passed aggregate candidates | 4 |
| Median selected test return | -1.037759% |
| Mean selected test return | -2.179892% |
| Best aggregate return | 74.945775% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | ema_cross | trend_high_vol | 1 | 0.0000 | 74.94577498 | 74.94577498 | 74.94577498 | false |
| 2 | LAB-USDT-SWAP | ema_cross | high_vol | 1 | 0.0000 | 74.94577498 | 74.94577498 | 74.94577498 | false |
| 3 | EDGE-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 32.52175941 | 32.52175941 | 32.52175941 | false |
| 4 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 4 | 100.0000 | 25.70887866 | 4.54673531 | 4.26576248 | true |
| 5 | LAB-USDT-SWAP | rsi_revert | high_vol | 1 | 100.0000 | 19.60428810 | 19.60428810 | 19.60428810 | false |
| 6 | EDGE-USDT-SWAP | ema_cross | high_vol | 1 | 0.0000 | 31.26818658 | 31.26818658 | 31.26818658 | false |
| 7 | EDGE-USDT-SWAP | macd_signal | high_vol | 5 | 40.0000 | 30.19702770 | 10.27258948 | -15.04847778 | false |
| 8 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 2 | 0.0000 | 34.10026826 | 17.19457870 | -0.82048308 | false |
| 9 | SOL-USDT-SWAP | rsi_revert | trend | 3 | 100.0000 | 12.12954438 | 2.52927412 | 0.78545636 | true |
| 10 | EDGE-USDT-SWAP | volatility_squeeze_breakout | trend_down | 2 | 50.0000 | 28.53002773 | 13.98075605 | 2.20748224 | false |
| 11 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 2 | 100.0000 | 11.37109591 | 5.59234051 | 2.03807790 | false |
| 12 | SOL-USDT-SWAP | ema_cross_atr_band | normal_vol | 2 | 100.0000 | 10.25169196 | 5.05530340 | 1.67187667 | false |
| 13 | SOL-USDT-SWAP | ema_cross_atr_band | range_normal_vol | 1 | 100.0000 | 8.43873013 | 8.43873013 | 8.43873013 | false |
| 14 | SOL-USDT-SWAP | rsi_revert | trend_high_vol | 6 | 50.0000 | 16.01660396 | 1.72826545 | -1.06121751 | false |
| 15 | SPCX-USDT-SWAP | macd_signal | high_vol | 6 | 50.0000 | 15.19328306 | 1.85863187 | 0.00000000 | false |
| 16 | EDGE-USDT-SWAP | ema_cross_atr_band | trend_high_vol | 1 | 100.0000 | 7.32719680 | 7.32719680 | 7.32719680 | false |
| 17 | EDGE-USDT-SWAP | macd_signal | all | 3 | 66.6667 | 14.21101848 | 11.40486865 | -13.21825181 | false |
| 18 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 100.0000 | 9.08891953 | 9.08891953 | 9.08891953 | false |
| 19 | ZEC-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 5.05871560 | 5.05871560 | 5.05871560 | false |
| 20 | SPCX-USDT-SWAP | rsi_revert | all | 1 | 100.0000 | 5.87243035 | 5.87243035 | 5.87243035 | false |
| 21 | SOL-USDT-SWAP | rsi_revert | trend_down | 3 | 66.6667 | 10.52597108 | 2.52927412 | -0.28542389 | true |
| 22 | EDGE-USDT-SWAP | rsi_revert | trend_high_vol | 1 | 100.0000 | 5.70971465 | 5.70971465 | 5.70971465 | false |
| 23 | SPCX-USDT-SWAP | macd_signal | trend_down | 1 | 100.0000 | 4.03630690 | 4.03630690 | 4.03630690 | false |
| 24 | LAB-USDT-SWAP | bollinger_revert | trend_up | 2 | 50.0000 | 13.83471686 | 7.37842366 | -4.73166227 | false |
| 25 | EDGE-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 3.20289517 | 3.20289517 | 3.20289517 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | ema_cross_atr_band | all | 1.77424313 | -1.93960975 | 0.255007 | 3.52705852 | false |
| 1 | 2 | ETH-USDT-SWAP | ema_cross_atr_band | normal_vol | 1.77424313 | -1.93960975 | 0.255007 | 3.52705852 | false |
| 1 | 3 | ETH-USDT-SWAP | ema_cross_atr_band | range_normal_vol | 1.77424313 | -1.93960975 | 0.255007 | 3.52705852 | false |
| 2 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.65309642 | -1.07634901 | 0.778142 | 4.25336310 | false |
| 2 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 5.65309642 | -1.07634901 | 0.778142 | 4.25336310 | false |
| 2 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 5.65309642 | -1.07634901 | 0.778142 | 4.25336310 | false |
| 3 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.59775923 | -1.74242942 | 0.522839 | 3.93092927 | false |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 5.59775923 | -1.74242942 | 0.522839 | 3.93092927 | false |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 5.59775923 | -1.74242942 | 0.522839 | 3.93092927 | false |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | all | 1.72370386 | -3.85866296 | 0.082926 | 4.51996646 | false |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 1.72370386 | -3.85866296 | 0.082926 | 4.51996646 | false |
| 4 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 1.72370386 | -3.85866296 | 0.082926 | 4.51996646 | false |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | trend_down | 1.40869382 | -1.45739255 | 0.643665 | 3.55913774 | false |
| 8 | 2 | ETH-USDT-SWAP | bollinger_revert | trend_up | 0.08366464 | 0.52935693 | 9.800115 | 0.29905471 | true |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | all | 0.48593008 | 1.41065720 | 43.142281 | 4.67266453 | true |
| 9 | 1 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 4.51970854 | 6.97882734 | 4.388851 | 1.61055750 | true |
| 9 | 2 | ETH-USDT-SWAP | macd_signal | high_vol | 3.03408811 | 2.61070446 | 2.562227 | 4.31973068 | true |
| 9 | 3 | ETH-USDT-SWAP | donchian_breakout | all | 5.11639450 | 10.81191290 | 999.000000 | 2.67819256 | false |
| 10 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 15.01990937 | 2.50744079 | 999.000000 | 4.69186329 | false |
| 10 | 2 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 11.16011502 | 2.05443468 | 2.104596 | 2.81126639 | true |
| 10 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 8.28583989 | -1.74423583 | 0.905618 | 4.80372865 | false |
| 11 | 1 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 18.87582282 | -10.38945870 | 0.120155 | 14.11659332 | false |
| 11 | 2 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 19.22124834 | -10.38945870 | 0.120155 | 14.11659332 | false |
| 11 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 10.99291356 | -0.34392461 | 1.029832 | 4.96938048 | false |
| 12 | 1 | ETH-USDT-SWAP | rsi_revert | all | 9.62213862 | 0.45999758 | 3.890596 | 0.76464610 | true |
