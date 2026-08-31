# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 559 |
| Passed window rows | 82 |
| Unique aggregate candidates | 403 |
| Passed aggregate candidates | 2 |
| Median selected test return | -1.102114% |
| Mean selected test return | -1.957129% |
| Best aggregate return | 9.366366% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 8.38440995 | 8.38440995 | 8.38440995 | false |
| 2 | SNDK-USDT-SWAP | rsi_trend | high_vol | 1 | 100.0000 | 7.17805625 | 7.17805625 | 7.17805625 | false |
| 3 | SNDK-USDT-SWAP | atr_vol_breakout | high_vol | 2 | 100.0000 | 7.03631106 | 3.45839400 | 3.36793660 | false |
| 4 | HYPE-USDT-SWAP | bollinger_revert | range_normal_vol | 2 | 100.0000 | 3.13544503 | 1.55700446 | 1.02723792 | false |
| 5 | SNDK-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 6.47637268 | 6.47637268 | 6.47637268 | false |
| 6 | SOL-USDT-SWAP | bollinger_revert | high_vol | 2 | 100.0000 | 2.48883823 | 1.24060920 | 0.35906006 | false |
| 7 | SPCX-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 100.0000 | 5.66366901 | 5.66366901 | 5.66366901 | false |
| 8 | SPCX-USDT-SWAP | bollinger_revert | all | 1 | 100.0000 | 5.65375659 | 5.65375659 | 5.65375659 | false |
| 9 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 2.27629221 | 2.27629221 | 2.27629221 | false |
| 10 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 1 | 100.0000 | 2.27629221 | 2.27629221 | 2.27629221 | false |
| 11 | HYPE-USDT-SWAP | rsi_revert | trend | 2 | 100.0000 | 1.70281404 | 0.85023870 | 0.15078052 | false |
| 12 | MU-USDT-SWAP | rsi_revert | range_normal_vol | 2 | 100.0000 | 1.79022167 | 0.89154340 | 0.60630426 | false |
| 13 | SOXL-USDT-SWAP | rsi_revert | all | 3 | 100.0000 | 2.64675618 | 0.44835814 | 0.20575538 | true |
| 14 | SPCX-USDT-SWAP | rsi_trend | high_vol | 1 | 100.0000 | 1.81069917 | 1.81069917 | 1.81069917 | false |
| 15 | SOXL-USDT-SWAP | rsi_revert | trend | 1 | 100.0000 | 0.69851599 | 0.69851599 | 0.69851599 | false |
| 16 | ETH-USDT-SWAP | atr_vol_breakout | trend_up | 1 | 100.0000 | 0.77254258 | 0.77254258 | 0.77254258 | false |
| 17 | HYPE-USDT-SWAP | ema_cross | high_vol | 1 | 100.0000 | 1.95223972 | 1.95223972 | 1.95223972 | false |
| 18 | HYPE-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 0.56389922 | 0.56389922 | 0.56389922 | false |
| 19 | SPCX-USDT-SWAP | bollinger_revert | trend_down | 1 | 100.0000 | 0.04352642 | 0.04352642 | 0.04352642 | false |
| 20 | SOL-USDT-SWAP | bollinger_revert | high_vol | 1 | 100.0000 | 0.89969065 | 0.89969065 | 0.89969065 | false |
| 21 | HYPE-USDT-SWAP | rsi_revert | mixed | 1 | 100.0000 | 0.72175635 | 0.72175635 | 0.72175635 | false |
| 22 | SOXL-USDT-SWAP | rsi_revert | trend | 1 | 100.0000 | 0.11984561 | 0.11984561 | 0.11984561 | false |
| 23 | SKHYNIX-USDT-SWAP | ema_cross | normal_vol | 3 | 66.6667 | 5.49307597 | 0.60673001 | -1.02043601 | true |
| 24 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_down | 1 | 100.0000 | 0.79935348 | 0.79935348 | 0.79935348 | false |
| 25 | BTC-USDT-SWAP | atr_vol_breakout | trend_down | 1 | 100.0000 | 0.80315854 | 0.80315854 | 0.80315854 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | trend_pullback | mixed | 0.11298419 | -0.94408656 | 0.000000 | 0.94408656 | false |
| 1 | 2 | ETH-USDT-SWAP | rsi_revert | trend_down | 0.19428505 | -0.15270089 | 0.000000 | 0.16102625 | false |
| 1 | 3 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.32800852 | -0.53026512 | 0.000000 | 0.92852564 | false |
| 2 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 2.35710973 | -0.95122606 | 0.328052 | 1.30531744 | false |
| 2 | 2 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 2.27263238 | -0.95122606 | 0.328052 | 1.30531744 | false |
| 2 | 3 | ETH-USDT-SWAP | bollinger_revert | range_normal_vol | 2.27263238 | -0.95122606 | 0.328052 | 1.30531744 | false |
| 3 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 1.52855972 | 0.13640784 | 2.513048 | 1.03643631 | true |
| 3 | 2 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 1.44476618 | 0.13640784 | 2.513048 | 1.03643631 | true |
| 3 | 3 | ETH-USDT-SWAP | bollinger_revert | range_normal_vol | 1.44476618 | 0.13640784 | 2.513048 | 1.03643631 | true |
| 4 | 1 | ETH-USDT-SWAP | bollinger_revert | all | 1.28517021 | -9.02811443 | 0.099627 | 10.02159516 | false |
| 4 | 2 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 1.28517021 | -9.02811443 | 0.099627 | 10.02159516 | false |
| 4 | 3 | ETH-USDT-SWAP | bollinger_revert | range_normal_vol | 1.28517021 | -9.02811443 | 0.099627 | 10.02159516 | false |
| 5 | 1 | ETH-USDT-SWAP | atr_vol_breakout | trend_up | 5.36324557 | 0.77254258 | 5.059744 | 1.24768630 | true |
| 5 | 2 | ETH-USDT-SWAP | rsi_trend | trend_up | 5.50930648 | -0.76981542 | 0.464300 | 2.13689195 | false |
| 5 | 3 | ETH-USDT-SWAP | rsi_trend | trend_up | 5.50930648 | -0.76981542 | 0.464300 | 2.13689195 | false |
| 6 | 1 | ETH-USDT-SWAP | ema_cross | all | 10.32234305 | -3.48786706 | 0.266675 | 4.61561443 | false |
| 6 | 2 | ETH-USDT-SWAP | ema_cross | normal_vol | 10.32234305 | -3.48786706 | 0.266675 | 4.61561443 | false |
| 6 | 3 | ETH-USDT-SWAP | ema_cross | range_normal_vol | 10.32234305 | -3.48786706 | 0.266675 | 4.61561443 | false |
| 7 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 4.92137467 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 7 | 2 | ETH-USDT-SWAP | ema_cross | all | 8.74886000 | -4.30898465 | 0.425168 | 7.54255559 | false |
| 7 | 3 | ETH-USDT-SWAP | ema_cross | normal_vol | 8.74886000 | -5.14249461 | 0.436875 | 8.34789976 | false |
| 8 | 1 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.36610691 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 8 | 2 | ETH-USDT-SWAP | volatility_squeeze_breakout | trend_up | 3.36610691 | -0.67830480 | 0.000000 | 1.01828392 | false |
| 8 | 3 | ETH-USDT-SWAP | volatility_squeeze_breakout | all | 2.54564774 | -1.65343156 | 0.192703 | 2.81877563 | false |
| 9 | 1 | ETH-USDT-SWAP | rsi_revert | trend_up | 0.95603662 | 0.01473511 | 999.000000 | 0.10931659 | false |
