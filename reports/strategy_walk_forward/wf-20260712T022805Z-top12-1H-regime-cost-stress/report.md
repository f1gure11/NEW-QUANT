# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 862 |
| Passed window rows | 288 |
| Unique aggregate candidates | 150 |
| Passed aggregate candidates | 4 |
| Median selected test return | -0.774386% |
| Mean selected test return | -0.594043% |
| Best aggregate return | 91.553953% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | BEAT-USDT-SWAP | multi_horizon_momentum | all | 9 | 33.3333 | 91.55395320 | -3.26454750 | -18.12198375 | false |
| 2 | BEAT-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 56.20104186 | 3.11560800 | -0.31109703 | true |
| 3 | PEPE-USDT-SWAP | time_series_momentum | all | 11 | 45.4545 | 54.71988315 | -0.80175010 | -9.23235797 | false |
| 4 | ZEC-USDT-SWAP | time_series_momentum | all | 13 | 46.1538 | 55.36561081 | 0.54083553 | -9.31088274 | false |
| 5 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 44.43915709 | 6.50985693 | -8.94248327 | false |
| 6 | BEAT-USDT-SWAP | time_series_momentum | all | 3 | 100.0000 | 39.97998157 | 8.32300625 | 4.28462095 | true |
| 7 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 12 | 41.6667 | 46.82190089 | 1.52145838 | -9.89238844 | false |
| 8 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 15 | 40.0000 | 43.43396771 | 2.05066422 | -3.94797552 | false |
| 9 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 10 | SOL-USDT-SWAP | time_series_momentum | all | 15 | 66.6667 | 31.13436596 | 1.45915703 | -9.42745747 | false |
| 11 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 12 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 13 | BTC-USDT-SWAP | time_series_momentum | all | 20 | 40.0000 | 29.51447883 | 1.76916651 | -10.99338769 | false |
| 14 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 15 | HYPE-USDT-SWAP | time_series_momentum | all | 13 | 53.8462 | 28.08636757 | 0.19243986 | -11.18966281 | false |
| 16 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 17 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 18 | HYPE-USDT-SWAP | time_series_momentum | all | 9 | 55.5556 | 20.81686641 | 3.12368556 | -5.12799360 | false |
| 19 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 20 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 21 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 22 | SOL-USDT-SWAP | multi_horizon_momentum | all | 6 | 50.0000 | 18.71593159 | 3.28611199 | -9.27494606 | false |
| 23 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 24 | BTC-USDT-SWAP | time_series_momentum | all | 10 | 70.0000 | 5.88741439 | 0.99571981 | -11.24377638 | false |
| 25 | SOL-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 4.30757714 | 4.30757714 | 4.30757714 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 23.30313545 | -17.16438246 | 0.000000 | 18.88449696 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 21.49741790 | -10.92912183 | 0.120595 | 12.77871400 | false |
| 1 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 17.66587834 | -16.95044222 | 0.063342 | 17.29561544 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 3.41965254 | 5.13122716 | 3.582726 | 4.87285960 | true |
| 2 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.19110730 | 0.06693291 | 1.193387 | 6.51074865 | false |
| 2 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 6.72264195 | -4.96588713 | 0.236498 | 6.52091902 | false |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 5.66213963 | 12.57383683 | 4.354449 | 7.91038934 | true |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.12805882 | 14.55653204 | 12.547563 | 5.54141010 | false |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 22.69133313 | 1.23687651 | 1.295004 | 6.19395364 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 8.12756016 | 1.95856338 | 3.006539 | 4.50503207 | true |
| 4 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.44599107 | -4.20525127 | 0.671971 | 8.45972864 | false |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.41509111 | -15.47256771 | 0.334981 | 15.59458405 | false |
| 5 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10.26688460 | 2.51685866 | 1.433311 | 6.67114402 | true |
| 5 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 1.49044016 | -11.72407240 | 0.546282 | 17.44443926 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 7.01255358 | 2.57918839 | 6.579869 | 7.86905870 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 6.42526393 | 2.57918839 | 6.579869 | 7.86905870 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 1.54920730 | 2.57918839 | 6.579869 | 7.86905870 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 15.65762600 | -6.52709168 | 0.077603 | 11.10325724 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 16.41587676 | -7.32067088 | 0.028125 | 11.71566593 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 11.89576979 | -1.26319705 | 0.959698 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 15.67682047 | -3.25063197 | 0.583444 | 11.57136626 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 11.65510807 | 7.53705459 | 22.038647 | 5.52166137 | true |
| 8 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 13.17619495 | -2.43167137 | 0.720981 | 13.51180332 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 10.56321956 | -1.76905283 | 0.811757 | 6.62550668 | false |
| 9 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 2.95714773 | -1.76905283 | 0.811757 | 6.62550668 | false |
