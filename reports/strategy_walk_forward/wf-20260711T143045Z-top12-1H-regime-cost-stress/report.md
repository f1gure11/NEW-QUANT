# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 681 |
| Passed window rows | 245 |
| Unique aggregate candidates | 124 |
| Passed aggregate candidates | 5 |
| Median selected test return | -0.223118% |
| Mean selected test return | -0.120059% |
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
| 9 | SNDK-USDT-SWAP | time_series_momentum | all | 1 | 100.0000 | 21.56727437 | 21.56727437 | 21.56727437 | false |
| 10 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 6 | 33.3333 | 36.27917256 | 2.71925505 | -11.84384364 | false |
| 11 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 23.20261483 | 8.00754634 | 2.46614493 | true |
| 12 | ZEC-USDT-SWAP | time_series_momentum | all | 6 | 83.3333 | 23.65052991 | 3.15238083 | -10.43425873 | false |
| 13 | BTC-USDT-SWAP | time_series_momentum | all | 21 | 47.6190 | 26.87710725 | 2.24137328 | -10.81652409 | false |
| 14 | MU-USDT-SWAP | multi_horizon_momentum | all | 10 | 40.0000 | 28.35521491 | 3.90007199 | -10.06333108 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 16.90966393 | 8.12631991 | 7.54781724 | false |
| 16 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 17.16144783 | 6.16572557 | 2.65160796 | true |
| 17 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9 | 66.6667 | 22.31010108 | 0.97410936 | -8.95862191 | false |
| 18 | HYPE-USDT-SWAP | multi_horizon_momentum | all | 3 | 100.0000 | 15.96095685 | 2.62054562 | 2.56601674 | true |
| 19 | BEAT-USDT-SWAP | time_series_momentum | all | 13 | 23.0769 | 28.47825884 | 2.80818659 | -9.23922233 | false |
| 20 | ZEC-USDT-SWAP | time_series_momentum | all | 7 | 57.1429 | 21.19229079 | 2.88583448 | -5.00137280 | false |
| 21 | SOL-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 11.38365334 | 5.56857555 | 3.04690773 | false |
| 22 | HYPE-USDT-SWAP | time_series_momentum | all | 8 | 50.0000 | 15.97737433 | -0.33205695 | -4.13393140 | false |
| 23 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 8 | 12.5000 | 23.99883667 | 3.99904614 | -10.26221309 | false |
| 24 | SOL-USDT-SWAP | time_series_momentum | all | 17 | 58.8235 | 11.67943632 | 3.18823155 | -11.70858872 | false |
| 25 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 7 | 14.2857 | 20.01661898 | 4.78281539 | -12.87078248 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 24.43004703 | -12.95032223 | 0.249047 | 18.24755450 | false |
| 1 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 19.85122396 | -14.87300132 | 0.118550 | 15.64365122 | false |
| 1 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 21.29164497 | -6.33366586 | 0.521250 | 12.08192972 | false |
| 2 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 16.83901970 | -6.70259312 | 0.384257 | 10.56444374 | false |
| 2 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 6.84383941 | 1.72101627 | 1.589897 | 4.64708884 | true |
| 2 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.73397102 | 1.94705958 | 1.879454 | 4.30353755 | true |
| 3 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 4.87742376 | 10.55958735 | 3.769554 | 7.84611367 | true |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3.81494981 | 7.13204844 | 2.912020 | 6.57341880 | false |
| 4 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 17.66569057 | 2.97929450 | 1.813395 | 7.43670225 | true |
| 4 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 3.92876946 | 3.98865551 | 999.000000 | 4.38805500 | false |
| 5 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 8.94817284 | -12.09745675 | 0.398575 | 13.50938385 | false |
| 5 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 6.92957511 | 3.32011945 | 1.702113 | 6.62380449 | true |
| 5 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 1.85903313 | -7.52467620 | 0.674042 | 14.77734785 | false |
| 6 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 9.01364689 | 0.97410936 | 1.496053 | 7.72009350 | true |
| 6 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 6.97230562 | 2.38419627 | 2.833353 | 7.66625741 | false |
| 7 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 18.49927969 | -6.42954270 | 0.000000 | 10.67721747 | false |
| 7 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 19.27752983 | -6.42954270 | 0.000000 | 10.67721747 | false |
| 7 | 3 | ETH-USDT-SWAP | time_series_momentum | all | 14.81692738 | -1.37173271 | 0.932850 | 8.61630232 | false |
| 8 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 16.43992589 | -5.12318378 | 0.354923 | 11.57136626 | false |
| 8 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 10.99976938 | 6.40792814 | 20.395784 | 4.26422980 | true |
| 8 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 13.40809214 | -8.78156535 | 0.269614 | 16.77610796 | false |
| 9 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 12.21951555 | -0.96771350 | 0.915268 | 6.74302353 | false |
| 9 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 4.69209240 | -0.96771350 | 0.915268 | 6.74302353 | false |
| 10 | 1 | ETH-USDT-SWAP | time_series_momentum | all | 6.38734772 | -8.98528754 | 0.182340 | 14.20852987 | false |
| 10 | 2 | ETH-USDT-SWAP | time_series_momentum | all | 1.93159693 | -5.68286009 | 0.155945 | 11.09406674 | false |
