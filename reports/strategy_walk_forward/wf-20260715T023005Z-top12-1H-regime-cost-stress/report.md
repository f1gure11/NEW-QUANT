# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 662 |
| Passed window rows | 226 |
| Unique aggregate candidates | 123 |
| Passed aggregate candidates | 5 |
| Median selected test return | -0.425908% |
| Mean selected test return | 0.108148% |
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
| 9 | SOL-USDT-SWAP | time_series_momentum | all | 10 | 50.0000 | 33.84528316 | 2.26711394 | -10.70877686 | false |
| 10 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 11 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 12 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 13 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 14 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 16 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 17 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 18 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 19 | SOL-USDT-SWAP | time_series_momentum | all | 17 | 58.8235 | 15.27798663 | 0.85629642 | -12.92314443 | false |
| 20 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 21 | XAU-USDT-SWAP | time_series_momentum | all | 3 | 100.0000 | 6.05854353 | 1.35933737 | 0.97235058 | true |
| 22 | HYPE-USDT-SWAP | time_series_momentum | all | 11 | 63.6364 | 10.47970021 | 2.78473295 | -20.30324797 | false |
| 23 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 24 | HYPE-USDT-SWAP | time_series_momentum | all | 8 | 12.5000 | 18.38642763 | 0.11630865 | -5.21757911 | false |
| 25 | HYPE-USDT-SWAP | multi_horizon_momentum | all | 1 | 100.0000 | 5.53274626 | 5.53274626 | 5.53274626 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 16.54677867 | -12.84234551 | 0.110150 | 13.52407186 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 14.27531160 | -13.78920637 | 0.000000 | 18.28653652 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 10.76626236 | -8.11513989 | 0.253429 | 11.62115674 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.55765733 | 10.36161256 | 15.807029 | 4.84067580 | true |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 10.95239349 | 7.24445117 | 2.181591 | 8.80350574 | true |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 25.85897212 | 0.17471448 | 1.080447 | 10.07475052 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 13.29320586 | 4.93718159 | 2.003501 | 9.10529218 | true |
| 4 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 4.16977025 | 5.69164902 | 1.860070 | 5.52701994 | true |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.70094382 | -11.34890679 | 0.285260 | 17.74710998 | false |
| 5 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 8.94238087 | -13.36798488 | 0.339911 | 19.59718258 | false |
| 5 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.21724693 | 7.83411847 | 999.000000 | 3.22487065 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 26.74164540 | -1.83613487 | 0.558332 | 6.44617071 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 28.16735172 | -1.83613487 | 0.558332 | 6.44617071 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 21.14532088 | -1.83613487 | 0.558332 | 6.44617071 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 24.89104045 | -11.82725327 | 0.010394 | 12.41819985 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 25.28046712 | -12.57685136 | 0.000000 | 13.16277402 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 17.41878978 | -4.94824374 | 0.337820 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 6.44040923 | -9.06508706 | 0.007903 | 12.08514911 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 7.13207646 | -11.25678074 | 0.000000 | 14.04294624 | false |
| 8 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 1.66531215 | 6.12441264 | 48.167152 | 8.07802062 | true |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.58875678 | -6.38260875 | 0.395639 | 10.43390646 | false |
| 9 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3.22957590 | -14.54625008 | 0.239095 | 16.21809065 | false |
| 9 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 5.06542139 | -7.32618089 | 0.315038 | 11.33664546 | false |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 4.49220396 | -9.55007270 | 0.149995 | 9.67117919 | false |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 2.85120706 | -6.09646742 | 0.000000 | 7.48690433 | false |
