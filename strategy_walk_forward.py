from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle
from okx_client import OkxRestClient
from strategy_search import (
    OUTPUT_ROOT as SEARCH_OUTPUT_ROOT,
    candles_to_tuples,
    load_candles_for_instruments,
    resolve_instruments,
    simulate_segment,
    strategy_grid,
    strategy_targets,
    train_selection_score,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = SEARCH_OUTPUT_ROOT.parent / "strategy_walk_forward"
ROW_FIELDS = [
    "window",
    "rank",
    "inst_id",
    "strategy",
    "family",
    "params",
    "regime_filter",
    "allowed_regimes",
    "train_start",
    "train_end",
    "test_start",
    "test_end",
    "train_return_pct",
    "train_profit_factor",
    "train_max_drawdown_pct",
    "train_trades",
    "train_exposure_pct",
    "train_score",
    "test_return_pct",
    "test_profit_factor",
    "test_max_drawdown_pct",
    "test_trades",
    "test_exposure_pct",
    "test_win_rate_pct",
    "test_fees",
    "passed",
]
AGG_FIELDS = [
    "rank",
    "inst_id",
    "strategy",
    "family",
    "params",
    "regime_filter",
    "allowed_regimes",
    "selected_windows",
    "passed_windows",
    "pass_rate_pct",
    "total_test_return_pct",
    "mean_test_return_pct",
    "median_test_return_pct",
    "worst_test_return_pct",
    "mean_test_profit_factor",
    "mean_test_drawdown_pct",
    "mean_test_exposure_pct",
    "total_test_trades",
    "score",
    "passed",
]


@dataclass(slots=True)
class Window:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass(slots=True)
class WindowCandidate:
    window: Window
    rank: int
    inst_id: str
    strategy: str
    family: str
    params: dict[str, Any]
    regime_filter: str
    allowed_regimes: tuple[str, ...]
    train: Any
    test: Any
    train_score: float
    passed: bool


@dataclass(slots=True)
class AggregateCandidate:
    inst_id: str
    strategy: str
    family: str
    params: str
    regime_filter: str
    allowed_regimes: str
    selected_windows: int
    passed_windows: int
    total_test_return_pct: float
    mean_test_return_pct: float
    median_test_return_pct: float
    worst_test_return_pct: float
    mean_test_profit_factor: float
    mean_test_drawdown_pct: float
    mean_test_exposure_pct: float
    total_test_trades: int
    score: float
    passed: bool


@dataclass(slots=True)
class RegimeVariant:
    name: str
    allowed: tuple[str, ...]


def main() -> int:
    args = parse_args()
    output_dir = resolve_walk_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inst_ids = resolve_instruments(args)
    for extra in args.extra_inst_id:
        if extra and extra not in inst_ids:
            inst_ids.append(extra)
    args.funding_daily_bps_map = build_funding_daily_bps_map(inst_ids, args) if args.funding_cost_from_cache else {}
    args.slippage_bps_map = build_slippage_bps_map(inst_ids, args) if args.slippage_from_microstructure else {}
    candles_by_inst = load_candles_for_instruments(args, inst_ids)
    rows = run_walk_forward(candles_by_inst, args)
    aggregates = aggregate_rows(rows, args)
    write_outputs(output_dir, rows, aggregates, args, inst_ids)
    print(f"strategy_walk_forward_report={output_dir}")
    print_summary(rows, aggregates)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only rolling walk-forward validation for multi-strategy OKX research.")
    parser.add_argument("--inst-id", action="append", default=[], help="Instrument to test. Can be repeated. Defaults to public top-N.")
    parser.add_argument(
        "--extra-inst-id",
        action="append",
        default=[],
        help="Instrument appended to the resolved pool (e.g. currently approved live instruments). Can be repeated.",
    )
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--strategy-name",
        action="append",
        default=[],
        help="Restrict research to named strategies. Can be repeated; default tests the full grid.",
    )
    parser.add_argument("--min-quote-volume", default="5000000")
    parser.add_argument("--max-spread-bps", default="20")
    parser.add_argument("--bar", default="5m")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=24)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--min-bars", type=int, default=900)
    parser.add_argument("--train-bars", type=int, default=1440)
    parser.add_argument("--test-bars", type=int, default=360)
    parser.add_argument("--step-bars", type=int, default=360)
    parser.add_argument("--select-top", type=int, default=3)
    parser.add_argument("--min-train-trades", type=int, default=6)
    parser.add_argument("--min-test-trades", type=int, default=3)
    parser.add_argument("--min-train-profit-factor", type=float, default=1.05)
    parser.add_argument("--min-test-profit-factor", type=float, default=1.05)
    parser.add_argument("--max-test-drawdown-pct", type=float, default=12.0)
    parser.add_argument(
        "--min-exposure-pct",
        type=float,
        default=0.0,
        help="Minimum in-position bar percentage required in both train and test windows.",
    )
    parser.add_argument(
        "--activity-score-weight",
        type=float,
        default=0.0,
        help="Small train-only score bonus at 100% exposure; return/risk gates remain unchanged.",
    )
    parser.add_argument("--regime-filter", choices=["off", "train_best"], default="off")
    parser.add_argument("--regime-lookback", type=int, default=48)
    parser.add_argument("--regime-vol-window", type=int, default=48)
    parser.add_argument("--regime-trend-bps", type=float, default=120.0)
    parser.add_argument("--regime-range-bps", type=float, default=45.0)
    parser.add_argument("--regime-high-vol-bps", type=float, default=25.0)
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--leverage", type=float, default=3.0)
    parser.add_argument("--margin-pct", type=float, default=35.0)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--cost-stress-multiplier", type=float, default=1.0)
    parser.add_argument("--holding-cost-bps-per-day", type=float, default=0.0)
    parser.add_argument(
        "--funding-cost-from-cache",
        action="store_true",
        help="Use realized funding history (data/funding cache, refreshed when missing) as a per-instrument holding-cost floor.",
    )
    parser.add_argument("--funding-sleep", type=float, default=0.15)
    parser.add_argument(
        "--slippage-from-microstructure",
        action="store_true",
        help="Use median half-spread from data/microstructure snapshots as a per-instrument slippage floor.",
    )
    parser.add_argument("--microstructure-min-samples", type=int, default=200)
    parser.add_argument("--include-cross-sectional", action="store_true", help="Add cross-sectional momentum candidates across the instrument basket.")
    parser.add_argument("--cross-sectional-top-k", type=int, default=2)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def run_walk_forward(candles_by_inst: dict[str, list[Candle]], args: argparse.Namespace) -> list[WindowCandidate]:
    specs = strategy_grid()
    selected_names = set(getattr(args, "strategy_name", []) or [])
    if selected_names:
        specs = [spec for spec in specs if spec.name in selected_names]
    variants = regime_variants(args)
    rows: list[WindowCandidate] = []
    normalized_candles = {
        inst_id: tuples_to_float_candles(candles_to_tuples(raw_candles))
        for inst_id, raw_candles in candles_by_inst.items()
    }
    for inst_id, raw_candles in candles_by_inst.items():
        candles = normalized_candles[inst_id]
        if len(candles) < max(args.min_bars, args.train_bars + args.test_bars):
            continue
        inst_args = instrument_cost_args(args, inst_id)
        windows = build_windows(len(candles), args.train_bars, args.test_bars, args.step_bars)
        memberships = build_regime_memberships(candles, args)
        target_cache = {
            target_cache_key(spec_key(spec), variant.name): filter_targets_by_regime(
                strategy_targets(candles, spec),
                memberships,
                variant.allowed,
            )
            for spec in specs
            for variant in variants
        }
        for window in windows:
            selected = select_window_candidates(inst_id, candles, specs, target_cache, variants, window, inst_args)
            rows.extend(selected)
    if getattr(args, "include_cross_sectional", False):
        rows.extend(run_cross_sectional_walk_forward(normalized_candles, args))
    return rows


