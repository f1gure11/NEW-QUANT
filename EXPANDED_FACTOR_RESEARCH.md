# BTC/ETH Expanded Multi-Factor Research

This read-only experiment tests whether the earlier three-factor price model
was under-specified. It expands the causal feature set to multi-horizon returns,
acceleration, price z-scores, range position, RSI, realized-volatility term
structure, trend efficiency, return autocorrelation and skew, upside/downside
semivolatility, spread, open-interest changes, funding, premium, and time of
day.

The model is an L2-regularized Ridge regression over standardized features.
Order flow is excluded from learned features and may contribute only 0%, 5%,
or 10% as an external confirmation overlay. The first 40% of history fits the
weights, the next 10% selects model and execution settings, the following 25%
is validation, and the final 25% is an exploratory reused-history test.

Run:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python expanded_factor_research.py \
  --output-dir btc-eth-20260807
```

The experiment does not load `.env`, access an account, start a service, or
place an order. The reused test cannot authorize paper or live trading.

## 2026-08-07 Result

The expanded model used 46 causal features. Training-internal selection chose
a 240-snapshot forecast, Ridge alpha 1000, 0% order-flow confirmation, a 0.15
signal threshold, and 250/120 bps take-profit/stop-loss levels. Validation was
positive at +0.1963% median with a 1.068 median profit factor, but the reused
test failed both assets: BTC -0.5984% and ETH -0.6193%, for a -0.6089% median
and 0.771 median profit factor. Cost stress fell to -1.1481%.

Adding factors therefore improved the intermediate validation result but did
not solve cross-period instability. The strategy remains research-only.

Report: `reports/expanded_factors/btc-eth-20260807/report.md`.
