# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 749 |
| Passed window rows | 244 |
| Unique aggregate candidates | 136 |
| Passed aggregate candidates | 4 |
| Median selected test return | -0.836323% |
| Mean selected test return | -0.222616% |
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
| 9 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 15 | 40.0000 | 38.01841596 | 3.86560002 | -9.39336775 | false |
| 10 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 11 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 12 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 13 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 14 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 14 | 21.4286 | 34.73070981 | 4.52797180 | -12.84892637 | false |
| 15 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 16 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 17 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 18 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 19 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 20 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 21 | ETH-USDT-SWAP | multi_horizon_momentum | all | 11 | 27.2727 | 18.30314559 | -0.57230211 | -11.40001207 | false |
| 22 | HYPE-USDT-SWAP | time_series_momentum | all | 8 | 50.0000 | 13.09292314 | 0.34451319 | -13.31880463 | false |
| 23 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 24 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 4.56233694 | 4.56233694 | 4.56233694 | false |
| 25 | BEAT-USDT-SWAP | time_series_momentum | all | 10 | 60.0000 | 7.23720222 | 1.18179802 | -10.88579526 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 14.93930279 | -13.40792434 | 0.000000 | 18.28653652 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 11.77810164 | -8.75261074 | 0.251267 | 12.48618282 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 12.64525643 | -13.17551816 | 0.125939 | 13.54735344 | false |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 10.26892896 | 4.11239388 | 1.622958 | 8.80350574 | true |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 21.56902887 | 1.37452190 | 1.237889 | 10.07475052 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 13.36094199 | 2.83003608 | 1.556695 | 9.10529218 | true |
| 4 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 0.53238963 | 8.26740034 | 2.419405 | 5.52701994 | true |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.80905003 | -15.09725515 | 0.274501 | 19.20221343 | false |
| 5 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 9.63518164 | -10.25016783 | 0.341081 | 16.86010662 | false |
| 5 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.95375699 | 9.11214910 | 15.238963 | 4.03351031 | true |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 29.90991485 | -2.55510158 | 0.416180 | 6.06905593 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 29.27066935 | -2.55510158 | 0.416180 | 6.06905593 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 22.22551224 | -2.55510158 | 0.416180 | 6.06905593 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 20.02875596 | -11.40001207 | 0.010847 | 12.83675751 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 20.05385380 | -12.15324234 | 0.000000 | 13.57777333 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 16.20984955 | -2.30069760 | 0.086322 | 10.35521700 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.83306773 | -9.91123467 | 0.004995 | 12.81772928 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 4.49764355 | -10.92479019 | 0.000000 | 14.04294624 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 9.67148233 | -6.19019783 | 0.419172 | 10.43390646 | false |
| 9 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 2.43840081 | -7.13570928 | 0.337901 | 11.33664546 | false |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.82981412 | -9.86416717 | 0.147787 | 10.39851712 | false |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 2.13858952 | -5.70685134 | 0.000000 | 7.91624793 | false |
| 15 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.57011287 | 2.82055128 | 1.459456 | 10.28021565 | true |
| 15 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 8.85391340 | 9.56087401 | 3.576346 | 8.41850405 | true |
| 15 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 8.47991544 | 6.11303045 | 1.950577 | 11.58523400 | true |
