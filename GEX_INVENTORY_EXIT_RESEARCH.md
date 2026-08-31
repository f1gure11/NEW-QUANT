# BTC/ETH GEX Inventory Exit Research

> Status: abandoned by user on 2026-08-06 after the paired/staged exit
> experiment underperformed the baseline. Retained only as reproducible
> evidence; do not tune, paper trade or deploy.

This follow-up freezes the prior BTC/ETH aggregation entry parameters and tests
whether inventory disposal improves with profitable-basket exits and staged
reduction. It retains 1x leverage, the 50% gross cap, the 10% entry-time net cap
and the point-in-time positive-GEX/put-call-wall gate.

The paired-exit mechanism first looks for aged equal-quantity long and short
lots whose combined exit remains profitable after taker fees and adverse
slippage. If no such pair exists, completed take-profit exit gains form a
single-use credit balance. That balance can pay for an aged inventory exit only
when the exit reduces absolute net exposure. Staged reduction separately closes
a fraction of the remaining lot at predetermined ages; any residual inventory
still exits at its mandatory timeout.

Run the read-only experiment:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python gex_inventory_exit_research.py \
  --output-dir btc-eth-paired-staged-20260806
```

The entry spacing, take profit, layer count and inventory timeout are frozen at
100 bps, 25 bps, six layers per side and 144 five-minute bars. Only exit timing
is selected on the first 50% of history. Pair-only, stage-only, combined and
cost-stress variants are reported separately.

This is an exploratory reuse of the prior history. The mechanism was proposed
after inspecting that history's inventory losses, so the chronologically named
validation and test segments are no longer untouched holdouts. Results cannot
authorize paper or live trading; a genuinely new point-in-time forward sample
is required.

The workflow uses public/cached market data only. It does not load `.env`, read
an account, start a service or place an order.
