# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 44 |
| Passed window rows | 11 |
| Unique aggregate candidates | 33 |
| Passed aggregate candidates | 0 |
| Median selected test return | -0.128157% |
| Mean selected test return | -0.225163% |
| Best aggregate return | 1.303021% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | ETH-USDT-SWAP | rsi_revert | all | 1 | 100.0000 | 1.28999590 | 1.28999590 | 1.28999590 | false |
| 2 | ETH-USDT-SWAP | rsi_revert | normal_vol | 1 | 100.0000 | 1.28999590 | 1.28999590 | 1.28999590 | false |
| 3 | ETH-USDT-SWAP | macd_signal | range_normal_vol | 1 | 100.0000 | 1.30302076 | 1.30302076 | 1.30302076 | false |
| 4 | ETH-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.93367944 | 0.93367944 | 0.93367944 | false |
| 5 | ETH-USDT-SWAP | bollinger_revert | trend | 1 | 100.0000 | 0.86396130 | 0.86396130 | 0.86396130 | false |
| 6 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 1 | 100.0000 | 0.01927216 | 0.01927216 | 0.01927216 | false |
| 7 | BTC-USDT-SWAP | bollinger_revert | all | 2 | 50.0000 | 0.27764200 | 0.14115620 | -0.55667271 | false |
| 8 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 2 | 50.0000 | 0.27764200 | 0.14115620 | -0.55667271 | false |
| 9 | ETH-USDT-SWAP | macd_signal | normal_vol | 2 | 50.0000 | -0.93976676 | -0.45545934 | -2.21393944 | false |
| 10 | ETH-USDT-SWAP | bollinger_revert | all | 2 | 50.0000 | -0.82482985 | -0.41233360 | -0.84393937 | false |
| 11 | ETH-USDT-SWAP | rsi_revert | mixed | 3 | 33.3333 | -2.10973076 | -1.40662771 | -2.03583471 | false |
| 12 | BTC-USDT-SWAP | rsi_revert | all | 1 | 0.0000 | 0.91148295 | 0.91148295 | 0.91148295 | false |
| 13 | BTC-USDT-SWAP | rsi_revert | normal_vol | 1 | 0.0000 | 0.91148295 | 0.91148295 | 0.91148295 | false |
| 14 | BTC-USDT-SWAP | bollinger_revert | trend | 1 | 0.0000 | 0.00000000 | 0.00000000 | 0.00000000 | false |
| 15 | BTC-USDT-SWAP | bollinger_revert | trend_high_vol | 1 | 0.0000 | 0.00000000 | 0.00000000 | 0.00000000 | false |
| 16 | BTC-USDT-SWAP | bollinger_revert | trend | 2 | 0.0000 | -0.07688873 | -0.03844436 | -0.07688873 | false |
| 17 | BTC-USDT-SWAP | bollinger_revert | trend_high_vol | 2 | 0.0000 | -0.07688873 | -0.03844436 | -0.07688873 | false |
| 18 | BTC-USDT-SWAP | bollinger_revert | all | 1 | 0.0000 | 0.05654878 | 0.05654878 | 0.05654878 | false |
| 19 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 1 | 0.0000 | 0.05654878 | 0.05654878 | 0.05654878 | false |
| 20 | ETH-USDT-SWAP | ema_cross | all | 1 | 0.0000 | -0.12815733 | -0.12815733 | -0.12815733 | false |
| 21 | ETH-USDT-SWAP | ema_cross | normal_vol | 1 | 0.0000 | -0.12815733 | -0.12815733 | -0.12815733 | false |
| 22 | BTC-USDT-SWAP | rsi_revert | trend | 1 | 0.0000 | -0.33429268 | -0.33429268 | -0.33429268 | false |
| 23 | BTC-USDT-SWAP | rsi_revert | trend_high_vol | 1 | 0.0000 | -0.33429268 | -0.33429268 | -0.33429268 | false |
| 24 | BTC-USDT-SWAP | macd_signal | all | 1 | 0.0000 | -0.93421207 | -0.93421207 | -0.93421207 | false |
| 25 | BTC-USDT-SWAP | macd_signal | normal_vol | 1 | 0.0000 | -0.93421207 | -0.93421207 | -0.93421207 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | macd_signal | all | 2.08823676 | -0.93421207 | 0.444941 | 1.01814518 | false |
| 1 | 2 | BTC-USDT-SWAP | macd_signal | normal_vol | 2.08823676 | -0.93421207 | 0.444941 | 1.01814518 | false |
| 2 | 1 | BTC-USDT-SWAP | bollinger_revert | trend | 1.31981101 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 2 | 2 | BTC-USDT-SWAP | bollinger_revert | trend_high_vol | 1.31981101 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 3 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 0.46123626 | 0.05654878 | 96.832950 | 0.56685638 | false |
| 3 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 0.46123626 | 0.05654878 | 96.832950 | 0.56685638 | false |
| 4 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 1.11889552 | -0.55667271 | 0.365819 | 1.28706568 | false |
| 4 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 1.11889552 | -0.55667271 | 0.365819 | 1.28706568 | false |
| 5 | 1 | BTC-USDT-SWAP | rsi_revert | all | 0.55674700 | 0.91148295 | 999.000000 | 0.08122188 | false |
| 5 | 2 | BTC-USDT-SWAP | rsi_revert | normal_vol | 0.55674700 | 0.91148295 | 999.000000 | 0.08122188 | false |
| 6 | 1 | BTC-USDT-SWAP | bollinger_revert | all | 1.51140753 | 0.83898511 | 2.581811 | 0.94226728 | true |
| 6 | 2 | BTC-USDT-SWAP | bollinger_revert | normal_vol | 1.51140753 | 0.83898511 | 2.581811 | 0.94226728 | true |
| 7 | 1 | BTC-USDT-SWAP | rsi_revert | all | 3.23199234 | -0.68519046 | 0.219009 | 1.22404683 | false |
| 7 | 2 | BTC-USDT-SWAP | rsi_revert | normal_vol | 3.23199234 | -0.68519046 | 0.219009 | 1.22404683 | false |
| 8 | 1 | BTC-USDT-SWAP | rsi_revert | all | 3.11256776 | -0.90963477 | 0.067372 | 1.39073106 | false |
| 8 | 2 | BTC-USDT-SWAP | rsi_revert | normal_vol | 3.11256776 | -0.90963477 | 0.067372 | 1.39073106 | false |
| 9 | 1 | BTC-USDT-SWAP | bollinger_revert | trend | 2.15853728 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 9 | 2 | BTC-USDT-SWAP | bollinger_revert | trend_high_vol | 2.15853728 | 0.00000000 | 0.000000 | 0.00000000 | false |
| 10 | 1 | BTC-USDT-SWAP | bollinger_revert | trend | 0.86601574 | -0.07688873 | 0.000000 | 0.39237665 | false |
| 10 | 2 | BTC-USDT-SWAP | bollinger_revert | trend_high_vol | 0.86601574 | -0.07688873 | 0.000000 | 0.39237665 | false |
| 11 | 1 | BTC-USDT-SWAP | rsi_revert | trend | 0.67562756 | -0.33429268 | 0.297446 | 1.51801668 | false |
| 11 | 2 | BTC-USDT-SWAP | rsi_revert | trend_high_vol | 0.67562756 | -0.33429268 | 0.297446 | 1.51801668 | false |
| 1 | 1 | ETH-USDT-SWAP | bollinger_revert | normal_vol | 1.65989856 | -1.24663734 | 0.196047 | 1.60929647 | false |
| 1 | 2 | ETH-USDT-SWAP | bollinger_revert | range_normal_vol | 1.65989856 | -1.24663734 | 0.196047 | 1.60929647 | false |
| 2 | 1 | ETH-USDT-SWAP | bollinger_revert | trend | 0.33526101 | 0.93367944 | 31.354895 | 0.46752587 | true |
