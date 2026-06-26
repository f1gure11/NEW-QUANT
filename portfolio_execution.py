from __future__ import annotations

import csv
import json
import re
import shlex
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import plain, round_to_tick
from market_selector import MarketCandidate
from portfolio_allocator import RebalanceAction, TargetAllocation
from rolling_adaptive import RollingAdaptiveLimits, adaptive_exit_parameters, clamp, lerp, rounded_int, scale_score


@dataclass(slots=True)
class ExecutionConfig:
    trading_mode: str = "paper"
    runtime_subdir: str = "runtime_configs"
    log_dir: str = "data/okx"
    profile_name: str = "portfolio_rolling_adaptive_v1"
    initial_leverage: Decimal = Decimal("7")
    initial_grid_bps: Decimal = Decimal("10")
    initial_adaptive_width_bps: Decimal = Decimal("420")
    initial_adaptive_min_width_bps: Decimal = Decimal("260")
    initial_adaptive_max_width_bps: Decimal = Decimal("1200")
    initial_adaptive_vol_multiplier: Decimal = Decimal("12")
    initial_order_margin_pct: Decimal = Decimal("25")
    initial_max_margin_pct: Decimal = Decimal("75")
    min_net_bps: Decimal = Decimal("1")
    max_open_orders_per_side: int = 5
    max_actions_per_cycle: int = 4
    interval: Decimal = Decimal("8")
    ord_type: str = "post_only"
    total_profit_tp_pct: Decimal = Decimal("1.5")
    total_profit_tp_cap: Decimal = Decimal("0.4")
    total_profit_action: str = "checkpoint"
    min_tp_profit: Decimal = Decimal("0")
    min_tp_bps: Decimal = Decimal("30")
    total_loss_sl_pct: Decimal = Decimal("4")
    total_loss_sl_cap: Decimal = Decimal("0.8")
    position_loss_sl_bps: Decimal = Decimal("700")
    exchange_stop_enabled: bool = True
    exchange_stop_bps: Decimal = Decimal("800")
    exchange_stop_trigger_px_type: str = "mark"
    exchange_stop_reprice_bps: Decimal = Decimal("5")
    missed_tp_ord_type: str = "limit"
    missed_tp_slippage_bps: Decimal = Decimal("20")
    hard_stop_ord_type: str = "market"
    hard_stop_slippage_bps: Decimal = Decimal("50")
    risk_cooldown: Decimal = Decimal("60")
    recenter_on_cooldown: bool = True
    one_way_open: bool = False
    cancel_on_stop: bool = True
    cash_reserve_pct: Decimal = Decimal("10")
    market_regime_filter: str = "off"
    market_regime_model_path: str = ""
    market_regime_min_confidence: Decimal = Decimal("0.52")
    market_regime_mixed_policy: str = "price_anchor"
    rolling_adaptive_enabled: bool = True
    rolling_adaptive_window: int = 20
    rolling_adaptive_low_vol_bps: Decimal = Decimal("3")
    rolling_adaptive_high_vol_bps: Decimal = Decimal("25")
    rolling_adaptive_min_leverage: Decimal = Decimal("3")
    rolling_adaptive_max_leverage: Decimal = Decimal("7")
    rolling_adaptive_min_grid_bps: Decimal = Decimal("8")
    rolling_adaptive_max_grid_bps: Decimal = Decimal("36")
    rolling_adaptive_grid_vol_multiplier: Decimal = Decimal("1.0")
    rolling_adaptive_min_width_bps: Decimal = Decimal("260")
    rolling_adaptive_max_width_bps: Decimal = Decimal("1200")
    rolling_adaptive_width_vol_multiplier: Decimal = Decimal("14")
    rolling_adaptive_min_order_margin_pct: Decimal = Decimal("12")
    rolling_adaptive_max_order_margin_pct: Decimal = Decimal("22")
    rolling_adaptive_min_max_margin_pct: Decimal = Decimal("55")
    rolling_adaptive_max_max_margin_pct: Decimal = Decimal("95")
    rolling_adaptive_min_stop_bps: Decimal = Decimal("700")
    rolling_adaptive_max_stop_bps: Decimal = Decimal("1300")
    rolling_adaptive_stop_vol_multiplier: Decimal = Decimal("26")
    rolling_adaptive_min_tp_bps: Decimal = Decimal("30")
    rolling_adaptive_max_tp_bps: Decimal = Decimal("120")
    rolling_adaptive_tp_grid_multiplier: Decimal = Decimal("1.6")
    rolling_adaptive_min_total_profit_tp_pct: Decimal = Decimal("0.8")
    rolling_adaptive_max_total_profit_tp_pct: Decimal = Decimal("3")
    rolling_adaptive_min_total_loss_sl_pct: Decimal = Decimal("3")
    rolling_adaptive_max_total_loss_sl_pct: Decimal = Decimal("8")
    backtest_tp_return_share: Decimal = Decimal("0.45")
    backtest_sl_drawdown_share: Decimal = Decimal("1.5")
    backtest_min_total_profit_tp_pct: Decimal = Decimal("0.8")
    backtest_max_total_profit_tp_pct: Decimal = Decimal("3.0")
    backtest_min_total_loss_sl_pct: Decimal = Decimal("3.0")
    backtest_max_total_loss_sl_pct: Decimal = Decimal("8.0")
    backtest_min_position_loss_sl_bps: Decimal = Decimal("700")
    backtest_max_position_loss_sl_bps: Decimal = Decimal("1300")
    backtest_min_take_profit_bps: Decimal = Decimal("30")
    backtest_max_take_profit_bps: Decimal = Decimal("120")
    tp_sl_min_ratio: Decimal = Decimal("2.2")
    tp_sl_max_ratio: Decimal = Decimal("3.2")


