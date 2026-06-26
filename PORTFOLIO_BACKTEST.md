# OKX Portfolio Candidate Backtest

This is the first-stage, read-only research workflow for selecting hot OKX
USDT perpetual swaps and batch-backtesting the existing adaptive grid strategy.
By default it uses public OKX endpoints only and does not read `.env` or call
private trading APIs. Passing `--include-account` enables private position reads
for dry-run comparison, but still does not trade.

## Quick Run

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python portfolio_backtest.py \
  --top-n 20 \
  --min-quote-volume 5000000 \
  --max-spread-bps 20 \
  --backtest-bar 1m \
  --backtest-pages 3 \
  --backtest-limit 300
```

## Modes

Portfolio output is explicitly separated by mode:

- `backtest`: public-data research report and execution drafts only.
- `paper`: dry-run portfolio plan with generated runtime configs, no live start.
- `live`: account-aware candidate plan intended for dashboard live start.

The dashboard live start path reruns account-aware preflight, writes
`live_plan.json`, then starts only runtime-ready enter/increase/hold bot items.
Reduce/exit items stay one-shot reduce-only operations and are logged
separately.

For a small smoke run:

```bash
PYTHONPATH=. .venv/bin/python portfolio_backtest.py \
  --top-n 3 \
  --min-quote-volume 1000000 \
  --max-spread-bps 50 \
  --backtest-pages 1 \
  --backtest-limit 80 \
  --output-dir /tmp/okx-portfolio-smoke
```

## Outputs

Default output directories are timestamped under:

```text
reports/portfolio/
```

Files:

- `candidates.json`: selected instrument metadata and run configuration.
- `scores.csv`: sortable score table and headline backtest metrics.
- `rebalance_plan.json`: dry-run target allocations and action plan.
- `rebalance_plan.csv`: sortable dry-run action table.
- `execution_intents.json`: dry-run execution bundle and generated bot commands.
- `execution_intents.csv`: sortable execution intent table.
- `runtime_configs/`: generated runtime config drafts for enter/increase/hold targets.
- `summary.md`: human-readable score summary.

Public candle cache is still stored under `data/backtest/`.

## Scoring

The score combines total return, max drawdown, profit factor, fill count, and
risk events. A candidate with no fills receives a no-trade penalty, because a
grid that never trades is not useful for allocation even if it avoids drawdown.

Each scored candidate also records recent trading-pool movement metrics over
`--pool-window-hours` hours, default `5`. For 1m backtests this is the latest
300 candles. The execution bundle uses these metrics to prewrite per-symbol
runtime values before a bot starts: leverage, grid bps, adaptive width, order
margin %, max margin %, take-profit bps, position stop bps, exchange stop bps,
total profit %, and total loss %. The live bot can still keep recalculating
those values each cycle through `--rolling-adaptive`.

Runtime configs also include backtest risk/reward fields. Total return,
drawdown, profit factor, fills, and risk-event count are mapped into
`totalProfitTpPct`, `totalLossSlPct`, `minTpBps`, `positionLossSlBps`, and
`exchangeStopBps` so live TP/SL ratios are controlled by the selected backtest,
not only by recent pool volatility.

## Rebalance Dry Run

The workflow also creates a dry-run target portfolio from the hot-symbol score
table, not from only the currently held symbols. It does not place or cancel
orders. By default it uses the configured `--starting-equity` as planning equity
and assumes no current holdings.

Useful knobs:

```bash
--target-symbols 4
--allocation-min-score -999999
--allocation-min-fills 1
--allocation-max-risk-events 5
--cash-reserve-pct 20
--max-weight-pct 40
--min-weight-pct 5
--core-symbols 2
--core-weight-share-pct 70
--satellite-max-weight-pct 12
--satellite-min-weight-pct 3
--rebalance-threshold-pct 5
```

The first `--core-symbols` ranked targets are core positions. Remaining selected
targets are satellites, capped by `--satellite-max-weight-pct` and floored by
`--satellite-min-weight-pct`.

To include current OKX positions in the dry-run comparison, pass
`--include-account`. This loads `.env` and reads private position data, but
still does not trade:

```bash
PYTHONPATH=. .venv/bin/python portfolio_backtest.py \
  --top-n 10 \
  --include-account \
  --close-missing
```

## Execution Bundle

Each run now writes runtime config drafts and dry-run commands for target
allocations. The generated commands intentionally omit `--live`; they are
one-cycle bot dry runs for operator inspection. Running one of these commands
will read private account state through `auto_grid_bot.py`, but it will not
place or cancel orders unless the operator manually adds `--live`:

```text
PYTHONPATH=. .venv/bin/python auto_grid_bot.py --inst-id ... --runtime-config ... --once
```

Actions that imply reducing or exiting exposure generate a
`portfolio_rebalancer.py` dry-run command. The command is reduce-only shaped and
still omits `--live`; it must pass preflight and be reviewed before any live
confirmation is added. The current stage does not start processes, install
systemd units, or live trade.

## Preflight Guard

Before using any generated runtime config, run the preflight guard against the
report directory:

```bash
PYTHONPATH=. .venv/bin/python portfolio_preflight.py reports/portfolio/<run-dir>
```

Default checks are local only: runtime config exists, command remains dry-run,
`--once` is present, and no matching local bot process is already running.

To also read OKX positions, normal pending orders, and conditional algo orders:

```bash
PYTHONPATH=. .venv/bin/python portfolio_preflight.py \
  reports/portfolio/<run-dir> \
  --include-account
```

Preflight writes:

- `preflight_report.json`
- `preflight_report.md`

Any `block` check means the execution bundle should not be promoted.

## Live Drafts

After a passing account-aware preflight, you can generate live start drafts:

```bash
PYTHONPATH=. .venv/bin/python portfolio_live_plan.py reports/portfolio/<run-dir>
```

This writes:

- `live_plan.json`
- `live_plan.csv`
- `live_plan.md`
- `systemd/*.service.draft`

The script does not start bots or install systemd units. It refuses to generate
ready start items unless `preflight_report.json` has `status=pass` and
`includeAccount=true`. Reduce/exit intents remain review-only and are not
promoted into live start drafts.
