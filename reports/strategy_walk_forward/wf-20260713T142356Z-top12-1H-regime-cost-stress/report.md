# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 764 |
| Passed window rows | 240 |
| Unique aggregate candidates | 137 |
| Passed aggregate candidates | 5 |
| Median selected test return | -0.825864% |
| Mean selected test return | -0.230854% |
| Best aggregate return | 91.553953% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | BEAT-USDT-SWAP | multi_horizon_momentum | all | 9 | 33.3333 | 91.55395320 | -3.26454750 | -18.12198375 | false |
| 2 | BEAT-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 56.20104186 | 3.11560800 | -0.31109703 | true |
| 3 | ZEC-USDT-SWAP | time_series_momentum | all | 13 | 46.1538 | 55.36561081 | 0.54083553 | -9.31088274 | false |
| 4 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 44.43915709 | 6.50985693 | -8.94248327 | false |
| 5 | MU-USDT-SWAP | time_series_momentum | all | 9 | 55.5556 | 47.47027167 | 4.71040146 | -3.14835418 | false |
| 6 | BEAT-USDT-SWAP | time_series_momentum | all | 3 | 100.0000 | 39.97998157 | 8.32300625 | 4.28462095 | true |
| 7 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 12 | 41.6667 | 46.82190089 | 1.52145838 | -9.89238844 | false |
| 8 | SOL-USDT-SWAP | multi_horizon_momentum | all | 6 | 66.6667 | 36.48911723 | 4.45757448 | -8.50065715 | false |
| 9 | MU-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | 43.13687193 | 5.69425294 | 2.75925012 | false |
| 10 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 11 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 12 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 13 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 14 | SOL-USDT-SWAP | time_series_momentum | all | 16 | 50.0000 | 28.94017599 | 0.36278985 | -10.38639583 | false |
| 15 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 16 | BTC-USDT-SWAP | time_series_momentum | all | 21 | 47.6190 | 24.52752113 | 1.31618074 | -7.57795713 | false |
| 17 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 18 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 19 | ETH-USDT-SWAP | multi_horizon_momentum | all | 11 | 18.1818 | 28.22135297 | -0.04356867 | -6.72185573 | false |
| 20 | SOL-USDT-SWAP | time_series_momentum | all | 9 | 22.2222 | 27.95362904 | -1.10374595 | -9.91057437 | false |
| 21 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 22 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 23 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 13 | 23.0769 | 26.45021404 | 0.52883248 | -10.22309517 | false |
| 24 | HYPE-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 13.95866312 | 3.56759928 | 3.32513954 | true |
| 25 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 15 | 20.0000 | 24.77246831 | 0.61777325 | -10.58401566 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 18.94646270 | -11.05865271 | 0.140034 | 15.06313482 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 17.63059680 | -16.79241630 | 0.000000 | 20.68825069 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 10.66294124 | -6.78754805 | 0.337490 | 11.40490729 | false |
| 2 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.29337822 | 3.30062759 | 3.423237 | 8.77497692 | true |
| 2 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 0.09220912 | 12.18547351 | 10.486428 | 4.32643243 | true |
| 2 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 0.03532750 | -5.72669162 | 0.313484 | 12.70796161 | false |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 10.10957991 | 1.70229084 | 1.266696 | 7.50252477 | true |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 7.63001638 | 9.97902450 | 999.000000 | 4.77756781 | false |
| 3 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3.03670553 | 8.66972535 | 2.731608 | 7.13890480 | true |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 16.59056250 | -1.51640843 | 0.906913 | 10.07475052 | false |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.61160950 | -3.20484308 | 0.634630 | 9.10529218 | false |
| 4 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.19615706 | -0.58511509 | 0.991532 | 7.83909767 | false |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.72607596 | -11.11616889 | 0.322308 | 18.53589423 | false |
| 5 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.77424897 | 10.42515056 | 999.000000 | 4.01068251 | false |
| 5 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 2.86180929 | -15.75482678 | 0.318462 | 22.31643872 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 22.55001572 | 1.99139108 | 999.000000 | 7.81838138 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 20.71860389 | 1.99139108 | 999.000000 | 7.81838138 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 11.52644623 | 7.56518616 | 999.000000 | 4.05532546 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 21.67146523 | -6.72185573 | 0.352883 | 12.42908718 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 22.47051885 | -7.50608965 | 0.305969 | 13.03236225 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 17.23944656 | -0.20613315 | 1.160129 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 13.26885080 | -14.42112521 | 0.000000 | 14.73084616 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 12.60747582 | -11.40921994 | 0.065208 | 12.56571917 | false |
| 8 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 6.94051085 | -2.53508228 | 0.635574 | 6.68720746 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 11.38080763 | 0.51449844 | 1.251125 | 5.33987701 | true |