@dataclass(slots=True)
class ExecutionIntent:
    inst_id: str
    action: str
    status: str
    runtime_config_path: str
    bot_prefix: str
    log_path: str
    stdout_log_path: str
    dry_run_command: str
    requires_private_read: bool
    note: str


EXECUTION_FIELDS = [
    "inst_id",
    "action",
    "status",
    "runtime_config_path",
    "bot_prefix",
    "log_path",
    "stdout_log_path",
    "dry_run_command",
    "requires_private_read",
    "note",
]


def build_execution_intents(
    *,
    targets: list[TargetAllocation],
    actions: list[RebalanceAction],
    candidates: list[MarketCandidate],
    strategy_config: Any,
    output_dir: Path,
    execution_config: ExecutionConfig | None = None,
) -> list[ExecutionIntent]:
    execution_config = execution_config or ExecutionConfig()
    target_by_id = {target.inst_id: target for target in targets}
    candidate_by_id = {candidate.inst_id: candidate for candidate in candidates}
    intents: list[ExecutionIntent] = []
    for action in actions:
        target = target_by_id.get(action.inst_id)
        candidate = candidate_by_id.get(action.inst_id)
        if action.action in {"enter", "increase", "decrease", "hold"} and target and candidate:
            runtime_config = runtime_config_for_target(target, candidate, strategy_config, execution_config)
            runtime_path = output_dir / execution_config.runtime_subdir / f"{safe_name(action.inst_id)}.json"
            log_path = Path(execution_config.log_dir) / f"portfolio_{safe_name(action.inst_id)}_actions.jsonl"
            stdout_path = Path(execution_config.log_dir) / f"portfolio_{safe_name(action.inst_id)}_stdout.log"
            bot_prefix = bot_prefix_for_inst(action.inst_id)
            command = dry_run_command(
                action.inst_id,
                runtime_path,
                log_path,
                bot_prefix,
                runtime_config,
            )
            intents.append(
                ExecutionIntent(
                    inst_id=action.inst_id,
                    action=action.action,
                    status="runtime_config_ready",
                    runtime_config_path=str(runtime_path),
                    bot_prefix=bot_prefix,
                    log_path=str(log_path),
                    stdout_log_path=str(stdout_path),
                    dry_run_command=command,
                    requires_private_read=True,
                    note="one-cycle bot dry run; reads account state but has no --live flag",
                )
            )
            if action.action != "decrease":
                continue
        if action.action in {"decrease", "exit"}:
            log_path = Path(execution_config.log_dir) / "portfolio_rebalancer_actions.jsonl"
            command = rebalance_reduce_command(output_dir, action.inst_id, log_path, execution_config)
            intents.append(
                ExecutionIntent(
                    inst_id=action.inst_id,
                    action=action.action,
                    status="rebalance_reduce_ready",
                    runtime_config_path="",
                    bot_prefix="",
                    log_path=str(log_path),
                    stdout_log_path="",
                    dry_run_command=command,
                    requires_private_read=True,
                    note="reduce-only rebalance dry run; reads account state but has no --live flag",
                )
            )
            continue

        status = "no_action"
        note = action.note
        intents.append(
            ExecutionIntent(
                inst_id=action.inst_id,
                action=action.action,
                status=status,
                runtime_config_path="",
                bot_prefix="",
                log_path="",
                stdout_log_path="",
                dry_run_command="",
                requires_private_read=False,
                note=note,
            )
        )
    return intents


def rebalance_reduce_command(
    report_dir: Path,
    inst_id: str,
    log_path: Path,
    execution_config: ExecutionConfig,
) -> str:
    parts = [
        "PYTHONPATH=.",
        ".venv/bin/python",
        "portfolio_rebalancer.py",
        "--report-dir",
        str(report_dir),
        "--inst-id",
        inst_id,
        "--log-path",
        str(log_path),
        "--ord-type",
        execution_config.hard_stop_ord_type,
        "--slippage-bps",
        str(execution_config.hard_stop_slippage_bps),
        "--once",
    ]
    if execution_config.cancel_on_stop:
        parts.extend(["--cancel-pending", "--cancel-algos"])
    return shlex.join(parts)


def write_execution_bundle(
    *,
    targets: list[TargetAllocation],
    actions: list[RebalanceAction],
    candidates: list[MarketCandidate],
    strategy_config: Any,
    output_dir: Path,
    execution_config: ExecutionConfig | None = None,
) -> list[ExecutionIntent]:
    execution_config = execution_config or ExecutionConfig()
    intents = build_execution_intents(
        targets=targets,
        actions=actions,
        candidates=candidates,
        strategy_config=strategy_config,
        output_dir=output_dir,
        execution_config=execution_config,
    )
    runtime_dir = output_dir / execution_config.runtime_subdir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target_by_id = {target.inst_id: target for target in targets}
    candidate_by_id = {candidate.inst_id: candidate for candidate in candidates}
    for intent in intents:
        if intent.status != "runtime_config_ready" or not intent.runtime_config_path:
            continue
        target = target_by_id[intent.inst_id]
        candidate = candidate_by_id[intent.inst_id]
        runtime_config = runtime_config_for_target(target, candidate, strategy_config, execution_config)
        Path(intent.runtime_config_path).write_text(json.dumps(runtime_config, indent=2), encoding="utf-8")

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "dry_run_execution_bundle",
        "execution": execution_config_to_dict(execution_config),
        "intents": [intent_to_dict(intent) for intent in intents],
    }
    (output_dir / "execution_intents.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output_dir / "execution_intents.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=EXECUTION_FIELDS)
        writer.writeheader()
        for intent in intents:
            row = intent_to_dict(intent)
            writer.writerow({field: row.get(field, "") for field in EXECUTION_FIELDS})
    return intents


