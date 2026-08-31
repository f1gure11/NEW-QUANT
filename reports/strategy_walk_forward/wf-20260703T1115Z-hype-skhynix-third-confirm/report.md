# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 250 |
| Passed window rows | 57 |
| Unique aggregate candidates | 163 |
| Passed aggregate candidates | 1 |
| Median selected test return | -0.778353% |
| Mean selected test return | -1.439570% |
| Best aggregate return | 7.645081% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 5.28289433 | 5.28289433 | 5.28289433 | false |
| 2 | HYPE-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 5.01215613 | 5.01215613 | 5.01215613 | false |
| 3 | SKHYNIX-USDT-SWAP | macd_signal | trend | 1 | 100.0000 | 4.78182712 | 4.78182712 | 4.78182712 | false |
| 4 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 2.22847952 | 2.22847952 | 2.22847952 | false |
| 5 | HYPE-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.84742128 | 0.84742128 | 0.84742128 | false |
| 6 | HYPE-USDT-SWAP | trend_pullback | trend_high_vol | 1 | 100.0000 | 0.63248799 | 0.63248799 | 0.63248799 | false |
| 7 | HYPE-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 0.83373052 | 0.83373052 | 0.83373052 | false |
| 8 | SKHYNIX-USDT-SWAP | volatility_squeeze_breakout | trend | 1 | 100.0000 | 1.11895692 | 1.11895692 | 1.11895692 | false |
| 9 | SKHYNIX-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 0.67622255 | 0.67622255 | 0.67622255 | false |
| 10 | SKHYNIX-USDT-SWAP | trend_pullback | range_normal_vol | 1 | 100.0000 | 0.35323696 | 0.35323696 | 0.35323696 | false |
| 11 | SKHYNIX-USDT-SWAP | macd_signal | high_vol | 1 | 100.0000 | 0.29273354 | 0.29273354 | 0.29273354 | false |
| 12 | SKHYNIX-USDT-SWAP | trend_pullback | all | 1 | 100.0000 | 0.02891483 | 0.02891483 | 0.02891483 | false |
| 13 | HYPE-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.29778230 | 0.29778230 | 0.29778230 | false |
| 14 | SKHYNIX-USDT-SWAP | atr_vol_breakout | normal_vol | 1 | 100.0000 | 0.93377733 | 0.93377733 | 0.93377733 | false |
| 15 | HYPE-USDT-SWAP | rsi_revert | range_normal_vol | 1 | 100.0000 | 0.19308165 | 0.19308165 | 0.19308165 | false |
| 16 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 3 | 66.6667 | 4.39821441 | 0.07080973 | -0.72023376 | true |
| 17 | SKHYNIX-USDT-SWAP | ema_cross | all | 1 | 100.0000 | 0.11025941 | 0.11025941 | 0.11025941 | false |
| 18 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 0.07080973 | 0.07080973 | 0.07080973 | false |
| 19 | SKHYNIX-USDT-SWAP | donchian_breakout | all | 1 | 100.0000 | 1.47449546 | 1.47449546 | 1.47449546 | false |
| 20 | HYPE-USDT-SWAP | ema_cross | all | 3 | 33.3333 | 7.64508085 | 2.18838219 | -1.23878212 | false |
| 21 | SKHYNIX-USDT-SWAP | macd_signal | trend_down | 2 | 50.0000 | 4.19110545 | 2.10315887 | -0.33497679 | false |
| 22 | HYPE-USDT-SWAP | rsi_revert | trend_high_vol | 2 | 50.0000 | 2.27066488 | 1.12924850 | 0.88756021 | false |
| 23 | HYPE-USDT-SWAP | rsi_revert | all | 3 | 33.3333 | 3.99432617 | 0.88756021 | 0.51568649 | false |
| 24 | SKHYNIX-USDT-SWAP | trend_pullback | range_normal_vol | 2 | 50.0000 | 0.79598415 | 0.39793084 | 0.01569871 | false |
| 25 | HYPE-USDT-SWAP | ema_cross | all | 4 | 25.0000 | 6.18034076 | 0.92410223 | -1.86688299 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | HYPE-USDT-SWAP | trend_pullback | trend_down | 3.88071638 | -0.24055162 | 0.000000 | 0.60306821 | false |
| 1 | 2 | HYPE-USDT-SWAP | bollinger_revert | mixed | 2.33490532 | -1.23392402 | 0.304861 | 1.53658982 | false |
| 1 | 3 | HYPE-USDT-SWAP | rsi_revert | mixed | 2.53099426 | -0.50155713 | 0.494627 | 0.76055549 | false |
| 1 | 4 | HYPE-USDT-SWAP | rsi_revert | mixed | 2.04954284 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 1 | 5 | HYPE-USDT-SWAP | macd_signal | trend_up | 5.04182765 | -6.05598859 | 0.413820 | 6.22539764 | false |
| 2 | 1 | HYPE-USDT-SWAP | ema_cross | all | 12.97595414 | 2.18838219 | 3.345890 | 3.66532702 | true |
| 2 | 2 | HYPE-USDT-SWAP | ema_cross | all | 11.23900982 | -2.96089796 | 0.437709 | 5.60769154 | false |
| 2 | 3 | HYPE-USDT-SWAP | trend_pullback | all | 6.49245096 | -0.51509871 | 1.059213 | 3.07339714 | false |
| 2 | 4 | HYPE-USDT-SWAP | ema_cross | all | 9.60505880 | 2.92882700 | 5.761747 | 3.47736289 | true |
| 2 | 5 | HYPE-USDT-SWAP | donchian_breakout | trend_down | 5.56118414 | -0.43052220 | 0.593067 | 2.57743591 | false |
| 3 | 1 | HYPE-USDT-SWAP | ema_cross | all | 11.21191734 | 6.66114166 | 999.000000 | 3.21718976 | false |
| 3 | 2 | HYPE-USDT-SWAP | ema_cross | all | 9.75665991 | 6.26986360 | 999.000000 | 3.58262159 | false |
| 3 | 3 | HYPE-USDT-SWAP | rsi_revert | trend_up | 4.92717229 | -0.53360938 | 0.939344 | 1.36029645 | false |
| 3 | 4 | HYPE-USDT-SWAP | trend_pullback | all | 4.86609623 | -2.47522098 | 0.520557 | 3.21318914 | false |
| 3 | 5 | HYPE-USDT-SWAP | trend_pullback | all | 4.61239276 | 0.85996511 | 1.584063 | 2.29412530 | true |
| 4 | 1 | HYPE-USDT-SWAP | atr_vol_breakout | all | 14.81009922 | -5.58414435 | 0.203823 | 6.97497213 | false |
| 4 | 2 | HYPE-USDT-SWAP | ema_cross | all | 13.40515851 | -1.08062253 | 0.804656 | 4.54273003 | false |
| 4 | 3 | HYPE-USDT-SWAP | ema_cross | all | 12.22535495 | -1.55520915 | 0.718619 | 3.63232064 | false |
| 4 | 4 | HYPE-USDT-SWAP | trend_pullback | mixed | 5.17246783 | 0.02915325 | 2.076872 | 0.88519403 | true |
| 4 | 5 | HYPE-USDT-SWAP | rsi_revert | trend_up | 5.34967821 | 0.00240394 | 2.181202 | 0.45158862 | true |
| 5 | 1 | HYPE-USDT-SWAP | trend_pullback | mixed | 5.00637520 | 0.28434876 | 2.748212 | 0.72851034 | true |
| 5 | 2 | HYPE-USDT-SWAP | ema_cross | all | 8.82569287 | -1.23878212 | 0.836160 | 5.96109775 | false |
| 5 | 3 | HYPE-USDT-SWAP | ema_cross | all | 8.80416476 | -1.86688299 | 0.747681 | 6.61868274 | false |
| 5 | 4 | HYPE-USDT-SWAP | trend_pullback | mixed | 3.97296456 | 0.04020897 | 999.000000 | 0.10986803 | false |
| 5 | 5 | HYPE-USDT-SWAP | trend_pullback | mixed | 2.19025023 | -0.43348824 | 1.124531 | 1.15258185 | false |
