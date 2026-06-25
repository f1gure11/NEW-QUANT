# Doubao Quant

Self-hosted OKX quantitative research and execution console.

This project keeps live execution locked behind explicit server-side permission,
preflight checks, and manual confirmation. The current product layer integrates:

- adaptive grid backtests for OKX USDT swaps
- hot-contract portfolio selection and rebalance planning
- RF/HMM market-regime research models under `reports/regime_model/`
- rolling adaptive runtime configs for grid, sizing, TP/SL, and exchange stops
- a web console branded as 豆包 Quant

Core commands:

```bash
PYTHONPATH=. .venv/bin/python portfolio_backtest.py --market-regime-filter auto --trend-filter compare
PYTHONPATH=. .venv/bin/python regime_research.py
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests
```

Reference lineage: QuantDinger was used for signal/execution-contract and
monitoring/report shape ideas only. No QuantDinger live execution code is
vendored into this OKX execution path.
