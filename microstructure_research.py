from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_ROOT = PROJECT_ROOT / "data" / "microstructure"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "microstructure_research"
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


@dataclass(slots=True)
class MicroResult:
    inst_id: str
    strategy: str
    params: dict[str, Any]
    samples: int
    trades: int
    total_return_pct: float
    mean_return_pct: float
    median_return_pct: float
    worst_return_pct: float
    profit_factor: float
    max_drawdown_pct: float
    hit_rate_pct: float
    passed: bool
    score: float


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_records(Path(args.input_root))
    results = evaluate_records(records, args)
    write_outputs(output_dir, records, results, args)
    print(f"microstructure_research_report={output_dir}")
    print_summary(records, results)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline research over collected public order-book/trade-flow snapshots.")
    parser.add_argument("--input-root", default=str(INPUT_ROOT))
    parser.add_argument("--min-samples", type=int, default=200)
    parser.add_argument("--threshold", type=float, default=0.2)
    parser.add_argument("--fee-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    parser.add_argument("--cost-stress-multiplier", type=float, default=1.5)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def load_records(input_root: Path) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {}
    if not input_root.exists():
        return records
    for path in sorted(input_root.glob("*/*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not row.get("ok", False):
                continue
            inst_id = str(row.get("instId", ""))
            if not inst_id:
                continue
            records.setdefault(inst_id, []).append(row)
    for rows in records.values():
        rows.sort(key=lambda item: int(float(item.get("capturedTs") or 0)))
    return records


def evaluate_records(records: dict[str, list[dict[str, Any]]], args: argparse.Namespace) -> list[MicroResult]:
    results: list[MicroResult] = []
    for inst_id, rows in records.items():
        if len(rows) < max(2, int(args.min_samples)):
            continue
        for strategy, feature in (
            ("book_imbalance", "book.imbalance_10"),
            ("trade_flow", "trades.imbalance"),
            ("book_and_trade_flow", "combined"),
        ):
            result = evaluate_strategy(inst_id, rows, strategy, feature, args)
            results.append(result)
    results.sort(key=lambda item: item.score, reverse=True)
    return results


def evaluate_strategy(inst_id: str, rows: list[dict[str, Any]], strategy: str, feature: str, args: argparse.Namespace) -> MicroResult:
    threshold = abs(float(args.threshold))
    cost_bps = (float(args.fee_bps) + float(args.slippage_bps)) * max(0.0, float(args.cost_stress_multiplier))
    trade_returns: list[float] = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for index in range(len(rows) - 1):
        side = signal_side(rows[index], feature, threshold)
        if side == 0:
            continue
        start = mid_price(rows[index])
        end = mid_price(rows[index + 1])
        if start <= 0 or end <= 0:
            continue
        ret_pct = side * (end / start - 1.0) * 100.0 - cost_bps / 100.0
        trade_returns.append(ret_pct)
        equity *= 1.0 + ret_pct / 100.0
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    gross_profit = sum(value for value in trade_returns if value > 0)
    gross_loss = abs(sum(value for value in trade_returns if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    total_return = (equity - 1.0) * 100.0
    hit_rate = sum(1 for value in trade_returns if value > 0) / len(trade_returns) * 100.0 if trade_returns else 0.0
    score = total_return + 0.3 * hit_rate - 0.8 * max_dd + 0.05 * min(len(trade_returns), 500)
    passed = (
        len(trade_returns) >= max(20, int(args.min_samples) // 4)
        and total_return > 0
        and profit_factor >= 1.05
        and hit_rate >= 52.0
        and max_dd <= 8.0
    )
    return MicroResult(
        inst_id=inst_id,
        strategy=strategy,
        params={"threshold": threshold, "fee_bps": args.fee_bps, "slippage_bps": args.slippage_bps, "cost_stress_multiplier": args.cost_stress_multiplier},
        samples=len(rows),
        trades=len(trade_returns),
        total_return_pct=total_return,
        mean_return_pct=statistics.fmean(trade_returns) if trade_returns else 0.0,
        median_return_pct=statistics.median(trade_returns) if trade_returns else 0.0,
        worst_return_pct=min(trade_returns, default=0.0),
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd,
        hit_rate_pct=hit_rate,
        passed=passed,
        score=score,
    )


def signal_side(row: dict[str, Any], feature: str, threshold: float) -> int:
    if feature == "combined":
        book = nested_float(row, "features.book.imbalance_10")
        trades = nested_float(row, "features.trades.imbalance")
        if book >= threshold and trades >= threshold:
            return 1
        if book <= -threshold and trades <= -threshold:
            return -1
        return 0
    value = nested_float(row, f"features.{feature}")
    if value >= threshold:
        return 1
    if value <= -threshold:
        return -1
    return 0


def mid_price(row: dict[str, Any]) -> float:
    value = nested_float(row, "features.book.mid")
    if value > 0:
        return value
    bid = nested_float(row, "ticker.bidPx")
    ask = nested_float(row, "ticker.askPx")
    return (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0


def nested_float(row: dict[str, Any], path: str) -> float:
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict):
            return 0.0
        current = current.get(part)
    try:
        return float(current)
    except (TypeError, ValueError):
        return 0.0


def write_outputs(output_dir: Path, records: dict[str, list[dict[str, Any]]], results: list[MicroResult], args: argparse.Namespace) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [result_to_row(index + 1, result) for index, result in enumerate(results)]
    summary = {
        "instrumentCount": len(records),
        "totalSnapshots": sum(len(items) for items in records.values()),
        "minSamples": args.min_samples,
        "testedCandidates": len(results),
        "passedCandidates": sum(1 for result in results if result.passed),
        "status": "ready" if results else "insufficient_data",
    }
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_microstructure_research",
        "summary": summary,
        "config": {
            "threshold": args.threshold,
            "feeBps": args.fee_bps,
            "slippageBps": args.slippage_bps,
            "costStressMultiplier": args.cost_stress_multiplier,
        },
        "aggregates": rows,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output_dir / "aggregate.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=AGG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def result_to_row(rank: int, result: MicroResult) -> dict[str, Any]:
    return {
        "rank": rank,
        "inst_id": result.inst_id,
        "strategy": result.strategy,
        "family": "microstructure",
        "params": json.dumps(result.params, sort_keys=True),
        "regime_filter": "microstructure",
        "allowed_regimes": "microstructure",
        "selected_windows": result.samples,
        "passed_windows": int(round(result.hit_rate_pct / 100.0 * result.trades)),
        "pass_rate_pct": f"{result.hit_rate_pct:.4f}",
        "total_test_return_pct": f"{result.total_return_pct:.8f}",
        "mean_test_return_pct": f"{result.mean_return_pct:.8f}",
        "median_test_return_pct": f"{result.median_return_pct:.8f}",
        "worst_test_return_pct": f"{result.worst_return_pct:.8f}",
        "mean_test_profit_factor": f"{result.profit_factor:.6f}",
        "mean_test_drawdown_pct": f"{result.max_drawdown_pct:.8f}",
        "total_test_trades": result.trades,
        "score": f"{result.score:.8f}",
        "passed": str(result.passed).lower(),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Microstructure Research",
        "",
        "Offline research over collected public order-book and trade-flow snapshots.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Instruments | {summary['instrumentCount']} |",
        f"| Total snapshots | {summary['totalSnapshots']} |",
        f"| Min samples per instrument | {summary['minSamples']} |",
        f"| Tested candidates | {summary['testedCandidates']} |",
        f"| Passed candidates | {summary['passedCandidates']} |",
        f"| Status | {summary['status']} |",
        "",
    ]
    if summary["status"] == "insufficient_data":
        lines.append("Not enough historical snapshots yet. Keep collecting before using this research path for candidate gates.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "## Top Aggregates",
            "",
            "| Rank | Instrument | Strategy | Samples | Trades | Return % | PF | DD % | Passed |",
            "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in payload["aggregates"][:25]:
        lines.append(
            f"| {row['rank']} | {row['inst_id']} | {row['strategy']} | {row['selected_windows']} | "
            f"{row['total_test_trades']} | {row['total_test_return_pct']} | {row['mean_test_profit_factor']} | "
            f"{row['mean_test_drawdown_pct']} | {row['passed']} |"
        )
    return "\n".join(lines) + "\n"


def print_summary(records: dict[str, list[dict[str, Any]]], results: list[MicroResult]) -> None:
    print(
        "instruments={insts} snapshots={snapshots} candidates={candidates} passed={passed}".format(
            insts=len(records),
            snapshots=sum(len(items) for items in records.values()),
            candidates=len(results),
            passed=sum(1 for result in results if result.passed),
        )
    )


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
