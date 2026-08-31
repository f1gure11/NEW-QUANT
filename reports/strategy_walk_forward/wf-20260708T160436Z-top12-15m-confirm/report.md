# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1779 |
| Passed window rows | 329 |
| Unique aggregate candidates | 1039 |
| Passed aggregate candidates | 10 |
| Median selected test return | -0.730341% |
| Mean selected test return | -1.752453% |
| Best aggregate return | 56.479699% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | keltner_breakout | trend_high_vol | 2 | 0.0000 | 56.47969882 | 26.49138731 | 7.72702796 | false |
| 2 | ZEC-USDT-SWAP | ema_cross_atr_band | trend_down | 5 | 40.0000 | 35.11779961 | 1.50116666 | -0.44521759 | false |
| 3 | LAB-USDT-SWAP | keltner_breakout | high_vol | 3 | 0.0000 | 43.18161197 | 7.72702796 | -8.49828249 | false |
| 4 | ZEC-USDT-SWAP | ema_cross_atr_band | trend_high_vol | 2 | 50.0000 | 26.34861311 | 13.05998626 | 0.90683099 | false |
| 5 | ZEC-USDT-SWAP | ema_cross_atr_band | trend_high_vol | 2 | 50.0000 | 26.34861311 | 13.05998626 | 0.90683099 | false |
| 6 | ZEC-USDT-SWAP | atr_vol_breakout | all | 1 | 100.0000 | 16.69489615 | 16.69489615 | 16.69489615 | false |
| 7 | ZEC-USDT-SWAP | atr_vol_breakout | high_vol | 1 | 100.0000 | 16.69489615 | 16.69489615 | 16.69489615 | false |
| 8 | ZEC-USDT-SWAP | atr_vol_breakout | trend_high_vol | 1 | 100.0000 | 16.69489615 | 16.69489615 | 16.69489615 | false |
| 9 | LAB-USDT-SWAP | keltner_breakout | trend_down | 2 | 0.0000 | 31.83105220 | 17.04975787 | -5.69976075 | false |
| 10 | LAB-USDT-SWAP | atr_vol_breakout | trend_down | 2 | 0.0000 | 32.41586437 | 18.72644061 | -10.50336032 | false |
| 11 | ZEC-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 14.45800663 | 14.45800663 | 14.45800663 | false |
| 12 | ZEC-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 100.0000 | 14.45800663 | 14.45800663 | 14.45800663 | false |
| 13 | MU-USDT-SWAP | rsi_revert | trend_down | 2 | 100.0000 | 14.32492400 | 6.93709310 | 5.19081662 | false |
| 14 | EDGE-USDT-SWAP | keltner_breakout | trend_down | 2 | 0.0000 | 34.93091227 | 17.57951930 | -0.63728971 | false |
| 15 | ZEC-USDT-SWAP | ema_cross | trend_down | 1 | 0.0000 | 30.51323461 | 30.51323461 | 30.51323461 | false |
| 16 | ZEC-USDT-SWAP | ema_cross | trend_high_vol | 2 | 0.0000 | 28.76368834 | 14.02437195 | 2.83560236 | false |
| 17 | MU-USDT-SWAP | rsi_revert | all | 6 | 50.0000 | 20.08863547 | 2.81243057 | -0.71561739 | false |
| 18 | LAB-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 11.81653177 | 11.81653177 | 11.81653177 | false |
| 19 | LAB-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 11.81653177 | 11.81653177 | 11.81653177 | false |
| 20 | SOXL-USDT-SWAP | ema_cross | trend_down | 1 | 100.0000 | 12.76052529 | 12.76052529 | 12.76052529 | false |
| 21 | LAB-USDT-SWAP | keltner_breakout | all | 4 | 0.0000 | 32.49171705 | 0.13052943 | -8.49828249 | false |
| 22 | MU-USDT-SWAP | ema_cross_atr_band | trend_up | 4 | 50.0000 | 15.86914926 | 1.56417910 | -2.69949681 | false |
| 23 | SKHYNIX-USDT-SWAP | keltner_breakout | all | 1 | 100.0000 | 8.11009836 | 8.11009836 | 8.11009836 | false |
| 24 | ZEC-USDT-SWAP | ema_cross_atr_band | trend_down | 5 | 40.0000 | 20.74340104 | 1.59586795 | -11.11919954 | false |
| 25 | SNDK-USDT-SWAP | ema_cross_atr_band | trend_down | 1 | 100.0000 | 7.46380247 | 7.46380247 | 7.46380247 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | rsi_revert | trend | 0.86923740 | -1.37907893 | 0.575085 | 2.75043749 | false |
| 1 | 2 | ETH-USDT-SWAP | rsi_revert | trend_high_vol | 0.86923740 | -1.08805579 | 0.573504 | 2.75043749 | false |
| 1 | 3 | ETH-USDT-SWAP | macd_signal | trend_up | 0.57534778 | -0.45272749 | 0.000000 | 0.45272749 | false |
| 2 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 1.13658976 | -0.69209664 | 0.390779 | 1.07473037 | false |
| 2 | 2 | ETH-USDT-SWAP | donchian_breakout | normal_vol | 2.63345362 | -1.14038913 | 0.340073 | 2.14270079 | false |
| 2 | 3 | ETH-USDT-SWAP | donchian_breakout | range_normal_vol | 2.63345362 | -1.14038913 | 0.340073 | 2.14270079 | false |
| 3 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.65546316 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 3 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 1.44336015 | -3.91670219 | 0.000000 | 3.89303186 | false |
| 3 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 1.44336015 | -3.91670219 | 0.000000 | 3.89303186 | false |
| 4 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.65546316 | -0.97731786 | 0.275981 | 1.02230461 | false |
| 4 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | normal_vol | 0.58895910 | -1.90392952 | 0.246332 | 2.74830827 | false |
| 4 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | range_normal_vol | 0.58895910 | -1.90392952 | 0.246332 | 2.74830827 | false |
| 5 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.03041651 | 0.07959920 | 999.000000 | 0.63291719 | false |
| 5 | 2 | ETH-USDT-SWAP | rsi_revert | all | 2.99940850 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 5 | 3 | ETH-USDT-SWAP | bollinger_revert | all | 2.25811316 | 0.79043546 | 6.846672 | 0.91893272 | true |
| 6 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.01815083 | 1.59812197 | 6.427004 | 0.88070688 | true |
| 6 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 3.01815083 | 1.59812197 | 6.427004 | 0.88070688 | true |
| 6 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 3.01815083 | 1.59812197 | 6.427004 | 0.88070688 | true |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | all | 4.98005163 | 0.33872490 | 3.393786 | 0.67393069 | true |
| 7 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 4.98005163 | 0.33872490 | 3.393786 | 0.67393069 | true |
| 7 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 4.98005163 | 0.33872490 | 3.393786 | 0.67393069 | true |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | all | 4.91399855 | 0.84032193 | 999.000000 | 0.52988939 | false |
| 8 | 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 4.91399855 | 0.84032193 | 999.000000 | 0.52988939 | false |
| 8 | 3 | ETH-USDT-SWAP | rsi_revert | range_normal_vol | 4.91399855 | 0.84032193 | 999.000000 | 0.52988939 | false |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | all | 3.10794046 | 0.09454099 | 2.288398 | 1.49471327 | false |
