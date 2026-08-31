from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import (
    BAR_MS,
    Candle,
    GridBacktestConfig,
    fetch_okx_candle_rows,
    parse_okx_candles,
    plain,
    run_grid_backtest,
)
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_ROOT = PROJECT_ROOT / "reports" / "portfolio"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "walk_forward"

ROW_FIELDS = [
    "report_dir",
    "generated_at",
    "inst_id",
    "decision_action",
    "train_return_pct",
    "train_profit_factor",
    "train_max_drawdown_pct",
    "train_risk_events",
    "test_bars",
    "test_start",
    "test_end",
    "test_return_pct",
    "test_profit_factor",
    "test_max_drawdown_pct",
    "test_fills",
    "test_risk_events",
    "fees",
    "selected_trend_filter",
    "market_regime_filter",
    "note",
]


@dataclass(slots=True)
class AuditRow:
    report_dir: str
    generated_at: str
    inst_id: str
    decision_action: str
    train_return_pct: Decimal
    train_profit_factor: Decimal
    train_max_drawdown_pct: Decimal
    train_risk_events: int
    test_bars: int
    test_start: str
    test_end: str
    test_return_pct: Decimal
    test_profit_factor: Decimal
    test_max_drawdown_pct: Decimal
    test_fills: int
    test_risk_events: int
    fees: Decimal
    selected_trend_filter: str
    market_regime_filter: str
    note: str


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    reports = selected_reports(
        report_dirs=args.report_dir,
        limit=args.limit,
        only_with_targets=not args.include_empty,
    )
    client = OkxRestClient()
    rows: list[AuditRow] = []
    for report_dir in reports:
        rows.extend(audit_report(client, report_dir, args))
    write_outputs(output_dir, rows, args)
    print(f"walk_forward_report={output_dir}")
    print_summary(rows)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a read-only walk-forward audit from historical portfolio reports. "
            "Each report's frozen runtime config is tested only on candles after its generatedAt timestamp."
        )
    )
    parser.add_argument(
        "--report-dir",
        action="append",
        default=[],
        help="Portfolio report directory to audit. Can be repeated. Defaults to recent reports.",
    )
    parser.add_argument("--limit", type=int, default=24, help="Number of recent report directories to inspect when --report-dir is omitted.")
    parser.add_argument("--test-bars", type=int, default=300, help="Out-of-sample candle bars after each report timestamp.")
    parser.add_argument("--bar", default="1m", choices=list(BAR_MS), help="Candle bar for out-of-sample validation.")
    parser.add_argument("--include-empty", action="store_true", help="Include reports with no runtime configs in the audit set.")
    parser.add_argument("--output-dir", default="", help="Output directory. Relative paths are under reports/walk_forward/.")
    parser.add_argument("--sleep", type=float, default=0.15, help="Delay between public OKX candle requests.")
    return parser.parse_args()


def selected_reports(*, report_dirs: list[str], limit: int, only_with_targets: bool) -> list[Path]:
    if report_dirs:
        paths = [resolve_report_dir(value) for value in report_dirs]
    else:
        paths = [path for path in REPORT_ROOT.iterdir() if path.is_dir()] if REPORT_ROOT.exists() else []
        paths.sort(key=lambda item: generated_at_ms(item) or 0, reverse=True)
        paths = paths[: max(0, limit)]
    if only_with_targets:
        paths = [path for path in paths if list_runtime_paths(path)]
    paths.sort(key=lambda item: generated_at_ms(item) or 0)
    return paths


