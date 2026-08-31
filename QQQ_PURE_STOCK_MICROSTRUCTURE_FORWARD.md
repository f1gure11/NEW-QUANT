# Pure-stock microstructure forward observation

This is a public-data-only forward observation for the exact 29 equity
contracts in the frozen pure-stock Monte Carlo universe. It adds point-in-time
open interest, OKX funding premium, latest-trade order-flow samples, and
50-level book depth to the existing 30-minute collector.

## Frozen boundary

- Registry: `config/qqq_pure_stock_microstructure_forward_preregistration.json`
- Model: `qqq-stock-microstructure-ee829cd47ba482d5`
- Forward boundary: `2026-08-12T02:53:48Z`
- Classification: `new_forward_observation_only`
- Paper/live authorization: `false`

Only snapshots captured strictly after the boundary and tagged with this model
ID are eligible. Older snapshots, the inspected 2026-06-18+ window, and the
2026-08-11 Monte Carlo output cannot be backfilled or reused as validation.

## Observation schema

Every scheduled run requests public OKX data at UTC minute 00 and 30:

- OI: contracts, underlying units, and USD value from `open-interest`;
- premium: the OKX `funding-rate` response's point-in-time `premium` field;
- order flow: buyer/seller counts and notional imbalance over the latest 100
  public trades returned at capture time;
- depth: raw 50-level bid/ask price and size, plus frozen 5/10/25/50-level
  contract, USDT-notional, and imbalance features.

The latest 100 trades are a sample, not complete 30-minute flow. A snapshot is
complete only when ticker, both book sides, trades, OI, and premium are present.
The collector writes append-only JSONL to both `data/microstructure/` and
`data_lake/snapshots/`; research must read the latter with
`data_pipeline.load_snapshots`.

## Evaluation gate

No four-field reduction formula is authorized yet. Existing short-window
factor rules are already inspected and cannot be imported. A single
deterministic reduction mapping must receive its own content-hashed
preregistration before the end of the first complete eligible calendar month,
or this dataset remains descriptive only.

Comparison with the unchanged source strategy stays locked until all gates
pass: at least 12 complete calendar months, 90% complete scheduled snapshots
for every contract in every counted month, 100 independent reduction events,
at least 25 events in validation and 25 in test, and event coverage across at
least 12 contracts. Repeated alerts for one contract in one monthly cohort
count as one event.

After maturity there is one chronological 50/25/25 evaluation. It must report
the unchanged baseline and frozen candidate side by side, including gross,
net at 10 bps/side, net at 20 bps/side, funding, turnover, activity, profit
factor, drawdown, worst month, and missingness. The result cannot modify the
old Monte Carlo report or authorize paper/live trading.
