from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import (
    BAR_MS,
    DATA_DIR,
    Candle,
    fetch_okx_candle_rows,
    parse_okx_candles,
    read_candles_csv,
    write_candles_csv,
)
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "volume_price_bubble"
EPS = 1e-12


@dataclass(frozen=True, slots=True)
class BubbleParams:
    """Parameters for the volume-price exhaustion/reversal indicator.

    Every feature at candle i uses candles through i only.  An event derived
    from candle i is executed at candle i+1 open by the research backtest.
    """

    trend_window: int = 48
    momentum_window: int = 12
    volume_window: int = 24
    zscore_window: int = 48
    atr_window: int = 14
    trigger_window: int = 3
    bubble_lookback: int = 12
    min_score: float = 60.0
    min_extension_atr: float = 1.0
    min_divergence_z: float = 0.5
    min_volume_z: float = 0.5
    min_absorption_z: float = 0.5
    extension_scale_atr: float = 1.5
    divergence_scale: float = 1.5
    volume_scale: float = 1.5
    absorption_scale: float = 1.5
    stop_atr_mult: float = 1.25
    stop_buffer_atr: float = 0.15
    max_stop_atr: float = 4.0
    take_profit_r: float = 1.4
    breakeven_r: float = 0.8
    trail_atr_mult: float = 1.5
    max_hold_bars: int = 48
    cooldown_bars: int = 4


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    starting_equity: float = 100.0
    leverage: float = 3.0
    margin_pct: float = 35.0
    risk_pct: float = 0.75
    max_margin_pct: float = 50.0
    entry_fee_bps: float = 2.0
    exit_fee_bps: float = 5.0
    slippage_bps: float = 2.0
    holding_cost_bps_per_day: float = 0.0
    ct_val: float = 1.0
    lot_sz: float = 0.01
    min_sz: float = 0.01


@dataclass(frozen=True, slots=True)
class BubbleFeature:
    ts: int
    close: float
    atr: float
    price_extension_atr: float
    price_momentum_z: float
    volume_z: float
    pressure_z: float
    pv_divergence_z: float
    result_z: float
    absorption_z: float
    up_bubble_score: float
    down_bubble_score: float
    previous_high: float
    previous_low: float
    bubble_high: float
    bubble_low: float
    short_trigger: bool
    long_trigger: bool


@dataclass(frozen=True, slots=True)
class BubbleSignal:
    as_of: str
    inst_id: str
    bar: str
    side: int
    label: str
    score: float
    price_extension_atr: float
    volume_z: float
    pv_divergence_z: float
    absorption_z: float
    reference_entry: float
    stop: float | None
    take_profit: float | None
    risk_distance: float | None
    explanation: str


@dataclass(slots=True)
class BubblePosition:
    side: int
    qty: float
    entry: float
    stop: float
    take_profit: float
    risk_distance: float
    entry_index: int
    entry_fee: float
    best_price: float


@dataclass(frozen=True, slots=True)
class BubbleTrade:
    entry_time: str
    exit_time: str
    side: int
    qty: float
    entry: float
    exit: float
    reason: str
    gross_pnl: float
    net_pnl: float
    entry_fee: float
    exit_fee: float
    bars_held: int


@dataclass(frozen=True, slots=True)
class BubbleBacktestResult:
    start: str
    end: str
    starting_equity: float
    final_equity: float
    return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    fees: float
    exposure_pct: float
    stop_exits: int
    target_exits: int
    signal_exits: int
    time_exits: int
    end_exits: int


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_log_return(current: float, previous: float) -> float:
    if current <= 0 or previous <= 0:
        return math.nan
    return math.log(current / previous)


def ema(values: list[float], window: int) -> list[float]:
    window = max(1, int(window))
    alpha = 2.0 / (window + 1.0)
    result: list[float] = [math.nan] * len(values)
    previous = math.nan
    for index, value in enumerate(values):
        if not _finite(value):
            result[index] = previous
            continue
        previous = value if not _finite(previous) else alpha * value + (1.0 - alpha) * previous
        result[index] = previous
    return result


