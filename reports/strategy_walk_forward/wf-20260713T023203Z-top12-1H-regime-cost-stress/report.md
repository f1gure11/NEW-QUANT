# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 831 |
| Passed window rows | 268 |
| Unique aggregate candidates | 146 |
| Passed aggregate candidates | 4 |
| Median selected test return | -1.073414% |
| Mean selected test return | -0.447180% |
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
| 8 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 16 | 25.0000 | 44.89785079 | 2.84555362 | -7.33696470 | false |
| 9 | MU-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | 43.13687193 | 5.69425294 | 2.75925012 | false |
| 10 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 11 | SOL-USDT-SWAP | time_series_momentum | all | 16 | 75.0000 | 29.64647615 | 1.48569848 | -9.95097392 | false |
| 12 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 13 | BTC-USDT-SWAP | time_series_momentum | all | 20 | 45.0000 | 31.06451972 | 1.66206749 | -5.26161527 | false |
| 14 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 16 | SOL-USDT-SWAP | multi_horizon_momentum | all | 6 | 50.0000 | 30.36693427 | 3.50622593 | -9.02124093 | false |
| 17 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 18 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 19 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 20 | SOL-USDT-SWAP | time_series_momentum | all | 7 | 28.5714 | 27.03356960 | 2.28426398 | -4.31011621 | false |
| 21 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 22 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 23 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10 | 30.0000 | 25.87983434 | 1.46056413 | -6.80185374 | false |
| 24 | SOL-USDT-SWAP | multi_horizon_momentum | all | 7 | 28.5714 | 21.75492513 | 0.19689629 | -6.67508121 | false |
| 25 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 20.68860226 | -11.57401306 | 0.145221 | 13.63216865 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 19.45443410 | -18.00125732 | 0.000000 | 19.61484843 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 12.58769394 | -13.05398523 | 0.112664 | 14.89040016 | false |
| 2 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.78287755 | -1.49497766 | 0.420872 | 8.77497692 | false |
| 2 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 1.13623766 | 6.08926505 | 3.345216 | 3.89272588 | true |
| 2 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 2.13851580 | -7.62277750 | 0.040063 | 9.90532452 | false |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 5.24664259 | 7.80671527 | 3.103371 | 7.60406397 | true |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.18169503 | 11.29750606 | 999.000000 | 4.89932669 | false |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 18.58720390 | -6.01689164 | 0.470205 | 9.31558262 | false |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.05611522 | -1.50745463 | 0.784119 | 9.10529218 | false |
| 5 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.90777952 | 9.26284549 | 27.174400 | 3.95046979 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 13.01760323 | 4.57721812 | 999.000000 | 7.45411291 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10.27188248 | 4.57721812 | 999.000000 | 7.45411291 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 6.95606442 | 4.57721812 | 999.000000 | 7.45411291 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 22.52329478 | -6.80185374 | 0.351854 | 11.77474022 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 23.32792144 | -7.58531708 | 0.305554 | 12.38252307 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 17.93419800 | -0.91916148 | 1.020692 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 16.90765144 | -13.45213499 | 0.000000 | 13.38646711 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 16.23725838 | -10.45802458 | 0.091591 | 11.86626336 | false |
| 8 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 10.58874908 | -1.33533954 | 0.802086 | 5.87613576 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 7.55248235 | 4.70780017 | 2.198614 | 4.63244660 | true |
| 9 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 0.50626937 | 4.70780017 | 2.198614 | 4.63244660 | true |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.94462420 | -14.36528794 | 0.080261 | 15.11576542 | false |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 8.61406375 | -10.03559506 | 0.033688 | 10.86614373 | false |
| 15 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 6.06072642 | -5.33164277 | 0.085235 | 8.41850405 | false |