def instrument_cost_args(args: argparse.Namespace, inst_id: str) -> argparse.Namespace:
    funding_map = getattr(args, "funding_daily_bps_map", {}) or {}
    slippage_map = getattr(args, "slippage_bps_map", {}) or {}
    funding_bps = funding_map.get(inst_id)
    slippage_bps = slippage_map.get(inst_id)
    if funding_bps is None and slippage_bps is None:
        return args
    inst_args = argparse.Namespace(**vars(args))
    if funding_bps is not None:
        inst_args.holding_cost_bps_per_day = max(float(args.holding_cost_bps_per_day), float(funding_bps))
    if slippage_bps is not None:
        inst_args.slippage_bps = max(float(args.slippage_bps), float(slippage_bps))
    return inst_args


def build_funding_daily_bps_map(inst_ids: list[str], args: argparse.Namespace) -> dict[str, float]:
    from funding_research import fetch_funding_history, funding_cache_path, read_funding_csv, write_funding_csv

    client = OkxRestClient()
    result: dict[str, float] = {}
    for inst_id in inst_ids:
        path = funding_cache_path(inst_id, 100, 1)
        points = read_funding_csv(path) if path.exists() else []
        stale = not points or (time.time() * 1000 - points[-1].ts) > 7 * 86_400_000
        if stale:
            try:
                points = fetch_funding_history(client, inst_id, limit=100, pages=1, sleep=args.funding_sleep)
                write_funding_csv(path, points)
            except Exception as exc:  # noqa: BLE001 - research cost floor must not kill the run
                print(f"funding fetch failed for {inst_id}: {exc}")
        daily_bps = funding_daily_bps(points)
        if daily_bps is not None:
            result[inst_id] = daily_bps
    return result


