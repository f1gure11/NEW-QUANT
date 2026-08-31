# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 38 |
| Passed window rows | 11 |
| Unique aggregate candidates | 20 |
| Passed aggregate candidates | 1 |
| Median selected test return | -0.556673% |
| Mean selected test return | -0.386627% |
| Best aggregate return | 1.948769% |

## Top Aggregates

| Rank | Instrument | Strategy | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | ETH-USDT-SWAP | rsi_revert | 1 | 100.0000 | 1.28999590 | 1.28999590 | 1.28999590 | false |
| 2 | BTC-USDT-SWAP | atr_vol_breakout | 1 | 100.0000 | 0.87874292 | 0.87874292 | 0.87874292 | false |
| 3 | BTC-USDT-SWAP | rsi_revert | 1 | 100.0000 | 0.18069059 | 0.18069059 | 0.18069059 | false |
| 4 | ETH-USDT-SWAP | bollinger_revert | 3 | 66.6667 | 1.29877290 | 0.48766855 | -1.24663734 | true |
| 5 | BTC-USDT-SWAP | bollinger_revert | 5 | 40.0000 | 1.94876857 | 0.43727568 | -0.55667271 | false |
| 6 | ETH-USDT-SWAP | bollinger_revert | 2 | 50.0000 | -0.82482985 | -0.41233360 | -0.84393937 | false |
| 7 | BTC-USDT-SWAP | rsi_revert | 3 | 33.3333 | -1.15871573 | -0.68519046 | -0.90963477 | false |
| 8 | ETH-USDT-SWAP | macd_signal | 3 | 33.3333 | -1.66553515 | -0.73265362 | -2.21393944 | false |
| 9 | BTC-USDT-SWAP | rsi_revert | 1 | 0.0000 | 0.91148295 | 0.91148295 | 0.91148295 | false |
| 10 | BTC-USDT-SWAP | bollinger_revert | 5 | 20.0000 | -1.71514189 | -0.55667271 | -1.22148543 | false |
| 11 | BTC-USDT-SWAP | bollinger_revert | 1 | 0.0000 | -0.18895605 | -0.18895605 | -0.18895605 | false |
| 12 | ETH-USDT-SWAP | ema_cross | 1 | 0.0000 | -0.12815733 | -0.12815733 | -0.12815733 | false |
| 13 | ETH-USDT-SWAP | ema_cross | 1 | 0.0000 | -0.64774366 | -0.64774366 | -0.64774366 | false |
| 14 | ETH-USDT-SWAP | rsi_revert | 1 | 0.0000 | -0.82015617 | -0.82015617 | -0.82015617 | false |
| 15 | ETH-USDT-SWAP | rsi_revert | 2 | 0.0000 | -1.95029972 | -0.97973145 | -1.18842839 | false |
| 16 | ETH-USDT-SWAP | bollinger_revert | 2 | 0.0000 | -2.26815706 | -1.13847639 | -1.78388878 | false |
| 17 | BTC-USDT-SWAP | ema_cross | 1 | 0.0000 | -1.99067034 | -1.99067034 | -1.99067034 | false |
| 18 | BTC-USDT-SWAP | macd_signal | 2 | 0.0000 | -3.14868813 | -1.58478556 | -2.23535905 | false |
| 19 | BTC-USDT-SWAP | ema_cross | 1 | 0.0000 | -2.41671193 | -2.41671193 | -2.41671193 | false |
| 20 | ETH-USDT-SWAP | atr_vol_breakout | 1 | 0.0000 | -2.27894976 | -2.27894976 | -2.27894976 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | macd_signal | 2.08823676 | -0.93421207 | 0.444941 | 1.01814518 | false |
| 1 | 2 | BTC-USDT-SWAP | bollinger_revert | 0.60230173 | -0.25815389 | 0.716761 | 0.61178243 | false |
| 2 | 1 | BTC-USDT-SWAP | bollinger_revert | 0.75225365 | -0.18895605 | 1.193025 | 0.76443243 | false |
| 2 | 2 | BTC-USDT-SWAP | rsi_revert | 0.00664442 | 0.18069059 | 16.975682 | 0.61597493 | true |
| 3 | 1 | BTC-USDT-SWAP | bollinger_revert | 0.46123626 | 0.05654878 | 96.832950 | 0.56685638 | false |
| 3 | 2 | BTC-USDT-SWAP | bollinger_revert | 0.36185720 | 0.43727568 | 999.000000 | 0.33531514 | false |
| 4 | 1 | BTC-USDT-SWAP | bollinger_revert | 1.11889552 | -0.55667271 | 0.365819 | 1.28706568 | false |
| 4 | 2 | BTC-USDT-SWAP | bollinger_revert | 0.24299826 | -0.55667271 | 0.365819 | 1.28706568 | false |
| 5 | 1 | BTC-USDT-SWAP | rsi_revert | 0.55674700 | 0.91148295 | 999.000000 | 0.08122188 | false |
| 5 | 2 | BTC-USDT-SWAP | bollinger_revert | 0.66498761 | 1.48586199 | 999.000000 | 0.59304782 | true |
| 6 | 1 | BTC-USDT-SWAP | bollinger_revert | 1.51140753 | 0.83898511 | 2.581811 | 0.94226728 | true |
| 6 | 2 | BTC-USDT-SWAP | bollinger_revert | 1.40971819 | 0.61231274 | 2.259107 | 0.94226728 | true |
| 7 | 1 | BTC-USDT-SWAP | rsi_revert | 3.23199234 | -0.68519046 | 0.219009 | 1.22404683 | false |
| 7 | 2 | BTC-USDT-SWAP | bollinger_revert | 2.12189518 | -0.60790928 | 0.512903 | 1.13928926 | false |
| 8 | 1 | BTC-USDT-SWAP | rsi_revert | 3.11256776 | -0.90963477 | 0.067372 | 1.39073106 | false |
| 8 | 2 | BTC-USDT-SWAP | bollinger_revert | 2.07289495 | -1.22148543 | 0.056724 | 1.74370646 | false |
| 9 | 1 | BTC-USDT-SWAP | rsi_revert | 1.27906347 | 0.43681600 | 999.000000 | 0.23498273 | true |
| 9 | 2 | BTC-USDT-SWAP | macd_signal | 0.00031415 | -2.23535905 | 0.161196 | 2.73768712 | false |
| 10 | 1 | BTC-USDT-SWAP | ema_cross | 0.83236102 | -1.99067034 | 0.000000 | 2.08393656 | false |
| 10 | 2 | BTC-USDT-SWAP | ema_cross | 0.70922126 | -2.41671193 | 0.000000 | 2.48505252 | false |
| 11 | 1 | BTC-USDT-SWAP | atr_vol_breakout | 0.07143385 | 0.87874292 | 1.882969 | 1.39202221 | true |
| 1 | 1 | ETH-USDT-SWAP | bollinger_revert | 1.07247315 | -1.24663734 | 0.196047 | 1.60929647 | false |
| 1 | 2 | ETH-USDT-SWAP | macd_signal | 1.21729559 | -0.73265362 | 0.793808 | 1.98886752 | false |
| 3 | 1 | ETH-USDT-SWAP | bollinger_revert | 0.27159181 | 0.01927216 | 2.711932 | 0.72689659 | true |
| 3 | 2 | ETH-USDT-SWAP | bollinger_revert | 0.06196519 | 0.48766855 | 999.000000 | 0.60481663 | true |