def runtime_config_for_target(
    target: TargetAllocation,
    candidate: MarketCandidate,
    strategy_config: Any,
    execution_config: ExecutionConfig | None = None,
) -> dict[str, Any]:
    execution_config = execution_config or ExecutionConfig()
    outer_range_bps = dec(getattr(strategy_config, "outer_range_bps", Decimal("1200")))
    half_width = outer_range_bps / Decimal("20000")
    lower = round_to_tick(target.last * (Decimal("1") - half_width), candidate.tick_sz)
    upper = round_to_tick(target.last * (Decimal("1") + half_width), candidate.tick_sz)
    if lower <= 0:
        lower = candidate.tick_sz
    if upper <= lower:
        upper = lower + candidate.tick_sz
    adaptive = pool_adaptive_runtime_values(target, execution_config)
    risk_reward = backtest_risk_reward_values(target, adaptive, execution_config)

    return {
        "instId": target.inst_id,
        "portfolioTradingMode": execution_config.trading_mode,
        "strategyProfile": execution_config.profile_name,
        "lower": plain(lower),
        "upper": plain(upper),
        "leverage": plain(execution_config.initial_leverage),
        "gridBps": plain(execution_config.initial_grid_bps),
        "minNetBps": plain(execution_config.min_net_bps),
        "softBps": plain(dec(getattr(strategy_config, "soft_bps", Decimal("45")))),
        "hardBps": plain(dec(getattr(strategy_config, "hard_bps", Decimal("80")))),
        "mode": "adaptive",
        "adaptiveWidthBps": plain(execution_config.initial_adaptive_width_bps),
        "adaptiveMinWidthBps": plain(execution_config.initial_adaptive_min_width_bps),
        "adaptiveMaxWidthBps": plain(execution_config.initial_adaptive_max_width_bps),
        "adaptiveVolMultiplier": plain(execution_config.initial_adaptive_vol_multiplier),
        "rangeDriftMode": "cooldown",
        "rangeDriftWeightBps": plain(dec(getattr(strategy_config, "range_drift_weight_bps", Decimal("5000")))),
        "rangeDriftMaxBps": plain(dec(getattr(strategy_config, "range_drift_max_bps", Decimal("500")))),
        "sizingMode": "margin_pct" if execution_config.rolling_adaptive_enabled else "fixed",
        "orderMarginPct": plain(execution_config.initial_order_margin_pct),
        "maxMarginPct": plain(execution_config.initial_max_margin_pct),
        "cashReservePct": plain(execution_config.cash_reserve_pct),
        "orderSz": plain(target.order_sz),
        "maxPosition": plain(target.max_position),
        "maxOpenOrdersPerSide": str(execution_config.max_open_orders_per_side),
        "maxActionsPerCycle": str(execution_config.max_actions_per_cycle),
        "interval": plain(execution_config.interval),
        "ordType": execution_config.ord_type,
        "totalProfitTp": "0",
        "totalProfitTpPct": plain(execution_config.total_profit_tp_pct),
        "totalProfitTpCap": plain(execution_config.total_profit_tp_cap),
        "totalProfitAction": execution_config.total_profit_action,
        "minTpProfit": plain(execution_config.min_tp_profit),
        "minTpBps": plain(execution_config.min_tp_bps),
        "totalLossSl": "0",
        "totalLossSlPct": plain(execution_config.total_loss_sl_pct),
        "totalLossSlCap": plain(execution_config.total_loss_sl_cap),
        "positionLossSlBps": plain(execution_config.position_loss_sl_bps),
        "exchangeStopEnabled": execution_config.exchange_stop_enabled,
        "exchangeStopBps": plain(execution_config.exchange_stop_bps),
        "exchangeStopTriggerPxType": execution_config.exchange_stop_trigger_px_type,
        "exchangeStopRepriceBps": plain(execution_config.exchange_stop_reprice_bps),
        "missedTpOrdType": execution_config.missed_tp_ord_type,
        "missedTpSlippageBps": plain(execution_config.missed_tp_slippage_bps),
        "hardStopOrdType": execution_config.hard_stop_ord_type,
        "hardStopSlippageBps": plain(execution_config.hard_stop_slippage_bps),
        "riskCooldown": plain(execution_config.risk_cooldown),
        "recenterOnCooldown": execution_config.recenter_on_cooldown,
        "trendFilter": runtime_trend_filter(target),
        "trendLookback": str(int(getattr(strategy_config, "trend_lookback", 8))),
        "trendThresholdBps": plain(dec(getattr(strategy_config, "trend_threshold_bps", Decimal("90")))),
        "marketRegimeFilter": execution_config.market_regime_filter,
        "marketRegimeModelPath": execution_config.market_regime_model_path,
        "marketRegimeMinConfidence": plain(execution_config.market_regime_min_confidence),
        "marketRegimeMixedPolicy": execution_config.market_regime_mixed_policy,
        "marketRegimeSignal": str(getattr(target, "market_regime_signal", "")),
        "marketRegimeConfidence": plain(dec(getattr(target, "market_regime_confidence", Decimal("0")))),
        "marketRegimeAllowedSides": str(getattr(target, "market_regime_allowed_sides", "")),
        "mlScoreDeltaVsBaseline": plain(dec(getattr(target, "ml_score_delta_vs_baseline", Decimal("0")))),
        "mlReturnDeltaVsBaseline": plain(dec(getattr(target, "ml_return_delta_vs_baseline", Decimal("0")))),
        "mlDrawdownDeltaVsBaseline": plain(dec(getattr(target, "ml_drawdown_delta_vs_baseline", Decimal("0")))),
        "mlRiskEventDeltaVsBaseline": str(int(getattr(target, "ml_risk_event_delta_vs_baseline", 0))),
        "regimeFilter": "off",
        "regimeBar": str(getattr(strategy_config, "regime_bar", "15m")),
        "regimeShortMa": str(int(getattr(strategy_config, "regime_short_ma", 5))),
        "regimeLongMa": str(int(getattr(strategy_config, "regime_long_ma", 20))),
        "regimeDiffBps": plain(dec(getattr(strategy_config, "regime_diff_bps", Decimal("50")))),
        "regimeConfirmBars": str(int(getattr(strategy_config, "regime_confirm_bars", 3))),
        "oneWayOpen": execution_config.one_way_open,
        "cancelOnStop": execution_config.cancel_on_stop,
        "setLeverage": execution_config.rolling_adaptive_enabled,
        "rollingAdaptiveEnabled": execution_config.rolling_adaptive_enabled,
        "rollingAdaptiveWindow": str(execution_config.rolling_adaptive_window),
        "rollingAdaptiveLowVolBps": plain(execution_config.rolling_adaptive_low_vol_bps),
        "rollingAdaptiveHighVolBps": plain(execution_config.rolling_adaptive_high_vol_bps),
        "rollingAdaptiveMinLeverage": plain(execution_config.rolling_adaptive_min_leverage),
        "rollingAdaptiveMaxLeverage": plain(execution_config.rolling_adaptive_max_leverage),
        "rollingAdaptiveMinGridBps": plain(execution_config.rolling_adaptive_min_grid_bps),
        "rollingAdaptiveMaxGridBps": plain(execution_config.rolling_adaptive_max_grid_bps),
        "rollingAdaptiveGridVolMultiplier": plain(execution_config.rolling_adaptive_grid_vol_multiplier),
        "rollingAdaptiveMinWidthBps": plain(execution_config.rolling_adaptive_min_width_bps),
        "rollingAdaptiveMaxWidthBps": plain(execution_config.rolling_adaptive_max_width_bps),
        "rollingAdaptiveWidthVolMultiplier": plain(execution_config.rolling_adaptive_width_vol_multiplier),
        "rollingAdaptiveMinOrderMarginPct": plain(execution_config.rolling_adaptive_min_order_margin_pct),
        "rollingAdaptiveMaxOrderMarginPct": plain(execution_config.rolling_adaptive_max_order_margin_pct),
        "rollingAdaptiveMinMaxMarginPct": plain(execution_config.rolling_adaptive_min_max_margin_pct),
        "rollingAdaptiveMaxMaxMarginPct": plain(execution_config.rolling_adaptive_max_max_margin_pct),
        "rollingAdaptiveMinStopBps": plain(execution_config.rolling_adaptive_min_stop_bps),
        "rollingAdaptiveMaxStopBps": plain(execution_config.rolling_adaptive_max_stop_bps),
        "rollingAdaptiveStopVolMultiplier": plain(execution_config.rolling_adaptive_stop_vol_multiplier),
        "rollingAdaptiveMinTpBps": plain(execution_config.rolling_adaptive_min_tp_bps),
        "rollingAdaptiveMaxTpBps": plain(execution_config.rolling_adaptive_max_tp_bps),
        "rollingAdaptiveTpGridMultiplier": plain(execution_config.rolling_adaptive_tp_grid_multiplier),
        "rollingAdaptiveMinTotalProfitTpPct": plain(execution_config.rolling_adaptive_min_total_profit_tp_pct),
        "rollingAdaptiveMaxTotalProfitTpPct": plain(execution_config.rolling_adaptive_max_total_profit_tp_pct),
        "rollingAdaptiveMinTotalLossSlPct": plain(execution_config.rolling_adaptive_min_total_loss_sl_pct),
        "rollingAdaptiveMaxTotalLossSlPct": plain(execution_config.rolling_adaptive_max_total_loss_sl_pct),
        "poolAdaptiveWindowHours": plain(target.pool_window_hours),
        "poolAdaptiveWindowBars": str(target.pool_window_bars),
        "poolAdaptiveAvgAbsBps": plain(target.pool_avg_abs_bps),
        "poolAdaptiveShockBps": plain(target.pool_shock_bps),
        "poolAdaptiveTrendBps": plain(target.pool_trend_bps),
        "poolAdaptiveRiskScore": plain(adaptive["risk_score"]),
        "poolAdaptiveNote": adaptive["note"],
        "backtestTotalReturnPct": plain(target.total_return_pct),
        "backtestMaxDrawdownPct": plain(target.max_drawdown_pct),
        "backtestProfitFactor": plain(target.profit_factor),
        "backtestFills": str(target.fills),
        "backtestRiskEvents": str(target.risk_events),
        "backtestWinRatePct": plain(target.win_rate_pct),
        "backtestRiskRewardScore": plain(risk_reward["risk_reward_score"]),
        "backtestTargetSlRatio": plain(risk_reward["target_sl_ratio"]),
        "backtestRiskRewardNote": f"{risk_reward['note']}; strategy uses {execution_config.profile_name} runtime seed",
        "trendFilterChecked": bool(getattr(target, "trend_filter_checked", False)),
        "trendScoreDelta": plain(dec(getattr(target, "trend_score_delta", Decimal("0")))),
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "portfolioTargetWeightPct": plain(target.weight_pct),
        "portfolioTargetMargin": plain(target.target_margin),
        "portfolioTargetNotional": plain(target.target_notional),
        "portfolioRole": target.role,
        "portfolioGenerated": True,
    }