def funding_daily_bps(points: list[Any]) -> float | None:
    if len(points) < 10:
        return None
    timestamps = [point.ts for point in points]
    intervals = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
    if not intervals:
        return None
    median_interval = statistics.median(intervals)
    if median_interval <= 0:
        return None
    settlements_per_day = 86_400_000.0 / median_interval
    rates = [abs(point.realized_rate if point.realized_rate else point.rate) for point in points]
    mean_abs_rate = statistics.fmean(rates)
    return mean_abs_rate * settlements_per_day * 10000.0


def build_slippage_bps_map(inst_ids: list[str], args: argparse.Namespace) -> dict[str, float]:
    root = PROJECT_ROOT / "data" / "microstructure"
    result: dict[str, float] = {}
    for inst_id in inst_ids:
        token = "".join(ch.lower() if ch.isalnum() else "_" for ch in inst_id).strip("_")
        inst_dir = root / token
        if not inst_dir.is_dir():
            continue
        spreads: list[float] = []
        for path in sorted(inst_dir.glob("*.jsonl"))[-3:]:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines[-4000:]:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                value = ((record.get("features") or {}).get("book") or {}).get("spread_bps")
                if isinstance(value, (int, float)) and value >= 0:
                    spreads.append(float(value))
        if len(spreads) >= max(1, args.microstructure_min_samples):
            result[inst_id] = statistics.median(spreads) / 2.0
    return result


def build_windows(total_bars: int, train_bars: int, test_bars: int, step_bars: int) -> list[Window]:
    if train_bars <= 1 or test_bars <= 1 or step_bars <= 0:
        raise ValueError("train-bars and test-bars must be > 1; step-bars must be > 0")
    windows: list[Window] = []
    start = 1
    index = 1
    while start + train_bars + test_bars <= total_bars:
        train_start = start
        train_end = train_start + train_bars
        test_start = train_end
        test_end = test_start + test_bars
        windows.append(Window(index, train_start, train_end, test_start, test_end))
        index += 1
        start += step_bars
    return windows


def select_window_candidates(
    inst_id: str,
    candles: list[Candle],
    specs: list[Any],
    target_cache: dict[str, list[int]],
    variants: list[RegimeVariant],
    window: Window,
    args: argparse.Namespace,
) -> list[WindowCandidate]:
    ranked: list[WindowCandidate] = []
    for spec in specs:
        key = spec_key(spec)
        for variant in variants:
            targets = target_cache[target_cache_key(key, variant.name)]
            train = simulate_segment(candles, targets, window.train_start, window.train_end, args, spec.params)
            if train.trades < args.min_train_trades:
                continue
            if train.exposure_pct < float(getattr(args, "min_exposure_pct", 0.0)):
                continue
            if train.return_pct <= 0 or train.profit_factor < args.min_train_profit_factor:
                continue
            train_score = train_selection_score(train, float(getattr(args, "activity_score_weight", 0.0)))
            ranked.append(
                WindowCandidate(
                    window=window,
                    rank=0,
                    inst_id=inst_id,
                    strategy=spec.name,
                    family=spec.family,
                    params=spec.params,
                    regime_filter=variant.name,
                    allowed_regimes=variant.allowed,
                    train=train,
                    test=train,
                    train_score=train_score,
                    passed=False,
                )
            )
    ranked.sort(key=lambda item: item.train_score, reverse=True)
    selected: list[WindowCandidate] = []
    for rank, candidate in enumerate(ranked[: max(0, args.select_top)], start=1):
        targets = target_cache[target_cache_key(spec_key_from_parts(candidate.strategy, candidate.params), candidate.regime_filter)]
        test = simulate_segment(candles, targets, window.test_start, window.test_end, args, candidate.params)
        passed = is_test_pass(test, args)
        selected.append(
            WindowCandidate(
                window=window,
                rank=rank,
                inst_id=candidate.inst_id,
                strategy=candidate.strategy,
                family=candidate.family,
                params=candidate.params,
                regime_filter=candidate.regime_filter,
                allowed_regimes=candidate.allowed_regimes,
                train=candidate.train,
                test=test,
                train_score=candidate.train_score,
                passed=passed,
            )
        )
    return selected


