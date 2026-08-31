# Multi-Strategy Search

Read-only train/test search over independent strategy families.

## Summary

| Metric | Value |
| --- | ---: |
| Tested configs | 520 |
| Passed configs | 0 |
| Passed rate | 0.00% |
| Best test return | 99.284638% |
| Median test return | -17.313368% |
| Mean test return | -18.049208% |
| Median positive holdout-fold rate | 25.00% |

## Top 25

Ranked by train-only selection score. Test columns are holdout validation.

| Rank | Instrument | Strategy | Family | Train Ret % | Train Score | Test Ret % | Test PF | Test DD % | Folds +/N | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 52.87751775 | 24.03728857 | -23.98207196 | 0.866735 | 54.70711606 | 2/4 | false |
| 2 | LAB-USDT-SWAP | ema_cross | trend | 48.15670490 | 17.28411658 | 4.19737043 | 1.089427 | 40.38227547 | 3/4 | false |
| 3 | LAB-USDT-SWAP | ema_cross | trend | 40.85016295 | 8.03582284 | 17.13541044 | 1.209521 | 44.37878208 | 3/4 | false |
| 4 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 36.22682001 | 7.98908141 | -35.29657897 | 0.799692 | 47.47258946 | 2/4 | false |
| 5 | SNDK-USDT-SWAP | rsi_revert | mean_reversion | 9.07922769 | 4.91740972 | -8.81795059 | 0.641913 | 15.18368680 | 1/4 | false |
| 6 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 29.97412733 | 4.21316006 | -12.11823099 | 0.979146 | 44.63568934 | 1/4 | false |
| 7 | BASED-USDT-SWAP | bollinger_revert | mean_reversion | 17.41791884 | 2.77296365 | -14.08208382 | 0.919144 | 31.53550402 | 1/4 | false |
| 8 | BASED-USDT-SWAP | bollinger_revert | mean_reversion | 15.23303458 | 0.57066975 | -21.28613961 | 0.838879 | 39.76613464 | 1/4 | false |
| 9 | XAU-USDT-SWAP | donchian_breakout | breakout | -0.85234519 | -2.67493543 | -0.83503928 | 1.085763 | 6.02740233 | 2/4 | false |
| 10 | SPCX-USDT-SWAP | rsi_revert | mean_reversion | 10.03044847 | -5.11518574 | -8.40291784 | 0.751640 | 15.25950751 | 1/4 | false |
| 11 | LAB-USDT-SWAP | volatility_squeeze_breakout | breakout | 2.08599814 | -6.40249542 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
| 12 | LAB-USDT-SWAP | volatility_squeeze_breakout | breakout | 2.08599814 | -6.40249542 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
| 13 | SNDK-USDT-SWAP | donchian_breakout | breakout | 3.84800743 | -6.65505213 | -10.07063575 | 0.783777 | 31.05499428 | 2/4 | false |
| 14 | LAB-USDT-SWAP | bollinger_revert | mean_reversion | 29.35360934 | -7.15407830 | -6.88347382 | 1.030099 | 43.55012654 | 2/4 | false |
| 15 | BTC-USDT-SWAP | rsi_revert | mean_reversion | -4.57698026 | -7.82135785 | -11.31711113 | 0.402759 | 11.71739515 | 1/4 | false |
| 16 | HYPE-USDT-SWAP | rsi_revert | mean_reversion | -0.01791832 | -9.10878520 | -2.48536230 | 0.942755 | 7.13403138 | 1/4 | false |
| 17 | ETH-USDT-SWAP | rsi_revert | mean_reversion | -4.57880083 | -9.53963989 | -9.87248208 | 0.466930 | 11.60679209 | 1/4 | false |
| 18 | LAB-USDT-SWAP | volatility_squeeze_breakout | breakout | -0.85291819 | -9.95525275 | -2.13338809 | 0.000000 | 2.13338809 | 0/4 | false |
| 19 | SPCX-USDT-SWAP | rsi_revert | mean_reversion | 4.55069278 | -9.97470056 | -13.18036722 | 0.720946 | 19.78121415 | 1/4 | false |
| 20 | BASED-USDT-SWAP | volatility_squeeze_breakout | breakout | 0.00000000 | -10.00000000 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
| 21 | BASED-USDT-SWAP | volatility_squeeze_breakout | breakout | 0.00000000 | -10.00000000 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
| 22 | BASED-USDT-SWAP | volatility_squeeze_breakout | breakout | 0.00000000 | -10.00000000 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
| 23 | LAB-USDT-SWAP | volatility_squeeze_breakout | breakout | 0.00000000 | -10.00000000 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
| 24 | LAB-USDT-SWAP | trend_pullback | trend | -1.03362550 | -10.06004392 | -6.55015013 | 0.986731 | 14.67190742 | 2/4 | false |
| 25 | BASED-USDT-SWAP | volatility_squeeze_breakout | breakout | -1.00249483 | -10.66210952 | 0.00000000 | 0.000000 | 0.00000000 | 0/4 | false |
