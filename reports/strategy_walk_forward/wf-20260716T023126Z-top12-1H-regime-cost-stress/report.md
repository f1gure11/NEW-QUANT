# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 742 |
| Passed window rows | 256 |
| Unique aggregate candidates | 136 |
| Passed aggregate candidates | 4 |
| Median selected test return | -0.636533% |
| Mean selected test return | -0.066959% |
| Best aggregate return | 91.553953% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | BEAT-USDT-SWAP | multi_horizon_momentum | all | 9 | 33.3333 | 91.55395320 | -3.26454750 | -18.12198375 | false |
| 2 | ZEC-USDT-SWAP | time_series_momentum | all | 14 | 42.8571 | 85.72635720 | 2.22601370 | -9.16711738 | false |
| 3 | BEAT-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 56.20104186 | 3.11560800 | -0.31109703 | true |
| 4 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 45.95151282 | 6.65175714 | -8.84387091 | false |
| 5 | MU-USDT-SWAP | time_series_momentum | all | 9 | 55.5556 | 47.47027167 | 4.71040146 | -3.14835418 | false |
| 6 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 13 | 30.7692 | 51.60217116 | 4.84514963 | -8.59278468 | false |
| 7 | BEAT-USDT-SWAP | time_series_momentum | all | 3 | 100.0000 | 39.97998157 | 8.32300625 | 4.28462095 | true |
| 8 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 12 | 41.6667 | 48.95169048 | 1.66383925 | -9.80956964 | false |
| 9 | BTC-USDT-SWAP | time_series_momentum | all | 19 | 47.3684 | 44.60953971 | 3.16258218 | -9.00547243 | false |
| 10 | MU-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | 43.13687193 | 5.69425294 | 2.75925012 | false |
| 11 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 12 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 16 | 43.7500 | 34.40090705 | 3.20211306 | -14.74281124 | false |
| 13 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 37.41344815 | 2.85393564 | -11.70886755 | false |
| 14 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 24.58883161 | 3.28865422 | -10.30347226 | false |
| 16 | HYPE-USDT-SWAP | time_series_momentum | all | 8 | 75.0000 | 25.59338972 | 3.20160812 | -11.32322177 | false |
| 17 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 18 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 19 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 22.12265516 | 2.99421806 | -4.94895450 | false |
| 20 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 21 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 22 | ZEC-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 7.67304641 | 7.67304641 | 7.67304641 | false |
| 23 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 24 | HYPE-USDT-SWAP | time_series_momentum | all | 10 | 40.0000 | 12.89628256 | 2.32811470 | -11.86780423 | false |
| 25 | XAU-USDT-SWAP | multi_horizon_momentum | all | 9 | 33.3333 | 10.99370965 | 0.08556320 | -2.12687070 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 13.31794315 | -9.28725712 | 0.200105 | 12.83170843 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 13.65213504 | -12.85672923 | 0.037839 | 18.28653652 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 12.42805491 | -13.94590109 | 0.120071 | 14.70453029 | false |
| 2 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.05689705 | 1.94596981 | 999.000000 | 8.77437163 | false |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.50113848 | 5.00430340 | 1.790368 | 8.80350574 | true |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 22.50281365 | 0.01702833 | 1.074992 | 10.07475052 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 12.25343797 | 3.89048669 | 1.804469 | 9.05526144 | true |
| 4 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 2.56796816 | 2.88251950 | 1.377815 | 7.55227489 | true |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 9.22684684 | -7.95448180 | 0.469472 | 16.88769176 | false |
| 5 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10.10367926 | 7.50829365 | 12.747328 | 4.11838136 | true |
| 5 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 9.02334467 | -11.77751267 | 0.362922 | 16.78830883 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 27.89989633 | -1.47641537 | 0.544696 | 5.60872032 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 27.44672699 | -1.47641537 | 0.544696 | 5.60872032 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 20.46802955 | -1.47641537 | 0.544696 | 5.60872032 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 21.38511688 | -12.77421230 | 0.026032 | 14.46951192 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 20.80155228 | -12.40197076 | 0.000000 | 14.32463503 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 17.53972521 | -1.77353847 | 0.251609 | 10.35521700 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 4.61376206 | -10.48337505 | 0.000000 | 13.06847822 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 5.25313926 | -11.63618275 | 0.000000 | 14.04294624 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 5.23063621 | -6.00040705 | 0.441787 | 10.43390646 | false |
| 14 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.94242565 | 2.16603319 | 1.530323 | 5.30548793 | true |
| 15 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 12.25429883 | 9.72446315 | 2.566858 | 11.61711224 | true |
| 15 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10.77148874 | 13.12528463 | 4.744510 | 8.47113726 | true |
| 15 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 8.27238378 | 13.12528463 | 4.744510 | 8.47113726 | true |
| 16 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 31.90963694 | 9.88111911 | 999.000000 | 6.54831284 | false |