def resolve_report_dir(value: str) -> Path:
    path = Path(value)
    if path.exists():
        return path.resolve()
    candidate = REPORT_ROOT / value
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(f"portfolio report not found: {value}")


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def audit_report(client: OkxRestClient, report_dir: Path, args: argparse.Namespace) -> list[AuditRow]:
    generated_ms = generated_at_ms(report_dir)
    if generated_ms is None:
        return []
    candidates = load_candidates(report_dir)
    targets = load_targets(report_dir)
    actions = load_actions(report_dir)
    rows = load_score_rows(report_dir)
    results: list[AuditRow] = []
    runtime_paths = list_runtime_paths(report_dir)
    for runtime_path in runtime_paths:
        runtime = read_json(runtime_path)
        inst_id = str(runtime.get("instId") or runtime_path.stem.upper().replace("_", "-"))
        candidate = candidates.get(inst_id, {})
        target = targets.get(inst_id, {})
        score_row = rows.get(inst_id, {})
        test_candles = fetch_forward_candles(
            client,
            inst_id=inst_id,
            bar=args.bar,
            after_ms=generated_ms,
            limit=args.test_bars,
        )
        time.sleep(max(0.0, args.sleep))
        if len(test_candles) < 30:
            results.append(
                empty_row(
                    report_dir=report_dir,
                    generated_ms=generated_ms,
                    inst_id=inst_id,
                    action=actions.get(inst_id, ""),
                    target=target,
                    score_row=score_row,
                    runtime=runtime,
                    note=f"not enough forward candles: {len(test_candles)}",
                )
            )
            continue
        config = grid_config_from_runtime(runtime, candidate, test_candles, args.bar, args.test_bars)
        result, _, _ = run_grid_backtest(test_candles, config)
        results.append(
            AuditRow(
                report_dir=report_dir.name,
                generated_at=iso_time(generated_ms),
                inst_id=inst_id,
                decision_action=actions.get(inst_id, ""),
                train_return_pct=dec(target.get("total_return_pct", score_row.get("total_return_pct"))),
                train_profit_factor=dec(target.get("profit_factor", score_row.get("profit_factor"))),
                train_max_drawdown_pct=dec(target.get("max_drawdown_pct", score_row.get("max_drawdown_pct"))),
                train_risk_events=int(dec(target.get("risk_events", score_row.get("risk_events")))),
                test_bars=result.bars,
                test_start=result.start_time,
                test_end=result.end_time,
                test_return_pct=result.total_return_pct,
                test_profit_factor=result.profit_factor,
                test_max_drawdown_pct=result.max_drawdown_pct,
                test_fills=result.fills,
                test_risk_events=result.risk_events,
                fees=result.fees,
                selected_trend_filter=str(runtime.get("trendFilter", "")),
                market_regime_filter=str(runtime.get("marketRegimeFilter", "")),
                note="",
            )
        )
    return results


def fetch_forward_candles(
    client: OkxRestClient,
    *,
    inst_id: str,
    bar: str,
    after_ms: int,
    limit: int,
) -> list[Candle]:
    # OKX `after` returns candles older than the supplied timestamp. Requesting
    # from report_time + validation_window gives the contiguous out-of-sample
    # window immediately after the report, instead of a later future segment.
    bar_ms = BAR_MS.get(bar, BAR_MS["1m"])
    end_ms = after_ms + max(1, limit) * bar_ms
    response = client.request(
        "GET",
        "/api/v5/market/history-candles",
        params={"instId": inst_id, "bar": bar, "limit": str(max(1, min(limit, 300))), "after": str(end_ms)},
    )
    candles = [
        candle
        for candle in parse_okx_candles(response.get("data", []))
        if after_ms <= candle.ts < end_ms
    ]
    return candles[:limit]


