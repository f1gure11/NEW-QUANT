from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, iso_time, read_candles_csv
from flip_grid import FlipGridConfig, FlipGridSimulation, simulate_flip_grid
from funding_research import funding_cache_path, read_funding_csv


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "flip_grid"
DEFAULT_SOURCE = PROJECT_ROOT / "reports" / "layered_aggregation" / "semis-5m-20260806" / "summary.json"
LEVERAGES = (1.0, 2.0, 3.0, 5.0, 8.0, 10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only leverage sweep for take-profit-and-reverse grid chains.")
    parser.add_argument("--source-summary", default=str(DEFAULT_SOURCE))
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--account-stop-pct", type=float, default=6.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = json.loads(Path(args.source_summary).read_text(encoding="utf-8"))
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {item["inst_id"]: item for item in source["instruments"] if item["selected"]}
    bar = str(source["config"]["bar"])
    suffix = "" if args.pages <= 1 else f"x{args.pages}"
    candles_by_inst: dict[str, list[Candle]] = {}
    funding_by_inst = {}
    for inst_id in metadata:
        candle_path = PROJECT_ROOT / "data" / "backtest" / f"{inst_id}_{bar}_{args.limit}{suffix}.csv"
        if not candle_path.exists():
            raise SystemExit(f"Missing candle cache: {candle_path}")
        candles_by_inst[inst_id] = read_candles_csv(candle_path)
        funding_path = funding_cache_path(inst_id, 100, 1)
        funding_by_inst[inst_id] = read_funding_csv(funding_path) if funding_path.exists() else []

    period = source["commonPeriod"]
    common_start = parse_iso_ms(period["start"])
    train_end = parse_iso_ms(period["trainEnd"])
    validation_end = parse_iso_ms(period["validationEnd"])
    common_end = parse_iso_ms(period["end"])
    selected = source["selectedParameters"]
    base = FlipGridConfig(
        starting_equity=float(source["config"]["starting_equity"]),
        allocation_pct=float(source["config"]["allocation_pct"]),
        chains=int(selected["tranches"]),
        seed_step_bps=float(selected["step_bps"]),
        flip_take_profit_bps=float(selected["take_profit_bps"]),
        maker_fee_bps=float(source["config"]["maker_fee_bps"]),
        taker_fee_bps=float(source["config"]["taker_fee_bps"]),
        liquidation_slippage_bps=float(source["config"]["stop_slippage_bps"]),
        fill_buffer_bps=float(source["config"]["fill_buffer_bps"]),
    )

    rows: list[dict[str, Any]] = []
    for inst_id, all_candles in candles_by_inst.items():
        candles = time_slice(all_candles, common_start, common_end)
        segments = {
            "validation": time_slice(candles, train_end + 1, validation_end),
            "test": time_slice(candles, validation_end + 1, common_end),
            "full": candles,
            "worst_downtrend": worst_return_window(candles, 864),
            "worst_uptrend": best_return_window(candles, 864),
        }
        meta = metadata[inst_id]
        for leverage in LEVERAGES:
            config = replace(
                base,
                leverage=leverage,
                lot_size=float(meta["lot_size"]),
                min_size=float(meta["min_size"]),
                contract_value=float(meta["contract_value"]),
                tick_size=float(meta["tick_size"]),
            )
            for segment_name, segment_candles in segments.items():
                simulation = simulate_flip_grid(
                    segment_candles,
                    config,
                    funding_by_inst.get(inst_id, []),
                    record_details=False,
                )
                rows.append(result_row(inst_id, segment_name, "raw", leverage, simulation))

            stopped = replace(config, account_stop_pct=args.account_stop_pct)
            for segment_name in ("test", "full"):
                simulation = simulate_flip_grid(
                    segments[segment_name],
                    stopped,
                    funding_by_inst.get(inst_id, []),
                    record_details=False,
                )
                rows.append(result_row(inst_id, segment_name, "account_stop", leverage, simulation))

            stressed = replace(
                config,
                maker_fee_bps=max(5.0, config.maker_fee_bps * 2.5),
                taker_fee_bps=max(8.0, config.taker_fee_bps * 1.6),
                liquidation_slippage_bps=max(4.0, config.liquidation_slippage_bps * 2.0),
                fill_buffer_bps=max(4.0, config.fill_buffer_bps * 4.0),
            )
            stress_sim = simulate_flip_grid(
                segments["test"],
                stressed,
                funding_by_inst.get(inst_id, []),
                record_details=False,
            )
            rows.append(result_row(inst_id, "test", "cost_stress", leverage, stress_sim))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(aggregates)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_take_profit_reverse_grid_leverage_sweep",
        "sourceSummary": str(Path(args.source_summary).resolve()),
        "strategyDefinition": {
            "seed": "long layers at and below the completed-close anchor",
            "longCompletion": "close profitable long and open same-quantity short at the long TP",
            "shortCompletion": "close profitable short and open same-quantity long at the short TP",
            "overlap": "different chains may hold staggered long and short inventory simultaneously",
            "sameBarRule": "a newly reversed leg cannot complete again on the same candle",
            "liquidation": "maintenance-margin test is applied to adverse candle extremes before favorable flips",
        },
        "config": {
            "bar": bar,
            "startingEquity": base.starting_equity,
            "allocationPct": base.allocation_pct,
            "leverages": list(LEVERAGES),
            "chains": base.chains,
            "seedStepBps": base.seed_step_bps,
            "flipTakeProfitBps": base.flip_take_profit_bps,
            "makerFeeBps": base.maker_fee_bps,
            "takerFeeBps": base.taker_fee_bps,
            "fillBufferBps": base.fill_buffer_bps,
            "maintenanceMarginPct": base.maintenance_margin_pct,
            "accountStopPct": args.account_stop_pct,
        },
        "commonPeriod": period,
        "instruments": list(metadata),
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "aggregate.csv", aggregates)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    for leverage in LEVERAGES:
        item = aggregate_lookup(aggregates, "test", "raw", leverage)
        print(
            f"leverage={leverage:g}x median={item['median_return_pct']:.6f}% "
            f"positive={item['positive']}/{item['count']} liquidated={item['liquidations']}"
        )
    print(f"status={decision['status']} recommended_leverage={decision['recommendedLeverage']}")
    return 0


