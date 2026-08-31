# BTC/ETH Order-Flow Reward/Risk Research

This experiment replaces the abandoned aggregation family with a directional,
single-position order-flow strategy. It uses only locally collected OKX public
snapshots for BTC and ETH swaps.

The tested point-in-time factors are:

- average five-/ten-level depth imbalance;
- aggressive buy/sell imbalance in the latest 100 public trades;
- normalized top-of-book order-flow imbalance (OFI), including best-price and
  queue-size changes;
- confirmation and absorption combinations of those factors.

Signals never overlap on the same instrument. A long pays the executable ask
and exits at the bid; a short pays the bid and exits at the ask. The simulator
adds adverse slippage and taker fees on both sides, sizes every position at 20%
of current equity, and uses no leverage. Stops, targets and time exits are
evaluated only on later executable snapshots.

Run the fixed train/validation/test experiment:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python orderflow_rr_research.py \
  --output-dir btc-eth-20260806
```

The first 50% of the common history selects one factor family, threshold,
take-profit, stop-loss and maximum holding period for both instruments. The
next 25% is validation and the final 25% is untouched test. Reports include
realized win rate, average win/loss payoff ratio, breakeven win rate,
expectancy, profit factor, drawdown, consecutive losses, cost stress and a
one-snapshot latency stress.

Important data limitation: the collector polls REST roughly every 65 seconds
and stores the latest 100 trades. It is not a lossless event-by-event WebSocket
feed, so it cannot model queue priority or maker-fill probability. A passing
REST result would still require reproduction on WebSocket events and paper
simulation before any deployment.

References:

- Cont, Kukanov and Stoikov (2014), DOI `10.1093/jjfinec/nbt003`.
- Gould and Bonart (2016), DOI `10.1142/S2382626616500064`.
- Cartea, Donnelly and Jaimungal (2018), DOI
  `10.1080/1350486X.2018.1434009`.

This workflow does not load `.env`, access an account, start a service or place
an order.
