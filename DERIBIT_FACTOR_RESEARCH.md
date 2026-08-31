# Deribit Option-Information Factor Research

This experiment is a final bounded screen for short-horizon information in
public Deribit option trades. It is read-only and cannot authorize paper or
live trading.

The factor directions are registered before looking at validation and test:

- call-minus-put implied volatility follows Cremers and Weinbaum (2010), DOI
  `10.1017/S002210901000013X`;
- call-versus-put volume follows Pan and Poteshman (2006), DOI
  `10.1093/rfs/hhj024`;
- variance-risk-premium level follows Bollerslev, Tauchen and Zhou (2009), DOI
  `10.1093/rfs/hhp008`, with the Bitcoin/Deribit construction motivated by
  Alexander and Imeraj (2020), DOI `10.3905/jai.2020.1.112`;
- 25-delta risk reversal and butterfly capture the Bitcoin option skew/smile
  documented by Zulfiqar and Gulzar (2021), DOI
  `10.1186/s40854-021-00280-y`.

At 72 hours to each monthly expiry, the script infers an ATM surface and 25
delta call/put observations using only trades already observed at the signal
time. It then holds the Deribit perpetual for 24 hours. Call-rich IV and volume
are assigned the positive direction exactly as in the equity-option papers;
both orientations are not searched. Each asset receives 10% equity with no
leverage. The normal round-trip cost is 12 bps and the stress cost is 24 bps.

A secondary long-ATM-straddle comparison risks at most 0.5% equity in premium
per asset. It uses the previously measured Tardis 72-hour ATM Deribit median
half-spreads of 4.35% for BTC and 3.64% for ETH, rather than pretending the
historical trade close is an executable quote. No naked short-option rule is
tested.

Pan and Poteshman use buyer-initiated opening option volume. Deribit's public
historical chart endpoint exposes only total contract volume, without trade
direction or open/close classification. The call/put volume ratio here is
therefore an explicitly weaker proxy, not a reproduction of their proprietary
signal.

The expiry split is chronological: first 50% training, next 25% validation,
last 25% reused-history test. Strategy choice and numeric medians are fit only
on training. A candidate must stay positive in validation, test, doubled-cost
test and one-hour-latency test, with test PF at least 1.10, ten trades and at
most 3% endpoint drawdown. A pass would still require a new pre-registered
forward sample; a failure means short-term strategy research should stop.

## Result (2026-08-07)

The completed run covers all 42 monthly expiries from 2023-01-27 through
2026-06-26, with one BTC and one ETH surface per expiry: 42 training, 20
validation and 22 reused-test observations. The option surface factors had
complete coverage; 79 of 84 observations also had a sufficiently fresh ATM
option exit for the bounded long-premium comparison.

No directional option-information candidate had a positive eligible training
result. The least-bad candidate was the fixed-orientation 25-delta risk
reversal: training -1.7907% (PF 0.639), validation -0.5222%, test -0.5609%,
cost-stressed test -0.8232%, one-hour-latency test -0.9157%, and full history
-2.8514%. These are account returns with 10% equity per asset.

The ATM call-minus-put IV spread happened to return +0.9052% with PF 1.718 in
the already isolated test, but it was -2.6281% in training, -0.0549% in
validation and -1.8007% over the full history. Switching to it after observing
the test would be test-set selection and is prohibited.

The best training-selected bounded long-premium filter also failed: IV/RV at
or below 1.0 returned -0.6318% in training, -1.3561% in validation, -0.6065%
in test and -2.5739% over the full sample with a 0.5% premium budget per asset.
All five long-premium variants were negative in every chronological segment.

Decision: `stop_short_term_strategy_research`. The evidence does not support a
paper or live trial, further threshold mining, or switching to a test winner.
Retain the public-data collector if desired, but do not resume short-term model
selection until a separately pre-registered fresh forward sample exists.

Run with public data only:

```bash
cd /opt/okx-quant
PYTHONPATH=. .venv/bin/python deribit_factor_research.py \
  --start-month 2023-01 --end-month 2026-06 \
  --output-dir reports/deribit_factors/monthly-20260807
```
