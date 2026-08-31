# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 382 |
| Passed window rows | 105 |
| Unique aggregate candidates | 170 |
| Passed aggregate candidates | 5 |
| Median selected test return | -1.519699% |
| Mean selected test return | -1.730720% |
| Best aggregate return | 40.106996% |

## Top Aggregates

| Rank | Instrument | Strategy | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | rsi_revert | 2 | 100.0000 | 27.02478458 | 12.71146139 | 11.53033000 | false |
| 2 | BASED-USDT-SWAP | donchian_breakout | 4 | 0.0000 | 40.10699635 | 9.42459214 | -2.30188211 | false |
| 3 | LAB-USDT-SWAP | atr_vol_breakout | 3 | 33.3333 | 36.44787524 | 10.17100445 | -7.16292444 | false |
| 4 | SPCX-USDT-SWAP | bollinger_revert | 2 | 100.0000 | 18.84374174 | 9.29342582 | 1.50376905 | false |
| 5 | LAB-USDT-SWAP | bollinger_revert | 6 | 33.3333 | 33.32464832 | 3.93808962 | -12.48588066 | false |
| 6 | HYPE-USDT-SWAP | ema_cross | 1 | 100.0000 | 8.34366712 | 8.34366712 | 8.34366712 | false |
| 7 | HYPE-USDT-SWAP | rsi_revert | 6 | 83.3333 | 10.17750642 | 1.69555840 | -1.78163036 | true |
| 8 | HYPE-USDT-SWAP | rsi_revert | 1 | 100.0000 | 5.17358494 | 5.17358494 | 5.17358494 | false |
| 9 | LAB-USDT-SWAP | rsi_revert | 2 | 50.0000 | 15.95570369 | 7.78602598 | 3.06829057 | false |
| 10 | HYPE-USDT-SWAP | ema_cross | 4 | 75.0000 | 9.83926423 | 2.93123710 | -3.39632659 | false |
| 11 | HYPE-USDT-SWAP | macd_signal | 1 | 100.0000 | 4.32755612 | 4.32755612 | 4.32755612 | false |
| 12 | HYPE-USDT-SWAP | ema_cross | 4 | 75.0000 | 9.95507575 | 3.00937094 | -2.60843508 | true |
| 13 | SOL-USDT-SWAP | ema_cross | 2 | 50.0000 | 10.59722358 | 5.21398093 | 2.01094706 | false |
| 14 | SPCX-USDT-SWAP | bollinger_revert | 1 | 100.0000 | 1.24311141 | 1.24311141 | 1.24311141 | false |
| 15 | SPCX-USDT-SWAP | atr_vol_breakout | 3 | 100.0000 | 2.88768959 | 0.13151018 | 0.04186153 | true |
| 16 | LAB-USDT-SWAP | atr_vol_breakout | 3 | 0.0000 | 21.69565021 | 8.06270780 | -4.21627167 | false |
| 17 | SOL-USDT-SWAP | rsi_revert | 1 | 100.0000 | 0.55585563 | 0.55585563 | 0.55585563 | false |
| 18 | SPCX-USDT-SWAP | donchian_breakout | 2 | 50.0000 | 8.63749204 | 4.32352607 | -0.10918057 | false |
| 19 | HYPE-USDT-SWAP | ema_cross | 1 | 100.0000 | 1.72907755 | 1.72907755 | 1.72907755 | false |
| 20 | SOL-USDT-SWAP | ema_cross | 3 | 33.3333 | 8.85807604 | 2.16565148 | -3.49479868 | false |
| 21 | SNDK-USDT-SWAP | bollinger_revert | 1 | 100.0000 | 0.96077905 | 0.96077905 | 0.96077905 | false |
| 22 | HYPE-USDT-SWAP | ema_cross | 2 | 50.0000 | 6.36118469 | 3.18669489 | -0.18606850 | false |
| 23 | BASED-USDT-SWAP | ema_cross | 2 | 50.0000 | 9.27468747 | 5.27570085 | -7.19444119 | false |
| 24 | SOL-USDT-SWAP | donchian_breakout | 3 | 66.6667 | 3.15324179 | 0.73618244 | 0.20654706 | true |
| 25 | HYPE-USDT-SWAP | rsi_revert | 5 | 60.0000 | 3.13662970 | 0.54117932 | -1.06748997 | true |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | bollinger_revert | 1.69748457 | -2.32970066 | 0.142011 | 2.60383998 | false |
| 1 | 2 | BTC-USDT-SWAP | bollinger_revert | 2.79596443 | -0.15612893 | 1.487852 | 0.86126451 | false |
| 1 | 3 | BTC-USDT-SWAP | rsi_revert | 1.43057876 | -1.18799148 | 0.479959 | 2.05078622 | false |
| 2 | 1 | BTC-USDT-SWAP | bollinger_revert | 0.18609526 | -1.86107667 | 0.422526 | 1.88443113 | false |
| 2 | 2 | BTC-USDT-SWAP | bollinger_revert | 1.19156108 | -0.79674348 | 0.682524 | 1.17800761 | false |
| 2 | 3 | BTC-USDT-SWAP | bollinger_revert | 0.49372851 | -1.10471352 | 0.441644 | 1.48481054 | false |
| 4 | 1 | BTC-USDT-SWAP | ema_cross | 0.33490518 | -6.13464115 | 0.175842 | 6.21247296 | false |
| 6 | 1 | BTC-USDT-SWAP | atr_vol_breakout | 3.18503097 | -3.75889425 | 0.224573 | 4.71780134 | false |
| 6 | 2 | BTC-USDT-SWAP | atr_vol_breakout | 2.72981879 | -2.43407287 | 0.282171 | 3.13367055 | false |
| 6 | 3 | BTC-USDT-SWAP | ema_cross | 0.65021037 | 0.95525338 | 2.176262 | 1.58203137 | true |
| 7 | 1 | BTC-USDT-SWAP | ema_cross | 1.15791506 | -1.95001220 | 0.334311 | 3.74306572 | false |
| 7 | 2 | BTC-USDT-SWAP | macd_signal | 0.42255744 | -2.56029576 | 0.558469 | 3.63645725 | false |
| 7 | 3 | BTC-USDT-SWAP | ema_cross | 0.80771410 | -1.53148556 | 0.441546 | 3.33216542 | false |
| 8 | 1 | BTC-USDT-SWAP | rsi_revert | 0.48242678 | 0.51396035 | 9.535040 | 0.88519754 | true |
| 8 | 2 | BTC-USDT-SWAP | rsi_revert | 0.25213234 | -0.40641120 | 1.115843 | 1.51209228 | false |
| 9 | 1 | BTC-USDT-SWAP | rsi_revert | 1.18537817 | -2.18764589 | 0.174515 | 2.96047439 | false |
| 10 | 1 | BTC-USDT-SWAP | donchian_breakout | 2.93027407 | -0.27621104 | 0.995431 | 4.96848522 | false |
| 10 | 2 | BTC-USDT-SWAP | donchian_breakout | 1.62782458 | -3.69729178 | 0.546142 | 8.22859484 | false |
| 10 | 3 | BTC-USDT-SWAP | ema_cross | 0.21324621 | 1.35124302 | 1.741393 | 3.44449456 | true |
| 11 | 1 | BTC-USDT-SWAP | donchian_breakout | 1.40963497 | -2.35585211 | 0.366402 | 4.06761930 | false |
| 11 | 2 | BTC-USDT-SWAP | ema_cross | 0.85697512 | 0.55635439 | 1.359738 | 3.29209612 | true |
| 12 | 1 | BTC-USDT-SWAP | donchian_breakout | 6.20694152 | -4.64550581 | 0.318669 | 6.11055770 | false |
| 12 | 2 | BTC-USDT-SWAP | ema_cross | 1.80555147 | -3.74542798 | 0.059551 | 4.82423725 | false |
| 12 | 3 | BTC-USDT-SWAP | atr_vol_breakout | 1.41781344 | -4.44929537 | 0.273167 | 5.45718135 | false |
| 13 | 1 | BTC-USDT-SWAP | donchian_breakout | 2.86889334 | -2.82437678 | 0.000000 | 2.80049483 | false |
