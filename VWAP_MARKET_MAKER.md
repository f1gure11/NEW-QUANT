# BTC/ETH VWAP Inventory-Skew Market Maker Research

This is an isolated, read-only research path for a rolling-VWAP market-maker
candidate. It does not connect to the signal bot, grid bot, account endpoints,
or order APIs.

The strategy treats VWAP as one input to a reservation price rather than as a
standalone long/short signal:

```text
fair value = completed-bar close + anchor_weight * (rolling_vwap - close)
reservation price = fair value - normalized_inventory_skew
bid/ask = reservation price +/- volatility_scaled_half_spread
```

Quotes computed from a completed candle become eligible only on the following
candle. A candle must trade through a quote by the configured penetration
amount before a maker fill is counted. If both sides are crossed in one candle,
the base simulation keeps only the side with the worse close-marked outcome.
This avoids manufacturing a free intrabar round trip from unknown OHLC path
ordering.

Risk controls are part of the strategy definition:

- 2% equity notional per quote and 10% maximum net inventory;
- inventory-dependent quote skew;
- VWAP-slope and realized-volatility pause for new inventory;
- passive reduction remains available during a pause;
- inventory loss stop, maximum inventory age, terminal liquidation;
- maker fees on passive fills and taker fee/slippage on forced exits;
- no leverage.

Run the fixed BTC/ETH 5-minute experiment with fresh public candles:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python vwap_market_maker_research.py \
  --bar 5m --limit 300 --pages 48 --refresh \
  --output-dir reports/vwap_market_maker/btc-eth-20260807
```

The first 50% of common history selects one parameter set shared by BTC and
ETH. The next 25% is validation and the final 25% is an exploratory test. The
training selector includes a separate stressed-cost/trade-through checker.
Test output also includes stressed costs, one-bar latency, no-VWAP, no-inventory
skew, and no-regime-filter ablations.

OHLCV bars cannot determine queue priority, cancellation timing, or actual
post-only fill probability. Even a passing bar result remains `research_only`
until reproduced on a sufficiently long, previously unseen WebSocket event
period with a conservative queue/fill model.

## 2026-08-07 result

The fixed 192-candidate training grid selected a 288-bar (24-hour) VWAP, 50%
anchor weight, 10 bps minimum half-spread, 1.0 volatility multiplier, 10 bps
full-inventory skew, and a 50 bps one-hour VWAP-slope gate. This was only the
least-bad training candidate: no candidate had a positive cross-instrument
training median.

Selected train/validation/test/full median returns were
`-0.4309%/-1.0270%/-0.0006%/-1.7631%`. In the exploratory test, BTC returned
`-0.3752%` with PF `0.706`, while ETH returned `+0.3739%` with PF `1.233`.
Cost stress returned `-0.5393%` and one-bar latency returned `-0.5319%`.
Profitable passive inventory cycles were offset by inventory stop/timeout
losses, especially on BTC. The quantitative gate failed and the strategy
remains `research_only`.

Report: `reports/vwap_market_maker/btc-eth-20260807/report.md`.
