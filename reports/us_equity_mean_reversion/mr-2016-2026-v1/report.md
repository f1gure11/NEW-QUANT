# US equity mean-reversion portfolios

Registry: `us-equity-mr-registry-9a7b89fd71f4adeb`. Model: `us-equity-mr-4567b2fa37926c56`. Generated: `2026-08-12T07:23:48Z`.

This is a development-only historical test on an inspected, current-survivor universe. It is not new validation and cannot authorize paper or live trading.

## Frozen design

- Universe: 26 current OKX-mapped US equities with complete 2016-08-08 through 2026-08-07 adjusted-close history.
- Capital and sizing: $1000, 0.01-share increments, leverage 2x through 10x.
- Splits: train 2017-08-08 to 2022-02-02; validation 2022-02-03 to 2024-05-03; test 2024-05-06 to 2026-08-07.
- Costs: gross/no carry, base 10 bps per side + 5% long financing + 1% short borrow, stress 20 bps + 8% + 3%.
- Margin proxy: daily-close cross-margin liquidation at equity <= 5% of gross, plus 50 bps of gross penalty.
- OKX funding is excluded: data-lake coverage begins only in 2026 and cannot be backfilled over this history without temporal bias.

## Training selection

- Eligible training candidates: none.
- Selected portfolio: `none` using training 2x base-cost results only.
- Validation status: `failed_validation_research_only`.

## Base-cost results

