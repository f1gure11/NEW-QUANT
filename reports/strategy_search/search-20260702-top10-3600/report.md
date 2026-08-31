# Multi-Strategy Search

Read-only train/test search over independent strategy families.

## Summary

| Metric | Value |
| --- | ---: |
| Tested configs | 360 |
| Passed configs | 1 |
| Passed rate | 0.28% |
| Best test return | 23.119270% |
| Median test return | -2.361022% |
| Mean test return | -3.844887% |
| Median positive holdout-fold rate | 33.33% |

## Top 25

Ranked by train-only selection score. Test columns are holdout validation.

| Rank | Instrument | Strategy | Family | Train Ret % | Train Score | Test Ret % | Test PF | Test DD % | Folds +/N | Passed |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | MU-USDT-SWAP | rsi_revert | mean_reversion | 4.00996319 | 6.50740005 | -4.67310050 | 0.596907 | 5.37506931 | 0/3 | false |
| 2 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 20.11637884 | 6.04403536 | -4.08660367 | 0.911261 | 29.85023262 | 1/3 | false |
| 3 | SNDK-USDT-SWAP | rsi_revert | mean_reversion | 3.38265806 | 4.89790670 | -2.01692179 | 0.924736 | 5.40590824 | 2/3 | false |
| 4 | XAU-USDT-SWAP | ema_cross | trend | 2.43267226 | 2.96295612 | 0.10292771 | 1.309164 | 1.66469566 | 1/3 | false |
| 5 | MU-USDT-SWAP | rsi_revert | mean_reversion | 1.65164866 | 2.55140301 | -2.10883198 | 0.705877 | 4.13006331 | 2/3 | false |
| 6 | SNDK-USDT-SWAP | rsi_revert | mean_reversion | 1.94412681 | 2.30622383 | -3.90338054 | 0.309952 | 5.13086159 | 0/3 | false |
| 7 | BASED-USDT-SWAP | rsi_revert | mean_reversion | 3.94197750 | 2.04032619 | 10.44362662 | 2.124568 | 9.48344937 | 2/3 | false |
| 8 | HYPE-USDT-SWAP | rsi_revert | mean_reversion | 0.35173242 | 0.97685764 | 0.10728844 | 1.483688 | 2.34338644 | 1/3 | false |
| 9 | XAU-USDT-SWAP | donchian_breakout | breakout | -0.17276783 | 0.84256570 | -1.41822084 | 0.866785 | 1.96468861 | 1/3 | false |
| 10 | SNDK-USDT-SWAP | ema_cross | trend | 3.37446245 | 0.52155475 | -0.33690162 | 1.080869 | 7.00744293 | 2/3 | false |
| 11 | XAU-USDT-SWAP | ema_cross | trend | 0.25539669 | 0.48487254 | 0.50658929 | 1.566209 | 1.93765783 | 1/3 | false |
| 12 | BASED-USDT-SWAP | rsi_revert | mean_reversion | 3.16244455 | 0.46122853 | 11.52566022 | 1.771703 | 10.59461241 | 2/3 | false |
| 13 | MU-USDT-SWAP | bollinger_revert | mean_reversion | -0.17838545 | 0.31125752 | -6.83825661 | 0.550766 | 8.08534479 | 0/3 | false |
| 14 | XAU-USDT-SWAP | ema_cross | trend | 0.66223063 | 0.08997551 | 1.25894567 | 2.167676 | 2.08676889 | 2/3 | true |
| 15 | LAB-USDT-SWAP | atr_vol_breakout | breakout | 14.73806907 | -0.10521666 | -19.15118463 | 0.590076 | 37.80062872 | 1/3 | false |
| 16 | XAU-USDT-SWAP | donchian_breakout | breakout | -0.14678344 | -0.76700179 | -0.47673321 | 1.040533 | 2.16115576 | 1/3 | false |
| 17 | MU-USDT-SWAP | bollinger_revert | mean_reversion | -1.26725850 | -0.81827296 | -7.58232593 | 0.534820 | 9.21564309 | 0/3 | false |
| 18 | ETH-USDT-SWAP | rsi_revert | mean_reversion | -0.50115711 | -1.15122574 | -2.70812665 | 0.455816 | 3.01236344 | 0/3 | false |
| 19 | HYPE-USDT-SWAP | atr_vol_breakout | breakout | -0.84900415 | -1.71403614 | 6.56312269 | 2.295081 | 5.14569832 | 2/3 | false |
| 20 | SOL-USDT-SWAP | bollinger_revert | mean_reversion | -2.26966864 | -2.09236050 | -5.45808896 | 0.546397 | 6.94582622 | 0/3 | false |
| 21 | XAU-USDT-SWAP | ema_cross | trend | -1.32351738 | -2.38062544 | 1.69231565 | 2.914222 | 1.49573112 | 2/3 | false |
| 22 | XAU-USDT-SWAP | ema_cross | trend | 0.34351708 | -2.39781544 | -1.05120627 | 0.511492 | 3.17430734 | 0/3 | false |
| 23 | SNDK-USDT-SWAP | rsi_revert | mean_reversion | -2.67654581 | -2.53837398 | -4.48635076 | 0.766806 | 6.95079627 | 1/3 | false |
| 24 | XAU-USDT-SWAP | ema_cross | trend | -1.56635657 | -2.70123305 | 0.73051471 | 1.728941 | 1.49188658 | 2/3 | false |
| 25 | XAU-USDT-SWAP | ema_cross | trend | -1.76679903 | -2.93103431 | 0.83626744 | 1.849785 | 1.75997288 | 2/3 | false |