def run_cross_sectional_walk_forward(candles_by_inst: dict[str, list[Candle]], args: argparse.Namespace) -> list[WindowCandidate]:
    eligible = {
        inst_id: candles
        for inst_id, candles in candles_by_inst.items()
        if len(candles) >= max(args.min_bars, args.train_bars + args.test_bars)
    }
    if len(eligible) < 2:
        return []
    shared_bars = min(len(candles) for candles in eligible.values())
    windows = build_windows(shared_bars, args.train_bars, args.test_bars, args.step_bars)
    specs = cross_sectional_specs(args)
    rows: list[WindowCandidate] = []
    for window in windows:
        ranked: list[tuple[float, dict[str, list[int]], Any, Any]] = []
        for spec in specs:
            targets_by_inst = cross_sectional_momentum_targets(eligible, spec.params, shared_bars)
            train = simulate_portfolio_segment(eligible, targets_by_inst, window.train_start, window.train_end, args)
            if train.trades < args.min_train_trades:
                continue
            if train.return_pct <= 0 or train.profit_factor < args.min_train_profit_factor:
                continue
            if train.exposure_pct < float(getattr(args, "min_exposure_pct", 0.0)):
                continue
            ranked.append((train_selection_score(train, float(getattr(args, "activity_score_weight", 0.0))), targets_by_inst, spec, train))
        ranked.sort(key=lambda item: item[0], reverse=True)
        for rank, (train_score, targets_by_inst, spec, train) in enumerate(ranked[: max(0, args.select_top)], start=1):
            test = simulate_portfolio_segment(eligible, targets_by_inst, window.test_start, window.test_end, args)
            rows.append(
                WindowCandidate(
                    window=window,
                    rank=rank,
                    inst_id="CROSS_SECTIONAL",
                    strategy=spec.name,
                    family=spec.family,
                    params=spec.params,
                    regime_filter="basket",
                    allowed_regimes=("basket",),
                    train=train,
                    test=test,
                    train_score=train_score,
                    passed=is_test_pass(test, args),
                )
            )
    return rows


def cross_sectional_specs(args: argparse.Namespace) -> list[Any]:
    top_k = max(1, int(getattr(args, "cross_sectional_top_k", 2)))
    specs = []
    for lookback in (24, 48, 96):
        for threshold_bps in (50.0, 100.0):
            specs.append(
                type(
                    "CrossSectionalSpec",
                    (),
                    {
                        "name": "cross_sectional_momentum",
                        "family": "cross_sectional",
                        "params": {"lookback": lookback, "top_k": top_k, "threshold_bps": threshold_bps},
                    },
                )()
            )
    return specs


