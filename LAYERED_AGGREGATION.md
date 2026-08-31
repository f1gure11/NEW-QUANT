# Layered Aggregation Research

`layered_aggregation.py` and `layered_aggregation_research.py` implement a
read-only backtest for a long-only layered inventory strategy:

- split a fixed risk budget into equal quote-notional tranches;
- place each tranche at a percentage step below a completed-close anchor;
- account for each filled layer independently;
- reduce a layer at the nearer of its fixed take-profit price or the previous
  higher layer's entry price;
- re-anchor only after inventory is flat or a risk cooldown completes.

The simulator marks terminal inventory to market and deducts estimated exit
cost. It also includes maker/taker fees, funding settlements, contract lot and
minimum sizes, an optional basket stop, current-equity notional caps, and a
conservative OHLC fill model. A newly opened layer cannot take profit on the
same candle.

## Run the semiconductor experiment

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python layered_aggregation_research.py \
  --bar 5m \
  --limit 300 \
  --pages 30 \
  --refresh \
  --refresh-funding \
  --output-dir semis-5m-20260806
```

The workflow uses public OKX endpoints only. It does not load `.env`, read the
account, start services, or place/cancel orders.

## Validation design

- Instruments are screened by current public spread and 24-hour turnover.
- Only the common candle interval is used.
- One parameter set is selected across all instruments using the first 50% of
  time; the next 25% is validation and the last 25% is final test.
- Parameters that cannot satisfy every instrument's minimum order size at the
  configured starting equity are rejected.
- Final tests include higher costs/fill buffers, funding removal attribution,
  a naive narrow-grid comparison, the worst multi-day decline per instrument,
  and synthetic range/downtrend paths.
- A separately selected risk-capped variant shows whether adding a basket stop
  improves or merely converts inventory drawdown into repeated realized loss.

Outputs are written under `reports/layered_aggregation/<run>/`:

- `report.md`: human-readable conclusion;
- `summary.json`: configuration and all metrics;
- `segments.csv`: instrument/period/stress comparisons;
- `fills.csv`: final-test fills;
- `equity_curve.csv`: final-test marked equity and inventory.

This module is research-only and is intentionally not connected to any live
executor or systemd trading unit.
