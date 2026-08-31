# Take-Profit-And-Reverse Grid Research

This research models staggered reversal chains rather than an equal-price
long/short lock:

1. Seed long tranches at an anchor and lower percentage levels.
2. When a long tranche reaches its take profit, close it and open a
   same-quantity short at that higher price.
3. When that short reaches its take profit, close it and open a long at the
   lower price.
4. Separate chains can therefore hold long and short inventory at different
   cost bases at the same time. One chain never holds both directions at once.

Run the leverage sweep against the cached semiconductor experiment:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python flip_grid_research.py \
  --source-summary reports/layered_aggregation/semis-5m-20260806/summary.json \
  --output-dir semis-flip-leverage-20260806
```

The sweep tests 1x, 2x, 3x, 5x, 8x and 10x exchange leverage over validation,
final-test, continuous, worst-downtrend and worst-uptrend intervals. It also
tests stressed costs and a 6% account stop. Funding, fees, tick/lot/minimum
sizes, current-equity exposure limits and maintenance-margin liquidation are
included.

The workflow is public-data and research-only. It does not load `.env`, read
an account, start a service or place an order.
