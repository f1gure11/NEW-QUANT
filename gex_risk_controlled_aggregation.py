from __future__ import annotations

import argparse
import bisect
import csv
import json
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, iso_time, read_candles_csv
from dual_aggregation import DualAggregationConfig, DualAggregationSimulation, simulate_dual_aggregation
from funding_research import funding_cache_path, read_funding_csv
from gex_delta_neutral_research import GexEvent, load_crypto_gex_events, public_swap_metadata


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GEX = PROJECT_ROOT / "data" / "okx" / "gex_snapshots.jsonl"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "gex_risk_controlled"
UNDERLYINGS = ("BTC", "ETH")
MAX_GEX_AGE_MS = 6 * 60 * 60 * 1000


@dataclass(frozen=True, slots=True)
class Candidate:
    step_bps: float
    take_profit_bps: float
    tranches_per_side: int
    inventory_timeout_bars: int


@dataclass(slots=True)
class CandidateScore:
    params: Candidate
    score: float
    median_return_pct: float
    median_drawdown_pct: float
    worst_return_pct: float
    positive: int
    instruments: int
    median_round_trips: float
    median_inventory_expiries: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BTC/ETH dual aggregation with point-in-time GEX as a reduce-risk entry gate."
    )
    parser.add_argument("--gex-file", default=str(DEFAULT_GEX))
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--max-gex-age-hours", type=float, default=6.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_events = load_crypto_gex_events(Path(args.gex_file))
    events = {base: all_events[base] for base in UNDERLYINGS if base in all_events}
    if set(events) != set(UNDERLYINGS):
        raise SystemExit(f"Missing GEX history for {sorted(set(UNDERLYINGS) - set(events))}")
    candles_by_base = {
        base: read_candles_csv(
            PROJECT_ROOT / "data" / "backtest" / f"{base}-USDT-SWAP_5m_300x30.csv"
        )
        for base in UNDERLYINGS
    }
    max_age_ms = int(args.max_gex_age_hours * 60 * 60 * 1000)
    common_start = max(events[base][0].event_ts for base in UNDERLYINGS)
    common_end = min(
        min(events[base][-1].event_ts + max_age_ms, candles_by_base[base][-1].ts)
        for base in UNDERLYINGS
    )
    candles_by_base = {
        base: time_slice(candles, common_start, common_end)
        for base, candles in candles_by_base.items()
    }
    train_end, validation_end = chronological_boundaries(common_start, common_end)
    segments_by_base = {
        base: {
            "train": time_slice(candles, common_start, train_end),
            "validation": time_slice(candles, train_end + 1, validation_end),
            "test": time_slice(candles, validation_end + 1, common_end),
            "full": candles,
        }
        for base, candles in candles_by_base.items()
    }
    gates = {
        base: {
            segment: gex_entry_gate(rows, events[base], max_age_ms=max_age_ms, require_inside_walls=True)
            for segment, rows in segments.items()
        }
        for base, segments in segments_by_base.items()
    }
    sign_only_gates = {
        base: {
            segment: gex_entry_gate(rows, events[base], max_age_ms=max_age_ms, require_inside_walls=False)
            for segment, rows in segments.items()
        }
        for base, segments in segments_by_base.items()
    }
    metadata = public_swap_metadata([f"{base}-USDT-SWAP" for base in UNDERLYINGS])
    funding = {}
    for base in UNDERLYINGS:
        path = funding_cache_path(f"{base}-USDT-SWAP", 100, 1)
        funding[base] = read_funding_csv(path) if path.exists() else []

    base_config = DualAggregationConfig(
        starting_equity=args.starting_equity,
        allocation_pct=50.0,
        leverage=1.0,
        side_stop_bps=0.0,
        cooldown_bars=12,
        account_stop_pct=0.0,
        max_abs_net_exposure_pct=10.0,
        maker_fee_bps=2.0,
        taker_fee_bps=5.0,
        liquidation_slippage_bps=2.0,
        fill_buffer_bps=1.0,
    )
    train_candles = {base: segments_by_base[base]["train"] for base in UNDERLYINGS}
    train_gates = {base: gates[base]["train"] for base in UNDERLYINGS}
    candidate_scores = select_parameters(
        train_candles,
        train_gates,
        funding,
        metadata,
        base_config,
    )
    if not candidate_scores:
        raise SystemExit("No candidate produced enough training activity")
    selected = candidate_scores[0].params

    rows: list[dict[str, Any]] = []
    for base in UNDERLYINGS:
        config = instrument_config(base_config, selected, metadata[f"{base}-USDT-SWAP"])
        for segment, candles in segments_by_base[base].items():
            selected_sim = simulate_dual_aggregation(
                candles,
                config,
                funding[base],
                record_details=False,
                entry_enabled_by_ts=gates[base][segment],
            )
            rows.append(result_row(base, segment, "gex_wall_expiry", selected_sim))

            always_on = simulate_dual_aggregation(
                candles, config, funding[base], record_details=False
            )
            rows.append(result_row(base, segment, "always_on_expiry", always_on))

            no_expiry = replace(config, inventory_timeout_bars=0)
            gex_no_expiry = simulate_dual_aggregation(
                candles,
                no_expiry,
                funding[base],
                record_details=False,
                entry_enabled_by_ts=gates[base][segment],
            )
            rows.append(result_row(base, segment, "gex_wall_no_expiry", gex_no_expiry))

            sign_only = simulate_dual_aggregation(
                candles,
                config,
                funding[base],
                record_details=False,
                entry_enabled_by_ts=sign_only_gates[base][segment],
            )
            rows.append(result_row(base, segment, "gex_sign_expiry", sign_only))

            if segment == "test":
                stressed = replace(
                    config,
                    maker_fee_bps=5.0,
                    taker_fee_bps=8.0,
                    liquidation_slippage_bps=4.0,
                    fill_buffer_bps=4.0,
                )
                stress_sim = simulate_dual_aggregation(
                    candles,
                    stressed,
                    funding[base],
                    record_details=False,
                    entry_enabled_by_ts=gates[base][segment],
                )
                rows.append(result_row(base, segment, "cost_stress", stress_sim))

    aggregates = aggregate_rows(rows)
    gate_stats = gate_statistics(gates, segments_by_base)
    decision = decision_payload(aggregates, rows)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_btc_eth_gex_risk_controlled_dual_aggregation",
        "gexFile": str(Path(args.gex_file).resolve()),
        "strategyDefinition": {
            "universe": "BTC-USDT-SWAP and ETH-USDT-SWAP replace stale equity GEX inputs",
            "entryGate": "new entries only while point-in-time GEX is fresh, positive, and prior close is between put/call walls",
            "riskUse": "GEX can only disable entries; it never increases exposure or leverage",
            "grossCap": "50% of current equity at 1x exchange leverage",
            "netCap": "10% absolute net notional of current equity at entry",
            "inventoryExpiry": "each old lot exits at the next candle open with taker fee and slippage",
            "forecast": "no price trend forecast",
        },
        "config": {
            "bar": "5m",
            "startingEquity": args.starting_equity,
            "maxGexAgeHours": args.max_gex_age_hours,
            "allocationPct": base_config.allocation_pct,
            "leverage": base_config.leverage,
            "maxAbsNetExposurePct": base_config.max_abs_net_exposure_pct,
            "makerFeeBps": base_config.maker_fee_bps,
            "takerFeeBps": base_config.taker_fee_bps,
        },
        "period": {
            "start": iso_time(common_start),
            "trainEnd": iso_time(train_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "selectedParameters": asdict(selected),
        "candidateScores": [score_payload(item) for item in candidate_scores],
        "gateStatistics": gate_stats,
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "aggregate.csv", aggregates)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={asdict(selected)}")
    print(f"decision={decision}")
    for item in aggregates:
        if item["variant"] == "gex_wall_expiry":
            print(
                f"segment={item['segment']} median={item['median_return_pct']:.6f}% "
                f"positive={item['positive']}/{item['count']} drawdown={item['worst_drawdown_pct']:.6f}%"
            )
    return 0


def candidate_grid() -> list[Candidate]:
    return [
        Candidate(step, take_profit, tranches, timeout)
        for step in (25.0, 50.0, 75.0, 100.0)
        for take_profit in (15.0, 25.0, 40.0)
        if take_profit <= step
        for tranches in (4, 6)
        for timeout in (72, 144, 288)
    ]


def select_parameters(
    candles_by_base: dict[str, list[Candle]],
    gates_by_base: dict[str, dict[int, bool]],
    funding_by_base: dict[str, list[Any]],
    metadata: dict[str, dict[str, Any]],
    base_config: DualAggregationConfig,
) -> list[CandidateScore]:
    scores = []
    for params in candidate_grid():
        returns = []
        drawdowns = []
        trips = []
        expiries = []
        for base, candles in candles_by_base.items():
            config = instrument_config(base_config, params, metadata[f"{base}-USDT-SWAP"])
            result = simulate_dual_aggregation(
                candles,
                config,
                funding_by_base.get(base, []),
                record_details=False,
                entry_enabled_by_ts=gates_by_base[base],
            ).result
            returns.append(result.return_pct)
            drawdowns.append(result.max_drawdown_pct)
            trips.append(result.round_trips)
            expiries.append(result.inventory_expiries)
        median_trips = statistics.median(trips)
        if median_trips < 3:
            continue
        median_return = statistics.median(returns)
        median_drawdown = statistics.median(drawdowns)
        positive = sum(value > 0 for value in returns)
        score = (
            median_return
            - 0.70 * median_drawdown
            + 0.004 * min(median_trips, 100)
            + 0.08 * (positive - len(returns) / 2.0)
            + 0.20 * min(returns)
        )
        scores.append(
            CandidateScore(
                params=params,
                score=score,
                median_return_pct=median_return,
                median_drawdown_pct=median_drawdown,
                worst_return_pct=min(returns),
                positive=positive,
                instruments=len(returns),
                median_round_trips=median_trips,
                median_inventory_expiries=statistics.median(expiries),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def instrument_config(
    base: DualAggregationConfig,
    params: Candidate,
    meta: dict[str, Any],
) -> DualAggregationConfig:
    return replace(
        base,
        step_bps=params.step_bps,
        take_profit_bps=params.take_profit_bps,
        tranches_per_side=params.tranches_per_side,
        inventory_timeout_bars=params.inventory_timeout_bars,
        lot_size=float(meta["lotSz"]),
        min_size=float(meta["minSz"]),
        contract_value=float(meta["ctVal"]),
        tick_size=float(meta["tickSz"]),
    )


def gex_entry_gate(
    candles: list[Candle],
    events: list[GexEvent],
    *,
    max_age_ms: int = MAX_GEX_AGE_MS,
    require_inside_walls: bool,
) -> dict[int, bool]:
    event_times = [event.event_ts for event in events]
    result = {}
    for index, candle in enumerate(candles):
        if index == 0:
            result[candle.ts] = False
            continue
        latest_index = bisect.bisect_left(event_times, candle.ts) - 1
        if latest_index < 0:
            result[candle.ts] = False
            continue
        event = events[latest_index]
        age = candle.ts - event.event_ts
        fresh_positive = 0 <= age <= max_age_ms and event.net_gex > 0
        if not fresh_positive:
            result[candle.ts] = False
            continue
        if require_inside_walls:
            prior_close = float(candles[index - 1].close)
            inside = (
                event.put_wall > 0
                and event.call_wall > event.put_wall
                and event.put_wall <= prior_close <= event.call_wall
            )
            result[candle.ts] = inside
        else:
            result[candle.ts] = True
    return result


def result_row(
    base: str,
    segment: str,
    variant: str,
    simulation: DualAggregationSimulation,
) -> dict[str, Any]:
    result = simulation.result
    return {
        "underlying": base,
        "inst_id": f"{base}-USDT-SWAP",
        "segment": segment,
        "variant": variant,
        "start": iso_time(result.start_ts),
        "end": iso_time(result.end_ts),
        "bars": result.bars,
        "price_return_pct": result.price_return_pct,
        "return_pct": result.return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "realized_harvest_pct": result.realized_harvest / result.starting_equity * 100.0,
        "expiry_stop_pnl_pct": result.stop_pnl / result.starting_equity * 100.0,
        "terminal_unrealized_pct": result.terminal_unrealized / result.starting_equity * 100.0,
        "fees_pct": result.fees / result.starting_equity * 100.0,
        "funding_cost_pct": result.funding_cost / result.starting_equity * 100.0,
        "entries": result.entries,
        "round_trips": result.round_trips,
        "inventory_expiries": result.inventory_expiries,
        "max_gross_exposure_pct": result.max_gross_exposure_pct,
        "max_abs_net_exposure_pct": result.max_abs_net_exposure_pct,
        "liquidated": result.liquidated,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["segment"], row["variant"]), []).append(row)
    result = []
    for (segment, variant), items in groups.items():
        returns = [float(item["return_pct"]) for item in items]
        drawdowns = [float(item["max_drawdown_pct"]) for item in items]
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "count": len(items),
                "positive": sum(value > 0 for value in returns),
                "median_return_pct": statistics.median(returns),
                "worst_return_pct": min(returns),
                "median_drawdown_pct": statistics.median(drawdowns),
                "worst_drawdown_pct": max(drawdowns),
                "median_round_trips": statistics.median(float(item["round_trips"]) for item in items),
                "median_inventory_expiries": statistics.median(
                    float(item["inventory_expiries"]) for item in items
                ),
                "median_max_gross_exposure_pct": statistics.median(
                    float(item["max_gross_exposure_pct"]) for item in items
                ),
                "median_max_abs_net_exposure_pct": statistics.median(
                    float(item["max_abs_net_exposure_pct"]) for item in items
                ),
                "liquidations": sum(bool(item["liquidated"]) for item in items),
            }
        )
    result.sort(key=lambda item: (item["segment"], item["variant"]))
    return result