| Strategy | Split | Lev | Terminal $ | Return | Ann. | Sharpe | PF | Max DD | Avg gross | Turnover $ | Orders | Liq |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| cross_sectional_5d_reversal | train | 2x | 397.63 | -60.24% | -18.57% | -0.62 | 0.89 | 64.67% | 2.00x | 531262 | 3505 | no |
| cross_sectional_5d_reversal | train | 3x | 194.83 | -80.52% | -30.54% | -0.68 | 0.88 | 83.46% | 3.01x | 635520 | 3518 | no |
| cross_sectional_5d_reversal | train | 4x | 87.67 | -91.23% | -41.86% | -0.72 | 0.87 | 92.89% | 4.02x | 671132 | 3515 | no |
| cross_sectional_5d_reversal | train | 5x | 35.82 | -96.42% | -52.38% | -0.74 | 0.85 | 97.23% | 5.03x | 666726 | 3504 | no |
| cross_sectional_5d_reversal | train | 6x | 13.90 | -98.61% | -61.43% | -0.74 | 0.84 | 98.98% | 6.02x | 641895 | 3504 | no |
| cross_sectional_5d_reversal | train | 7x | 4.95 | -99.50% | -69.35% | -0.74 | 0.83 | 99.64% | 6.96x | 611543 | 3467 | no |
| cross_sectional_5d_reversal | train | 8x | 2.31 | -99.77% | -74.14% | -0.69 | 0.81 | 99.84% | 7.77x | 585832 | 3400 | no |
| cross_sectional_5d_reversal | train | 9x | 0.60 | -99.94% | -80.82% | -0.76 | 0.80 | 99.95% | 8.38x | 567014 | 3283 | no |
| cross_sectional_5d_reversal | train | 10x | 19.22 | -98.08% | -58.54% | -1.15 | 0.77 | 98.39% | 2.81x | 489283 | 962 | yes |
| cross_sectional_5d_reversal | validation | 2x | 463.59 | -53.64% | -29.03% | -1.08 | 0.81 | 62.69% | 2.00x | 239751 | 1766 | no |
| cross_sectional_5d_reversal | validation | 3x | 278.27 | -72.17% | -43.48% | -1.13 | 0.79 | 79.75% | 3.01x | 288176 | 1771 | no |
| cross_sectional_5d_reversal | validation | 4x | 157.60 | -84.24% | -56.14% | -1.15 | 0.77 | 89.62% | 4.03x | 311348 | 1766 | no |
| cross_sectional_5d_reversal | validation | 5x | 84.19 | -91.58% | -66.84% | -1.17 | 0.76 | 94.96% | 5.05x | 320214 | 1765 | no |
| cross_sectional_5d_reversal | validation | 6x | 42.43 | -95.76% | -75.57% | -1.17 | 0.76 | 97.66% | 6.06x | 322709 | 1763 | no |
| cross_sectional_5d_reversal | validation | 7x | 20.92 | -97.91% | -82.18% | -1.16 | 0.75 | 98.95% | 7.06x | 323178 | 1757 | no |
| cross_sectional_5d_reversal | validation | 8x | 9.57 | -99.04% | -87.43% | -1.15 | 0.75 | 99.54% | 8.01x | 321105 | 1745 | no |
| cross_sectional_5d_reversal | validation | 9x | 10.47 | -98.95% | -86.91% | -1.46 | 0.74 | 99.24% | 4.09x | 310833 | 772 | yes |
| cross_sectional_5d_reversal | validation | 10x | 93.56 | -90.64% | -65.24% | -0.67 | 0.75 | 93.37% | 3.34x | 304445 | 587 | yes |
| cross_sectional_5d_reversal | test | 2x | 546.76 | -45.32% | -23.57% | -0.38 | 0.87 | 68.65% | 1.99x | 223445 | 1743 | no |
| cross_sectional_5d_reversal | test | 3x | 345.33 | -65.47% | -37.71% | -0.37 | 0.84 | 84.57% | 2.99x | 261477 | 1746 | no |
| cross_sectional_5d_reversal | test | 4x | 192.69 | -80.73% | -51.96% | -0.38 | 0.81 | 93.07% | 3.99x | 274170 | 1753 | no |
| cross_sectional_5d_reversal | test | 5x | 109.37 | -89.06% | -62.67% | -0.33 | 0.79 | 96.83% | 4.98x | 276441 | 1748 | no |
| cross_sectional_5d_reversal | test | 6x | 49.20 | -95.08% | -73.84% | -0.37 | 0.76 | 98.77% | 5.95x | 271228 | 1745 | no |
| cross_sectional_5d_reversal | test | 7x | 12.47 | -98.75% | -85.80% | -0.79 | 0.74 | 99.42% | 6.70x | 262547 | 1705 | no |
| cross_sectional_5d_reversal | test | 8x | 6.15 | -99.38% | -89.63% | -0.94 | 0.74 | 99.67% | 7.30x | 257006 | 1619 | no |
| cross_sectional_5d_reversal | test | 9x | 77.49 | -92.25% | -67.98% | -0.81 | 0.71 | 92.82% | 2.52x | 213953 | 479 | yes |
| cross_sectional_5d_reversal | test | 10x | 441.19 | -55.88% | -30.53% | -0.78 | 0.56 | 59.34% | 0.55x | 96515 | 97 | yes |
| distance_pairs_252_126 | train | 2x | 954.95 | -4.51% | -1.02% | -0.02 | 0.98 | 26.11% | 1.51x | 48101 | 621 | no |
| distance_pairs_252_126 | train | 3x | 866.93 | -13.31% | -3.13% | -0.07 | 0.97 | 38.37% | 2.28x | 65946 | 627 | no |
| distance_pairs_252_126 | train | 4x | 755.02 | -24.50% | -6.07% | -0.11 | 0.95 | 49.66% | 3.06x | 78456 | 623 | no |
| distance_pairs_252_126 | train | 5x | 640.28 | -35.97% | -9.46% | -0.14 | 0.93 | 59.45% | 3.86x | 86536 | 628 | no |
| distance_pairs_252_126 | train | 6x | 528.68 | -47.13% | -13.24% | -0.16 | 0.91 | 67.86% | 4.67x | 90534 | 624 | no |
| distance_pairs_252_126 | train | 7x | 428.63 | -57.14% | -17.20% | -0.16 | 0.90 | 74.99% | 5.50x | 91442 | 631 | no |
| distance_pairs_252_126 | train | 8x | 337.05 | -66.30% | -21.52% | -0.17 | 0.88 | 80.93% | 6.36x | 89669 | 627 | no |
| distance_pairs_252_126 | train | 9x | 257.40 | -74.26% | -26.09% | -0.16 | 0.86 | 85.82% | 7.25x | 85970 | 631 | no |
| distance_pairs_252_126 | train | 10x | 190.63 | -80.94% | -30.88% | -1.06 | 0.65 | 82.31% | 1.39x | 32544 | 85 | yes |
| distance_pairs_252_126 | validation | 2x | 1060.23 | 6.02% | 2.64% | 0.26 | 1.04 | 15.93% | 1.16x | 22729 | 219 | no |
| distance_pairs_252_126 | validation | 3x | 1073.37 | 7.34% | 3.21% | 0.26 | 1.03 | 23.96% | 1.76x | 34540 | 221 | no |
| distance_pairs_252_126 | validation | 4x | 1068.61 | 6.86% | 3.00% | 0.24 | 1.02 | 32.08% | 2.38x | 46298 | 223 | no |
| distance_pairs_252_126 | validation | 5x | 1054.26 | 5.43% | 2.38% | 0.24 | 1.01 | 40.07% | 3.01x | 57910 | 227 | no |
| distance_pairs_252_126 | validation | 6x | 1033.68 | 3.37% | 1.49% | 0.25 | 1.01 | 47.72% | 3.67x | 69325 | 227 | no |
| distance_pairs_252_126 | validation | 7x | 1006.90 | 0.69% | 0.31% | 0.26 | 1.00 | 55.02% | 4.35x | 80430 | 226 | no |
| distance_pairs_252_126 | validation | 8x | 978.23 | -2.18% | -0.98% | 0.28 | 1.00 | 61.94% | 5.07x | 91318 | 226 | no |
| distance_pairs_252_126 | validation | 9x | 945.22 | -5.48% | -2.48% | 0.30 | 0.99 | 68.50% | 5.83x | 101842 | 227 | no |
| distance_pairs_252_126 | validation | 10x | 390.52 | -60.95% | -34.25% | -0.83 | 0.82 | 73.55% | 2.70x | 47333 | 88 | yes |
| distance_pairs_252_126 | test | 2x | 743.00 | -25.70% | -12.39% | -0.70 | 0.86 | 43.41% | 1.60x | 27264 | 401 | no |
| distance_pairs_252_126 | test | 3x | 607.85 | -39.21% | -19.88% | -0.74 | 0.85 | 58.76% | 2.43x | 37964 | 421 | no |
| distance_pairs_252_126 | test | 4x | 481.36 | -51.86% | -27.79% | -0.77 | 0.84 | 70.49% | 3.26x | 46812 | 417 | no |
| distance_pairs_252_126 | test | 5x | 372.90 | -62.71% | -35.54% | -0.78 | 0.83 | 79.16% | 4.12x | 54650 | 418 | no |
| distance_pairs_252_126 | test | 6x | 284.38 | -71.56% | -42.87% | -0.78 | 0.82 | 85.63% | 4.99x | 61512 | 415 | no |
| distance_pairs_252_126 | test | 7x | 209.15 | -79.09% | -50.18% | -0.78 | 0.82 | 90.25% | 5.88x | 67914 | 419 | no |
| distance_pairs_252_126 | test | 8x | 148.07 | -85.19% | -57.28% | -0.78 | 0.82 | 93.60% | 6.80x | 73791 | 419 | no |
| distance_pairs_252_126 | test | 9x | 102.35 | -89.77% | -63.75% | -0.76 | 0.82 | 95.91% | 7.75x | 79499 | 420 | no |
| distance_pairs_252_126 | test | 10x | 159.69 | -84.03% | -55.81% | -0.70 | 0.83 | 85.92% | 5.22x | 78825 | 209 | yes |
| market_residual_5d_reversal | train | 2x | 496.06 | -50.39% | -14.46% | -0.46 | 0.91 | 58.85% | 2.00x | 556209 | 3529 | no |
| market_residual_5d_reversal | train | 3x | 274.05 | -72.59% | -25.06% | -0.52 | 0.89 | 79.16% | 3.01x | 675304 | 3532 | no |
| market_residual_5d_reversal | train | 4x | 135.84 | -86.42% | -35.90% | -0.56 | 0.88 | 90.50% | 4.02x | 722263 | 3532 | no |
| market_residual_5d_reversal | train | 5x | 62.10 | -93.79% | -46.16% | -0.58 | 0.86 | 96.00% | 5.03x | 726642 | 3534 | no |
| market_residual_5d_reversal | train | 6x | 26.51 | -97.35% | -55.46% | -0.59 | 0.85 | 98.44% | 6.03x | 710449 | 3524 | no |
| market_residual_5d_reversal | train | 7x | 9.02 | -99.10% | -64.97% | -0.63 | 0.84 | 99.51% | 6.98x | 687687 | 3505 | no |
| market_residual_5d_reversal | train | 8x | 3.69 | -99.63% | -71.30% | -0.61 | 0.83 | 99.79% | 7.84x | 669218 | 3456 | no |
| market_residual_5d_reversal | train | 9x | 18.37 | -98.16% | -58.96% | -0.74 | 0.81 | 98.63% | 5.07x | 638455 | 1958 | yes |
| market_residual_5d_reversal | train | 10x | 8.08 | -99.19% | -65.82% | -0.76 | 0.81 | 99.41% | 5.64x | 647245 | 1955 | yes |
| market_residual_5d_reversal | validation | 2x | 576.49 | -42.35% | -21.78% | -0.78 | 0.84 | 53.59% | 2.00x | 249435 | 1769 | no |
| market_residual_5d_reversal | validation | 3x | 390.53 | -60.95% | -34.25% | -0.83 | 0.81 | 71.38% | 3.01x | 301519 | 1766 | no |
| market_residual_5d_reversal | validation | 4x | 252.66 | -74.73% | -45.86% | -0.85 | 0.78 | 83.06% | 4.03x | 325725 | 1771 | no |
| market_residual_5d_reversal | validation | 5x | 159.18 | -84.08% | -55.94% | -0.84 | 0.76 | 90.27% | 5.05x | 334365 | 1767 | no |
| market_residual_5d_reversal | validation | 6x | 95.71 | -90.43% | -64.88% | -0.83 | 0.74 | 94.64% | 6.07x | 334486 | 1766 | no |
| market_residual_5d_reversal | validation | 7x | 54.52 | -94.55% | -72.68% | -0.82 | 0.73 | 97.21% | 7.09x | 332306 | 1758 | no |
| market_residual_5d_reversal | validation | 8x | 28.90 | -97.11% | -79.42% | -0.80 | 0.72 | 98.64% | 8.11x | 330210 | 1758 | no |
| market_residual_5d_reversal | validation | 9x | 19.91 | -98.01% | -82.57% | -1.52 | 0.70 | 98.66% | 4.04x | 309831 | 779 | yes |
| market_residual_5d_reversal | validation | 10x | 10.29 | -98.97% | -87.01% | -1.52 | 0.70 | 99.34% | 4.51x | 321299 | 779 | yes |
| market_residual_5d_reversal | test | 2x | 669.68 | -33.03% | -16.35% | -0.25 | 0.90 | 65.34% | 1.99x | 222163 | 1743 | no |
| market_residual_5d_reversal | test | 3x | 474.93 | -52.51% | -28.22% | -0.25 | 0.86 | 81.29% | 3.00x | 261945 | 1743 | no |
| market_residual_5d_reversal | test | 4x | 312.82 | -68.72% | -40.39% | -0.23 | 0.83 | 90.22% | 4.00x | 279445 | 1745 | no |
| market_residual_5d_reversal | test | 5x | 191.74 | -80.83% | -52.07% | -0.21 | 0.80 | 95.11% | 5.00x | 285513 | 1739 | no |
| market_residual_5d_reversal | test | 6x | 104.17 | -89.58% | -63.47% | -0.21 | 0.78 | 97.70% | 5.98x | 288642 | 1732 | no |
| market_residual_5d_reversal | test | 7x | 55.90 | -94.41% | -72.31% | -0.19 | 0.77 | 98.98% | 6.94x | 292284 | 1725 | no |
| market_residual_5d_reversal | test | 8x | 26.64 | -97.34% | -80.09% | -0.27 | 0.76 | 99.55% | 7.71x | 297073 | 1699 | no |
| market_residual_5d_reversal | test | 9x | 79.12 | -92.09% | -67.68% | -0.89 | 0.76 | 94.49% | 2.53x | 275551 | 482 | yes |
| market_residual_5d_reversal | test | 10x | 51.75 | -94.83% | -73.25% | -0.87 | 0.77 | 96.53% | 2.83x | 293426 | 482 | yes |

