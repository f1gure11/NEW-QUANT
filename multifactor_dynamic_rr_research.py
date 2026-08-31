"""Read-only multi-factor research with dynamic win-rate and reward/risk entries.

The input is the locally collected OKX public snapshot stream.  Every feature
uses the current snapshot and earlier snapshots only.  Candidate parameters are
chosen on the selection interval and then reported on validation and test
intervals; this module never reads private endpoints or sends orders.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from orderflow_rr_research import (
    DEFAULT_INSTRUMENTS,
    INPUT_ROOT,
    OrderFlowSnapshot,
    load_snapshot_history,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "multifactor_dynamic_rr"
MAX_LOOKBACK = 240
FORECAST_HORIZON = 30
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class DynamicCandidate:
    threshold: float
    target_vol_mult: float
    stop_vol_mult: float
    min_win_rate_pct: float
    min_edge_bps: float
    max_hold_bars: int


@dataclass(slots=True)
class FeatureSeries:
    inst_id: str
    snapshots: list[OrderFlowSnapshot]
    timestamps: np.ndarray
    features: np.ndarray
    feature_names: list[str]
    volatility_bps: np.ndarray
    liquidity_score: np.ndarray
    correlation_score: np.ndarray
    predictions: np.ndarray | None = None
    scores: np.ndarray | None = None


@dataclass(slots=True)
class DynamicTrade:
    entry_ts: int
    exit_ts: int
    side: int
    signal_score: float
    estimated_win_rate_pct: float
    breakeven_win_rate_pct: float
    target_bps: float
    stop_bps: float
    expected_value_bps: float
    entry_price: float
    exit_price: float
    exit_reason: str
    hold_bars: int
    net_pnl_bps: float
    mae_bps: float
    mfe_bps: float


@dataclass(slots=True)
class DynamicResult:
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    average_win_bps: float
    average_loss_bps: float
    payoff_ratio: float
    breakeven_win_rate_pct: float
    win_rate_edge_pct: float
    expectancy_bps: float
    profit_factor: float
    total_return_pct: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    tp_exits: int
    stop_exits: int
    time_exits: int
    gap_exits: int
    average_hold_bars: float
    average_estimated_win_rate_pct: float
    average_target_bps: float
    average_stop_bps: float
    final_equity: float
    trade_rows: list[DynamicTrade]


@dataclass(slots=True)
class FittedModel:
    model: Any
    feature_names: list[str]
    prediction_scale_bps: float
    coefficients: dict[str, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only momentum/liquidity/correlation/technical/Alpha101 dynamic RR research."
    )
    parser.add_argument("--input-root", default=str(INPUT_ROOT))
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--allocation-pct", type=float, default=20.0)
    parser.add_argument("--fee-bps-per-side", type=float, default=5.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=1.0)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    parser.add_argument("--max-gap-seconds", type=float, default=180.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def feature_names() -> list[str]:
    names = [f"momentum_{window}" for window in (5, 10, 30, 60, 120)]
    names += ["momentum_acceleration", "technical_rsi_14", "technical_rsi_60"]
    names += ["technical_ema_trend", "technical_bollinger", "technical_range", "technical_autocorr"]
    names += ["liquidity_depth", "liquidity_volume", "liquidity_spread", "liquidity_score"]
    names += ["correlation_btc_30", "correlation_btc_120", "correlation_x_btc_momentum"]
    names += [f"alpha{alpha}" for alpha in (6, 7, 9, 12, 21, 23, 41, 53, 54, 101)]
    names += ["book_imbalance", "trade_imbalance", "ofi"]
    return names


def prepare_series(
    inst_id: str,
    snapshots: list[OrderFlowSnapshot],
    benchmark: list[OrderFlowSnapshot],
) -> FeatureSeries:
    names = feature_names()
    n = len(snapshots)
    timestamps = np.asarray([row.ts for row in snapshots], dtype=np.int64)
    mids = np.asarray([max(row.mid, EPSILON) for row in snapshots], dtype=float)
    log_mids = np.log(mids)
    one_bar = np.diff(log_mids, prepend=log_mids[0])
    volumes = np.asarray([max(row.volume, EPSILON) for row in snapshots], dtype=float)
    volume_delta = np.diff(volumes, prepend=volumes[0])
    depths = np.asarray(
        [max(row.bid_depth_5 + row.ask_depth_5, EPSILON) for row in snapshots],
        dtype=float,
    )
    spreads = np.asarray([max(row.spread_bps, EPSILON) for row in snapshots], dtype=float)
    ema_fast_values = ewma(log_mids, 12)
    ema_slow_values = ewma(log_mids, 26)
    benchmark_times = np.asarray([row.ts for row in benchmark], dtype=np.int64)
    benchmark_log = np.log(np.asarray([max(row.mid, EPSILON) for row in benchmark], dtype=float))
    benchmark_returns = np.diff(benchmark_log, prepend=benchmark_log[0])
    aligned_benchmark = np.zeros(n, dtype=float)
    for i, ts in enumerate(timestamps):
        benchmark_index = bisect.bisect_right(benchmark_times, int(ts)) - 1
        if benchmark_index >= 0:
            aligned_benchmark[i] = benchmark_returns[benchmark_index]

    values: list[list[float]] = []
    vols: list[float] = []
    liquidities: list[float] = []
    correlations: list[float] = []
    for index in range(MAX_LOOKBACK, n - 1):
        row_returns = one_bar[1 : index + 1]
        volatility = max(float(np.std(row_returns[-30:])) * 10_000.0, 1.0)
        depth_score = _relative_score(depths[index], depths[index - 59 : index + 1])
        volume_score = _relative_score(volumes[index], volumes[index - 59 : index + 1])
        spread_score = -_relative_score(spreads[index], spreads[index - 59 : index + 1])
        liquidity_score = clip(0.45 * depth_score + 0.35 * volume_score + 0.20 * spread_score, -3.0, 3.0)

        asset_returns = row_returns[-120:]
        btc_returns = aligned_benchmark[1 : index + 1][-120:]
        corr30 = rolling_corr(asset_returns[-30:], btc_returns[-30:])
        corr120 = rolling_corr(asset_returns, btc_returns)
        benchmark_momentum = float(np.sum(btc_returns[-30:])) * 10_000.0
        corr_x_momentum = clip(corr30 * math.tanh(benchmark_momentum / 50.0), -1.0, 1.0)

        momentum = [
            clip((log_mids[index] - log_mids[index - window]) * 10_000.0 / volatility, -3.0, 3.0)
            for window in (5, 10, 30, 60, 120)
        ]
        rsi14 = centered_rsi(row_returns[-14:])
        rsi60 = centered_rsi(row_returns[-60:])
        ema_fast = float(ema_fast_values[index])
        ema_slow = float(ema_slow_values[index])
        ema_trend = clip((ema_fast - ema_slow) * 10_000.0 / volatility, -3.0, 3.0)
        window60 = log_mids[index - 60 : index + 1]
        bollinger = clip((log_mids[index] - float(np.mean(window60))) / max(float(np.std(window60)), EPSILON), -3.0, 3.0)
        range120 = log_mids[index - 120 : index + 1]
        technical_range = 0.0 if np.ptp(range120) <= EPSILON else 2.0 * (log_mids[index] - float(np.min(range120))) / float(np.ptp(range120)) - 1.0
        technical_autocorr = rolling_corr(row_returns[-60:-1], row_returns[-60 + 1 :])

        alphas = alpha101_features(log_mids, one_bar, volumes, volume_delta, index, volatility)
        vector = momentum + [
            clip((momentum[0] - momentum[2]), -3.0, 3.0),
            rsi14,
            rsi60,
            ema_trend,
            bollinger,
            technical_range,
            technical_autocorr,
            depth_score,
            volume_score,
            spread_score,
            liquidity_score,
            corr30,
            corr120,
            corr_x_momentum,
            *alphas,
            snapshots[index].book_imbalance,
            snapshots[index].trade_imbalance,
            snapshots[index].ofi,
        ]
        if len(vector) != len(names) or not all(math.isfinite(value) for value in vector):
            continue
        values.append(vector)
        vols.append(volatility)
        liquidities.append(liquidity_score)
        correlations.append(corr_x_momentum)
    return FeatureSeries(
        inst_id,
        snapshots,
        timestamps,
        np.asarray(values, dtype=float),
        names,
        np.asarray(vols, dtype=float),
        np.asarray(liquidities, dtype=float),
        np.asarray(correlations, dtype=float),
    )


def fit_model(series: dict[str, FeatureSeries], train_end: int, horizon: int = FORECAST_HORIZON) -> FittedModel:
    feature_rows: list[np.ndarray] = []
    targets: list[float] = []
    for prepared in series.values():
        for row_index, matrix_row in enumerate(prepared.features):
            timestamp = int(prepared.timestamps[MAX_LOOKBACK + row_index])
            if timestamp > train_end:
                break
            future_index = MAX_LOOKBACK + row_index + horizon
            if future_index >= len(prepared.snapshots) or int(prepared.timestamps[future_index]) > train_end:
                continue
            current = max(prepared.snapshots[MAX_LOOKBACK + row_index].mid, EPSILON)
            future = max(prepared.snapshots[future_index].mid, EPSILON)
            feature_rows.append(matrix_row)
            targets.append(math.log(future / current) * 10_000.0)
    if len(feature_rows) < 100:
        raise ValueError(f"not enough model training rows: {len(feature_rows)}")
    matrix = np.asarray(feature_rows, dtype=float)
    target = np.asarray(targets, dtype=float)
    model = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
    model.fit(matrix, target)
    prediction = model.predict(matrix)
    scale = max(float(np.std(prediction)), float(np.std(target)), 10.0)
    ridge = model.named_steps["ridge"]
    coefficient_total = max(float(np.sum(np.abs(ridge.coef_))), EPSILON)
    coefficients = {
        name: float(coef / coefficient_total)
        for name, coef in zip(prepared_names(series), ridge.coef_)
    }
    for prepared in series.values():
        prepared.predictions = model.predict(prepared.features)
        prepared.scores = np.tanh(prepared.predictions / scale)
    return FittedModel(model, prepared_names(series), scale, coefficients)


def prepared_names(series: dict[str, FeatureSeries]) -> list[str]:
    for prepared in series.values():
        return prepared.feature_names
    return feature_names()


def training_posterior(
    series: dict[str, FeatureSeries],
    train_end: int,
    horizon: int = FORECAST_HORIZON,
) -> dict[tuple[int, int], list[int]]:
    """Use only labels ending inside model training to seed the online Beta prior."""
    counts: dict[tuple[int, int], list[int]] = {}
    for prepared in series.values():
        if prepared.scores is None:
            continue
        for feature_position, score in enumerate(prepared.scores):
            current_index = MAX_LOOKBACK + feature_position
            future_index = current_index + horizon
            if future_index >= len(prepared.snapshots):
                break
            if int(prepared.timestamps[future_index]) > train_end:
                break
            side = 1 if score > 0 else -1
            bucket = 1 if abs(float(score)) >= 0.55 else 0
            counts.setdefault((side, bucket), [0, 0])[0 if side * math.log(
                max(prepared.snapshots[future_index].mid, EPSILON)
                / max(prepared.snapshots[current_index].mid, EPSILON)
            ) * 10_000.0 > 0 else 1] += 1
    effective: dict[tuple[int, int], list[int]] = {}
    for key, (wins, losses) in counts.items():
        total = wins + losses
        if total <= 0:
            continue
        effective_total = min(20, total)
        effective_wins = int(round(effective_total * wins / total))
        effective[key] = [effective_wins, effective_total - effective_wins]
    return effective


def dynamic_levels(volatility_bps: float, score: float, win_rate_pct: float, candidate: DynamicCandidate) -> tuple[float, float]:
    confidence = min(1.0, abs(score))
    posterior = max(0.0, min(1.0, win_rate_pct / 100.0))
    horizon_volatility = max(volatility_bps, 1.0) * math.sqrt(max(candidate.max_hold_bars, 1))
    target = horizon_volatility * candidate.target_vol_mult * (1.70 + 1.20 * confidence + 0.35 * (posterior - 0.5))
    stop = horizon_volatility * candidate.stop_vol_mult * (0.90 + 0.25 * (1.0 - confidence) + 0.20 * (1.0 - posterior))
    return max(45.0, min(300.0, target)), max(18.0, min(200.0, stop))


def simulate_dynamic_rr(
    prepared: FeatureSeries,
    candidate: DynamicCandidate,
    start_ts: int,
    end_ts: int,
    *,
    starting_equity: float = 100_000.0,
    allocation_pct: float = 20.0,
    fee_bps_per_side: float = 5.0,
    slippage_bps_per_side: float = 1.0,
    max_spread_bps: float = 1.0,
    max_gap_ms: int = 180_000,
    latency_bars: int = 0,
    record_trades: bool = False,
    prior_posterior: dict[tuple[int, int], list[int]] | None = None,
) -> DynamicResult:
    if prepared.scores is None:
        raise ValueError("series must be scored before simulation")
    row_indices = [
        pos for pos in range(len(prepared.features))
        if start_ts <= int(prepared.timestamps[MAX_LOOKBACK + pos]) <= end_ts
    ]
    if len(row_indices) < 2:
        return empty_dynamic_result(starting_equity)
    fee_rate = fee_bps_per_side / 10_000.0
    slip_rate = slippage_bps_per_side / 10_000.0
    cash_equity = starting_equity
    peak_equity = starting_equity
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    trades: list[DynamicTrade] = []
    posterior: dict[tuple[int, int], list[int]] = {
        key: list(value) for key, value in (prior_posterior or {}).items()
    }
    cooldown_until = -1

    def posterior_probability(side: int, bucket: int) -> float:
        wins, losses = posterior.get((side, bucket), [0, 0])
        total_wins = sum(item[0] for item in posterior.values())
        total_losses = sum(item[1] for item in posterior.values())
        # A small pooled Beta prior prevents a new regime from taking a zero-trade bet.
        return (2.0 + wins + 0.25 * total_wins) / (4.0 + wins + losses + 0.25 * (total_wins + total_losses))

    def mark_equity(snapshot: OrderFlowSnapshot) -> float:
        if position is None:
            return cash_equity
        raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
        exit_price = raw_exit * (1.0 - slip_rate * position["side"])
        gross = position["side"] * (exit_price - position["entry_price"]) * position["units"]
        return cash_equity + gross - exit_price * position["units"] * fee_rate

    def close_position(snapshot_index: int, reason: str) -> None:
        nonlocal position, cash_equity, cooldown_until
        if position is None:
            return
        snapshot = prepared.snapshots[snapshot_index]
        raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
        exit_price = raw_exit * (1.0 - slip_rate * position["side"])
        gross = position["side"] * (exit_price - position["entry_price"]) * position["units"]
        exit_fee = exit_price * position["units"] * fee_rate
        cash_equity += gross - exit_fee
        net_pnl = gross - exit_fee - position["entry_fee"]
        net_bps = net_pnl / position["notional"] * 10_000.0
        key = (position["side"], position["bucket"])
        counts = posterior.setdefault(key, [0, 0])
        counts[0 if net_pnl > 0 else 1] += 1
        trades.append(
            DynamicTrade(
                entry_ts=position["entry_ts"],
                exit_ts=snapshot.ts,
                side=position["side"],
                signal_score=position["signal_score"],
                estimated_win_rate_pct=position["win_rate_pct"],
                breakeven_win_rate_pct=position["breakeven_pct"],
                target_bps=position["target_bps"],
                stop_bps=position["stop_bps"],
                expected_value_bps=position["expected_value_bps"],
                entry_price=position["entry_price"],
                exit_price=exit_price,
                exit_reason=reason,
                hold_bars=snapshot_index - position["entry_index"],
                net_pnl_bps=net_bps,
                mae_bps=position["mae_bps"],
                mfe_bps=position["mfe_bps"],
            )
        )
        position = None
        cooldown_until = snapshot_index + 1

    for local_index, feature_position in enumerate(row_indices):
        snapshot_index = MAX_LOOKBACK + feature_position
        snapshot = prepared.snapshots[snapshot_index]
        previous_index = MAX_LOOKBACK + row_indices[local_index - 1] if local_index > 0 else snapshot_index
        previous_gap = snapshot.ts - prepared.snapshots[previous_index].ts if local_index > 0 else 0
        if position is not None:
            raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
            gross_move_bps = position["side"] * (raw_exit / position["entry_price"] - 1.0) * 10_000.0
            position["mae_bps"] = min(position["mae_bps"], gross_move_bps)
            position["mfe_bps"] = max(position["mfe_bps"], gross_move_bps)
            reason = ""
            if snapshot_index > position["entry_index"] and previous_gap > max_gap_ms:
                reason = "gap"
            elif gross_move_bps >= position["target_bps"]:
                reason = "take_profit"
            elif gross_move_bps <= -position["stop_bps"]:
                reason = "stop_loss"
            elif snapshot_index - position["entry_index"] >= candidate.max_hold_bars:
                reason = "time_exit"
            if reason:
                close_position(snapshot_index, reason)

        equity = mark_equity(snapshot)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100.0)
        if position is not None or local_index >= len(row_indices) - 1 or snapshot_index < cooldown_until:
            continue
        signal_position = max(0, feature_position - latency_bars)
        if signal_position >= len(prepared.scores):
            continue
        signal_score = float(prepared.scores[signal_position])
        if abs(signal_score) < candidate.threshold:
            continue
        if snapshot.spread_bps > max_spread_bps or previous_gap > max_gap_ms:
            continue
        side = 1 if signal_score > 0 else -1
        bucket = 1 if abs(signal_score) >= 0.55 else 0
        win_rate = posterior_probability(side, bucket)
        target, stop = dynamic_levels(float(prepared.volatility_bps[feature_position]), signal_score, win_rate * 100.0, candidate)
        roundtrip_cost = 2.0 * (fee_bps_per_side + slippage_bps_per_side) + max(snapshot.spread_bps, 0.0)
        breakeven = (stop + roundtrip_cost) / max(target + stop, EPSILON) * 100.0
        expected_value = (win_rate * target) - ((1.0 - win_rate) * stop) - roundtrip_cost
        if win_rate * 100.0 < max(candidate.min_win_rate_pct, breakeven + candidate.min_edge_bps):
            continue
        if expected_value < candidate.min_edge_bps:
            continue
        entry_price = snapshot.ask * (1.0 + slip_rate) if side > 0 else snapshot.bid * (1.0 - slip_rate)
        notional = cash_equity * allocation_pct / 100.0
        if entry_price <= 0 or notional <= 0:
            continue
        entry_fee = notional * fee_rate
        cash_equity -= entry_fee
        position = {
            "side": side,
            "bucket": bucket,
            "entry_index": snapshot_index,
            "entry_ts": snapshot.ts,
            "entry_price": entry_price,
            "notional": notional,
            "units": notional / entry_price,
            "entry_fee": entry_fee,
            "signal_score": signal_score,
            "win_rate_pct": win_rate * 100.0,
            "breakeven_pct": breakeven,
            "target_bps": target,
            "stop_bps": stop,
            "expected_value_bps": expected_value,
            "mae_bps": 0.0,
            "mfe_bps": 0.0,
        }
    if position is not None:
        close_position(MAX_LOOKBACK + row_indices[-1], "time_exit")
    return summarize_dynamic(trades, starting_equity, cash_equity, max_drawdown, record_trades)


def summarize_dynamic(
    trades: list[DynamicTrade],
    starting_equity: float,
    final_equity: float,
    max_drawdown_pct: float,
    record_trades: bool,
) -> DynamicResult:
    wins = [trade.net_pnl_bps for trade in trades if trade.net_pnl_bps > 0]
    losses = [trade.net_pnl_bps for trade in trades if trade.net_pnl_bps <= 0]
    avg_win = statistics.fmean(wins) if wins else 0.0
    avg_loss = abs(statistics.fmean(losses)) if losses else 0.0
    payoff = avg_win / avg_loss if avg_loss > EPSILON else (999.0 if avg_win > 0 else 0.0)
    breakeven = 100.0 / (1.0 + payoff) if payoff > 0 else 100.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > EPSILON else (999.0 if gross_profit > 0 else 0.0)
    consecutive = max_consecutive = 0
    for trade in trades:
        consecutive = 0 if trade.net_pnl_bps > 0 else consecutive + 1
        max_consecutive = max(max_consecutive, consecutive)
    return DynamicResult(
        len(trades), len(wins), len(losses), len(wins) / len(trades) * 100.0 if trades else 0.0,
        avg_win, avg_loss, payoff, breakeven,
        (len(wins) / len(trades) * 100.0 - breakeven) if trades else 0.0,
        statistics.fmean(trade.net_pnl_bps for trade in trades) if trades else 0.0,
        profit_factor, (final_equity / starting_equity - 1.0) * 100.0,
        max_drawdown_pct, max_consecutive,
        sum(trade.exit_reason == "take_profit" for trade in trades),
        sum(trade.exit_reason == "stop_loss" for trade in trades),
        sum(trade.exit_reason == "time_exit" for trade in trades),
        sum(trade.exit_reason == "gap" for trade in trades),
        statistics.fmean(trade.hold_bars for trade in trades) if trades else 0.0,
        statistics.fmean(trade.estimated_win_rate_pct for trade in trades) if trades else 0.0,
        statistics.fmean(trade.target_bps for trade in trades) if trades else 0.0,
        statistics.fmean(trade.stop_bps for trade in trades) if trades else 0.0,
        final_equity, trades if record_trades else [],
    )


def empty_dynamic_result(starting_equity: float) -> DynamicResult:
    return DynamicResult(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, starting_equity, [])


def alpha101_features(
    log_mids: np.ndarray,
    one_bar: np.ndarray,
    volumes: np.ndarray,
    volume_delta: np.ndarray,
    index: int,
    volatility_bps: float,
) -> list[float]:
    close = float(math.exp(log_mids[index]))
    open_price = float(math.exp(log_mids[index - 1]))
    window5 = np.exp(log_mids[index - 4 : index + 1])
    high = float(np.max(window5))
    low = float(np.min(window5))
    delta = one_bar[1 : index + 1]
    safe_vol = max(volatility_bps, 1.0)
    alpha6 = -rolling_corr(log_mids[index - 9 : index + 1], volumes[index - 9 : index + 1])
    delta7 = (log_mids[index] - log_mids[index - 7]) * 10_000.0
    ranks = _rank_abs_delta(delta, 60)
    adv20 = float(np.mean(volumes[index - 19 : index + 1]))
    alpha7 = -ranks * (1.0 if delta7 > 0 else -1.0) if volumes[index] >= adv20 else -1.0
    delta1 = delta[-1] if len(delta) else 0.0
    recent_delta = delta[-5:] if len(delta) >= 5 else delta
    alpha9 = delta1 if (len(recent_delta) and (np.min(recent_delta) > 0 or np.max(recent_delta) < 0)) else -delta1
    alpha12 = math.copysign(abs(delta1) * safe_vol, volume_delta[index]) * -1.0
    ma2 = float(np.mean(np.exp(log_mids[index - 1 : index + 1])))
    ma8 = float(np.mean(np.exp(log_mids[index - 7 : index + 1])))
    std8 = float(np.std(np.exp(log_mids[index - 7 : index + 1])))
    alpha21 = -1.0 if ma8 + std8 < ma2 else 1.0 if ma2 < ma8 - std8 else 1.0 if volumes[index] >= adv20 else -1.0
    alpha23 = -(math.exp(log_mids[index]) - math.exp(log_mids[index - 2])) if float(np.mean(np.exp(log_mids[index - 19 : index + 1]))) < high else 0.0
    typical = (high + low + close) / 3.0
    alpha41 = (high * low) ** 0.5 - typical
    denominator = max(close - low, EPSILON)
    position = ((close - low) - (high - close)) / denominator
    old_index = max(0, index - 9)
    old_close = float(math.exp(log_mids[old_index]))
    old_high = float(np.max(np.exp(log_mids[max(0, old_index - 4) : old_index + 1])))
    old_low = float(np.min(np.exp(log_mids[max(0, old_index - 4) : old_index + 1])))
    old_position = ((old_close - old_low) - (old_high - old_close)) / max(old_close - old_low, EPSILON)
    alpha53 = -(position - old_position)
    alpha54 = -((low - close) * (open_price**5)) / ((low - high) * (close**5) + EPSILON)
    alpha101 = (close - open_price) / max(high - low + 0.001, EPSILON)
    raw = [alpha6, alpha7, alpha9 * safe_vol, alpha12, alpha21, alpha23 / max(close, EPSILON), alpha41 / max(close, EPSILON), alpha53, alpha54, alpha101]
    return [clip(value, -3.0, 3.0) for value in raw]


def fit_and_score(series: dict[str, FeatureSeries], train_end: int) -> FittedModel:
    return fit_model(series, train_end)


def run_research(args: argparse.Namespace) -> dict[str, Any]:
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    histories = load_snapshot_history(Path(args.input_root), instruments)
    missing = [inst for inst in instruments if len(histories.get(inst, [])) < MAX_LOOKBACK + FORECAST_HORIZON + 50]
    if missing:
        raise SystemExit(f"Insufficient snapshots for {missing}")
    common_start = max(histories[inst][0].ts for inst in instruments)
    common_end = min(histories[inst][-1].ts for inst in instruments)
    span = common_end - common_start
    train_end = common_start + int(span * 0.50)
    selection_end = common_start + int(span * 0.65)
    validation_end = common_start + int(span * 0.80)
    boundaries = {
        "train": (common_start, train_end),
        "selection": (train_end + 1, selection_end),
        "validation": (selection_end + 1, validation_end),
        "test": (validation_end + 1, common_end),
        "full": (common_start, common_end),
    }
    benchmark = histories.get("BTC-USDT-SWAP", histories[instruments[0]])
    prepared = {inst: prepare_series(inst, histories[inst], benchmark) for inst in instruments}
    model = fit_and_score(prepared, train_end)
    prior_posterior = training_posterior(prepared, train_end)
    execution = dict(
        starting_equity=args.starting_equity,
        allocation_pct=args.allocation_pct,
        fee_bps_per_side=args.fee_bps_per_side,
        slippage_bps_per_side=args.slippage_bps_per_side,
        max_spread_bps=args.max_spread_bps,
        max_gap_ms=int(args.max_gap_seconds * 1000),
    )
    candidates = candidate_grid()
    scores: list[dict[str, Any]] = []
    for candidate in candidates:
        results = [
            simulate_dynamic_rr(
                prepared[inst], candidate, *boundaries["selection"],
                **execution, prior_posterior=prior_posterior,
            )
            for inst in instruments
        ]
        if not results or min(result.trades for result in results) < 5:
            continue
        expectancies = [result.expectancy_bps for result in results]
        positive = sum(value > 0 for value in expectancies)
        scores.append({
            "params": asdict(candidate),
            "score": statistics.median(expectancies) + 0.5 * min(expectancies) - 0.20 * statistics.median(result.max_drawdown_pct for result in results) + positive - len(results) / 2.0,
            "median_expectancy_bps": statistics.median(expectancies),
            "worst_expectancy_bps": min(expectancies),
            "median_return_pct": statistics.median(result.total_return_pct for result in results),
            "median_profit_factor": statistics.median(result.profit_factor for result in results),
            "median_win_rate_pct": statistics.median(result.win_rate_pct for result in results),
            "median_payoff_ratio": statistics.median(result.payoff_ratio for result in results),
            "median_drawdown_pct": statistics.median(result.max_drawdown_pct for result in results),
            "median_trades": statistics.median(result.trades for result in results),
            "positive_instruments": positive,
            "instruments": len(results),
        })
    if not scores:
        raise SystemExit("No dynamic RR candidate generated enough selection trades")
    scores.sort(key=lambda item: item["score"], reverse=True)
    selected = DynamicCandidate(**scores[0]["params"])
    rows: list[dict[str, Any]] = []
    test_trades: list[dict[str, Any]] = []
    for inst in instruments:
        for segment, (start_ts, end_ts) in boundaries.items():
            result = simulate_dynamic_rr(
                prepared[inst], selected, start_ts, end_ts, **execution,
                record_trades=segment == "test",
                prior_posterior=prior_posterior if segment != "train" else None,
            )
            row = result_row(inst, segment, "selected", selected, result)
            rows.append(row)
            if segment == "test":
                test_trades.extend(dynamic_trade_payload(inst, trade) for trade in result.trade_rows)
                stress = simulate_dynamic_rr(
                    prepared[inst], selected, start_ts, end_ts,
                    **{**execution, "fee_bps_per_side": 8.0, "slippage_bps_per_side": 2.0},
                    prior_posterior=prior_posterior,
                )
                rows.append(result_row(inst, segment, "cost_stress", selected, stress))
                latency = simulate_dynamic_rr(
                    prepared[inst], selected, start_ts, end_ts, **execution,
                    latency_bars=1, prior_posterior=prior_posterior,
                )
                rows.append(result_row(inst, segment, "one_snapshot_latency", selected, latency))
    aggregates = aggregate_rows(rows)
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "selected")]
    test = lookup[("test", "selected")]
    decision = {
        "status": "research_only",
        "quantitativePassOnReusedHistory": bool(validation["median_expectancy_bps"] > 0 and test["positive"] == test["count"] and lookup[("test", "cost_stress")]["positive"] == test["count"] and test["worst_drawdown_pct"] <= 3.0),
        "requiresFreshForwardData": True,
        "liveAuthorized": False,
        "rule": "验证期望为正，测试每个标的和成本压力均盈利，且最差回撤不超过3%；否则仅研究。",
    }
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_pooled_multifactor_dynamic_win_rate_reward_risk",
        "instruments": list(instruments),
        "dataDefinition": {"source": "locally collected OKX public REST snapshots", "sampling": "approximately 65 seconds", "limitation": "not a lossless websocket event stream; no live authorization"},
        "strategyDefinition": {"factors": ["momentum", "liquidity", "BTC correlation", "technical indicators", "Alpha101"], "alphaInput": "five-snapshot midpoint microbars and public-trade notional volume; not native exchange OHLCV candles", "model": "StandardScaler + Ridge on future mid-price return", "entry": "signal threshold plus online Beta win-rate and expected-value gate", "exits": "volatility-scaled dynamic target/stop or maximum hold", "execution": "executable bid/ask, taker fees and adverse slippage"},
        "period": {"start": iso_time(common_start), "trainEnd": iso_time(train_end), "selectionEnd": iso_time(selection_end), "validationEnd": iso_time(validation_end), "end": iso_time(common_end)},
        "sampleCounts": {inst: len(value.snapshots) for inst, value in prepared.items()},
        "selectedParameters": asdict(selected),
        "selectedFeatureWeights": model.coefficients,
        "predictionScaleBps": model.prediction_scale_bps,
        "candidateScores": scores[:100],
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
        "trades": test_trades,
    }


def candidate_grid() -> Iterable[DynamicCandidate]:
    for threshold in (0.15, 0.25, 0.35):
        for target_mult in (1.0, 1.5, 2.0):
            for stop_mult in (0.6, 0.9):
                for min_win in (45.0, 50.0):
                    for min_edge in (0.0, 2.0):
                        for max_hold in (30, 60):
                            yield DynamicCandidate(threshold, target_mult, stop_mult, min_win, min_edge, max_hold)


def result_row(inst_id: str, segment: str, variant: str, candidate: DynamicCandidate, result: DynamicResult) -> dict[str, Any]:
    return {"inst_id": inst_id, "segment": segment, "variant": variant, **asdict(candidate), **{key: value for key, value in asdict(result).items() if key != "trade_rows"}}


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["segment"], row["variant"]), []).append(row)
    result: list[dict[str, Any]] = []
    for (segment, variant), items in grouped.items():
        result.append({
            "segment": segment,
            "variant": variant,
            "positive": sum(float(item["expectancy_bps"]) > 0 for item in items),
            "count": len(items),
            "median_return_pct": statistics.median(float(item["total_return_pct"]) for item in items),
            "median_expectancy_bps": statistics.median(float(item["expectancy_bps"]) for item in items),
            "median_win_rate_pct": statistics.median(float(item["win_rate_pct"]) for item in items),
            "median_payoff_ratio": statistics.median(float(item["payoff_ratio"]) for item in items),
            "median_profit_factor": statistics.median(float(item["profit_factor"]) for item in items),
            "worst_drawdown_pct": max(float(item["max_drawdown_pct"]) for item in items),
            "total_trades": sum(int(item["trades"]) for item in items),
        })
    return sorted(result, key=lambda item: (item["segment"], item["variant"]))


def dynamic_trade_payload(inst_id: str, trade: DynamicTrade) -> dict[str, Any]:
    return {"inst_id": inst_id, **asdict(trade)}


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    lookup = {(item["segment"], item["variant"]): item for item in payload["aggregates"]}
    lines = [
        "# 多因子动态胜率—盈亏比入场回测",
        "",
        "> 只读探索性研究；没有读取账户、启动服务或发送订单。",
        "",
        "## 方法",
        "",
        "- 因子：多周期动量、深度/成交量/价差流动性、与 BTC 的滚动相关性、RSI/EMA/Bollinger/波动率技术指标，以及 Alpha6/7/9/12/21/23/41/53/54/101。",
        "- REST 快照没有原生 OHLCV；Alpha101 使用连续5个中间价构造微型 bar，volume 使用公开成交名义额，因此不是标准日频 Alpha101。",
        "- 前50%历史拟合 Ridge，随后15%只用于选择阈值、动态目标/止损和最长持有，最后35%分验证与复用测试。",
        "- 每次入场的胜率是此前已平仓样本的 Beta 后验；盈亏平衡胜率包含双边手续费、滑点和当前价差，只有期望值达到门槛才入场。",
        "- 目标和止损按当前30快照实现波动率、信号置信度和后验胜率动态缩放。",
        "",
        "## 选中的参数",
        "",
        f"- 信号阈值 {selected['threshold']:.2f}，目标波动率倍数 {selected['target_vol_mult']:.2f}，止损波动率倍数 {selected['stop_vol_mult']:.2f}，最低胜率 {selected['min_win_rate_pct']:.1f}%，最低期望 {selected['min_edge_bps']:.1f} bps，最长 {selected['max_hold_bars']} 快照。",
        "",
        "## 跨区间结果",
        "",
        "| 区间 | 正期望 | 中位收益 | 中位胜率 | 中位盈亏比 | 中位PF | 最差回撤 | 交易 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for segment, label in (("train", "训练"), ("selection", "选择"), ("validation", "验证"), ("test", "复用测试"), ("full", "完整")):
        item = lookup.get((segment, "selected"))
        if item:
            lines.append(f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | {item['median_win_rate_pct']:.2f}% | {item['median_payoff_ratio']:.3f} | {item['median_profit_factor']:.3f} | {item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |")
    lines += ["", "## 复用测试压力", "", "| 版本 | 正期望 | 中位收益 | 中位期望 | 中位PF | 最差回撤 | 交易 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for variant, label in (("selected", "选中模型"), ("cost_stress", "成本压力"), ("one_snapshot_latency", "一快照延迟")):
        item = lookup.get(("test", variant))
        if item:
            lines.append(f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | {item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | {item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |")
    lines += ["", "## 复用测试逐标的", "", "| 标的 | 交易 | 收益 | 胜率 | 盈亏比 | 盈亏平衡胜率 | 胜率优势 | 期望 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in payload["rows"]:
        if row["segment"] == "test" and row["variant"] == "selected":
            lines.append(f"| {row['inst_id']} | {row['trades']} | {row['total_return_pct']:.4f}% | {row['win_rate_pct']:.2f}% | {row['payoff_ratio']:.3f} | {row['breakeven_win_rate_pct']:.2f}% | {row['win_rate_edge_pct']:.2f} pct | {row['expectancy_bps']:.3f} bps |")
    ranked = sorted(payload["selectedFeatureWeights"].items(), key=lambda item: abs(float(item[1])), reverse=True)
    lines += ["", "## 主要模型权重", "", "| 因子 | 标准化系数 |", "| --- | ---: |"]
    lines += [f"| `{name}` | {value:+.5f} |" for name, value in ranked[:15]]
    decision = payload["decision"]
    lines += ["", "## 判定", "", "- **仅研究**。", f"- 复用历史量化准入：`{str(decision['quantitativePassOnReusedHistory']).lower()}`。", f"- {decision['rule']}", "- REST 快照不是逐笔 WebSocket，下一步仍需新鲜前向数据和纸面仿真。"]
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _relative_score(value: float, history: np.ndarray) -> float:
    median = float(np.median(history)) if len(history) else value
    mad = float(np.median(np.abs(history - median))) if len(history) else 0.0
    return clip((value - median) / max(1.4826 * mad, abs(median) * 0.05, EPSILON), -3.0, 3.0)


def rolling_corr(left: np.ndarray, right: np.ndarray) -> float:
    length = min(len(left), len(right))
    if length < 3:
        return 0.0
    left, right = left[-length:], right[-length:]
    if float(np.std(left)) <= EPSILON or float(np.std(right)) <= EPSILON:
        return 0.0
    result = float(np.corrcoef(left, right)[0, 1])
    return result if math.isfinite(result) else 0.0


def centered_rsi(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    gains = float(np.mean(np.maximum(values, 0.0)))
    losses = float(np.mean(np.maximum(-values, 0.0)))
    return (gains - losses) / max(gains + losses, EPSILON)


def ewma(values: np.ndarray, span: int) -> np.ndarray:
    if len(values) == 0:
        return np.asarray([], dtype=float)
    alpha = 2.0 / (span + 1.0)
    result = np.empty(len(values), dtype=float)
    result[0] = values[0]
    for index in range(1, len(values)):
        result[index] = alpha * values[index] + (1.0 - alpha) * result[index - 1]
    return result


def _rank_abs_delta(values: np.ndarray, window: int) -> float:
    if len(values) == 0:
        return 0.0
    sample = np.abs(values[-window:])
    return float(np.mean(sample <= sample[-1])) if len(sample) else 0.0


def clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def iso_time(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    args = parse_args()
    payload = run_research(args)
    path = output_dir(args.output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(path / "rows.csv", payload["rows"])
    write_csv(path / "trades.csv", payload["trades"])
    (path / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={path}")
    print(f"selected={payload['selectedParameters']}")
    lookup = {(item["segment"], item["variant"]): item for item in payload["aggregates"]}
    for segment in ("train", "selection", "validation", "test", "full"):
        item = lookup.get((segment, "selected"))
        if item:
            print(f"segment={segment} median_return={item['median_return_pct']:.6f}% median_expectancy={item['median_expectancy_bps']:.4f}bps median_pf={item['median_profit_factor']:.4f}")
    print(f"decision={payload['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
