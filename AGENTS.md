# AGENTS.md — Project Instructions for AI Agents

Working directory: `/opt/okx-quant`. This file governs how any coding agent
operates in this repository.

## Non-negotiable rules

1. **Never read, print, or commit `.env`.** It holds OKX API keys. Any output
   that would reveal a key value is forbidden. `CODEX_MEMORY.md` and
   `CODEX_MEMORY_ARCHIVE.md` also must never contain secrets.
2. **Live trading is gated.** Do not start, stop, modify, or re-enable any
   live trading system unless the user explicitly asks in the current
   session. Read current unit/config state first; do not trust old memory
   snapshots.
3. **Research freeze.** History from 2026-06-18 onward has been repeatedly
   inspected. Every mined factor/strategy on that window is `research_only`.
   Do not retune it. New research needs a frozen, preregistered rule and a
   genuinely new forward sample.
4. **Read the compact memory first.** Before portfolio, runtime, live, risk,
   or deploy changes, read `CODEX_MEMORY.md`. The chronological dump is
   `CODEX_MEMORY_ARCHIVE.md` and is historical only. After such changes,
   update the current-state section in place and append a 5-10 line note.
5. **Prefer the data lake.** Use `data_pipeline.py` loaders (`load_candles`,
   `load_funding`, `load_snapshots`, `load_events`,
   `load_research_observations`) rather than ad-hoc CSV parsing.
6. **Tests must pass.** Run `PYTHONPATH=. .venv/bin/python -m unittest
   discover -s tests` before finishing a code change. Keep new code covered.
7. **Keep the public frontend up.** `https://panel.doubaoquant.ltd` is part
   of every dashboard/frontend deploy. Verify the domain path, not only
   localhost.

## How files of record are split

| File | Role |
|---|---|
| `CODEX_MEMORY.md` | Current operating truth. Keep it short. |
| `CODEX_MEMORY_ARCHIVE.md` | Pre-2026-08-12 diary. Do not treat as live. |
| `AGENTS.md` | Durable agent rules for every session. |
| `/root/.codex/skills/okx-*` | Task skills Codex should load. |
| `skills/okx-*` | Same skills, versioned in the repo. |

Do not grow `CODEX_MEMORY.md` back into a session log.

## Repository layout

- `data_lake/` — symlink to `data/data_lake` on the data disk (parquet
  candles/funding, jsonl events/research, `manifest.json`)
- `data/microstructure/` — the only 30-minute snapshot store; the lake
  `snapshots/` path is a symlink to it
- `data/` — raw sources plus the lake; treat historical inputs as read-only
- `reports/<study>/` — one dir per research study
- `config/` — frozen playbooks, preregistrations, live configs
- `deploy/systemd/` — service + timer unit files
- `tests/` — unittest suite (598 tests at 2026-08-12)
- `web/` — ops dashboard, readonly view, research panel
- `english_learning/` — separate reader on port 8780

## Data lake quick reference

```python
from data_pipeline import (
    load_candles, load_funding, load_snapshots,
    load_events, load_research_observations,
)
from deribit_collect import load_deribit_candles, load_deribit_funding, load_deribit_dvol
candles = load_candles("BTC-USDT-SWAP", "5m", start="2026-07-01")
funding = load_funding("QQQ-USDT-SWAP")
snaps   = load_snapshots("btc_usdt_swap")
```

- Instrument names normalize `-` → `_` and lowercase (`btc_usdt_swap`).
- Candle columns: `time, ts, open, high, low, close, volume, inst_id, timeframe`.
- Funding columns: `funding_time, ts, funding_rate, realized_rate, inst_id`.
- Rebuild/increment: `data_pipeline.py build|collect|manifest`.
- Daily incremental timer: `okx-data-pipeline.timer` (00:37 UTC).
- If you rebuild the lake as root, `chown -R okxbot:okxbot data/data_lake
  data/microstructure`.
- Do not copy snapshots into a second tree. `data_pipeline.py build`
  skips the copy when both paths resolve to the same directory.

## Research protocol

1. Preregister the hypothesis and frozen rule set *before* looking at the
   test window. State them in the report.
2. Split chronologically (e.g. 50/25/25). Select only on training.
3. Report gross, net-of-cost, and cost-stress. Mechanical reversal needs
   gross loss `N < -2C`.
4. If it fails: mark `research_only`, do not tune on test, do not
   paper/live promote, append a short memory note.
5. If it passes: still gate live behind explicit user approval.

Use the `okx-research-gate` skill before writing research code.

## Live operations

Use the `okx-live-ops` skill. Current authorized live books, if still
inside their expiry windows:

- QQQ all-min: `config/qqq_allmin_live.json`, expires 2026-09-01, 12
  names, gross 1.20, 100 USDT cap.
- Active subjective books: `config/active_books.json` can list more than
  one one-day view. Each view has its own config, state, halt, and flatten
  time. `okx-active-sector-expire.timer` disables the trading timers only
  when every registered view has expired. Do not add a view without an
  explicit user request.
- Shared risk: `config/shared_live_risk.json`. Combined 1.60 is
  observational (`combinedEnforcement=observe`). QQQ 1.20 and active 2.00
  are independent. They still share one wallet and liquidation.

Grid, portfolio auto-apply, and old signal bots are off. Do not revive
them without a new explicit request.

## Frontend

Use the `okx-frontend` skill. Main and readonly ops pages must stay in
sync. After `dashboard_server.py`, proxy, nginx, or `web/` changes, check
`https://panel.doubaoquant.ltd/view` and `/research`.

## Common pitfalls

- `history-candles` returns each candle as a **list** `[ts,o,h,l,c,vol,...]`.
- Paginate older OKX history with `after`, not `before`.
- Funding is 8-hour. Long-lived contracts have 265-289 lake points; newer
  listings correctly have fewer.
- `data_lake/` is owned by `okxbot`. Root rebuilds break the timer.
- Dashboard restart is not free. Confirm no assumption that it kills
  children (`KillMode=process`), but still avoid bouncing it casually.
- June 2026 BEAT/RE/portfolio-grid memory is historical debris.