## Cost comparison at 2x

| Strategy | Split | Gross | Base | Stress | Base costs $ | Stress costs $ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| cross_sectional_5d_reversal | train | -14.70% | -60.24% | -82.44% | 566.96 | 826.13 |
| cross_sectional_5d_reversal | validation | -31.51% | -53.64% | -69.23% | 255.74 | 446.22 |
| cross_sectional_5d_reversal | test | -19.79% | -45.32% | -63.45% | 238.77 | 417.53 |
| market_residual_5d_reversal | train | 7.43% | -50.39% | -78.05% | 593.24 | 864.37 |
| market_residual_5d_reversal | validation | -15.17% | -42.35% | -61.86% | 266.02 | 459.55 |
| market_residual_5d_reversal | test | -2.45% | -33.03% | -54.87% | 237.65 | 415.82 |
| distance_pairs_252_126 | train | 4.70% | -4.51% | -15.64% | 80.71 | 180.02 |
| distance_pairs_252_126 | validation | 9.87% | 6.02% | 1.19% | 36.12 | 83.72 |
| distance_pairs_252_126 | test | -21.62% | -25.70% | -30.61% | 43.46 | 99.51 |

## Interpretation limits

- The universe is selected using current contract availability and complete surviving price histories; delisted names and later listings are absent.
- Adjusted underlying closes do not reproduce OKX contract basis, intraday path, spreads, depth, funding, margin tiers, or liquidation marks.
- Every portfolio and leverage row is reported. Validation/test results must not be used to alter thresholds, pairs, symbols, or choose a test-only winner.
- In liquidated paths, a higher-cost scenario can retain more terminal cash because it breaches the daily-close margin proxy earlier and stops taking risk. Such non-monotonic terminal values are liquidation timing artifacts, not evidence that higher costs help.
- A positive row remains research-only. New forward data and explicit approval are required before paper or live use.