def runtime_trend_filter(target: TargetAllocation) -> str:
    selected = str(getattr(target, "selected_trend_filter", "") or "off").strip()
    return selected if selected in {"off", "auto"} else "off"


def pool_adaptive_runtime_values(
    target: TargetAllocation,
    execution_config: ExecutionConfig,
) -> dict[str, Any]:
    limits = execution_limits(execution_config)
    rolling_vol_bps = max(target.pool_avg_abs_bps, target.pool_shock_bps / Decimal("3"))
    vol_score = scale_score(rolling_vol_bps, limits.low_vol_bps, limits.high_vol_bps)
    trend_score = scale_score(abs(target.pool_trend_bps), limits.low_vol_bps * Decimal("2"), limits.high_vol_bps * Decimal("3"))
    risk_score = max(vol_score, trend_score / Decimal("2"))

    leverage = rounded_int(lerp(limits.max_leverage, limits.min_leverage, risk_score))
    leverage = clamp(leverage, limits.min_leverage, limits.max_leverage)
    if leverage <= 0:
        leverage = Decimal("1")

    grid_bps = clamp(
        rolling_vol_bps * limits.grid_vol_multiplier,
        limits.min_grid_bps,
        limits.max_grid_bps,
    )
    adaptive_width_bps = clamp(
        rolling_vol_bps * limits.width_vol_multiplier,
        limits.min_width_bps,
        limits.max_width_bps,
    )
    adaptive_min_width_bps = clamp(adaptive_width_bps * Decimal("0.75"), limits.min_width_bps, limits.max_width_bps)
    adaptive_max_width_bps = clamp(adaptive_width_bps * Decimal("1.35"), limits.min_width_bps, limits.max_width_bps)
    if adaptive_max_width_bps < adaptive_min_width_bps:
        adaptive_max_width_bps = adaptive_min_width_bps

    order_margin_pct = clamp(
        lerp(limits.max_order_margin_pct, limits.min_order_margin_pct, risk_score),
        limits.min_order_margin_pct,
        limits.max_order_margin_pct,
    )
    max_margin_pct = clamp(
        lerp(limits.max_max_margin_pct, limits.min_max_margin_pct, risk_score),
        limits.min_max_margin_pct,
        limits.max_max_margin_pct,
    )

    exit_params = adaptive_exit_parameters(grid_bps, rolling_vol_bps, risk_score, limits)
    min_tp_bps = exit_params["min_tp_bps"]
    position_loss_sl_bps = exit_params["position_loss_sl_bps"]
    exchange_stop_bps = exit_params["exchange_stop_bps"]
    total_profit_tp_pct = exit_params["total_profit_tp_pct"]
    total_loss_sl_pct = exit_params["total_loss_sl_pct"]

    regime_note = ""
    target_regime = str(getattr(target, "market_regime_signal", "") or "")
    if execution_config.market_regime_filter != "off":
        allowed = str(getattr(target, "market_regime_allowed_sides", "") or "none")
        confidence = plain(dec(getattr(target, "market_regime_confidence", Decimal("0"))))
        regime_note = (
            f"; ml_regime={execution_config.market_regime_filter}/{target_regime or 'unknown'} "
            f"conf={confidence} sides={allowed}"
        )
    note = (
        f"pool {plain(target.pool_window_hours)}h avg_abs={plain(target.pool_avg_abs_bps)}bps "
        f"shock={plain(target.pool_shock_bps)}bps trend={plain(target.pool_trend_bps)}bps "
        f"risk={plain(risk_score)}{regime_note}"
    )
    return {
        "risk_score": q(risk_score),
        "leverage": leverage,
        "grid_bps": q(grid_bps),
        "adaptive_width_bps": q(adaptive_width_bps),
        "adaptive_min_width_bps": q(adaptive_min_width_bps),
        "adaptive_max_width_bps": q(adaptive_max_width_bps),
        "order_margin_pct": q(order_margin_pct),
        "max_margin_pct": q(max_margin_pct),
        "min_tp_bps": q(min_tp_bps),
        "position_loss_sl_bps": q(position_loss_sl_bps),
        "exchange_stop_bps": q(exchange_stop_bps),
        "total_profit_tp_pct": q(total_profit_tp_pct),
        "total_loss_sl_pct": q(total_loss_sl_pct),
        "note": note,
    }