def cross_sectional_momentum_targets(
    candles_by_inst: dict[str, list[Candle]],
    params: dict[str, Any],
    bars: int,
) -> dict[str, list[int]]:
    lookback = int(params["lookback"])
    top_k = max(1, int(params["top_k"]))
    threshold_bps = float(params.get("threshold_bps", 0.0))
    targets_by_inst = {inst_id: [0] * bars for inst_id in candles_by_inst}
    closes_by_inst = {inst_id: [float(candle.close) for candle in candles[:bars]] for inst_id, candles in candles_by_inst.items()}
    for index in range(lookback + 1, bars):
        scores: list[tuple[str, float]] = []
        for inst_id, closes in closes_by_inst.items():
            start = closes[index - 1 - lookback]
            end = closes[index - 1]
            if start > 0:
                scores.append((inst_id, (end / start - 1.0) * 10000.0))
        if len(scores) < 2:
            continue
        scores.sort(key=lambda item: item[1], reverse=True)
        longs = {inst_id for inst_id, score in scores[:top_k] if score >= threshold_bps}
        shorts = {inst_id for inst_id, score in scores[-top_k:] if score <= -threshold_bps}
        for inst_id in targets_by_inst:
            if inst_id in longs:
                targets_by_inst[inst_id][index] = 1
            elif inst_id in shorts:
                targets_by_inst[inst_id][index] = -1
    return targets_by_inst


def simulate_portfolio_segment(
    candles_by_inst: dict[str, list[Candle]],
    targets_by_inst: dict[str, list[int]],
    start: int,
    end: int,
    args: argparse.Namespace,
) -> Any:
    child_args = argparse.Namespace(**vars(args))
    child_args.starting_equity = float(args.starting_equity) / max(1, len(candles_by_inst))
    results = [
        simulate_segment(candles[:end], targets_by_inst[inst_id], start, end, child_args)
        for inst_id, candles in candles_by_inst.items()
        if inst_id in targets_by_inst
    ]
    from strategy_search import SegmentResult

    returns = [result.return_pct for result in results]
    total_return = statistics.fmean(returns)
    gross_profit = 0.0
    gross_loss = 0.0
    for result in results:
        pnl = child_args.starting_equity * result.return_pct / 100.0
        if pnl > 0:
            gross_profit += pnl
        elif pnl < 0:
            gross_loss += abs(pnl)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    trades = sum(result.trades for result in results)
    wins = sum(result.wins for result in results)
    losses = sum(result.losses for result in results)
    return SegmentResult(
        start=results[0].start,
        end=results[0].end,
        return_pct=total_return,
        profit_factor=profit_factor,
        max_drawdown_pct=max(result.max_drawdown_pct for result in results),
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate_pct=wins / trades * 100.0 if trades else 0.0,
        fees=sum(result.fees for result in results),
        exposure_pct=statistics.fmean(result.exposure_pct for result in results),
    )


def is_test_pass(test: Any, args: argparse.Namespace) -> bool:
    return (
        test.return_pct > 0
        and test.profit_factor >= args.min_test_profit_factor
        and test.trades >= args.min_test_trades
        and test.max_drawdown_pct <= args.max_test_drawdown_pct
        and test.exposure_pct >= float(getattr(args, "min_exposure_pct", 0.0))
    )


def regime_variants(args: argparse.Namespace) -> list[RegimeVariant]:
    if getattr(args, "regime_filter", "off") == "off":
        return [RegimeVariant("all", ("all",))]
    return [
        RegimeVariant("all", ("all",)),
        RegimeVariant("trend", ("trend",)),
        RegimeVariant("trend_up", ("trend_up",)),
        RegimeVariant("trend_down", ("trend_down",)),
        RegimeVariant("range", ("range",)),
        RegimeVariant("mixed", ("mixed",)),
        RegimeVariant("high_vol", ("high_vol",)),
        RegimeVariant("normal_vol", ("normal_vol",)),
        RegimeVariant("trend_high_vol", ("trend", "high_vol")),
        RegimeVariant("range_normal_vol", ("range", "normal_vol")),
    ]