def true_range_atr(candles: list[Candle], window: int) -> list[float]:
    if not candles:
        return []
    true_ranges: list[float] = []
    for index, candle in enumerate(candles):
        high = float(candle.high)
        low = float(candle.low)
        if index == 0:
            true_ranges.append(max(0.0, high - low))
            continue
        previous_close = float(candles[index - 1].close)
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return ema(true_ranges, max(1, window))


def _rolling_sample(values: list[float], index: int, window: int) -> list[float]:
    start = max(0, index - max(1, window) + 1)
    return [value for value in values[start : index + 1] if _finite(value)]


def rolling_mean(values: list[float], window: int) -> list[float]:
    result: list[float] = [math.nan] * len(values)
    for index in range(len(values)):
        sample = _rolling_sample(values, index, window)
        result[index] = statistics.fmean(sample) if sample else math.nan
    return result


def robust_zscore(values: list[float], window: int, min_observations: int | None = None) -> list[float]:
    """Rolling median/MAD z-score; robust to volume spikes and listing noise."""

    result: list[float] = [math.nan] * len(values)
    window = max(2, int(window))
    required = min_observations if min_observations is not None else max(10, window // 3)
    for index, value in enumerate(values):
        sample = _rolling_sample(values, index, window)
        if not _finite(value) or len(sample) < min(required, window):
            continue
        median = statistics.median(sample)
        deviations = [abs(item - median) for item in sample]
        mad = statistics.median(deviations)
        scale = 1.4826 * mad
        if scale <= EPS:
            scale = statistics.pstdev(sample)
        if scale > EPS:
            result[index] = (value - median) / scale
        else:
            result[index] = 0.0
    return result


def _rolling_min(values: list[float], start: int, end: int) -> float:
    sample = [value for value in values[max(0, start) : max(0, end)] if _finite(value)]
    return min(sample) if sample else math.nan


def _rolling_max(values: list[float], start: int, end: int) -> float:
    sample = [value for value in values[max(0, start) : max(0, end)] if _finite(value)]
    return max(sample) if sample else math.nan


def _directional_score(
    direction: int,
    extension: float,
    divergence: float,
    volume_z: float,
    absorption: float,
    params: BubbleParams,
) -> float:
    directional_extension = direction * extension
    directional_divergence = direction * divergence
    if not all(_finite(value) for value in (directional_extension, directional_divergence, volume_z, absorption)):
        return 0.0
    extension_component = _clip(
        (directional_extension - params.min_extension_atr) / max(EPS, params.extension_scale_atr)
    )
    divergence_component = _clip(
        (directional_divergence - params.min_divergence_z) / max(EPS, params.divergence_scale)
    )
    volume_component = _clip((volume_z - params.min_volume_z) / max(EPS, params.volume_scale))
    absorption_component = _clip((absorption - params.min_absorption_z) / max(EPS, params.absorption_scale))
    # Price extension and a mismatch are mandatory.  Volume climax/absorption
    # refine the score rather than creating a signal on their own.
    if extension_component <= 0 or (divergence_component <= 0 and absorption_component <= 0):
        return 0.0
    return 100.0 * (
        0.40 * extension_component
        + 0.35 * divergence_component
        + 0.15 * volume_component
        + 0.10 * absorption_component
    )


def compute_bubble_features(candles: list[Candle], params: BubbleParams | None = None) -> list[BubbleFeature]:
    """Compute the indicator with current-bar information only."""

    params = params or BubbleParams()
    if not candles:
        return []
    closes = [float(candle.close) for candle in candles]
    opens = [float(candle.open) for candle in candles]
    highs = [float(candle.high) for candle in candles]
    lows = [float(candle.low) for candle in candles]
    volumes = [max(0.0, float(candle.volume)) for candle in candles]
    atr_values = true_range_atr(candles, params.atr_window)
    slow_ema = ema(closes, max(params.trend_window, params.atr_window) * 2)
    volume_log = [math.log(max(value, EPS)) for value in volumes]
    volume_z = robust_zscore(volume_log, params.volume_window)
    volume_median = rolling_mean(volumes, params.volume_window)
    normalized_volume = [
        volume / max(EPS, median) if _finite(median) else math.nan
        for volume, median in zip(volumes, volume_median)
    ]
    clv_volume: list[float] = []
    body_atr: list[float] = []
    for index, candle in enumerate(candles):
        high = highs[index]
        low = lows[index]
        close = closes[index]
        candle_range = high - low
        clv = (2.0 * close - high - low) / candle_range if candle_range > EPS else 0.0
        clv = _clip(clv, -1.0, 1.0)
        clv_volume.append(clv * normalized_volume[index] if _finite(normalized_volume[index]) else math.nan)
        atr_value = atr_values[index]
        body_atr.append(abs(close - opens[index]) / atr_value if _finite(atr_value) and atr_value > EPS else math.nan)
    pressure = rolling_mean(clv_volume, params.momentum_window)
    price_momentum: list[float] = [math.nan] * len(candles)
    for index in range(len(candles)):
        lookback = max(1, params.momentum_window)
        if index < lookback:
            continue
        atr_value = atr_values[index]
        close = closes[index]
        baseline_move = atr_value * math.sqrt(lookback) if _finite(atr_value) else math.nan
        if close > EPS and _finite(baseline_move) and baseline_move > EPS:
            price_momentum[index] = (closes[index] - closes[index - lookback]) / baseline_move
    price_momentum_z = robust_zscore(price_momentum, params.zscore_window)
    pressure_z = robust_zscore(pressure, params.zscore_window)
    result_z = robust_zscore(body_atr, params.zscore_window)
    absorption_z: list[float] = [math.nan] * len(candles)
    for index in range(len(candles)):
        if _finite(volume_z[index]) and _finite(result_z[index]):
            absorption_z[index] = volume_z[index] - result_z[index]
    features: list[BubbleFeature] = []
    for index, candle in enumerate(candles):
        atr_value = atr_values[index]
        extension = (
            (closes[index] - slow_ema[index]) / atr_value
            if _finite(slow_ema[index]) and _finite(atr_value) and atr_value > EPS
            else math.nan
        )
        divergence = (
            price_momentum_z[index] - pressure_z[index]
            if _finite(price_momentum_z[index]) and _finite(pressure_z[index])
            else math.nan
        )
        up_score = _directional_score(
            1,
            extension,
            divergence,
            volume_z[index],
            absorption_z[index],
            params,
        )
        down_score = _directional_score(
            -1,
            extension,
            divergence,
            volume_z[index],
            absorption_z[index],
            params,
        )
        previous_high = _rolling_max(highs, index - params.trigger_window, index)
        previous_low = _rolling_min(lows, index - params.trigger_window, index)
        bubble_high = _rolling_max(highs, index - params.bubble_lookback + 1, index + 1)
        bubble_low = _rolling_min(lows, index - params.bubble_lookback + 1, index + 1)
        short_trigger = (
            up_score >= params.min_score
            and _finite(previous_low)
            and closes[index] < previous_low
        )
        long_trigger = (
            down_score >= params.min_score
            and _finite(previous_high)
            and closes[index] > previous_high
        )
        features.append(
            BubbleFeature(
                ts=candle.ts,
                close=closes[index],
                atr=atr_value,
                price_extension_atr=extension,
                price_momentum_z=price_momentum_z[index],
                volume_z=volume_z[index],
                pressure_z=pressure_z[index],
                pv_divergence_z=divergence,
                result_z=result_z[index],
                absorption_z=absorption_z[index],
                up_bubble_score=up_score,
                down_bubble_score=down_score,
                previous_high=previous_high,
                previous_low=previous_low,
                bubble_high=bubble_high,
                bubble_low=bubble_low,
                short_trigger=short_trigger,
                long_trigger=long_trigger,
            )
        )
    return features


def bubble_events(candles: list[Candle], params: BubbleParams | None = None) -> list[int]:
    """Return entry events indexed by execution bar; event i uses feature i-1."""

    params = params or BubbleParams()
    features = compute_bubble_features(candles, params)
    events = [0] * len(candles)
    last_event = -10**9
    for execution_index in range(1, len(candles)):
        feature = features[execution_index - 1]
        if execution_index - last_event <= max(0, params.cooldown_bars):
            continue
        if feature.short_trigger and feature.long_trigger:
            if feature.up_bubble_score > feature.down_bubble_score:
                events[execution_index] = -1
            elif feature.down_bubble_score > feature.up_bubble_score:
                events[execution_index] = 1
        elif feature.short_trigger:
            events[execution_index] = -1
        elif feature.long_trigger:
            events[execution_index] = 1
        if events[execution_index]:
            last_event = execution_index
    return events


def _levels_for_signal(side: int, entry: float, feature: BubbleFeature, params: BubbleParams) -> tuple[float, float, float] | None:
    if side not in {-1, 1} or entry <= 0 or not _finite(feature.atr) or feature.atr <= 0:
        return None
    if side < 0:
        extreme_distance = feature.bubble_high - entry if _finite(feature.bubble_high) else 0.0
    else:
        extreme_distance = entry - feature.bubble_low if _finite(feature.bubble_low) else 0.0
    distance = max(
        params.stop_atr_mult * feature.atr,
        extreme_distance + params.stop_buffer_atr * feature.atr,
    )
    if distance <= 0 or distance > params.max_stop_atr * feature.atr:
        return None
    stop = entry + distance if side < 0 else entry - distance
    take_profit = entry - params.take_profit_r * distance if side < 0 else entry + params.take_profit_r * distance
    return stop, take_profit, distance


def latest_bubble_signal(
    candles: list[Candle],
    *,
    inst_id: str,
    bar: str,
    params: BubbleParams | None = None,
) -> BubbleSignal:
    params = params or BubbleParams()
    if not candles:
        raise ValueError("No candles available")
    features = compute_bubble_features(candles, params)
    feature = features[-1]
    side = -1 if feature.short_trigger else 1 if feature.long_trigger else 0
    if feature.short_trigger and feature.long_trigger:
        side = -1 if feature.up_bubble_score >= feature.down_bubble_score else 1
    score = feature.up_bubble_score if side < 0 else feature.down_bubble_score if side > 0 else max(feature.up_bubble_score, feature.down_bubble_score)
    levels = _levels_for_signal(side, feature.close, feature, params) if side else None
    stop, take_profit, distance = levels if levels else (None, None, None)
    if side < 0:
        label = "short_reversal"
        explanation = "上行价格泡沫出现量价失配，且收盘跌破短结构；等待下一根开盘做空。"
    elif side > 0:
        label = "long_reversal"
        explanation = "下行价格泡沫出现量价失配，且收盘突破短结构；等待下一根开盘做多。"
    elif feature.up_bubble_score >= params.min_score:
        label = "upside_bubble_watch"
        explanation = "上行量价失配达到预警，但尚未完成结构破位确认，不追空。"
    elif feature.down_bubble_score >= params.min_score:
        label = "downside_bubble_watch"
        explanation = "下行量价失配达到预警，但尚未完成结构突破确认，不抢多。"
    else:
        label = "neutral"
        explanation = "当前没有达到量价失配与结构确认的组合条件。"
    return BubbleSignal(
        as_of=datetime.fromtimestamp(feature.ts / 1000, timezone.utc).isoformat(timespec="seconds"),
        inst_id=inst_id,
        bar=bar,
        side=side,
        label=label,
        score=score,
        price_extension_atr=feature.price_extension_atr,
        volume_z=feature.volume_z,
        pv_divergence_z=feature.pv_divergence_z,
        absorption_z=feature.absorption_z,
        reference_entry=feature.close,
        stop=stop,
        take_profit=take_profit,
        risk_distance=distance,
        explanation=explanation,
    )


def _execution_price(raw_price: float, side: int, slippage_bps: float, is_entry: bool) -> float:
    slip = max(0.0, slippage_bps) / 10000.0
    if is_entry:
        return raw_price * (1.0 + slip if side > 0 else 1.0 - slip)
    return raw_price * (1.0 - slip if side > 0 else 1.0 + slip)


def _round_down_size(size: float, lot_sz: float, min_sz: float) -> float:
    if size <= 0 or lot_sz <= 0:
        return 0.0
    rounded = math.floor(size / lot_sz + EPS) * lot_sz
    return rounded if rounded + EPS >= min_sz else 0.0


def run_bubble_backtest(
    candles: list[Candle],
    params: BubbleParams | None = None,
    config: BacktestConfig | None = None,
    *,
    start: int = 0,
    end: int | None = None,
) -> tuple[BubbleBacktestResult, list[BubbleTrade], list[dict[str, Any]]]:
    params = params or BubbleParams()
    config = config or BacktestConfig()
    end = len(candles) if end is None else min(len(candles), end)
    start = max(0, min(start, end))
    if end - start < 2:
        raise ValueError("Bubble backtest needs at least two candles")
    features = compute_bubble_features(candles, params)
    events = bubble_events(candles, params)
    entry_fee_rate = max(0.0, config.entry_fee_bps) / 10000.0
    exit_fee_rate = max(0.0, config.exit_fee_bps) / 10000.0
    equity = config.starting_equity
    peak = equity
    max_drawdown = 0.0
    fees = 0.0
    position: BubblePosition | None = None
    trades: list[BubbleTrade] = []
    equity_curve: list[dict[str, Any]] = []
    active_bars = 0
    exit_counts = {"stop": 0, "target": 0, "signal": 0, "time": 0, "end": 0}

    def close_position(index: int, raw_exit: float, reason: str) -> None:
        nonlocal equity, fees, position
        if position is None:
            return
        exit_px = _execution_price(raw_exit, position.side, config.slippage_bps, False)
        gross_pnl = position.side * position.qty * (exit_px - position.entry) * config.ct_val
        exit_fee = abs(position.qty * exit_px * config.ct_val) * exit_fee_rate
        equity += gross_pnl - exit_fee
        fees += exit_fee
        net_pnl = gross_pnl - exit_fee - position.entry_fee
        trades.append(
            BubbleTrade(
                entry_time=datetime.fromtimestamp(candles[position.entry_index].ts / 1000, timezone.utc).isoformat(timespec="seconds"),
                exit_time=datetime.fromtimestamp(candles[index].ts / 1000, timezone.utc).isoformat(timespec="seconds"),
                side=position.side,
                qty=position.qty,
                entry=position.entry,
                exit=exit_px,
                reason=reason,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                entry_fee=position.entry_fee,
                exit_fee=exit_fee,
                bars_held=max(1, index - position.entry_index),
            )
        )
        exit_counts[reason] = exit_counts.get(reason, 0) + 1
        position = None

    for index in range(max(start, 1), end):
        candle = candles[index]
        event = events[index]
        if position is not None:
            if index - position.entry_index >= max(1, params.max_hold_bars):
                close_position(index, float(candle.open), "time")
            elif event and event != position.side:
                close_position(index, float(candle.open), "signal")

        if position is None and event:
            prior_feature = features[index - 1]
            raw_entry = float(candle.open)
            entry = _execution_price(raw_entry, event, config.slippage_bps, True)
            levels = _levels_for_signal(event, entry, prior_feature, params)
            if levels:
                stop, take_profit, risk_distance = levels
                risk_budget = max(0.0, equity) * max(0.0, config.risk_pct) / 100.0
                risk_qty = risk_budget / max(EPS, risk_distance * config.ct_val)
                margin_pct = min(max(0.0, config.margin_pct), max(0.0, config.max_margin_pct))
                notional_cap = max(0.0, equity) * margin_pct / 100.0 * max(0.0, config.leverage)
                margin_qty = notional_cap / max(EPS, entry * config.ct_val)
                qty = _round_down_size(min(risk_qty, margin_qty), config.lot_sz, config.min_sz)
                if qty > 0:
                    entry_fee = abs(qty * entry * config.ct_val) * entry_fee_rate
                    equity -= entry_fee
                    fees += entry_fee
                    position = BubblePosition(
                        side=event,
                        qty=qty,
                        entry=entry,
                        stop=stop,
                        take_profit=take_profit,
                        risk_distance=risk_distance,
                        entry_index=index,
                        entry_fee=entry_fee,
                        best_price=entry,
                    )

        if position is not None:
            # If a candle touches both levels, stop-first is deliberately
            # conservative because OHLC data cannot reveal intrabar order.
            if position.side > 0 and float(candle.low) <= position.stop:
                close_position(index, position.stop, "stop")
            elif position.side < 0 and float(candle.high) >= position.stop:
                close_position(index, position.stop, "stop")
            elif position.side > 0 and float(candle.high) >= position.take_profit:
                close_position(index, position.take_profit, "target")
            elif position.side < 0 and float(candle.low) <= position.take_profit:
                close_position(index, position.take_profit, "target")
            elif position is not None:
                if position.side > 0:
                    position.best_price = max(position.best_price, float(candle.high))
                else:
                    position.best_price = min(position.best_price, float(candle.low))
                current_feature = features[index]
                if _finite(current_feature.atr) and current_feature.atr > 0:
                    close_profit = position.side * (float(candle.close) - position.entry)
                    if close_profit >= params.breakeven_r * position.risk_distance:
                        if position.side > 0:
                            position.stop = max(position.stop, position.entry)
                        else:
                            position.stop = min(position.stop, position.entry)
                    if position.side > 0:
                        position.stop = max(
                            position.stop,
                            position.best_price - params.trail_atr_mult * current_feature.atr,
                        )
                    else:
                        position.stop = min(
                            position.stop,
                            position.best_price + params.trail_atr_mult * current_feature.atr,
                        )
                active_bars += 1

        mark_equity = equity
        if position is not None:
            mark_equity += position.side * position.qty * (float(candle.close) - position.entry) * config.ct_val
        peak = max(peak, mark_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - mark_equity) / peak * 100.0)
        equity_curve.append(
            {
                "ts": candle.ts,
                "time": datetime.fromtimestamp(candle.ts / 1000, timezone.utc).isoformat(timespec="seconds"),
                "equity": mark_equity,
                "cash": equity,
                "side": position.side if position else 0,
                "qty": position.qty if position else 0.0,
                "close": float(candle.close),
            }
        )

    if position is not None:
        close_position(end - 1, float(candles[end - 1].close), "end")
        final_mark = equity
    else:
        final_mark = equity
    gross_profit = sum(max(0.0, trade.net_pnl) for trade in trades)
    gross_loss = abs(sum(min(0.0, trade.net_pnl) for trade in trades))
    profit_factor = gross_profit / gross_loss if gross_loss > EPS else (999.0 if gross_profit > 0 else 0.0)
    wins = sum(1 for trade in trades if trade.net_pnl > 0)
    losses = sum(1 for trade in trades if trade.net_pnl < 0)
    return (
        BubbleBacktestResult(
            start=datetime.fromtimestamp(candles[start].ts / 1000, timezone.utc).isoformat(timespec="seconds"),
            end=datetime.fromtimestamp(candles[end - 1].ts / 1000, timezone.utc).isoformat(timespec="seconds"),
            starting_equity=config.starting_equity,
            final_equity=final_mark,
            return_pct=(final_mark / config.starting_equity - 1.0) * 100.0 if config.starting_equity > 0 else 0.0,
            max_drawdown_pct=max_drawdown,
            profit_factor=profit_factor,
            trades=len(trades),
            wins=wins,
            losses=losses,
            win_rate_pct=wins / len(trades) * 100.0 if trades else 0.0,
            fees=fees,
            exposure_pct=active_bars / max(1, end - max(start, 1)) * 100.0,
            stop_exits=exit_counts["stop"],
            target_exits=exit_counts["target"],
            signal_exits=exit_counts["signal"],
            time_exits=exit_counts["time"],
            end_exits=exit_counts["end"],
        ),
        trades,
        equity_curve,
    )


