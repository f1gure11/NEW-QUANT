# Strategy Evidence And Activity Upgrade

Updated: 2026-07-10 UTC

## Objective

Increase live market participation without forcing positions, weakening return
and drawdown gates, or copying unverified public strategy parameters.

## Production evidence gate

`strategy_evidence.py` is the live allow-list. The candidate gate now rejects a
strategy unless that module contains at least one HTTPS journal or GitHub
source, and embeds the source snapshot in every newly approved candidate. The
live executor repeats the same check, so manually placing an unverified
strategy in `approved_candidates.json` cannot bypass the rule. At present only
`time_series_momentum` and `multi_horizon_momentum` are eligible; implemented
indicator experiments such as RSI, MACD, Bollinger and EMA remain research-only.

Source evidence is necessary but not sufficient. A registered strategy must
also pass two chronological out-of-sample reports under stressed fees,
instrument slippage and funding cost before it can be applied to live trading.

## Academic basis

- Moskowitz, Ooi and Pedersen (2012), *Time Series Momentum*, Journal of
  Financial Economics, DOI: https://doi.org/10.1016/j.jfineco.2011.11.003
  - Directional input adopted: the sign of an asset's own lagged return.
- Hurst, Ooi and Pedersen (2017), *A Century of Evidence on Trend-Following
  Investing*, DOI: https://doi.org/10.3905/jpm.2017.44.1.015
  - Multi-horizon diversification adopted: several lagged trend horizons vote
    on one persistent position instead of relying on a single optimized period.
- Moreira and Muir (2017), *Volatility-Managed Portfolios*, DOI:
  https://doi.org/10.1111/jofi.12513
  - Risk scaling adopted: target less notional exposure when recent realized
    volatility is high. The live/research target is 300 bps daily volatility.
- Liu and Tsyvinski (2021), *Risks and Returns of Cryptocurrency*, Review of
  Financial Studies, DOI: https://doi.org/10.1093/rfs/hhaa113
  - Crypto-specific support: the paper reports a strong time-series momentum
    effect in cryptocurrency returns.
- Bailey and López de Prado (2014), *The Deflated Sharpe Ratio*, DOI:
  https://doi.org/10.3905/jpm.2014.40.5.094
  - The project retains DSR reporting and multiple-testing context. DSR is not
    used as a hard threshold for the sparse selected-window sample; this is a
    known limitation, not evidence that the candidate passed DSR.

## GitHub review

- https://github.com/freqtrade/freqtrade (GPL-3.0): mature crypto bot and
  lookahead-analysis workflow. Its warning that dataframe-wide calculations can
  leak future candles informed the prior-bar-only tests.
- https://github.com/freqtrade/freqtrade-strategies (GPL-3.0): reviewed as an
  idea catalog only. Its Supertrend example explicitly says the implementation
  is not validated against a paper or trusted source, so it was rejected.
- https://github.com/pst-group/pysystemtrade (GPL-3.0): reviewed for the common
  volatility-normalized EWMAC / diversified trend-forecast shape. No GPL code
  was copied.
- https://github.com/jesse-ai/jesse (MIT) and
  https://github.com/kernc/backtesting.py (AGPL-3.0): reviewed for execution and
  backtest architecture, not for parameter copying.

All new strategy code in this project is an independent implementation of the
published equations and existing project primitives.

## Implemented strategy

`multi_horizon_momentum`:

- live bar: `1H`;
- lookbacks: `6, 12, 24, 48` completed hourly bars;
- each lagged return votes long or short;
- at least two aligned votes establish/flip the position;
- the current side persists through a vote dead zone instead of returning to
  flat, which raises participation without generating an order every bar;
- volatility-normalized vote threshold: `0.1` sigma in the primary report;
- daily volatility target: `300 bps`, 48-bar realized-volatility window;
- all signals for bar `i` use data through bar `i-1` only;
- post-only live entry, funding veto, exchange OCO, drawdown halt, CUSUM and
  heartbeat watchdog remain active.

Research now records train/test exposure percentage. Scheduled candidate gates
require mean test exposure of at least 60% in both reports. Activity gets only a
small train-only ranking bonus; positive return, profit factor, trade count,
worst-window return and drawdown rules are unchanged.

## Validation results

Primary 1H report:

- `reports/strategy_walk_forward/wf-20260710-active-1h-primary`
- SPCX multi-horizon momentum: 3/3 passed windows;
- total test return `+23.20261483%`;
- median test return `+8.00754634%`;
- worst test return `+2.46614493%`;
- 20 trades; mean exposure `100%`.

Independent window-geometry confirmation:

- `reports/strategy_walk_forward/wf-20260710-active-1h-confirm`
- 4/5 passed windows;
- total test return `+13.94885650%`;
- median test return `+2.36625047%`;
- worst test return `-2.61578197%`;
- 44 trades; mean exposure `100%`.

Equivalent-horizon 30m cross-check:

- `reports/strategy_walk_forward/wf-20260710-active-30m-crosscheck`
- equivalent `12, 24, 48, 96` half-hour lookbacks;
- 3/5 passed windows;
- total test return `+24.91422203%`;
- median test return `+3.70978100%`;
- worst test return `-1.41892125%`;
- 42 trades; mean exposure `100%`.

Production gate:

- `reports/strategy_candidates/gate-20260710-evidence-live`
- temporal strategy match approved SPCX only;
- the approval embeds two journal references and one GitHub reference;
- combined primary/confirm trades: 64;
- minimum mean exposure: `100%`;
- combined worst window: `-2.61578197%`.

## Live deployment

- `SPCX-USDT-SWAP` is the only enabled signal service.
- Initial live signal was long; post-only entry filled `0.43` at `150.92`.
- Exchange OCO after fill: TP `154.99`, SL `148.20`, state `live`.
- `SOL-USDT-SWAP` service was disabled after confirming zero position, normal
  orders and algo orders.
- Scheduled research is configured in `/etc/okx-signal-refresh.env` for the
  same 1H activity-aware strategy family, window sizes and 60% exposure gate.

The live service was restarted at `2026-07-10 07:56 UTC` after enabling the
evidence allow-list. It retained the approved `0.45` SPCX short and its live
exchange OCO (TP `146.38`, SL `153.15`).

## Faster-bar rejection

The evidence-backed strategies were separately evaluated on 5m bars in
`reports/strategy_walk_forward/wf-20260710-evidence-5m-primary`, using 5 bps
fees, 2 bps slippage, a 1.5x cost stress multiplier, funding, and observed
microstructure slippage floors. There were 82 selected window rows and 33
aggregate candidates, but zero aggregate passes; median selected out-of-sample
return was `-4.424448%`. Existing 15m primary/confirmation research also had no
candidate passing both reports. No 5m or 15m candidate was promoted to live.

These results are historical sample-out evidence, not a profit guarantee. The
candidate still has a small number of selected windows and does not clear a
hard DSR threshold; live kill switches and the next temporal refresh remain
essential.
