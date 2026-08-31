# GEX And Delta-Neutral Feasibility Research

The point-in-time experiment distinguishes two ideas that are often both
called "delta neutral":

1. Equal or near-equal long/short linear contracts have near-zero first-order
   delta but zero gamma. This is an inventory/grid strategy.
2. Long options provide positive gamma; spot or perpetual hedges can then keep
   portfolio delta near zero. This is a true long-volatility strategy, but its
   gamma-scalping gains must exceed theta, option spread and hedge costs.

Run the available point-in-time GEX experiment:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python gex_delta_neutral_research.py \
  --output-dir crypto-gex-6h-20260806
```

The script uses only GEX events known before each forward price window. It
deduplicates source timestamps, starts the first candle strictly after the GEX
event, forms non-overlapping six-hour windows, selects grid parameters on the
first chronological half for each underlying and reports only the latter half
as out of sample.

The stored snapshots currently permit only the linear GEX-conditioned test.
They do not contain the point-in-time option bid/ask, implied volatility,
theta, contract-level Greeks and executable hedge fills required for an honest
delta-hedged option backtest. Current GEX signs also assume calls are dealer
long gamma and puts dealer short gamma; actual dealer positioning is not
published.

Core references are Black and Scholes (1973), DOI `10.1086/260062`, for option
pricing/dynamic replication and Leland (1985), DOI
`10.1111/j.1540-6261.1985.tb02383.x`, for replication with transaction costs.
The project GEX documentation also links the empirical *Option Gamma and Stock
Returns* paper; market-GEX evidence is not itself an executable hedge rule.

The workflow is public-data and research-only. It does not read an account,
start a service or place an order.
