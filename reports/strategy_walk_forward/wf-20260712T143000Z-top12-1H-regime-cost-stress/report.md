# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 912 |
| Passed window rows | 285 |
| Unique aggregate candidates | 159 |
| Passed aggregate candidates | 4 |
| Median selected test return | -1.406728% |
| Mean selected test return | -0.677167% |
| Best aggregate return | 91.553953% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | BEAT-USDT-SWAP | multi_horizon_momentum | all | 9 | 33.3333 | 91.55395320 | -3.26454750 | -18.12198375 | false |
| 2 | BEAT-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 56.20104186 | 3.11560800 | -0.31109703 | true |
| 3 | ZEC-USDT-SWAP | time_series_momentum | all | 13 | 46.1538 | 55.36561081 | 0.54083553 | -9.31088274 | false |
| 4 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 44.43915709 | 6.50985693 | -8.94248327 | false |
| 5 | BEAT-USDT-SWAP | time_series_momentum | all | 3 | 100.0000 | 39.97998157 | 8.32300625 | 4.28462095 | true |
| 6 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 12 | 41.6667 | 46.82190089 | 1.52145838 | -9.89238844 | false |
| 7 | SOL-USDT-SWAP | time_series_momentum | all | 16 | 62.5000 | 37.04313253 | 1.94384372 | -8.31647516 | false |
| 8 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 9 | DOGE-USDT-SWAP | multi_horizon_momentum | all | 15 | 26.6667 | 36.62352145 | 1.58882035 | -6.45597437 | false |
| 10 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 11 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 12 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 13 | HYPE-USDT-SWAP | time_series_momentum | all | 14 | 50.0000 | 26.32739345 | 0.87587324 | -13.36711928 | false |
| 14 | BTC-USDT-SWAP | time_series_momentum | all | 21 | 47.6190 | 23.66382583 | 0.14151760 | -6.56459222 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 16 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 17 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 18 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 19 | EDGE-USDT-SWAP | time_series_momentum | all | 2 | 0.0000 | 30.86774678 | 14.96010458 | 3.60004443 | false |
| 20 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 21 | EDGE-USDT-SWAP | time_series_momentum | all | 1 | 0.0000 | 28.04903002 | 28.04903002 | 28.04903002 | false |
| 22 | SOL-USDT-SWAP | multi_horizon_momentum | all | 5 | 20.0000 | 22.56726832 | 2.61600383 | -8.59192689 | false |
| 23 | HYPE-USDT-SWAP | time_series_momentum | all | 8 | 12.5000 | 23.81706224 | 2.79963608 | -11.95376375 | false |
| 24 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |
| 25 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 4.56233694 | 4.56233694 | 4.56233694 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 20.22242698 | -11.07596435 | 0.133518 | 13.63216865 | false |
| 1 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 18.56500462 | -16.08399517 | 0.000000 | 18.84411757 | false |
| 1 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 11.93085070 | -14.61166373 | 0.054139 | 15.52756778 | false |
| 2 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.37405033 | -1.48152474 | 0.297464 | 7.02329313 | false |
| 2 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 0.35603396 | 5.91501012 | 3.528789 | 4.87921277 | true |
| 2 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 1.34941353 | -4.41858958 | 0.070175 | 7.02468330 | false |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 5.66822215 | 9.74767943 | 3.653081 | 8.12378399 | true |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.76922305 | 14.46767776 | 999.000000 | 5.54141010 | false |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 20.35233321 | -5.95254506 | 0.470072 | 8.56536866 | false |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3.31412684 | -1.45492268 | 0.796270 | 9.10529218 | false |
| 5 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.18092099 | 9.98569302 | 10.325384 | 3.95046979 | true |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 10.31332291 | 0.07112492 | 1.543962 | 7.62112422 | false |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.51576531 | 0.07112492 | 1.543962 | 7.62112422 | false |
| 6 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 6.24672316 | 0.07112492 | 1.543962 | 7.62112422 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 16.63773862 | -5.75976330 | 0.215127 | 11.51716767 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 17.40281449 | -6.55734825 | 0.157816 | 12.12672494 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 12.83679656 | -0.05846368 | 1.186940 | 8.96853198 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.63536633 | -7.59926710 | 0.176411 | 12.37218253 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 11.95100778 | -4.41565699 | 0.498140 | 12.12315467 | false |
| 8 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 7.61150886 | 6.32582094 | 4.287573 | 6.15510132 | true |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 14.71964425 | -0.75724782 | 0.962932 | 6.63950644 | false |
| 9 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 6.77027287 | -0.75724782 | 0.962932 | 6.63950644 | false |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.90540003 | -11.65165073 | 0.150291 | 15.19829641 | false |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 8.50437414 | -7.18516769 | 0.135110 | 10.95280652 | false |
| 14 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 2.19182647 | 0.05719549 | 1.074223 | 7.54903258 | true |
