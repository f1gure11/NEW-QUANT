# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 498 |
| Passed window rows | 191 |
| Unique aggregate candidates | 101 |
| Passed aggregate candidates | 1 |
| Median selected test return | -0.547609% |
| Mean selected test return | -0.163120% |
| Best aggregate return | 55.365611% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | ZEC-USDT-SWAP | time_series_momentum | all | 13 | 53.8462 | 55.36561081 | 0.54083553 | -9.31088274 | false |
| 2 | MU-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 47.47027167 | 4.71040146 | -3.14835418 | false |
| 3 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 44.43915709 | 6.50985693 | -8.94248327 | false |
| 4 | MU-USDT-SWAP | time_series_momentum | all | 8 | 25.0000 | 50.21370557 | 4.84438245 | -9.31226561 | false |
| 5 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 6 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 8 | 50.0000 | 36.90922079 | 2.71925505 | -11.84384364 | false |
| 7 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 8 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 9 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 66.6667 | 26.15174192 | 3.42131321 | -5.00137280 | false |
| 10 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 11 | 36.3636 | 29.50563161 | -1.87831955 | -9.89238844 | false |
| 11 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 12 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 37.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 13 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | 19.43350646 | 10.12833976 | -3.46947520 | false |
| 14 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 2 | 100.0000 | 10.35713004 | 5.07904382 | 2.65160796 | false |
| 15 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 28.5714 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 16 | BTC-USDT-SWAP | time_series_momentum | all | 21 | 52.3810 | 12.66174286 | 0.64104998 | -10.21308463 | false |
| 17 | ETH-USDT-SWAP | multi_horizon_momentum | all | 11 | 27.2727 | 16.81128663 | -0.05916504 | -8.12349912 | false |
| 18 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 7 | 57.1429 | 13.75088612 | 3.47092067 | -9.87614599 | false |
| 19 | SOL-USDT-SWAP | time_series_momentum | all | 16 | 50.0000 | 11.30271418 | -0.15324850 | -12.44778515 | false |
| 20 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3 | 66.6667 | 9.31282484 | 2.87452886 | -7.42528133 | false |
| 21 | XAU-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 6.64319269 | 1.69050718 | -4.00651807 | false |
| 22 | BTC-USDT-SWAP | multi_horizon_momentum | all | 10 | 50.0000 | 9.10696302 | 2.12696409 | -12.27848844 | false |
| 23 | XAU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 8.23257199 | 0.93913025 | -5.00926885 | false |
| 24 | MU-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 3.03705935 | 3.03705935 | 3.03705935 | false |
| 25 | MU-USDT-SWAP | multi_horizon_momentum | all | 5 | 40.0000 | 11.08879324 | 2.72953816 | -9.55891113 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 16.25657039 | 0.64104998 | 1.178569 | 7.21877845 | true |
| 1 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 14.23251186 | 7.00337149 | 5.186556 | 2.60072651 | true |
| 1 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 13.36482270 | 3.56689880 | 999.000000 | 5.43496181 | true |
| 2 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 25.48169165 | -6.35151163 | 0.490404 | 12.08004565 | false |
| 2 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 22.05729752 | -6.65265648 | 0.466286 | 10.98192897 | false |
| 2 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 18.69136270 | 2.74007409 | 1.983408 | 5.60284831 | true |
| 3 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 21.72096072 | -0.57746480 | 1.031825 | 4.48416733 | false |
| 3 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 20.97215739 | -0.94326334 | 0.908381 | 5.01056635 | false |
| 3 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 16.04986133 | -0.81806805 | 0.942436 | 4.92221249 | false |
| 4 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 10.76287611 | 3.87938656 | 1.784273 | 7.08564299 | true |
| 4 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 6.86741839 | 8.14519509 | 6.041936 | 4.90627247 | true |
| 4 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.83781256 | 6.86581095 | 5.315889 | 4.52823119 | true |
| 5 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 6.67614739 | 2.22571446 | 1.586616 | 4.92161595 | true |
| 5 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 7.05518709 | 4.69919208 | 2.691655 | 5.04108447 | true |
| 5 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 4.34612739 | -4.37343475 | 0.622327 | 11.44798302 | false |
| 6 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 18.90384115 | 4.83498702 | 2.608837 | 6.96172109 | true |
| 6 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 13.62662197 | 7.23261069 | 5.251058 | 5.59771594 | true |
| 6 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.70096838 | -5.56947685 | 0.609268 | 16.66495897 | false |
| 7 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 22.86936585 | 3.18528217 | 1.879009 | 5.56955685 | true |
| 7 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 18.78508403 | 1.30062627 | 1.434041 | 6.02819007 | true |
| 7 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 17.68635410 | -0.93196021 | 0.956371 | 10.13845910 | false |
| 8 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 22.48505201 | -3.14306002 | 0.591973 | 8.86071603 | false |
| 8 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 17.16832165 | -4.12777384 | 0.568400 | 10.67763227 | false |
| 8 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 16.56283667 | -12.42877730 | 0.000000 | 13.96722098 | false |
| 9 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 15.78810459 | -2.21247564 | 0.005707 | 8.39976490 | false |