def backtest_risk_reward_values(
    target: TargetAllocation,
    adaptive: dict[str, Any],
    execution_config: ExecutionConfig,
) -> dict[str, Any]:
    total_return_pct = max(Decimal("0"), dec(target.total_return_pct))
    max_drawdown_pct = max(Decimal("0"), dec(target.max_drawdown_pct))
    profit_factor = max(Decimal("0"), dec(target.profit_factor))
    fills = max(Decimal("0"), Decimal(target.fills))
    risk_events = max(Decimal("0"), Decimal(target.risk_events))

    pf_score = clamp((profit_factor - Decimal("1")) / Decimal("2"), Decimal("0"), Decimal("1"))
    return_score = scale_score(total_return_pct, Decimal("0"), Decimal("8"))
    fill_score = clamp(fills / Decimal("20"), Decimal("0"), Decimal("1"))
    drawdown_score = scale_score(max_drawdown_pct, Decimal("1"), Decimal("8"))
    risk_event_score = clamp(risk_events / Decimal("3"), Decimal("0"), Decimal("1"))
    reward_score = (pf_score + return_score + fill_score) / Decimal("3")
    risk_score = max(drawdown_score, risk_event_score)
    risk_reward_score = clamp(reward_score - risk_score / Decimal("2"), Decimal("0"), Decimal("1"))

    adaptive_tp_pct = dec(adaptive.get("total_profit_tp_pct"))
    adaptive_sl_pct = dec(adaptive.get("total_loss_sl_pct"))
    adaptive_tp_bps = dec(adaptive.get("min_tp_bps"))
    adaptive_sl_bps = dec(adaptive.get("position_loss_sl_bps"))
    adaptive_exchange_bps = dec(adaptive.get("exchange_stop_bps"))

    tp_from_return = total_return_pct * execution_config.backtest_tp_return_share
    total_profit_tp_pct = clamp(
        max(adaptive_tp_pct, tp_from_return),
        execution_config.backtest_min_total_profit_tp_pct,
        execution_config.backtest_max_total_profit_tp_pct,
    )

    sl_from_drawdown = max_drawdown_pct * execution_config.backtest_sl_drawdown_share
    ratio_score = clamp(risk_score + (Decimal("1") - risk_reward_score) / Decimal("2"), Decimal("0"), Decimal("1"))
    target_sl_ratio = lerp(execution_config.tp_sl_max_ratio, execution_config.tp_sl_min_ratio, ratio_score)
    ratio_stop_pct = total_profit_tp_pct * target_sl_ratio
    if risk_events > 0:
        sl_from_drawdown *= max(Decimal("0.8"), Decimal("1") - Decimal("0.05") * risk_events)
    drawdown_tightener = clamp(Decimal("1") - drawdown_score * Decimal("0.18"), Decimal("0.75"), Decimal("1"))
    risk_event_tightener = clamp(Decimal("1") - risk_event_score * Decimal("0.12"), Decimal("0.8"), Decimal("1"))
    stop_budget_pct = max(adaptive_sl_pct, sl_from_drawdown, ratio_stop_pct) * drawdown_tightener * risk_event_tightener
    total_loss_sl_pct = clamp(
        stop_budget_pct,
        execution_config.backtest_min_total_loss_sl_pct,
        execution_config.backtest_max_total_loss_sl_pct,
    )
    min_ratio_loss_pct = total_profit_tp_pct * execution_config.tp_sl_min_ratio
    if total_loss_sl_pct < min_ratio_loss_pct:
        total_loss_sl_pct = clamp(
            min_ratio_loss_pct,
            execution_config.backtest_min_total_loss_sl_pct,
            execution_config.backtest_max_total_loss_sl_pct,
        )
    max_ratio_loss_pct = total_profit_tp_pct * execution_config.tp_sl_max_ratio
    if total_loss_sl_pct > max_ratio_loss_pct:
        total_loss_sl_pct = clamp(
            max_ratio_loss_pct,
            execution_config.backtest_min_total_loss_sl_pct,
            execution_config.backtest_max_total_loss_sl_pct,
        )

    tp_multiplier = lerp(Decimal("0.9"), Decimal("1.25"), risk_reward_score)
    sl_multiplier = lerp(Decimal("0.78"), Decimal("1.2"), risk_score)
    min_tp_bps = clamp(
        adaptive_tp_bps * tp_multiplier,
        execution_config.backtest_min_take_profit_bps,
        execution_config.backtest_max_take_profit_bps,
    )
    stop_floor_bps = min_tp_bps * Decimal("1.35")
    risk_tightener = clamp(Decimal("1") - risk_score * Decimal("0.18"), Decimal("0.75"), Decimal("1"))
    position_loss_sl_bps = clamp(
        max(adaptive_sl_bps * sl_multiplier * risk_tightener, stop_floor_bps),
        execution_config.backtest_min_position_loss_sl_bps,
        execution_config.backtest_max_position_loss_sl_bps,
    )
    exchange_stop_bps = clamp(
        max(adaptive_exchange_bps, position_loss_sl_bps * Decimal("1.08")),
        execution_config.backtest_min_position_loss_sl_bps,
        execution_config.backtest_max_position_loss_sl_bps,
    )

    note = (
        f"backtest ret={plain(total_return_pct)}% dd={plain(max_drawdown_pct)}% "
        f"pf={plain(profit_factor)} fills={plain(fills)} risk_events={plain(risk_events)} "
        f"reward={plain(reward_score)} risk={plain(risk_score)}"
    )
    return {
        "risk_reward_score": q(risk_reward_score),
        "total_profit_tp_pct": q(total_profit_tp_pct),
        "total_loss_sl_pct": q(total_loss_sl_pct),
        "min_tp_bps": q(min_tp_bps),
        "position_loss_sl_bps": q(position_loss_sl_bps),
        "exchange_stop_bps": q(exchange_stop_bps),
        "target_sl_ratio": q(target_sl_ratio),
        "note": note,
    }