def grid_config_from_runtime(
    runtime: dict[str, Any],
    candidate: dict[str, Any],
    candles: list[Candle],
    bar: str,
    limit: int,
) -> GridBacktestConfig:
    first = candles[0].close
    lower = dec(runtime.get("lower"))
    upper = dec(runtime.get("upper"))
    if lower <= 0 or upper <= lower or first < lower or first > upper:
        width_bps = Decimal("1200")
        if lower > 0 and upper > lower:
            midpoint = (lower + upper) / Decimal("2")
            if midpoint > 0:
                width_bps = (upper - lower) / midpoint * Decimal("10000")
        half = width_bps / Decimal("20000")
        tick = dec(candidate.get("tick_sz"), Decimal("0.0001"))
        lower = round_to_tick(first * (Decimal("1") - half), tick)
        upper = round_to_tick(first * (Decimal("1") + half), tick)

    return GridBacktestConfig(
        inst_id=str(runtime.get("instId", "")),
        bar=bar,
        limit=limit,
        lower=lower,
        upper=upper,
        leverage=dec(runtime.get("leverage"), Decimal("1")),
        grid_bps=dec(runtime.get("gridBps"), Decimal("10")),
        soft_bps=dec(runtime.get("softBps"), Decimal("35")),
        hard_bps=dec(runtime.get("hardBps"), Decimal("60")),
        order_sz=dec(runtime.get("orderSz"), Decimal("1")),
        max_position=dec(runtime.get("maxPosition"), Decimal("1")),
        max_open_orders_per_side=int(dec(runtime.get("maxOpenOrdersPerSide"), Decimal("5"))),
        max_actions_per_bar=int(dec(runtime.get("maxActionsPerCycle"), Decimal("4"))),
        mode=str(runtime.get("mode", "adaptive")),
        adaptive_width_bps=dec(runtime.get("adaptiveWidthBps"), Decimal("420")),
        adaptive_min_width_bps=dec(runtime.get("adaptiveMinWidthBps"), Decimal("260")),
        adaptive_max_width_bps=dec(runtime.get("adaptiveMaxWidthBps"), Decimal("1200")),
        adaptive_vol_multiplier=dec(runtime.get("adaptiveVolMultiplier"), Decimal("12")),
        range_drift_mode=str(runtime.get("rangeDriftMode", "cooldown")),
        range_drift_weight_bps=dec(runtime.get("rangeDriftWeightBps"), Decimal("2500")),
        range_drift_max_bps=dec(runtime.get("rangeDriftMaxBps"), Decimal("250")),
        one_way_open=bool(runtime.get("oneWayOpen", False)),
        starting_equity=Decimal("100"),
        ct_val=dec(candidate.get("ct_val"), Decimal("1")),
        tick_sz=dec(candidate.get("tick_sz"), Decimal("0.0001")),
        lot_sz=dec(candidate.get("lot_sz"), Decimal("1")),
        min_sz=dec(candidate.get("min_sz"), Decimal("1")),
        min_tp_bps=dec(runtime.get("minTpBps"), Decimal("30")),
        total_loss_sl_pct=dec(runtime.get("totalLossSlPct"), Decimal("4")),
        total_loss_sl_cap=dec(runtime.get("totalLossSlCap"), Decimal("0.8")),
        position_loss_sl_bps=dec(runtime.get("positionLossSlBps"), Decimal("700")),
        risk_cooldown_bars=cooldown_seconds_to_bars(dec(runtime.get("riskCooldown"), Decimal("60")), bar),
        regime_filter=str(runtime.get("regimeFilter", "off")),
        regime_bar=str(runtime.get("regimeBar", "15m")),
        regime_short_ma=int(dec(runtime.get("regimeShortMa"), Decimal("5"))),
        regime_long_ma=int(dec(runtime.get("regimeLongMa"), Decimal("20"))),
        regime_diff_bps=dec(runtime.get("regimeDiffBps"), Decimal("50")),
        regime_confirm_bars=int(dec(runtime.get("regimeConfirmBars"), Decimal("3"))),
        trend_filter=str(runtime.get("trendFilter", "off")),
        trend_lookback=int(dec(runtime.get("trendLookback"), Decimal("8"))),
        trend_threshold_bps=dec(runtime.get("trendThresholdBps"), Decimal("70")),
        market_regime_filter="off",
        market_regime_model_path="",
        market_regime_min_confidence=dec(runtime.get("marketRegimeMinConfidence"), Decimal("0.52")),
        market_regime_mixed_policy=str(runtime.get("marketRegimeMixedPolicy", "price_anchor")),
    )


def empty_row(
    *,
    report_dir: Path,
    generated_ms: int,
    inst_id: str,
    action: str,
    target: dict[str, Any],
    score_row: dict[str, Any],
    runtime: dict[str, Any],
    note: str,
) -> AuditRow:
    return AuditRow(
        report_dir=report_dir.name,
        generated_at=iso_time(generated_ms),
        inst_id=inst_id,
        decision_action=action,
        train_return_pct=dec(target.get("total_return_pct", score_row.get("total_return_pct"))),
        train_profit_factor=dec(target.get("profit_factor", score_row.get("profit_factor"))),
        train_max_drawdown_pct=dec(target.get("max_drawdown_pct", score_row.get("max_drawdown_pct"))),
        train_risk_events=int(dec(target.get("risk_events", score_row.get("risk_events")))),
        test_bars=0,
        test_start="",
        test_end="",
        test_return_pct=Decimal("0"),
        test_profit_factor=Decimal("0"),
        test_max_drawdown_pct=Decimal("0"),
        test_fills=0,
        test_risk_events=0,
        fees=Decimal("0"),
        selected_trend_filter=str(runtime.get("trendFilter", "")),
        market_regime_filter=str(runtime.get("marketRegimeFilter", "")),
        note=note,
    )


