# US equity mean-reversion portfolio research

This isolated research tool compares three fixed literature-inspired
mean-reversion portfolios on a chronological train/validation/test split. It
uses a 1000 USD account, 0.01-share quantity increments, and reports every
leverage from 2x through 10x under gross, base-cost, and stress-cost profiles.

The frozen registry is
`config/us_equity_mean_reversion_preregistration.json`. The tool has no account,
order, paper, live, or service-control path.

## Frozen portfolios

- Five-day cross-sectional reversal: long the five worst and short the five
  best recent performers, rebalanced every five sessions.
- Five-day market-residual reversal: estimate each stock's rolling 252-session
  QQQ regression, then long/short the five-day residual losers/winners.
- Distance pairs: select five disjoint pairs on a 252-session formation window,
  trade for 126 sessions at a fixed two-standard-deviation entry, and exit on
  convergence to the formation mean.

The common universe contains 26 current OKX-mapped equities with complete
cached adjusted-close histories from 2016-08-08 through 2026-08-07. This
creates current-survivor and current-contract bias. Later listings are excluded
by the data-completeness rule, not by their returns.

## Split and costs

- Train: 2017-08-08 through 2022-02-02.
- Validation: 2022-02-03 through 2024-05-03.
- Test: 2024-05-06 through 2026-08-07.
- Base: 10 bps per side, 5% annual financing on long notional above equity,
  and 1% annual short borrow.
- Stress: 20 bps per side, 8% financing, and 3% short borrow.
- Margin proxy: liquidate on a completed daily close when equity is at or below
  5% of gross notional, plus a 50 bps gross penalty.

Once a path liquidates it remains in cash. A higher-cost high-leverage scenario
can therefore retain more terminal cash by liquidating earlier; this is a path
timing artifact and never evidence that higher costs improve the strategy.

OKX funding is audited through `data_pipeline.load_funding` but excluded from
the historical PnL because its point-in-time coverage begins only in 2026.
Backfilling it across the underlying 2016-2026 sample would introduce temporal
bias.

## Run

```bash
PYTHONPATH=. .venv/bin/python us_equity_mean_reversion_research.py
```

Outputs are written under `reports/us_equity_mean_reversion/mr-2016-2026-v1/`.
All results are development-only and cannot authorize paper or live trading.
