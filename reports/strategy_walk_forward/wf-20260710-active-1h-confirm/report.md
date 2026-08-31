# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 777 |
| Passed window rows | 271 |
| Unique aggregate candidates | 116 |
| Passed aggregate candidates | 2 |
| Median selected test return | -0.581662% |
| Mean selected test return | 0.291803% |
| Best aggregate return | 168.147527% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | ZEC-USDT-SWAP | time_series_momentum | all | 17 | 41.1765 | 168.14752667 | 3.82044770 | -6.45403745 | false |
| 2 | MU-USDT-SWAP | time_series_momentum | all | 12 | 50.0000 | 105.76677798 | 2.55615977 | -5.58907517 | false |
| 3 | SPCX-USDT-SWAP | time_series_momentum | all | 2 | 50.0000 | 84.48266875 | 43.23320573 | -2.23639235 | false |
| 4 | SPCX-USDT-SWAP | time_series_momentum | all | 4 | 25.0000 | 80.19225023 | -0.34422797 | -5.48944659 | false |
| 5 | MU-USDT-SWAP | multi_horizon_momentum | all | 8 | 25.0000 | 70.33110003 | 4.13277056 | -7.10239223 | false |
| 6 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 9 | 11.1111 | 55.62834959 | 7.72782989 | -7.50046230 | false |
| 7 | SOL-USDT-SWAP | time_series_momentum | all | 20 | 60.0000 | 45.78282783 | 1.54370000 | -11.93374369 | false |
| 8 | ZEC-USDT-SWAP | time_series_momentum | all | 15 | 66.6667 | 43.55726611 | 3.10874373 | -12.50538579 | false |
| 9 | MU-USDT-SWAP | time_series_momentum | all | 8 | 12.5000 | 50.29836896 | 3.85386938 | -6.22354690 | false |
| 10 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 11 | 63.6364 | 37.93434658 | 0.72278502 | -3.80334173 | false |
| 11 | SOL-USDT-SWAP | multi_horizon_momentum | all | 8 | 25.0000 | 30.42458500 | 3.32775243 | -6.47129341 | false |
| 12 | BTC-USDT-SWAP | time_series_momentum | all | 24 | 45.8333 | 23.83101287 | 0.29490542 | -8.23554986 | false |
| 13 | SNDK-USDT-SWAP | time_series_momentum | all | 7 | 14.2857 | 31.07239691 | 0.89935767 | -4.80216775 | false |
| 14 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 8 | 62.5000 | 20.17541195 | 3.34998322 | -7.58719325 | false |
| 15 | ZEC-USDT-SWAP | time_series_momentum | all | 11 | 54.5455 | 19.77470550 | 0.15754822 | -5.91460622 | false |
| 16 | ETH-USDT-SWAP | multi_horizon_momentum | all | 19 | 31.5789 | 24.67156428 | 0.62974338 | -10.49569530 | false |
| 17 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 5 | 80.0000 | 13.94885650 | 2.36625047 | -2.61578197 | true |
| 18 | SPCX-USDT-SWAP | time_series_momentum | all | 5 | 60.0000 | 16.83965207 | 3.80661016 | -7.84916187 | false |
| 19 | BASED-USDT-SWAP | multi_horizon_momentum | all | 9 | 66.6667 | 13.92764743 | 2.80784952 | -11.88981354 | false |
| 20 | SOL-USDT-SWAP | multi_horizon_momentum | all | 8 | 50.0000 | 15.22114264 | 1.99255181 | -11.69379736 | false |
| 21 | ZEC-USDT-SWAP | time_series_momentum | all | 2 | 100.0000 | 6.95397128 | 3.47546779 | 0.04395101 | false |
| 22 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 8 | 37.5000 | 15.70680780 | 2.02048163 | -8.84156922 | false |
| 23 | MU-USDT-SWAP | time_series_momentum | all | 3 | 66.6667 | 9.09515326 | 1.61209065 | -0.26921040 | true |
| 24 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | 8.55357669 | 4.26621571 | 0.25547133 | false |
| 25 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 33.3333 | 11.39964341 | -1.14920202 | -7.34277643 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 10.23819857 | -0.88161719 | 0.781773 | 5.36423393 | false |
| 1 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 12.44146704 | -2.48681083 | 0.000000 | 5.31534691 | false |
| 1 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 10.07818414 | -2.42315283 | 0.058953 | 5.25353542 | false |
| 2 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 10.93757084 | 6.87069692 | 10.232636 | 5.08478257 | true |
| 2 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 9.88984593 | 5.63002857 | 3.245388 | 4.75138655 | true |
| 2 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 9.88366903 | 2.79000696 | 2.028733 | 6.80182883 | true |
| 3 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 15.30432310 | 2.95131348 | 5.245280 | 2.48070958 | true |
| 3 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 14.38176540 | 4.62264306 | 999.000000 | 2.43285470 | false |
| 3 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 13.65901998 | -0.42762946 | 0.983554 | 4.00728248 | false |
| 4 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 19.96506024 | -7.29059630 | 0.261919 | 11.97780436 | false |
| 4 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 18.64326760 | -6.00430855 | 0.405391 | 10.52798726 | false |
| 4 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 15.12272468 | -10.04165711 | 0.194808 | 12.37373077 | false |
| 5 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 8.90075142 | 0.28128383 | 1.850683 | 3.62725408 | true |
| 5 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 5.45829199 | 1.09489391 | 8.001530 | 2.97440417 | true |
| 5 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.47314459 | -1.80676993 | 0.500789 | 3.62649566 | false |
| 6 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 6.69778306 | 3.14655184 | 4.541240 | 4.45632620 | true |
| 6 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 5.13620968 | 1.96089224 | 2.551320 | 5.00772216 | true |
| 6 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.85092524 | -4.96389454 | 0.335727 | 6.93885415 | false |
| 7 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 5.24766092 | 0.43697732 | 1.247414 | 7.03608657 | true |
| 7 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 1.32688138 | 3.32816670 | 2.727258 | 4.90627247 | true |
| 7 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.06051047 | 4.87151455 | 999.000000 | 3.86404498 | false |
| 8 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 8.26359646 | 1.05867776 | 5.022476 | 5.03498258 | true |
| 8 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 7.22668772 | 0.01037005 | 1.412770 | 4.91556036 | true |
| 8 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.79357057 | -7.51118065 | 0.131090 | 9.39749280 | false |
| 9 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 8.34665855 | 13.85835948 | 999.000000 | 2.09787470 | false |
