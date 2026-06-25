from __future__ import annotations

import argparse
import json
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from okx_client import OkxApiError, OkxRestClient, load_env
from rolling_adaptive import RollingAdaptiveLimits, calculate_rolling_adaptive, result_to_dict


LOG_PATH = Path("data") / "okx" / "grid_bot_actions.jsonl"
RUNTIME_CONFIG_PATH = Path("data") / "okx" / "grid_bot_runtime_config.json"
BOT_PREFIX = "gb"
OPEN_ORDER_MARGIN_SAFETY = Decimal("2.5")


@dataclass(slots=True)
class BotConfig:
    inst_id: str
    lower: Decimal
    upper: Decimal
    leverage: Decimal
    grid_bps: Decimal
    min_net_bps: Decimal
    soft_bps: Decimal
    hard_bps: Decimal
    order_sz: Decimal
    max_position: Decimal
    max_open_orders_per_side: int
    max_actions_per_cycle: int
    interval: float
    live: bool
    once: bool
    set_leverage: bool
    cancel_on_stop: bool
    ord_type: str
    mode: str
    adaptive_width_bps: Decimal
    adaptive_min_width_bps: Decimal
    adaptive_max_width_bps: Decimal
    adaptive_vol_multiplier: Decimal
    range_drift_mode: str
    range_drift_weight_bps: Decimal
    range_drift_max_bps: Decimal
    sizing_mode: str
    order_margin_pct: Decimal
    max_margin_pct: Decimal
    cash_reserve_pct: Decimal
    total_profit_tp: Decimal
    total_profit_tp_pct: Decimal
    total_profit_tp_cap: Decimal
    total_profit_action: str
    min_tp_profit: Decimal
    total_loss_sl: Decimal
    total_loss_sl_pct: Decimal
    total_loss_sl_cap: Decimal
    position_loss_sl_bps: Decimal
    exchange_stop_enabled: bool
    exchange_stop_bps: Decimal
    exchange_stop_trigger_px_type: str
    exchange_stop_reprice_bps: Decimal
    min_tp_bps: Decimal
    missed_tp_ord_type: str
    missed_tp_slippage_bps: Decimal
    hard_stop_ord_type: str
    hard_stop_slippage_bps: Decimal
    risk_cooldown: float
    recenter_on_cooldown: bool
    trend_filter: str
    trend_lookback: int
    trend_threshold_bps: Decimal
    market_regime_filter: str
    market_regime_model_path: str
    market_regime_min_confidence: Decimal
    regime_filter: str
    regime_bar: str
    regime_short_ma: int
    regime_long_ma: int
    regime_diff_bps: Decimal
    regime_confirm_bars: int
    one_way_open: bool
    bot_started_ms: int
    rolling_adaptive_enabled: bool
    rolling_adaptive_window: int
    rolling_adaptive_low_vol_bps: Decimal
    rolling_adaptive_high_vol_bps: Decimal
    rolling_adaptive_min_leverage: Decimal
    rolling_adaptive_max_leverage: Decimal
    rolling_adaptive_min_grid_bps: Decimal
    rolling_adaptive_max_grid_bps: Decimal
    rolling_adaptive_grid_vol_multiplier: Decimal
    rolling_adaptive_min_width_bps: Decimal
    rolling_adaptive_max_width_bps: Decimal
    rolling_adaptive_width_vol_multiplier: Decimal
    rolling_adaptive_min_order_margin_pct: Decimal
    rolling_adaptive_max_order_margin_pct: Decimal
    rolling_adaptive_min_max_margin_pct: Decimal
    rolling_adaptive_max_max_margin_pct: Decimal
    rolling_adaptive_min_stop_bps: Decimal
    rolling_adaptive_max_stop_bps: Decimal
    rolling_adaptive_stop_vol_multiplier: Decimal
    rolling_adaptive_min_tp_bps: Decimal
    rolling_adaptive_max_tp_bps: Decimal
    rolling_adaptive_tp_grid_multiplier: Decimal
    rolling_adaptive_min_total_profit_tp_pct: Decimal
    rolling_adaptive_max_total_profit_tp_pct: Decimal
    rolling_adaptive_min_total_loss_sl_pct: Decimal
    rolling_adaptive_max_total_loss_sl_pct: Decimal
    runtime_config_mtime: float = 0.0
    cooldown_until_ms: int = 0
    cooldown_reason: str = ""
    recenter_pending: bool = False
    regime_state: str = "range"
    regime_pending_state: str = ""
    regime_pending_count: int = 0
    regime_last_ts: int = 0
    rolling_adaptive_last_leverage: Decimal = Decimal("0")
    exchange_stop_triggers: dict[str, Decimal] = field(default_factory=dict)
    private_cache: dict[str, Any] = field(default_factory=dict)
    backoff_until_ms: int = 0
    backoff_seconds: float = 0.0
    open_backoff_until_ms: int = 0


def main() -> None:
    global LOG_PATH, RUNTIME_CONFIG_PATH, BOT_PREFIX
    load_env()
    args = parse_args()
    LOG_PATH = Path(args.log_path)
    RUNTIME_CONFIG_PATH = Path(args.runtime_config)
    BOT_PREFIX = str(args.bot_prefix or "gb")[:8]
    config = BotConfig(
        inst_id=args.inst_id,
        lower=Decimal(args.lower),
        upper=Decimal(args.upper),
        leverage=Decimal(args.leverage),
        grid_bps=Decimal(args.grid_bps),
        min_net_bps=Decimal(args.min_net_bps),
        soft_bps=Decimal(args.soft_bps),
        hard_bps=Decimal(args.hard_bps),
        order_sz=Decimal(args.order_sz),
        max_position=Decimal(args.max_position),
        max_open_orders_per_side=args.max_open_orders_per_side,
        max_actions_per_cycle=args.max_actions_per_cycle,
        interval=args.interval,
        live=args.live,
        once=args.once,
        set_leverage=args.set_leverage,
        cancel_on_stop=args.cancel_on_stop,
        ord_type=args.ord_type,
        mode=args.mode,
        adaptive_width_bps=Decimal(args.adaptive_width_bps),
        adaptive_min_width_bps=Decimal(args.adaptive_min_width_bps),
        adaptive_max_width_bps=Decimal(args.adaptive_max_width_bps),
        adaptive_vol_multiplier=Decimal(args.adaptive_vol_multiplier),
        range_drift_mode=args.range_drift_mode,
        range_drift_weight_bps=Decimal(args.range_drift_weight_bps),
        range_drift_max_bps=Decimal(args.range_drift_max_bps),
        sizing_mode=args.sizing_mode,
        order_margin_pct=Decimal(args.order_margin_pct),
        max_margin_pct=Decimal(args.max_margin_pct),
        cash_reserve_pct=Decimal(args.cash_reserve_pct),
        total_profit_tp=Decimal(args.total_profit_tp),
        total_profit_tp_pct=Decimal(args.total_profit_tp_pct),
        total_profit_tp_cap=Decimal(args.total_profit_tp_cap),
        total_profit_action=args.total_profit_action,
        min_tp_profit=Decimal(args.min_tp_profit),
        total_loss_sl=Decimal(args.total_loss_sl),
        total_loss_sl_pct=Decimal(args.total_loss_sl_pct),
        total_loss_sl_cap=Decimal(args.total_loss_sl_cap),
        position_loss_sl_bps=Decimal(args.position_loss_sl_bps),
        exchange_stop_enabled=args.exchange_stop_enabled,
        exchange_stop_bps=Decimal(args.exchange_stop_bps),
        exchange_stop_trigger_px_type=args.exchange_stop_trigger_px_type,
        exchange_stop_reprice_bps=Decimal(args.exchange_stop_reprice_bps),
        min_tp_bps=Decimal(args.min_tp_bps),
        missed_tp_ord_type=args.missed_tp_ord_type,
        missed_tp_slippage_bps=Decimal(args.missed_tp_slippage_bps),
        hard_stop_ord_type=args.hard_stop_ord_type,
        hard_stop_slippage_bps=Decimal(args.hard_stop_slippage_bps),
        risk_cooldown=args.risk_cooldown,
        recenter_on_cooldown=args.recenter_on_cooldown,
        trend_filter=args.trend_filter,
        trend_lookback=args.trend_lookback,
        trend_threshold_bps=Decimal(args.trend_threshold_bps),
        market_regime_filter=args.market_regime_filter,
        market_regime_model_path=args.market_regime_model_path,
        market_regime_min_confidence=Decimal(args.market_regime_min_confidence),
        regime_filter=args.regime_filter,
        regime_bar=args.regime_bar,
        regime_short_ma=args.regime_short_ma,
        regime_long_ma=args.regime_long_ma,
        regime_diff_bps=Decimal(args.regime_diff_bps),
        regime_confirm_bars=args.regime_confirm_bars,
        one_way_open=args.one_way_open,
        bot_started_ms=current_ms(),
        rolling_adaptive_enabled=args.rolling_adaptive,
        rolling_adaptive_window=args.rolling_adaptive_window,
        rolling_adaptive_low_vol_bps=Decimal(args.rolling_adaptive_low_vol_bps),
        rolling_adaptive_high_vol_bps=Decimal(args.rolling_adaptive_high_vol_bps),
        rolling_adaptive_min_leverage=Decimal(args.rolling_adaptive_min_leverage),
        rolling_adaptive_max_leverage=Decimal(args.rolling_adaptive_max_leverage),
        rolling_adaptive_min_grid_bps=Decimal(args.rolling_adaptive_min_grid_bps),
        rolling_adaptive_max_grid_bps=Decimal(args.rolling_adaptive_max_grid_bps),
        rolling_adaptive_grid_vol_multiplier=Decimal(args.rolling_adaptive_grid_vol_multiplier),
        rolling_adaptive_min_width_bps=Decimal(args.rolling_adaptive_min_width_bps),
        rolling_adaptive_max_width_bps=Decimal(args.rolling_adaptive_max_width_bps),
        rolling_adaptive_width_vol_multiplier=Decimal(args.rolling_adaptive_width_vol_multiplier),
        rolling_adaptive_min_order_margin_pct=Decimal(args.rolling_adaptive_min_order_margin_pct),
        rolling_adaptive_max_order_margin_pct=Decimal(args.rolling_adaptive_max_order_margin_pct),
        rolling_adaptive_min_max_margin_pct=Decimal(args.rolling_adaptive_min_max_margin_pct),
        rolling_adaptive_max_max_margin_pct=Decimal(args.rolling_adaptive_max_max_margin_pct),
        rolling_adaptive_min_stop_bps=Decimal(args.rolling_adaptive_min_stop_bps),
        rolling_adaptive_max_stop_bps=Decimal(args.rolling_adaptive_max_stop_bps),
        rolling_adaptive_stop_vol_multiplier=Decimal(args.rolling_adaptive_stop_vol_multiplier),
        rolling_adaptive_min_tp_bps=Decimal(args.rolling_adaptive_min_tp_bps),
        rolling_adaptive_max_tp_bps=Decimal(args.rolling_adaptive_max_tp_bps),
        rolling_adaptive_tp_grid_multiplier=Decimal(args.rolling_adaptive_tp_grid_multiplier),
        rolling_adaptive_min_total_profit_tp_pct=Decimal(args.rolling_adaptive_min_total_profit_tp_pct),
        rolling_adaptive_max_total_profit_tp_pct=Decimal(args.rolling_adaptive_max_total_profit_tp_pct),
        rolling_adaptive_min_total_loss_sl_pct=Decimal(args.rolling_adaptive_min_total_loss_sl_pct),
        rolling_adaptive_max_total_loss_sl_pct=Decimal(args.rolling_adaptive_max_total_loss_sl_pct),
    )

    if config.live:
        require_live_permission(args.confirm_live)

    client = OkxRestClient.from_env()
    print_banner(config)
    install_shutdown_handlers(client, config)
    if config.set_leverage:
        set_leverage(client, config)
        config.rolling_adaptive_last_leverage = config.leverage

    while True:
        try:
            should_stop = run_cycle(client, config)
        except OkxApiError as exc:
            log_event("okx_error", {"error": str(exc), "code": exc.okx_code, "response": exc.response})
            print(f"OKX error: {exc}")
            register_okx_error_backoff(config, exc)
            should_stop = False
        except Exception as exc:
            log_event("bot_error", {"error": str(exc)})
            print(f"Bot error: {exc}")
            should_stop = False

        if config.once or should_stop:
            break
        time.sleep(next_sleep_seconds(config))


