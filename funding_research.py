from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import BAR_MS, DATA_DIR, Candle
from okx_client import OkxRestClient, load_env
from strategy_search import (
    candles_to_tuples,
    load_candles_for_instruments,
    resolve_instruments,
    train_selection_score,
)
from strategy_walk_forward import Window, build_windows, compound_returns


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "funding_research"
FUNDING_CACHE_DIR = PROJECT_ROOT / "data" / "funding"
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
    "train_score",
    "test_return_pct",
    "test_profit_factor",
    "test_max_drawdown_pct",
    "test_trades",
    "test_win_rate_pct",
    "test_fees",
    "funding_pnl",
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
    "total_test_trades",
    "score",
    "passed",
]


@dataclass(frozen=True, slots=True)
class FundingPoint:
    ts: int
    rate: float
    realized_rate: float


@dataclass(frozen=True, slots=True)
class FundingSpec:
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
    funding_pnl: float


@dataclass(slots=True)
class WindowCandidate:
    window: Window
    rank: int
    inst_id: str
    strategy: str
    family: str
    params: dict[str, Any]
    train: SegmentResult
    test: SegmentResult
    train_score: float
    passed: bool


@dataclass(slots=True)
class AggregateCandidate:
    inst_id: str
    strategy: str
    family: str
    params: str
    selected_windows: int
    passed_windows: int
    total_test_return_pct: float
    mean_test_return_pct: float
    median_test_return_pct: float
    worst_test_return_pct: float
    mean_test_profit_factor: float
    mean_test_drawdown_pct: float
    total_test_trades: int
    score: float
    passed: bool


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    inst_ids = resolve_instruments(args)
    candles_by_inst = load_candles_for_instruments(args, inst_ids)
    funding_by_inst = load_funding_for_instruments(args, inst_ids)
    rows = run_walk_forward(candles_by_inst, funding_by_inst, args)
    aggregates = aggregate_rows(rows, args)
    write_outputs(output_dir, rows, aggregates, args, inst_ids)
    print(f"funding_research_report={output_dir}")
    print_summary(rows, aggregates)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only funding-aware OKX swap research with walk-forward validation.")
    parser.add_argument("--inst-id", action="append", default=[], help="Instrument to test. Can be repeated. Defaults to public top-N.")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-quote-volume", default="5000000")
    parser.add_argument("--max-spread-bps", default="20")
    parser.add_argument("--bar", default="5m", choices=list(BAR_MS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=24)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--funding-limit", type=int, default=100)
    parser.add_argument("--funding-pages", type=int, default=1)
    parser.add_argument("--refresh-funding", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--min-bars", type=int, default=900)
    parser.add_argument("--train-bars", type=int, default=1440)
    parser.add_argument("--test-bars", type=int, default=360)
    parser.add_argument("--step-bars", type=int, default=360)
    parser.add_argument("--select-top", type=int, default=3)
    parser.add_argument("--min-train-trades", type=int, default=4)
    parser.add_argument("--min-test-trades", type=int, default=2)
    parser.add_argument("--min-train-profit-factor", type=float, default=1.05)
    parser.add_argument("--min-test-profit-factor", type=float, default=1.05)
    parser.add_argument("--max-test-drawdown-pct", type=float, default=12.0)
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--leverage", type=float, default=2.0)
    parser.add_argument("--margin-pct", type=float, default=25.0)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--cost-stress-multiplier", type=float, default=1.5)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def load_funding_for_instruments(args: argparse.Namespace, inst_ids: list[str]) -> dict[str, list[FundingPoint]]:
    load_env()
    client = OkxRestClient.from_env()
    FUNDING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[FundingPoint]] = {}
    for inst_id in inst_ids:
        path = funding_cache_path(inst_id, args.funding_limit, args.funding_pages)
        if path.exists() and not args.refresh_funding:
            points = read_funding_csv(path)
        else:
            points = fetch_funding_history(client, inst_id, limit=args.funding_limit, pages=args.funding_pages, sleep=args.sleep)
            write_funding_csv(path, points)
        result[inst_id] = points
    return result


def funding_cache_path(inst_id: str, limit: int, pages: int) -> Path:
    suffix = "" if pages <= 1 else f"x{pages}"
    return FUNDING_CACHE_DIR / f"{inst_id}_funding_{limit}{suffix}.csv"


def fetch_funding_history(client: OkxRestClient, inst_id: str, *, limit: int, pages: int, sleep: float) -> list[FundingPoint]:
    page_limit = max(1, min(100, int(limit)))
    before: str | None = None
    points: dict[int, FundingPoint] = {}
    for _ in range(max(1, int(pages))):
        params: dict[str, Any] = {"instId": inst_id, "limit": str(page_limit)}
        if before:
            params["before"] = before
        data = client.request("GET", "/api/v5/public/funding-rate-history", params=params).get("data", [])
        page_points = [funding_point_from_payload(item) for item in data if isinstance(item, dict)]
        page_points = [item for item in page_points if item is not None]
        if not page_points:
            break
        for item in page_points:
            points[item.ts] = item
        oldest = min(item.ts for item in page_points)
        next_before = str(oldest - 1)
        if next_before == before:
            break
        before = next_before
        time.sleep(max(0.0, sleep))
    return sorted(points.values(), key=lambda item: item.ts)


def funding_point_from_payload(item: dict[str, Any]) -> FundingPoint | None:
    ts = as_int(item.get("fundingTime") or item.get("ts"))
    if ts <= 0:
        return None
    rate = as_float(item.get("fundingRate"))
    realized = as_float(item.get("realizedRate"))
    return FundingPoint(ts=ts, rate=rate, realized_rate=realized if realized else rate)


def read_funding_csv(path: Path) -> list[FundingPoint]:
    with path.open("r", encoding="utf-8", newline="") as file:
        rows = csv.DictReader(file)
        return [
            FundingPoint(ts=as_int(row.get("funding_time")), rate=as_float(row.get("funding_rate")), realized_rate=as_float(row.get("realized_rate")))
            for row in rows
            if as_int(row.get("funding_time")) > 0
        ]


def write_funding_csv(path: Path, points: list[FundingPoint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["funding_time", "funding_rate", "realized_rate"])
        writer.writeheader()
        for point in sorted(points, key=lambda item: item.ts):
            writer.writerow({"funding_time": point.ts, "funding_rate": f"{point.rate:.12f}", "realized_rate": f"{point.realized_rate:.12f}"})


def funding_specs() -> list[FundingSpec]:
    specs: list[FundingSpec] = []
    for threshold_bps in (1.0, 2.5, 5.0):
        specs.append(FundingSpec("funding_carry", "funding", {"threshold_bps": threshold_bps, "mode": "carry"}))
        specs.append(FundingSpec("funding_sentiment", "funding", {"threshold_bps": threshold_bps, "mode": "sentiment"}))
    for threshold_bps in (2.5, 5.0):
        for momentum_lookback in (24, 72):
            specs.append(
                FundingSpec(
                    "funding_carry_momentum_filter",
                    "funding",
                    {
                        "threshold_bps": threshold_bps,
                        "momentum_lookback": momentum_lookback,
                        "max_against_momentum_bps": 150.0,
                    },
                )
            )
    for threshold_bps in (5.0, 10.0):
        specs.append(
            FundingSpec(
                "funding_extreme_reversal",
                "funding",
                {"threshold_bps": threshold_bps, "momentum_lookback": 72, "min_same_side_momentum_bps": 100.0},
            )
        )
    return specs


def run_walk_forward(
    candles_by_inst: dict[str, list[Candle]],
    funding_by_inst: dict[str, list[FundingPoint]],
    args: argparse.Namespace,
) -> list[WindowCandidate]:
    rows: list[WindowCandidate] = []
    specs = funding_specs()
    for inst_id, raw_candles in candles_by_inst.items():
        candles = tuples_to_float_candles(candles_to_tuples(raw_candles))
        funding = funding_by_inst.get(inst_id, [])
        if len(candles) < max(args.min_bars, args.train_bars + args.test_bars) or not funding:
            continue
        windows = build_windows(len(candles), args.train_bars, args.test_bars, args.step_bars)
        target_cache = {params_key(spec.params): funding_targets(candles, funding, spec.params) for spec in specs}
        for window in windows:
            ranked: list[WindowCandidate] = []
            for spec in specs:
                targets = target_cache[params_key(spec.params)]
                train = simulate_funding_segment(candles, funding, targets, window.train_start, window.train_end, args)
                if train.trades < args.min_train_trades:
                    continue
                if train.return_pct <= 0 or train.profit_factor < args.min_train_profit_factor:
                    continue
                score = train_selection_score(train)
                ranked.append(
                    WindowCandidate(
                        window=window,
                        rank=0,
                        inst_id=inst_id,
                        strategy=spec.name,
                        family=spec.family,
                        params=spec.params,
                        train=train,
                        test=train,
                        train_score=score,
                        passed=False,
                    )
                )
            ranked.sort(key=lambda item: item.train_score, reverse=True)
            for rank, candidate in enumerate(ranked[: max(0, args.select_top)], start=1):
                targets = target_cache[params_key(candidate.params)]
                test = simulate_funding_segment(candles, funding, targets, window.test_start, window.test_end, args)
                rows.append(
                    WindowCandidate(
                        window=window,
                        rank=rank,
                        inst_id=candidate.inst_id,
                        strategy=candidate.strategy,
                        family=candidate.family,
                        params=candidate.params,
                        train=candidate.train,
                        test=test,
                        train_score=candidate.train_score,
                        passed=is_test_pass(test, args),
                    )
                )
    return rows


def funding_targets(candles: list[Candle], funding: list[FundingPoint], params: dict[str, Any]) -> list[int]:
    targets = [0] * len(candles)
    threshold = float(params.get("threshold_bps", 0.0)) / 10000.0
    mode = str(params.get("mode") or "")
    funding_index = 0
    last_rate = 0.0
    closes = [float(candle.close) for candle in candles]
    for index in range(1, len(candles)):
        decision_ts = candles[index - 1].ts
        while funding_index < len(funding) and funding[funding_index].ts <= decision_ts:
            last_rate = funding[funding_index].realized_rate or funding[funding_index].rate
            funding_index += 1
        if abs(last_rate) < threshold:
            targets[index] = 0
            continue
        base_side = -1 if last_rate > 0 else 1
        if mode == "sentiment":
            base_side *= -1
        if "momentum_lookback" in params:
            lookback = int(params["momentum_lookback"])
            if index - 1 - lookback < 0 or closes[index - 1 - lookback] <= 0:
                targets[index] = 0
                continue
            momentum_bps = (closes[index - 1] / closes[index - 1 - lookback] - 1.0) * 10000.0
            if "max_against_momentum_bps" in params:
                max_against = float(params["max_against_momentum_bps"])
                if base_side > 0 and momentum_bps < -max_against:
                    targets[index] = 0
                    continue
                if base_side < 0 and momentum_bps > max_against:
                    targets[index] = 0
                    continue
            if "min_same_side_momentum_bps" in params:
                minimum = float(params["min_same_side_momentum_bps"])
                if last_rate > 0 and momentum_bps < minimum:
                    targets[index] = 0
                    continue
                if last_rate < 0 and momentum_bps > -minimum:
                    targets[index] = 0
                    continue
        targets[index] = base_side
    return targets


def simulate_funding_segment(
    candles: list[Candle],
    funding: list[FundingPoint],
    targets: list[int],
    start: int,
    end: int,
    args: argparse.Namespace,
) -> SegmentResult:
    if end <= start or not candles:
        return SegmentResult("", "", 0.0, 0.0, 0.0, 0, 0, 0, 0.0, 0.0, 0.0)
    cash = float(args.starting_equity)
    peak = cash
    max_dd = 0.0
    side = 0
    qty = 0.0
    entry = 0.0
    trade_pnls: list[float] = []
    fees = 0.0
    funding_pnl = 0.0
    wins = 0
    losses = 0
    cost_stress = max(0.0, float(getattr(args, "cost_stress_multiplier", 1.0)))
    fee_rate = float(args.fee_bps) * cost_stress / 10000.0
    slip = float(args.slippage_bps) * cost_stress / 10000.0
    funding_index = first_funding_index_after(funding, candles[max(0, start - 1)].ts)

    for index in range(max(1, start), end):
        while funding_index < len(funding) and funding[funding_index].ts <= candles[index].ts:
            if side and qty:
                px = candles[index].open
                notional = abs(qty * px)
                rate = funding[funding_index].realized_rate or funding[funding_index].rate
                payment = -side * notional * rate
                cash += payment
                funding_pnl += payment
            funding_index += 1

        desired = targets[index]
        open_px = candles[index].open
        if desired != side:
            if side:
                fill = open_px * (1.0 - slip if side > 0 else 1.0 + slip)
                pnl = side * qty * (fill - entry)
                fee = abs(qty * fill) * fee_rate
                cash += pnl - fee
                fees += fee
                net = pnl - fee
                trade_pnls.append(net)
                if net > 0:
                    wins += 1
                elif net < 0:
                    losses += 1
            side = desired
            qty = 0.0
            entry = 0.0
            if side and cash > 0:
                fill = open_px * (1.0 + slip if side > 0 else 1.0 - slip)
                notional = cash * float(args.margin_pct) / 100.0 * float(args.leverage)
                qty = notional / fill if fill > 0 else 0.0
                fee = abs(notional) * fee_rate
                cash -= fee
                fees += fee
                entry = fill

        equity = cash + (side * qty * (candles[index].close - entry) if side else 0.0)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)

    if side and end > start:
        fill = candles[end - 1].close * (1.0 - slip if side > 0 else 1.0 + slip)
        pnl = side * qty * (fill - entry)
        fee = abs(qty * fill) * fee_rate
        cash += pnl - fee
        fees += fee
        net = pnl - fee
        trade_pnls.append(net)
        if net > 0:
            wins += 1
        elif net < 0:
            losses += 1

    gross_profit = sum(value for value in trade_pnls if value > 0)
    gross_loss = abs(sum(value for value in trade_pnls if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    trades = len(trade_pnls)
    return SegmentResult(
        start=iso_time(candles[start].ts),
        end=iso_time(candles[end - 1].ts),
        return_pct=(cash / float(args.starting_equity) - 1.0) * 100.0 if args.starting_equity > 0 else 0.0,
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd,
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate_pct=wins / trades * 100.0 if trades else 0.0,
        fees=fees,
        funding_pnl=funding_pnl,
    )


def first_funding_index_after(funding: list[FundingPoint], ts: int) -> int:
    for index, point in enumerate(funding):
        if point.ts > ts:
            return index
    return len(funding)


def is_test_pass(test: SegmentResult, args: argparse.Namespace) -> bool:
    return (
        test.return_pct > 0
        and test.profit_factor >= args.min_test_profit_factor
        and test.trades >= args.min_test_trades
        and test.max_drawdown_pct <= args.max_test_drawdown_pct
    )


def aggregate_rows(rows: list[WindowCandidate], args: argparse.Namespace) -> list[AggregateCandidate]:
    grouped: dict[tuple[str, str, str, str], list[WindowCandidate]] = {}
    for row in rows:
        key = (row.inst_id, row.strategy, row.family, params_key(row.params))
        grouped.setdefault(key, []).append(row)
    aggregates: list[AggregateCandidate] = []
    for (inst_id, strategy, family, params), items in grouped.items():
        returns = [item.test.return_pct for item in items]
        pfs = [item.test.profit_factor for item in items if math.isfinite(item.test.profit_factor) and item.test.profit_factor < 900]
        drawdowns = [item.test.max_drawdown_pct for item in items]
        selected_windows = len(items)
        passed_windows = sum(1 for item in items if item.passed)
        pass_rate = passed_windows / selected_windows * 100.0 if selected_windows else 0.0
        total_return = compound_returns(returns)
        mean_return = statistics.fmean(returns) if returns else 0.0
        median_return = statistics.median(returns) if returns else 0.0
        worst_return = min(returns, default=0.0)
        mean_pf = statistics.fmean(pfs) if pfs else 999.0 if returns and min(returns) > 0 else 0.0
        mean_dd = statistics.fmean(drawdowns) if drawdowns else 0.0
        total_trades = sum(item.test.trades for item in items)
        score = total_return + 0.35 * mean_return + 0.15 * pass_rate - 0.7 * mean_dd + 0.05 * min(total_trades, 100)
        passed = (
            selected_windows >= max(2, min(3, args.select_top))
            and pass_rate >= 60.0
            and total_return > 0
            and median_return > 0
            and worst_return > -3.0
        )
        aggregates.append(
            AggregateCandidate(
                inst_id=inst_id,
                strategy=strategy,
                family=family,
                params=params,
                selected_windows=selected_windows,
                passed_windows=passed_windows,
                total_test_return_pct=total_return,
                mean_test_return_pct=mean_return,
                median_test_return_pct=median_return,
                worst_test_return_pct=worst_return,
                mean_test_profit_factor=mean_pf,
                mean_test_drawdown_pct=mean_dd,
                total_test_trades=total_trades,
                score=score,
                passed=passed,
            )
        )
    aggregates.sort(key=lambda item: item.score, reverse=True)
    return aggregates


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
        "mode": "read_only_funding_walk_forward",
        "instruments": inst_ids,
        "config": {
            "bar": args.bar,
            "limit": args.limit,
            "pages": args.pages,
            "fundingLimit": args.funding_limit,
            "fundingPages": args.funding_pages,
            "trainBars": args.train_bars,
            "testBars": args.test_bars,
            "stepBars": args.step_bars,
            "selectTop": args.select_top,
            "feeBps": args.fee_bps,
            "slippageBps": args.slippage_bps,
            "costStressMultiplier": args.cost_stress_multiplier,
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
        "regime_filter": "funding",
        "allowed_regimes": "funding",
        "train_start": row.train.start,
        "train_end": row.train.end,
        "test_start": row.test.start,
        "test_end": row.test.end,
        "train_return_pct": f"{row.train.return_pct:.8f}",
        "train_profit_factor": f"{row.train.profit_factor:.6f}",
        "train_max_drawdown_pct": f"{row.train.max_drawdown_pct:.8f}",
        "train_trades": row.train.trades,
        "train_score": f"{row.train_score:.8f}",
        "test_return_pct": f"{row.test.return_pct:.8f}",
        "test_profit_factor": f"{row.test.profit_factor:.6f}",
        "test_max_drawdown_pct": f"{row.test.max_drawdown_pct:.8f}",
        "test_trades": row.test.trades,
        "test_win_rate_pct": f"{row.test.win_rate_pct:.4f}",
        "test_fees": f"{row.test.fees:.8f}",
        "funding_pnl": f"{row.test.funding_pnl:.8f}",
        "passed": str(row.passed).lower(),
    }


def aggregate_to_dict(rank: int, item: AggregateCandidate) -> dict[str, Any]:
    return {
        "rank": rank,
        "inst_id": item.inst_id,
        "strategy": item.strategy,
        "family": item.family,
        "params": item.params,
        "regime_filter": "funding",
        "allowed_regimes": "funding",
        "selected_windows": item.selected_windows,
        "passed_windows": item.passed_windows,
        "pass_rate_pct": f"{item.passed_windows / item.selected_windows * 100.0 if item.selected_windows else 0.0:.4f}",
        "total_test_return_pct": f"{item.total_test_return_pct:.8f}",
        "mean_test_return_pct": f"{item.mean_test_return_pct:.8f}",
        "median_test_return_pct": f"{item.median_test_return_pct:.8f}",
        "worst_test_return_pct": f"{item.worst_test_return_pct:.8f}",
        "mean_test_profit_factor": f"{item.mean_test_profit_factor:.6f}",
        "mean_test_drawdown_pct": f"{item.mean_test_drawdown_pct:.8f}",
        "total_test_trades": item.total_test_trades,
        "score": f"{item.score:.8f}",
        "passed": str(item.passed).lower(),
    }


def summary_payload(rows: list[WindowCandidate], aggregates: list[AggregateCandidate]) -> dict[str, Any]:
    returns = [row.test.return_pct for row in rows]
    return {
        "selectedRows": len(rows),
        "passedRows": sum(1 for row in rows if row.passed),
        "uniqueAggregates": len(aggregates),
        "passedAggregates": sum(1 for item in aggregates if item.passed),
        "medianSelectedTestReturnPct": statistics.median(returns) if returns else 0.0,
        "meanSelectedTestReturnPct": statistics.fmean(returns) if returns else 0.0,
        "bestAggregateReturnPct": max((item.total_test_return_pct for item in aggregates), default=0.0),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Funding Research",
        "",
        "Read-only walk-forward validation over funding-rate-aware strategies. Signals use only prior funding events and prior price bars.",
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
        "| Rank | Instrument | Strategy | Windows | Pass % | Total Test Ret % | Median Test Ret % | Worst Test Ret % | Passed |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["aggregates"][:25]:
        lines.append(
            f"| {row['rank']} | {row['inst_id']} | {row['strategy']} | {row['selected_windows']} | "
            f"{row['pass_rate_pct']} | {row['total_test_return_pct']} | {row['median_test_return_pct']} | "
            f"{row['worst_test_return_pct']} | {row['passed']} |"
        )
    return "\n".join(lines) + "\n"


def print_summary(rows: list[WindowCandidate], aggregates: list[AggregateCandidate]) -> None:
    summary = summary_payload(rows, aggregates)
    print(
        "selected_rows={selectedRows} passed_rows={passedRows} "
        "aggregates={uniqueAggregates} passed_aggregates={passedAggregates} "
        "median_test={medianSelectedTestReturnPct:.6f}%".format(**summary)
    )


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def tuples_to_float_candles(values: list[tuple[int, float, float, float, float]]) -> list[Candle]:
    return [Candle(ts, open_, high, low, close, 0.0) for ts, open_, high, low, close in values]


def params_key(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True)


def iso_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
