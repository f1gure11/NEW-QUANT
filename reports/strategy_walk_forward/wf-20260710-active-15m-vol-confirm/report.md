# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 1337 |
| Passed window rows | 325 |
| Unique aggregate candidates | 159 |
| Passed aggregate candidates | 0 |
| Median selected test return | -1.065792% |
| Mean selected test return | -0.918919% |
| Best aggregate return | 97.697031% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | time_series_momentum | all | 18 | 22.2222 | 97.69703102 | 0.10323536 | -7.50330423 | false |
| 2 | ZEC-USDT-SWAP | time_series_momentum | all | 19 | 52.6316 | 32.82067086 | 0.78971831 | -5.35278524 | false |
| 3 | MU-USDT-SWAP | multi_horizon_momentum | all | 13 | 7.6923 | 33.29229457 | 1.57752126 | -1.93488613 | false |
| 4 | ZEC-USDT-SWAP | time_series_momentum | all | 10 | 50.0000 | 18.94470054 | -0.01096076 | -9.36140349 | false |
| 5 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 6 | 16.6667 | 23.92810085 | 3.09456560 | -2.32220253 | false |
| 6 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 1 | 100.0000 | 5.41158390 | 5.41158390 | 5.41158390 | false |
| 7 | LAB-USDT-SWAP | time_series_momentum | all | 10 | 50.0000 | 12.39154425 | 0.33452733 | -3.71354425 | false |
| 8 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 22 | 40.9091 | 10.80594315 | -0.16776877 | -5.10557417 | false |
| 9 | LAB-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 3.92588219 | 1.95310658 | 0.59379726 | false |
| 10 | LAB-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 0.66209581 | 0.66209581 | 0.66209581 | false |
| 11 | ZEC-USDT-SWAP | time_series_momentum | all | 10 | 20.0000 | 11.95834550 | -0.08546038 | -2.53882396 | false |
| 12 | LAB-USDT-SWAP | time_series_momentum | all | 8 | 50.0000 | 4.55295579 | -1.04410163 | -3.20655052 | false |
| 13 | SPCX-USDT-SWAP | time_series_momentum | all | 18 | 22.2222 | 6.05025508 | -0.55594012 | -3.69619333 | false |
| 14 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 14 | 28.5714 | 5.23579457 | -1.00146556 | -5.84601820 | false |
| 15 | MU-USDT-SWAP | multi_horizon_momentum | all | 13 | 7.6923 | 7.90743364 | 0.01119600 | -5.74020205 | false |
| 16 | MU-USDT-SWAP | time_series_momentum | all | 17 | 41.1765 | 2.32876261 | 0.29819637 | -8.22508734 | false |
| 17 | SOXL-USDT-SWAP | time_series_momentum | all | 10 | 30.0000 | 5.84529642 | 0.83719349 | -5.05901752 | false |
| 18 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 5.92239519 | -1.61714040 | -3.39148398 | false |
| 19 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 14 | 28.5714 | 3.27993196 | -0.41311256 | -4.95507048 | false |
| 20 | ETH-USDT-SWAP | multi_horizon_momentum | all | 12 | 58.3333 | -1.57785415 | 0.33332446 | -5.08816318 | false |
| 21 | SOL-USDT-SWAP | multi_horizon_momentum | all | 19 | 31.5789 | 1.87252520 | -0.32525403 | -5.66563595 | false |
| 22 | LAB-USDT-SWAP | multi_horizon_momentum | all | 8 | 25.0000 | 4.41407015 | -1.60789028 | -5.51972016 | false |
| 23 | MU-USDT-SWAP | multi_horizon_momentum | all | 12 | 33.3333 | 0.34469849 | -0.41200695 | -4.31398176 | false |
| 24 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 8 | 37.5000 | 1.65362026 | 0.34644338 | -4.75615112 | false |
| 25 | SOL-USDT-SWAP | time_series_momentum | all | 4 | 50.0000 | -1.08043610 | -0.39050769 | -2.66761756 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.11586285 | -2.97620324 | 0.000000 | 4.21314387 | false |
| 2 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.95952917 | 2.90834011 | 999.000000 | 0.72235382 | false |
| 2 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.93290096 | 2.90834011 | 999.000000 | 0.72235382 | false |
| 3 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 3.38449822 | -2.18784643 | 0.000000 | 2.23541996 | false |
| 3 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 1.87952106 | -3.35380102 | 0.000000 | 3.48204070 | false |
| 3 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.81847973 | -1.96596462 | 0.000000 | 2.11075829 | false |
| 4 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.76368234 | -1.83703127 | 0.000000 | 2.38701890 | false |
| 5 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.29126532 | -6.72505596 | 0.000000 | 7.79737531 | false |
| 5 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.02135200 | -6.63558437 | 0.000000 | 7.70893232 | false |
| 5 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.29148497 | -0.97444315 | 0.718106 | 3.70580712 | false |
| 6 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.46811743 | 1.04570122 | 999.000000 | 0.77213070 | false |
| 6 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.34571868 | 1.04570122 | 999.000000 | 0.77213070 | false |
| 6 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 0.29486958 | 1.04570122 | 999.000000 | 0.77213070 | false |
| 7 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.34958787 | 0.06591955 | 999.000000 | 1.61495197 | false |
| 7 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 0.17874559 | 0.06591955 | 999.000000 | 1.61495197 | false |
| 7 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.14184371 | 0.06591955 | 999.000000 | 1.61495197 | false |
| 8 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.41954197 | -1.26267443 | 0.594702 | 2.77822450 | false |
| 8 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.56663639 | -1.64086041 | 0.496088 | 3.15060559 | false |
| 9 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.57345597 | -3.21262475 | 0.000000 | 3.69259202 | false |
| 14 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.96046652 | -0.62465554 | 0.765409 | 1.91906551 | false |
| 15 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.23799595 | 0.54170886 | 1.657926 | 1.45778608 | true |
| 16 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 2.63055435 | 0.86692627 | 2.121661 | 1.23007623 | true |
| 16 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 0.95982253 | -3.97405490 | 0.000000 | 4.03061525 | false |
| 16 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.37540975 | 0.90256339 | 2.464041 | 1.11359815 | true |
| 17 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 4.74234233 | 0.49123151 | 3.417788 | 0.85659574 | true |
