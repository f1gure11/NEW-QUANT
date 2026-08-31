# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 981 |
| Passed window rows | 228 |
| Unique aggregate candidates | 150 |
| Passed aggregate candidates | 2 |
| Median selected test return | -1.076482% |
| Mean selected test return | -0.502402% |
| Best aggregate return | 127.872455% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | time_series_momentum | all | 23 | 47.8261 | 127.87245476 | 0.53057268 | -7.95851508 | false |
| 2 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 8 | 25.0000 | 94.64773611 | 0.37047465 | -6.27756572 | false |
| 3 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 12 | 25.0000 | 73.68522822 | 0.15515658 | -8.18713712 | false |
| 4 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 13 | 61.5385 | 49.97713543 | 1.52305641 | -2.52810579 | true |
| 5 | ZEC-USDT-SWAP | time_series_momentum | all | 10 | 90.0000 | 38.94536012 | 1.92363386 | -6.63288412 | false |
| 6 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 11 | 27.2727 | 27.25527538 | 1.12930687 | -4.41350085 | false |
| 7 | BASED-USDT-SWAP | time_series_momentum | all | 8 | 75.0000 | 14.84228378 | 1.30498356 | -3.05026484 | false |
| 8 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 11 | 54.5455 | 16.02375128 | 0.93029808 | -2.68347471 | false |
| 9 | SOXL-USDT-SWAP | time_series_momentum | all | 16 | 25.0000 | 17.77767284 | 0.95956994 | -7.44047866 | false |
| 10 | MU-USDT-SWAP | multi_horizon_momentum | all | 19 | 21.0526 | 17.43740377 | 0.58253118 | -5.38667327 | false |
| 11 | LAB-USDT-SWAP | time_series_momentum | all | 6 | 50.0000 | 13.56314928 | 0.25964659 | -8.69140878 | false |
| 12 | SOXL-USDT-SWAP | time_series_momentum | all | 12 | 33.3333 | 16.24969754 | 0.97881065 | -4.32973222 | false |
| 13 | MU-USDT-SWAP | time_series_momentum | all | 15 | 26.6667 | 14.58201863 | -0.01089913 | -5.48976553 | false |
| 14 | MU-USDT-SWAP | time_series_momentum | all | 8 | 50.0000 | 12.01874982 | 1.77719617 | -6.81001733 | false |
| 15 | BASED-USDT-SWAP | multi_horizon_momentum | all | 8 | 50.0000 | 9.78673904 | 1.90176344 | -6.13709407 | false |
| 16 | ZEC-USDT-SWAP | time_series_momentum | all | 4 | 50.0000 | 8.96611851 | -1.38128144 | -3.78607437 | false |
| 17 | ZEC-USDT-SWAP | time_series_momentum | all | 4 | 75.0000 | 4.25478894 | 0.73454604 | -1.31979065 | true |
| 18 | SOXL-USDT-SWAP | time_series_momentum | all | 5 | 60.0000 | 3.28754158 | 1.07401860 | -6.57579455 | false |
| 19 | BASED-USDT-SWAP | time_series_momentum | all | 20 | 25.0000 | 6.87750850 | -0.95080597 | -5.22785036 | false |
| 20 | MU-USDT-SWAP | multi_horizon_momentum | all | 13 | 7.6923 | 8.76760298 | 2.05607973 | -4.94593128 | false |
| 21 | SOL-USDT-SWAP | time_series_momentum | all | 6 | 0.0000 | 8.87660969 | 1.51619858 | -3.44237283 | false |
| 22 | LAB-USDT-SWAP | time_series_momentum | all | 2 | 50.0000 | 0.57388853 | 0.29015125 | -0.56166115 | false |
| 23 | LAB-USDT-SWAP | multi_horizon_momentum | all | 7 | 28.5714 | 4.16443567 | -1.90319295 | -4.96063853 | false |
| 24 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 12 | 33.3333 | 3.32817109 | 0.89647247 | -6.28783604 | false |
| 25 | ZEC-USDT-SWAP | time_series_momentum | all | 14 | 57.1429 | -1.50166636 | 0.77652606 | -5.66146677 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.77444753 | 0.18479402 | 1.664439 | 1.74205447 | true |
| 1 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 0.35651987 | -0.24230489 | 1.281226 | 2.16094289 | false |
| 1 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.27252337 | 0.54485901 | 2.592381 | 1.38891580 | true |
| 2 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 3.12212192 | -2.45031924 | 0.000000 | 2.57392332 | false |
| 2 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.06785323 | -1.01295040 | 0.395320 | 1.49091205 | false |
| 2 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.01896774 | -4.29227352 | 0.000000 | 4.41354368 | false |
| 3 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.08227019 | -7.35931525 | 0.000000 | 7.79737531 | false |
| 4 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.34215549 | 1.60215171 | 999.000000 | 1.03895511 | false |
| 5 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.63011561 | -2.19954692 | 0.072334 | 3.87810039 | false |
| 5 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.40773843 | -2.57413765 | 0.042293 | 4.24626200 | false |
| 5 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.43212388 | -0.82297432 | 0.000000 | 3.38478778 | false |
| 6 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.15406420 | -1.80712460 | 0.379053 | 3.65816459 | false |
| 10 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.94747886 | -0.33234215 | 0.938220 | 2.46235986 | false |
| 11 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.74071255 | -0.00931367 | 1.151477 | 1.45778608 | false |
| 12 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.56791655 | -2.93975360 | 0.017449 | 3.71827049 | false |
| 13 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 3.47588619 | -1.52411356 | 0.407646 | 2.96280538 | false |
| 13 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 1.75644600 | 0.54199408 | 4.574406 | 1.27687265 | true |
| 13 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.62147342 | 0.22967082 | 3.052066 | 1.31320277 | true |
| 14 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.72981804 | -0.36067835 | 0.981777 | 2.06740740 | false |
| 14 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 2.39672106 | -3.10984416 | 0.127197 | 3.07377308 | false |
| 14 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 0.71888276 | -3.77559600 | 0.264906 | 3.68464198 | false |
| 15 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.61590917 | -2.29671765 | 0.000000 | 2.82665346 | false |
| 15 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.36123393 | -5.06740383 | 0.000000 | 5.38581734 | false |
| 15 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 0.02545787 | -4.52485491 | 0.045089 | 4.84517223 | false |
| 23 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.22836167 | -5.19376616 | 0.000120 | 5.48233027 | false |
