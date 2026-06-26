#!/usr/bin/env bash
set -euo pipefail

cd /opt/okx-quant

export PYTHONPATH=.
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log_path="/opt/okx-quant/data/okx/portfolio_scheduled_backtest_stdout.log"
run_log="$(mktemp)"

mkdir -p "$(dirname "$log_path")"

set +e
{
  echo
  echo "--- scheduled portfolio backtest start ${started_at} ---"
  .venv/bin/python portfolio_backtest.py \
    --top-n "${PORTFOLIO_SCHEDULE_TOP_N:-12}" \
    --target-symbols "${PORTFOLIO_SCHEDULE_TARGET_SYMBOLS:-4}" \
    --backtest-pages "${PORTFOLIO_SCHEDULE_BACKTEST_PAGES:-2}" \
    --backtest-limit "${PORTFOLIO_SCHEDULE_BACKTEST_LIMIT:-300}" \
    --min-quote-volume "${PORTFOLIO_SCHEDULE_MIN_QUOTE_VOLUME:-5000000}" \
    --max-spread-bps "${PORTFOLIO_SCHEDULE_MAX_SPREAD_BPS:-20}" \
    --starting-equity "${PORTFOLIO_SCHEDULE_STARTING_EQUITY:-100}" \
    --cash-reserve-pct "${PORTFOLIO_SCHEDULE_CASH_RESERVE_PCT:-3}" \
    --allocation-max-risk-events "${PORTFOLIO_SCHEDULE_MAX_RISK_EVENTS:-5}" \
    --core-symbols "${PORTFOLIO_SCHEDULE_CORE_SYMBOLS:-2}" \
    --core-weight-share-pct "${PORTFOLIO_SCHEDULE_CORE_WEIGHT_SHARE_PCT:-70}" \
    --satellite-max-weight-pct "${PORTFOLIO_SCHEDULE_SATELLITE_MAX_WEIGHT_PCT:-15}" \
    --satellite-min-weight-pct "${PORTFOLIO_SCHEDULE_SATELLITE_MIN_WEIGHT_PCT:-3}" \
    --trend-filter "${PORTFOLIO_SCHEDULE_TREND_FILTER:-compare}" \
    --market-regime-filter "${PORTFOLIO_SCHEDULE_MARKET_REGIME_FILTER:-auto}" \
    --market-regime-min-confidence "${PORTFOLIO_SCHEDULE_MARKET_REGIME_MIN_CONFIDENCE:-0.52}" \
    --market-regime-mixed-policy "${PORTFOLIO_SCHEDULE_MARKET_REGIME_MIXED_POLICY:-price_anchor}" \
    --trading-mode "${PORTFOLIO_SCHEDULE_TRADING_MODE:-live}" \
    --include-account
} > "$run_log" 2>&1
backtest_status=$?
set -e
cat "$run_log" >> "$log_path"
if [[ "$backtest_status" -ne 0 ]]; then
  rm -f "$run_log"
  exit "$backtest_status"
fi

report_dir="$(awk -F= '/^portfolio_report=/{value=$2} END{print value}' "$run_log")"
rm -f "$run_log"
if [[ -n "${report_dir}" && -d "${report_dir}" ]]; then
  {
    echo "--- scheduled portfolio preflight ${report_dir} ---"
    .venv/bin/python portfolio_preflight.py "${report_dir}" --include-account
    echo "--- scheduled portfolio live plan ${report_dir} ---"
    .venv/bin/python portfolio_live_plan.py "${report_dir}"
  } >> "$log_path" 2>&1 || true
  if [[ "${PORTFOLIO_SCHEDULE_AUTO_APPLY:-1}" == "1" ]]; then
    {
      echo "--- scheduled portfolio auto apply ${report_dir} ---"
      .venv/bin/python portfolio_auto_apply.py \
        --report-dir "${report_dir}" \
        --confirm-live I_UNDERSTAND \
        --allow-blocked-start \
        --max-changes "${PORTFOLIO_SCHEDULE_AUTO_APPLY_MAX_CHANGES:-4}"
    } >> "$log_path" 2>&1 || true
  fi
fi
