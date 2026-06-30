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
- `hedge_plan.json`: portfolio tail-hedge diagnostics and scheduled/manual hedge action draft.
- `hedge_plan.csv`: sortable tail-hedge action draft.
- `hedge_plan.md`: human-readable tail-hedge plan.
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

## Tail Hedge Plan

Each portfolio report also writes a tail hedge diagnostic. It measures
current account net notional exposure when `--include-account` is passed,
combines it with recent pool shock/trend and target risk-event counts, then
drafts an opposite-direction hedge if the configured thresholds are hit.
Scheduled reports default to `dynamic` mode: base risk hedges 35% of net
exposure, stress risk hedges 70%, and extreme risk targets a full 100% hedge
subject to margin caps, tradable size, and available USDT.

Hedge instrument selection is asset-aware. Crypto exposure can use the preferred
BTC/ETH/SOL hedge instrument set. Non-crypto contracts such as XAU, stocks, or
indices never fall back to BTC as a proxy hedge: if the same instrument metadata
is available, the hedge plan uses a same-instrument opposite SWAP leg; otherwise
it generates a reduce-only fallback for the existing position.

The scheduled runner can execute a ready hedge automatically after the normal
live guard. It re-checks current SWAP exposure, skips stale plans, skips when
the exposure direction has changed, and avoids repeated same-report or already
sized same-direction hedges.

Useful knobs:

```bash
--tail-hedge-mode plan
--tail-hedge-inst-id BTC-USDT-SWAP
--tail-hedge-ratio 0.35
--tail-hedge-stress-ratio 0.70
--tail-hedge-full-ratio 1
--tail-hedge-trigger-net-exposure-pct 120
--tail-hedge-trigger-shock-bps 120
--tail-hedge-trigger-trend-bps 350
--tail-hedge-trigger-risk-events 8
--tail-hedge-stress-net-exposure-pct 180
--tail-hedge-stress-shock-bps 180
--tail-hedge-stress-trend-bps 550
--tail-hedge-stress-risk-events 40
--tail-hedge-full-net-exposure-pct 240
--tail-hedge-full-shock-bps 260
--tail-hedge-full-trend-bps 800
--tail-hedge-full-risk-events 80
--tail-hedge-min-notional 10
--tail-hedge-max-margin-pct 20
--tail-hedge-stress-max-margin-pct 40
--tail-hedge-full-max-margin-pct 100
--tail-hedge-leverage 3
```

After reviewing `hedge_plan.md`, a ready action can be dry-run manually:

```bash
PYTHONPATH=. .venv/bin/python portfolio_tail_hedge.py --report-dir reports/portfolio/<run-dir>
```

Live hedge execution still requires the normal server live guard and explicit
confirmation. Scheduled auto hedge uses the same guard:

```bash
PYTHONPATH=. .venv/bin/python portfolio_tail_hedge.py \
  --report-dir reports/portfolio/<run-dir> \
  --live \
  --confirm-live I_UNDERSTAND
```

Scheduled auto hedge is enabled by default in
`scripts/run_scheduled_portfolio_backtest.sh` and can be disabled with:

```bash
PORTFOLIO_SCHEDULE_AUTO_HEDGE=0
```

## Scheduled Live Refresh

The installed portfolio timer generates a fresh account-aware report every 30
minutes after an initial 5 minute startup delay. The scheduled command auto
applies the latest plan by default when live trading guards are enabled.

Useful environment overrides in `/etc/okx-portfolio-backtest.env`:

```bash
PORTFOLIO_SCHEDULE_REBALANCE_THRESHOLD_PCT=1
PORTFOLIO_SCHEDULE_TREND_FILTER=auto
PORTFOLIO_SCHEDULE_TAIL_HEDGE_MODE=dynamic
PORTFOLIO_SCHEDULE_TAIL_HEDGE_RATIO=0.35
PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_RATIO=0.70
PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_RATIO=1
PORTFOLIO_SCHEDULE_TAIL_HEDGE_TRIGGER_NET_EXPOSURE_PCT=120
PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_NET_EXPOSURE_PCT=180
PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_NET_EXPOSURE_PCT=240
PORTFOLIO_SCHEDULE_AUTO_APPLY_MAX_CHANGES=4
PORTFOLIO_SCHEDULE_AUTO_APPLY=1
```

Lowering `PORTFOLIO_SCHEDULE_REBALANCE_THRESHOLD_PCT` makes weight-drift
actions trigger sooner; raising `PORTFOLIO_SCHEDULE_AUTO_APPLY_MAX_CHANGES`
allows more stop/start/reduce actions per scheduled cycle.
`PORTFOLIO_SCHEDULE_TREND_FILTER=auto` keeps the per-symbol trend gate enabled
for live scheduled reports; set it to `compare` only if you want each report to
disable the trend gate when the recent backtest scores that variant higher.

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
--rebalance-threshold-pct 1
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