def execution_limits(execution_config: ExecutionConfig) -> RollingAdaptiveLimits:
    return RollingAdaptiveLimits(
        window=execution_config.rolling_adaptive_window,
        low_vol_bps=execution_config.rolling_adaptive_low_vol_bps,
        high_vol_bps=execution_config.rolling_adaptive_high_vol_bps,
        min_leverage=execution_config.rolling_adaptive_min_leverage,
        max_leverage=execution_config.rolling_adaptive_max_leverage,
        min_grid_bps=execution_config.rolling_adaptive_min_grid_bps,
        max_grid_bps=execution_config.rolling_adaptive_max_grid_bps,
        grid_vol_multiplier=execution_config.rolling_adaptive_grid_vol_multiplier,
        min_width_bps=execution_config.rolling_adaptive_min_width_bps,
        max_width_bps=execution_config.rolling_adaptive_max_width_bps,
        width_vol_multiplier=execution_config.rolling_adaptive_width_vol_multiplier,
        min_order_margin_pct=execution_config.rolling_adaptive_min_order_margin_pct,
        max_order_margin_pct=execution_config.rolling_adaptive_max_order_margin_pct,
        min_max_margin_pct=execution_config.rolling_adaptive_min_max_margin_pct,
        max_max_margin_pct=execution_config.rolling_adaptive_max_max_margin_pct,
        min_stop_bps=execution_config.rolling_adaptive_min_stop_bps,
        max_stop_bps=execution_config.rolling_adaptive_max_stop_bps,
        stop_vol_multiplier=execution_config.rolling_adaptive_stop_vol_multiplier,
        min_tp_bps=execution_config.rolling_adaptive_min_tp_bps,
        max_tp_bps=execution_config.rolling_adaptive_max_tp_bps,
        tp_grid_multiplier=execution_config.rolling_adaptive_tp_grid_multiplier,
        min_total_profit_tp_pct=execution_config.rolling_adaptive_min_total_profit_tp_pct,
        max_total_profit_tp_pct=execution_config.rolling_adaptive_max_total_profit_tp_pct,
        min_total_loss_sl_pct=execution_config.rolling_adaptive_min_total_loss_sl_pct,
        max_total_loss_sl_pct=execution_config.rolling_adaptive_max_total_loss_sl_pct,
    )