def run_cycle(client: OkxRestClient, config: BotConfig) -> bool:
    load_runtime_config(config)
    if config.backoff_until_ms > current_ms():
        remaining = max(1, int((config.backoff_until_ms - current_ms()) / 1000))
        print(f"OKX request backoff active remaining={remaining}s after rate-limit/network error.")
        return False
    state = fetch_state(client, config)
    clear_okx_backoff(config)
    ensure_account_ready(state)

    meta = state["meta"]
    ticker = state["ticker"]
    mark_px = Decimal(state["mark"]["markPx"])
    tick = Decimal(meta["tickSz"])
    lot = Decimal(meta["lotSz"])
    min_sz = Decimal(meta["minSz"])
    now_ms = current_ms()
    apply_rolling_adaptive_config(client, config, state, mark_px)
    if config.cooldown_until_ms > now_ms:
        remaining = max(0, int((config.cooldown_until_ms - now_ms) / 1000))
        print(f"Risk cooldown active reason={config.cooldown_reason} remaining={remaining}s. No new orders.")
        return False
    if config.cooldown_reason:
        if config.recenter_pending and config.mode == "adaptive":
            recenter_outer_range(config, mark_px, tick)
            config.recenter_pending = False
        print(f"Risk cooldown ended reason={config.cooldown_reason}. Resuming grid.")
        config.cooldown_reason = ""
        config.bot_started_ms = now_ms

    step = grid_step(config, tick)
    midpoint = (config.lower + config.upper) / Decimal("2")
    soft_lower = round_to_tick(config.lower * (Decimal("1") - config.soft_bps / Decimal("10000")), tick)
    soft_upper = round_to_tick(config.upper * (Decimal("1") + config.soft_bps / Decimal("10000")), tick)
    hard_lower = round_to_tick(config.lower * (Decimal("1") - config.hard_bps / Decimal("10000")), tick)
    hard_upper = round_to_tick(config.upper * (Decimal("1") + config.hard_bps / Decimal("10000")), tick)

    bot_orders = [order for order in state["pending"] if is_bot_order(order)]
    effective_lower, effective_upper, range_note = effective_range(config, state, mark_px, tick)
    step = grid_step(config, tick, effective_lower, effective_upper)
    midpoint = (effective_lower + effective_upper) / Decimal("2")
    soft_lower = round_to_tick(effective_lower * (Decimal("1") - config.soft_bps / Decimal("10000")), tick)
    soft_upper = round_to_tick(effective_upper * (Decimal("1") + config.soft_bps / Decimal("10000")), tick)
    hard_lower = round_to_tick(effective_lower * (Decimal("1") - config.hard_bps / Decimal("10000")), tick)
    hard_upper = round_to_tick(effective_upper * (Decimal("1") + config.hard_bps / Decimal("10000")), tick)
    stop_state = classify_stop(mark_px, effective_lower, effective_upper, soft_lower, soft_upper, hard_lower, hard_upper)
    print_cycle_header(mark_px, ticker, step, stop_state, state, effective_lower, effective_upper, range_note)

    triggered_exchange_stop = detect_triggered_exchange_stop(config, state)
    if triggered_exchange_stop:
        print(
            f"Exchange protection stop likely triggered: {triggered_exchange_stop['posSide']} "
            f"trigger={triggered_exchange_stop['triggerPx']} fill_pnl={triggered_exchange_stop['fillPnl']}. "
            "Canceling bot orders and entering cooldown."
        )
        try:
            cancel_all_bot_orders(client, config, bot_orders, reason=f"exchange_stop_{triggered_exchange_stop['posSide']}")
        except Exception as exc:
            log_event("risk_cancel_error", {"reason": "exchange_stop_triggered", "error": str(exc)})
            print(f"Exchange protection stop: cancel failed: {exc}")
        log_event("exchange_stop_triggered", {"live": config.live, **triggered_exchange_stop})
        enter_risk_cooldown(config, f"exchange_stop_{triggered_exchange_stop['posSide']}")
        return False

    pnl = pnl_breakdown(state, config.bot_started_ms)
    estimated_total = pnl["estimatedTotal"]
    profit_threshold, profit_note = pnl_threshold(
        state,
        fixed=config.total_profit_tp,
        pct=config.total_profit_tp_pct,
        cap=config.total_profit_tp_cap,
    )
    loss_threshold, loss_note = pnl_threshold(
        state,
        fixed=config.total_loss_sl,
        pct=config.total_loss_sl_pct,
        cap=config.total_loss_sl_cap,
    )
    if profit_threshold > 0 and estimated_total >= profit_threshold:
        print(
            f"Total profit TP hit: estimated_total={estimated_total} "
            f"target={profit_threshold} ({profit_note}) "
            f"unrealized={pnl['unrealized']} session_realized={pnl['sessionRealized']} "
            f"session_fees={pnl['sessionFees']} fills={pnl['sessionFillCount']} action={config.total_profit_action}."
        )
        log_event("total_profit_tp", {"target": profit_threshold, "note": profit_note, **pnl})
        if config.total_profit_action == "close":
            closed = risk_close_all_positions(client, config, state["positions"], tick, bot_orders, reason="total_profit_tp")
            if closed:
                enter_risk_cooldown(config, "total_profit_tp")
            else:
                print("Total profit TP close was not confirmed; retrying next cycle without cooldown.")
        else:
            config.bot_started_ms = now_ms
            log_event("profit_checkpoint", {"live": config.live, "target": profit_threshold, **pnl})
            print("Profit checkpoint recorded: session PnL baseline reset, grid continues.")
        return False

    if loss_threshold > 0 and estimated_total <= -loss_threshold:
        print(
            f"Total loss hard SL hit: estimated_total={estimated_total} "
            f"target=-{loss_threshold} ({loss_note}) "
            f"unrealized={pnl['unrealized']} session_realized={pnl['sessionRealized']} "
            f"session_fees={pnl['sessionFees']} fills={pnl['sessionFillCount']}. Closing all positions."
        )
        closed = risk_close_all_positions(client, config, state["positions"], tick, bot_orders, reason="total_loss_sl")
        log_event("total_loss_sl", {"target": loss_threshold, "note": loss_note, **pnl})
        if closed:
            enter_risk_cooldown(config, "total_loss_sl")
        else:
            print("Total loss hard SL close was not confirmed; retrying next cycle without cooldown.")
        return False

    side_stop = position_loss_stop(config, state["positions"], mark_px)
    if side_stop:
        pos_side = str(side_stop["posSide"])
        print(
            f"Position loss SL hit: {pos_side} adverse={plain(side_stop['adverseBps'])}bps "
            f"target={plain(config.position_loss_sl_bps)}bps avg={side_stop['avgPx']} "
            f"mark={mark_px} size={side_stop['size']} upl={side_stop['upl']} "
            f"metric={side_stop.get('metric')}. Closing side."
        )
        try:
            cancel_all_bot_orders(client, config, bot_orders, reason=f"position_loss_sl_{pos_side}")
        except Exception as exc:
            log_event("risk_cancel_error", {"reason": f"position_loss_sl_{pos_side}", "error": str(exc)})
            print(f"Position loss SL {pos_side}: cancel failed, still trying reduce-only close: {exc}")
        closed = close_positions_by_side(client, config, state["positions"], tick, pos_side, reason=f"position_loss_sl_{pos_side}")
        log_event("position_loss_sl", {"live": config.live, **side_stop})
        if closed:
            enter_risk_cooldown(config, f"position_loss_sl_{pos_side}")
        else:
            print(f"Position loss SL {pos_side} close was not confirmed; retrying next cycle without cooldown.")
        return False

    if stop_state in {"hard_low", "hard_high"}:
        closed = handle_price_hard_stop(client, config, state, bot_orders, tick, stop_state)
        if closed:
            enter_risk_cooldown(config, stop_state)
        else:
            print(f"Price hard stop {stop_state} close was not confirmed; retrying next cycle without cooldown.")
        return False

    exchange_stop_actions = sync_exchange_protection_stops(client, config, state, tick, lot)
    if exchange_stop_actions:
        return False

    ct_val = dec(meta.get("ctVal"), Decimal("0"))
    edge = grid_edge_summary(config, state, step, midpoint)
    missed_tp = missed_take_profit_orders(config, state, mark_px, step, tick, ct_val, edge)
    if missed_tp:
        print(f"missed_tp={len(missed_tp)}: price crossed TP, closing reduce-only now.")
        cancel_orders(client, config, bot_orders, reason="missed_tp")
        for order in missed_tp[: config.max_actions_per_cycle]:
            place_one(client, config, order)
        return False

    positions = position_summary(state["positions"])
    config.private_cache["marketRegimeCandles"] = state.get("candles", [])
    regime = market_regime_signal(config, state.get("regimeCandles", []))
    trend = trend_signal(state.get("candles", []), mark_px, config.trend_lookback, config.trend_threshold_bps)
    trend_side = trend_follow_side(config, trend)
    price_anchor_side = regime_follow_side(config, regime) or trend_side
    if config.regime_filter == "ma_cross":
        trend_side = None
    low_guard_zone = stop_state == "soft_low" or (stop_state == "buffer" and mark_px < effective_lower)
    high_guard_zone = stop_state == "soft_high" or (stop_state == "buffer" and mark_px > effective_upper)
    soft_restricted_open = low_guard_zone or high_guard_zone
    if trend_side:
        soft_allowed_sides = {trend_side}
    else:
        soft_allowed_sides = {"long"} if low_guard_zone else {"short"} if high_guard_zone else set()
    if soft_restricted_open:
        if config.cancel_on_stop:
            allowed_label = ",".join(sorted(soft_allowed_sides))
            print(
                f"Stop state {stop_state}: restricted-open; only {allowed_label} opens allowed, "
                "opposite open bot orders will be canceled, reduce-only TP kept/maintained."
            )
        else:
            print(f"Stop state {stop_state}: restricted-open; existing open bot orders left untouched.")

    order_sz, max_position, sizing_note = resolve_sizing(config, state, mark_px, lot, min_sz)
    close_sz = resolve_close_size(config, order_sz, lot, min_sz)
    print(f"sizing order_sz={order_sz} max_position={max_position} {sizing_note}")
    allow_open = True
    preserve_valid_open = True
    if order_sz <= 0 or max_position <= 0:
        print("Open sizing resolved to zero: close orders will still be maintained.")
        allow_open = False
    equity, available = balance_summary(state.get("balance", {}))
    reserve_margin = equity * clamp_pct(config.cash_reserve_pct) / Decimal("100") if equity > 0 else Decimal("0")
    if reserve_margin > 0 and available < reserve_margin:
        print(
            f"Cash reserve guard: available={plain(available)} below reserve={plain(reserve_margin)} "
            "so no new open orders; stale open orders will be canceled."
        )
        log_event(
            "cash_reserve_guard",
            {
                "live": config.live,
                "available": available,
                "reserveMargin": reserve_margin,
                "cashReservePct": config.cash_reserve_pct,
            },
        )
        allow_open = False
        preserve_valid_open = False
    print(
        f"edge gross={plain(edge['grossBps'])}bps net_est={plain(edge['netBps'])}bps "
        f"min_net={plain(config.min_net_bps)}bps fees=open {plain(edge['openFeeBps'])}bps "
        f"close {plain(edge['closeFeeBps'])}bps"
    )
    if config.min_net_bps > 0 and edge["netBps"] < config.min_net_bps:
        print("Net edge too low: no new open orders; close orders will still be maintained.")
        log_event(
            "net_edge_guard",
            {
                "live": config.live,
                "minNetBps": config.min_net_bps,
                **edge,
            },
        )
        allow_open = False

    open_sides, open_note = allowed_open_sides(config, positions, mark_px, midpoint, trend, tick, regime)
    if soft_restricted_open:
        before_soft = set(open_sides)
        open_sides &= soft_allowed_sides
        soft_label = ",".join(sorted(soft_allowed_sides))
        if before_soft and not open_sides:
            open_note = f"{open_note}; {stop_state} allows only {soft_label}"
        elif open_sides:
            open_note = f"{open_note}; {stop_state} allowed"
    open_label = ",".join(sorted(open_sides)) if open_sides else "none"
    print(
        f"open_guard sides={open_label} trend={trend['direction']} "
        f"change={plain(trend['changeBps'])}bps regime={regime['state']} "
        f"maDiff={plain(regime['diffBps'])}bps "
        f"note=raw={regime.get('rawState', 'unknown')} confirmed={int(bool(regime.get('confirmed')))} "
        f"pending={regime.get('pendingState') or '-'}:{regime.get('pendingCount', 0)} {open_note}"
    )
    if not open_sides:
        allow_open = False
    if config.open_backoff_until_ms > current_ms():
        remaining = max(1, int((config.open_backoff_until_ms - current_ms()) / 1000))
        print(
            f"Open-order backoff active remaining={remaining}s after insufficient margin; "
            "close orders will still be maintained."
        )
        allow_open = False

    order_lower = hard_lower if low_guard_zone else effective_lower
    order_upper = hard_upper if high_guard_zone else effective_upper
    desired = desired_orders(
        config,
        state,
        mark_px,
        midpoint,
        step,
        tick,
        close_sz,
        order_sz,
        max_position,
        ct_val,
        edge,
        order_lower,
        order_upper,
        allow_open=allow_open,
        open_sides=open_sides,
        trend_side=price_anchor_side,
    )
    open_px_tolerance = open_order_price_tolerance(step, tick)
    open_capacity = {
        "long": max(Decimal("0"), max_position - positions["long"]),
        "short": max(Decimal("0"), max_position - positions["short"]),
    }
    stale, missing, matched = reconcile_orders(
        bot_orders,
        desired,
        open_px_tolerance,
        lower=order_lower,
        upper=order_upper,
        open_sides=open_sides,
        open_capacity=open_capacity,
        preserve_valid_open=preserve_valid_open,
    )
    if soft_restricted_open and not config.cancel_on_stop:
        stale = [order for order in stale if is_reduce_only_pending_order(order)]
    missing = fit_missing_orders_to_margin_budget(
        missing,
        available=available,
        reserve_margin=reserve_margin,
        ct_val=ct_val,
        leverage=config.leverage,
    )

    print(
        f"desired={len(desired)} existing_bot={len(bot_orders)} matched={matched} "
        f"missing={len(missing)} stale={len(stale)} open_px_tolerance={plain(open_px_tolerance)} "
        f"preserve_valid_open={str(preserve_valid_open).lower()}"
    )
    actions_left = config.max_actions_per_cycle

    for order in stale:
        if actions_left <= 0:
            break
        reason = (
            stop_state
            if soft_restricted_open
            and not is_reduce_only_pending_order(order)
            and order.get("posSide") not in open_sides
            else "stale"
        )
        cancel_one(client, config, order, reason=reason)
        actions_left -= 1

    for order in missing:
        if actions_left <= 0:
            break
        if place_one(client, config, order):
            actions_left -= 1
    return False


def fetch_state(client: OkxRestClient, config: BotConfig) -> dict[str, Any]:
    family = "-".join(config.inst_id.split("-")[:2])
    regime_candles = []
    if config.regime_filter == "ma_cross":
        regime_candles = client.request(
            "GET",
            "/api/v5/market/candles",
            params={
                "instId": config.inst_id,
                "bar": config.regime_bar,
                "limit": str(max(80, config.regime_long_ma + config.regime_confirm_bars + 10)),
            },
        ).get("data", [])
    pending_algos = client.get_pending_algo_orders(ord_type="conditional", inst_id=config.inst_id, inst_type="SWAP").get("data", [])
    positions = cached_private_call(
        config,
        "positions",
        ttl_seconds=max(12.0, min(config.interval * 2, 20.0)),
        loader=lambda: client.get_positions("SWAP").get("data", []),
    )
    return {
        "account": one(cached_private_call(config, "account_config", ttl_seconds=300.0, loader=client.get_account_config)),
        "meta": one(
            cached_private_call(
                config,
                "instrument_meta",
                ttl_seconds=1800.0,
                loader=lambda: client.request(
                    "GET",
                    "/api/v5/public/instruments",
                    params={"instType": "SWAP", "instId": config.inst_id},
                ),
            )
        ),
        "ticker": one(client.request("GET", "/api/v5/market/ticker", params={"instId": config.inst_id})),
        "mark": one(client.request("GET", "/api/v5/public/mark-price", params={"instType": "SWAP", "instId": config.inst_id})),
        "fee": one(
            cached_private_call(
                config,
                "trade_fee",
                ttl_seconds=1800.0,
                loader=lambda: client.request(
                    "GET",
                    "/api/v5/account/trade-fee",
                    params={"instType": "SWAP", "instFamily": family},
                    private=True,
                ),
            )
        ),
        "balance": one(
            cached_private_call(
                config,
                "balance",
                ttl_seconds=max(12.0, min(config.interval * 2, 20.0)),
                loader=client.get_balance,
            )
        ),
        "positions": [item for item in positions if item.get("instId") == config.inst_id],
        "pending": client.get_pending_orders(config.inst_id).get("data", []),
        "pendingAlgos": pending_algos,
        "fills": cached_private_call(
            config,
            "fills",
            ttl_seconds=20.0,
            loader=lambda: client.get_fills(inst_id=config.inst_id, inst_type="SWAP", limit="100").get("data", []),
        ),
        "candles": client.request("GET", "/api/v5/market/candles", params={"instId": config.inst_id, "bar": "1m", "limit": "60"}).get("data", []),
        "regimeCandles": regime_candles,
    }


