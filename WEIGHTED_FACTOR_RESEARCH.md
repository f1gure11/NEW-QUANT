# BTC/ETH Non-Order-Flow-Core Weighted Factor Research

This read-only experiment tests whether changing the signal mix away from an
order-flow core improves the existing BTC/ETH result. Candidate signals assign
at least 85% total weight to price momentum, price mean reversion, and range
breakout. The combined depth/trade/OFI factor is capped at 15%.

The first 50% of common history selects a predeclared weight profile, fast and
slow lookback, threshold, take-profit, stop-loss, and maximum holding period.
The next 25% is validation and the final 25% is an exploratory reused-history
test. Entries and exits use executable bid/ask quotes with two-sided taker fees
and adverse slippage. The test is unleveraged and allows only one position per
instrument.

Run:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python weighted_factor_research.py \
  --output-dir btc-eth-20260807
```

This experiment does not load `.env`, use private account endpoints, start a
service, or place an order. Because the period overlaps previous research, a
positive result would still require fresh forward data before paper trading.

## 2026-08-07 Result

The training-selected profile used 55% multi-horizon momentum, 45% range
breakout, and 0% order flow. It improved the training median to +0.2705%, but
did not persist: validation was -0.7362%, the reused test was -1.5150%, and the
full-period median was -2.1683%. BTC and ETH both lost money in the reused test,
and cost/latency stress made the result worse. The experiment therefore did
not turn the strategy profitable and remains research-only.

Report: `reports/weighted_factors/btc-eth-20260807/report.md`.
