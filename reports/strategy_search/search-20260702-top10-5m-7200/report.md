# Multi-Strategy Search

Read-only train/test search over independent strategy families.

## Summary

| Metric | Value |
| --- | ---: |
| Tested configs | 360 |
| Passed configs | 0 |
| Passed rate | 0.00% |
| Best test return | 101.195970% |
| Median test return | -10.569182% |
| Mean test return | -10.101321% |
| Median positive holdout-fold rate | 33.33% |

## Top 25

Ranked by train-only selection score. Test columns are holdout validation.

| Rank | Instrument | Strategy | Family | Train Ret % | Train Score | Test Ret % | Test PF | Test DD % | Folds +/N | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 98.75427547 | 74.61863405 | -16.70132941 | 0.830249 | 50.81820996 | 1/3 | false |
| 2 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 56.87793683 | 32.53769360 | 13.84196724 | 1.182251 | 33.80481896 | 2/3 | false |
| 3 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 63.03282037 | 31.61231044 | -14.59670912 | 0.888868 | 41.46287212 | 1/3 | false |
| 4 | LAB-USDT-SWAP | ema_cross | trend | 58.74200879 | 29.01468358 | 9.55526741 | 1.124549 | 39.28132643 | 2/3 | false |
| 5 | BASED-USDT-SWAP | bollinger_revert | mean_reversion | 33.89421664 | 19.40715284 | -13.69032290 | 0.903030 | 35.68069344 | 2/3 | false |
| 6 | BASED-USDT-SWAP | bollinger_revert | mean_reversion | 33.44411181 | 18.96991415 | -6.90777725 | 0.977643 | 28.54457295 | 2/3 | false |
| 7 | LAB-USDT-SWAP | ema_cross | trend | 49.37420601 | 17.82262369 | 21.35204597 | 1.238518 | 43.51471602 | 2/3 | false |
| 8 | LAB-USDT-SWAP | bollinger_revert | mean_reversion | 49.29820855 | 15.48290518 | 2.64820172 | 1.063808 | 41.42022579 | 2/3 | false |
| 9 | SNDK-USDT-SWAP | rsi_revert | mean_reversion | 12.19836939 | 8.28337646 | -6.82365307 | 0.703135 | 14.51923005 | 2/3 | false |
| 10 | LAB-USDT-SWAP | bollinger_revert | mean_reversion | 36.24831481 | 3.71528949 | -6.10999224 | 1.000036 | 40.35135347 | 2/3 | false |
| 11 | SNDK-USDT-SWAP | bollinger_revert | mean_reversion | 5.51258709 | -0.16107952 | -13.73300425 | 0.837767 | 20.11521519 | 1/3 | false |
| 12 | XAU-USDT-SWAP | donchian_breakout | breakout | 1.21392454 | -0.33002852 | 0.51528500 | 1.220022 | 5.48917144 | 1/3 | false |
| 13 | SNDK-USDT-SWAP | rsi_revert | mean_reversion | 3.46339264 | -1.31989760 | -1.07045789 | 1.091138 | 11.79365113 | 2/3 | false |
| 14 | SPCX-USDT-SWAP | rsi_revert | mean_reversion | 13.11107431 | -1.74312359 | -6.13291339 | 0.808005 | 14.04981573 | 1/3 | false |
| 15 | BASED-USDT-SWAP | rsi_revert | mean_reversion | 9.48724957 | -2.67426710 | -8.27766471 | 0.939914 | 30.00912841 | 2/3 | false |
| 16 | SPCX-USDT-SWAP | rsi_revert | mean_reversion | 10.06162298 | -4.10771223 | -9.82711592 | 0.780107 | 17.86887272 | 1/3 | false |
| 17 | SNDK-USDT-SWAP | bollinger_revert | mean_reversion | 4.46626386 | -4.30437091 | -15.02264045 | 0.689227 | 18.91991886 | 1/3 | false |
| 18 | BTC-USDT-SWAP | rsi_revert | mean_reversion | -1.98574023 | -4.42287552 | -8.70261054 | 0.491335 | 9.93392687 | 0/3 | false |
| 19 | SNDK-USDT-SWAP | donchian_breakout | breakout | 5.64025962 | -4.49513713 | -8.77619137 | 0.801538 | 30.22571074 | 1/3 | false |
| 20 | ETH-USDT-SWAP | rsi_revert | mean_reversion | -1.40509359 | -4.51758507 | -7.96929087 | 0.531422 | 11.00698330 | 1/3 | false |
| 21 | HYPE-USDT-SWAP | rsi_revert | mean_reversion | 3.15101092 | -4.93562302 | -0.72869217 | 1.053453 | 6.77858039 | 2/3 | false |
| 22 | LAB-USDT-SWAP | ema_cross | trend | 22.87438819 | -7.39454649 | 33.61709220 | 1.407894 | 43.94101621 | 2/3 | false |
| 23 | SPCX-USDT-SWAP | rsi_revert | mean_reversion | 7.73019678 | -7.85721195 | -13.75331289 | 0.679693 | 15.34555809 | 0/3 | false |
| 24 | SNDK-USDT-SWAP | bollinger_revert | mean_reversion | 2.86332290 | -7.88109141 | -16.12641690 | 0.689911 | 20.42737719 | 1/3 | false |
| 25 | BTC-USDT-SWAP | rsi_revert | mean_reversion | -5.47576739 | -8.38181762 | -15.62083230 | 0.493595 | 16.04630189 | 0/3 | false |
