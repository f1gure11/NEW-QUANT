# Pure-stock factor Monte Carlo (development only)

Registry: `qqq-pure-stock-mc-registry-6c8f1e715a78797a`. Generated: `2026-08-11T16:52:41Z`.

This is a risk stress test on inspected history, not new validation and not paper/live authorization. The book has no QQQ or SPY core. Locked factor weights are normalized to 100% gross, then leverage sets notional gross.

## Frozen model and data

- Universe: 29 validated equity mappings; DASH crypto is excluded.
- Source: 24 completed monthly signal/return episodes, 501 underlying daily closes.
- Monte Carlo: 4000 paths x 24 sampled months, seed 20260811.
- Funding proxy: 50 synchronized OKX daily vectors from 2026-06-23 through 2026-08-11; missing symbol-days are zero and trading-day funding is multiplied by 1.4.
- Position increment: synthetic 0.01 underlying share with contract value 1. This overrides real ctVal/lotSz/minSz and is not executable sizing proof.
- Exit trigger: completed daily close; execution: next completed daily close. Intraday touches and true OKX liquidation marks are unavailable.

## Monte Carlo results

| Exit | Lev | Cost/side | Actual gross | Gross P50 | Net P1 | Net P5 | Net P50 | Net P95 | Net P99 | Ruin | Liq proxy | DD>=50 | DD>=90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fixed_take_profit_10pct | 2x | 10 bps | 1.31x | 7.72% | -30.55% | -22.54% | 4.28% | 42.48% | 62.73% | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_take_profit_10pct | 2x | 20 bps | 1.30x | 7.38% | -34.13% | -25.61% | -0.79% | 36.18% | 54.25% | 0.00% | 0.00% | 0.00% | 0.00% |
| fixed_take_profit_10pct | 3x | 10 bps | 2.24x | 17.74% | -43.56% | -31.34% | 11.48% | 87.02% | 137.54% | 0.00% | 0.00% | 1.90% | 0.00% |
| fixed_take_profit_10pct | 3x | 20 bps | 2.22x | 16.59% | -47.68% | -36.29% | 2.75% | 72.50% | 113.40% | 0.00% | 0.00% | 3.55% | 0.00% |
| fixed_take_profit_10pct | 5x | 10 bps | 4.17x | 36.54% | -64.57% | -49.29% | 23.24% | 232.01% | 388.23% | 0.00% | 0.00% | 28.65% | 0.00% |
| fixed_take_profit_10pct | 5x | 20 bps | 4.13x | 33.59% | -69.11% | -56.46% | 5.92% | 179.98% | 307.11% | 0.00% | 0.00% | 36.88% | 0.00% |
| fixed_take_profit_10pct | 10x | 10 bps | 8.98x | 59.03% | -91.71% | -82.27% | 24.84% | 952.67% | 2191.11% | 0.00% | 0.00% | 92.95% | 8.05% |
| fixed_take_profit_10pct | 10x | 20 bps | 8.86x | 49.34% | -93.89% | -87.36% | -14.01% | 644.06% | 1544.73% | 0.00% | 0.00% | 95.30% | 12.90% |
| trailing_profit_6pct_4pct | 2x | 10 bps | 1.33x | 18.29% | -28.56% | -18.93% | 14.32% | 65.04% | 93.48% | 0.00% | 0.00% | 0.03% | 0.00% |
| trailing_profit_6pct_4pct | 2x | 20 bps | 1.32x | 17.32% | -32.09% | -22.44% | 8.52% | 56.23% | 82.06% | 0.00% | 0.00% | 0.05% | 0.00% |
| trailing_profit_6pct_4pct | 3x | 10 bps | 2.28x | 36.94% | -40.08% | -25.17% | 29.35% | 136.05% | 203.61% | 0.00% | 0.00% | 1.90% | 0.00% |
| trailing_profit_6pct_4pct | 3x | 20 bps | 2.26x | 34.67% | -44.39% | -32.10% | 18.15% | 116.18% | 177.03% | 0.00% | 0.00% | 3.35% | 0.00% |
| trailing_profit_6pct_4pct | 5x | 10 bps | 4.27x | 78.82% | -61.29% | -42.53% | 61.54% | 388.91% | 685.39% | 0.00% | 0.00% | 29.12% | 0.00% |
| trailing_profit_6pct_4pct | 5x | 20 bps | 4.23x | 69.84% | -66.06% | -51.39% | 35.96% | 318.27% | 534.37% | 0.00% | 0.00% | 35.75% | 0.00% |
| trailing_profit_6pct_4pct | 10x | 10 bps | 9.18x | 156.26% | -90.97% | -80.72% | 105.44% | 2060.66% | 5285.27% | 0.00% | 0.00% | 93.83% | 8.62% |
| trailing_profit_6pct_4pct | 10x | 20 bps | 9.09x | 127.76% | -93.04% | -86.43% | 36.96% | 1450.40% | 3718.22% | 0.00% | 0.00% | 95.45% | 13.05% |