def candidate_params() -> list[BubbleParams]:
    """Small, interpretable grid; selection belongs inside each train window."""

    base = BubbleParams()
    candidates: list[BubbleParams] = []
    for momentum_window in (8, 12, 20):
        for min_score in (55.0, 65.0):
            for trigger_window in (2, 4):
                candidates.append(
                    replace(
                        base,
                        momentum_window=momentum_window,
                        min_score=min_score,
                        trigger_window=trigger_window,
                        bubble_lookback=max(8, momentum_window),
                    )
                )
    return candidates


def selection_score(result: BubbleBacktestResult) -> float:
    if result.trades < 2:
        return -1e9
    return (
        result.return_pct
        - 0.60 * result.max_drawdown_pct
        + 0.50 * min(result.profit_factor, 3.0)
        + 0.03 * min(result.trades, 30)
    )


def forward_return_diagnostics(
    candles: list[Candle],
    params: BubbleParams | None = None,
    *,
    thresholds: tuple[float, ...] = (50.0, 60.0, 70.0),
    horizons: tuple[int, ...] = (5, 15, 30),
) -> dict[str, Any]:
    """Describe conditional future returns for research only.

    Future candles are used here solely as the evaluation label.  They are
    never read by compute_bubble_features, bubble_events, or the backtest
    when forming a signal.
    """

    params = params or BubbleParams()
    features = compute_bubble_features(candles, params)
    output: dict[str, Any] = {}
    for label, score_attr, trigger_attr, direction in (
        ("up_bubble_short", "up_bubble_score", "short_trigger", -1),
        ("down_bubble_long", "down_bubble_score", "long_trigger", 1),
    ):
        label_output: dict[str, Any] = {}
        for threshold in thresholds:
            indices = [
                index
                for index, feature in enumerate(features)
                if getattr(feature, score_attr) >= threshold
            ]
            horizon_output: dict[str, Any] = {"n": len(indices)}
            for horizon in horizons:
                values = [
                    direction * (float(candles[index + horizon].close) / float(candles[index].close) - 1.0) * 10000.0
                    for index in indices
                    if index + horizon < len(candles) and float(candles[index].close) > 0
                ]
                horizon_output[f"h{horizon}"] = {
                    "n": len(values),
                    "avg_bps": statistics.fmean(values) if values else None,
                    "median_bps": statistics.median(values) if values else None,
                    "win_rate_pct": sum(value > 0 for value in values) / len(values) * 100.0 if values else None,
                }
            label_output[str(threshold)] = horizon_output
        trigger_indices = [index for index, feature in enumerate(features) if getattr(feature, trigger_attr)]
        trigger_values = [
            direction * (float(candles[index + 15].close) / float(candles[index].close) - 1.0) * 10000.0
            for index in trigger_indices
            if index + 15 < len(candles) and float(candles[index].close) > 0
        ]
        label_output["trigger"] = {
            "n": len(trigger_values),
            "avg_h15_bps": statistics.fmean(trigger_values) if trigger_values else None,
            "median_h15_bps": statistics.median(trigger_values) if trigger_values else None,
            "win_rate_pct": sum(value > 0 for value in trigger_values) / len(trigger_values) * 100.0 if trigger_values else None,
        }
        output[label] = label_output
    return output


