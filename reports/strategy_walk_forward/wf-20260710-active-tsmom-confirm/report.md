# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 380 |
| Passed window rows | 68 |
| Unique aggregate candidates | 67 |
| Passed aggregate candidates | 1 |
| Median selected test return | -4.033614% |
| Mean selected test return | -3.808897% |
| Best aggregate return | 10.399716% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SKHYNIX-USDT-SWAP | time_series_momentum | all | 4 | 75.0000 | 6.61974245 | 2.35282927 | -2.54893545 | true |
| 2 | SKHYNIX-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 0.31992071 | 0.31992071 | 0.31992071 | false |
| 3 | SPCX-USDT-SWAP | time_series_momentum | all | 11 | 45.4545 | 0.40462523 | 0.98034692 | -15.64421639 | false |
| 4 | ZEC-USDT-SWAP | time_series_momentum | all | 21 | 33.3333 | -4.52880765 | 0.31037508 | -15.06412584 | false |
| 5 | XAU-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -1.18861347 | -1.18861347 | -1.18861347 | false |
| 6 | LAB-USDT-SWAP | time_series_momentum | all | 10 | 0.0000 | 10.39971638 | -3.89201463 | -32.30712259 | false |
| 7 | XAU-USDT-SWAP | time_series_momentum | all | 9 | 11.1111 | -9.56436730 | -1.05077392 | -1.86999834 | false |
| 8 | SOL-USDT-SWAP | time_series_momentum | all | 5 | 20.0000 | -8.17164006 | -2.97266599 | -6.20821606 | false |
| 9 | SOL-USDT-SWAP | time_series_momentum | all | 16 | 31.2500 | -12.93852562 | -0.76923919 | -7.87041399 | false |
| 10 | SOXL-USDT-SWAP | time_series_momentum | all | 11 | 27.2727 | -9.16016895 | -5.92227424 | -6.85211073 | false |
| 11 | ETH-USDT-SWAP | time_series_momentum | all | 14 | 35.7143 | -15.76547320 | -0.52776320 | -10.89905342 | false |
| 12 | MU-USDT-SWAP | time_series_momentum | all | 6 | 50.0000 | -14.94445404 | -2.37002148 | -8.70706700 | false |
| 13 | ETH-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -7.84980215 | -4.00203404 | -4.76994301 | false |
| 14 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -5.63771137 | -5.63771137 | -5.63771137 | false |
| 15 | SOL-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -7.38290422 | -3.73293518 | -6.10742264 | false |
| 16 | EDGE-USDT-SWAP | time_series_momentum | all | 12 | 25.0000 | -11.99405786 | -2.82676202 | -15.78560397 | false |
| 17 | SOXL-USDT-SWAP | time_series_momentum | all | 19 | 31.5789 | -15.41211597 | -0.27724409 | -20.14754381 | false |
| 18 | BTC-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -9.79122566 | -5.01743281 | -5.91778573 | false |
| 19 | SKHYNIX-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -9.46308765 | -3.90755690 | -4.58179756 | false |
| 20 | BTC-USDT-SWAP | time_series_momentum | all | 6 | 0.0000 | -12.45452320 | -1.04888033 | -5.71795082 | false |
| 21 | ZEC-USDT-SWAP | time_series_momentum | all | 8 | 37.5000 | -18.61231620 | -2.49665800 | -8.32998663 | false |
| 22 | EDGE-USDT-SWAP | time_series_momentum | all | 11 | 0.0000 | -11.41971137 | -3.17280669 | -42.61940667 | false |
| 23 | ZEC-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -12.20375645 | -3.91225154 | -5.93788210 | false |
| 24 | SNDK-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -12.45925842 | -6.37668420 | -9.73095069 | false |
| 25 | SPCX-USDT-SWAP | time_series_momentum | all | 4 | 25.0000 | -20.63653953 | -6.25668500 | -11.45746036 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.60750258 | -1.57988299 | 0.186126 | 1.66058042 | false |
| 2 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.81932427 | -0.42940116 | 0.974343 | 1.65032658 | false |
| 11 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.15089471 | -0.39824166 | 0.971204 | 8.08349597 | false |
| 12 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 3.95290917 | -4.37363315 | 0.476927 | 9.05654480 | false |
| 24 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.11363575 | -4.11707989 | 0.260886 | 4.24669982 | false |
| 33 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.93219525 | -5.71795082 | 0.000000 | 6.35604864 | false |
| 33 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 0.00150788 | -5.91778573 | 0.000000 | 5.96953135 | false |
| 43 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.75646686 | -0.51787767 | 1.019917 | 2.58156454 | false |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.62340969 | -0.63129428 | 0.597375 | 2.71129808 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 0.47621958 | -4.92290779 | 0.080743 | 4.98141911 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 4.65092776 | 1.53437197 | 4.117916 | 1.36458650 | true |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.16766146 | -5.60252705 | 0.027027 | 5.79793660 | false |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 0.89194602 | -2.14989210 | 0.338404 | 4.06201442 | false |
| 11 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.57350778 | -6.19096698 | 0.161880 | 11.10742272 | false |
| 12 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.07381818 | 8.78390148 | 10.278769 | 2.71880377 | true |
| 13 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 14.19798685 | -2.32822501 | 0.424397 | 7.05282066 | false |
| 13 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 0.60055060 | -5.50434445 | 0.392969 | 9.35085982 | false |
| 14 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 5.81041330 | 2.24599268 | 3.072769 | 2.80397874 | true |
| 15 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.68108790 | -2.75873264 | 0.565752 | 6.74781100 | false |
| 16 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 4.99424026 | 0.50034667 | 2.033921 | 3.23088797 | true |
| 24 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 5.72738047 | -2.91079070 | 0.450105 | 5.39478470 | false |
| 25 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.97870681 | -5.85395288 | 0.000000 | 6.22608702 | false |
| 33 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 7.87622008 | -10.89905342 | 0.005444 | 11.11807478 | false |
| 33 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 2.44289416 | -12.57507126 | 0.005505 | 12.78997276 | false |
| 33 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 1.83673744 | -3.23412507 | 0.537983 | 4.63955173 | false |
