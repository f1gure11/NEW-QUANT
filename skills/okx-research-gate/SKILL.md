---
name: okx-research-gate
description: Enforce research discipline for OKX quant. Use before writing any backtest, factor, or strategy-improvement code.
metadata:
  short-description: Research discipline gate
---

# Research Gate

This project burned many research attempts on the same 2026-06-18+ window.
Every mined candidate failed validation and is `research_only`. The failure
was structural: re-fitting inspected history.

## Gate checklist

Answer all before coding:

1. **New hypothesis, or re-fit?** Reusing 2026-06-18+ data with new
   parameters, weights, filters, or periods is a re-fit. Do not build it.
2. **Frozen and preregistered?** Write the exact model, costs, and split
   before seeing the test window.
3. **New data?** Only a forward sample collected after the hypothesis
   boundary can reopen a direction.
4. **Reversal math?** Reverse a loser only if gross loss `N < -2C`.
   Otherwise it pays friction twice.
5. **Live gated?** A passing study never authorizes paper/live. Live needs
   explicit user approval in the current session.

If the gate rejects the request, say so. Offer the data-pipeline or
forward-collector work that would actually unblock it.

## If the gate passes

- Load data through `data_pipeline.py`.
- Split chronologically 50/25/25. Select on training only.
- Report gross, net-of-cost, and cost-stress.
- On failure: `research_only`, no test-window tuning, short memory note.
- Never swap in a test-only winner after the fact.

## Known dead ends on the inspected window

Do not reopen these without a new forward sample:

- Portfolio grid / rolling-adaptive / walk-forward (0 quality instances)
- Regime RF/HMM as an alpha replacement
- 46-factor Ridge (validation +0.20%, reused test −0.61%, signs flip)
- Factor filters, Americas splits, session-specialized shorts
- GEX aggregation / pin catcher / inventory-exit overlays
- Order-flow RR and ML probability
- VWAP inventory-skew MM
- Deribit option-information shorts
- Slow factors + deep-OTM tail hedge
- TRADFI US-equity intraday and slow daily factors
- QQQ daily-flat contract overlay (failed before costs)
- US-equity mean-reversion books (failed the training gate)
- Altcoin negative-funding V1 replay (0 signals; do not relax thresholds
  on that window)

Options-hedged reversal cut the worst tail (−69% → −54%) and made every
median worse. Insurance is not alpha.

## What is allowed

- Frozen forward collectors already registered under `config/`.
- Descriptive data-lake work.
- A new preregistered rule that can only see post-boundary data.

The QQQ monthly enhancement is the only historically promising locked
result. Its research file still has `paperOrLiveAuthorized: false`.
The live QQQ book is a separate user override, not a research promotion.

Current frozen model IDs are listed in `CODEX_MEMORY.md`.