def gate_statistics(
    gates: dict[str, dict[str, dict[int, bool]]],
    segments: dict[str, dict[str, list[Candle]]],
) -> list[dict[str, Any]]:
    rows = []
    for base in UNDERLYINGS:
        for segment in ("train", "validation", "test", "full"):
            gate = gates[base][segment]
            enabled = sum(bool(value) for value in gate.values())
            total = max(1, len(segments[base][segment]) - 1)
            rows.append(
                {
                    "underlying": base,
                    "segment": segment,
                    "enabledBars": enabled,
                    "eligibleBars": total,
                    "enabledPct": enabled / total * 100.0,
                }
            )
    return rows


def decision_payload(
    aggregates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "gex_wall_expiry")]
    test = lookup[("test", "gex_wall_expiry")]
    full = lookup[("full", "gex_wall_expiry")]
    stress = lookup[("test", "cost_stress")]
    test_rows = [
        row for row in rows if row["segment"] == "test" and row["variant"] == "gex_wall_expiry"
    ]
    passing = (
        validation["median_return_pct"] > 0
        and test["median_return_pct"] > 0
        and full["median_return_pct"] > 0
        and stress["median_return_pct"] > 0
        and test["positive"] == test["count"]
        and all(not row["liquidated"] for row in test_rows)
        and test["worst_drawdown_pct"] <= 2.0
    )
    return {
        "status": "paper_candidate" if passing else "research_only",
        "rule": "Positive validation/test/full/cost-stress medians, both BTC and ETH positive in test, zero liquidations, and <=2% worst test drawdown.",
    }


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    top = payload["candidateScores"][0]
    period = payload["period"]
    aggregates = payload["aggregates"]
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    lines = [
        "# BTC/ETH GEX 只减风险的双账本聚合回测",
        "",
        "> 只读研究；美股 GEX 过期时切换为 BTC/ETH，没有读取账户、启动服务或发送订单。",
        "",
        "## 调整后的规则",
        "",
        "- 只交易 BTC-USDT-SWAP 与 ETH-USDT-SWAP，交易所杠杆固定 1x。",
        "- 总毛敞口最多为当前权益 50%，入场时绝对净敞口最多为当前权益 10%。",
        "- 只有点时 GEX 不超过六小时、净 GEX 为正、上一收盘位于 Put/Call 墙之间时才允许新增聚合仓。",
        "- 其他状态仅处理止盈和库存到期退出；GEX 永远不能增加仓位上限。",
        "- 每个过期仓位按下一根 K 线开盘并计入 Taker、滑点强制退出，不使用趋势预测。",
        "",
        "## 数据与训练",
        "",
        f"- 公共 5m 区间：`{period['start']}` 至 `{period['end']}`；前 50% 训练，随后 25% 验证，最后 25% 测试。",
        f"- 训练选择：层距 {selected['step_bps']:.1f} bps、止盈 {selected['take_profit_bps']:.1f} bps、每边 {selected['tranches_per_side']} 层、库存期限 {selected['inventory_timeout_bars']} 根 5m K。",
        f"- 训练最优候选中位收益 {top['median_return_pct']:.4f}%，{top['positive']}/{top['instruments']} 个标的为正；最差收益 {top['worst_return_pct']:.4f}%。",
        "",
        "## GEX允许新增仓位的覆盖率",
        "",
        "| 标的 | 训练 | 验证 | 测试 |",
        "| --- | ---: | ---: | ---: |",
    ]
    gate_lookup = {
        (item["underlying"], item["segment"]): item for item in payload["gateStatistics"]
    }
    for base in UNDERLYINGS:
        lines.append(
            f"| {base} | {gate_lookup[(base, 'train')]['enabledPct']:.1f}% | "
            f"{gate_lookup[(base, 'validation')]['enabledPct']:.1f}% | "
            f"{gate_lookup[(base, 'test')]['enabledPct']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## 主策略跨时间结果",
            "",
            "| 区间 | 正收益 | 中位收益 | 最差收益 | 最差回撤 | 中位往返 | 中位库存到期 | 中位最大毛敞口 | 中位最大净敞口 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for segment, label in (("train", "训练"), ("validation", "验证"), ("test", "测试"), ("full", "完整")):
        item = lookup[(segment, "gex_wall_expiry")]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['worst_return_pct']:.4f}% | {item['worst_drawdown_pct']:.4f}% | "
            f"{item['median_round_trips']:.1f} | {item['median_inventory_expiries']:.1f} | "
            f"{item['median_max_gross_exposure_pct']:.2f}% | {item['median_max_abs_net_exposure_pct']:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## 最终测试消融与成本压力",
            "",
            "| 版本 | 正收益 | 中位收益 | 最差收益 | 最差回撤 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    variants = (
        ("gex_wall_expiry", "GEX+墙位+库存期限"),
        ("gex_sign_expiry", "仅正GEX+库存期限"),
        ("always_on_expiry", "始终入场+库存期限"),
        ("gex_wall_no_expiry", "GEX+墙位但无期限"),
        ("cost_stress", "GEX主策略成本压力"),
    )
    for variant, label in variants:
        item = lookup[("test", variant)]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['worst_return_pct']:.4f}% | {item['worst_drawdown_pct']:.4f}% |"
        )
    test_rows = [
        row for row in payload["rows"] if row["segment"] == "test" and row["variant"] == "gex_wall_expiry"
    ]
    lines.extend(
        [
            "",
            "## 最终测试逐标的",
            "",
            "| 标的 | 标的涨跌 | 策略收益 | 最大回撤 | 毛收割 | 到期/风险损益 | 费用 | 往返 | 到期数 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in test_rows:
        lines.append(
            f"| {row['underlying']} | {row['price_return_pct']:.4f}% | {row['return_pct']:.4f}% | "
            f"{row['max_drawdown_pct']:.4f}% | {row['realized_harvest_pct']:.4f}% | "
            f"{row['expiry_stop_pnl_pct']:.4f}% | {row['fees_pct']:.4f}% | "
            f"{row['round_trips']} | {row['inventory_expiries']} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            f"- **{'可进入仿真盘候选' if decision['status'] == 'paper_candidate' else '仅研究'}**。",
            f"- 准入规则：{decision['rule']}",
            "- 即使通过，也只代表可以进入仿真盘，不授权实盘或提高杠杆。",
        ]
    )
    return "\n".join(lines) + "\n"


def score_payload(item: CandidateScore) -> dict[str, Any]:
    return {
        "params": asdict(item.params),
        **{key: value for key, value in asdict(item).items() if key != "params"},
    }


def chronological_boundaries(start_ts: int, end_ts: int) -> tuple[int, int]:
    span = end_ts - start_ts
    return start_ts + int(span * 0.50), start_ts + int(span * 0.75)


def time_slice(candles: list[Candle], start_ts: int, end_ts: int) -> list[Candle]:
    rows = [item for item in candles if start_ts <= item.ts <= end_ts]
    if len(rows) < 2:
        raise ValueError("candle slice too short")
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
