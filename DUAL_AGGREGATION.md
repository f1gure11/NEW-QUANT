# Dual-Book Aggregation Research

> Status: abandoned by user on 2026-08-06 after repeated negative validation,
> test and inventory-exit experiments. Retained only as reproducible evidence;
> do not tune, paper trade or deploy.

This experiment runs two independent layered books in one marked-to-market
account:

- the long book adds only at its anchor and lower levels;
- the short book adds only at its anchor and higher levels;
- every layer exits at the nearer of its fixed take-profit or the preceding
  ladder level;
- the two books independently reanchor when flat;
- half of the total gross-notional budget is reserved for each direction, so
  hedge mode does not silently double configured leverage.

Run the semiconductor walk-forward, leverage and path-shape experiment using
the existing public candle caches:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python dual_aggregation_research.py \
  --output-dir semis-dual-volatility-20260806
```

The report includes train-only parameter selection, validation/final/full
segments, cost stress, worst up/down windows, synthetic paths and a three-day
rolling decomposition. Path efficiency is an ex-post explanatory metric only;
it is not used as a direction forecast.

The simulator accounts for shared equity, fees, funding, tick/lot/minimum
sizes, current-equity gross and per-side caps, side/account stops, terminal
liquidation cost and maintenance-margin liquidation. Existing risk exits are
checked before profitable intrabar fills, and a new lot cannot take profit in
the candle in which it entered.

The simulator also supports an explicit absolute-net-notional cap, per-lot
inventory expiry and a point-in-time entry-enable map. Disabled bars are
reduce-risk periods: take-profit, expiry, stops and liquidation remain active,
but no new aggregation lot can open.

Optional inventory-exit research controls support two additional mechanisms:

- aged equal-quantity long/short lots can close together at the current bar
  open only when their combined PnL remains positive after two taker fees and
  adverse slippage;
- prior completed take-profit exit gains can be held as single-use exit credit
  for aged inventory, but only when the exit reduces absolute net exposure;
- staged reduction can close a configured fraction of the remaining lot at
  deterministic age intervals before mandatory expiry.

All such exits use only information available at the bar open, pay taker costs,
and block same-candle re-entry on the affected side. The simulator keeps these
features disabled by default.

This workflow is public-data and research-only. It does not load `.env`, read
an account, start a service or place an order.
