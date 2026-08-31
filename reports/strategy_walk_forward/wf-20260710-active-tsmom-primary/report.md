# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 233 |
| Passed window rows | 36 |
| Unique aggregate candidates | 50 |
| Passed aggregate candidates | 0 |
| Median selected test return | -4.742646% |
| Mean selected test return | -4.804527% |
| Best aggregate return | -1.415415% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | XAU-USDT-SWAP | time_series_momentum | all | 4 | 25.0000 | -2.88995083 | -0.33010128 | -2.59921311 | false |
| 2 | BTC-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -1.41541474 | -1.41541474 | -1.41541474 | false |
| 3 | SPCX-USDT-SWAP | time_series_momentum | all | 8 | 25.0000 | -7.24501883 | -1.66597985 | -17.38349485 | false |
| 4 | ETH-USDT-SWAP | time_series_momentum | all | 10 | 30.0000 | -10.46467803 | -2.24676453 | -5.88906565 | false |
| 5 | SOL-USDT-SWAP | time_series_momentum | all | 10 | 40.0000 | -11.70395779 | -1.90174817 | -5.06359685 | false |
| 6 | SOL-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -4.74264629 | -4.74264629 | -4.74264629 | false |
| 7 | MU-USDT-SWAP | time_series_momentum | all | 4 | 25.0000 | -11.48925718 | -3.29416329 | -5.46061187 | false |
| 8 | EDGE-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -4.81023255 | -2.42320929 | -3.92432219 | false |
| 9 | SOL-USDT-SWAP | time_series_momentum | all | 3 | 33.3333 | -13.17676793 | -7.46134622 | -9.45710208 | false |
| 10 | SOL-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -8.70184079 | -2.59845668 | -5.49352990 | false |
| 11 | SOXL-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | -7.09071240 | -2.31048737 | -14.70393774 | false |
| 12 | EDGE-USDT-SWAP | time_series_momentum | all | 9 | 0.0000 | -8.69986687 | -3.22111131 | -7.15678738 | false |
| 13 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 42.8571 | -20.64200909 | -5.29083250 | -20.47926460 | false |
| 14 | SNDK-USDT-SWAP | time_series_momentum | all | 6 | 33.3333 | -21.32196453 | -2.52376048 | -17.96385262 | false |
| 15 | SKHYNIX-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -15.43798086 | -4.21742216 | -11.00249952 | false |
| 16 | ZEC-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -9.45588447 | -9.45588447 | -9.45588447 | false |
| 17 | SOXL-USDT-SWAP | time_series_momentum | all | 18 | 44.4444 | -25.85552667 | 1.57930870 | -22.41289145 | false |
| 18 | EDGE-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -13.28823459 | -6.61656569 | -13.63719696 | false |
| 19 | ZEC-USDT-SWAP | time_series_momentum | all | 14 | 28.5714 | -25.35075089 | -2.59533943 | -18.09759350 | false |
| 20 | SPCX-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -21.67772253 | -9.74359594 | -11.32236900 | false |
| 21 | SKHYNIX-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -17.07765617 | -8.93289729 | -9.92426666 | false |
| 22 | ETH-USDT-SWAP | time_series_momentum | all | 3 | 0.0000 | -20.36869572 | -5.72693371 | -11.78871831 | false |
| 23 | MU-USDT-SWAP | time_series_momentum | all | 6 | 0.0000 | -24.61578135 | -3.51204419 | -10.14927481 | false |
| 24 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | -17.79559442 | -9.29548699 | -11.91619710 | false |
| 25 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | -12.06422778 | -12.06422778 | -12.06422778 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 2 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.33291809 | -1.41541474 | 0.750200 | 3.15846808 | false |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.58308603 | -3.26535059 | 0.120598 | 5.14164033 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.82700212 | 2.79573184 | 4.030685 | 1.86866999 | true |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.09615162 | -5.88906565 | 0.066265 | 7.61602795 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.48072781 | -11.78871831 | 0.107906 | 14.25249970 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.58268299 | 5.17329479 | 2.630177 | 6.01276101 | true |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 10.81825932 | 2.19797188 | 2.570977 | 4.14732630 | true |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 1.25624405 | -5.72693371 | 0.387617 | 8.66546651 | false |
| 11 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 14.28984233 | -3.00756044 | 0.539566 | 6.74781100 | false |
| 12 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 4.10095946 | -1.07789592 | 0.807210 | 4.40981875 | false |
| 13 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.82557357 | -2.91371143 | 0.274000 | 5.02713121 | false |
| 20 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 0.32542615 | -4.24266215 | 0.109775 | 4.27434695 | false |
| 33 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 1.51699797 | -2.03721727 | 0.000000 | 2.66322636 | false |
| 34 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.75711570 | -2.45631180 | 0.028679 | 4.66195927 | false |
| 3 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 0.31565963 | -6.69516080 | 0.398704 | 10.04080232 | false |
| 3 | 2 | SNDK-USDT-SWAP | time_series_momentum | all | 0.12382296 | -2.72884922 | 0.162434 | 5.13179925 | false |
| 4 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 1.06362188 | -2.31867173 | 0.078823 | 2.45289685 | false |
| 22 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 0.36925188 | 1.24370757 | 2.025846 | 2.83583464 | true |
| 23 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 5.49116512 | 10.58541712 | 5.697533 | 3.97681911 | true |
| 24 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 6.87263673 | -17.96385262 | 0.102078 | 19.94063966 | false |
| 25 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 2.74781890 | -4.76093284 | 0.543097 | 13.36850828 | false |
| 26 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 2.67524234 | -4.68004646 | 0.420450 | 7.62487898 | false |
| 26 | 2 | SNDK-USDT-SWAP | time_series_momentum | all | 0.51983664 | -14.38127547 | 0.164768 | 15.22283840 | false |
| 32 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 5.43297615 | -5.81045381 | 0.076695 | 6.49765384 | false |
| 33 | 1 | SNDK-USDT-SWAP | time_series_momentum | all | 2.71990112 | -13.81182742 | 0.050615 | 13.94835191 | false |
