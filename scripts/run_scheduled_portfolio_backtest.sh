#!/usr/bin/env bash
set -euo pipefail

cd /opt/okx-quant

export PYTHONPATH=.
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log_path="/opt/okx-quant/data/okx/portfolio_scheduled_backtest_stdout.log"
run_log="$(mktemp)"

mkdir -p "$(dirname "$log_path")"

backtest_status=1
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
    --allocation-max-risk-events "${PORTFOLIO_SCHEDULE_MAX_RISK_EVENTS:-80}" \
    --core-symbols "${PORTFOLIO_SCHEDULE_CORE_SYMBOLS:-2}" \
    --core-weight-share-pct "${PORTFOLIO_SCHEDULE_CORE_WEIGHT_SHARE_PCT:-70}" \
    --satellite-max-weight-pct "${PORTFOLIO_SCHEDULE_SATELLITE_MAX_WEIGHT_PCT:-15}" \
    --satellite-min-weight-pct "${PORTFOLIO_SCHEDULE_SATELLITE_MIN_WEIGHT_PCT:-3}" \
    --rebalance-threshold-pct "${PORTFOLIO_SCHEDULE_REBALANCE_THRESHOLD_PCT:-1}" \
    --trend-filter "${PORTFOLIO_SCHEDULE_TREND_FILTER:-auto}" \
    --market-regime-filter "${PORTFOLIO_SCHEDULE_MARKET_REGIME_FILTER:-auto}" \
    --market-regime-min-confidence "${PORTFOLIO_SCHEDULE_MARKET_REGIME_MIN_CONFIDENCE:-0.52}" \
    --market-regime-mixed-policy "${PORTFOLIO_SCHEDULE_MARKET_REGIME_MIXED_POLICY:-price_anchor}" \
    --tail-hedge-mode "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_MODE:-dynamic}" \
    --tail-hedge-inst-id "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_INST_ID:-}" \
    --tail-hedge-ratio "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_RATIO:-0.35}" \
    --tail-hedge-stress-ratio "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_RATIO:-0.70}" \
    --tail-hedge-full-ratio "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_RATIO:-1}" \
    --tail-hedge-trigger-net-exposure-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_TRIGGER_NET_EXPOSURE_PCT:-120}" \
    --tail-hedge-trigger-shock-bps "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_TRIGGER_SHOCK_BPS:-120}" \
    --tail-hedge-trigger-trend-bps "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_TRIGGER_TREND_BPS:-350}" \
    --tail-hedge-trigger-risk-events "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_TRIGGER_RISK_EVENTS:-8}" \
    --tail-hedge-stress-net-exposure-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_NET_EXPOSURE_PCT:-180}" \
    --tail-hedge-stress-shock-bps "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_SHOCK_BPS:-180}" \
    --tail-hedge-stress-trend-bps "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_TREND_BPS:-550}" \
    --tail-hedge-stress-risk-events "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_RISK_EVENTS:-40}" \
    --tail-hedge-full-net-exposure-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_NET_EXPOSURE_PCT:-240}" \
    --tail-hedge-full-shock-bps "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_SHOCK_BPS:-260}" \
    --tail-hedge-full-trend-bps "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_TREND_BPS:-800}" \
    --tail-hedge-full-risk-events "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_RISK_EVENTS:-80}" \
    --tail-hedge-min-notional "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_MIN_NOTIONAL:-10}" \
    --tail-hedge-max-margin-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_MAX_MARGIN_PCT:-20}" \
    --tail-hedge-stress-max-margin-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_STRESS_MAX_MARGIN_PCT:-40}" \
    --tail-hedge-full-max-margin-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_FULL_MAX_MARGIN_PCT:-100}" \
    --tail-hedge-leverage "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_LEVERAGE:-3}" \
    --tail-hedge-ord-type "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_ORD_TYPE:-market}" \
    --trading-mode "${PORTFOLIO_SCHEDULE_TRADING_MODE:-live}" \
    --include-account
} > "$run_log" 2>&1
backtest_status="${?}"
set -e
cat "$run_log" >> "$log_path"
if [[ "${backtest_status:-1}" -ne 0 ]]; then
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
  if [[ "${PORTFOLIO_SCHEDULE_AUTO_HEDGE:-1}" == "1" ]]; then
    {
      echo "--- scheduled portfolio tail hedge ${report_dir} ---"
      .venv/bin/python portfolio_tail_hedge.py \
        --report-dir "${report_dir}" \
        --auto \
        --live \
        --confirm-live I_UNDERSTAND \
        --max-plan-age-min "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_MAX_PLAN_AGE_MIN:-120}" \
        --existing-hedge-threshold-pct "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_EXISTING_THRESHOLD_PCT:-95}" \
        --min-remaining-notional "${PORTFOLIO_SCHEDULE_TAIL_HEDGE_MIN_REMAINING_NOTIONAL:-10}"
    } >> "$log_path" 2>&1 || true
  fi
fi