def build_regime_memberships(candles: list[Candle], args: argparse.Namespace) -> list[set[str]]:
    closes = [float(candle.close) for candle in candles]
    lookback = max(2, int(getattr(args, "regime_lookback", 48)))
    vol_window = max(2, int(getattr(args, "regime_vol_window", 48)))
    trend_bps = float(getattr(args, "regime_trend_bps", 120.0))
    range_bps = float(getattr(args, "regime_range_bps", 45.0))
    high_vol_bps = float(getattr(args, "regime_high_vol_bps", 25.0))
    memberships: list[set[str]] = []
    one_bar_returns = [0.0]
    for index in range(1, len(closes)):
        prev = closes[index - 1]
        current = closes[index]
        one_bar_returns.append((current / prev - 1.0) * 10000.0 if prev > 0 else 0.0)

    for index in range(len(closes)):
        labels = {"all"}
        if index <= 1:
            labels.update({"unknown", "normal_vol"})
            memberships.append(labels)
            continue

        end = index - 1
        trend_start = max(0, end - lookback)
        start_close = closes[trend_start]
        end_close = closes[end]
        move_bps = (end_close / start_close - 1.0) * 10000.0 if start_close > 0 else 0.0
        if move_bps >= trend_bps:
            labels.update({"trend", "trend_up"})
        elif move_bps <= -trend_bps:
            labels.update({"trend", "trend_down"})
        elif abs(move_bps) <= range_bps:
            labels.add("range")
        else:
            labels.add("mixed")

        vol_start = max(1, end - vol_window + 1)
        sample = one_bar_returns[vol_start : end + 1]
        avg_abs_bps = statistics.fmean(abs(value) for value in sample) if sample else 0.0
        labels.add("high_vol" if avg_abs_bps >= high_vol_bps else "normal_vol")
        memberships.append(labels)
    return memberships


def filter_targets_by_regime(targets: list[int], memberships: list[set[str]], allowed: tuple[str, ...]) -> list[int]:
    if "all" in allowed:
        return list(targets)
    allowed_set = set(allowed)
    return [target if index < len(memberships) and memberships[index].intersection(allowed_set) else 0 for index, target in enumerate(targets)]


def aggregate_rows(rows: list[WindowCandidate], args: argparse.Namespace) -> list[AggregateCandidate]:
    grouped: dict[tuple[str, str, str, str, str, str], list[WindowCandidate]] = {}
    for row in rows:
        key = (row.inst_id, row.strategy, row.family, params_key(row.params), row.regime_filter, ",".join(row.allowed_regimes))
        grouped.setdefault(key, []).append(row)

    aggregates: list[AggregateCandidate] = []
    for (inst_id, strategy, family, params, regime_filter, allowed_regimes), items in grouped.items():
        returns = [item.test.return_pct for item in items]
        pfs = [item.test.profit_factor for item in items if math.isfinite(item.test.profit_factor) and item.test.profit_factor < 900]
        drawdowns = [item.test.max_drawdown_pct for item in items]
        passed_windows = sum(1 for item in items if item.passed)
        total_return = compound_returns(returns)
        mean_return = statistics.fmean(returns) if returns else 0.0
        median_return = statistics.median(returns) if returns else 0.0
        worst_return = min(returns, default=0.0)
        mean_pf = statistics.fmean(pfs) if pfs else 999.0 if returns and min(returns) > 0 else 0.0
        mean_dd = statistics.fmean(drawdowns) if drawdowns else 0.0
        mean_exposure = statistics.fmean(item.test.exposure_pct for item in items) if items else 0.0
        total_trades = sum(item.test.trades for item in items)
        selected_windows = len(items)
        pass_rate = passed_windows / selected_windows * 100.0 if selected_windows else 0.0
        score = total_return + 0.35 * mean_return + 0.15 * pass_rate - 0.7 * mean_dd + 0.05 * min(total_trades, 100)
        passed = (
            selected_windows >= max(2, min(3, args.select_top))
            and pass_rate >= 60.0
            and total_return > 0
            and median_return > 0
            and worst_return > -3.0
            and mean_exposure >= float(getattr(args, "min_exposure_pct", 0.0))
        )
        aggregates.append(
            AggregateCandidate(
                inst_id=inst_id,
                strategy=strategy,
                family=family,
                params=params,
                regime_filter=regime_filter,
                allowed_regimes=allowed_regimes,
                selected_windows=selected_windows,
                passed_windows=passed_windows,
                total_test_return_pct=total_return,
                mean_test_return_pct=mean_return,
                median_test_return_pct=median_return,
                worst_test_return_pct=worst_return,
                mean_test_profit_factor=mean_pf,
                mean_test_drawdown_pct=mean_dd,
                mean_test_exposure_pct=mean_exposure,
                total_test_trades=total_trades,
                score=score,
                passed=passed,
            )
        )
    aggregates.sort(key=lambda item: item.score, reverse=True)
    return aggregates


def compound_returns(returns_pct: list[float]) -> float:
    value = 1.0
    for ret in returns_pct:
        value *= 1.0 + ret / 100.0
    return (value - 1.0) * 100.0


