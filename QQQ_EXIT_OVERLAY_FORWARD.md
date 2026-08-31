# QQQ Exit Overlay Forward Study

This study compares profit-protection overlays for the locked QQQ monthly
active-enhancement book. It is public-data research only. It cannot access an
account, place an order, modify the QQQ live deployment, or authorize paper or
live trading.

## Frozen boundary

- Registry: `config/qqq_exit_overlay_forward_preregistration.json`
- Model: `qqq-exit-496ffb3159b6f4d6`
- Forward boundary: `2026-08-10T17:05:00Z`
- Data before the boundary is not replayed or counted as evidence.
- The locked monthly QQQ weights supply directions and active weights. New
  append-only monthly decisions start a new cohort at the first subsequent
  weekday 09:35 America/New_York 5-minute bar.
- A leg that exits early stays flat until the next monthly cohort.
- Monthly cohort changes use the source model's target-weight delta turnover;
  unchanged exposure is not charged as a synthetic close-and-reopen round trip.

## Frozen variants

All variants retain the 15% active-leg stop and use completed 5-minute closes.
Exit decisions execute at the next available 5-minute open.

1. `monthly_control`: no profit exit; hold until the next monthly cohort or
   the 15% stop.
2. `fixed_take_profit_10pct`: exit after a completed close reaches a 10%
   favorable return.
3. `trailing_profit_6pct_4pct`: activate after peak favorable return reaches
   6%, then exit after a 4 percentage-point giveback from the peak.
4. `biweekly_20session_trend_review`: after accumulating 20 entirely forward
   US-session closes, review every 10 sessions and exit if the 20-session
   return opposes the position side. Session-close history remains continuous
   while a leg is flat so each lookback is made from consecutive market
   observations.

These round parameters were frozen before any post-boundary observation. They
must not be tuned against the accumulating sample.

## Accounting and maturity

The observer reads `load_candles` and `load_funding` from `data_pipeline.py`.
It reports gross return, realized funding, base net return, double-cost return,
one-extra-bar exit latency, trades, profit factor, maximum drawdown and worst
daily return. Base cost is 5 bps fee plus 5 bps slippage per side; stress
doubles both.

A single frozen evaluation is allowed only after at least 365 forward days, 12
monthly cohorts, 80 closed candidate legs, 20 candidate-specific exits and 90%
complete cross-instrument market observations. Evaluation still cannot promote
the strategy automatically.

## Operation

The public-only timer runs daily after the data-lake refresh:

```bash
systemctl status okx-qqq-exit-overlay-forward.timer
PYTHONPATH=. .venv/bin/python qqq_exit_overlay_forward.py --force
```

Append-only observations are stored under
`data_lake/research/qqq-exit-496ffb3159b6f4d6/`. Current status is written to
`reports/qqq_exit_overlay_forward/`.
