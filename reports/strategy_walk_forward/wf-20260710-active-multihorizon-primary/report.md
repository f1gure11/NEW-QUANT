# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 195 |
| Passed window rows | 34 |
| Unique aggregate candidates | 44 |
| Passed aggregate candidates | 0 |
| Median selected test return | -4.641298% |
| Mean selected test return | -3.635415% |
| Best aggregate return | 16.266849% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 17 | 47.0588 | 8.00823713 | 0.29262082 | -23.16911800 | false |
| 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | -1.94966247 | -0.96817217 | -2.47454863 | false |
| 3 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | 0.54857186 | 0.27942338 | -0.77203624 | false |
| 4 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -3.45723127 | -1.74276859 | -2.19735844 | false |
| 5 | LAB-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | 16.26684922 | 29.17162906 | -41.95238118 | false |
| 6 | SOL-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -4.14119145 | -4.14119145 | -4.14119145 | false |
| 7 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 4 | 25.0000 | -5.77143219 | 0.68113487 | -11.82853797 | false |
| 8 | SOL-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -5.40642739 | -2.73012939 | -4.16904137 | false |
| 9 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5 | 0.0000 | -11.02225399 | -2.64970655 | -3.62951000 | false |
| 10 | SOL-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -5.55845352 | -5.55845352 | -5.55845352 | false |
| 11 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 4 | 25.0000 | -13.93219614 | -2.58605460 | -10.45385504 | false |
| 12 | SOL-USDT-SWAP | multi_horizon_momentum | all | 9 | 22.2222 | -18.82358141 | -1.58531463 | -7.43735544 | false |
| 13 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -10.93577363 | -5.57780890 | -8.59898993 | false |
| 14 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 15 | 33.3333 | -20.21751684 | 0.10916368 | -21.17704252 | false |
| 15 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -13.34655225 | -6.89952240 | -8.43384760 | false |
| 16 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 3 | 66.6667 | -20.68126391 | 0.44135336 | -23.95615826 | false |
| 17 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -13.46062877 | -6.97161433 | -7.55763268 | false |
| 18 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -10.23172452 | -10.23172452 | -10.23172452 | false |
| 19 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -11.78308247 | -6.00222215 | -9.72921658 | false |
| 20 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -15.20820086 | -7.91603802 | -8.44152855 | false |
| 21 | MU-USDT-SWAP | multi_horizon_momentum | all | 4 | 0.0000 | -19.48788326 | -5.62974193 | -7.65962935 | false |
| 22 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 4 | 0.0000 | -16.07482853 | -5.06670542 | -6.39195706 | false |
| 23 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | -23.25484990 | -4.89843380 | -12.71530956 | false |
| 24 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 0.0000 | -17.74050283 | -3.00523743 | -13.03736445 | false |
| 25 | SKHYNIX-USDT-SWAP | multi_horizon_momentum | all | 4 | 0.0000 | -18.23984956 | -4.34037714 | -8.51733920 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.70978242 | -2.47454863 | 0.416832 | 3.19298284 | false |
| 2 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.32193594 | 0.53820429 | 1.494773 | 1.92614824 | true |
| 10 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 6.77433199 | -1.08941160 | 0.909835 | 6.13332969 | false |
| 11 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.68169388 | -3.08623220 | 0.570842 | 6.43634552 | false |
| 13 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.03633381 | -3.62951000 | 0.301006 | 5.72701973 | false |
| 33 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.59851579 | -2.19735844 | 0.425146 | 2.96987544 | false |
| 33 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.56376300 | -1.06002323 | 0.488402 | 2.77883877 | false |
| 34 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.39888883 | -2.64970655 | 0.296008 | 5.10706884 | false |
| 34 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3.11052104 | -1.28817874 | 0.604154 | 3.77791937 | false |
| 3 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 0.04208022 | -8.31305726 | 0.290821 | 11.07298375 | false |
| 25 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 2.99591792 | -2.99836089 | 0.724091 | 13.46147069 | false |
| 26 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8.61634455 | -7.55763268 | 0.290123 | 10.01179049 | false |
| 26 | 2 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 5.76467037 | -5.36519721 | 0.537629 | 7.87755974 | false |
| 26 | 3 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7.19821882 | -5.40405350 | 0.435877 | 7.91538448 | false |
| 27 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8.78528737 | -8.43384760 | 0.163482 | 8.89639611 | false |
| 27 | 2 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 6.96262162 | -6.38559598 | 0.233894 | 7.64975252 | false |
| 27 | 3 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 6.52740188 | -7.39054748 | 0.145389 | 7.98507586 | false |
| 32 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 0.50747496 | -5.33331765 | 0.074552 | 6.02400467 | false |
| 32 | 2 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 0.94245385 | -8.44152855 | 0.040105 | 9.01168677 | false |
| 33 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 1.58259730 | -8.90194841 | 0.086970 | 9.73693051 | false |
| 35 | 1 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 2.50070508 | -11.53046927 | 0.150295 | 20.43825209 | false |
| 1 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 0.51084373 | -4.14119145 | 0.375782 | 4.75194241 | false |
| 2 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 0.10373663 | -7.43735544 | 0.316342 | 8.62915116 | false |
| 9 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 1.41260984 | -5.55845352 | 0.504562 | 11.15518028 | false |
| 10 | 1 | SOL-USDT-SWAP | multi_horizon_momentum | all | 6.92483223 | -4.16904137 | 0.459569 | 8.37105708 | false |
