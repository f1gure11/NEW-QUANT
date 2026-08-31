# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 665 |
| Passed window rows | 211 |
| Unique aggregate candidates | 125 |
| Passed aggregate candidates | 6 |
| Median selected test return | -0.874970% |
| Mean selected test return | -0.039931% |
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
| 8 | HYPE-USDT-SWAP | multi_horizon_momentum | all | 4 | 100.0000 | 28.23974385 | 5.16678059 | 2.16930883 | true |
| 9 | MU-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | 43.13687193 | 5.69425294 | 2.75925012 | false |
| 10 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 11 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 12 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 13 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 14 | SOL-USDT-SWAP | time_series_momentum | all | 15 | 40.0000 | 28.68304279 | 1.63638056 | -10.91488854 | false |
| 15 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 16 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 17 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 18 | SOL-USDT-SWAP | multi_horizon_momentum | all | 5 | 40.0000 | 24.98138086 | 0.58575397 | -11.55492467 | false |
| 19 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 20 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 21 | ETH-USDT-SWAP | multi_horizon_momentum | all | 11 | 9.0909 | 27.86421804 | -0.96583911 | -7.50476535 | false |
| 22 | SOL-USDT-SWAP | time_series_momentum | all | 7 | 28.5714 | 24.37145124 | 1.61144538 | -12.84921779 | false |
| 23 | SOL-USDT-SWAP | time_series_momentum | all | 10 | 60.0000 | 15.06660085 | 2.43789871 | -10.99198209 | false |
| 24 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 25 | HYPE-USDT-SWAP | time_series_momentum | all | 12 | 66.6667 | 12.62564012 | 3.57415660 | -17.05861191 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 18.62479996 | -10.59621666 | 0.134400 | 15.08147073 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 17.36334220 | -16.32602207 | 0.000000 | 20.53703448 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 11.57819888 | -6.06369918 | 0.399772 | 11.62115674 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.19238695 | 10.28730872 | 7.963916 | 4.32674526 | true |
| 2 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.27366524 | 2.23016161 | 3.306591 | 8.77497692 | true |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.95135636 | 1.96823865 | 1.313223 | 8.44195693 | true |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.83906902 | 9.83607522 | 999.000000 | 4.56535629 | false |
| 3 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.51459940 | 8.93414173 | 3.329005 | 5.72870754 | true |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 13.65848674 | 3.43697202 | 1.479357 | 10.07475052 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.53192318 | 0.97855548 | 1.223666 | 9.10529218 | true |
| 4 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 2.22506533 | -0.62059652 | 0.976787 | 10.24715086 | false |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 6.64017733 | -11.59520768 | 0.260667 | 18.40148929 | false |
| 5 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.00614225 | 8.91377163 | 999.000000 | 3.68483656 | false |
| 5 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 6.76331123 | -16.24174243 | 0.265053 | 22.17870795 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 25.91598024 | -1.16468430 | 0.636752 | 7.15442352 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 27.44353120 | -1.16468430 | 0.636752 | 7.15442352 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 17.65891325 | -1.16468430 | 0.636752 | 7.15442352 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 26.48834045 | -7.50476535 | 0.285301 | 12.70082344 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 25.68236439 | -8.28397994 | 0.242331 | 13.30222652 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 18.27291736 | -0.78238970 | 1.049660 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.96344318 | -12.06548943 | 0.000000 | 13.67443355 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 8.30764201 | -8.97876454 | 0.198828 | 11.48270230 | false |
| 8 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 3.00478325 | -3.25101782 | 0.577878 | 8.07802062 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.43141367 | -1.85308481 | 0.859732 | 9.44963711 | false |
| 9 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 1.03060266 | -1.85308481 | 0.859732 | 9.44963711 | false |
