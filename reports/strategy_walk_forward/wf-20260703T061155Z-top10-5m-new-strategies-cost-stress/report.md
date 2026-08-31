# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 300 |
| Passed window rows | 47 |
| Unique aggregate candidates | 144 |
| Passed aggregate candidates | 0 |
| Median selected test return | -2.490745% |
| Mean selected test return | -2.700101% |
| Best aggregate return | 43.054013% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SOXL-USDT-SWAP | donchian_breakout | all | 10 | 20.0000 | 43.05401270 | 3.39779082 | -6.54754872 | false |
| 2 | SNDK-USDT-SWAP | donchian_breakout | all | 1 | 100.0000 | 6.24680956 | 6.24680956 | 6.24680956 | false |
| 3 | HYPE-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 4.27864219 | 4.27864219 | 4.27864219 | false |
| 4 | SKHYNIX-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 1.45116325 | 1.45116325 | 1.45116325 | false |
| 5 | SOL-USDT-SWAP | ema_cross | all | 3 | 33.3333 | 10.89915333 | 1.73603105 | -2.16922790 | false |
| 6 | MU-USDT-SWAP | ema_cross | all | 5 | 40.0000 | 11.54700561 | 0.15272562 | -3.35456158 | false |
| 7 | SPCX-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 0.51000324 | 0.51000324 | 0.51000324 | false |
| 8 | SOXL-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 2.06521702 | 2.06521702 | 2.06521702 | false |
| 9 | XAU-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 1.03813688 | 1.03813688 | 1.03813688 | false |
| 10 | SOL-USDT-SWAP | ema_cross | all | 1 | 0.0000 | 11.45819702 | 11.45819702 | 11.45819702 | false |
| 11 | SOXL-USDT-SWAP | rsi_revert | all | 6 | 50.0000 | 6.34453751 | -0.04007430 | -8.45814358 | false |
| 12 | HYPE-USDT-SWAP | ema_cross | all | 2 | 50.0000 | 7.06995421 | 3.64961010 | -2.37087599 | false |
| 13 | HYPE-USDT-SWAP | rsi_revert | all | 2 | 50.0000 | 2.78957567 | 1.43117629 | -1.62266678 | false |
| 14 | HYPE-USDT-SWAP | rsi_revert | all | 6 | 66.6667 | -1.12835959 | 0.12133412 | -1.98720553 | false |
| 15 | SOXL-USDT-SWAP | rsi_revert | all | 6 | 66.6667 | -1.19991393 | 0.75516960 | -7.30552111 | false |
| 16 | SOL-USDT-SWAP | ema_cross | all | 2 | 0.0000 | 6.74656948 | 3.62032999 | -4.28636581 | false |
| 17 | HYPE-USDT-SWAP | ema_cross | all | 3 | 33.3333 | 2.98956037 | -1.81745798 | -4.10722001 | false |
| 18 | SKHYNIX-USDT-SWAP | rsi_revert | all | 2 | 50.0000 | -0.55217832 | -0.27401335 | -0.97418825 | false |
| 19 | SOL-USDT-SWAP | donchian_breakout | all | 4 | 0.0000 | 5.23106499 | 1.42034764 | -1.18589857 | false |
| 20 | HYPE-USDT-SWAP | trend_pullback | all | 2 | 50.0000 | -2.19265275 | -1.09240917 | -2.49839570 | false |
| 21 | MU-USDT-SWAP | ema_cross | all | 2 | 0.0000 | 4.65850808 | 2.33452934 | -0.21597787 | false |
| 22 | SPCX-USDT-SWAP | donchian_breakout | all | 4 | 25.0000 | 2.58966175 | 0.23948028 | -6.90034301 | false |
| 23 | HYPE-USDT-SWAP | bollinger_revert | all | 2 | 50.0000 | -2.38864904 | -1.18418761 | -3.03612813 | false |
| 24 | MU-USDT-SWAP | rsi_revert | all | 2 | 50.0000 | -2.29766023 | -1.09132930 | -4.65379502 | false |
| 25 | MU-USDT-SWAP | ema_cross | all | 3 | 33.3333 | 0.40756871 | -1.13353097 | -3.14609258 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 2.01116022 | -0.19355944 | 1.745385 | 1.19696004 | false |
| 1 | 2 | ETH-USDT-SWAP | bollinger_revert | all | 1.10571357 | -0.52551765 | 1.241793 | 1.33517626 | false |
| 1 | 3 | ETH-USDT-SWAP | rsi_revert | all | 0.85720430 | -0.35615426 | 1.553995 | 0.79736874 | false |
| 2 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 1.81483565 | -9.44733690 | 0.095810 | 10.43623940 | false |
| 2 | 2 | ETH-USDT-SWAP | bollinger_revert | all | 0.22190848 | -9.49050547 | 0.129625 | 10.48052179 | false |
| 3 | 1 | ETH-USDT-SWAP | ema_cross | all | 0.86438393 | 0.01625121 | 1.226747 | 4.58997643 | true |
| 4 | 1 | ETH-USDT-SWAP | ema_cross | all | 4.36387274 | -6.20150929 | 0.274959 | 7.24612346 | false |
| 4 | 2 | ETH-USDT-SWAP | ema_cross | all | 3.34021317 | -4.80008024 | 0.293201 | 5.86030183 | false |
| 4 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 0.52998006 | -0.48844076 | 0.994375 | 2.26272016 | false |
| 5 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 2.71061898 | -3.75512480 | 0.086890 | 3.91057058 | false |
| 5 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 2.71061898 | -2.32549041 | 0.137309 | 2.48324520 | false |
| 5 | 3 | ETH-USDT-SWAP | ema_cross | all | 4.00990742 | -3.39733378 | 0.368948 | 4.89795732 | false |
| 6 | 1 | ETH-USDT-SWAP | keltner_breakout | all | 5.48458793 | -4.71736391 | 0.128737 | 4.80488814 | false |
| 6 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 3.59011114 | -3.39737381 | 0.116708 | 3.59263758 | false |
| 6 | 3 | ETH-USDT-SWAP | keltner_breakout | all | 2.10588759 | -4.26530900 | 0.178017 | 4.59318579 | false |
| 7 | 1 | ETH-USDT-SWAP | rsi_revert | all | 1.26674062 | -0.39543864 | 1.000414 | 1.09597813 | false |
| 8 | 1 | ETH-USDT-SWAP | rsi_revert | all | 0.95870668 | -0.72976174 | 0.653750 | 1.48703356 | false |
| 9 | 1 | ETH-USDT-SWAP | donchian_breakout | all | 0.09299156 | -5.47579949 | 0.316814 | 8.73018675 | false |
| 11 | 1 | ETH-USDT-SWAP | ema_cross | all | 5.83230006 | -0.79020708 | 0.707890 | 5.29190654 | false |
| 11 | 2 | ETH-USDT-SWAP | ema_cross | all | 6.83475798 | -4.66617611 | 0.103527 | 5.54976197 | false |
| 11 | 3 | ETH-USDT-SWAP | ema_cross | all | 5.01233469 | -5.84679870 | 0.041064 | 7.20406743 | false |
| 12 | 1 | ETH-USDT-SWAP | ema_cross | all | 7.97402857 | 1.43929238 | 999.000000 | 1.48567342 | false |
| 12 | 2 | ETH-USDT-SWAP | ema_cross | all | 5.63013026 | 0.10341697 | 1.409381 | 1.82883960 | true |
| 12 | 3 | ETH-USDT-SWAP | ema_cross | all | 5.10246556 | 1.34327543 | 3.861870 | 1.45696720 | true |
| 13 | 1 | ETH-USDT-SWAP | ema_cross | all | 7.04404251 | -6.53722444 | 0.000000 | 6.43400543 | false |