def q(value: Decimal, places: str = "0.0001") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP).normalize()


def dry_run_command(
    inst_id: str,
    runtime_path: Path,
    log_path: Path,
    bot_prefix: str,
    runtime_config: dict[str, Any],
) -> str:
    parts = [
        "PYTHONPATH=.",
        ".venv/bin/python",
        "auto_grid_bot.py",
        "--inst-id",
        inst_id,
        "--runtime-config",
        str(runtime_path),
        "--log-path",
        str(log_path),
        "--bot-prefix",
        bot_prefix,
        "--lower",
        str(runtime_config["lower"]),
        "--upper",
        str(runtime_config["upper"]),
        "--leverage",
        str(runtime_config["leverage"]),
        "--grid-bps",
        str(runtime_config["gridBps"]),
        "--min-net-bps",
        str(runtime_config["minNetBps"]),
        "--soft-bps",
        str(runtime_config["softBps"]),
        "--hard-bps",
        str(runtime_config["hardBps"]),
        "--order-sz",
        str(runtime_config["orderSz"]),
        "--max-position",
        str(runtime_config["maxPosition"]),
        "--max-open-orders-per-side",
        str(runtime_config["maxOpenOrdersPerSide"]),
        "--max-actions-per-cycle",
        str(runtime_config["maxActionsPerCycle"]),
        "--interval",
        str(runtime_config["interval"]),
        "--ord-type",
        str(runtime_config["ordType"]),
        "--mode",
        str(runtime_config["mode"]),
        "--adaptive-width-bps",
        str(runtime_config["adaptiveWidthBps"]),
        "--adaptive-min-width-bps",
        str(runtime_config["adaptiveMinWidthBps"]),
        "--adaptive-max-width-bps",
        str(runtime_config["adaptiveMaxWidthBps"]),
        "--adaptive-vol-multiplier",
        str(runtime_config["adaptiveVolMultiplier"]),
        "--range-drift-mode",
        str(runtime_config["rangeDriftMode"]),
        "--range-drift-weight-bps",
        str(runtime_config["rangeDriftWeightBps"]),
        "--range-drift-max-bps",
        str(runtime_config["rangeDriftMaxBps"]),
        "--sizing-mode",
        str(runtime_config["sizingMode"]),
        "--order-margin-pct",
        str(runtime_config["orderMarginPct"]),
        "--max-margin-pct",
        str(runtime_config["maxMarginPct"]),
        "--cash-reserve-pct",
        str(runtime_config["cashReservePct"]),
        "--total-profit-tp",
        str(runtime_config["totalProfitTp"]),
        "--total-profit-tp-pct",
        str(runtime_config["totalProfitTpPct"]),
        "--total-profit-tp-cap",
        str(runtime_config["totalProfitTpCap"]),
        "--total-profit-action",
        str(runtime_config["totalProfitAction"]),
        "--min-tp-profit",
        str(runtime_config["minTpProfit"]),
        "--min-tp-bps",
        str(runtime_config["minTpBps"]),
        "--total-loss-sl",
        str(runtime_config["totalLossSl"]),
        "--total-loss-sl-pct",
        str(runtime_config["totalLossSlPct"]),
        "--total-loss-sl-cap",
        str(runtime_config["totalLossSlCap"]),
        "--position-loss-sl-bps",
        str(runtime_config["positionLossSlBps"]),
        "--exchange-stop-bps",
        str(runtime_config["exchangeStopBps"]),
        "--exchange-stop-trigger-px-type",
        str(runtime_config["exchangeStopTriggerPxType"]),
        "--exchange-stop-reprice-bps",
        str(runtime_config["exchangeStopRepriceBps"]),
        "--missed-tp-ord-type",
        str(runtime_config["missedTpOrdType"]),
        "--missed-tp-slippage-bps",
        str(runtime_config["missedTpSlippageBps"]),
        "--hard-stop-ord-type",
        str(runtime_config["hardStopOrdType"]),
        "--hard-stop-slippage-bps",
        str(runtime_config["hardStopSlippageBps"]),
        "--risk-cooldown",
        str(runtime_config["riskCooldown"]),
        "--trend-filter",
        str(runtime_config["trendFilter"]),
        "--trend-lookback",
        str(runtime_config["trendLookback"]),
        "--trend-threshold-bps",
        str(runtime_config["trendThresholdBps"]),
        "--market-regime-filter",
        str(runtime_config["marketRegimeFilter"]),
        "--market-regime-model-path",
        str(runtime_config["marketRegimeModelPath"]),
        "--market-regime-min-confidence",
        str(runtime_config["marketRegimeMinConfidence"]),
        "--market-regime-mixed-policy",
        str(runtime_config["marketRegimeMixedPolicy"]),
        "--regime-filter",
        str(runtime_config["regimeFilter"]),
        "--regime-bar",
        str(runtime_config["regimeBar"]),
        "--regime-short-ma",
        str(runtime_config["regimeShortMa"]),
        "--regime-long-ma",
        str(runtime_config["regimeLongMa"]),
        "--regime-diff-bps",
        str(runtime_config["regimeDiffBps"]),
        "--regime-confirm-bars",
        str(runtime_config["regimeConfirmBars"]),
        "--once",
    ]
    if runtime_config.get("rollingAdaptiveEnabled"):
        parts.extend(
            [
                "--rolling-adaptive",
                "--rolling-adaptive-window",
                str(runtime_config["rollingAdaptiveWindow"]),
                "--rolling-adaptive-low-vol-bps",
                str(runtime_config["rollingAdaptiveLowVolBps"]),
                "--rolling-adaptive-high-vol-bps",
                str(runtime_config["rollingAdaptiveHighVolBps"]),
                "--rolling-adaptive-min-leverage",
                str(runtime_config["rollingAdaptiveMinLeverage"]),
                "--rolling-adaptive-max-leverage",
                str(runtime_config["rollingAdaptiveMaxLeverage"]),
                "--rolling-adaptive-min-grid-bps",
                str(runtime_config["rollingAdaptiveMinGridBps"]),
                "--rolling-adaptive-max-grid-bps",
                str(runtime_config["rollingAdaptiveMaxGridBps"]),
                "--rolling-adaptive-grid-vol-multiplier",
                str(runtime_config["rollingAdaptiveGridVolMultiplier"]),
                "--rolling-adaptive-min-width-bps",
                str(runtime_config["rollingAdaptiveMinWidthBps"]),
                "--rolling-adaptive-max-width-bps",
                str(runtime_config["rollingAdaptiveMaxWidthBps"]),
                "--rolling-adaptive-width-vol-multiplier",
                str(runtime_config["rollingAdaptiveWidthVolMultiplier"]),
                "--rolling-adaptive-min-order-margin-pct",
                str(runtime_config["rollingAdaptiveMinOrderMarginPct"]),
                "--rolling-adaptive-max-order-margin-pct",
                str(runtime_config["rollingAdaptiveMaxOrderMarginPct"]),
                "--rolling-adaptive-min-max-margin-pct",
                str(runtime_config["rollingAdaptiveMinMaxMarginPct"]),
                "--rolling-adaptive-max-max-margin-pct",
                str(runtime_config["rollingAdaptiveMaxMaxMarginPct"]),
                "--rolling-adaptive-min-stop-bps",
                str(runtime_config["rollingAdaptiveMinStopBps"]),
                "--rolling-adaptive-max-stop-bps",
                str(runtime_config["rollingAdaptiveMaxStopBps"]),
                "--rolling-adaptive-stop-vol-multiplier",
                str(runtime_config["rollingAdaptiveStopVolMultiplier"]),
                "--rolling-adaptive-min-tp-bps",
                str(runtime_config["rollingAdaptiveMinTpBps"]),
                "--rolling-adaptive-max-tp-bps",
                str(runtime_config["rollingAdaptiveMaxTpBps"]),
                "--rolling-adaptive-tp-grid-multiplier",
                str(runtime_config["rollingAdaptiveTpGridMultiplier"]),
                "--rolling-adaptive-min-total-profit-tp-pct",
                str(runtime_config["rollingAdaptiveMinTotalProfitTpPct"]),
                "--rolling-adaptive-max-total-profit-tp-pct",
                str(runtime_config["rollingAdaptiveMaxTotalProfitTpPct"]),
                "--rolling-adaptive-min-total-loss-sl-pct",
                str(runtime_config["rollingAdaptiveMinTotalLossSlPct"]),
                "--rolling-adaptive-max-total-loss-sl-pct",
                str(runtime_config["rollingAdaptiveMaxTotalLossSlPct"]),
            ]
        )
    if runtime_config.get("setLeverage"):
        parts.append("--set-leverage")
    if runtime_config.get("exchangeStopEnabled"):
        parts.append("--exchange-stop-enabled")
    if runtime_config.get("cancelOnStop"):
        parts.append("--cancel-on-stop")
    if not runtime_config.get("recenterOnCooldown", True):
        parts.append("--no-recenter-on-cooldown")
    if not runtime_config.get("oneWayOpen", True):
        parts.append("--allow-dual-open")
    return shlex.join(parts)


def safe_name(inst_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", inst_id.lower()).strip("_")


def bot_prefix_for_inst(inst_id: str) -> str:
    base = inst_id.split("-")[0].lower()
    clean = re.sub(r"[^a-z0-9]", "", base)
    return f"p{clean}"[:8] or "pbot"


def intent_to_dict(intent: ExecutionIntent) -> dict[str, Any]:
    return jsonable(asdict(intent))


def execution_config_to_dict(config: ExecutionConfig) -> dict[str, Any]:
    return jsonable(asdict(config))


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default
