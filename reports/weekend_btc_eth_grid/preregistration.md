# Weekend BTC/ETH Static Grid

Status: `preregistered_collecting`<br>
Model: `weekend-btc-eth-grid-v1-20260818`<br>
Forward boundary: `2026-08-18T07:48:08Z`<br>
Paper/live authorization: `false`

## Frozen rule

- Trade BTC-USDT-SWAP and ETH-USDT-SWAP separately on 5-minute candles.
- Open a static grid at Saturday 00:00 UTC using the first complete candle close as the anchor.
- Use eight levels on each side, 100 bps apart, with a fixed outer band of plus/minus 800 bps. Never recenter.
- One-way inventory only. At leverage `L`, each level is `L / 8` times starting equity notional, with a gross cap of `L` times equity.
- If a candle touches both sides, process the adverse side first. A band breach cancels orders and flattens at the next bar open. A 12% equity drawdown also stops the session. No re-entry after a stop.
- Flatten at the first bar at or after Monday 00:00 UTC.
- Evaluate isolated 3x as the base case and isolated 5x as a cost/risk stress case. 10x is excluded by design.

Base costs are 2 bps maker fee, 5 bps taker fee and 2 bps slippage per side. Stress costs are 4, 10 and 5 bps. Funding is taken from the point-in-time funding rows; it is not assumed to be zero.

## Evidence boundary

The repository rules prohibit treating the inspected 2026-06-18-and-later history as new strategy evidence. Therefore the historical figures below are a descriptive volatility check only; they are not a grid backtest, parameter selection, or promotion result. Only complete weekends captured after the boundary count toward evaluation. The minimum is 12 complete weekends, split chronologically 50/25/25 (train/validation/test), with no tuning on validation or test.

At registration time there are zero complete post-boundary weekends for either instrument, so a formal strategy result is not available yet.

## Descriptive volatility check

Using the data-lake 1-hour candles from late 2019 through 2026-08-17, UTC weekend days were quieter than weekdays but still had large tails:

| Instrument | Weekend daily range median / p90 | 48h weekend range median / p90 | 48h range above 10% |
| --- | --- | --- | --- |
| BTC | 2.64% / 6.45% | 4.63% / 10.78% | 11.8% of weekends |
| ETH | 3.88% / 9.69% | 6.59% / 15.63% | 24.1% of weekends |

Recent data does not remove the tail: from 2024-01-01, the largest observed 48h weekend range was 13.89% for BTC and 22.34% for ETH. A 5x position can lose roughly 50% or more of equity on a 10% adverse move before fees if inventory becomes one-sided; a grid without a hard stop is therefore unsuitable for high leverage.

## Decision rule

When 12 complete post-boundary weekends exist, report gross return, net return, stress net return, funding, fills, stop rate, maximum drawdown, worst weekend, and liquidation/gap events. The frozen rule passes only if the held-out test has positive net and stress-net return, base maximum drawdown below 20%, and no unmodeled liquidation. Any failure remains `research_only`; no retuning is permitted.
