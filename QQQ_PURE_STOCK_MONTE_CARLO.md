# Pure-stock factor Monte Carlo

`qqq_pure_stock_monte_carlo.py` is an isolated, read-only risk stress test for
the locked QQQ active-enhancement stock signals. It removes the QQQ/SPY core,
normalizes the remaining signed factor weights to 100% gross, applies frozen
leverage and exit rules, and generates two-year synchronized monthly block
bootstrap paths. It cannot read an account, place orders, modify services, or
authorize paper/live trading.

## Frozen scope

- Registry: `config/qqq_pure_stock_monte_carlo_preregistration.json`
- Classification: `development_only_risk_stress_on_inspected_history`
- Capital: 100 USDT
- Leverage family: 2x, 3x, 5x, and 10x
- Quantity step: synthetic 0.01 underlying share; real OKX `ctVal`, `lotSz`,
  and `minSz` are deliberately overridden
- Rebalance: monthly locked factor weights, with no factor refit
- Stop: 15% adverse completed-close return, executed at the next daily close
- Profit exits: fixed +10%, or trailing +6% activation with a four percentage
  point giveback; exited legs remain flat until the next monthly rebalance
- Costs: 10 bps per side and a frozen 20 bps stress profile
- Margin proxy: cross-margin maintenance at 5% of gross, plus a 50 bps gross
  liquidation penalty
- Monte Carlo: 4,000 paths, 24 sampled monthly episodes, seed 20260811

The factor universe has 29 stocks. `DASH` is excluded because
`DASH-USDT-SWAP` is the category-1 Dash cryptocurrency contract, not DoorDash
equity. Newly tracked stocks outside the source model are not added or fitted.

## Data and interpretation

Each empirical episode keeps one locked point-in-time factor target together
with its actual following-month cross-sectional adjusted-close path. Episodes
are sampled with replacement, preserving within-month stock correlation and
signal/return pairing. Public realized funding is loaded only with
`data_pipeline.load_funding`, aggregated into synchronized daily vectors, and
bootstrapped independently.

This design does not recreate historical OKX stock contracts. The two-year
price source is underlying adjusted daily closes, while OKX contract histories
are much shorter. Intraday stop touches, bid/ask, mark-price liquidation,
margin tiers, depth, basis, and real order-size constraints are unavailable.
The forced 0.01 step also means realized gross can fall below the leverage
target in a 100 USDT account.

All history was already inspected. The chronological 50/25/25 diagnostics and
Monte Carlo output are descriptive development evidence only, not a new
validation sample. All exit, leverage, and cost combinations must be reported;
none may be selected and retuned on this window.

## Run

```bash
PYTHONPATH=. .venv/bin/python qqq_pure_stock_monte_carlo.py
```

The frozen study report is under
`reports/qqq_pure_stock_monte_carlo/pure-stock-mc-20260811-v1/`.
