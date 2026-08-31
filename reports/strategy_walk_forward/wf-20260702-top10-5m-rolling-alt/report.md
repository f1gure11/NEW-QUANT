# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 551 |
| Passed window rows | 126 |
| Unique aggregate candidates | 211 |
| Passed aggregate candidates | 4 |
| Median selected test return | -1.552754% |
| Mean selected test return | -1.552060% |
| Best aggregate return | 62.057075% |

## Top Aggregates

| Rank | Instrument | Strategy | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | atr_vol_breakout | 3 | 0.0000 | 62.05707450 | 26.83586109 | -0.87688708 | false |
| 2 | LAB-USDT-SWAP | ema_cross | 5 | 40.0000 | 53.25981184 | 7.74156333 | -2.92230595 | false |
| 3 | LAB-USDT-SWAP | ema_cross | 4 | 25.0000 | 38.21774596 | 8.50137628 | 0.05267350 | false |
| 4 | LAB-USDT-SWAP | atr_vol_breakout | 3 | 0.0000 | 36.33895634 | 11.78204490 | -1.72980640 | false |
| 5 | LAB-USDT-SWAP | rsi_revert | 3 | 66.6667 | 22.80339735 | 6.95861150 | 3.06829057 | true |
| 6 | SPCX-USDT-SWAP | bollinger_revert | 2 | 100.0000 | 11.00019845 | 5.44664521 | 1.09059872 | false |
| 7 | LAB-USDT-SWAP | bollinger_revert | 6 | 50.0000 | 19.93761294 | 7.99058897 | -23.47708688 | false |
| 8 | LAB-USDT-SWAP | donchian_breakout | 3 | 33.3333 | 22.89200313 | 7.84071504 | 0.90798974 | false |
| 9 | BASED-USDT-SWAP | donchian_breakout | 3 | 33.3333 | 18.05910350 | 4.27759294 | -0.89647568 | false |
| 10 | HYPE-USDT-SWAP | atr_vol_breakout | 1 | 100.0000 | 5.20289732 | 5.20289732 | 5.20289732 | false |
| 11 | LAB-USDT-SWAP | ema_cross | 2 | 0.0000 | 24.00142818 | 11.63979419 | 3.68361242 | false |
| 12 | HYPE-USDT-SWAP | ema_cross | 4 | 25.0000 | 14.68535445 | 2.27022672 | -2.08222285 | false |
| 13 | HYPE-USDT-SWAP | bollinger_revert | 4 | 75.0000 | 5.32698573 | 1.52288747 | -1.04199946 | true |
| 14 | HYPE-USDT-SWAP | ema_cross | 2 | 100.0000 | 4.11888672 | 2.05157107 | 0.42846136 | false |
| 15 | SPCX-USDT-SWAP | bollinger_revert | 2 | 50.0000 | 10.98801645 | 5.51435986 | -0.35747893 | false |
| 16 | MU-USDT-SWAP | ema_cross | 2 | 100.0000 | 3.90241379 | 1.93994593 | 0.71063848 | false |
| 17 | BASED-USDT-SWAP | rsi_revert | 6 | 33.3333 | 12.71800477 | 0.22196550 | -0.43940788 | false |
| 18 | LAB-USDT-SWAP | ema_cross | 2 | 50.0000 | 13.23301466 | 6.43013532 | 4.41215663 | false |
| 19 | BTC-USDT-SWAP | atr_vol_breakout | 1 | 100.0000 | 0.12084850 | 0.12084850 | 0.12084850 | false |
| 20 | LAB-USDT-SWAP | donchian_breakout | 1 | 100.0000 | 4.53391080 | 4.53391080 | 4.53391080 | false |
| 21 | MU-USDT-SWAP | ema_cross | 3 | 66.6667 | 5.08633187 | 2.44703755 | -0.55124720 | true |
| 22 | MU-USDT-SWAP | bollinger_revert | 3 | 66.6667 | 1.97352334 | 0.83194627 | -1.73381218 | true |
| 23 | SOL-USDT-SWAP | donchian_breakout | 3 | 66.6667 | 2.63247372 | 0.03291225 | -3.20880235 | false |
| 24 | LAB-USDT-SWAP | ema_cross | 2 | 0.0000 | 19.27027133 | 9.77113569 | -1.30474343 | false |
| 25 | XAU-USDT-SWAP | ema_cross | 3 | 66.6667 | -0.60372807 | 0.21851742 | -1.14554502 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | bollinger_revert | 2.58564431 | -0.01918738 | 1.152944 | 2.20123053 | false |
| 1 | 2 | BTC-USDT-SWAP | bollinger_revert | 0.66701949 | 0.74351443 | 2.139762 | 1.54182653 | true |
| 1 | 3 | BTC-USDT-SWAP | rsi_revert | 0.72243044 | -0.18870616 | 0.000000 | 0.75568506 | false |
| 2 | 1 | BTC-USDT-SWAP | bollinger_revert | 2.52799106 | -1.30615662 | 0.570063 | 2.68771766 | false |
| 2 | 2 | BTC-USDT-SWAP | bollinger_revert | 1.62652640 | 0.82256255 | 5.891027 | 0.86126451 | true |
| 2 | 3 | BTC-USDT-SWAP | rsi_revert | 0.19608926 | -0.82469637 | 0.000000 | 0.96133519 | false |
| 5 | 1 | BTC-USDT-SWAP | bollinger_revert | 0.92309396 | -3.60705359 | 0.173971 | 4.30741256 | false |
| 5 | 2 | BTC-USDT-SWAP | bollinger_revert | 0.09417624 | -3.52985121 | 0.206462 | 4.23077112 | false |
| 6 | 1 | BTC-USDT-SWAP | ema_cross | 3.47189975 | -0.91563011 | 0.827366 | 2.61930549 | false |
| 6 | 2 | BTC-USDT-SWAP | ema_cross | 1.92504113 | -1.04142153 | 0.760857 | 3.20013519 | false |
| 6 | 3 | BTC-USDT-SWAP | ema_cross | 1.14806785 | -2.07312793 | 0.550046 | 3.79940636 | false |
| 7 | 1 | BTC-USDT-SWAP | ema_cross | 3.95506918 | -3.43762903 | 0.450911 | 5.69794326 | false |
| 7 | 2 | BTC-USDT-SWAP | atr_vol_breakout | 3.70355824 | 0.12084850 | 1.239351 | 1.69482843 | true |
| 7 | 3 | BTC-USDT-SWAP | ema_cross | 3.07357061 | 0.55686208 | 2.057228 | 1.65901411 | true |
| 8 | 1 | BTC-USDT-SWAP | ema_cross | 3.85706457 | -3.66715678 | 0.363347 | 5.88923102 | false |
| 8 | 2 | BTC-USDT-SWAP | ema_cross | 3.49634208 | -2.90016533 | 0.408823 | 5.17266337 | false |
| 8 | 3 | BTC-USDT-SWAP | ema_cross | 2.59556654 | -2.86155386 | 0.416887 | 5.13495555 | false |
| 9 | 1 | BTC-USDT-SWAP | macd_signal | 1.32168472 | -2.08467170 | 0.465442 | 3.33022925 | false |
| 9 | 2 | BTC-USDT-SWAP | rsi_revert | 0.50068355 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 9 | 3 | BTC-USDT-SWAP | atr_vol_breakout | 0.87997571 | -4.08036975 | 0.000000 | 4.49420853 | false |
| 10 | 1 | BTC-USDT-SWAP | macd_signal | 0.77809758 | -2.69301979 | 0.420775 | 3.63645725 | false |
| 10 | 2 | BTC-USDT-SWAP | rsi_revert | 0.14781272 | -0.04955151 | 1.300281 | 0.81474657 | false |
| 11 | 1 | BTC-USDT-SWAP | macd_signal | 2.25558211 | -1.88353330 | 0.568753 | 2.11267207 | false |
| 11 | 2 | BTC-USDT-SWAP | rsi_revert | 0.59417835 | 0.19689943 | 15.835518 | 0.35671893 | true |
| 11 | 3 | BTC-USDT-SWAP | rsi_revert | 0.29717125 | -0.07228965 | 1.672173 | 0.63511852 | false |
