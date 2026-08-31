# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 419 |
| Passed window rows | 86 |
| Unique aggregate candidates | 286 |
| Passed aggregate candidates | 2 |
| Median selected test return | -0.896428% |
| Mean selected test return | -0.830211% |
| Best aggregate return | 162.951776% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | donchian_breakout | all | 2 | 0.0000 | 162.95177623 | 85.76414444 | -4.86222996 | false |
| 2 | LAB-USDT-SWAP | donchian_breakout | high_vol | 2 | 0.0000 | 162.95177623 | 85.76414444 | -4.86222996 | false |
| 3 | LAB-USDT-SWAP | donchian_breakout | trend_high_vol | 2 | 0.0000 | 162.95177623 | 85.76414444 | -4.86222996 | false |
| 4 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 50.0000 | 34.92809847 | 16.16057071 | 15.47621643 | false |
| 5 | LAB-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 18.19833731 | 18.19833731 | 18.19833731 | false |
| 6 | LAB-USDT-SWAP | atr_vol_breakout | trend_up | 2 | 100.0000 | 8.92276498 | 4.41983114 | 1.06951224 | false |
| 7 | LAB-USDT-SWAP | donchian_breakout | trend_up | 1 | 100.0000 | 9.00083683 | 9.00083683 | 9.00083683 | false |
| 8 | LAB-USDT-SWAP | ema_cross | all | 2 | 50.0000 | 17.65640823 | 8.77644854 | 0.61097648 | false |
| 9 | SPCX-USDT-SWAP | trend_pullback | high_vol | 1 | 100.0000 | 3.73786816 | 3.73786816 | 3.73786816 | false |
| 10 | SPCX-USDT-SWAP | ema_cross | high_vol | 2 | 100.0000 | 5.45369891 | 2.69448249 | 1.80744129 | false |
| 11 | LAB-USDT-SWAP | macd_signal | trend_down | 2 | 50.0000 | 15.05650161 | 7.26482000 | 6.96241684 | false |
| 12 | SNDK-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 4.57816962 | 4.57816962 | 4.57816962 | false |
| 13 | HYPE-USDT-SWAP | bollinger_revert | trend_up | 1 | 100.0000 | 1.89480450 | 1.89480450 | 1.89480450 | false |
| 14 | SKHYNIX-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 3.62374043 | 3.62374043 | 3.62374043 | false |
| 15 | LAB-USDT-SWAP | rsi_revert | range | 1 | 100.0000 | 1.15088911 | 1.15088911 | 1.15088911 | false |
| 16 | LAB-USDT-SWAP | rsi_revert | range_normal_vol | 1 | 100.0000 | 1.15088911 | 1.15088911 | 1.15088911 | false |
| 17 | MU-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 2.43741753 | 2.43741753 | 2.43741753 | false |
| 18 | SPCX-USDT-SWAP | rsi_revert | trend_up | 1 | 100.0000 | 1.47694134 | 1.47694134 | 1.47694134 | false |
| 19 | HYPE-USDT-SWAP | rsi_revert | range_normal_vol | 1 | 100.0000 | 0.93264951 | 0.93264951 | 0.93264951 | false |
| 20 | HYPE-USDT-SWAP | trend_pullback | range_normal_vol | 3 | 100.0000 | 0.30772924 | 0.10533468 | 0.05436354 | true |
| 21 | HYPE-USDT-SWAP | trend_pullback | normal_vol | 2 | 100.0000 | 0.25322804 | 0.12653621 | 0.10533468 | false |
| 22 | SPCX-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 0.84882324 | 0.84882324 | 0.84882324 | false |
| 23 | SPCX-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 1.80744129 | 1.80744129 | 1.80744129 | false |
| 24 | SNDK-USDT-SWAP | macd_signal | high_vol | 1 | 100.0000 | 1.56918102 | 1.56918102 | 1.56918102 | false |
| 25 | BTC-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.04867743 | 0.04867743 | 0.04867743 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | donchian_breakout | trend_up | 6.67190035 | -4.06030006 | 0.000000 | 4.49449612 | false |
| 1 | 2 | ETH-USDT-SWAP | keltner_breakout | trend_up | 6.67190035 | -3.58535391 | 0.000000 | 4.02169944 | false |
| 1 | 3 | ETH-USDT-SWAP | keltner_breakout | trend_up | 6.67190035 | -3.58535391 | 0.000000 | 4.02169944 | false |
| 2 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.92137467 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 2 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.26028016 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 2 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 1.79690039 | -3.58992090 | 0.092431 | 3.77145236 | false |
| 3 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.20968795 | -1.17040757 | 0.000000 | 1.17040757 | false |
| 3 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.55307767 | -1.17040757 | 0.000000 | 1.17040757 | false |
| 3 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 3.39734151 | -2.54195349 | 0.156561 | 2.68285256 | false |
| 4 | 1 | ETH-USDT-SWAP | rsi_revert | normal_vol | 1.58959226 | 0.34892356 | 3.948910 | 1.26858509 | true |
| 4 | 2 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 1.58959226 | 0.34892356 | 3.948910 | 1.26858509 | true |
| 4 | 3 | ETH-USDT-SWAP | rsi_revert | all | 1.31568588 | 0.34892356 | 3.948910 | 1.26858509 | true |
| 5 | 1 | ETH-USDT-SWAP | rsi_revert | normal_vol | 1.51421836 | -3.78965030 | 0.105023 | 5.20336129 | false |
| 5 | 2 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 1.51421836 | -3.78965030 | 0.105023 | 5.20336129 | false |
| 5 | 3 | ETH-USDT-SWAP | rsi_revert | all | 1.24051520 | -3.78965030 | 0.105023 | 5.20336129 | false |
| 6 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 4.28405051 | -5.84593867 | 0.458199 | 10.92583637 | false |
| 6 | 2 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 4.28405051 | -6.45133789 | 0.410975 | 10.92583637 | false |
| 6 | 3 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 4.28405051 | -6.45133789 | 0.410975 | 10.92583637 | false |
| 7 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_down | 4.37044763 | -0.69781593 | 0.894734 | 3.24422141 | false |
| 7 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_down | 2.72584315 | 1.31145465 | 2.538100 | 2.65325095 | true |
| 7 | 3 | ETH-USDT-SWAP | donchian_breakout | trend_down | 1.57895416 | 0.53797694 | 1.364842 | 2.87892377 | true |
| 8 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_down | 4.07304599 | -0.47816496 | 0.847099 | 2.83368002 | false |
| 8 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_down | 4.18388600 | -1.39463247 | 0.267998 | 3.72845628 | false |
| 8 | 3 | ETH-USDT-SWAP | ema_cross | all | 5.94875881 | -1.22701184 | 0.490159 | 5.32485431 | false |
| 9 | 1 | ETH-USDT-SWAP | ema_cross | all | 7.96982462 | 0.68427997 | 999.000000 | 1.48574438 | true |
