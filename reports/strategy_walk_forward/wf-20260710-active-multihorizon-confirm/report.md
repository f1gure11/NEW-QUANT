# Strategy Walk-Forward

Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.

## Summary

| Metric | Value |
| --- | ---: |
| Selected window rows | 326 |
| Passed window rows | 56 |
| Unique aggregate candidates | 56 |
| Passed aggregate candidates | 0 |
| Median selected test return | -3.988527% |
| Mean selected test return | -3.739177% |
| Best aggregate return | -2.514857% |

## Top Aggregates

| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | MU-USDT-SWAP | multi_horizon_momentum | all | 3 | 33.3333 | -2.51485712 | 0.46868310 | -4.53885653 | false |
| 2 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 3 | 33.3333 | -7.40818856 | -2.08309480 | -8.63922947 | false |
| 3 | ZEC-USDT-SWAP | multi_horizon_momentum | all | 4 | 25.0000 | -4.86492896 | -4.01864672 | -8.59058277 | false |
| 4 | SKHYNIX-USDT-SWAP | multi_horizon_momentum | all | 3 | 33.3333 | -8.62558788 | -2.03233067 | -7.46376019 | false |
| 5 | XAU-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -3.78721109 | -3.78721109 | -3.78721109 | false |
| 6 | BTC-USDT-SWAP | multi_horizon_momentum | all | 4 | 0.0000 | -5.97078321 | -1.66173992 | -5.90640062 | false |
| 7 | ETH-USDT-SWAP | multi_horizon_momentum | all | 7 | 28.5714 | -13.38930829 | -2.95370229 | -5.33632349 | false |
| 8 | XAU-USDT-SWAP | multi_horizon_momentum | all | 3 | 0.0000 | -10.03415086 | -2.66358108 | -5.90733413 | false |
| 9 | SOL-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -8.18086210 | -4.17730163 | -4.45249893 | false |
| 10 | ETH-USDT-SWAP | multi_horizon_momentum | all | 12 | 41.6667 | -19.44555076 | -1.68524952 | -8.70978131 | false |
| 11 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4 | 0.0000 | -11.47793373 | -2.68542419 | -5.29475153 | false |
| 12 | SOL-USDT-SWAP | multi_horizon_momentum | all | 7 | 28.5714 | -18.21551852 | -2.53615546 | -7.68977802 | false |
| 13 | SOL-USDT-SWAP | multi_horizon_momentum | all | 4 | 25.0000 | -16.04940379 | -5.69922961 | -9.20792333 | false |
| 14 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -7.71060213 | -7.71060213 | -7.71060213 | false |
| 15 | SOXL-USDT-SWAP | multi_horizon_momentum | all | 20 | 30.0000 | -21.55925475 | -1.52505521 | -24.39353756 | false |
| 16 | SOL-USDT-SWAP | multi_horizon_momentum | all | 5 | 20.0000 | -19.14802219 | -7.09859693 | -8.11811758 | false |
| 17 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -10.21092429 | -10.21092429 | -10.21092429 | false |
| 18 | EDGE-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -12.15587504 | -6.26417329 | -7.67580779 | false |
| 19 | BTC-USDT-SWAP | multi_horizon_momentum | all | 3 | 0.0000 | -15.14538436 | -2.98476965 | -9.93796829 | false |
| 20 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 5 | 40.0000 | -20.69489460 | -6.86264260 | -10.02164162 | false |
| 21 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 5 | 20.0000 | -17.95744399 | -5.19780052 | -6.98952937 | false |
| 22 | SNDK-USDT-SWAP | multi_horizon_momentum | all | 5 | 20.0000 | -20.24492245 | -5.97240665 | -7.83433110 | false |
| 23 | SPCX-USDT-SWAP | multi_horizon_momentum | all | 1 | 0.0000 | -10.17584196 | -10.17584196 | -10.17584196 | false |
| 24 | MU-USDT-SWAP | multi_horizon_momentum | all | 2 | 0.0000 | -16.00959154 | -8.23053721 | -12.98379448 | false |
| 25 | SOL-USDT-SWAP | multi_horizon_momentum | all | 12 | 25.0000 | -27.34526516 | -2.42342189 | -10.66172436 | false |

## Top Window Selections

| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |
| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.93585585 | -1.89952364 | 0.105896 | 1.95752620 | false |
| 1 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.99824004 | -2.98476965 | 0.085004 | 2.98615885 | false |
| 2 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.53804255 | -1.42395621 | 0.354360 | 2.43815795 | false |
| 11 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 0.94678902 | 3.33804381 | 14.987583 | 4.77131792 | false |
| 12 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 7.85544689 | -5.90640062 | 0.384252 | 9.56801729 | false |
| 12 | 2 | BTC-USDT-SWAP | multi_horizon_momentum | all | 5.48220073 | -2.88332356 | 0.716060 | 6.66112193 | false |
| 12 | 3 | BTC-USDT-SWAP | multi_horizon_momentum | all | 2.26006674 | -7.71060213 | 0.275424 | 11.34248898 | false |
| 13 | 1 | BTC-USDT-SWAP | multi_horizon_momentum | all | 1.59156125 | -9.93796829 | 0.000000 | 12.11507283 | false |
| 1 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.32099552 | -2.77109819 | 0.218816 | 4.54059762 | false |
| 1 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.60077647 | -3.50205648 | 0.144811 | 4.32359321 | false |
| 2 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.34036154 | 1.46072505 | 4.847514 | 1.51719376 | true |
| 2 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.41301307 | 0.64490533 | 3.009735 | 1.51719376 | true |
| 3 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.45976842 | -4.25393341 | 0.277943 | 4.85957429 | false |
| 3 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.92596156 | -3.21755702 | 0.329939 | 3.82975349 | false |
| 11 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.72405018 | -1.29201393 | 0.690804 | 7.05861077 | false |
| 12 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.61646690 | 2.16902171 | 1.535544 | 6.51037250 | true |
| 12 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.74046761 | -1.86879190 | 0.903611 | 8.30492667 | false |
| 13 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 5.91962009 | 0.57943063 | 1.926172 | 4.94336026 | true |
| 13 | 2 | ETH-USDT-SWAP | multi_horizon_momentum | all | 2.34196199 | -3.93518215 | 0.408169 | 8.41000715 | false |
| 13 | 3 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.03448499 | -5.29475153 | 0.378945 | 9.14979853 | false |
| 14 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 4.48921899 | -0.59940086 | 1.008444 | 5.50883712 | false |
| 16 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 7.27623043 | -3.39678803 | 0.373758 | 6.15711676 | false |
| 24 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 1.40813645 | -3.44872126 | 0.363538 | 5.59339278 | false |
| 25 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 0.94219100 | -8.70978131 | 0.034975 | 9.07062712 | false |
| 33 | 1 | ETH-USDT-SWAP | multi_horizon_momentum | all | 6.18693374 | -5.33632349 | 0.000000 | 5.68069771 | false |