def write_outputs(output_dir: Path, rows: list[AuditRow], args: argparse.Namespace) -> None:
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "walk_forward_from_frozen_portfolio_reports",
        "bar": args.bar,
        "testBars": args.test_bars,
        "notes": [
            "Uses each report's generatedAt as the decision timestamp.",
            "Uses only runtime configs already present in the report directory.",
            "Tests only candles at or after generatedAt.",
            "Disables ML regime model during validation unless the frozen runtime already encoded deterministic rules; this avoids retraining or reselecting from test data.",
        ],
        "summary": summary_payload(rows),
        "rows": [row_to_dict(row) for row in rows],
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output_dir / "rows.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ROW_FIELDS)
        writer.writeheader()
        for row in rows:
            row_dict = row_to_dict(row)
            writer.writerow({field: row_dict.get(field, "") for field in ROW_FIELDS})
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def summary_payload(rows: list[AuditRow]) -> dict[str, Any]:
    tested = [row for row in rows if row.test_bars > 0]
    returns = [float(row.test_return_pct) for row in tested]
    profitable = [row for row in tested if row.test_return_pct > 0 and row.test_profit_factor >= 1]
    return {
        "reports": len({row.report_dir for row in rows}),
        "items": len(rows),
        "testedItems": len(tested),
        "profitableItems": len(profitable),
        "profitableRatePct": (len(profitable) / len(tested) * 100.0) if tested else 0.0,
        "medianReturnPct": statistics.median(returns) if returns else 0.0,
        "meanReturnPct": statistics.fmean(returns) if returns else 0.0,
        "minReturnPct": min(returns) if returns else 0.0,
        "maxReturnPct": max(returns) if returns else 0.0,
        "totalFills": sum(row.test_fills for row in tested),
        "totalRiskEvents": sum(row.test_risk_events for row in tested),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Portfolio Walk-Forward Audit",
        "",
        "Read-only sample-out validation from frozen portfolio reports.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Reports | {summary['reports']} |",
        f"| Tested items | {summary['testedItems']} |",
        f"| Profitable items | {summary['profitableItems']} |",
        f"| Profitable rate | {summary['profitableRatePct']:.2f}% |",
        f"| Median return | {summary['medianReturnPct']:.6f}% |",
        f"| Mean return | {summary['meanReturnPct']:.6f}% |",
        f"| Min return | {summary['minReturnPct']:.6f}% |",
        f"| Max return | {summary['maxReturnPct']:.6f}% |",
        f"| Total fills | {summary['totalFills']} |",
        f"| Total risk events | {summary['totalRiskEvents']} |",
        "",
        "## Rows",
        "",
        "| Report | Instrument | Train Return % | Test Return % | Test PF | Fills | Risk Events | Note |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {report} | {inst} | {train_ret} | {test_ret} | {pf} | {fills} | {risk} | {note} |".format(
                report=row["report_dir"],
                inst=row["inst_id"],
                train_ret=row["train_return_pct"],
                test_ret=row["test_return_pct"],
                pf=row["test_profit_factor"],
                fills=row["test_fills"],
                risk=row["test_risk_events"],
                note=row["note"],
            )
        )
    return "\n".join(lines) + "\n"


def print_summary(rows: list[AuditRow]) -> None:
    summary = summary_payload(rows)
    print(
        "tested={testedItems} profitable={profitableItems} profitable_rate={profitableRatePct:.2f}% "
        "median_return={medianReturnPct:.6f}% mean_return={meanReturnPct:.6f}% risk_events={totalRiskEvents}".format(
            **summary
        )
    )


def list_runtime_paths(report_dir: Path) -> list[Path]:
    runtime_dir = report_dir / "runtime_configs"
    if not runtime_dir.exists():
        return []
    return sorted(runtime_dir.glob("*.json"))


def load_candidates(report_dir: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(report_dir / "candidates.json")
    return {str(item.get("inst_id", "")): item for item in payload.get("candidates", []) if item.get("inst_id")}


def load_targets(report_dir: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(report_dir / "rebalance_plan.json")
    return {str(item.get("inst_id", "")): item for item in payload.get("targets", []) if item.get("inst_id")}


def load_actions(report_dir: Path) -> dict[str, str]:
    payload = read_json(report_dir / "rebalance_plan.json")
    return {str(item.get("inst_id", "")): str(item.get("action", "")) for item in payload.get("actions", []) if item.get("inst_id")}


def load_score_rows(report_dir: Path) -> dict[str, dict[str, Any]]:
    path = report_dir / "scores.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as file:
        return {str(row.get("inst_id", "")): row for row in csv.DictReader(file) if row.get("inst_id")}


def generated_at_ms(report_dir: Path) -> int | None:
    payload = read_json(report_dir / "candidates.json")
    generated_at = str(payload.get("generatedAt", ""))
    if not generated_at:
        payload = read_json(report_dir / "rebalance_plan.json")
        generated_at = str(payload.get("generatedAt", ""))
    if not generated_at:
        return None
    if generated_at.endswith("Z"):
        generated_at = generated_at[:-1] + "+00:00"
    try:
        return int(datetime.fromisoformat(generated_at).timestamp() * 1000)
    except ValueError:
        return None


def row_to_dict(row: AuditRow) -> dict[str, Any]:
    return {key: value_to_json(value) for key, value in asdict(row).items()}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def value_to_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    return value


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def cooldown_seconds_to_bars(seconds: Decimal, bar: str) -> int:
    if seconds <= 0:
        return 0
    bar_seconds = Decimal(BAR_MS.get(bar, BAR_MS["1m"])) / Decimal("1000")
    return max(1, int((seconds / bar_seconds).to_integral_value(rounding=ROUND_UP)))


def iso_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