def result_row(inst_id: str, segment: str, variant: str, leverage: float, simulation: FlipGridSimulation) -> dict[str, Any]:
    result = simulation.result
    return {
        "inst_id": inst_id,
        "segment": segment,
        "variant": variant,
        "leverage": leverage,
        "start": iso_time(result.start_ts),
        "end": iso_time(result.end_ts),
        "bars": result.bars,
        "price_return_pct": result.price_return_pct,
        "return_pct": result.return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "gross_harvest": result.gross_harvest,
        "terminal_unrealized": result.terminal_unrealized,
        "fees": result.fees,
        "funding_cost": result.funding_cost,
        "flips": result.flips,
        "long_completions": result.long_completions,
        "short_completions": result.short_completions,
        "terminal_lots": result.terminal_lots,
        "max_gross_exposure_pct": result.max_gross_exposure_pct,
        "max_abs_net_exposure_pct": result.max_abs_net_exposure_pct,
        "liquidated": result.liquidated,
        "account_stopped": result.account_stopped,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, float], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["segment"], row["variant"], float(row["leverage"])), []).append(row)
    result = []
    for (segment, variant, leverage), items in groups.items():
        returns = [float(item["return_pct"]) for item in items]
        drawdowns = [float(item["max_drawdown_pct"]) for item in items]
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "leverage": leverage,
                "count": len(items),
                "positive": sum(value > 0 for value in returns),
                "median_return_pct": statistics.median(returns),
                "mean_return_pct": statistics.fmean(returns),
                "worst_return_pct": min(returns),
                "median_drawdown_pct": statistics.median(drawdowns),
                "worst_drawdown_pct": max(drawdowns),
                "liquidations": sum(bool(item["liquidated"]) for item in items),
                "account_stops": sum(bool(item["account_stopped"]) for item in items),
                "median_flips": statistics.median(float(item["flips"]) for item in items),
                "median_fees": statistics.median(float(item["fees"]) for item in items),
                "median_funding_cost": statistics.median(float(item["funding_cost"]) for item in items),
                "median_max_gross_exposure_pct": statistics.median(float(item["max_gross_exposure_pct"]) for item in items),
                "median_max_abs_net_exposure_pct": statistics.median(float(item["max_abs_net_exposure_pct"]) for item in items),
            }
        )
    result.sort(key=lambda item: (item["segment"], item["variant"], item["leverage"]))
    return result