`Liq proxy` uses cross-margin liquidation when completed-close equity is at or below 5% of gross notional, plus a 50 bps gross penalty. Actual OKX tiering, mark price, intraday liquidation, ADL, and insurance behavior can differ materially.

## Activity and friction

| Exit | Lev | Cost/side | Positions | Stops | Profit exits | Cost | Funding PnL | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fixed_take_profit_10pct | 2x | 10 bps | 16.1 | 78.3 | 135.0 | 4.87 USDT | 1.33 USDT | 4871 USDT |
| fixed_take_profit_10pct | 2x | 20 bps | 15.9 | 77.5 | 133.4 | 9.44 USDT | 1.29 USDT | 4722 USDT |
| fixed_take_profit_10pct | 3x | 10 bps | 19.4 | 91.5 | 163.7 | 8.82 USDT | 2.25 USDT | 8822 USDT |
| fixed_take_profit_10pct | 3x | 20 bps | 19.1 | 90.4 | 161.2 | 16.77 USDT | 2.14 USDT | 8385 USDT |
| fixed_take_profit_10pct | 5x | 10 bps | 22.4 | 105.1 | 191.8 | 18.75 USDT | 4.38 USDT | 18752 USDT |
| fixed_take_profit_10pct | 5x | 20 bps | 22.0 | 103.3 | 188.1 | 34.23 USDT | 4.02 USDT | 17114 USDT |
| fixed_take_profit_10pct | 10x | 10 bps | 24.6 | 116.3 | 213.0 | 58.58 USDT | 12.29 USDT | 58577 USDT |
| fixed_take_profit_10pct | 10x | 20 bps | 24.0 | 113.1 | 206.6 | 96.08 USDT | 10.18 USDT | 48039 USDT |
| trailing_profit_6pct_4pct | 2x | 10 bps | 16.6 | 75.8 | 160.3 | 5.37 USDT | 1.24 USDT | 5366 USDT |
| trailing_profit_6pct_4pct | 2x | 20 bps | 16.4 | 75.0 | 158.2 | 10.38 USDT | 1.21 USDT | 5191 USDT |
| trailing_profit_6pct_4pct | 3x | 10 bps | 19.9 | 89.2 | 194.0 | 10.10 USDT | 2.12 USDT | 10098 USDT |
| trailing_profit_6pct_4pct | 3x | 20 bps | 19.7 | 88.0 | 191.2 | 19.14 USDT | 2.03 USDT | 9569 USDT |
| trailing_profit_6pct_4pct | 5x | 10 bps | 23.1 | 102.9 | 223.2 | 23.34 USDT | 4.30 USDT | 23337 USDT |
| trailing_profit_6pct_4pct | 5x | 20 bps | 22.7 | 101.2 | 219.5 | 42.25 USDT | 3.94 USDT | 21124 USDT |
| trailing_profit_6pct_4pct | 10x | 10 bps | 25.3 | 113.2 | 243.9 | 92.96 USDT | 14.60 USDT | 92961 USDT |
| trailing_profit_6pct_4pct | 10x | 20 bps | 24.7 | 110.5 | 238.2 | 149.47 USDT | 11.92 USDT | 74736 USDT |

## Source stability (no leverage, exits, costs, or funding)

| Split | Episodes | Return | Annualized | Volatility | Max DD | Positive months |
|---|---:|---:|---:|---:|---:|---:|
| train | 12 | 0.10% | 0.10% | 11.58% | 10.87% | 50.00% |
| validation | 6 | 28.26% | 64.51% | 13.13% | 4.28% | 83.33% |
| test | 6 | 17.21% | 37.74% | 15.99% | 6.30% | 66.67% |

## Reading the result

- Gross return is price PnL before transaction cost, funding, and liquidation penalty. Net return includes all modeled items.
- P1/P5 are downside percentiles across the same frozen random paths used for every scenario. They are empirical bootstrap tails, not guarantees.
- A leg stopped or profit-exited remains flat until the next sampled monthly factor rebalance.
- The direct chronological replay in `scenario_rows.csv` is descriptive only and uses the mean available funding vector; it is not a separate validation sample.
- Parameters must not be changed after reading this report and then retested on the same source window.
