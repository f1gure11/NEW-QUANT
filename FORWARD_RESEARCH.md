# Frozen Forward Research

`research_forward.py` is the collection and maturity gate for the strategies
that remain legitimate after the 2026-08-08 research freeze. It is public and
read-only: it does not load `.env`, use account endpoints, submit orders, or
authorize paper/live trading.

## Frozen studies

The immutable registry is `config/research_preregistrations.json`. It contains:

1. QQQ monthly active enhancement model `qqq-pit-1fda3d7e14f137bf`.
2. A new QQQ event gate whose surprise scales and 5-minute breakout/reversal
   confirmation rules were frozen before its forward sample.
3. The existing SPCX 1H `6/12/24/48` multi-horizon momentum rule, observed
   without adding a new funding threshold.

Each model has an artifact checksum, a forward boundary, explicit costs,
sample-maturity checks, and `paperOrLiveAuthorized: false`. Changing any frozen
field invalidates the registry checksum.

## Event data

The collector stores the complete TradingView Economic Calendar response by
content hash under `data_lake/events/raw/tradingview/`. Normalized append-only
observations preserve:

- official scheduled time and source release time;
- capture time and the first time an actual value was observed;
- point-in-time consensus, actual, previous, derived previous revision;
- the fixed-scale surprise and source row identifiers;
- recent public QQQ 5-minute candles and the frozen price-path decision.

The exact source tickers are preregistered. Missing, ambiguous, late, or
unit-incompatible fields set `dataComplete: false`; they never become a trade
signal. A significant surprise only makes an event eligible. Price action still
decides breakout, reversal, or no trade.

## Collection and status

```bash
PYTHONPATH=. .venv/bin/python research_forward.py collect
PYTHONPATH=. .venv/bin/python research_forward.py qqq-signal
PYTHONPATH=. .venv/bin/python research_forward.py status
```

The timer checks every 30 minutes so that pre-release consensus and the first
post-release actual can both be retained. QQQ and SPCX market observations are
deduplicated to one per UTC day. A separate QQQ timer checks after the US close
on days 1-5 of each month. It accepts only a newly completed month, applies the
already frozen universe/factors/constraints, and archives the exact Yahoo/SEC
inputs with SHA256 checksums before appending one immutable decision. Output
locations:

- `data_lake/events/` - normalized and raw event observations;
- `data_lake/research/<modelId>/` - daily frozen-model observations;
- `reports/forward_research/status.json` - machine-readable maturity checks;
- `reports/forward_research/report.md` - compact operator status.

Maturity allows exactly one frozen `50/25/25` evaluation with gross, net,
double-cost, funding, latency, trade count, PF, drawdown, and worst-window
reporting. It does not authorize paper or live trading.
