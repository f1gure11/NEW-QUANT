# BTC/ETH GEX Risk-Controlled Aggregation

> Status: abandoned by user on 2026-08-06. Retained only as reproducible
> research evidence; do not tune, paper trade or deploy.

This experiment replaces stale US-equity GEX inputs with the locally stored
point-in-time BTC and ETH option GEX series. GEX is used only as a risk gate:

- new dual-book aggregation entries require fresh positive net GEX and the
  prior completed close between the contemporaneous put and call walls;
- every other state blocks new entries while existing take-profit and
  inventory-expiry exits remain active;
- GEX can never increase leverage or an exposure limit;
- exchange leverage is fixed at 1x, combined gross notional is capped at 50%
  of current equity, and entry-time absolute net notional is capped at 10%;
- old lots expire after a train-selected number of bars and close at the next
  candle open with taker fee and slippage.

Run the train/validation/test experiment against public cached BTC/ETH candles
and point-in-time GEX snapshots:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python gex_risk_controlled_aggregation.py \
  --output-dir btc-eth-20260806
```

The first 50% of the common history selects one parameter set for both
underlyings. The next 25% is validation and the final 25% is untouched test.
The report compares the selected GEX/wall/expiry strategy with always-on,
sign-only, no-expiry and stressed-cost variants.

This is public-data research only. It does not load `.env`, read an account,
start a service or place an order. Passing its gate would authorize paper
simulation only, not live trading.
