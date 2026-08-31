# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 82 |
| Passed window rows | 12 |
| Unique aggregate candidates | 33 |
| Passed aggregate candidates | 0 |
| Median selected test return | -4.424448% |
| Mean selected test return | -5.009652% |
| Best aggregate return | -0.474091% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 5 | 60.0000 | -2.62486861 | 0.25131398 | -5.07361631 | false |
| 2 | SOXL-USDT-SWAP | time_series_momentum | all | 2 | 50.0000 | -0.47409051 | -0.04024861 | -6.31407909 | false |
| 3 | SOXL-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -0.78716663 | -0.78716663 | -0.78716663 | false |
| 4 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | -6.53405243 | -3.03301613 | -10.51641136 | false |
| 5 | XAU-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -2.30305426 | -2.30305426 | -2.30305426 | false |
| 6 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -1.67979377 | -1.67979377 | -1.67979377 | false |
| 7 | MU-USDT-SWAP | multi_horizon_momentum | all | 3 | 33.3333 | -8.48542159 | -1.03258904 | -8.18095321 | false |
| 8 | SOL-USDT-SWAP | multi_horizon_momentum | all | 4 | 25.0000 | -9.16067496 | -1.09943344 | -9.01936364 | false |
| 9 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -4.25787225 | -4.25787225 | -4.25787225 | false |
| 10 | SOL-USDT-SWAP | time_series_momentum | all | 5 | 40.0000 | -12.51259987 | -3.74465630 | -6.50220585 | false |
| 11 | MU-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -4.11336772 | -4.11336772 | -4.11336772 | false |
| 12 | MU-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -4.44371697 | -4.44371697 | -4.44371697 | false |
| 13 | LAB-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -3.58797633 | -3.58797633 | -3.58797633 | false |
| 14 | LAB-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -3.90724638 | -3.90724638 | -3.90724638 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -6.47648523 | -6.47648523 | -6.47648523 | false |
| 16 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 3 | 33.3333 | -15.09985187 | -3.91633497 | -14.27195333 | false |
| 17 | SOXL-USDT-SWAP | time_series_momentum | all | 5 | 20.0000 | -13.86540030 | -1.29157634 | -13.57458154 | false |
| 18 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 4 | 25.0000 | -16.53759583 | -4.60158656 | -9.94631974 | false |
| 19 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -10.45637706 | -5.33957054 | -7.83649084 | false |
| 20 | LAB-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -5.78592227 | -5.78592227 | -5.78592227 | false |
| 21 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -12.00907854 | -6.16550847 | -8.57790452 | false |
| 22 | ZEC-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -9.54287641 | -9.54287641 | -9.54287641 | false |
| 23 | ETH-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -13.26647532 | -6.80863749 | -10.16684801 | false |
| 24 | EDGE-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -16.65824610 | -6.10043756 | -11.04943418 | false |
| 25 | EDGE-USDT-SWAP | time_series_momentum | all | 5 | 0.0000 | -17.84013410 | -2.17330728 | -8.02445157 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 0.01180182 | -3.45042698 | 0.650558 | 6.78754020 | false |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 6.17408565 | -10.16684801 | 0.043173 | 10.92076122 | false |
| 5 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.68426350 | -7.83649084 | 0.152608 | 8.60952409 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.30114653 | -2.84265025 | 0.718515 | 6.27543323 | false |
| 5 | 1 | SOL-USDT-SWAP | time_series_momentum | all | 6.52333736 | -6.35898516 | 0.311495 | 8.17074404 | false |
| 5 | 2 | SOL-USDT-SWAP | multi_horizon_momentum | all | 1.51844989 | -1.76402822 | 0.811120 | 3.91094471 | false |
| 6 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 4.14879951 | 2.08148542 | 1.754374 | 4.80469666 | true |
| 6 | 2 | SOL-USDT-SWAP | time_series_momentum | all | 0.75882667 | 3.63816775 | 2.571358 | 6.03249451 | true |
| 7 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 2.80484740 | -0.43483866 | 1.097078 | 7.12704776 | false |
| 8 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 1.85925929 | -9.01936364 | 0.240531 | 9.39930801 | false |
| 13 | 1 | SOL-USDT-SWAP | time_series_momentum | all | 0.13689342 | 0.16902779 | 1.210538 | 6.70383162 | true |
| 14 | 1 | SOL-USDT-SWAP | time_series_momentum | all | 4.88460338 | -3.74465630 | 0.542635 | 5.53476326 | false |
| 15 | 1 | SOL-USDT-SWAP | time_series_momentum | all | 0.14885807 | -6.50220585 | 0.000000 | 7.64166337 | false |
| 1 | 1 | MU-USDT-SWAP | multi_horizon_momentum | all | 3.13388528 | -8.18095321 | 0.271888 | 8.55041403 | false |
| 2 | 1 | MU-USDT-SWAP | time_series_momentum | all | 3.08778450 | -4.11336772 | 0.556802 | 7.89070200 | false |
| 2 | 2 | MU-USDT-SWAP | multi_horizon_momentum | all | 1.19384848 | -1.03258904 | 0.963576 | 5.40631073 | false |
| 3 | 1 | MU-USDT-SWAP | time_series_momentum | all | 1.83906064 | -4.44371697 | 0.693843 | 9.65596614 | false |
| 3 | 2 | MU-USDT-SWAP | multi_horizon_momentum | all | 0.50382476 | 0.70830683 | 1.263976 | 8.17823133 | true |
| 15 | 1 | LAB-USDT-SWAP | time_series_momentum | all | 9.23093967 | -3.90724638 | 1.252026 | 11.69171543 | false |
| 15 | 2 | LAB-USDT-SWAP | multi_horizon_momentum | all | 5.40470046 | -3.58797633 | 1.319072 | 11.24004971 | false |
| 15 | 3 | LAB-USDT-SWAP | time_series_momentum | all | 0.07153301 | -5.78592227 | 1.014264 | 13.71891449 | false |
| 1 | 1 | ZEC-USDT-SWAP | time_series_momentum | all | 3.00365292 | -9.54287641 | 0.066652 | 9.96287185 | false |
| 1 | 2 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 0.35904853 | -1.67979377 | 0.687199 | 5.56671698 | false |
| 5 | 1 | ZEC-USDT-SWAP | time_series_momentum | all | 4.87885780 | -6.47648523 | 0.292583 | 8.33954534 | false |
| 5 | 2 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 3.14611376 | -3.88732790 | 0.471877 | 5.19822586 | false |
