# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 702 |
| Passed window rows | 232 |
| Unique aggregate candidates | 133 |
| Passed aggregate candidates | 4 |
| Median selected test return | -0.539719% |
| Mean selected test return | -0.151725% |
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
| 8 | MU-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | 43.13687193 | 5.69425294 | 2.75925012 | false |
| 9 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 10 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 11 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 12 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 13 | CL-USDT-SWAP | time_series_momentum | all | 6 | 66.6667 | 23.31124359 | 4.38997698 | -3.23069206 | false |
| 14 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 16 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 17 | SOL-USDT-SWAP | multi_horizon_momentum | all | 5 | 40.0000 | 25.99600586 | 1.59342730 | -7.29374500 | false |
| 18 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 19 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 20 | HYPE-USDT-SWAP | time_series_momentum | all | 11 | 63.6364 | 16.47178729 | 2.21939877 | -20.63125024 | false |
| 21 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 22 | BTC-USDT-SWAP | time_series_momentum | all | 19 | 36.8421 | 13.76750787 | 1.92222312 | -9.26809759 | false |
| 23 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 24 | SOL-USDT-SWAP | time_series_momentum | all | 7 | 71.4286 | 5.89066886 | 2.78920964 | -10.98990847 | false |
| 25 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 4.56233694 | 4.56233694 | 4.56233694 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 22.66609583 | -12.96129768 | 0.106846 | 14.62818931 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 21.91708661 | -18.52713927 | 0.000000 | 20.13315127 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 12.59022896 | -8.69638227 | 0.225933 | 11.62115674 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.63244072 | 9.38377221 | 7.186831 | 4.32177264 | true |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.26121862 | 3.72987293 | 1.665980 | 8.80350574 | true |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 14.68542264 | 2.90232723 | 1.401871 | 10.07475052 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10.69978827 | 0.40686718 | 1.118861 | 9.10529218 | true |
| 4 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.67360573 | 3.14098796 | 1.575792 | 7.83909767 | true |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 11.29030604 | -10.11991322 | 0.355479 | 18.38154772 | false |
| 5 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 11.30084307 | -14.87986984 | 0.337062 | 21.38086473 | false |
| 5 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 7.91111947 | 10.29713446 | 999.000000 | 3.63635570 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 28.45843901 | -1.54721315 | 0.712120 | 6.79088776 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 29.80394351 | -1.54721315 | 0.712120 | 6.79088776 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 20.76185590 | -1.54721315 | 0.712120 | 6.79088776 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 29.67348632 | -11.12159345 | 0.118428 | 13.14770658 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 27.36438125 | -10.36380546 | 0.149256 | 12.54523163 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 18.76762135 | -4.07066069 | 0.522995 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.30746396 | -13.65947509 | 0.000000 | 13.94179145 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 7.63369055 | -10.60810276 | 0.000000 | 11.51655835 | false |
| 8 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 2.86401926 | 3.54842070 | 2.318564 | 8.07802062 | true |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.17472136 | -7.16416804 | 0.332666 | 10.36268119 | false |
| 9 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.99482609 | -15.28294470 | 0.211285 | 16.21809065 | false |
| 9 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 4.72688889 | -8.09989662 | 0.258077 | 10.93952673 | false |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.90206984 | -8.47836390 | 0.167992 | 9.27702991 | false |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 0.47618751 | -4.06836699 | 0.000000 | 6.16234273 | false |
