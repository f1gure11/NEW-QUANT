# OKX Grid Backtest

This module provides an offline research backtest for the OKX grid bot. It uses public OKX candles or a local CSV cache, and it never calls private trading APIs.

It is for validation and research only. Backtest results are not investment advice and do not predict future performance.

## Quick Run

Run a BEAT backtest using the current dashboard runtime config:

```bash
cd /opt/okx-quant
.venv/bin/python -m backtest.okx_grid_backtest \
  --inst-id BEAT-USDT-SWAP \
  --bar 1m \
  --limit 300 \
  --runtime-config data/okx/grid_bot_runtime_config.json \
  --starting-equity 100 \
  --ct-val 1 \
  --tick-sz 0.0001 \
  --lot-sz 0.1 \
  --min-sz 0.1
```

Run RE:

```bash
.venv/bin/python -m backtest.okx_grid_backtest \
  --inst-id RE-USDT-SWAP \
  --bar 1m \
  --limit 300 \
  --runtime-config data/okx/re_grid_bot_runtime_config.json \
  --starting-equity 100 \
  --ct-val 1 \
  --tick-sz 0.00001 \
  --lot-sz 1 \
  --min-sz 1
```

## Outputs

Each run writes a timestamped directory under:

```text
reports/backtests/
```

Files:

- `summary.json`: parameters and headline metrics.
- `report.md`: Markdown summary.
- `fills.csv`: simulated fills.
- `equity_curve.csv`: bar-by-bar equity, position, and order state.

Public candle cache is saved under:

```text
data/backtest/
```

Both output directories are ignored by Git except for `.gitkeep`.

Use `--output-dir name` to write to `reports/backtests/name`, or pass an absolute path such as `/tmp/okx-grid-backtest-smoke` for temporary smoke runs.

## Execution Model

- Limit orders fill when a candle high/low crosses the order price.
- Intrabar order sequence is approximate; this is not tick-level matching.
- Fees, slippage, contract value, tick size, and lot size are configurable.
- The strategy approximates the live grid bot logic: adaptive range, one-way open guard, MA-cross regime filter, TP orders, total-loss stop, position-loss stop, cooldown, and recenter after risk events.

## Local CSV Input

Use a local candle CSV with columns:

```text
ts,open,high,low,close,volume
```

Then run:

```bash
.venv/bin/python -m backtest.okx_grid_backtest --input-csv data/backtest/my_candles.csv
```