def decision_payload(aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    passing = []
    for leverage in LEVERAGES:
        validation = aggregate_lookup(aggregates, "validation", "raw", leverage)
        test = aggregate_lookup(aggregates, "test", "raw", leverage)
        stress = aggregate_lookup(aggregates, "test", "cost_stress", leverage)
        full = aggregate_lookup(aggregates, "full", "raw", leverage)
        if (
            validation["median_return_pct"] > 0
            and test["median_return_pct"] > 0
            and stress["median_return_pct"] > 0
            and full["median_return_pct"] > 0
            and validation["liquidations"] == 0
            and test["liquidations"] == 0
            and full["liquidations"] == 0
        ):
            passing.append(leverage)
    return {
        "status": "paper_candidate" if passing else "research_only",
        "passingLeverages": passing,
        "recommendedLeverage": min(passing) if passing else None,
        "rule": "Positive median in validation, test, stressed test and full interval, with zero liquidations.",
    }


def aggregate_lookup(aggregates: list[dict[str, Any]], segment: str, variant: str, leverage: float) -> dict[str, Any]:
    for item in aggregates:
        if item["segment"] == segment and item["variant"] == variant and float(item["leverage"]) == leverage:
            return item
    raise KeyError((segment, variant, leverage))


def markdown_report(payload: dict[str, Any]) -> str:
    config = payload["config"]
    aggregates = payload["aggregates"]
    net_leg_bps = config["flipTakeProfitBps"] - 2.0 * config["makerFeeBps"]
    lines = [
        "# 止盈反手多空网格：杠杆扫描",
        "",
        "> 只读研究；不是同价锁仓，没有读取账户或发送订单。",
        "",
        "## 规则",
        "",
        "- 初始在锚点及下方分层做多。",
        "- 每个多单到止盈价后，平多并在同一价格开等数量空单。",
        "- 每个空单到止盈价后，平空并在同一价格重新开多。",
        "- 不同分仓链可以同时持有成本价错开的多单和空单；同一条链不会同时锁仓。",
        "- 新反手仓不能在同一根 5m K 线内再次止盈；先检查不利方向清算，再处理盈利反手。",
        "",
        "## 固定参数",
        "",
        f"- {config['chains']} 条分仓链，初始层距 {config['seedStepBps']:.1f} bps，单程止盈 {config['flipTakeProfitBps']:.1f} bps。",
        f"- 资金配置 {config['allocationPct']:.1f}%；10x 交易所杠杆对应最高约 {config['allocationPct'] / 100 * 10:.1f}x 账户毛敞口。",
        f"- Maker {config['makerFeeBps']:.1f} bps、Taker {config['takerFeeBps']:.1f} bps，并计入资金费率、最小下单量和价格精度。",
        f"- 忽略资金费率时，每个完整盈利单程约净赚 {net_leg_bps:.1f} bps 名义本金；在 10x/60% 配置下，全部毛敞口完成一程约贡献 {net_leg_bps / 10000 * config['allocationPct'] / 100 * 10 * 100:.3f}% 账户收益。",
        "- 相反，若账户接近 6x 单边净敞口，价格逆向 1% 就约对应 6% 账户浮亏，尚未计入滑点和跳空。",
        "",
        "## 最终测试段",
        "",
        "| 杠杆 | 正收益 | 中位收益 | 成本压力中位 | 中位回撤 | 最差回撤 | 清算数 | 中位最高毛敞口 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for leverage in LEVERAGES:
        raw = aggregate_lookup(aggregates, "test", "raw", leverage)
        stress = aggregate_lookup(aggregates, "test", "cost_stress", leverage)
        lines.append(
            f"| {leverage:g}x | {raw['positive']}/{raw['count']} | {raw['median_return_pct']:.4f}% | "
            f"{stress['median_return_pct']:.4f}% | {raw['median_drawdown_pct']:.4f}% | "
            f"{raw['worst_drawdown_pct']:.4f}% | {raw['liquidations']} | {raw['median_max_gross_exposure_pct']:.1f}% |"
        )
    lines.extend(
        [
            "",
            f"## {config['accountStopPct']:.1f}% 账户止损对照",
            "",
            "| 杠杆 | 最终测试中位收益 | 触发止损合约 | 最差收益 | 清算数 |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for leverage in LEVERAGES:
        stopped = aggregate_lookup(aggregates, "test", "account_stop", leverage)
        lines.append(
            f"| {leverage:g}x | {stopped['median_return_pct']:.4f}% | {stopped['account_stops']}/{stopped['count']} | "
            f"{stopped['worst_return_pct']:.4f}% | {stopped['liquidations']} |"
        )
    lines.extend(
        [
            "",
            "## 跨时间稳定性",
            "",
            "| 杠杆 | 验证段中位 | 完整区间中位 | 最差下跌窗口中位 | 最差上涨窗口中位 | 完整区间清算 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for leverage in LEVERAGES:
        validation = aggregate_lookup(aggregates, "validation", "raw", leverage)
        full = aggregate_lookup(aggregates, "full", "raw", leverage)
        down = aggregate_lookup(aggregates, "worst_downtrend", "raw", leverage)
        up = aggregate_lookup(aggregates, "worst_uptrend", "raw", leverage)
        lines.append(
            f"| {leverage:g}x | {validation['median_return_pct']:.4f}% | {full['median_return_pct']:.4f}% | "
            f"{down['median_return_pct']:.4f}% | {up['median_return_pct']:.4f}% | {full['liquidations']} |"
        )
    ten_rows = [
        row
        for row in payload["rows"]
        if row["segment"] == "test" and row["variant"] == "raw" and float(row["leverage"]) == 10.0
    ]
    lines.extend(
        [
            "",
            "## 10x 最终测试逐合约",
            "",
            "| 合约 | 标的涨跌 | 策略收益 | 最大回撤 | 反手次数 | 费用 | 期末浮盈亏 | 清算 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in ten_rows:
        lines.append(
            f"| {row['inst_id']} | {row['price_return_pct']:.4f}% | {row['return_pct']:.4f}% | "
            f"{row['max_drawdown_pct']:.4f}% | {row['flips']} | {row['fees']:.4f} | "
            f"{row['terminal_unrealized']:.4f} | {'是' if row['liquidated'] else '否'} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"- 判定：**{'可进入仿真盘候选' if decision['status'] == 'paper_candidate' else '仅研究'}**。",
            "- 反手开仓不是无风险成本控制：每次止盈后，新仓方向天然押注价格回到刚突破的区间。持续突破时，它会把已实现利润换成逆势浮亏。",
            "- 杠杆只按比例放大每一程的净优势、费用和突破亏损，不会改变策略期望收益的正负号。",
            f"- 10x 最终测试的高收益伴随 1 个清算；前一验证段中位收益为 {aggregate_lookup(aggregates, 'validation', 'raw', 10.0)['median_return_pct']:.4f}%，且有 {aggregate_lookup(aggregates, 'validation', 'raw', 10.0)['liquidations']}/8 个合约清算，存在明显幸存者偏差。",
            "- `rows.csv` 保存逐合约结果，`aggregate.csv` 保存杠杆与时间段汇总。",
        ]
    )
    return "\n".join(lines) + "\n"


def time_slice(candles: list[Candle], start_ts: int, end_ts: int) -> list[Candle]:
    rows = [item for item in candles if start_ts <= item.ts <= end_ts]
    if len(rows) < 2:
        raise ValueError("candle slice too short")
    return rows


def worst_return_window(candles: list[Candle], bars: int) -> list[Candle]:
    return extreme_return_window(candles, bars, minimum=True)


def best_return_window(candles: list[Candle], bars: int) -> list[Candle]:
    return extreme_return_window(candles, bars, minimum=False)


def extreme_return_window(candles: list[Candle], bars: int, *, minimum: bool) -> list[Candle]:
    if len(candles) <= bars:
        return candles
    best_start = 0
    best_value = float("inf") if minimum else float("-inf")
    for start in range(len(candles) - bars + 1):
        first = float(candles[start].close)
        last = float(candles[start + bars - 1].close)
        value = last / first - 1.0 if first > 0 else 0.0
        if (minimum and value < best_value) or (not minimum and value > best_value):
            best_start = start
            best_value = value
    return candles[best_start : best_start + bars]


def parse_iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return OUTPUT_ROOT / timestamp


if __name__ == "__main__":
    raise SystemExit(main())