def write_outputs(
    output_dir: Path,
    rows: list[WindowCandidate],
    aggregates: list[AggregateCandidate],
    args: argparse.Namespace,
    inst_ids: list[str],
) -> None:
    row_payloads = [row_to_dict(row) for row in rows]
    aggregate_payloads = [aggregate_to_dict(index + 1, item) for index, item in enumerate(aggregates)]
    summary = summary_payload(rows, aggregates)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_rolling_walk_forward",
        "instruments": inst_ids,
        "config": {
            "bar": args.bar,
            "limit": args.limit,
            "pages": args.pages,
            "trainBars": args.train_bars,
            "testBars": args.test_bars,
            "stepBars": args.step_bars,
            "selectTop": args.select_top,
            "strategyNames": getattr(args, "strategy_name", []) or [],
            "minExposurePct": getattr(args, "min_exposure_pct", 0.0),
            "activityScoreWeight": getattr(args, "activity_score_weight", 0.0),
            "regimeFilter": args.regime_filter,
            "regimeLookback": args.regime_lookback,
            "regimeVolWindow": args.regime_vol_window,
            "regimeTrendBps": args.regime_trend_bps,
            "regimeRangeBps": args.regime_range_bps,
            "regimeHighVolBps": args.regime_high_vol_bps,
            "feeBps": args.fee_bps,
            "slippageBps": args.slippage_bps,
            "costStressMultiplier": getattr(args, "cost_stress_multiplier", 1.0),
            "holdingCostBpsPerDay": getattr(args, "holding_cost_bps_per_day", 0.0),
            "fundingDailyBpsMap": getattr(args, "funding_daily_bps_map", {}) or {},
            "slippageBpsMap": getattr(args, "slippage_bps_map", {}) or {},
            "includeCrossSectional": getattr(args, "include_cross_sectional", False),
            "crossSectionalTopK": getattr(args, "cross_sectional_top_k", 0),
            "leverage": args.leverage,
            "marginPct": args.margin_pct,
        },
        "summary": summary,
        "rows": row_payloads,
        "aggregates": aggregate_payloads,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output_dir / "rows.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(row_payloads)
    with (output_dir / "aggregate.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=AGG_FIELDS)
        writer.writeheader()
        writer.writerows(aggregate_payloads)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def row_to_dict(row: WindowCandidate) -> dict[str, Any]:
    return {
        "window": row.window.index,
        "rank": row.rank,
        "inst_id": row.inst_id,
        "strategy": row.strategy,
        "family": row.family,
        "params": params_key(row.params),
        "regime_filter": row.regime_filter,
        "allowed_regimes": ",".join(row.allowed_regimes),
        "train_start": row.train.start,
        "train_end": row.train.end,
        "test_start": row.test.start,
        "test_end": row.test.end,
        "train_return_pct": f"{row.train.return_pct:.8f}",
        "train_profit_factor": f"{row.train.profit_factor:.6f}",
        "train_max_drawdown_pct": f"{row.train.max_drawdown_pct:.8f}",
        "train_trades": row.train.trades,
        "train_exposure_pct": f"{row.train.exposure_pct:.4f}",
        "train_score": f"{row.train_score:.8f}",
        "test_return_pct": f"{row.test.return_pct:.8f}",
        "test_profit_factor": f"{row.test.profit_factor:.6f}",
        "test_max_drawdown_pct": f"{row.test.max_drawdown_pct:.8f}",
        "test_trades": row.test.trades,
        "test_exposure_pct": f"{row.test.exposure_pct:.4f}",
        "test_win_rate_pct": f"{row.test.win_rate_pct:.4f}",
        "test_fees": f"{row.test.fees:.8f}",
        "passed": str(row.passed).lower(),
    }


def aggregate_to_dict(rank: int, item: AggregateCandidate) -> dict[str, Any]:
    return {
        "rank": rank,
        "inst_id": item.inst_id,
        "strategy": item.strategy,
        "family": item.family,
        "params": item.params,
        "regime_filter": item.regime_filter,
        "allowed_regimes": item.allowed_regimes,
        "selected_windows": item.selected_windows,
        "passed_windows": item.passed_windows,
        "pass_rate_pct": f"{item.passed_windows / item.selected_windows * 100.0 if item.selected_windows else 0.0:.4f}",
        "total_test_return_pct": f"{item.total_test_return_pct:.8f}",
        "mean_test_return_pct": f"{item.mean_test_return_pct:.8f}",
        "median_test_return_pct": f"{item.median_test_return_pct:.8f}",
        "worst_test_return_pct": f"{item.worst_test_return_pct:.8f}",
        "mean_test_profit_factor": f"{item.mean_test_profit_factor:.6f}",
        "mean_test_drawdown_pct": f"{item.mean_test_drawdown_pct:.8f}",
        "mean_test_exposure_pct": f"{item.mean_test_exposure_pct:.4f}",
        "total_test_trades": item.total_test_trades,
        "score": f"{item.score:.8f}",
        "passed": str(item.passed).lower(),
    }


def summary_payload(rows: list[WindowCandidate], aggregates: list[AggregateCandidate]) -> dict[str, Any]:
    test_returns = [row.test.return_pct for row in rows]
    return {
        "selectedRows": len(rows),
        "passedRows": sum(1 for row in rows if row.passed),
        "passedAggregates": sum(1 for item in aggregates if item.passed),
        "uniqueAggregates": len(aggregates),
        "medianSelectedTestReturnPct": statistics.median(test_returns) if test_returns else 0.0,
        "meanSelectedTestReturnPct": statistics.fmean(test_returns) if test_returns else 0.0,
        "bestAggregateScore": max((item.score for item in aggregates), default=0.0),
        "bestAggregateReturnPct": max((item.total_test_return_pct for item in aggregates), default=0.0),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Strategy Walk-Forward",
        "",
        "Rolling validation: each window ranks strategies only on the training segment, then validates selected strategies on the next unseen segment.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Selected window rows | {summary['selectedRows']} |",
        f"| Passed window rows | {summary['passedRows']} |",
        f"| Unique aggregate candidates | {summary['uniqueAggregates']} |",
        f"| Passed aggregate candidates | {summary['passedAggregates']} |",
        f"| Median selected test return | {summary['medianSelectedTestReturnPct']:.6f}% |",
        f"| Mean selected test return | {summary['meanSelectedTestReturnPct']:.6f}% |",
        f"| Best aggregate return | {summary['bestAggregateReturnPct']:.6f}% |",
        "",
        "## Top Aggregates",
        "",
        "| Rank | Instrument | Strategy | Regime | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["aggregates"][:25]:
        lines.append(
            f"| {row['rank']} | {row['inst_id']} | {row['strategy']} | {row['regime_filter']} | "
            f"{row['selected_windows']} | {row['pass_rate_pct']} | {row['total_test_return_pct']} | "
            f"{row['median_test_return_pct']} | {row['worst_test_return_pct']} | {row['passed']} |"
        )
    lines.extend(
        [
            "",
            "## Top Window Selections",
            "",
            "| Window | Rank | Instrument | Strategy | Regime | Train Ret % | Test Ret % | Test PF | Test DD % | Passed |",
            "| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["rows"][:25]:
        lines.append(
            f"| {row['window']} | {row['rank']} | {row['inst_id']} | {row['strategy']} | {row['regime_filter']} | "
            f"{row['train_return_pct']} | {row['test_return_pct']} | {row['test_profit_factor']} | "
            f"{row['test_max_drawdown_pct']} | {row['passed']} |"
        )
    return "\n".join(lines) + "\n"


def print_summary(rows: list[WindowCandidate], aggregates: list[AggregateCandidate]) -> None:
    summary = summary_payload(rows, aggregates)
    print(
        "selected_rows={selectedRows} passed_rows={passedRows} "
        "aggregates={uniqueAggregates} passed_aggregates={passedAggregates} "
        "median_test={medianSelectedTestReturnPct:.6f}%".format(**summary)
    )


def resolve_walk_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def spec_key(spec: Any) -> str:
    return spec_key_from_parts(spec.name, spec.params)


def spec_key_from_parts(name: str, params: dict[str, Any]) -> str:
    return f"{name}:{params_key(params)}"


def target_cache_key(base_key: str, regime_name: str) -> str:
    return f"{base_key}|regime={regime_name}"


def params_key(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True)


def tuples_to_float_candles(values: list[tuple[int, float, float, float, float]]) -> list[Candle]:
    return [Candle(ts, open_, high, low, close, 0.0) for ts, open_, high, low, close in values]


if __name__ == "__main__":
    raise SystemExit(main())
