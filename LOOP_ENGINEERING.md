# Loop Engineering Implementation

This repo now maps the blog "一人量化基金：如何用 Loop Engineering 搭建自进化量化框架？" into a dry-by-default OKX workflow.

## GitHub References

- [okx/agent-trade-kit](https://github.com/okx/agent-trade-kit): closest fit for an OKX MCP connector. It exposes OKX market, account, spot, swap, futures, option, bot, and order tooling to MCP-capable agents.
- [lazy-dinosaur/ccxt-mcp](https://github.com/lazy-dinosaur/ccxt-mcp): exchange-agnostic crypto MCP server through CCXT.
- [code-rabi/interactive-brokers-mcp](https://github.com/code-rabi/interactive-brokers-mcp): useful brokerage MCP reference for market data, positions, and orders.
- [trade-it-inc/trade-it-mcp](https://github.com/trade-it-inc/trade-it-mcp): broker aggregation MCP pattern with draft order and explicit execution split.
- [l3a0/snaptrade-mcp-server](https://github.com/l3a0/snaptrade-mcp-server): read-only brokerage MCP design that is useful for safe portfolio context.

## Local Mapping

The entry point is `quant_loop.py`. It writes `run_plan.json`, `run_plan.md`, `STATE.md`, and `PROGRESS.md` under `reports/loop/<timestamp>/`.

Default behavior is plan-only:

```bash
PYTHONPATH=. .venv/bin/python quant_loop.py
```

Run a small single-instrument plan:

```bash
PYTHONPATH=. .venv/bin/python quant_loop.py \
  --inst-id BTC-USDT-SWAP \
  --pages 1 \
  --walk-pages 2
```

Execute the planned dry-run commands:

```bash
PYTHONPATH=. .venv/bin/python quant_loop.py \
  --inst-id BTC-USDT-SWAP \
  --pages 1 \
  --walk-pages 2 \
  --execute
```

The generated commands intentionally do not include `--live`, `--confirm-live`, or `I_UNDERSTAND`. Private account reads are opt-in with `--include-account` and still do not trade.

## Five Stages

| Blog stage | Local command path |
| --- | --- |
| Data ingestion | `microstructure_collect.py` |
| Signal generation | `strategy_search.py` |
| Verification | two `strategy_walk_forward.py` runs plus `strategy_candidate_gate.py` |
| Execution planning | `portfolio_backtest.py`, `portfolio_preflight.py`, `strategy_signal_plan.py` |
| Risk monitoring | `portfolio_preflight.py`, `portfolio_tail_hedge.py` dry-run |

## Safety Boundary

This implementation uses the existing native OKX REST client. The GitHub MCP projects above are reference connector options if you want an MCP-capable agent to call the same workflow. Live order placement remains outside `quant_loop.py`; it still requires the existing server-side live guard and explicit confirmation in the execution modules.