def cached_private_call(config: BotConfig, key: str, *, ttl_seconds: float, loader: Any) -> Any:
    now_ms = current_ms()
    cached = config.private_cache.get(key)
    if cached and now_ms - int(cached.get("ts", 0)) < int(ttl_seconds * 1000):
        return cached.get("value")
    value = loader()
    config.private_cache[key] = {"ts": now_ms, "value": value}
    return value


def register_okx_error_backoff(config: BotConfig, exc: OkxApiError) -> None:
    if exc.okx_code != "50011" and exc.status != 429:
        return
    base = max(config.interval, 8.0)
    next_seconds = base if config.backoff_seconds <= 0 else min(config.backoff_seconds * 2, 64.0)
    config.backoff_seconds = next_seconds
    config.backoff_until_ms = current_ms() + int(next_seconds * 1000)
    print(f"OKX rate-limit backoff scheduled {next_seconds:.0f}s.")


def clear_okx_backoff(config: BotConfig) -> None:
    config.backoff_seconds = 0.0
    config.backoff_until_ms = 0


def next_sleep_seconds(config: BotConfig) -> float:
    if config.backoff_until_ms > current_ms():
        return min(max(1.0, (config.backoff_until_ms - current_ms()) / 1000), 64.0)
    return config.interval


def ensure_account_ready(state: dict[str, Any]) -> None:
    account = state["account"]
    if account.get("posMode") != "long_short_mode":
        raise RuntimeError(f"Account posMode is {account.get('posMode')}; expected long_short_mode.")
    if "trade" not in (account.get("perm") or ""):
        raise RuntimeError("API key does not have trade permission.")


def desired_orders(
    config: BotConfig,
    state: dict[str, Any],
    mark_px: Decimal,
    midpoint: Decimal,
    step: Decimal,
    tick: Decimal,
    close_sz: Decimal,
    order_sz: Decimal,
    max_position: Decimal,
    ct_val: Decimal,
    edge: dict[str, Decimal],
    lower: Decimal,
    upper: Decimal,
    *,
    allow_open: bool,
    open_sides: set[str],
    trend_side: str | None = None,
) -> list[dict[str, Any]]:
    positions = position_summary(state["positions"])
    desired: list[dict[str, str]] = []

    if positions["long"] > 0:
        avg = positions["long_avg"] or midpoint
        size = min(close_sz, positions["long"])
        desired.append(
            make_order(
                config,
                "sell",
                "long",
                tp_price(config, "long", avg, step, tick, size, ct_val, edge),
                size,
                tick,
                close=True,
            )
        )
    if positions["short"] > 0:
        avg = positions["short_avg"] or midpoint
        size = min(close_sz, positions["short"])
        desired.append(
            make_order(
                config,
                "buy",
                "short",
                tp_price(config, "short", avg, step, tick, size, ct_val, edge),
                size,
                tick,
                close=True,
            )
        )

    if not allow_open:
        return valid_desired_orders(desired, lower, upper)

    open_pending = open_pending_by_side(state.get("pending", []), lower=lower, upper=upper, open_sides=open_sides)

    if "long" in open_sides and positions["long"] + open_pending["long"] < max_position:
        remaining = max_position - positions["long"] - open_pending["long"]
        long_end = mark_px - step if trend_side == "long" else min(mark_px - step, midpoint - step)
        prices = nearest_grid_prices(lower, long_end, step, tick, reverse=True)
        if not prices and lower < mark_px:
            prices = [round_to_tick(lower, tick)]
        for price in prices[: config.max_open_orders_per_side]:
            open_sz = min(order_sz, remaining)
            if open_sz <= 0:
                break
            desired.append(make_order(config, "buy", "long", price, open_sz, tick, close=False))
            remaining -= open_sz

    if "short" in open_sides and positions["short"] + open_pending["short"] < max_position:
        remaining = max_position - positions["short"] - open_pending["short"]
        short_start = mark_px + step if trend_side == "short" else max(mark_px + step, midpoint + step)
        prices = nearest_grid_prices(short_start, upper, step, tick, reverse=False)
        if not prices and upper > mark_px:
            prices = [round_to_tick(upper, tick)]
        for price in prices[: config.max_open_orders_per_side]:
            open_sz = min(order_sz, remaining)
            if open_sz <= 0:
                break
            desired.append(make_order(config, "sell", "short", price, open_sz, tick, close=False))
            remaining -= open_sz

    return valid_desired_orders(desired, lower, upper)


def valid_desired_orders(orders: list[dict[str, Any]], lower: Decimal, upper: Decimal) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for order in orders:
        if Decimal(order["sz"]) <= 0:
            continue
        if order.get("reduce_only"):
            result.append(order)
            continue
        px = Decimal(order["px"])
        if lower <= px <= upper:
            result.append(order)
    return result


def tp_price(
    config: BotConfig,
    pos_side: str,
    avg_px: Decimal,
    step: Decimal,
    tick: Decimal,
    size: Decimal,
    ct_val: Decimal,
    edge: dict[str, Decimal],
) -> Decimal:
    base = avg_px + step if pos_side == "long" else avg_px - step
    target = round_to_tick(base, tick)
    if avg_px > 0 and config.min_tp_bps > 0:
        bps_gap = avg_px * config.min_tp_bps / Decimal("10000")
        bps_target = avg_px + bps_gap if pos_side == "long" else avg_px - bps_gap
        target = max(target, bps_target) if pos_side == "long" else min(target, bps_target)

    if config.min_tp_profit <= 0 or avg_px <= 0 or size <= 0 or ct_val <= 0:
        return round_to_tick(target, tick)

    fee_bps = max(Decimal("0"), edge.get("openFeeBps", Decimal("0"))) + max(
        Decimal("0"),
        edge.get("closeFeeBps", Decimal("0")),
    )
    fee_price_gap = avg_px * fee_bps / Decimal("10000")
    profit_price_gap = config.min_tp_profit / (size * ct_val)
    min_gap = profit_price_gap + fee_price_gap
    min_target = avg_px + min_gap if pos_side == "long" else avg_px - min_gap
    if pos_side == "long":
        return round_to_tick(max(target, min_target), tick)
    return round_to_tick(min(target, min_target), tick)


def trend_signal(candles: list[list[str]], mark_px: Decimal, lookback: int, threshold_bps: Decimal) -> dict[str, Decimal | str | int]:
    closes = [dec(item[4], Decimal("0")) for item in candles if len(item) > 4 and dec(item[4], Decimal("0")) > 0]
    if not closes:
        return {"direction": "flat", "changeBps": Decimal("0"), "lookback": 0}
    current = mark_px if mark_px > 0 else closes[0]
    index = min(max(1, lookback), len(closes) - 1)
    past = closes[index]
    if past <= 0:
        return {"direction": "flat", "changeBps": Decimal("0"), "lookback": index}
    change_bps = (current / past - Decimal("1")) * Decimal("10000")
    if change_bps >= threshold_bps:
        direction = "up"
    elif change_bps <= -threshold_bps:
        direction = "down"
    else:
        direction = "flat"
    return {"direction": direction, "changeBps": change_bps, "lookback": index}


def market_regime_signal(config: BotConfig, candles: list[list[str]]) -> dict[str, Any]:
    default = {
        "filter": config.regime_filter,
        "state": "range",
        "rawState": "range",
        "confirmed": False,
        "allowedOpenSides": ["long", "short"],
        "bar": config.regime_bar,
        "shortMa": str(config.regime_short_ma),
        "longMa": str(config.regime_long_ma),
        "diffBps": Decimal("0"),
        "confirmBars": config.regime_confirm_bars,
        "pendingState": config.regime_pending_state,
        "pendingCount": config.regime_pending_count,
    }
    if config.regime_filter != "ma_cross":
        default["state"] = "off"
        default["rawState"] = "off"
        default["confirmed"] = True
        return default

    closed = sorted(
        [
            (int(item[0]), dec(item[4], Decimal("0")))
            for item in candles
            if len(item) > 8 and item[8] == "1" and dec(item[4], Decimal("0")) > 0
        ],
        key=lambda item: item[0],
    )
    need = config.regime_long_ma + max(0, config.regime_confirm_bars - 1)
    if len(closed) < need:
        default["state"] = config.regime_state
        default["rawState"] = "insufficient"
        default["allowedOpenSides"] = regime_allowed_sides(config.regime_state)
        return default

    last_ts = closed[-1][0]
    closes = [item[1] for item in closed]
    short_ma = sum(closes[-config.regime_short_ma :]) / Decimal(config.regime_short_ma)
    long_ma = sum(closes[-config.regime_long_ma :]) / Decimal(config.regime_long_ma)
    diff_bps = (short_ma / long_ma - Decimal("1")) * Decimal("10000") if long_ma > 0 else Decimal("0")
    raw_state = "range"
    if diff_bps >= config.regime_diff_bps:
        raw_state = "up"
    elif diff_bps <= -config.regime_diff_bps:
        raw_state = "down"

    if config.regime_last_ts == 0 and config.regime_state == "range":
        recent_states: list[str] = []
        for offset in range(config.regime_confirm_bars):
            end = len(closes) - offset
            window = closes[:end]
            if len(window) < config.regime_long_ma:
                break
            short = sum(window[-config.regime_short_ma :]) / Decimal(config.regime_short_ma)
            long = sum(window[-config.regime_long_ma :]) / Decimal(config.regime_long_ma)
            diff = (short / long - Decimal("1")) * Decimal("10000") if long > 0 else Decimal("0")
            if diff >= config.regime_diff_bps:
                recent_states.append("up")
            elif diff <= -config.regime_diff_bps:
                recent_states.append("down")
            else:
                recent_states.append("range")
        if len(recent_states) == config.regime_confirm_bars and all(item == recent_states[0] for item in recent_states):
            config.regime_state = recent_states[0]

    if last_ts != config.regime_last_ts:
        config.regime_last_ts = last_ts
        if raw_state == config.regime_state:
            config.regime_pending_state = ""
            config.regime_pending_count = 0
        elif raw_state == config.regime_pending_state:
            config.regime_pending_count += 1
        else:
            config.regime_pending_state = raw_state
            config.regime_pending_count = 1
        if config.regime_pending_count >= config.regime_confirm_bars:
            config.regime_state = raw_state
            config.regime_pending_state = ""
            config.regime_pending_count = 0

    return {
        "filter": config.regime_filter,
        "state": config.regime_state,
        "rawState": raw_state,
        "confirmed": raw_state == config.regime_state,
        "allowedOpenSides": regime_allowed_sides(config.regime_state),
        "bar": config.regime_bar,
        "shortMa": str(short_ma),
        "longMa": str(long_ma),
        "diffBps": diff_bps,
        "confirmBars": config.regime_confirm_bars,
        "pendingState": config.regime_pending_state,
        "pendingCount": config.regime_pending_count,
    }


def regime_allowed_sides(state: str) -> list[str]:
    if state == "up":
        return ["long"]
    if state == "down":
        return ["short"]
    return ["long", "short"]


def regime_follow_side(config: BotConfig, regime: dict[str, Any]) -> str | None:
    if config.regime_filter != "ma_cross":
        return None
    state = str(regime.get("state", "range"))
    if state == "up":
        return "long"
    if state == "down":
        return "short"
    return None


def allowed_open_sides(
    config: BotConfig,
    positions: dict[str, Decimal],
    mark_px: Decimal,
    midpoint: Decimal,
    trend: dict[str, Decimal | str | int],
    tick: Decimal,
    regime: dict[str, Any] | None = None,
) -> tuple[set[str], str]:
    regime = regime or {"state": "off", "allowedOpenSides": []}
    market_sides, market_note = market_regime_open_sides(config, positions, mark_px, midpoint)
    if market_sides is not None:
        return market_sides, market_note

    regime_sides = set(regime.get("allowedOpenSides") or [])
    if config.regime_filter == "ma_cross" and regime.get("state") in {"up", "down"}:
        if config.one_way_open:
            if positions["short"] > 0 and "long" in regime_sides:
                return set(), "ma-cross long blocked by active short"
            if positions["long"] > 0 and "short" in regime_sides:
                return set(), "ma-cross short blocked by active long"
        return regime_sides, f"ma-cross {regime.get('state')} confirmed diff={plain(dec(regime.get('diffBps'), Decimal('0')))}bps"

    trend_side = trend_follow_side(config, trend)
    if trend_side:
        if config.one_way_open:
            if positions["short"] > 0 and trend_side == "long":
                return set(), "trend-follow long blocked by active short"
            if positions["long"] > 0 and trend_side == "short":
                return set(), "trend-follow short blocked by active long"
        direction = str(trend.get("direction", "flat"))
        change_bps = abs(dec(trend.get("changeBps"), Decimal("0")))
        return {trend_side}, f"trend-follow {direction} change={plain(change_bps)}bps"

    if not config.one_way_open and config.trend_filter == "off":
        return {"long", "short"}, "legacy-dual-side"

    if config.one_way_open and positions["long"] > 0 and positions["short"] > 0:
        return set(), "dual-position-protect close-only"

    if mark_px < midpoint - tick / Decimal("2"):
        sides = {"long"}
        reason = "lower-half buy-dip"
    elif mark_px > midpoint + tick / Decimal("2"):
        sides = {"short"}
        reason = "upper-half sell-rally"
    else:
        direction = str(trend.get("direction", "flat"))
        if config.trend_filter == "auto" and direction == "up":
            sides = {"long"}
            reason = "midpoint trend-follow long"
        elif config.trend_filter == "auto" and direction == "down":
            sides = {"short"}
            reason = "midpoint trend-follow short"
        elif mark_px <= midpoint:
            sides = {"long"}
            reason = "midpoint neutral passive-long"
        else:
            sides = {"short"}
            reason = "midpoint neutral passive-short"

    if config.one_way_open:
        if positions["short"] > 0 and "long" in sides:
            return set(), "short-position-active blocks opposite long"
        if positions["long"] > 0 and "short" in sides:
            return set(), "long-position-active blocks opposite short"

    if config.trend_filter == "auto":
        direction = str(trend.get("direction", "flat"))
        change_bps = abs(dec(trend.get("changeBps"), Decimal("0")))
        strong_threshold = max(config.trend_threshold_bps * Decimal("2"), Decimal("80"))
        if direction == "up" and "short" in sides and change_bps >= strong_threshold:
            return set(), f"strong-uptrend blocks new short change={plain(change_bps)}bps threshold={plain(strong_threshold)}bps"
        if direction == "down" and "long" in sides and change_bps >= strong_threshold:
            return set(), f"strong-downtrend blocks new long change={plain(change_bps)}bps threshold={plain(strong_threshold)}bps"
        reason = f"{reason} trend={direction}"

    if config.regime_filter == "ma_cross" and regime.get("state") == "range":
        reason = f"{reason}; ma-cross range"

    return sides, reason


