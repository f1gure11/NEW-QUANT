from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, iso_time, read_candles_csv
from dual_aggregation import DualAggregationConfig, DualAggregationSimulation, simulate_dual_aggregation
from funding_research import funding_cache_path, read_funding_csv
from gex_delta_neutral_research import load_crypto_gex_events, public_swap_metadata
from gex_risk_controlled_aggregation import (
    Candidate as AggregationCandidate,
    chronological_boundaries,
    gex_entry_gate,
    instrument_config,
    time_slice,
    write_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GEX = PROJECT_ROOT / "data" / "okx" / "gex_snapshots.jsonl"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "gex_inventory_exit"
UNDERLYINGS = ("BTC", "ETH")
FROZEN_ENTRY = AggregationCandidate(100.0, 25.0, 6, 144)


@dataclass(frozen=True, slots=True)
class ExitCandidate:
    pair_start_fraction: float
    pair_min_net_bps: float
    stage_start_fraction: float
    stage_fraction_pct: float = 50.0


@dataclass(slots=True)
class ExitCandidateScore:
    params: ExitCandidate
    score: float
    median_return_pct: float
    median_drawdown_pct: float
    worst_return_pct: float
    positive: int
    instruments: int
    median_pair_events: float
    median_stage_events: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exploratory BTC/ETH GEX aggregation test with paired and staged inventory exits."
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
    events = load_crypto_gex_events(Path(args.gex_file))
    missing = set(UNDERLYINGS) - set(events)
    if missing:
        raise SystemExit(f"Missing GEX history for {sorted(missing)}")

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
    segments = {
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
            name: gex_entry_gate(
                rows,
                events[base],
                max_age_ms=max_age_ms,
                require_inside_walls=True,
            )
            for name, rows in base_segments.items()
        }
        for base, base_segments in segments.items()
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
    scores = select_exit_parameters(
        {base: segments[base]["train"] for base in UNDERLYINGS},
        {base: gates[base]["train"] for base in UNDERLYINGS},
        funding,
        metadata,
        base_config,
    )
    selected = scores[0].params

    rows: list[dict[str, Any]] = []
    for base in UNDERLYINGS:
        frozen = instrument_config(
            base_config,
            FROZEN_ENTRY,
            metadata[f"{base}-USDT-SWAP"],
        )
        variants = {
            "baseline_expiry": frozen,
            "pair_only": apply_exit_policy(frozen, selected, pair=True, stage=False),
            "stage_only": apply_exit_policy(frozen, selected, pair=False, stage=True),
            "pair_stage": apply_exit_policy(frozen, selected, pair=True, stage=True),
        }
        for segment, candles in segments[base].items():
            for variant, config in variants.items():
                simulation = simulate_dual_aggregation(
                    candles,
                    config,
                    funding[base],
                    record_details=False,
                    entry_enabled_by_ts=gates[base][segment],
                )
                rows.append(result_row(base, segment, variant, simulation))
            if segment == "test":
                stressed = replace(
                    variants["pair_stage"],
                    maker_fee_bps=5.0,
                    taker_fee_bps=8.0,
                    liquidation_slippage_bps=4.0,
                    fill_buffer_bps=4.0,
                )
                simulation = simulate_dual_aggregation(
                    candles,
                    stressed,
                    funding[base],
                    record_details=False,
                    entry_enabled_by_ts=gates[base][segment],
                )
                rows.append(result_row(base, segment, "pair_stage_cost_stress", simulation))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(aggregates, rows)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_reused_history_exploratory_inventory_exit",
        "sampleWarning": (
            "The mechanism was proposed after inspecting the prior final-test inventory loss; "
            "validation and test labels are retained for chronology but are not untouched holdouts."
        ),
        "gexFile": str(Path(args.gex_file).resolve()),
        "strategyDefinition": {
            "universe": "BTC-USDT-SWAP and ETH-USDT-SWAP",
            "entryPolicy": "frozen prior GEX/wall entry gate and aggregation parameters",
            "pairExit": "first pair equal long/short quantities when their open-price net PnL is positive; otherwise spend prior realized take-profit credit once to close aged inventory only when absolute net exposure falls",
            "stagedExit": "reduce a trained fraction of remaining lot quantity at deterministic age stages before mandatory expiry",
            "sameBarRule": "a side that risk-exits cannot reopen on the same candle",
            "leverage": "fixed 1x; GEX never increases exposure",
        },
        "period": {
            "start": iso_time(common_start),
            "trainEnd": iso_time(train_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "frozenEntryParameters": asdict(FROZEN_ENTRY),
        "selectedExitParameters": asdict(selected),
        "selectedExitBars": exit_bar_payload(FROZEN_ENTRY.inventory_timeout_bars, selected),
        "candidateScores": [score_payload(item) for item in scores],
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "aggregate.csv", aggregates)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected_exit={asdict(selected)}")
    print(f"decision={decision}")
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    for segment in ("train", "validation", "test", "full"):
        item = lookup[(segment, "pair_stage")]
        print(
            f"segment={segment} median={item['median_return_pct']:.6f}% "
            f"positive={item['positive']}/{item['count']} drawdown={item['worst_drawdown_pct']:.6f}%"
        )
    return 0


def candidate_grid() -> list[ExitCandidate]:
    return [
        ExitCandidate(pair_start, minimum_net, stage_start)
        for pair_start in (0.25, 0.50, 0.75)
        for minimum_net in (0.0, 5.0)
        for stage_start in (0.50, 0.75)
    ]


def exit_bar_payload(timeout_bars: int, params: ExitCandidate) -> dict[str, int | float]:
    pair_start = max(1, round(timeout_bars * params.pair_start_fraction))
    stage_start = max(1, round(timeout_bars * params.stage_start_fraction))
    stage_interval = max(1, (timeout_bars - stage_start) // 2)
    return {
        "pairStartBars": pair_start,
        "stageStartBars": stage_start,
        "stageIntervalBars": stage_interval,
        "stageFractionPct": params.stage_fraction_pct,
    }


def apply_exit_policy(
    config: DualAggregationConfig,
    params: ExitCandidate,
    *,
    pair: bool,
    stage: bool,
) -> DualAggregationConfig:
    bars = exit_bar_payload(config.inventory_timeout_bars, params)
    return replace(
        config,
        basket_pair_start_bars=int(bars["pairStartBars"]) if pair else 0,
        basket_pair_min_net_bps=params.pair_min_net_bps if pair else 0.0,
        staged_reduction_start_bars=int(bars["stageStartBars"]) if stage else 0,
        staged_reduction_interval_bars=int(bars["stageIntervalBars"]) if stage else 0,
        staged_reduction_fraction_pct=params.stage_fraction_pct if stage else 0.0,
    )


def select_exit_parameters(
    candles_by_base: dict[str, list[Candle]],
    gates_by_base: dict[str, dict[int, bool]],
    funding_by_base: dict[str, list[Any]],
    metadata: dict[str, dict[str, Any]],
    base_config: DualAggregationConfig,
) -> list[ExitCandidateScore]:
    scores = []
    for params in candidate_grid():
        returns = []
        drawdowns = []
        pair_events = []
        stage_events = []
        for base, candles in candles_by_base.items():
            frozen = instrument_config(
                base_config,
                FROZEN_ENTRY,
                metadata[f"{base}-USDT-SWAP"],
            )
            config = apply_exit_policy(frozen, params, pair=True, stage=True)
            result = simulate_dual_aggregation(
                candles,
                config,
                funding_by_base.get(base, []),
                record_details=False,
                entry_enabled_by_ts=gates_by_base[base],
            ).result
            returns.append(result.return_pct)
            drawdowns.append(result.max_drawdown_pct)
            pair_events.append(result.basket_pair_events)
            stage_events.append(result.staged_reduction_events)
        median_return = statistics.median(returns)
        median_drawdown = statistics.median(drawdowns)
        positive = sum(value > 0 for value in returns)
        score = (
            median_return
            - 0.70 * median_drawdown
            + 0.08 * (positive - len(returns) / 2.0)
            + 0.20 * min(returns)
        )
        scores.append(
            ExitCandidateScore(
                params,
                score,
                median_return,
                median_drawdown,
                min(returns),
                positive,
                len(returns),
                statistics.median(pair_events),
                statistics.median(stage_events),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


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
        "risk_exit_pnl_pct": result.stop_pnl / result.starting_equity * 100.0,
        "basket_pair_gross_pnl_pct": result.basket_pair_gross_pnl / result.starting_equity * 100.0,
        "staged_reduction_gross_pnl_pct": result.staged_reduction_gross_pnl / result.starting_equity * 100.0,
        "terminal_unrealized_pct": result.terminal_unrealized / result.starting_equity * 100.0,
        "fees_pct": result.fees / result.starting_equity * 100.0,
        "funding_cost_pct": result.funding_cost / result.starting_equity * 100.0,
        "entries": result.entries,
        "round_trips": result.round_trips,
        "inventory_expiries": result.inventory_expiries,
        "basket_pair_events": result.basket_pair_events,
        "simultaneous_pair_events": result.simultaneous_pair_events,
        "harvest_budget_exit_events": result.harvest_budget_exit_events,
        "harvest_budget_exit_gross_pnl_pct": result.harvest_budget_exit_gross_pnl / result.starting_equity * 100.0,
        "harvest_exit_credit_remaining_pct": result.harvest_exit_credit_remaining / result.starting_equity * 100.0,
        "staged_reduction_events": result.staged_reduction_events,
        "max_gross_exposure_pct": result.max_gross_exposure_pct,
        "max_abs_net_exposure_pct": result.max_abs_net_exposure_pct,
        "liquidated": result.liquidated,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["segment"], row["variant"]), []).append(row)
    aggregates = []
    for (segment, variant), items in groups.items():
        returns = [float(item["return_pct"]) for item in items]
        drawdowns = [float(item["max_drawdown_pct"]) for item in items]
        aggregates.append(
            {
                "segment": segment,
                "variant": variant,
                "count": len(items),
                "positive": sum(value > 0 for value in returns),
                "median_return_pct": statistics.median(returns),
                "worst_return_pct": min(returns),
                "median_drawdown_pct": statistics.median(drawdowns),
                "worst_drawdown_pct": max(drawdowns),
                "median_risk_exit_pnl_pct": statistics.median(
                    float(item["risk_exit_pnl_pct"]) for item in items
                ),
                "median_pair_events": statistics.median(
                    float(item["basket_pair_events"]) for item in items
                ),
                "median_simultaneous_pair_events": statistics.median(
                    float(item["simultaneous_pair_events"]) for item in items
                ),
                "median_harvest_budget_exit_events": statistics.median(
                    float(item["harvest_budget_exit_events"]) for item in items
                ),
                "median_stage_events": statistics.median(
                    float(item["staged_reduction_events"]) for item in items
                ),
                "liquidations": sum(bool(item["liquidated"]) for item in items),
            }
        )
    aggregates.sort(key=lambda item: (item["segment"], item["variant"]))
    return aggregates


def decision_payload(
    aggregates: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "pair_stage")]
    test = lookup[("test", "pair_stage")]
    full = lookup[("full", "pair_stage")]
    stress = lookup[("test", "pair_stage_cost_stress")]
    test_rows = [
        row for row in rows if row["segment"] == "test" and row["variant"] == "pair_stage"
    ]
    quantitative_pass = (
        validation["median_return_pct"] > 0
        and test["median_return_pct"] > 0
        and full["median_return_pct"] > 0
        and stress["median_return_pct"] > 0
        and test["positive"] == test["count"]
        and all(not row["liquidated"] for row in test_rows)
        and test["worst_drawdown_pct"] <= 2.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedHistory": quantitative_pass,
        "requiresFreshForwardData": True,
        "rule": (
            "复用历史不能授权仿真交易；未来新增的点时样本还必须满足 BTC/ETH 验证、测试及成本压力收益均为正，"
            "零清算且最差回撤不超过 2%。"
        ),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    period = payload["period"]
    selected = payload["selectedExitParameters"]
    bars = payload["selectedExitBars"]
    lookup = {
        (item["segment"], item["variant"]): item
        for item in payload["aggregates"]
    }
    lines = [
        "# BTC/ETH GEX 聚合策略：配对退出与分阶段减仓",
        "",
        "> 只读探索性研究；本机制源于上一轮测试期诊断，因此复用的验证/测试段不是全新未触碰样本。",
        "",
        "## 固定条件与退出规则",
        "",
        "- 保持 BTC/ETH、1x、50% 总毛敞口、10% 入场净敞口及原 GEX+墙位门控。",
        "- 固定上一轮入场参数：100 bps 层距、25 bps 止盈、每边 6 层、144 根 5m K 库存期限。",
        "- 配对退出只使用当前 K 线开盘价：先尝试扣费后盈利的等量多空；若没有，则过去已完成止盈的退出净收益可作为一次性预算，覆盖能降低绝对净敞口的老库存亏损。",
        "- 止盈预算不会重复使用，也不能为新增仓位、提高杠杆或扩大敞口提供额度。",
        "- 分阶段减仓按仓龄触发，每次减少当前剩余数量；期限到达后剩余库存仍强制退出。",
        "- 风险退出方向在同一根 K 线不得重新开仓，不使用未来最高/最低价决定退出。",
        "",
        "## 数据与训练选择",
        "",
        f"- 区间：`{period['start']}` 至 `{period['end']}`；仍按前 50%/25%/25% 排列，但后两段仅作探索性复用样本。",
        f"- 训练选择：仓龄达到期限的 {selected['pair_start_fraction']:.0%} 后允许配对，配对最低净收益 {selected['pair_min_net_bps']:.1f} bps；仓龄达到 {selected['stage_start_fraction']:.0%} 后开始分阶段减仓。",
        f"- 换算为 5m K：配对从第 {bars['pairStartBars']} 根开始；第 {bars['stageStartBars']} 根开始、每隔 {bars['stageIntervalBars']} 根减掉当前剩余 {bars['stageFractionPct']:.0f}%。",
        "",
        "## 组合机制跨时间结果",
        "",
        "| 区间 | 正收益 | 中位收益 | 最差收益 | 最差回撤 | 中位风险退出损益 | 中位配对事件 | 中位阶段减仓 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for segment, label in (
        ("train", "训练"),
        ("validation", "复用验证"),
        ("test", "复用测试"),
        ("full", "完整"),
    ):
        item = lookup[(segment, "pair_stage")]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['worst_return_pct']:.4f}% | {item['worst_drawdown_pct']:.4f}% | "
            f"{item['median_risk_exit_pnl_pct']:.4f}% | {item['median_pair_events']:.1f} | "
            f"{item['median_stage_events']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## 复用测试段消融",
            "",
            "| 版本 | 正收益 | 中位收益 | 最差收益 | 最差回撤 | 中位风险退出损益 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for variant, label in (
        ("baseline_expiry", "原库存期限"),
        ("pair_only", "仅盈利配对"),
        ("stage_only", "仅分阶段减仓"),
        ("pair_stage", "盈利配对+分阶段"),
        ("pair_stage_cost_stress", "组合机制成本压力"),
    ):
        item = lookup[("test", variant)]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['worst_return_pct']:.4f}% | {item['worst_drawdown_pct']:.4f}% | "
            f"{item['median_risk_exit_pnl_pct']:.4f}% |"
        )
    test_rows = [
        row
        for row in payload["rows"]
        if row["segment"] == "test" and row["variant"] == "pair_stage"
    ]
    lines.extend(
        [
            "",
            "## 复用测试段逐标的",
            "",
            "| 标的 | 收益 | 回撤 | 毛收割 | 风险退出损益 | 盈利预算退出损益 | 阶段减仓损益 | 费用 | 同时配对/预算退出/阶段事件 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in test_rows:
        lines.append(
            f"| {row['underlying']} | {row['return_pct']:.4f}% | {row['max_drawdown_pct']:.4f}% | "
            f"{row['realized_harvest_pct']:.4f}% | {row['risk_exit_pnl_pct']:.4f}% | "
            f"{row['harvest_budget_exit_gross_pnl_pct']:.4f}% | {row['staged_reduction_gross_pnl_pct']:.4f}% | "
            f"{row['fees_pct']:.4f}% | {row['simultaneous_pair_events']}/{row['harvest_budget_exit_events']}/{row['staged_reduction_events']} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            "- **仅研究**；复用历史不能授权仿真盘或实盘。",
            f"- 复用历史数量门槛是否通过：`{str(decision['quantitativePassOnReusedHistory']).lower()}`。",
            f"- {decision['rule']}",
            "- 没有读取账户、启动服务或发送订单。",
        ]
    )
    return "\n".join(lines) + "\n"


def score_payload(item: ExitCandidateScore) -> dict[str, Any]:
    return {
        "params": asdict(item.params),
        **{key: value for key, value in asdict(item).items() if key != "params"},
    }


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
