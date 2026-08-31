from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
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
from market_selector import MarketSelectorConfig, select_candidates
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "strategy_search"
ROW_FIELDS = [
    "rank",
    "inst_id",
    "strategy",
    "family",
    "params",
    "bars",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
    "train_return_pct",
    "train_profit_factor",
    "train_max_drawdown_pct",
    "train_trades",
    "train_exposure_pct",
    "test_return_pct",
    "test_profit_factor",
    "test_max_drawdown_pct",
    "test_trades",
    "test_exposure_pct",
    "test_win_rate_pct",
    "test_fees",
    "test_positive_folds",
    "test_folds",
    "test_worst_fold_return_pct",
    "test_median_fold_return_pct",
    "train_score",
    "holdout_score",
    "score",
    "passed",
]


@dataclass(slots=True)
class StrategySpec:
    name: str
    family: str
    params: dict[str, Any]


@dataclass(slots=True)
class SegmentResult:
    start: str
    end: str
    return_pct: float
    profit_factor: float
    max_drawdown_pct: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    fees: float
    exposure_pct: float = 0.0


@dataclass(slots=True)
class SearchResult:
    inst_id: str
    strategy: str
    family: str
    params: dict[str, Any]
    bars: int
    train: SegmentResult
    test: SegmentResult
    test_folds: list[SegmentResult]
    train_score: float
    holdout_score: float
    score: float
    passed: bool


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inst_ids = resolve_instruments(args)
    candles_by_inst = load_candles_for_instruments(args, inst_ids)
    specs = strategy_grid()
    tasks = [
        (inst_id, candles_to_tuples(candles), spec, args)
        for inst_id, candles in candles_by_inst.items()
        if len(candles) >= args.min_bars
        for spec in specs
    ]
    results = run_parallel(tasks, args.workers)
    results.sort(key=lambda item: item.score, reverse=True)
    write_outputs(output_dir, results, args, inst_ids)
    print(f"strategy_search_report={output_dir}")
    print_summary(results)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only multi-strategy OKX futures search with train/test split.")
    parser.add_argument("--inst-id", action="append", default=[], help="Instrument to test. Can be repeated. Defaults to public top-N.")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-quote-volume", default="5000000")
    parser.add_argument("--max-spread-bps", default="20")
    parser.add_argument("--bar", default="1m", choices=list(BAR_MS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=6)
    parser.add_argument("--refresh", action="store_true", help="Fetch fresh public candles instead of using data/backtest cache.")
    parser.add_argument("--train-ratio", type=float, default=0.6)
    parser.add_argument("--test-folds", type=int, default=3, help="Chronological holdout sub-folds used as an overfit sanity check.")
    parser.add_argument("--min-bars", type=int, default=300)
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--leverage", type=float, default=3.0)
    parser.add_argument("--margin-pct", type=float, default=35.0)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--cost-stress-multiplier", type=float, default=1.0, help="Multiplier applied to fee and slippage assumptions.")
    parser.add_argument("--holding-cost-bps-per-day", type=float, default=0.0, help="Conservative carrying/funding cost charged while in position.")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--sleep", type=float, default=0.15)
    return parser.parse_args()


def resolve_instruments(args: argparse.Namespace) -> list[str]:
    if args.inst_id:
        return list(dict.fromkeys(args.inst_id))
    client = OkxRestClient()
    candidates = select_candidates(
        client,
        MarketSelectorConfig(
            min_quote_volume=dec(args.min_quote_volume),
            max_spread_bps=dec(args.max_spread_bps),
            top_n=args.top_n,
        ),
    )
    return [candidate.inst_id for candidate in candidates]


def load_candles_for_instruments(args: argparse.Namespace, inst_ids: list[str]) -> dict[str, list[Candle]]:
    client = OkxRestClient()
    result: dict[str, list[Candle]] = {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.pages <= 1 else f"x{args.pages}"
    for inst_id in inst_ids:
        cache_path = DATA_DIR / f"{inst_id}_{args.bar}_{args.limit}{suffix}.csv"
        if cache_path.exists() and not args.refresh:
            candles = read_candles_csv(cache_path)
        else:
            rows = fetch_okx_candle_rows(client, inst_id, args.bar, args.limit, max(1, args.pages))
            candles = parse_okx_candles(rows)
            write_candles_csv(cache_path, candles)
            time.sleep(max(0.0, args.sleep))
        result[inst_id] = candles
    return result


def strategy_grid() -> list[StrategySpec]:
    specs: list[StrategySpec] = []
    # Moskowitz, Ooi & Pedersen (2012): sign of an asset's own lagged return.
    # Intraday horizons are selected only through chronological walk-forward;
    # threshold_sigma normalizes the entry/flip threshold by realized volatility.
    for lookback in (12, 24, 48, 96):
        for threshold_sigma in (0.0, 0.25):
            specs.append(
                StrategySpec(
                    "time_series_momentum",
                    "trend",
                    {
                        "lookback": lookback,
                        "vol_window": 48,
                        "threshold_sigma": threshold_sigma,
                        "target_daily_vol_bps": 300,
                        "vol_window_bars": 48,
                    },
                )
            )
    # Multi-horizon voting follows the diversified trend-forecast practice
    # documented by Hurst, Ooi & Pedersen (2017). It reduces dependence on one
    # hand-picked horizon while remaining fully lagged and live-executable.
    for base_lookback in (6, 12, 24):
        for threshold_sigma in (0.0, 0.1):
            specs.append(
                StrategySpec(
                    "multi_horizon_momentum",
                    "trend",
                    {
                        "lookbacks": [base_lookback, base_lookback * 2, base_lookback * 4, base_lookback * 8],
                        "vol_window": 48,
                        "threshold_sigma": threshold_sigma,
                        "min_votes": 2,
                        "target_daily_vol_bps": 300,
                        "vol_window_bars": 48,
                    },
                )
            )
    for fast in (8, 12, 21):
        for slow in (34, 55, 89):
            if fast < slow:
                for band_bps in (0, 5):
                    specs.append(StrategySpec("ema_cross", "trend", {"fast": fast, "slow": slow, "band_bps": band_bps}))
    for fast, slow in ((21, 34), (21, 89)):
        for atr_mult in (0.25, 0.4):
            for persist in (1, 2):
                specs.append(
                    StrategySpec(
                        "ema_cross_atr_band",
                        "trend",
                        {"fast": fast, "slow": slow, "atr_window": 14, "atr_mult": atr_mult, "persist": persist},
                    )
                )
    for fast, slow, signal in ((12, 26, 9), (8, 21, 5), (19, 39, 9)):
        specs.append(StrategySpec("macd_signal", "trend", {"fast": fast, "slow": slow, "signal": signal}))
    for lookback in (20, 40, 80):
        specs.append(StrategySpec("donchian_breakout", "breakout", {"lookback": lookback}))
    for window in (20, 40):
        for z in (1.8, 2.2):
            specs.append(StrategySpec("bollinger_revert", "mean_reversion", {"window": window, "z": z}))
    for window in (14, 21):
        for low, high in ((25, 75), (30, 70)):
            specs.append(StrategySpec("rsi_revert", "mean_reversion", {"window": window, "low": low, "high": high}))
    for window in (20, 40):
        for atr_mult in (1.5, 2.5):
            specs.append(
                StrategySpec(
                    "atr_vol_breakout",
                    "breakout",
                    {"window": window, "atr_window": 14, "atr_mult": atr_mult, "stop_loss_atr_mult": 2.0, "time_stop_bars": window * 2},
                )
            )
    for lookback in (20, 40):
        for vol_window in (20, 40):
            specs.append(
                StrategySpec(
                    "volatility_squeeze_breakout",
                    "breakout",
                    {
                        "lookback": lookback,
                        "vol_window": vol_window,
                        "max_avg_abs_bps": 18,
                        "stop_loss_atr_mult": 2.0,
                        "time_stop_bars": max(36, lookback * 2),
                    },
                )
            )
    for ema_window in (55, 89):
        for low, high in ((35, 65), (40, 60)):
            specs.append(
                StrategySpec(
                    "trend_pullback",
                    "trend",
                    {
                        "ema_window": ema_window,
                        "rsi_window": 14,
                        "low": low,
                        "high": high,
                        "stop_loss_atr_mult": 2.5,
                        "time_stop_bars": 72,
                    },
                )
            )
    for ema_window in (55, 89):
        for low, high in ((40, 60), (45, 55)):
            specs.append(
                StrategySpec(
                    "rsi_trend",
                    "trend",
                    {
                        "ema_window": ema_window,
                        "rsi_window": 14,
                        "low": low,
                        "high": high,
                        "stop_loss_atr_mult": 2.0,
                        "time_stop_bars": 72,
                    },
                )
            )
    for ema_window in (34, 55):
        for atr_mult in (1.5, 2.0):
            specs.append(
                StrategySpec(
                    "keltner_breakout",
                    "breakout",
                    {
                        "ema_window": ema_window,
                        "atr_window": 14,
                        "atr_mult": atr_mult,
                        "stop_loss_atr_mult": 2.0,
                        "time_stop_bars": 72,
                    },
                )
            )
    return specs


def run_parallel(tasks: list[tuple[str, list[tuple[int, float, float, float, float]], StrategySpec, argparse.Namespace]], workers: int) -> list[SearchResult]:
    if not tasks:
        return []
    max_workers = workers if workers > 0 else min(8, max(1, len(tasks)))
    results: list[SearchResult] = []
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(evaluate_task, task) for task in tasks]
        for future in as_completed(futures):
            item = future.result()
            if item:
                results.append(item)
    return results


def evaluate_task(task: tuple[str, list[tuple[int, float, float, float, float]], StrategySpec, argparse.Namespace]) -> SearchResult | None:
    inst_id, raw_candles, spec, args = task
    candles = tuples_to_candles(raw_candles)
    if len(candles) < args.min_bars:
        return None
    split = max(60, min(len(candles) - 60, int(len(candles) * args.train_ratio)))
    targets = strategy_targets(candles, spec)
    train = simulate_segment(candles, targets, 1, split, args, spec.params)
    test = simulate_segment(candles, targets, split, len(candles), args, spec.params)
    test_folds = simulate_test_folds(candles, targets, split, len(candles), int(args.test_folds), args, spec.params)
    train_score = train_selection_score(train)
    holdout_score = holdout_validation_score(test, test_folds)
    positive_folds = sum(1 for fold in test_folds if fold.return_pct > 0 and fold.profit_factor >= 1.0)
    min_positive_folds = math.ceil(len(test_folds) * 2 / 3) if test_folds else 1
    worst_fold_return = min((fold.return_pct for fold in test_folds), default=test.return_pct)
    passed = (
        train.return_pct > 0
        and train.profit_factor >= 1.05
        and train.trades >= 6
        and test.return_pct > 0
        and test.profit_factor >= 1.05
        and test.trades >= 6
        and positive_folds >= min_positive_folds
        and worst_fold_return > -2.0
        and test.max_drawdown_pct <= max(3.0, abs(test.return_pct) * 3.0)
    )
    return SearchResult(
        inst_id,
        spec.name,
        spec.family,
        spec.params,
        len(candles),
        train,
        test,
        test_folds,
        train_score,
        holdout_score,
        combined_search_score(train_score, holdout_score),
        passed,
    )


def combined_search_score(train_score: float, holdout_score: float) -> float:
    return 0.35 * train_score + 0.65 * holdout_score


def strategy_targets(candles: list[Candle], spec: StrategySpec) -> list[int]:
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    if spec.name == "time_series_momentum":
        return time_series_momentum_targets(
            closes,
            int(spec.params["lookback"]),
            int(spec.params.get("vol_window", 48)),
            float(spec.params.get("threshold_sigma", 0.0)),
        )
    if spec.name == "multi_horizon_momentum":
        return multi_horizon_momentum_targets(
            closes,
            [int(value) for value in spec.params["lookbacks"]],
            int(spec.params.get("vol_window", 48)),
            float(spec.params.get("threshold_sigma", 0.0)),
            int(spec.params.get("min_votes", 2)),
        )
    if spec.name == "ema_cross":
        fast = ema(closes, int(spec.params["fast"]))
        slow = ema(closes, int(spec.params["slow"]))
        band = float(spec.params.get("band_bps", 0.0)) / 10000.0
        return cross_targets(fast, slow, band)
    if spec.name == "ema_cross_atr_band":
        return ema_cross_atr_band_targets(
            closes,
            highs,
            lows,
            int(spec.params["fast"]),
            int(spec.params["slow"]),
            int(spec.params.get("atr_window", 14)),
            float(spec.params.get("atr_mult", 0.25)),
            int(spec.params.get("persist", 1)),
        )
    if spec.name == "macd_signal":
        line = [a - b for a, b in zip(ema(closes, int(spec.params["fast"])), ema(closes, int(spec.params["slow"])))]
        sig = ema(line, int(spec.params["signal"]))
        return cross_targets(line, sig, 0.0)
    if spec.name == "donchian_breakout":
        return donchian_targets(closes, highs, lows, int(spec.params["lookback"]))
    if spec.name == "bollinger_revert":
        return bollinger_targets(closes, int(spec.params["window"]), float(spec.params["z"]))
    if spec.name == "rsi_revert":
        return rsi_targets(closes, int(spec.params["window"]), float(spec.params["low"]), float(spec.params["high"]))
    if spec.name == "atr_vol_breakout":
        return atr_breakout_targets(closes, highs, lows, int(spec.params["window"]), int(spec.params["atr_window"]), float(spec.params["atr_mult"]))
    if spec.name == "volatility_squeeze_breakout":
        return volatility_squeeze_breakout_targets(
            closes,
            highs,
            lows,
            int(spec.params["lookback"]),
            int(spec.params["vol_window"]),
            float(spec.params["max_avg_abs_bps"]),
        )
    if spec.name == "trend_pullback":
        return trend_pullback_targets(
            closes,
            int(spec.params["ema_window"]),
            int(spec.params["rsi_window"]),
            float(spec.params["low"]),
            float(spec.params["high"]),
        )
    if spec.name == "rsi_trend":
        return rsi_trend_targets(
            closes,
            int(spec.params["ema_window"]),
            int(spec.params["rsi_window"]),
            float(spec.params["low"]),
            float(spec.params["high"]),
        )
    if spec.name == "keltner_breakout":
        return keltner_breakout_targets(
            closes,
            highs,
            lows,
            int(spec.params["ema_window"]),
            int(spec.params["atr_window"]),
            float(spec.params["atr_mult"]),
        )
    return [0] * len(candles)


def time_series_momentum_targets(
    closes: list[float],
    lookback: int,
    vol_window: int,
    threshold_sigma: float,
) -> list[int]:
    """Lagged own-return sign with a volatility-normalized flip threshold.

    Target for bar i uses closes through i-1 only. Once established, the trend
    state is retained through the noise band instead of going flat, increasing
    market participation without manufacturing a new signal every bar.
    """
    targets = [0] * len(closes)
    state = 0
    lookback = max(1, lookback)
    vol_window = max(2, vol_window)
    threshold_sigma = max(0.0, threshold_sigma)
    one_bar_returns = [math.nan]
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        one_bar_returns.append(closes[index] / previous - 1.0 if previous > 0 else math.nan)
    warmup = max(lookback, vol_window) + 1
    for index in range(warmup, len(closes)):
        start = closes[index - 1 - lookback]
        end = closes[index - 1]
        if start <= 0 or end <= 0:
            targets[index] = state
            continue
        momentum = end / start - 1.0
        sample = [
            value
            for value in one_bar_returns[max(1, index - 1 - vol_window + 1) : index]
            if math.isfinite(value)
        ]
        realized = statistics.pstdev(sample) if len(sample) >= 2 else 0.0
        threshold = threshold_sigma * realized * math.sqrt(lookback)
        if momentum > threshold:
            state = 1
        elif momentum < -threshold:
            state = -1
        targets[index] = state
    return targets


def multi_horizon_momentum_targets(
    closes: list[float],
    lookbacks: list[int],
    vol_window: int,
    threshold_sigma: float,
    min_votes: int,
) -> list[int]:
    """Combine several lagged own-return directions into one persistent side."""
    normalized_lookbacks = sorted({max(1, int(value)) for value in lookbacks})
    targets = [0] * len(closes)
    if not normalized_lookbacks:
        return targets
    state = 0
    vol_window = max(2, vol_window)
    min_votes = max(1, min(len(normalized_lookbacks), min_votes))
    one_bar_returns = [math.nan]
    for index in range(1, len(closes)):
        previous = closes[index - 1]
        one_bar_returns.append(closes[index] / previous - 1.0 if previous > 0 else math.nan)
    warmup = max(max(normalized_lookbacks), vol_window) + 1
    for index in range(warmup, len(closes)):
        sample = [
            value
            for value in one_bar_returns[max(1, index - 1 - vol_window + 1) : index]
            if math.isfinite(value)
        ]
        realized = statistics.pstdev(sample) if len(sample) >= 2 else 0.0
        votes = 0
        for lookback in normalized_lookbacks:
            start = closes[index - 1 - lookback]
            end = closes[index - 1]
            if start <= 0 or end <= 0:
                continue
            momentum = end / start - 1.0
            threshold = max(0.0, threshold_sigma) * realized * math.sqrt(lookback)
            if momentum > threshold:
                votes += 1
            elif momentum < -threshold:
                votes -= 1
        if votes >= min_votes:
            state = 1
        elif votes <= -min_votes:
            state = -1
        targets[index] = state
    return targets


def cross_targets(left: list[float], right: list[float], band: float) -> list[int]:
    targets = [0] * len(left)
    state = 0
    for i in range(1, len(left)):
        a = left[i - 1]
        b = right[i - 1]
        if not math.isfinite(a) or not math.isfinite(b) or b == 0:
            targets[i] = state
            continue
        if a > b * (1.0 + band):
            state = 1
        elif a < b * (1.0 - band):
            state = -1
        targets[i] = state
    return targets


def ema_cross_atr_band_targets(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    fast_window: int,
    slow_window: int,
    atr_window: int,
    atr_mult: float,
    persist: int,
) -> list[int]:
    fast = ema(closes, fast_window)
    slow = ema(closes, slow_window)
    atr_values = atr(highs, lows, closes, atr_window)
    targets = [0] * len(closes)
    state = 0
    streak_side = 0
    streak = 0
    persist = max(1, persist)
    for i in range(1, len(closes)):
        a = fast[i - 1]
        b = slow[i - 1]
        close_prev = closes[i - 1]
        if not math.isfinite(a) or not math.isfinite(b) or b == 0 or close_prev <= 0:
            targets[i] = state
            continue
        atr_prev = atr_values[i - 1] if i - 1 < len(atr_values) else math.nan
        band = atr_mult * atr_prev / close_prev if math.isfinite(atr_prev) and atr_prev > 0 else 0.0
        if a > b * (1.0 + band):
            raw = 1
        elif a < b * (1.0 - band):
            raw = -1
        else:
            raw = 0
        if raw != 0 and raw != state:
            streak = streak + 1 if raw == streak_side else 1
            streak_side = raw
            if streak >= persist:
                state = raw
                streak = 0
                streak_side = 0
        else:
            streak = 0
            streak_side = 0
        targets[i] = state
    return targets


def donchian_targets(closes: list[float], highs: list[float], lows: list[float], lookback: int) -> list[int]:
    targets = [0] * len(closes)
    state = 0
    for i in range(lookback + 1, len(closes)):
        prev_close = closes[i - 1]
        high = max(highs[i - 1 - lookback : i - 1])
        low = min(lows[i - 1 - lookback : i - 1])
        if prev_close > high:
            state = 1
        elif prev_close < low:
            state = -1
        targets[i] = state
    return targets


def bollinger_targets(closes: list[float], window: int, z: float) -> list[int]:
    targets = [0] * len(closes)
    state = 0
    for i in range(window + 1, len(closes)):
        prev = closes[i - 1]
        sample = closes[i - 1 - window : i - 1]
        mean = statistics.fmean(sample)
        std = statistics.pstdev(sample)
        if std <= 0:
            targets[i] = state
            continue
        upper = mean + z * std
        lower = mean - z * std
        if state == 1 and prev >= mean:
            state = 0
        elif state == -1 and prev <= mean:
            state = 0
        elif prev < lower:
            state = 1
        elif prev > upper:
            state = -1
        targets[i] = state
    return targets


def rsi_targets(closes: list[float], window: int, low: float, high: float) -> list[int]:
    values = rsi(closes, window)
    targets = [0] * len(closes)
    state = 0
    for i in range(window + 2, len(closes)):
        value = values[i - 1]
        if not math.isfinite(value):
            targets[i] = state
            continue
        if state == 1 and value >= 50:
            state = 0
        elif state == -1 and value <= 50:
            state = 0
        elif value <= low:
            state = 1
        elif value >= high:
            state = -1
        targets[i] = state
    return targets


def atr_breakout_targets(closes: list[float], highs: list[float], lows: list[float], window: int, atr_window: int, atr_mult: float) -> list[int]:
    values = atr(highs, lows, closes, atr_window)
    targets = [0] * len(closes)
    state = 0
    start = max(window, atr_window) + 1
    for i in range(start, len(closes)):
        prev = closes[i - 1]
        sample = closes[i - 1 - window : i - 1]
        mid = statistics.fmean(sample)
        threshold = values[i - 1] * atr_mult
        if prev > mid + threshold:
            state = 1
        elif prev < mid - threshold:
            state = -1
        targets[i] = state
    return targets


def volatility_squeeze_breakout_targets(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    lookback: int,
    vol_window: int,
    max_avg_abs_bps: float,
) -> list[int]:
    targets = [0] * len(closes)
    state = 0
    start = max(lookback, vol_window) + 2
    for i in range(start, len(closes)):
        prev = closes[i - 1]
        channel_high = max(highs[i - 1 - lookback : i - 1])
        channel_low = min(lows[i - 1 - lookback : i - 1])
        ret_start = max(1, i - vol_window)
        abs_returns = [
            abs(closes[j] / closes[j - 1] - 1.0) * 10000.0
            for j in range(ret_start, i)
            if closes[j - 1] > 0
        ]
        compressed = bool(abs_returns) and statistics.fmean(abs_returns) <= max_avg_abs_bps
        mid = (channel_high + channel_low) / 2.0
        if state == 1 and prev < mid:
            state = 0
        elif state == -1 and prev > mid:
            state = 0
        elif compressed and prev > channel_high:
            state = 1
        elif compressed and prev < channel_low:
            state = -1
        targets[i] = state
    return targets


def trend_pullback_targets(closes: list[float], ema_window: int, rsi_window: int, low: float, high: float) -> list[int]:
    trend = ema(closes, ema_window)
    values = rsi(closes, rsi_window)
    targets = [0] * len(closes)
    state = 0
    start = max(ema_window, rsi_window) + 2
    for i in range(start, len(closes)):
        prev = closes[i - 1]
        trend_now = trend[i - 1]
        trend_prev = trend[i - 2]
        value = values[i - 1]
        if not all(math.isfinite(item) for item in (trend_now, trend_prev, value)):
            targets[i] = state
            continue
        trend_up = prev > trend_now and trend_now >= trend_prev
        trend_down = prev < trend_now and trend_now <= trend_prev
        if state == 1 and (not trend_up or value >= 55):
            state = 0
        elif state == -1 and (not trend_down or value <= 45):
            state = 0
        elif trend_up and value <= low:
            state = 1
        elif trend_down and value >= high:
            state = -1
        targets[i] = state
    return targets


def rsi_trend_targets(closes: list[float], ema_window: int, rsi_window: int, low: float, high: float) -> list[int]:
    trend = ema(closes, ema_window)
    values = rsi(closes, rsi_window)
    targets = [0] * len(closes)
    state = 0
    start = max(ema_window, rsi_window) + 2
    for i in range(start, len(closes)):
        prev = closes[i - 1]
        trend_now = trend[i - 1]
        value = values[i - 1]
        if not math.isfinite(trend_now) or not math.isfinite(value):
            targets[i] = state
            continue
        if state == 1 and (prev < trend_now or value < 50):
            state = 0
        elif state == -1 and (prev > trend_now or value > 50):
            state = 0
        elif prev > trend_now and value >= high:
            state = 1
        elif prev < trend_now and value <= low:
            state = -1
        targets[i] = state
    return targets


def keltner_breakout_targets(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    ema_window: int,
    atr_window: int,
    atr_mult: float,
) -> list[int]:
    midline = ema(closes, ema_window)
    values = atr(highs, lows, closes, atr_window)
    targets = [0] * len(closes)
    state = 0
    start = max(ema_window, atr_window) + 2
    for i in range(start, len(closes)):
        prev = closes[i - 1]
        mid = midline[i - 1]
        width = values[i - 1] * atr_mult
        if not math.isfinite(mid) or not math.isfinite(width) or width <= 0:
            targets[i] = state
            continue
        if state == 1 and prev < mid:
            state = 0
        elif state == -1 and prev > mid:
            state = 0
        elif prev > mid + width:
            state = 1
        elif prev < mid - width:
            state = -1
        targets[i] = state
    return targets


def simulate_segment(
    candles: list[Candle],
    targets: list[int],
    start: int,
    end: int,
    args: argparse.Namespace,
    strategy_params: dict[str, Any] | None = None,
) -> SegmentResult:
    cash = float(args.starting_equity)
    peak = cash
    max_dd = 0.0
    side = 0
    qty = 0.0
    entry = 0.0
    entry_index = 0
    trade_pnls: list[float] = []
    fees = 0.0
    wins = 0
    losses = 0
    active_bars = 0
    cost_stress = max(0.0, float(getattr(args, "cost_stress_multiplier", 1.0)))
    fee_rate = float(args.fee_bps) * cost_stress / 10000.0
    slip = float(args.slippage_bps) * cost_stress / 10000.0
    holding_cost_rate = max(0.0, float(getattr(args, "holding_cost_bps_per_day", 0.0))) / 10000.0
    atr_values = strategy_atr_values(candles, strategy_params)

    for i in range(max(1, start), end):
        desired = targets[i]
        open_px = candles[i].open
        if side and strategy_risk_exit(candles, atr_values, i, side, entry, i - entry_index, strategy_params):
            desired = 0
        if desired != side:
            if side:
                fill = open_px * (1.0 - slip if side > 0 else 1.0 + slip)
                pnl = side * qty * (fill - entry)
                fee = abs(qty * fill) * fee_rate
                cash += pnl - fee
                fees += fee
                trade_pnls.append(pnl - fee)
                if pnl - fee > 0:
                    wins += 1
                elif pnl - fee < 0:
                    losses += 1
            side = desired
            qty = 0.0
            entry = 0.0
            if side and cash > 0:
                fill = open_px * (1.0 + slip if side > 0 else 1.0 - slip)
                vol_scale = simulator_volatility_scale(candles, i, strategy_params)
                notional = cash * float(args.margin_pct) / 100.0 * float(args.leverage) * vol_scale
                qty = notional / fill if fill > 0 else 0.0
                fee = abs(notional) * fee_rate
                cash -= fee
                fees += fee
                entry = fill
                entry_index = i
        if side:
            active_bars += 1
        close = candles[i].close
        if side and holding_cost_rate > 0 and i > 0:
            elapsed_ms = max(0, candles[i].ts - candles[i - 1].ts)
            days = elapsed_ms / 86_400_000.0
            holding_cost = abs(qty * close) * holding_cost_rate * days
            cash -= holding_cost
            fees += holding_cost
        equity = cash + (side * qty * (close - entry) if side else 0.0)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)

    if side and end > start:
        close_px = candles[end - 1].close
        fill = close_px * (1.0 - slip if side > 0 else 1.0 + slip)
        pnl = side * qty * (fill - entry)
        fee = abs(qty * fill) * fee_rate
        cash += pnl - fee
        fees += fee
        trade_pnls.append(pnl - fee)
        if pnl - fee > 0:
            wins += 1
        elif pnl - fee < 0:
            losses += 1

    gross_profit = sum(value for value in trade_pnls if value > 0)
    gross_loss = abs(sum(value for value in trade_pnls if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (0.0 if gross_profit <= 0 else 999.0)
    trades = len(trade_pnls)
    win_rate = wins / trades * 100.0 if trades else 0.0
    ret = (cash / float(args.starting_equity) - 1.0) * 100.0 if args.starting_equity > 0 else 0.0
    return SegmentResult(
        start=iso_time(candles[start].ts),
        end=iso_time(candles[end - 1].ts),
        return_pct=ret,
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd,
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate_pct=win_rate,
        fees=fees,
        exposure_pct=active_bars / max(1, end - max(1, start)) * 100.0,
    )


def simulator_volatility_scale(
    candles: list[Candle],
    index: int,
    strategy_params: dict[str, Any] | None,
) -> float:
    target_bps = float((strategy_params or {}).get("target_daily_vol_bps", 0.0) or 0.0)
    if target_bps <= 0 or index <= 2:
        return 1.0
    window = max(20, int((strategy_params or {}).get("vol_window_bars", 48) or 48))
    returns: list[float] = []
    start = max(1, index - window)
    for candle_index in range(start, index):
        previous = float(candles[candle_index - 1].close)
        current = float(candles[candle_index].close)
        if previous > 0 and current > 0:
            returns.append(math.log(current / previous))
    if len(returns) < 19:
        return 1.0
    sigma = statistics.pstdev(returns)
    if sigma <= 0:
        return 1.0
    intervals = [
        candles[i].ts - candles[i - 1].ts
        for i in range(max(1, start), index)
        if candles[i].ts > candles[i - 1].ts
    ]
    bar_ms = statistics.median(intervals) if intervals else 300_000.0
    realized_daily_bps = sigma * math.sqrt(86_400_000.0 / bar_ms) * 10000.0
    return min(1.0, target_bps / realized_daily_bps) if realized_daily_bps > 0 else 1.0


def strategy_atr_values(candles: list[Candle], strategy_params: dict[str, Any] | None) -> list[float]:
    if not strategy_params or "stop_loss_atr_mult" not in strategy_params:
        return [math.nan] * len(candles)
    window = int(strategy_params.get("atr_window", 14))
    return atr([c.high for c in candles], [c.low for c in candles], [c.close for c in candles], window)


def strategy_risk_exit(
    candles: list[Candle],
    atr_values: list[float],
    index: int,
    side: int,
    entry: float,
    bars_held: int,
    strategy_params: dict[str, Any] | None,
) -> bool:
    if not strategy_params or index <= 0 or entry <= 0:
        return False
    time_stop = int(strategy_params.get("time_stop_bars", 0) or 0)
    if time_stop > 0 and bars_held >= time_stop:
        return True
    prior = candles[index - 1]
    stop_distance = 0.0
    stop_bps = float(strategy_params.get("stop_loss_bps", 0.0) or 0.0)
    if stop_bps > 0:
        stop_distance = max(stop_distance, entry * stop_bps / 10000.0)
    atr_mult = float(strategy_params.get("stop_loss_atr_mult", 0.0) or 0.0)
    if atr_mult > 0 and index - 1 < len(atr_values) and math.isfinite(atr_values[index - 1]):
        stop_distance = max(stop_distance, atr_values[index - 1] * atr_mult)
    if stop_distance > 0:
        if side > 0 and prior.low <= entry - stop_distance:
            return True
        if side < 0 and prior.high >= entry + stop_distance:
            return True
    take_profit_bps = float(strategy_params.get("take_profit_bps", 0.0) or 0.0)
    if take_profit_bps > 0:
        take_distance = entry * take_profit_bps / 10000.0
        if side > 0 and prior.high >= entry + take_distance:
            return True
        if side < 0 and prior.low <= entry - take_distance:
            return True
    return False


def simulate_test_folds(
    candles: list[Candle],
    targets: list[int],
    start: int,
    end: int,
    requested_folds: int,
    args: argparse.Namespace,
    strategy_params: dict[str, Any] | None = None,
) -> list[SegmentResult]:
    length = max(0, end - start)
    if length < 2:
        return []
    folds = max(1, min(requested_folds, length // 2))
    step = max(1, length // folds)
    results: list[SegmentResult] = []
    for index in range(folds):
        fold_start = start + index * step
        fold_end = end if index == folds - 1 else min(end, fold_start + step)
        if fold_end - fold_start >= 2:
            results.append(simulate_segment(candles, targets, fold_start, fold_end, args, strategy_params))
    return results


def train_selection_score(train: SegmentResult, activity_weight: float = 0.0) -> float:
    trade_penalty = max(0, 6 - train.trades) * 1.5
    pf_bonus = min(2.0, math.log(max(train.profit_factor, 0.01))) if train.profit_factor > 1 else -1.0
    activity_bonus = max(0.0, activity_weight) * max(0.0, min(100.0, train.exposure_pct)) / 100.0
    return train.return_pct - 0.8 * train.max_drawdown_pct + 0.08 * min(train.trades, 50) + pf_bonus - trade_penalty + activity_bonus


def holdout_validation_score(test: SegmentResult, folds: list[SegmentResult]) -> float:
    positive_folds = sum(1 for fold in folds if fold.return_pct > 0 and fold.profit_factor >= 1.0)
    median_fold = statistics.median([fold.return_pct for fold in folds]) if folds else test.return_pct
    worst_fold = min((fold.return_pct for fold in folds), default=test.return_pct)
    pf_bonus = min(2.0, math.log(max(test.profit_factor, 0.01))) if test.profit_factor > 1 else -1.0
    return (
        test.return_pct
        - 0.8 * test.max_drawdown_pct
        + 0.08 * min(test.trades, 50)
        + pf_bonus
        + 0.5 * positive_folds
        + 0.25 * median_fold
        + 0.25 * min(0.0, worst_fold)
    )


def ema(values: list[float], window: int) -> list[float]:
    out = [math.nan] * len(values)
    if not values or window <= 0:
        return out
    alpha = 2.0 / (window + 1.0)
    current = values[0]
    for i, value in enumerate(values):
        current = value if i == 0 else alpha * value + (1.0 - alpha) * current
        out[i] = current
    return out


def rsi(values: list[float], window: int) -> list[float]:
    out = [math.nan] * len(values)
    if len(values) <= window:
        return out
    gains = []
    losses = []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(0.0, change))
        losses.append(max(0.0, -change))
        if i < window:
            continue
        avg_gain = statistics.fmean(gains[-window:])
        avg_loss = statistics.fmean(losses[-window:])
        if avg_loss <= 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], window: int) -> list[float]:
    out = [math.nan] * len(closes)
    trs = []
    for i in range(len(closes)):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
        if i >= window:
            out[i] = statistics.fmean(trs[i + 1 - window : i + 1])
    return out


def write_outputs(output_dir: Path, results: list[SearchResult], args: argparse.Namespace, inst_ids: list[str]) -> None:
    rows = [result_to_row(index + 1, result) for index, result in enumerate(results)]
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_multi_strategy_search",
        "instruments": inst_ids,
        "config": {
            "bar": args.bar,
            "limit": args.limit,
            "pages": args.pages,
            "trainRatio": args.train_ratio,
            "testFolds": args.test_folds,
            "feeBps": args.fee_bps,
            "slippageBps": args.slippage_bps,
            "costStressMultiplier": getattr(args, "cost_stress_multiplier", 1.0),
            "holdingCostBpsPerDay": getattr(args, "holding_cost_bps_per_day", 0.0),
            "leverage": args.leverage,
            "marginPct": args.margin_pct,
        },
        "sourceInspirations": [
            "freqtrade/freqtrade-strategies: common open-source crypto strategy examples",
            "jesse-ai/example-strategies: documented crypto strategy examples",
            "fmzquant/strategies: large strategy idea catalog",
            "polakowo/vectorbt: matrix-style multi-configuration backtesting concept",
        ],
        "summary": summary_payload(results),
        "rows": rows,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output_dir / "leaderboard.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def result_to_row(rank: int, result: SearchResult) -> dict[str, Any]:
    fold_returns = [fold.return_pct for fold in result.test_folds]
    positive_folds = sum(1 for fold in result.test_folds if fold.return_pct > 0 and fold.profit_factor >= 1.0)
    return {
        "rank": rank,
        "inst_id": result.inst_id,
        "strategy": result.strategy,
        "family": result.family,
        "params": json.dumps(result.params, sort_keys=True),
        "bars": result.bars,
        "train_start": result.train.start,
        "train_end": result.train.end,
        "test_start": result.test.start,
        "test_end": result.test.end,
        "train_return_pct": f"{result.train.return_pct:.8f}",
        "train_profit_factor": f"{result.train.profit_factor:.6f}",
        "train_max_drawdown_pct": f"{result.train.max_drawdown_pct:.8f}",
        "train_trades": result.train.trades,
        "train_exposure_pct": f"{result.train.exposure_pct:.4f}",
        "test_return_pct": f"{result.test.return_pct:.8f}",
        "test_profit_factor": f"{result.test.profit_factor:.6f}",
        "test_max_drawdown_pct": f"{result.test.max_drawdown_pct:.8f}",
        "test_trades": result.test.trades,
        "test_exposure_pct": f"{result.test.exposure_pct:.4f}",
        "test_win_rate_pct": f"{result.test.win_rate_pct:.4f}",
        "test_fees": f"{result.test.fees:.8f}",
        "test_positive_folds": positive_folds,
        "test_folds": len(result.test_folds),
        "test_worst_fold_return_pct": f"{min(fold_returns, default=result.test.return_pct):.8f}",
        "test_median_fold_return_pct": f"{statistics.median(fold_returns) if fold_returns else result.test.return_pct:.8f}",
        "train_score": f"{result.train_score:.8f}",
        "holdout_score": f"{result.holdout_score:.8f}",
        "score": f"{result.score:.8f}",
        "passed": str(result.passed).lower(),
    }


def summary_payload(results: list[SearchResult]) -> dict[str, Any]:
    passed = [item for item in results if item.passed]
    test_returns = [item.test.return_pct for item in results]
    positive_fold_rates = [
        sum(1 for fold in item.test_folds if fold.return_pct > 0 and fold.profit_factor >= 1.0) / len(item.test_folds) * 100.0
        for item in results
        if item.test_folds
    ]
    return {
        "testedConfigs": len(results),
        "passedConfigs": len(passed),
        "passedRatePct": len(passed) / len(results) * 100.0 if results else 0.0,
        "bestTrainScore": max((item.train_score for item in results), default=0.0),
        "bestHoldoutScore": max((item.holdout_score for item in results), default=0.0),
        "bestTestReturnPct": max(test_returns, default=0.0),
        "medianTestReturnPct": statistics.median(test_returns) if test_returns else 0.0,
        "meanTestReturnPct": statistics.fmean(test_returns) if test_returns else 0.0,
        "medianPositiveFoldRatePct": statistics.median(positive_fold_rates) if positive_fold_rates else 0.0,
        "families": sorted({item.family for item in results}),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Multi-Strategy Search",
        "",
        "Read-only train/test search over independent strategy families.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Tested configs | {summary['testedConfigs']} |",
        f"| Passed configs | {summary['passedConfigs']} |",
        f"| Passed rate | {summary['passedRatePct']:.2f}% |",
        f"| Best test return | {summary['bestTestReturnPct']:.6f}% |",
        f"| Median test return | {summary['medianTestReturnPct']:.6f}% |",
        f"| Mean test return | {summary['meanTestReturnPct']:.6f}% |",
        f"| Median positive holdout-fold rate | {summary['medianPositiveFoldRatePct']:.2f}% |",
        "",
        "## Top 25",
        "",
        "Ranked by a combined train/holdout score. Test columns are holdout validation.",
        "",
        "| Rank | Instrument | Strategy | Family | Train Ret % | Train Score | Test Ret % | Test PF | Test DD % | Folds +/N | Passed |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"][:25]:
        lines.append(
            f"| {row['rank']} | {row['inst_id']} | {row['strategy']} | {row['family']} | "
            f"{row['train_return_pct']} | {row['train_score']} | {row['test_return_pct']} | {row['test_profit_factor']} | "
            f"{row['test_max_drawdown_pct']} | {row['test_positive_folds']}/{row['test_folds']} | {row['passed']} |"
        )
    return "\n".join(lines) + "\n"


def print_summary(results: list[SearchResult]) -> None:
    summary = summary_payload(results)
    print(
        "tested={testedConfigs} passed={passedConfigs} passed_rate={passedRatePct:.2f}% "
        "best_test_return={bestTestReturnPct:.6f}% median_test_return={medianTestReturnPct:.6f}%".format(**summary)
    )


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def candles_to_tuples(candles: list[Candle]) -> list[tuple[int, float, float, float, float]]:
    return [(candle.ts, float(candle.open), float(candle.high), float(candle.low), float(candle.close)) for candle in candles]


def tuples_to_candles(values: list[tuple[int, float, float, float, float]]) -> list[Candle]:
    return [Candle(ts, open_, high, low, close, 0.0) for ts, open_, high, low, close in values]


def dec(value: Any) -> Any:
    from decimal import Decimal

    return Decimal(str(value))


def iso_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
