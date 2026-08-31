# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 395 |
| Passed window rows | 140 |
| Unique aggregate candidates | 97 |
| Passed aggregate candidates | 2 |
| Median selected test return | -1.505574% |
| Mean selected test return | -1.015714% |
| Best aggregate return | 122.731164% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | ZEC-USDT-SWAP | time_series_momentum | all | 16 | 50.0000 | 122.73116364 | 4.69058700 | -9.23348073 | false |
| 2 | SPCX-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 69.83173482 | 69.83173482 | 69.83173482 | false |
| 3 | ZEC-USDT-SWAP | time_series_momentum | all | 12 | 66.6667 | 48.25222936 | 2.24494431 | -9.56820572 | false |
| 4 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 7 | 71.4286 | 38.01268603 | 1.86086912 | -5.29111756 | false |
| 5 | SOL-USDT-SWAP | time_series_momentum | all | 5 | 40.0000 | 30.83201342 | 5.73135156 | -10.20941115 | false |
| 6 | MU-USDT-SWAP | time_series_momentum | all | 7 | 71.4286 | 25.27182166 | 3.36635468 | -4.84524809 | false |
| 7 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 5 | 60.0000 | 24.91422203 | 3.70978100 | -1.41892125 | true |
| 8 | BASED-USDT-SWAP | time_series_momentum | all | 6 | 66.6667 | 19.37939882 | 3.64979304 | -4.54425544 | false |
| 9 | SPCX-USDT-SWAP | time_series_momentum | all | 4 | 75.0000 | 17.44452861 | 3.45793031 | -2.97640357 | true |
| 10 | MU-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 24.50229835 | 1.43632154 | -4.98471718 | false |
| 11 | SPCX-USDT-SWAP | time_series_momentum | all | 3 | 33.3333 | 18.50171718 | 2.96304967 | -0.10737415 | false |
| 12 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 11.68743047 | 0.85788501 | -2.00178681 | false |
| 13 | BASED-USDT-SWAP | multi_horizon_momentum | all | 7 | 71.4286 | 8.74243798 | 2.59656904 | -7.46369065 | false |
| 14 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 50.0000 | 12.42145897 | -0.75093291 | -10.57757326 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 5 | 60.0000 | 8.71323901 | 5.35156680 | -6.45228516 | false |
| 16 | MU-USDT-SWAP | time_series_momentum | all | 10 | 50.0000 | 10.02606690 | 1.18722523 | -9.20839505 | false |
| 17 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1 | 100.0000 | 1.04912197 | 1.04912197 | 1.04912197 | false |
| 18 | BASED-USDT-SWAP | time_series_momentum | all | 3 | 66.6667 | 6.88899893 | 4.29258940 | -4.20048141 | false |
| 19 | BASED-USDT-SWAP | time_series_momentum | all | 6 | 50.0000 | 8.73456341 | 0.91314056 | -10.03507479 | false |
| 20 | BASED-USDT-SWAP | multi_horizon_momentum | all | 3 | 66.6667 | 7.59617862 | 7.77147947 | -8.38132404 | false |
| 21 | BASED-USDT-SWAP | multi_horizon_momentum | all | 7 | 57.1429 | 6.07289218 | 3.32566522 | -9.12665903 | false |
| 22 | BASED-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 0.15916925 | 0.15916925 | 0.15916925 | false |
| 23 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | 2.38230716 | 1.18925998 | 0.17160641 | false |
| 24 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 5 | 60.0000 | 0.54154741 | 2.36801224 | -12.82845005 | false |
| 25 | SOL-USDT-SWAP | time_series_momentum | all | 2 | 50.0000 | 2.82023298 | 1.56730554 | -4.25457178 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 4 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 4.96649577 | -3.45856106 | 0.721523 | 7.67163591 | false |
| 4 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 1.84616776 | -2.75739850 | 0.873474 | 10.16944545 | false |
| 4 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 3.08497319 | 5.52182709 | 3.146371 | 4.61638456 | true |
| 5 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 8.08344609 | 3.83222869 | 1.911083 | 5.99945316 | true |
| 5 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 8.28347604 | -1.14273016 | 0.848178 | 6.67427955 | false |
| 5 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.89337537 | -3.63205642 | 0.602616 | 8.61211246 | false |
| 6 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 11.57357635 | -8.18786201 | 0.213065 | 11.61529858 | false |
| 6 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.61306196 | -12.52268808 | 0.176727 | 13.59345686 | false |
| 6 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.99821323 | -12.61700563 | 0.096989 | 13.78169720 | false |
| 7 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 2.31979253 | -1.20508734 | 0.967879 | 6.84802430 | false |
| 9 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 2.93918823 | -6.91349435 | 0.000000 | 8.46031843 | false |
| 15 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.18085301 | -2.07718300 | 0.631753 | 5.44205443 | false |
| 17 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 2.87148328 | -4.71215889 | 0.001301 | 6.84326256 | false |
| 17 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 0.88826217 | -5.88029960 | 0.267746 | 7.57608379 | false |
| 17 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.61284786 | -6.45736791 | 0.115797 | 8.00356767 | false |
| 20 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 16.23640543 | -7.36588145 | 0.000000 | 7.69477666 | false |
| 20 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 14.28124385 | -7.05881074 | 0.098195 | 7.38892800 | false |
| 20 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 10.34556655 | -0.87886118 | 0.982984 | 4.94802287 | false |
| 21 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 8.90648842 | 2.65073925 | 2.994439 | 2.61465773 | true |
| 21 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 6.05408485 | 1.04912197 | 1.688652 | 3.34527188 | true |
| 21 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 7.71845850 | 1.81970858 | 2.125087 | 3.40219227 | true |
| 22 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 20.94265889 | 0.38593506 | 1.256498 | 5.15204917 | true |
| 22 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 19.40905500 | -1.88565954 | 0.633816 | 5.05686683 | false |
| 22 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 14.19902306 | -2.70418721 | 0.653468 | 5.75612415 | false |
| 23 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 17.64347633 | -5.50612476 | 0.427603 | 7.92648679 | false |