def run_walk_forward(
    candles: list[Candle],
    config: BacktestConfig,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates = candidate_params()
    window_start = 0
    window_index = 0
    while window_start + train_bars + test_bars <= len(candles):
        train_start = window_start
        train_end = window_start + train_bars
        test_end = train_end + test_bars
        scored: list[tuple[float, BubbleParams, BubbleBacktestResult]] = []
        for params in candidates:
            result, _, _ = run_bubble_backtest(candles, params, config, start=train_start, end=train_end)
            scored.append((selection_score(result), params, result))
        _, selected_params, train_result = max(scored, key=lambda item: item[0])
        test_result, _, _ = run_bubble_backtest(candles, selected_params, config, start=train_end, end=test_end)
        rows.append(
            {
                "window": window_index,
                "trainStart": train_result.start,
                "trainEnd": train_result.end,
                "testStart": test_result.start,
                "testEnd": test_result.end,
                "params": asdict(selected_params),
                "train": asdict(train_result),
                "test": asdict(test_result),
                "trainScore": selection_score(train_result),
                "testScore": selection_score(test_result),
                "testPassed": bool(test_result.return_pct > 0 and test_result.profit_factor >= 1 and test_result.trades >= 2),
            }
        )
        window_index += 1
        window_start += max(1, step_bars)
    return rows


def load_candles(args: argparse.Namespace) -> list[Candle]:
    if args.input_csv:
        return read_candles_csv(Path(args.input_csv))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.pages <= 1 else f"x{args.pages}"
    cache_path = DATA_DIR / f"{args.inst_id}_{args.bar}_{args.limit}{suffix}.csv"
    if cache_path.exists() and not args.refresh:
        return read_candles_csv(cache_path)
    rows = fetch_okx_candle_rows(OkxRestClient(), args.inst_id, args.bar, args.limit, max(1, args.pages))
    candles = parse_okx_candles(rows)
    write_candles_csv(cache_path, candles)
    time.sleep(max(0.0, args.sleep))
    return candles


def resolve_output_dir(value: str) -> Path:
    if not value:
        return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    flat_rows: list[dict[str, Any]] = []
    for row in rows:
        flat_rows.append({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(flat_rows[0]))
        writer.writeheader()
        writer.writerows(flat_rows)


def write_report(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    params: BubbleParams,
    backtest_config: BacktestConfig,
    candles: list[Candle],
    signal: BubbleSignal,
    result: BubbleBacktestResult,
    trades: list[BubbleTrade],
    equity_curve: list[dict[str, Any]],
    walk_forward: list[dict[str, Any]],
    forward_diagnostics: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instrument": args.inst_id,
        "bar": args.bar,
        "bars": len(candles),
        "dataStart": datetime.fromtimestamp(candles[0].ts / 1000, timezone.utc).isoformat(timespec="seconds") if candles else "",
        "dataEnd": datetime.fromtimestamp(candles[-1].ts / 1000, timezone.utc).isoformat(timespec="seconds") if candles else "",
        "method": "volume_price_bubble_reversal",
        "params": asdict(params),
        "backtestConfig": asdict(backtest_config),
        "latestSignal": asdict(signal),
        "backtest": asdict(result),
        "walkForward": walk_forward,
        "forwardReturnDiagnostics": forward_diagnostics,
        "sources": [
            "https://doi.org/10.2307/2330874",
            "https://doi.org/10.1111/j.1540-6261.1994.tb04424.x",
            "https://doi.org/10.1111/iere.12132",
            "https://github.com/mortenmus/Volume-Price-Phase-Shift-VPPS",
            "https://github.com/Boulder-Investment-Technologies/lppls",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest_signal.json").write_text(json.dumps(asdict(signal), ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "trades.csv", [asdict(trade) for trade in trades])
    write_csv(output_dir / "equity_curve.csv", equity_curve)
    write_csv(output_dir / "walk_forward.csv", walk_forward)
    passed = sum(1 for row in walk_forward if row["testPassed"])
    report = "# SKHY volume-price bubble research\n\n"
    report += f"- Instrument: `{args.inst_id}`\n- Bar: `{args.bar}`\n- Candles: `{len(candles)}`\n"
    report += f"- Data: `{payload['dataStart']}` → `{payload['dataEnd']}`\n"
    report += f"- Latest signal: **{signal.label}**, score `{signal.score:.2f}`, side `{signal.side}`\n"
    report += f"- Backtest: return `{result.return_pct:.3f}%`, max DD `{result.max_drawdown_pct:.3f}%`, PF `{result.profit_factor:.3f}`, trades `{result.trades}`\n"
    report += f"- Walk-forward test windows passed: `{passed}/{len(walk_forward)}`\n\n"
    report += "The signal is a research alert. It is not connected to live execution.\n"
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research a volume-price bubble/exhaustion reversal indicator.")
    parser.add_argument("--inst-id", default="SKHY-USDT-SWAP")
    parser.add_argument("--bar", default="1m", choices=list(BAR_MS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=24)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--input-csv", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--train-bars", type=int, default=2400)
    parser.add_argument("--test-bars", type=int, default=600)
    parser.add_argument("--step-bars", type=int, default=600)
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--sleep", type=float, default=0.15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candles = load_candles(args)
    if len(candles) < 100:
        raise SystemExit(f"Not enough candles for volume-price bubble research: {len(candles)}")
    params = BubbleParams()
    backtest_config = BacktestConfig(starting_equity=args.starting_equity)
    signal = latest_bubble_signal(candles, inst_id=args.inst_id, bar=args.bar, params=params)
    result, trades, equity_curve = run_bubble_backtest(candles, params, backtest_config)
    walk_forward = run_walk_forward(
        candles,
        backtest_config,
        train_bars=max(1, args.train_bars),
        test_bars=max(1, args.test_bars),
        step_bars=max(1, args.step_bars),
    )
    forward_diagnostics = forward_return_diagnostics(candles, params)
    output_dir = resolve_output_dir(args.output_dir)
    write_report(
        output_dir,
        args=args,
        params=params,
        backtest_config=backtest_config,
        candles=candles,
        signal=signal,
        result=result,
        trades=trades,
        equity_curve=equity_curve,
        walk_forward=walk_forward,
        forward_diagnostics=forward_diagnostics,
    )
    print(f"volume_price_bubble_report={output_dir}")
    print(json.dumps(asdict(signal), ensure_ascii=False, sort_keys=True))
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