def trend_follow_side(config: BotConfig, trend: dict[str, Decimal | str | int]) -> str | None:
    if config.trend_filter != "auto":
        return None
    direction = str(trend.get("direction", "flat"))
    if direction == "up":
        return "long"
    if direction == "down":
        return "short"
    return None


def market_regime_open_sides(
    config: BotConfig,
    positions: dict[str, Decimal],
    mark_px: Decimal,
    midpoint: Decimal,
) -> tuple[set[str], str] | tuple[None, str]:
    if config.market_regime_filter == "off":
        return None, ""
    from market_regime import signal_from_candles

    candles = config.private_cache.get("marketRegimeCandles", [])
    signal = signal_from_candles(
        candles,
        mode=config.market_regime_filter,
        model_path=config.market_regime_model_path,
        min_confidence=float(config.market_regime_min_confidence),
    )
    sides = set(signal.allowed_open_sides)
    note = (
        f"market-regime {signal.source} state={signal.state} "
        f"direction={signal.direction} confidence={signal.confidence:.3f} {signal.note}"
    )
    if not sides:
        return set(), f"{note}; mixed/unknown pauses new opens"
    if config.one_way_open and sides == {"long", "short"}:
        sides = {"long"} if mark_px <= midpoint else {"short"}
        note = f"{note}; one-way range uses price-anchor"
    if config.one_way_open:
        if positions["short"] > 0 and "long" in sides:
            return set(), f"{note}; blocked by active short"
        if positions["long"] > 0 and "short" in sides:
            return set(), f"{note}; blocked by active long"
    log_event("market_regime_signal", {"live": config.live, **signal.__dict__})
    return sides, note


def nearest_grid_prices(start: Decimal, end: Decimal, step: Decimal, tick: Decimal, *, reverse: bool) -> list[Decimal]:
    if start > end:
        return []
    prices = []
    price = round_to_tick(start, tick)
    while price <= end + tick / Decimal("2"):
        prices.append(price)
        price += step
    return list(reversed(prices)) if reverse else prices


def make_order(
    config: BotConfig,
    side: str,
    pos_side: str,
    price: Decimal,
    size: Decimal,
    tick: Decimal,
    *,
    close: bool,
) -> dict[str, Any]:
    order: dict[str, Any] = {
        "inst_id": config.inst_id,
        "td_mode": "cross",
        "side": side,
        "pos_side": pos_side,
        "ord_type": config.ord_type,
        "px": plain(price),
        "sz": plain(size),
        "cl_ord_id": client_order_id(side, pos_side, price, close),
        "tag": "tp" if close else "open",
    }
    if close:
        order["reduce_only"] = True
    elif config.exchange_stop_enabled and config.exchange_stop_bps > 0 and config.leverage > 0:
        order["attach_algo_ords"] = [attached_stop_order(config, pos_side, price, tick)]
    return order


def place_one(client: OkxRestClient, config: BotConfig, order: dict[str, Any]) -> bool:
    payload = {key: value for key, value in order.items() if key != "tag"}
    if config.live:
        try:
            response = client.place_order(**payload)
        except OkxApiError as exc:
            if not order.get("reduce_only") and okx_error_has_subcode(exc, "51008"):
                seconds = max(config.interval * 3, 24.0)
                config.open_backoff_until_ms = current_ms() + int(seconds * 1000)
                log_event(
                    "open_margin_backoff",
                    {
                        "live": config.live,
                        "seconds": seconds,
                        "order": order,
                        "error": str(exc),
                        "code": exc.okx_code,
                        "response": exc.response,
                    },
                )
                print(f"Open margin backoff scheduled {seconds:.0f}s after insufficient USDT margin.")
                return False
            raise
        print(f"LIVE place {order['tag']} {order['side']} {order['pos_side']} {order['sz']} @ {order.get('px', 'MKT')} -> {response.get('data')}")
    else:
        response = {"dryRun": True, "data": [payload]}
        print(f"DRY place {order['tag']} {order['side']} {order['pos_side']} {order['sz']} @ {order.get('px', 'MKT')}")
    log_event("place", {"live": config.live, "order": order, "response": response})
    return True


def okx_error_has_subcode(exc: OkxApiError, subcode: str) -> bool:
    data = exc.response.get("data") if isinstance(exc.response, dict) else None
    if not isinstance(data, list):
        return False
    return any(str(item.get("sCode", "")) == subcode for item in data if isinstance(item, dict))


def attached_stop_order(config: BotConfig, pos_side: str, entry_px: Decimal, tick: Decimal) -> dict[str, Any]:
    trigger_px = exchange_stop_trigger_price(config, pos_side, entry_px, tick)
    return {
        "attachAlgoClOrdId": exchange_stop_client_id(config, pos_side, trigger_px),
        "slTriggerPx": plain(trigger_px),
        "slOrdPx": "-1",
        "slTriggerPxType": config.exchange_stop_trigger_px_type,
    }


def cancel_orders(client: OkxRestClient, config: BotConfig, orders: list[dict[str, Any]], *, reason: str) -> None:
    for order in orders[: config.max_actions_per_cycle]:
        cancel_one(client, config, order, reason=reason)


def cancel_all_bot_orders(client: OkxRestClient, config: BotConfig, orders: list[dict[str, Any]], *, reason: str) -> None:
    if not orders:
        return
    if config.live:
        payload = [
            {"instId": config.inst_id, "ordId": order.get("ordId", ""), "clOrdId": order.get("clOrdId", "")}
            for order in orders
        ]
        response = client.cancel_orders(payload)
        print(f"LIVE cancel_all count={len(orders)} reason={reason} -> {response.get('data')}")
    else:
        response = {"dryRun": True, "data": orders}
        print(f"DRY cancel_all count={len(orders)} reason={reason}")
    log_event("cancel_all", {"live": config.live, "reason": reason, "orders": orders, "response": response})


def cancel_one(client: OkxRestClient, config: BotConfig, order: dict[str, Any], *, reason: str) -> None:
    payload = {
        "inst_id": config.inst_id,
        "ord_id": order.get("ordId"),
        "cl_ord_id": order.get("clOrdId"),
    }
    if config.live:
        response = client.cancel_order(inst_id=config.inst_id, ord_id=order.get("ordId"), cl_ord_id=order.get("clOrdId"))
        print(f"LIVE cancel {order.get('clOrdId')} reason={reason} -> {response.get('data')}")
    else:
        response = {"dryRun": True, "data": [payload]}
        print(f"DRY cancel {order.get('clOrdId')} reason={reason}")
    log_event("cancel", {"live": config.live, "reason": reason, "order": order, "response": response})


def set_leverage(client: OkxRestClient, config: BotConfig) -> None:
    for pos_side in ("long", "short"):
        payload = {
            "inst_id": config.inst_id,
            "lever": plain(config.leverage),
            "mgn_mode": "cross",
            "pos_side": pos_side,
        }
        if config.live:
            response = client.set_leverage(**payload)
            print(f"LIVE set leverage {pos_side} {config.leverage}x -> {response.get('data')}")
        else:
            response = {"dryRun": True, "data": [payload]}
            print(f"DRY set leverage {pos_side} {config.leverage}x")
        log_event("set_leverage", {"live": config.live, "payload": payload, "response": response})


def sync_exchange_protection_stops(
    client: OkxRestClient,
    config: BotConfig,
    state: dict[str, Any],
    tick: Decimal,
    lot: Decimal,
) -> int:
    existing = [order for order in state.get("pendingAlgos", []) if is_bot_algo_stop(order)]
    desired = desired_exchange_stops(config, state.get("positions", []), tick, lot)
    stale = stale_exchange_stops(existing, desired, config.exchange_stop_reprice_bps)
    missing = missing_exchange_stops(existing, desired, config.exchange_stop_reprice_bps)
    config.exchange_stop_triggers = {
        str(order["pos_side"]): dec(order.get("sl_trigger_px"), Decimal("0"))
        for order in desired
        if dec(order.get("sl_trigger_px"), Decimal("0")) > 0
    }

    if not existing and not desired:
        return 0
    print(f"exchange_stop desired={len(desired)} existing={len(existing)} missing={len(missing)} stale={len(stale)}")

    actions = 0
    if stale:
        orders = [{"instId": config.inst_id, "algoId": str(order.get("algoId"))} for order in stale if order.get("algoId")]
        if orders:
            if config.live:
                response = client.cancel_algo_orders(orders)
                print(f"LIVE cancel_exchange_stop count={len(orders)} -> {response.get('data')}")
            else:
                response = {"dryRun": True, "data": orders}
                print(f"DRY cancel_exchange_stop count={len(orders)}")
            log_event("cancel_exchange_stop", {"live": config.live, "orders": stale, "response": response})
            actions += len(orders)

    for order in missing[: max(0, config.max_actions_per_cycle - actions)]:
        if config.live:
            response = client.place_algo_order(**{key: value for key, value in order.items() if key != "tag"})
            print(
                f"LIVE place_exchange_stop {order['pos_side']} {order['sz']} "
                f"trigger={order['sl_trigger_px']} type={order['sl_trigger_px_type']} -> {response.get('data')}"
            )
        else:
            response = {"dryRun": True, "data": [order]}
            print(f"DRY place_exchange_stop {order['pos_side']} {order['sz']} trigger={order['sl_trigger_px']}")
        log_event("place_exchange_stop", {"live": config.live, "order": order, "response": response})
        actions += 1

    return actions


def desired_exchange_stops(
    config: BotConfig,
    positions: list[dict[str, Any]],
    tick: Decimal,
    lot: Decimal,
) -> list[dict[str, Any]]:
    if not config.exchange_stop_enabled or config.exchange_stop_bps <= 0 or config.leverage <= 0:
        return []

    desired: list[dict[str, Any]] = []
    for item in positions:
        pos_side = str(item.get("posSide", ""))
        if pos_side not in {"long", "short"}:
            continue
        size = round_size(abs(dec(item.get("pos"), Decimal("0"))), lot)
        avg_px = dec(item.get("avgPx"), Decimal("0"))
        if size <= 0 or avg_px <= 0:
            continue
        trigger_px = exchange_stop_trigger_price(config, pos_side, avg_px, tick)
        side = "sell" if pos_side == "long" else "buy"
        desired.append(
            {
                "inst_id": config.inst_id,
                "td_mode": "cross",
                "side": side,
                "pos_side": pos_side,
                "ord_type": "conditional",
                "sz": plain(size),
                "algo_cl_ord_id": exchange_stop_client_id(config, pos_side, trigger_px),
                "sl_trigger_px": plain(trigger_px),
                "sl_ord_px": "-1",
                "sl_trigger_px_type": config.exchange_stop_trigger_px_type,
                "reduce_only": True,
                "cxl_on_close_pos": True,
                "tag": "exchange_stop",
            }
        )
    return desired


def exchange_stop_trigger_price(config: BotConfig, pos_side: str, avg_px: Decimal, tick: Decimal) -> Decimal:
    price_bps = config.exchange_stop_bps / config.leverage
    gap = price_bps / Decimal("10000")
    raw = avg_px * (Decimal("1") - gap) if pos_side == "long" else avg_px * (Decimal("1") + gap)
    return round_to_tick(raw, tick)


def detect_triggered_exchange_stop(config: BotConfig, state: dict[str, Any]) -> dict[str, Any] | None:
    if not config.exchange_stop_triggers:
        return None
    positions = position_summary(state.get("positions", []))
    fills = state.get("fills", [])
    for pos_side, trigger_px in list(config.exchange_stop_triggers.items()):
        if pos_side not in {"long", "short"}:
            continue
        if positions.get(pos_side, Decimal("0")) > 0:
            continue
        fill = latest_loss_close_fill(pos_side, fills, since_ms=config.bot_started_ms)
        if fill is None:
            config.exchange_stop_triggers.pop(pos_side, None)
            continue
        config.exchange_stop_triggers.pop(pos_side, None)
        return {
            "posSide": pos_side,
            "triggerPx": plain(trigger_px),
            "fillPnl": fill.get("fillPnl"),
            "fillPx": fill.get("fillPx"),
            "fillSz": fill.get("fillSz"),
            "fillTime": fill_time_ms(fill),
            "ordId": fill.get("ordId"),
        }
    return None


def latest_loss_close_fill(pos_side: str, fills: list[dict[str, Any]], *, since_ms: int) -> dict[str, Any] | None:
    close_side = "sell" if pos_side == "long" else "buy"
    candidates = []
    for fill in fills:
        if fill_time_ms(fill) < since_ms:
            continue
        if str(fill.get("side", "")) != close_side:
            continue
        if str(fill.get("posSide", "")) != pos_side:
            continue
        if dec(fill.get("fillPnl"), Decimal("0")) >= 0:
            continue
        candidates.append(fill)
    if not candidates:
        return None
    return max(candidates, key=fill_time_ms)


def stale_exchange_stops(
    existing: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    reprice_bps: Decimal,
) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    for order in existing:
        match = desired_exchange_stop_for_existing(order, desired)
        if match is None or not exchange_stop_matches(order, match, reprice_bps):
            stale.append(order)
    return stale


def missing_exchange_stops(
    existing: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    reprice_bps: Decimal,
) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for order in desired:
        matches = [existing_order for existing_order in existing if exchange_stop_same_side(existing_order, order)]
        if not any(exchange_stop_matches(existing_order, order, reprice_bps) for existing_order in matches):
            missing.append(order)
    return missing


