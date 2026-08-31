# Layered Momentum, VWAP Execution, And Risk Overlays

This read-only experiment tests a deliberately hierarchical combination. It
does not average unrelated strategy scores:

1. The existing 1H multi-horizon momentum rule sets direction.
2. Prior-hour realized volatility scales the target notional.
3. Funding, point-in-time GEX, and scheduled macro events can only reduce the
   target. They cannot flip it or increase leverage.
4. The existing 24-hour VWAP configuration executes only the difference
   between current and target position. It does not quote both sides or create
   an independent inventory book.

The frozen defaults are `6/12/24/48` hourly momentum lookbacks, two required
votes, 0.1-sigma threshold, 300 bps target daily volatility, 50% maximum target
notional and no leverage. VWAP execution uses a 288-bar 5m window, 50% anchor,
10 bps minimum half-spread, 0.5 bps trade-through, 10% equity per passive slice
and a 30-minute timeout before a taker rebalance.

Risk multipliers are fixed before the test:

- a funding rate that costs the target side by more than 1 bps reduces target
  size to 50%;
- fresh negative GEX, or price outside positive-GEX walls, reduces target size
  to 50%;
- the hour before and after a reviewed macro release reduces target size to
  25%;
- unavailable or stale GEX is neutral, never backfilled.

Run the BTC/ETH/SPCX comparison using public data only:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python combined_overlay_research.py \
  --bar 5m --limit 300 --pages 48 --funding-pages 2 \
  --refresh --refresh-funding \
  --output-dir reports/combined_overlay/btc-eth-spcx-20260807
```

The report compares direct taker momentum, momentum with one-sided VWAP
execution, VWAP plus Funding/macro filters, the full GEX combination, stressed
costs and one-extra-bar latency. Historical GEX starts on 2026-07-24 for BTC
and ETH and is absent for SPCX, so its contribution is reported separately and
never treated as trained history.

All periods reuse history already inspected elsewhere in this repository. A
positive result would remain `research_only` until a fresh walk-forward and an
event-level maker queue/fill test pass.

## Frozen-Configuration Result (2026-08-07)

The public-data run used 14,399 continuous completed 5-minute candles per
instrument from 2026-06-18 11:40 UTC through 2026-08-07 11:30 UTC. The table
shows the cross-instrument median return:

| Period | Direct momentum | Momentum + VWAP | Full combination |
| --- | ---: | ---: | ---: |
| Train | -0.8712% | -0.7768% | -1.0896% |
| Validation | +1.3644% | +1.3052% | +2.4133% |
| Test | -5.3124% | -4.1963% | -3.2034% |
| Full history | -3.2179% | -4.0620% | -3.6744% |

The full combination improved the reused-test median relative to direct
momentum, but every instrument still lost money: BTC -3.2034% (PF 0.205), ETH
-2.8679% (PF 0.433), and SPCX -9.0073% (PF 0.285). Cost stress remained
-4.0394%, one-extra-bar latency remained -3.0098%, and the quantitative gate
failed.

The ablations show that the overlays are risk controls rather than a new
alpha. Removing GEX worsened the test median from -3.2034% to -4.2038%, so the
point-in-time BTC/ETH GEX reduction helped during its short coverage window.
It could not repair the underlying momentum regime failure. SPCX also exposes
the execution risk: direct taker momentum returned -5.3124%, while delayed
VWAP execution returned -8.8698% even though fees fell from 708.64 to 639.91
USDT. The 3.5574 percentage-point deterioration therefore came primarily from
tracking delay and adverse selection, not higher fees.

Decision: the strategies can be combined hierarchically, but this frozen
version is not tradeable. It remains `research_only`; do not tune it further
on this inspected test period or authorize paper/live execution. The next
valid evidence must come from a pre-registered fresh walk-forward period and,
for maker execution claims, event-level queue/fill data.
