# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 954 |
| Passed window rows | 205 |
| Unique aggregate candidates | 146 |
| Passed aggregate candidates | 0 |
| Median selected test return | -1.294414% |
| Mean selected test return | -0.851483% |
| Best aggregate return | 147.419692% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | SPCX-USDT-SWAP | time_series_momentum | all | 22 | 40.9091 | 147.41969214 | 1.99477109 | -9.35009431 | false |
| 2 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 10 | 20.0000 | 95.42223097 | 0.19082618 | -4.95087820 | false |
| 3 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 12 | 25.0000 | 93.26662866 | 0.69981179 | -8.93093658 | false |
| 4 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 14 | 64.2857 | 61.57955704 | 1.64739792 | -8.90888892 | false |
| 5 | EDGE-USDT-SWAP | time_series_momentum | all | 8 | 37.5000 | 62.80069569 | -0.09181131 | -6.37297144 | false |
| 6 | EDGE-USDT-SWAP | time_series_momentum | all | 11 | 45.4545 | 42.92508026 | 0.21455105 | -8.33871601 | false |
| 7 | ZEC-USDT-SWAP | time_series_momentum | all | 9 | 66.6667 | 32.13283958 | 1.66739175 | -12.95145521 | false |
| 8 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 14 | 50.0000 | 33.53950675 | 1.38975493 | -12.41750205 | false |
| 9 | SOXL-USDT-SWAP | time_series_momentum | all | 21 | 19.0476 | 30.70519365 | -0.35666351 | -18.98729183 | false |
| 10 | LAB-USDT-SWAP | time_series_momentum | all | 5 | 0.0000 | 41.30822162 | -8.61196938 | -34.42291626 | false |
| 11 | EDGE-USDT-SWAP | time_series_momentum | all | 8 | 37.5000 | 24.67872196 | 4.36787319 | -5.91247590 | false |
| 12 | ZEC-USDT-SWAP | time_series_momentum | all | 11 | 45.4545 | 19.53461342 | 0.24522998 | -10.26011391 | false |
| 13 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 9 | 33.3333 | 17.30781136 | -0.53180565 | -10.17436586 | false |
| 14 | LAB-USDT-SWAP | multi_horizon_momentum | all | 7 | 0.0000 | 37.49180113 | 34.54506428 | -54.53383417 | false |
| 15 | MU-USDT-SWAP | multi_horizon_momentum | all | 20 | 30.0000 | 13.82618626 | 0.23670802 | -13.34195743 | false |
| 16 | SKHYNIX-USDT-SWAP | time_series_momentum | all | 4 | 0.0000 | 16.58703962 | 3.83771683 | -0.31098633 | false |
| 17 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 1 | 100.0000 | 0.61032551 | 0.61032551 | 0.61032551 | false |
| 18 | SPCX-USDT-SWAP | time_series_momentum | all | 14 | 21.4286 | 7.35679521 | 0.48234481 | -4.88338539 | false |
| 19 | ZEC-USDT-SWAP | time_series_momentum | all | 4 | 50.0000 | 5.89410623 | 1.25503994 | -2.78089283 | false |
| 20 | ETH-USDT-SWAP | time_series_momentum | all | 5 | 20.0000 | 8.10060490 | -0.24506366 | -2.16868524 | false |
| 21 | MU-USDT-SWAP | time_series_momentum | all | 10 | 30.0000 | 7.31989057 | -1.41945816 | -6.70631264 | false |
| 22 | SOXL-USDT-SWAP | time_series_momentum | all | 18 | 22.2222 | 9.72265802 | 1.21713897 | -28.54129864 | false |
| 23 | SOL-USDT-SWAP | multi_horizon_momentum | all | 19 | 26.3158 | 4.08796202 | -0.78010621 | -6.39584106 | false |
| 24 | ETH-USDT-SWAP | multi_horizon_momentum | all | 11 | 9.0909 | 4.46661382 | -0.72484305 | -2.54477715 | false |
| 25 | SKHYNIX-USDT-SWAP | multi_horizon_momentum | all | 2 | 50.0000 | -0.19832226 | 0.01752937 | -4.81345471 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.77444753 | 0.18479402 | 1.664439 | 1.74205447 | true |
| 1 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 0.35651987 | -0.24230489 | 1.281226 | 2.16094289 | false |
| 1 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.27252337 | 0.54485901 | 2.592381 | 1.38891580 | true |
| 2 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 3.12212192 | -2.45031924 | 0.000000 | 2.57392332 | false |
| 2 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.06785323 | -1.01295040 | 0.395320 | 1.49091205 | false |
| 2 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.01896774 | -4.29227352 | 0.000000 | 4.41354368 | false |
| 3 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.08227019 | -7.42036311 | 0.000000 | 7.85813450 | false |
| 4 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.34215549 | 1.60215171 | 999.000000 | 1.03895511 | false |
| 5 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3.63011561 | -2.19954692 | 0.072334 | 3.87810039 | false |
| 5 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.52797890 | -2.57413765 | 0.042293 | 4.24626200 | false |
| 5 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 1.43212388 | -0.82297432 | 0.000000 | 3.38478778 | false |
| 6 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.15406420 | -1.80712460 | 0.379053 | 3.65816459 | false |
| 10 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 1.94747886 | -0.33234215 | 0.938220 | 2.46235986 | false |
| 11 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.74071255 | -0.00931367 | 1.151477 | 1.45778608 | false |
| 12 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 0.56791655 | -2.93975360 | 0.017449 | 3.71827049 | false |
| 13 | 1 | BTC-USDT-SWAP | time_series_momentum | all | 3.47588619 | -1.52411356 | 0.407646 | 2.96280538 | false |
| 13 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 1.75644600 | 0.54199408 | 4.574406 | 1.27687265 | true |
| 13 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.62147342 | 0.22967082 | 3.052066 | 1.31320277 | true |
| 14 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.72981804 | -0.36067835 | 0.981777 | 2.06740740 | false |
| 14 | 2 | BTC-USDT-SWAP | time_series_momentum | all | 2.39672106 | -3.10984416 | 0.127197 | 3.07377308 | false |
| 14 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 0.71888276 | -3.77559600 | 0.264906 | 3.68464198 | false |
| 15 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.61590917 | -2.29671765 | 0.000000 | 2.82665346 | false |
| 15 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.36123393 | -5.06740383 | 0.000000 | 5.38581734 | false |
| 15 | 3 | BTC-USDT-SWAP | time_series_momentum | all | 0.02545787 | -4.52485491 | 0.045089 | 4.84517223 | false |
| 23 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.22836167 | -5.19376616 | 0.000120 | 5.48233027 | false |