def desired_exchange_stop_for_existing(order: dict[str, Any], desired: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in desired:
        if exchange_stop_same_side(order, item):
            return item
    return None


def exchange_stop_same_side(existing: dict[str, Any], desired: dict[str, Any]) -> bool:
    return (
        str(existing.get("instId", "")) == str(desired.get("inst_id", ""))
        and str(existing.get("side", "")) == str(desired.get("side", ""))
        and str(existing.get("posSide", "")) == str(desired.get("pos_side", ""))
        and str(existing.get("ordType", "")) == str(desired.get("ord_type", ""))
    )


def exchange_stop_matches(existing: dict[str, Any], desired: dict[str, Any], reprice_bps: Decimal) -> bool:
    if not exchange_stop_same_side(existing, desired):
        return False
    if dec(existing.get("sz"), Decimal("0")) != dec(desired.get("sz"), Decimal("0")):
        return False
    if str(existing.get("slOrdPx", "")) not in {str(desired.get("sl_ord_px", "")), ""}:
        return False
    trigger_type = str(existing.get("slTriggerPxType", "") or desired.get("sl_trigger_px_type", ""))
    if trigger_type != str(desired.get("sl_trigger_px_type", "")):
        return False
    existing_trigger = dec(existing.get("slTriggerPx"), Decimal("0"))
    desired_trigger = dec(desired.get("sl_trigger_px"), Decimal("0"))
    if existing_trigger <= 0 or desired_trigger <= 0:
        return False
    if reprice_bps <= 0:
        return existing_trigger == desired_trigger
    diff_bps = abs(existing_trigger / desired_trigger - Decimal("1")) * Decimal("10000")
    return diff_bps <= reprice_bps


def is_bot_algo_stop(order: dict[str, Any]) -> bool:
    return str(order.get("algoClOrdId", "")).startswith(exchange_stop_prefix())


def exchange_stop_client_id(config: BotConfig, pos_side: str, trigger_px: Decimal) -> str:
    normalized = str(trigger_px).replace(".", "")
    return f"{exchange_stop_prefix()}{pos_side[0]}{normalized}"[:32]


def exchange_stop_prefix() -> str:
    return f"xs{BOT_PREFIX}"


def load_runtime_config(config: BotConfig) -> None:
    if not RUNTIME_CONFIG_PATH.exists():
        return
    mtime = RUNTIME_CONFIG_PATH.stat().st_mtime
    if mtime <= config.runtime_config_mtime:
        return
    try:
        payload = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
        runtime_inst_id = str(payload.get("instId", "") or "")
        if not runtime_inst_id and runtime_config_has_trading_fields(payload):
            config.runtime_config_mtime = mtime
            log_event(
                "runtime_config_missing_inst",
                {
                    "path": str(RUNTIME_CONFIG_PATH),
                    "botInstId": config.inst_id,
                },
            )
            print(f"Runtime config ignored: missing instId for bot instId {config.inst_id}")
            return
        if runtime_inst_id and runtime_inst_id != config.inst_id:
            config.runtime_config_mtime = mtime
            log_event(
                "runtime_config_inst_mismatch",
                {
                    "path": str(RUNTIME_CONFIG_PATH),
                    "runtimeInstId": runtime_inst_id,
                    "botInstId": config.inst_id,
                },
            )
            print(
                f"Runtime config ignored: instId {runtime_inst_id} does not match bot instId {config.inst_id}"
            )
            return
        apply_runtime_config(config, payload)
        config.runtime_config_mtime = mtime
        log_event("runtime_config_loaded", {"path": str(RUNTIME_CONFIG_PATH), "payload": payload})
        print(f"Runtime config applied from {RUNTIME_CONFIG_PATH}")
    except Exception as exc:
        config.runtime_config_mtime = mtime
        log_event("runtime_config_error", {"error": str(exc)})
        print(f"Runtime config ignored: {exc}")


def runtime_config_has_trading_fields(payload: dict[str, Any]) -> bool:
    fields = {
        "lower",
        "upper",
        "leverage",
        "gridBps",
        "orderSz",
        "maxPosition",
        "orderMarginPct",
        "maxMarginPct",
        "sizingMode",
        "marketRegimeFilter",
        "marketRegimeModelPath",
    }
    return any(field in payload for field in fields)


def apply_rolling_adaptive_config(
    client: OkxRestClient,
    config: BotConfig,
    state: dict[str, Any],
    mark_px: Decimal,
) -> None:
    if not config.rolling_adaptive_enabled:
        return
    if config.live and not config.set_leverage:
        raise RuntimeError("Rolling adaptive live mode requires --set-leverage so exchange leverage matches sizing.")

    meta = state.get("meta", {})
    equity, _available = balance_summary(state.get("balance", {}))
    limits = rolling_adaptive_limits(config)
    result = calculate_rolling_adaptive(
        state.get("candles", []),
        mark_px=mark_px,
        equity=equity,
        ct_val=dec(meta.get("ctVal"), Decimal("0")),
        min_sz=dec(meta.get("minSz"), Decimal("0")),
        limits=limits,
    )

    last_synced_leverage = config.rolling_adaptive_last_leverage
    old_leverage = config.leverage
    config.leverage = result.leverage
    config.grid_bps = result.grid_bps
    config.adaptive_width_bps = result.adaptive_width_bps
    config.adaptive_min_width_bps = result.adaptive_min_width_bps
    config.adaptive_max_width_bps = result.adaptive_max_width_bps
    config.adaptive_vol_multiplier = limits.width_vol_multiplier
    config.sizing_mode = "margin_pct"
    config.order_margin_pct = result.order_margin_pct
    config.max_margin_pct = result.max_margin_pct
    config.min_tp_bps = result.min_tp_bps
    config.position_loss_sl_bps = result.position_loss_sl_bps
    config.exchange_stop_bps = result.exchange_stop_bps
    config.total_profit_tp_pct = result.total_profit_tp_pct
    config.total_loss_sl_pct = result.total_loss_sl_pct

    if result.tradeable_min_contract:
        note = result.note
    else:
        note = f"{result.note} min contract exceeds adaptive max margin cap; open sizing may resolve to zero"
    print(
        f"rolling_adaptive leverage={plain(config.leverage)}x grid={plain(config.grid_bps)}bps "
        f"order_margin={plain(config.order_margin_pct)}% max_margin={plain(config.max_margin_pct)}% "
        f"tp={plain(config.min_tp_bps)}bps sl={plain(config.position_loss_sl_bps)}bps {note}"
    )
    log_event(
        "rolling_adaptive",
        {
            "live": config.live,
            "oldLeverage": old_leverage,
            "result": result_to_dict(result),
        },
    )

    leverage_needs_sync = config.rolling_adaptive_last_leverage != config.leverage
    if config.set_leverage and config.live and leverage_needs_sync:
        try:
            set_leverage(client, config)
            config.rolling_adaptive_last_leverage = config.leverage
        except Exception as exc:
            log_event(
                "rolling_adaptive_leverage_error",
                {
                    "oldLeverage": old_leverage,
                    "lastSyncedLeverage": last_synced_leverage,
                    "newLeverage": config.leverage,
                    "error": str(exc),
                },
            )
            raise RuntimeError(f"Rolling adaptive leverage sync failed; no orders placed this cycle: {exc}") from exc
    elif config.set_leverage and not config.live and leverage_needs_sync:
        set_leverage(client, config)
        config.rolling_adaptive_last_leverage = config.leverage


def rolling_adaptive_limits(config: BotConfig) -> RollingAdaptiveLimits:
    return RollingAdaptiveLimits(
        window=config.rolling_adaptive_window,
        low_vol_bps=config.rolling_adaptive_low_vol_bps,
        high_vol_bps=config.rolling_adaptive_high_vol_bps,
        min_leverage=config.rolling_adaptive_min_leverage,
        max_leverage=config.rolling_adaptive_max_leverage,
        min_grid_bps=config.rolling_adaptive_min_grid_bps,
        max_grid_bps=config.rolling_adaptive_max_grid_bps,
        grid_vol_multiplier=config.rolling_adaptive_grid_vol_multiplier,
        min_width_bps=config.rolling_adaptive_min_width_bps,
        max_width_bps=config.rolling_adaptive_max_width_bps,
        width_vol_multiplier=config.rolling_adaptive_width_vol_multiplier,
        min_order_margin_pct=config.rolling_adaptive_min_order_margin_pct,
        max_order_margin_pct=config.rolling_adaptive_max_order_margin_pct,
        min_max_margin_pct=config.rolling_adaptive_min_max_margin_pct,
        max_max_margin_pct=config.rolling_adaptive_max_max_margin_pct,
        min_stop_bps=config.rolling_adaptive_min_stop_bps,
        max_stop_bps=config.rolling_adaptive_max_stop_bps,
        stop_vol_multiplier=config.rolling_adaptive_stop_vol_multiplier,
        min_tp_bps=config.rolling_adaptive_min_tp_bps,
        max_tp_bps=config.rolling_adaptive_max_tp_bps,
        tp_grid_multiplier=config.rolling_adaptive_tp_grid_multiplier,
        min_total_profit_tp_pct=config.rolling_adaptive_min_total_profit_tp_pct,
        max_total_profit_tp_pct=config.rolling_adaptive_max_total_profit_tp_pct,
        min_total_loss_sl_pct=config.rolling_adaptive_min_total_loss_sl_pct,
        max_total_loss_sl_pct=config.rolling_adaptive_max_total_loss_sl_pct,
    )


def apply_runtime_config(config: BotConfig, payload: dict[str, Any]) -> None:
    decimal_fields = {
        "lower": "lower",
        "upper": "upper",
        "leverage": "leverage",
        "gridBps": "grid_bps",
        "minNetBps": "min_net_bps",
        "softBps": "soft_bps",
        "hardBps": "hard_bps",
        "orderSz": "order_sz",
        "maxPosition": "max_position",
        "adaptiveWidthBps": "adaptive_width_bps",
        "adaptiveMinWidthBps": "adaptive_min_width_bps",
        "adaptiveMaxWidthBps": "adaptive_max_width_bps",
        "adaptiveVolMultiplier": "adaptive_vol_multiplier",
        "rangeDriftWeightBps": "range_drift_weight_bps",
        "rangeDriftMaxBps": "range_drift_max_bps",
        "orderMarginPct": "order_margin_pct",
        "maxMarginPct": "max_margin_pct",
        "cashReservePct": "cash_reserve_pct",
        "totalProfitTp": "total_profit_tp",
        "totalProfitTpPct": "total_profit_tp_pct",
        "totalProfitTpCap": "total_profit_tp_cap",
        "minTpProfit": "min_tp_profit",
        "totalLossSl": "total_loss_sl",
        "totalLossSlPct": "total_loss_sl_pct",
        "totalLossSlCap": "total_loss_sl_cap",
        "positionLossSlBps": "position_loss_sl_bps",
        "exchangeStopBps": "exchange_stop_bps",
        "exchangeStopRepriceBps": "exchange_stop_reprice_bps",
        "minTpBps": "min_tp_bps",
        "missedTpSlippageBps": "missed_tp_slippage_bps",
        "hardStopSlippageBps": "hard_stop_slippage_bps",
        "trendThresholdBps": "trend_threshold_bps",
        "marketRegimeMinConfidence": "market_regime_min_confidence",
        "regimeDiffBps": "regime_diff_bps",
        "rollingAdaptiveLowVolBps": "rolling_adaptive_low_vol_bps",
        "rollingAdaptiveHighVolBps": "rolling_adaptive_high_vol_bps",
        "rollingAdaptiveMinLeverage": "rolling_adaptive_min_leverage",
        "rollingAdaptiveMaxLeverage": "rolling_adaptive_max_leverage",
        "rollingAdaptiveMinGridBps": "rolling_adaptive_min_grid_bps",
        "rollingAdaptiveMaxGridBps": "rolling_adaptive_max_grid_bps",
        "rollingAdaptiveGridVolMultiplier": "rolling_adaptive_grid_vol_multiplier",
        "rollingAdaptiveMinWidthBps": "rolling_adaptive_min_width_bps",
        "rollingAdaptiveMaxWidthBps": "rolling_adaptive_max_width_bps",
        "rollingAdaptiveWidthVolMultiplier": "rolling_adaptive_width_vol_multiplier",
        "rollingAdaptiveMinOrderMarginPct": "rolling_adaptive_min_order_margin_pct",
        "rollingAdaptiveMaxOrderMarginPct": "rolling_adaptive_max_order_margin_pct",
        "rollingAdaptiveMinMaxMarginPct": "rolling_adaptive_min_max_margin_pct",
        "rollingAdaptiveMaxMaxMarginPct": "rolling_adaptive_max_max_margin_pct",
        "rollingAdaptiveMinStopBps": "rolling_adaptive_min_stop_bps",
        "rollingAdaptiveMaxStopBps": "rolling_adaptive_max_stop_bps",
        "rollingAdaptiveStopVolMultiplier": "rolling_adaptive_stop_vol_multiplier",
        "rollingAdaptiveMinTpBps": "rolling_adaptive_min_tp_bps",
        "rollingAdaptiveMaxTpBps": "rolling_adaptive_max_tp_bps",
        "rollingAdaptiveTpGridMultiplier": "rolling_adaptive_tp_grid_multiplier",
        "rollingAdaptiveMinTotalProfitTpPct": "rolling_adaptive_min_total_profit_tp_pct",
        "rollingAdaptiveMaxTotalProfitTpPct": "rolling_adaptive_max_total_profit_tp_pct",
        "rollingAdaptiveMinTotalLossSlPct": "rolling_adaptive_min_total_loss_sl_pct",
        "rollingAdaptiveMaxTotalLossSlPct": "rolling_adaptive_max_total_loss_sl_pct",
    }
    int_fields = {
        "maxOpenOrdersPerSide": "max_open_orders_per_side",
        "maxActionsPerCycle": "max_actions_per_cycle",
        "trendLookback": "trend_lookback",
        "regimeShortMa": "regime_short_ma",
        "regimeLongMa": "regime_long_ma",
        "regimeConfirmBars": "regime_confirm_bars",
        "rollingAdaptiveWindow": "rolling_adaptive_window",
    }
    enum_fields = {
        "ordType": ("ord_type", {"post_only", "limit"}),
        "mode": ("mode", {"fixed", "adaptive"}),
        "rangeDriftMode": ("range_drift_mode", {"off", "cooldown"}),
        "sizingMode": ("sizing_mode", {"fixed", "margin_pct"}),
        "missedTpOrdType": ("missed_tp_ord_type", {"limit", "market"}),
        "hardStopOrdType": ("hard_stop_ord_type", {"limit", "market"}),
        "totalProfitAction": ("total_profit_action", {"checkpoint", "close"}),
        "trendFilter": ("trend_filter", {"off", "auto"}),
        "marketRegimeFilter": ("market_regime_filter", {"off", "rules", "rf", "hmm"}),
        "regimeFilter": ("regime_filter", {"off", "ma_cross"}),
        "regimeBar": ("regime_bar", {"5m", "15m", "30m", "1H"}),
        "exchangeStopTriggerPxType": ("exchange_stop_trigger_px_type", {"last", "mark", "index"}),
    }
    for key, attr in decimal_fields.items():
        if key in payload:
            setattr(config, attr, Decimal(str(payload[key])))
    for key, attr in int_fields.items():
        if key in payload:
            setattr(config, attr, max(1, int(payload[key])))
    for key, (attr, allowed) in enum_fields.items():
        if key in payload and str(payload[key]) in allowed:
            setattr(config, attr, str(payload[key]))
    if "interval" in payload:
        config.interval = max(1.0, float(payload["interval"]))
    if "riskCooldown" in payload:
        config.risk_cooldown = max(0.0, float(payload["riskCooldown"]))
    if "marketRegimeModelPath" in payload:
        config.market_regime_model_path = str(payload["marketRegimeModelPath"])
    if "cancelOnStop" in payload:
        config.cancel_on_stop = bool(payload["cancelOnStop"])
    if "exchangeStopEnabled" in payload:
        config.exchange_stop_enabled = bool(payload["exchangeStopEnabled"])
    if "recenterOnCooldown" in payload:
        config.recenter_on_cooldown = bool(payload["recenterOnCooldown"])
    if "oneWayOpen" in payload:
        config.one_way_open = bool(payload["oneWayOpen"])
    if "setLeverage" in payload:
        config.set_leverage = bool(payload["setLeverage"])
    if "rollingAdaptiveEnabled" in payload:
        config.rolling_adaptive_enabled = bool(payload["rollingAdaptiveEnabled"])
    config.trend_lookback = max(1, config.trend_lookback)
    config.regime_short_ma = max(1, config.regime_short_ma)
    config.regime_long_ma = max(config.regime_short_ma + 1, config.regime_long_ma)
    config.rolling_adaptive_window = max(2, config.rolling_adaptive_window)
    config.rolling_adaptive_min_leverage = max(Decimal("1"), config.rolling_adaptive_min_leverage)
    config.rolling_adaptive_max_leverage = max(config.rolling_adaptive_min_leverage, config.rolling_adaptive_max_leverage)
    config.rolling_adaptive_min_grid_bps = max(Decimal("1"), config.rolling_adaptive_min_grid_bps)
    config.rolling_adaptive_max_grid_bps = max(config.rolling_adaptive_min_grid_bps, config.rolling_adaptive_max_grid_bps)
    config.rolling_adaptive_min_width_bps = max(Decimal("1"), config.rolling_adaptive_min_width_bps)
    config.rolling_adaptive_max_width_bps = max(config.rolling_adaptive_min_width_bps, config.rolling_adaptive_max_width_bps)
    config.rolling_adaptive_min_order_margin_pct = clamp_pct(config.rolling_adaptive_min_order_margin_pct)
    config.cash_reserve_pct = clamp_pct(config.cash_reserve_pct)
    config.rolling_adaptive_max_order_margin_pct = max(
        config.rolling_adaptive_min_order_margin_pct,
        clamp_pct(config.rolling_adaptive_max_order_margin_pct),
    )
    config.rolling_adaptive_min_max_margin_pct = clamp_pct(config.rolling_adaptive_min_max_margin_pct)
    config.rolling_adaptive_max_max_margin_pct = max(
        config.rolling_adaptive_min_max_margin_pct,
        clamp_pct(config.rolling_adaptive_max_max_margin_pct),
    )
    config.rolling_adaptive_min_stop_bps = max(Decimal("1"), config.rolling_adaptive_min_stop_bps)
    config.rolling_adaptive_max_stop_bps = max(config.rolling_adaptive_min_stop_bps, config.rolling_adaptive_max_stop_bps)
    config.rolling_adaptive_min_tp_bps = max(Decimal("0"), config.rolling_adaptive_min_tp_bps)
    config.rolling_adaptive_max_tp_bps = max(config.rolling_adaptive_min_tp_bps, config.rolling_adaptive_max_tp_bps)
    config.regime_confirm_bars = max(1, config.regime_confirm_bars)


def position_summary(positions: list[dict[str, Any]]) -> dict[str, Decimal]:
    result = {
        "long": Decimal("0"),
        "short": Decimal("0"),
        "long_avg": Decimal("0"),
        "short_avg": Decimal("0"),
    }
    for item in positions:
        pos_side = item.get("posSide")
        pos = abs(dec(item.get("pos"), Decimal("0")))
        avg = dec(item.get("avgPx"), Decimal("0"))
        if pos_side == "long":
            result["long"] = pos
            result["long_avg"] = avg
        elif pos_side == "short":
            result["short"] = pos
            result["short_avg"] = avg
    return result


def estimated_total_pnl(state: dict[str, Any], since_ms: int) -> Decimal:
    unrealized = sum(dec(item.get("upl"), Decimal("0")) for item in state.get("positions", []))
    session_fills = [item for item in state.get("fills", []) if fill_time_ms(item) >= since_ms]
    realized = sum(dec(item.get("fillPnl"), Decimal("0")) for item in session_fills)
    fees = sum(dec(item.get("fee"), Decimal("0")) for item in session_fills)
    return unrealized + realized + fees


def pnl_breakdown(state: dict[str, Any], since_ms: int) -> dict[str, Decimal | int]:
    unrealized = sum(dec(item.get("upl"), Decimal("0")) for item in state.get("positions", []))
    session_fills = [item for item in state.get("fills", []) if fill_time_ms(item) >= since_ms]
    realized = sum(dec(item.get("fillPnl"), Decimal("0")) for item in session_fills)
    fees = sum(dec(item.get("fee"), Decimal("0")) for item in session_fills)
    return {
        "unrealized": unrealized,
        "sessionRealized": realized,
        "sessionFees": fees,
        "sessionFillCount": len(session_fills),
        "estimatedTotal": unrealized + realized + fees,
    }


def fill_time_ms(fill: dict[str, Any]) -> int:
    value = fill.get("fillTime") or fill.get("ts") or "0"
    try:
        return int(value)
    except Exception:
        return 0


def pnl_threshold(
    state: dict[str, Any],
    *,
    fixed: Decimal,
    pct: Decimal,
    cap: Decimal,
) -> tuple[Decimal, str]:
    equity, _available = balance_summary(state.get("balance", {}))
    fixed = max(Decimal("0"), fixed)
    pct = max(Decimal("0"), pct)
    cap = max(Decimal("0"), cap)
    pct_value = equity * pct / Decimal("100") if equity > 0 and pct > 0 else Decimal("0")
    if pct_value > 0:
        target = pct_value
        note_parts = [f"{plain(pct)}% equity={plain(pct_value)}"]
    elif fixed > 0:
        target = fixed
        note_parts = [f"fixed={plain(fixed)}"]
    else:
        return Decimal("0"), "disabled"
    if cap > 0 and target > cap:
        target = cap
        note_parts.append(f"cap={plain(cap)}")
    return target, ", ".join(note_parts)


def missed_take_profit_orders(
    config: BotConfig,
    state: dict[str, Any],
    mark_px: Decimal,
    step: Decimal,
    tick: Decimal,
    ct_val: Decimal,
    edge: dict[str, Decimal],
) -> list[dict[str, Any]]:
    positions = position_summary(state["positions"])
    orders: list[dict[str, Any]] = []

    if positions["long"] > 0:
        target = tp_price(config, "long", positions["long_avg"] or mark_px, step, tick, positions["long"], ct_val, edge)
        if mark_px >= target:
            orders.append(close_position_order(config, "sell", "long", positions["long"], mark_px, tick, "missed_tp_long"))

    if positions["short"] > 0:
        target = tp_price(config, "short", positions["short_avg"] or mark_px, step, tick, positions["short"], ct_val, edge)
        if mark_px <= target:
            orders.append(close_position_order(config, "buy", "short", positions["short"], mark_px, tick, "missed_tp_short"))

    return orders


def position_loss_stop(config: BotConfig, positions: list[dict[str, Any]], mark_px: Decimal) -> dict[str, Any] | None:
    if config.position_loss_sl_bps <= 0 or mark_px <= 0:
        return None
    worst: dict[str, Any] | None = None
    for item in positions:
        pos_side = item.get("posSide")
        if pos_side not in {"long", "short"}:
            continue
        size = abs(dec(item.get("pos"), Decimal("0")))
        avg_px = dec(item.get("avgPx"), Decimal("0"))
        if size <= 0 or avg_px <= 0:
            continue
        upl_ratio = dec(item.get("uplRatio"), Decimal("0"))
        if upl_ratio < 0:
            adverse_bps = abs(upl_ratio) * Decimal("10000")
            metric = "uplRatio"
        else:
            metric = "priceMoveLevered"
            if pos_side == "long":
                adverse_bps = (avg_px - mark_px) / avg_px * Decimal("10000") * config.leverage
            else:
                adverse_bps = (mark_px - avg_px) / avg_px * Decimal("10000") * config.leverage
        if adverse_bps < config.position_loss_sl_bps:
            continue
        payload = {
            "posSide": pos_side,
            "size": plain(size),
            "avgPx": plain(avg_px),
            "markPx": plain(mark_px),
            "adverseBps": adverse_bps,
            "metric": metric,
            "uplRatio": upl_ratio,
            "upl": dec(item.get("upl"), Decimal("0")),
        }
        if worst is None or adverse_bps > worst["adverseBps"]:
            worst = payload
    return worst


def handle_price_hard_stop(
    client: OkxRestClient,
    config: BotConfig,
    state: dict[str, Any],
    bot_orders: list[dict[str, Any]],
    tick: Decimal,
    stop_state: str,
) -> bool:
    pos_side = "long" if stop_state == "hard_low" else "short"
    print(f"Price hard stop {stop_state}: canceling all bot orders and closing {pos_side} side.")
    try:
        cancel_all_bot_orders(client, config, bot_orders, reason=stop_state)
    except Exception as exc:
        log_event("risk_cancel_error", {"reason": stop_state, "error": str(exc)})
        print(f"Price hard stop {stop_state}: cancel failed, still trying reduce-only close: {exc}")
    closed = close_positions_by_side(client, config, state["positions"], tick, pos_side, reason=stop_state)
    if not closed:
        print(f"Price hard stop {stop_state}: no {pos_side} position to close.")
    log_event("price_hard_stop", {"live": config.live, "state": stop_state, "closedSide": pos_side, "closed": closed})
    return closed > 0 or not has_position_by_side(state["positions"], pos_side)


def enter_risk_cooldown(config: BotConfig, reason: str) -> None:
    if config.risk_cooldown <= 0:
        print(f"Risk event {reason}: cooldown disabled, continuing next cycle.")
        config.bot_started_ms = current_ms()
        return
    config.cooldown_until_ms = current_ms() + int(config.risk_cooldown * 1000)
    config.cooldown_reason = reason
    config.recenter_pending = config.recenter_on_cooldown
    print(
        f"Risk event {reason}: entering cooldown {config.risk_cooldown}s. "
        f"recenter_on_resume={config.recenter_pending}"
    )
    log_event(
        "risk_cooldown",
        {
            "live": config.live,
            "reason": reason,
            "cooldownSeconds": config.risk_cooldown,
            "recenterOnResume": config.recenter_pending,
        },
    )


def recenter_outer_range(config: BotConfig, mark_px: Decimal, tick: Decimal) -> None:
    if config.range_drift_mode == "off" or config.range_drift_weight_bps <= 0 or mark_px <= 0:
        print(f"Recenter skipped: keeping fixed outer guard {config.lower}-{config.upper} around mark={mark_px}")
        log_event(
            "recenter_range",
            {
                "keptLower": config.lower,
                "keptUpper": config.upper,
                "mark": mark_px,
                "skipped": True,
            },
        )
        return

    old_lower = config.lower
    old_upper = config.upper
    width = old_upper - old_lower
    if width <= 0:
        print(f"Recenter skipped: invalid fixed outer guard {old_lower}-{old_upper}")
        return

    midpoint = (old_lower + old_upper) / Decimal("2")
    desired_shift = mark_px - midpoint
    weight = min(max(config.range_drift_weight_bps, Decimal("0")), Decimal("10000")) / Decimal("10000")
    weighted_shift = desired_shift * weight
    max_shift = midpoint * max(config.range_drift_max_bps, Decimal("0")) / Decimal("10000")
    if max_shift > 0:
        weighted_shift = max(-max_shift, min(weighted_shift, max_shift))

    if abs(weighted_shift) < tick / Decimal("2"):
        print(
            f"Recenter skipped: drift {plain(weighted_shift)} is below half tick; "
            f"keeping {old_lower}-{old_upper} around mark={mark_px}"
        )
        log_event(
            "recenter_range",
            {
                "keptLower": old_lower,
                "keptUpper": old_upper,
                "mark": mark_px,
                "shift": weighted_shift,
                "skipped": True,
            },
        )
        return

    config.lower = round_to_tick(old_lower + weighted_shift, tick)
    config.upper = round_to_tick(config.lower + width, tick)
    print(
        f"Weighted recenter outer range {old_lower}-{old_upper} -> {config.lower}-{config.upper} "
        f"mark={mark_px} weight={plain(config.range_drift_weight_bps)}bps "
        f"max_shift={plain(config.range_drift_max_bps)}bps"
    )
    log_event(
        "recenter_range",
        {
            "oldLower": old_lower,
            "oldUpper": old_upper,
            "newLower": config.lower,
            "newUpper": config.upper,
            "mark": mark_px,
            "shift": weighted_shift,
            "weightBps": config.range_drift_weight_bps,
            "maxShiftBps": config.range_drift_max_bps,
            "mode": config.range_drift_mode,
        },
    )


def risk_close_all_positions(
    client: OkxRestClient,
    config: BotConfig,
    positions: list[dict[str, Any]],
    tick: Decimal,
    bot_orders: list[dict[str, Any]],
    *,
    reason: str,
) -> bool:
    try:
        cancel_all_bot_orders(client, config, bot_orders, reason=reason)
    except Exception as exc:
        log_event("risk_cancel_error", {"reason": reason, "error": str(exc)})
        print(f"Risk close {reason}: cancel failed, still trying reduce-only close: {exc}")
    closed = close_all_positions(client, config, positions, tick, reason=reason)
    return closed > 0 or not has_open_position(positions)


def close_positions_by_side(
    client: OkxRestClient,
    config: BotConfig,
    positions: list[dict[str, Any]],
    tick: Decimal,
    pos_side: str,
    *,
    reason: str,
) -> int:
    closed = 0
    for item in positions:
        if item.get("posSide") != pos_side:
            continue
        size = abs(dec(item.get("pos"), Decimal("0")))
        mark_px = dec(item.get("markPx"), Decimal("0"))
        if size <= 0:
            continue
        side = "sell" if pos_side == "long" else "buy"
        order = close_position_order(
            config,
            side,
            pos_side,
            size,
            mark_px,
            tick,
            f"hard_stop_{reason}",
            ord_type=config.hard_stop_ord_type,
            slippage_bps=config.hard_stop_slippage_bps,
        )
        place_one(client, config, order)
        log_event("hard_stop_close", {"live": config.live, "reason": reason, "order": order})
        closed += 1
    return closed


def close_all_positions(client: OkxRestClient, config: BotConfig, positions: list[dict[str, Any]], tick: Decimal, *, reason: str) -> int:
    meta_note = {"reason": reason}
    closed = 0
    for item in positions[: config.max_actions_per_cycle]:
        pos_side = item.get("posSide")
        size = abs(dec(item.get("pos"), Decimal("0")))
        mark_px = dec(item.get("markPx"), Decimal("0"))
        if size <= 0 or pos_side not in {"long", "short"}:
            continue
        side = "sell" if pos_side == "long" else "buy"
        ord_type = config.hard_stop_ord_type if reason == "total_loss_sl" else config.missed_tp_ord_type
        slippage_bps = config.hard_stop_slippage_bps if reason == "total_loss_sl" else config.missed_tp_slippage_bps
        order = close_position_order(config, side, pos_side, size, mark_px, tick, f"close_all_{reason}", ord_type=ord_type, slippage_bps=slippage_bps)
        place_one(client, config, order)
        log_event("close_all", {"live": config.live, "order": order, **meta_note})
        closed += 1
    return closed


def has_open_position(positions: list[dict[str, Any]]) -> bool:
    return any(abs(dec(item.get("pos"), Decimal("0"))) > 0 for item in positions)


def has_position_by_side(positions: list[dict[str, Any]], pos_side: str) -> bool:
    return any(item.get("posSide") == pos_side and abs(dec(item.get("pos"), Decimal("0"))) > 0 for item in positions)


def close_position_order(
    config: BotConfig,
    side: str,
    pos_side: str,
    size: Decimal,
    mark_px: Decimal,
    tick: Decimal,
    tag: str,
    *,
    ord_type: str | None = None,
    slippage_bps: Decimal | None = None,
) -> dict[str, Any]:
    ord_type = ord_type or config.missed_tp_ord_type
    slippage_bps = config.missed_tp_slippage_bps if slippage_bps is None else slippage_bps
    order: dict[str, Any] = {
        "inst_id": config.inst_id,
        "td_mode": "cross",
        "side": side,
        "pos_side": pos_side,
        "ord_type": ord_type,
        "sz": plain(size),
        "reduce_only": True,
        "cl_ord_id": client_order_id(side, pos_side, mark_px, True),
        "tag": tag,
    }
    if ord_type != "market":
        order["px"] = plain(close_limit_price(side, mark_px, tick, slippage_bps))
    return order


def close_limit_price(side: str, mark_px: Decimal, tick: Decimal, slippage_bps: Decimal) -> Decimal:
    if tick <= 0:
        return mark_px
    bump = slippage_bps / Decimal("10000")
    if side == "buy":
        return round_to_tick(mark_px * (Decimal("1") + bump), tick)
    return round_to_tick(mark_px * (Decimal("1") - bump), tick)


def resolve_close_size(config: BotConfig, order_sz: Decimal, lot: Decimal, min_sz: Decimal) -> Decimal:
    if order_sz > 0:
        return round_size(max(order_sz, min_sz), lot)
    return round_size(max(config.order_sz, min_sz), lot)


def resolve_sizing(
    config: BotConfig,
    state: dict[str, Any],
    mark_px: Decimal,
    lot: Decimal,
    min_sz: Decimal,
) -> tuple[Decimal, Decimal, str]:
    if config.sizing_mode == "fixed":
        order_sz = round_size(max(config.order_sz, min_sz), lot)
        max_position = round_size(max(config.max_position, min_sz), lot) if config.max_position > 0 else Decimal("0")
        return order_sz, max_position, "fixed"

    meta = state["meta"]
    ct_val = dec(meta.get("ctVal"), Decimal("0"))
    if mark_px <= 0 or ct_val <= 0 or config.leverage <= 0:
        return Decimal("0"), Decimal("0"), "invalid contract sizing data"

    equity, available = balance_summary(state.get("balance", {}))
    reserved_open_margin = pending_open_margin(
        state.get("pending", []),
        ct_val=ct_val,
        leverage=config.leverage,
    )
    reserve_margin = equity * clamp_pct(config.cash_reserve_pct) / Decimal("100") if equity > 0 else Decimal("0")
    effective_available = max(Decimal("0"), available + reserved_open_margin - reserve_margin)
    basis_margin = min_positive(equity, effective_available)
    min_margin = min_sz * ct_val * mark_px / config.leverage
    if basis_margin <= 0 or basis_margin < min_margin:
        return (
            Decimal("0"),
            Decimal("0"),
            f"margin_pct basis={plain(basis_margin)} min_margin={plain(min_margin)} "
            f"reserve_margin={plain(reserve_margin)}",
        )

    order_margin = basis_margin * clamp_pct(config.order_margin_pct) / Decimal("100")
    raw_order_sz = order_margin * config.leverage / (mark_px * ct_val)
    order_sz = round_size(raw_order_sz, lot)
    if order_sz < min_sz:
        order_sz = min_sz

    max_margin = equity * clamp_pct(config.max_margin_pct) / Decimal("100")
    raw_max_position = max_margin * config.leverage / (mark_px * ct_val)
    max_position = round_size(raw_max_position, lot)
    if max_position < min_sz:
        max_position = min_sz if max_margin >= min_margin else Decimal("0")
    if config.max_position > 0:
        max_position = min(config.max_position, max_position)

    note = (
        f"margin_pct basis={plain(basis_margin)} equity={plain(equity)} "
        f"available={plain(available)} reserved_open_margin={plain(reserved_open_margin)} "
        f"reserve_margin={plain(reserve_margin)} effective_available={plain(effective_available)} "
        f"order_margin={plain(order_margin)} "
        f"max_margin={plain(max_margin)}"
    )
    return order_sz, max_position, note


def grid_edge_summary(config: BotConfig, state: dict[str, Any], step: Decimal, midpoint: Decimal) -> dict[str, Decimal]:
    fee = state.get("fee", {})
    maker_bps = abs(dec(fee.get("makerU") or fee.get("maker"), Decimal("0"))) * Decimal("10000")
    taker_bps = abs(dec(fee.get("takerU") or fee.get("taker"), Decimal("0"))) * Decimal("10000")
    open_fee_bps = taker_bps if config.ord_type == "limit" else maker_bps
    close_fee_bps = max(maker_bps, taker_bps)
    gross_bps = step / midpoint * Decimal("10000") if midpoint > 0 else Decimal("0")
    return {
        "grossBps": gross_bps,
        "makerBps": maker_bps,
        "takerBps": taker_bps,
        "openFeeBps": open_fee_bps,
        "closeFeeBps": close_fee_bps,
        "netBps": gross_bps - open_fee_bps - close_fee_bps,
    }


def balance_summary(balance: dict[str, Any]) -> tuple[Decimal, Decimal]:
    equity = dec(balance.get("totalEq"), Decimal("0"))
    available = Decimal("0")
    for item in balance.get("details", []):
        if item.get("ccy") == "USDT":
            available = dec(item.get("availBal"), Decimal("0"))
            equity = equity or dec(item.get("eq"), Decimal("0"))
            break
    return equity, available


def pending_open_margin(
    orders: list[dict[str, Any]],
    *,
    ct_val: Decimal,
    leverage: Decimal,
) -> Decimal:
    if ct_val <= 0 or leverage <= 0:
        return Decimal("0")
    total = Decimal("0")
    for order in orders:
        if not is_bot_order(order) or is_reduce_only_pending_order(order):
            continue
        px = dec(order.get("px"), Decimal("0"))
        sz = dec(order.get("sz"), Decimal("0"))
        if px <= 0 or sz <= 0:
            continue
        total += px * sz * ct_val / leverage
    return total


def fit_missing_orders_to_margin_budget(
    orders: list[dict[str, Any]],
    *,
    available: Decimal,
    reserve_margin: Decimal,
    ct_val: Decimal,
    leverage: Decimal,
) -> list[dict[str, Any]]:
    if not orders:
        return []
    budget = max(Decimal("0"), (available - reserve_margin) / OPEN_ORDER_MARGIN_SAFETY)
    if budget <= 0 or ct_val <= 0 or leverage <= 0:
        return [order for order in orders if order.get("reduce_only")]

    selected: list[dict[str, Any]] = []
    used = Decimal("0")
    for order in orders:
        if order.get("reduce_only"):
            selected.append(order)
            continue
        px = dec(order.get("px"), Decimal("0"))
        sz = dec(order.get("sz"), Decimal("0"))
        estimated_margin = px * sz * ct_val / leverage if px > 0 and sz > 0 else Decimal("0")
        if estimated_margin <= 0:
            continue
        if used + estimated_margin > budget:
            continue
        selected.append(order)
        used += estimated_margin
    return selected


def open_pending_by_side(
    orders: list[dict[str, Any]],
    *,
    lower: Decimal,
    upper: Decimal,
    open_sides: set[str],
) -> dict[str, Decimal]:
    totals = {"long": Decimal("0"), "short": Decimal("0")}
    for order in orders:
        if not is_bot_order(order) or is_reduce_only_pending_order(order):
            continue
        pos_side = str(order.get("posSide", ""))
        if pos_side not in totals or pos_side not in open_sides:
            continue
        px = dec(order.get("px"), Decimal("0"))
        sz = dec(order.get("sz"), Decimal("0"))
        if px <= 0 or sz <= 0 or px < lower or px > upper:
            continue
        totals[pos_side] += sz
    return totals


def min_positive(*values: Decimal) -> Decimal:
    positives = [value for value in values if value > 0]
    return min(positives) if positives else Decimal("0")


def clamp_pct(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(value, Decimal("100")))


def effective_range(
    config: BotConfig,
    state: dict[str, Any],
    mark_px: Decimal,
    tick: Decimal,
) -> tuple[Decimal, Decimal, str]:
    if config.mode == "fixed":
        return config.lower, config.upper, "fixed"

    avg_abs_bps = avg_abs_return_bps(state.get("candles", []))
    vol_width_bps = avg_abs_bps * config.adaptive_vol_multiplier
    width_bps = max(config.adaptive_width_bps, vol_width_bps, config.adaptive_min_width_bps)
    width_bps = min(width_bps, config.adaptive_max_width_bps)
    half = width_bps / Decimal("20000")
    raw_lower = round_to_tick(mark_px * (Decimal("1") - half), tick)
    raw_upper = round_to_tick(mark_px * (Decimal("1") + half), tick)
    lower = max(config.lower, raw_lower)
    upper = min(config.upper, raw_upper)

    if upper <= lower:
        return config.lower, config.upper, "adaptive-clipped-to-fixed"
    return lower, upper, f"adaptive width={width_bps:.2f}bps avg1m={avg_abs_bps:.2f}bps"


def avg_abs_return_bps(candles: list[list[str]]) -> Decimal:
    closes = [dec(item[4], Decimal("0")) for item in candles if len(item) > 4 and item[4]]
    values: list[Decimal] = []
    for index in range(len(closes) - 1):
        prev = closes[index + 1]
        if prev:
            values.append(abs((closes[index] / prev - Decimal("1")) * Decimal("10000")))
    if not values:
        return Decimal("0")
    return sum(values) / Decimal(len(values))


def grid_step(config: BotConfig, tick: Decimal, lower: Decimal | None = None, upper: Decimal | None = None) -> Decimal:
    lower = config.lower if lower is None else lower
    upper = config.upper if upper is None else upper
    midpoint = (lower + upper) / Decimal("2")
    target_step = midpoint * config.grid_bps / Decimal("10000")
    grid_count = max(1, int(((upper - lower) / target_step).to_integral_value(rounding=ROUND_HALF_UP)))
    return round_to_tick((upper - lower) / Decimal(grid_count), tick)


def classify_stop(
    mark_px: Decimal,
    lower: Decimal,
    upper: Decimal,
    soft_lower: Decimal,
    soft_upper: Decimal,
    hard_lower: Decimal,
    hard_upper: Decimal,
) -> str:
    if mark_px <= hard_lower:
        return "hard_low"
    if mark_px >= hard_upper:
        return "hard_high"
    if mark_px <= soft_lower:
        return "soft_low"
    if mark_px >= soft_upper:
        return "soft_high"
    if lower <= mark_px <= upper:
        return "inside"
    return "buffer"


def order_key(order: dict[str, str]) -> tuple[str, str, str, str]:
    return (order["side"], order["pos_side"], order["px"], order["sz"])


def order_key_from_pending(order: dict[str, Any]) -> tuple[str, str, str, str]:
    return (order.get("side", ""), order.get("posSide", ""), order.get("px", ""), order.get("sz", ""))


def reconcile_orders(
    pending_orders: list[dict[str, Any]],
    desired_orders: list[dict[str, Any]],
    open_px_tolerance: Decimal,
    *,
    lower: Decimal,
    upper: Decimal,
    open_sides: set[str],
    open_capacity: dict[str, Decimal],
    preserve_valid_open: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    matched_pending: set[int] = set()
    matched_desired: set[int] = set()
    preserved_open_by_side = {"long": Decimal("0"), "short": Decimal("0")}
    preserved_open_count_by_side = {"long": 0, "short": 0}

    for desired_index, desired in enumerate(desired_orders):
        for pending_index, pending in enumerate(pending_orders):
            if pending_index in matched_pending:
                continue
            if pending_matches_desired(pending, desired, open_px_tolerance):
                matched_pending.add(pending_index)
                matched_desired.add(desired_index)
                break

    if preserve_valid_open:
        for pending_index, pending in enumerate(pending_orders):
            if pending_index in matched_pending or is_reduce_only_pending_order(pending):
                continue
            pos_side = str(pending.get("posSide", ""))
            if pos_side not in {"long", "short"} or pos_side not in open_sides:
                continue
            px = dec(pending.get("px"), Decimal("0"))
            sz = dec(pending.get("sz"), Decimal("0"))
            if px <= 0 or sz <= 0 or px < lower or px > upper:
                continue
            if preserved_open_by_side[pos_side] + sz > open_capacity.get(pos_side, Decimal("0")):
                continue
            preserved_open_by_side[pos_side] += sz
            preserved_open_count_by_side[pos_side] += 1
            matched_pending.add(pending_index)

    stale = [order for index, order in enumerate(pending_orders) if index not in matched_pending]
    missing = []
    for index, order in enumerate(desired_orders):
        if index in matched_desired:
            continue
        if not order.get("reduce_only"):
            pos_side = str(order.get("pos_side", ""))
            if preserved_open_count_by_side.get(pos_side, 0) > 0:
                preserved_open_count_by_side[pos_side] -= 1
                continue
        missing.append(order)
    return stale, missing, len(matched_pending)


def pending_matches_desired(
    pending: dict[str, Any],
    desired: dict[str, Any],
    open_px_tolerance: Decimal,
) -> bool:
    if str(pending.get("side", "")) != str(desired.get("side", "")):
        return False
    if str(pending.get("posSide", "")) != str(desired.get("pos_side", "")):
        return False
    pending_reduce = is_reduce_only_pending_order(pending)
    desired_reduce = bool(desired.get("reduce_only"))
    if pending_reduce != desired_reduce:
        return False

    pending_sz = dec(pending.get("sz"), Decimal("0"))
    desired_sz = dec(desired.get("sz"), Decimal("0"))
    if pending_sz != desired_sz:
        return False

    pending_px = dec(pending.get("px"), Decimal("0"))
    desired_px = dec(desired.get("px"), Decimal("0"))
    if pending_reduce:
        return pending_px == desired_px
    return abs(pending_px - desired_px) <= open_px_tolerance


def open_order_price_tolerance(step: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        return Decimal("0")
    if step <= 0:
        return tick
    return max(tick, step * Decimal("0.2"))


def is_bot_order(order: dict[str, Any]) -> bool:
    return str(order.get("clOrdId", "")).startswith(BOT_PREFIX)


def is_reduce_only_pending_order(order: dict[str, Any]) -> bool:
    return str(order.get("reduceOnly", "")).lower() == "true"


def client_order_id(side: str, pos_side: str, price: Decimal, close: bool) -> str:
    normalized = str(price).replace(".", "")
    tag = "c" if close else "o"
    return f"{BOT_PREFIX}{tag}{side[0]}{pos_side[0]}{normalized}"[:32]


def require_live_permission(confirm_live: str) -> None:
    if os.getenv("OKX_ENABLE_LIVE_TRADING", "0") != "1":
        raise SystemExit("Live trading locked: set OKX_ENABLE_LIVE_TRADING=1 in .env first.")
    if confirm_live != "I_UNDERSTAND":
        raise SystemExit("Live trading requires --confirm-live I_UNDERSTAND.")


def install_shutdown_handlers(client: OkxRestClient, config: BotConfig) -> None:
    def handle_signal(signum: int, _frame: Any) -> None:
        signame = signal.Signals(signum).name
        print(f"Received {signame}: shutting down.")
        log_event("shutdown_signal", {"signal": signame, "live": config.live})
        if config.cancel_on_stop:
            try:
                orders = client.get_pending_orders(config.inst_id).get("data", [])
                open_orders = [
                    order
                    for order in orders
                    if is_bot_order(order) and not is_reduce_only_pending_order(order)
                ]
                cancel_all_bot_orders(client, config, open_orders, reason=f"shutdown_{signame.lower()}")
            except Exception as exc:
                log_event("shutdown_cancel_error", {"signal": signame, "error": str(exc)})
                print(f"Shutdown cancel failed: {exc}")
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


def print_banner(config: BotConfig) -> None:
    mode = "LIVE" if config.live else "DRY-RUN"
    print(f"{mode} grid bot for {config.inst_id}")
    print(f"range={config.lower}-{config.upper} leverage={config.leverage}x order_sz={config.order_sz}")
    print(f"runtime_config={RUNTIME_CONFIG_PATH} log_path={LOG_PATH} bot_prefix={BOT_PREFIX}")
    print(
        f"grid_bps={config.grid_bps} min_net_bps={config.min_net_bps} "
        f"interval={config.interval}s ord_type={config.ord_type} "
        f"mode={config.mode} sizing={config.sizing_mode} "
        f"reserve={config.cash_reserve_pct}% "
        f"range_drift={config.range_drift_mode}/{config.range_drift_weight_bps}bps"
    )
    print(
        f"total_profit_tp={config.total_profit_tp} tp_pct={config.total_profit_tp_pct}% tp_cap={config.total_profit_tp_cap} "
        f"min_tp_profit={config.min_tp_profit} min_tp_bps={config.min_tp_bps} "
        f"total_loss_sl={config.total_loss_sl} sl_pct={config.total_loss_sl_pct}% "
        f"sl_cap={config.total_loss_sl_cap} position_loss_sl_bps={config.position_loss_sl_bps}"
    )
    print(
        f"exchange_stop_enabled={config.exchange_stop_enabled} "
        f"exchange_stop_bps={config.exchange_stop_bps} "
        f"trigger_type={config.exchange_stop_trigger_px_type} "
        f"reprice_bps={config.exchange_stop_reprice_bps}"
    )
    print(f"risk_cooldown={config.risk_cooldown}s recenter_on_cooldown={config.recenter_on_cooldown}")
    print(
        f"trend_filter={config.trend_filter} trend_lookback={config.trend_lookback} "
        f"trend_threshold_bps={config.trend_threshold_bps} one_way_open={config.one_way_open}"
    )
    print(
        f"regime_filter={config.regime_filter} bar={config.regime_bar} "
        f"ma={config.regime_short_ma}/{config.regime_long_ma} "
        f"diff_bps={config.regime_diff_bps} confirm_bars={config.regime_confirm_bars}"
    )
    print(
        f"rolling_adaptive={config.rolling_adaptive_enabled} window={config.rolling_adaptive_window} "
        f"lev={config.rolling_adaptive_min_leverage}-{config.rolling_adaptive_max_leverage}x "
        f"grid={config.rolling_adaptive_min_grid_bps}-{config.rolling_adaptive_max_grid_bps}bps "
        f"margin={config.rolling_adaptive_min_order_margin_pct}-{config.rolling_adaptive_max_order_margin_pct}%/"
        f"{config.rolling_adaptive_min_max_margin_pct}-{config.rolling_adaptive_max_max_margin_pct}%"
    )


def print_cycle_header(
    mark_px: Decimal,
    ticker: dict[str, Any],
    step: Decimal,
    stop_state: str,
    state: dict[str, Any],
    lower: Decimal,
    upper: Decimal,
    range_note: str,
) -> None:
    positions = position_summary(state["positions"])
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] mark={mark_px} last={ticker.get('last')} "
        f"range={lower}-{upper} step={step} state={stop_state} "
        f"long={positions['long']} short={positions['short']} {range_note}"
    )


def log_event(kind: str, payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "payload": payload,
    }
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def one(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data", [])
    return data[0] if data else {}


def dec(value: Any, default: Decimal) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def round_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def round_size(value: Decimal, lot: Decimal) -> Decimal:
    return (value / lot).to_integral_value(rounding=ROUND_DOWN) * lot


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def current_ms() -> int:
    return int(time.time() * 1000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OKX dual-side range grid bot. Dry-run by default.")
    parser.add_argument("--inst-id", default="BEAT-USDT-SWAP")
    parser.add_argument("--runtime-config", default=str(RUNTIME_CONFIG_PATH), help="Runtime config JSON path for this bot instance")
    parser.add_argument("--log-path", default=str(LOG_PATH), help="Action log JSONL path for this bot instance")
    parser.add_argument("--bot-prefix", default=BOT_PREFIX, help="Client order id prefix for this bot instance")
    parser.add_argument("--lower", default="1.74")
    parser.add_argument("--upper", default="1.82")
    parser.add_argument("--leverage", default="3")
    parser.add_argument("--grid-bps", default="25")
    parser.add_argument("--min-net-bps", default="5", help="Minimum estimated net bps after open and close fees before placing new open orders")
    parser.add_argument("--soft-bps", default="35")
    parser.add_argument("--hard-bps", default="60")
    parser.add_argument("--order-sz", default="0.1", help="Contracts per order")
    parser.add_argument("--max-position", default="1.0", help="Max contracts per side")
    parser.add_argument("--max-open-orders-per-side", type=int, default=2)
    parser.add_argument("--max-actions-per-cycle", type=int, default=4)
    parser.add_argument("--interval", type=float, default=8)
    parser.add_argument("--ord-type", choices=("post_only", "limit"), default="post_only")
    parser.add_argument("--mode", choices=("fixed", "adaptive"), default="adaptive")
    parser.add_argument("--adaptive-width-bps", default="420")
    parser.add_argument("--adaptive-min-width-bps", default="260")
    parser.add_argument("--adaptive-max-width-bps", default="700")
    parser.add_argument("--adaptive-vol-multiplier", default="12")
    parser.add_argument("--range-drift-mode", choices=("off", "cooldown"), default="cooldown", help="Whether outer lower/upper should drift after cooldown")
    parser.add_argument("--range-drift-weight-bps", default="2500", help="Weighted outer range drift toward mark, in bps of distance; 2500 = 25%")
    parser.add_argument("--range-drift-max-bps", default="250", help="Maximum outer range shift per cooldown, in bps of midpoint; 0 disables cap")
    parser.add_argument("--sizing-mode", choices=("fixed", "margin_pct"), default="fixed")
    parser.add_argument("--order-margin-pct", default="30", help="Percent of available USDT margin per new order")
    parser.add_argument("--max-margin-pct", default="70", help="Percent of equity margin cap per side")
    parser.add_argument("--cash-reserve-pct", default="10", help="Minimum free margin reserve percent of equity before placing new opens")
    parser.add_argument("--total-profit-tp", default="0", help="Estimated total PnL in USDT that triggers full close; 0 disables")
    parser.add_argument("--total-profit-tp-pct", default="0", help="Equity percent profit target; overrides fixed target when >0")
    parser.add_argument("--total-profit-tp-cap", default="0", help="USDT cap for percent profit target; 0 disables cap")
    parser.add_argument("--total-profit-action", choices=("checkpoint", "close"), default="checkpoint", help="checkpoint resets session PnL and keeps grid running; close exits positions then cools down")
    parser.add_argument("--min-tp-profit", default="0", help="Minimum estimated net USDT profit per reduce-only TP order; 0 disables")
    parser.add_argument("--total-loss-sl", default="0", help="Estimated total loss in USDT that triggers full close; 0 disables")
    parser.add_argument("--total-loss-sl-pct", default="0", help="Equity percent hard stop; overrides fixed loss target when >0")
    parser.add_argument("--total-loss-sl-cap", default="0", help="USDT cap for percent hard stop; 0 disables cap")
    parser.add_argument("--position-loss-sl-bps", default="550", help="Per-side position loss ratio in bps that closes that side; 0 disables")
    parser.add_argument("--exchange-stop-enabled", action="store_true", help="Maintain exchange-side reduce-only conditional stop orders")
    parser.add_argument("--exchange-stop-bps", default="650", help="Exchange-side per-position stop distance in levered bps")
    parser.add_argument("--exchange-stop-trigger-px-type", choices=("last", "mark", "index"), default="mark")
    parser.add_argument("--exchange-stop-reprice-bps", default="5", help="Recreate exchange stop when trigger drifts more than this bps")
    parser.add_argument("--min-tp-bps", default="200", help="Minimum take-profit distance from side average price in bps; 0 disables")
    parser.add_argument("--missed-tp-ord-type", choices=("limit", "market"), default="limit")
    parser.add_argument("--missed-tp-slippage-bps", default="20", help="Limit close slippage bps when TP has already been crossed")
    parser.add_argument("--hard-stop-ord-type", choices=("limit", "market"), default="market")
    parser.add_argument("--hard-stop-slippage-bps", default="50", help="Limit close slippage bps for hard stop when not using market")
    parser.add_argument("--risk-cooldown", type=float, default=60, help="Seconds to pause after total TP/SL or price hard stop")
    parser.add_argument("--no-recenter-on-cooldown", dest="recenter_on_cooldown", action="store_false", help="Keep outer range after cooldown")
    parser.set_defaults(recenter_on_cooldown=True)
    parser.add_argument("--trend-filter", choices=("off", "auto"), default="auto")
    parser.add_argument("--trend-lookback", type=int, default=8, help="1m candles to compare for trend filtering")
    parser.add_argument("--trend-threshold-bps", default="70", help="Minimum lookback move in bps to classify up/down trend")
    parser.add_argument("--market-regime-filter", choices=("off", "rules", "rf", "hmm"), default="off", help="Optional ADX/CHOP/ML market regime gate for new opens")
    parser.add_argument("--market-regime-model-path", default="", help="Joblib model path for rf/hmm market regime modes")
    parser.add_argument("--market-regime-min-confidence", default="0.52", help="Minimum model confidence before allowing model-driven opens")
    parser.add_argument("--regime-filter", choices=("off", "ma_cross"), default="off")
    parser.add_argument("--regime-bar", choices=("5m", "15m", "30m", "1H"), default="15m")
    parser.add_argument("--regime-short-ma", type=int, default=5)
    parser.add_argument("--regime-long-ma", type=int, default=20)
    parser.add_argument("--regime-diff-bps", default="50", help="MA gap threshold in bps; 50 = 0.5%")
    parser.add_argument("--regime-confirm-bars", type=int, default=3)
    parser.add_argument("--allow-dual-open", dest="one_way_open", action="store_false", help="Allow both long and short open orders in the same cycle")
    parser.set_defaults(one_way_open=True)
    parser.add_argument("--rolling-adaptive", action="store_true", help="Recalculate leverage, sizing, grid, TP, and SL from rolling candles each cycle")
    parser.add_argument("--rolling-adaptive-window", type=int, default=30, help="1m candles used for rolling adaptive calculations")
    parser.add_argument("--rolling-adaptive-low-vol-bps", default="3")
    parser.add_argument("--rolling-adaptive-high-vol-bps", default="25")
    parser.add_argument("--rolling-adaptive-min-leverage", default="1")
    parser.add_argument("--rolling-adaptive-max-leverage", default="5")
    parser.add_argument("--rolling-adaptive-min-grid-bps", default="18")
    parser.add_argument("--rolling-adaptive-max-grid-bps", default="80")
    parser.add_argument("--rolling-adaptive-grid-vol-multiplier", default="2.4")
    parser.add_argument("--rolling-adaptive-min-width-bps", default="260")
    parser.add_argument("--rolling-adaptive-max-width-bps", default="1200")
    parser.add_argument("--rolling-adaptive-width-vol-multiplier", default="14")
    parser.add_argument("--rolling-adaptive-min-order-margin-pct", default="3")
    parser.add_argument("--rolling-adaptive-max-order-margin-pct", default="10")
    parser.add_argument("--rolling-adaptive-min-max-margin-pct", default="12")
    parser.add_argument("--rolling-adaptive-max-max-margin-pct", default="35")
    parser.add_argument("--rolling-adaptive-min-stop-bps", default="90")
    parser.add_argument("--rolling-adaptive-max-stop-bps", default="900")
    parser.add_argument("--rolling-adaptive-stop-vol-multiplier", default="8")
    parser.add_argument("--rolling-adaptive-min-tp-bps", default="45")
    parser.add_argument("--rolling-adaptive-max-tp-bps", default="180")
    parser.add_argument("--rolling-adaptive-tp-grid-multiplier", default="2.2")
    parser.add_argument("--rolling-adaptive-min-total-profit-tp-pct", default="0.6")
    parser.add_argument("--rolling-adaptive-max-total-profit-tp-pct", default="2.5")
    parser.add_argument("--rolling-adaptive-min-total-loss-sl-pct", default="0.8")
    parser.add_argument("--rolling-adaptive-max-total-loss-sl-pct", default="2.0")
    parser.add_argument("--set-leverage", action="store_true")
    parser.add_argument("--cancel-on-stop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live", default="")
    return parser.parse_args()


if __name__ == "__main__":
    main()
