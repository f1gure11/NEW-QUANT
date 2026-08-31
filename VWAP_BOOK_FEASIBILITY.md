# BTC/ETH VWAP + order-book snapshot feasibility

The published candle-only VWAP maker never saw a book. This path asks only
whether existing BTC/ETH snapshots can be joined to 5-minute VWAP and given
a fill rule. Parameters are inherited from
`reports/vwap_market_maker/btc-eth-20260807/` and are not re-searched.

The July 2–August 12 snapshot window is inspected. Diagnostic PnL cannot
select parameters or authorize paper/live trading.

If the join works, forward research uses only snapshots after
`2026-08-12T18:10:00Z` (`config/vwap_book_forward_preregistration.json`).
Collection: minute-level BTC/ETH/XAU via `okx-microstructure-core.timer`,
plus the existing 30-minute broad collector.

```bash
PYTHONPATH=. .venv/bin/python vwap_book_feasibility.py \
  --output-dir reports/vwap_book_feasibility/feasibility-20260812
```
