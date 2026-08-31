from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from orderflow_rr_research import (
    DEFAULT_INSTRUMENTS,
    INPUT_ROOT,
    OrderFlowSnapshot,
    StrategyCandidate,
    aggregate_rows,
    chronological_boundaries,
    iso_time,
    load_snapshot_history,
    result_row,
    simulate_strategy,
    time_slice,
    trade_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "weighted_factors"


@dataclass(frozen=True, slots=True)
class FactorWeights:
    momentum: float
    mean_reversion: float
    breakout: float
    orderflow: float

    def __post_init__(self) -> None:
        values = (self.momentum, self.mean_reversion, self.breakout, self.orderflow)
        if min(values) < 0:
            raise ValueError("factor weights cannot be negative")
        if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
            raise ValueError("factor weights must sum to 1")
        if self.orderflow > 0.15 + 1e-9:
            raise ValueError("order-flow weight must not exceed 15%")

    @property
    def price_weight(self) -> float:
        return self.momentum + self.mean_reversion + self.breakout


WEIGHT_PROFILES: dict[str, FactorWeights] = {
    "price_trend": FactorWeights(0.55, 0.00, 0.45, 0.00),
    "price_trend_confirmed": FactorWeights(0.50, 0.00, 0.40, 0.10),
    "price_balanced": FactorWeights(0.40, 0.25, 0.25, 0.10),
    "price_reversion": FactorWeights(0.00, 0.85, 0.00, 0.15),
    "price_reversion_only": FactorWeights(0.00, 1.00, 0.00, 0.00),
    "price_reversion_with_breakout": FactorWeights(0.00, 0.70, 0.20, 0.10),
}


@dataclass(frozen=True, slots=True)
class FactorComponents:
    momentum: float
    mean_reversion: float
    breakout: float
    orderflow: float


@dataclass(frozen=True, slots=True)
class WeightedCandidate:
    profile: str
    weights: FactorWeights
    fast_lookback: int
    slow_lookback: int
    threshold: float
    take_profit_bps: float
    stop_loss_bps: float
    max_hold_bars: int

    def __post_init__(self) -> None:
        if self.fast_lookback < 2 or self.slow_lookback <= self.fast_lookback:
            raise ValueError("lookbacks must satisfy 2 <= fast < slow")

    def execution_candidate(self) -> StrategyCandidate:
        return StrategyCandidate(
            "trade_flow_momentum",
            self.threshold,
            self.take_profit_bps,
            self.stop_loss_bps,
            self.max_hold_bars,
        )


@dataclass(slots=True)
class WeightedCandidateScore:
    params: WeightedCandidate
    score: float
    median_expectancy_bps: float
    worst_expectancy_bps: float
    median_profit_factor: float
    median_return_pct: float
    median_drawdown_pct: float
    median_trades: float
    positive_instruments: int
    instruments: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only BTC/ETH weighted-factor research with price factors as the core."
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


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    histories = load_snapshot_history(Path(args.input_root), instruments)
    missing = [inst_id for inst_id in instruments if len(histories.get(inst_id, [])) < 1_000]
    if missing:
        raise SystemExit(f"Insufficient snapshots for {missing}")

    common_start = max(histories[inst_id][0].ts for inst_id in instruments)
    common_end = min(histories[inst_id][-1].ts for inst_id in instruments)
    train_end, validation_end = chronological_boundaries(common_start, common_end)
    segments = {
        inst_id: {
            "train": time_slice(rows, common_start, train_end),
            "validation": time_slice(rows, train_end + 1, validation_end),
            "test": time_slice(rows, validation_end + 1, common_end),
            "full": time_slice(rows, common_start, common_end),
        }
        for inst_id, rows in histories.items()
        if inst_id in instruments
    }
    execution = {
        "starting_equity": args.starting_equity,
        "allocation_pct": args.allocation_pct,
        "fee_bps_per_side": args.fee_bps_per_side,
        "slippage_bps_per_side": args.slippage_bps_per_side,
        "max_spread_bps": args.max_spread_bps,
        "max_gap_ms": int(args.max_gap_seconds * 1000),
    }
    training = {inst_id: values["train"] for inst_id, values in segments.items()}
    candidate_scores = select_parameters(training, execution)
    if not candidate_scores:
        raise SystemExit("No weighted-factor candidate generated enough training trades")
    selected = candidate_scores[0].params

    rows: list[dict[str, Any]] = []
    selected_test_trades: list[dict[str, Any]] = []
    for inst_id in instruments:
        for segment, snapshots in segments[inst_id].items():
            scored = weighted_snapshots(snapshots, selected)
            result = simulate_strategy(
                scored,
                selected.execution_candidate(),
                **execution,
                record_trades=segment == "test",
            )
            rows.append(weighted_result_row(inst_id, segment, "selected", selected, result))
            if segment == "test":
                selected_test_trades.extend(trade_payload(inst_id, trade) for trade in result.trade_rows)
                rows.extend(test_variants(inst_id, snapshots, selected, execution))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, aggregates)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_non_orderflow_core_weighted_factor_research",
        "instruments": list(instruments),
        "dataDefinition": {
            "source": "locally collected OKX public REST snapshots",
            "sampling": "approximately 65 seconds",
            "limitation": "reuses previously inspected history and is not a lossless websocket event stream",
        },
        "strategyDefinition": {
            "priceFactors": "volatility-normalized multi-horizon momentum, rolling-price mean reversion, and range breakout",
            "orderFlowFactor": "equal average of depth imbalance, latest-trade imbalance, and normalized top-of-book OFI",
            "weightConstraint": "price factors >= 85%; order flow <= 15%",
            "execution": "marketable bid/ask, per-side taker fee and adverse slippage",
            "positioning": "one position per instrument, fixed fraction of current equity, no leverage",
        },
        "config": {
            "startingEquity": args.starting_equity,
            "allocationPct": args.allocation_pct,
            "feeBpsPerSide": args.fee_bps_per_side,
            "slippageBpsPerSide": args.slippage_bps_per_side,
            "maxSpreadBps": args.max_spread_bps,
            "maxGapSeconds": args.max_gap_seconds,
        },
        "period": {
            "start": iso_time(common_start),
            "trainEnd": iso_time(train_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "sampleCounts": {
            inst_id: {segment: len(values) for segment, values in inst_segments.items()}
            for inst_id, inst_segments in segments.items()
        },
        "weightProfiles": {name: asdict(weights) for name, weights in WEIGHT_PROFILES.items()},
        "selectedParameters": candidate_payload(selected),
        "candidateScores": [score_payload(item) for item in candidate_scores[:100]],
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "trades.csv", selected_test_trades)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={candidate_payload(selected)}")
    print(f"decision={decision}")
    lookup = {(item['segment'], item['variant']): item for item in aggregates}
    for segment in ("train", "validation", "test", "full"):
        item = lookup[(segment, "selected")]
        print(
            f"segment={segment} median_return={item['median_return_pct']:.6f}% "
            f"median_expectancy={item['median_expectancy_bps']:.4f}bps "
            f"median_pf={item['median_profit_factor']:.4f}"
        )
    return 0


def factor_components(
    snapshots: list[OrderFlowSnapshot],
    fast_lookback: int,
    slow_lookback: int,
) -> list[FactorComponents | None]:
    if fast_lookback < 2 or slow_lookback <= fast_lookback:
        raise ValueError("lookbacks must satisfy 2 <= fast < slow")
    result: list[FactorComponents | None] = [None] * len(snapshots)
    if len(snapshots) <= slow_lookback:
        return result
    log_mids = np.log(np.asarray([snapshot.mid for snapshot in snapshots], dtype=float))
    for index in range(slow_lookback, len(snapshots)):
        window = log_mids[index - slow_lookback : index + 1]
        returns = np.diff(window)
        volatility = max(float(np.std(returns)), 1e-9)
        fast_z = (log_mids[index] - log_mids[index - fast_lookback]) / (
            volatility * math.sqrt(fast_lookback)
        )
        slow_z = (log_mids[index] - log_mids[index - slow_lookback]) / (
            volatility * math.sqrt(slow_lookback)
        )
        momentum = math.tanh((fast_z + slow_z) / 2.0)
        level_std = max(float(np.std(window)), 1e-9)
        mean_reversion = -math.tanh((log_mids[index] - float(np.mean(window))) / (2.0 * level_std))
        low = float(np.min(window))
        high = float(np.max(window))
        breakout = 0.0 if high <= low else 2.0 * (log_mids[index] - low) / (high - low) - 1.0
        snapshot = snapshots[index]
        orderflow = (snapshot.book_imbalance + snapshot.trade_imbalance + snapshot.ofi) / 3.0
        result[index] = FactorComponents(
            clip(momentum),
            clip(mean_reversion),
            clip(breakout),
            clip(orderflow),
        )
    return result


def weighted_score(components: FactorComponents, weights: FactorWeights) -> float:
    return clip(
        components.momentum * weights.momentum
        + components.mean_reversion * weights.mean_reversion
        + components.breakout * weights.breakout
        + components.orderflow * weights.orderflow
    )


def weighted_snapshots(
    snapshots: list[OrderFlowSnapshot],
    candidate: WeightedCandidate,
) -> list[OrderFlowSnapshot]:
    components = factor_components(snapshots, candidate.fast_lookback, candidate.slow_lookback)
    return [
        replace(
            snapshot,
            trade_imbalance=(weighted_score(component, candidate.weights) if component else 0.0),
        )
        for snapshot, component in zip(snapshots, components)
    ]


def candidate_grid() -> Iterable[WeightedCandidate]:
    lookbacks = ((5, 30), (10, 60), (15, 120), (30, 240))
    exits = (
        (40.0, 30.0, 20),
        (60.0, 40.0, 40),
        (100.0, 60.0, 90),
        (150.0, 80.0, 180),
        (250.0, 120.0, 360),
    )
    for profile, weights in WEIGHT_PROFILES.items():
        for fast, slow in lookbacks:
            for threshold in (0.30, 0.50, 0.70):
                for take_profit, stop_loss, max_hold in exits:
                    yield WeightedCandidate(
                        profile,
                        weights,
                        fast,
                        slow,
                        threshold,
                        take_profit,
                        stop_loss,
                        max_hold,
                    )


def select_parameters(
    training_rows: dict[str, list[OrderFlowSnapshot]],
    simulation_kwargs: dict[str, Any],
) -> list[WeightedCandidateScore]:
    prepared: dict[tuple[str, str, int, int], list[OrderFlowSnapshot]] = {}
    scores = []
    for candidate in candidate_grid():
        scored_rows = []
        for inst_id, snapshots in training_rows.items():
            key = (inst_id, candidate.profile, candidate.fast_lookback, candidate.slow_lookback)
            if key not in prepared:
                prepared[key] = weighted_snapshots(snapshots, candidate)
            scored_rows.append(prepared[key])
        results = [
            simulate_strategy(rows, candidate.execution_candidate(), **simulation_kwargs)
            for rows in scored_rows
        ]
        if not results or min(result.trades for result in results) < 30:
            continue
        expectancies = [result.expectancy_bps for result in results]
        returns = [result.total_return_pct for result in results]
        drawdowns = [result.max_drawdown_pct for result in results]
        profit_factors = [result.profit_factor for result in results]
        positive = sum(value > 0 for value in expectancies)
        median_expectancy = statistics.median(expectancies)
        worst_expectancy = min(expectancies)
        score = (
            median_expectancy
            + 0.75 * worst_expectancy
            - 0.25 * statistics.median(drawdowns)
            + 1.0 * (positive - len(results) / 2.0)
        )
        scores.append(
            WeightedCandidateScore(
                candidate,
                score,
                median_expectancy,
                worst_expectancy,
                statistics.median(profit_factors),
                statistics.median(returns),
                statistics.median(drawdowns),
                statistics.median(result.trades for result in results),
                positive,
                len(results),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def test_variants(
    inst_id: str,
    snapshots: list[OrderFlowSnapshot],
    selected: WeightedCandidate,
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    scored = weighted_snapshots(snapshots, selected)
    variants = (
        ("cost_stress", scored, {**execution, "fee_bps_per_side": 8.0, "slippage_bps_per_side": 2.0}, 0, 0),
        ("one_snapshot_latency", scored, execution, 1, 0),
        ("long_only", scored, execution, 0, 1),
        ("short_only", scored, execution, 0, -1),
    )
    for variant, variant_rows, kwargs, latency, side_filter in variants:
        simulation = simulate_strategy(
            variant_rows,
            selected.execution_candidate(),
            **kwargs,
            latency_bars=latency,
            side_filter=side_filter,
        )
        result.append(weighted_result_row(inst_id, "test", variant, selected, simulation))

    price_weights = renormalize_price_weights(selected.weights)
    price_only = replace(selected, profile="price_only_ablation", weights=price_weights)
    price_rows = scored_snapshots_from_weights(snapshots, selected, price_weights)
    price_result = simulate_strategy(price_rows, selected.execution_candidate(), **execution)
    result.append(weighted_result_row(inst_id, "test", "price_only", price_only, price_result))

    order_rows = scored_snapshots_from_weights(
        snapshots,
        selected,
        FactorWeights(0.0, 0.0, 0.85, 0.15),
    )
    order_result = simulate_strategy(order_rows, selected.execution_candidate(), **execution)
    result.append(weighted_result_row(inst_id, "test", "breakout_orderflow_control", selected, order_result))
    return result


def scored_snapshots_from_weights(
    snapshots: list[OrderFlowSnapshot],
    candidate: WeightedCandidate,
    weights: FactorWeights,
) -> list[OrderFlowSnapshot]:
    components = factor_components(snapshots, candidate.fast_lookback, candidate.slow_lookback)
    return [
        replace(snapshot, trade_imbalance=weighted_score(component, weights) if component else 0.0)
        for snapshot, component in zip(snapshots, components)
    ]


def renormalize_price_weights(weights: FactorWeights) -> FactorWeights:
    total = weights.price_weight
    if total <= 0:
        raise ValueError("price weights must be positive")
    return FactorWeights(
        weights.momentum / total,
        weights.mean_reversion / total,
        weights.breakout / total,
        0.0,
    )


def weighted_result_row(
    inst_id: str,
    segment: str,
    variant: str,
    candidate: WeightedCandidate,
    result: Any,
) -> dict[str, Any]:
    row = result_row(inst_id, segment, variant, candidate.execution_candidate(), result)
    row.update(
        {
            "profile": candidate.profile,
            "fast_lookback": candidate.fast_lookback,
            "slow_lookback": candidate.slow_lookback,
            "momentum_weight": candidate.weights.momentum,
            "mean_reversion_weight": candidate.weights.mean_reversion,
            "breakout_weight": candidate.weights.breakout,
            "orderflow_weight": candidate.weights.orderflow,
            "price_weight": candidate.weights.price_weight,
        }
    )
    return row


def decision_payload(
    rows: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "selected")]
    test = lookup[("test", "selected")]
    stress = lookup[("test", "cost_stress")]
    latency = lookup[("test", "one_snapshot_latency")]
    test_rows = [row for row in rows if row["segment"] == "test" and row["variant"] == "selected"]
    quantitative_pass = (
        validation["median_return_pct"] > 0
        and validation["median_expectancy_bps"] > 0
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["profit_factor"]) >= 1.10 for row in test_rows)
        and all(int(row["trades"]) >= 30 for row in test_rows)
        and test["worst_drawdown_pct"] <= 3.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedHistory": quantitative_pass,
        "requiresFreshForwardData": True,
        "liveAuthorized": False,
        "rule": (
            "复用历史不能授权仿真或实盘；验证期望须为正，BTC/ETH 测试、成本和延迟压力须全部盈利，"
            "测试 PF>=1.10、每标的不少于30笔且最差回撤<=3%。"
        ),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    lookup = {(item["segment"], item["variant"]): item for item in payload["aggregates"]}
    period = payload["period"]
    lines = [
        "# BTC/ETH 非订单流核心加权因子研究",
        "",
        "> 只读探索性研究；复用已检查历史，不授权仿真或实盘。",
        "",
        "## 方法",
        "",
        "- 价格因子：波动率标准化的多周期动量、滚动价格偏离回归、滚动区间突破。",
        "- 订单流因子只把深度失衡、最近成交失衡和顶层 OFI 等权合并，候选权重上限为15%。",
        "- 所有候选的价格因子合计权重至少85%；权重、周期、阈值与退出参数仅由前50%训练段选择。",
        "- 后25%与既有订单流实验重叠，只能作复用测试；执行仍使用可成交bid/ask、双边Taker费和滑点。",
        "",
        "## 数据与训练选择",
        "",
        f"- 区间：`{period['start']}` 至 `{period['end']}`；50%训练、25%验证、25%复用测试。",
        f"- 训练选择：`{selected['profile']}`，快/慢周期 {selected['fast_lookback']}/{selected['slow_lookback']} 张快照，阈值 {selected['threshold']:.2f}。",
        f"- 权重：动量 {selected['weights']['momentum']:.0%}，均值回归 {selected['weights']['mean_reversion']:.0%}，突破 {selected['weights']['breakout']:.0%}，订单流 {selected['weights']['orderflow']:.0%}。",
        f"- 退出：止盈 {selected['take_profit_bps']:.0f} bps，止损 {selected['stop_loss_bps']:.0f} bps，最长持有 {selected['max_hold_bars']} 张快照。",
        "",
        "## 跨时间结果",
        "",
        "| 区间 | 正收益 | 中位收益 | 中位期望 | 中位胜率 | 中位盈亏比 | 中位PF | 最差回撤 | 交易 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for segment, label in (("train", "训练"), ("validation", "验证"), ("test", "复用测试"), ("full", "完整")):
        item = lookup[(segment, "selected")]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_win_rate_pct']:.2f}% | "
            f"{item['median_payoff_ratio']:.3f} | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    lines.extend(
        [
            "",
            "## 复用测试压力与消融",
            "",
            "| 版本 | 正收益 | 中位收益 | 中位期望 | 中位PF | 最差回撤 | 交易 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    variants = (
        ("selected", "选中加权因子"),
        ("price_only", "移除订单流"),
        ("breakout_orderflow_control", "突破85%+订单流15%对照"),
        ("cost_stress", "成本压力"),
        ("one_snapshot_latency", "延迟一张快照"),
        ("long_only", "仅多头"),
        ("short_only", "仅空头"),
    )
    for variant, label in variants:
        item = lookup[("test", variant)]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    test_rows = [row for row in payload["rows"] if row["segment"] == "test" and row["variant"] == "selected"]
    lines.extend(
        [
            "",
            "## 复用测试逐标的",
            "",
            "| 标的 | 交易 | 收益 | 胜率 | 盈亏比 | 期望 | PF | 最大连亏 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in test_rows:
        lines.append(
            f"| {row['inst_id']} | {row['trades']} | {row['total_return_pct']:.4f}% | "
            f"{row['win_rate_pct']:.2f}% | {row['payoff_ratio']:.3f} | {row['expectancy_bps']:.3f} bps | "
            f"{row['profit_factor']:.3f} | {row['max_consecutive_losses']} |"
        )
    decision = payload["decision"]
    train = lookup[("train", "selected")]
    validation = lookup[("validation", "selected")]
    test = lookup[("test", "selected")]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            "- **仅研究**。",
            (
                f"- 非订单流核心权重把训练中位收益改善到 {train['median_return_pct']:.4f}%，"
                f"但验证为 {validation['median_return_pct']:.4f}%、复用测试为 {test['median_return_pct']:.4f}%；"
                "本轮没有扭亏为盈。"
            ),
            f"- 复用历史量化准入：`{str(decision['quantitativePassOnReusedHistory']).lower()}`。",
            f"- {decision['rule']}",
            "- 没有读取账户、启动服务或发送订单。",
        ]
    )
    return "\n".join(lines) + "\n"


def candidate_payload(candidate: WeightedCandidate) -> dict[str, Any]:
    payload = asdict(candidate)
    payload["price_weight"] = candidate.weights.price_weight
    return payload


def score_payload(item: WeightedCandidateScore) -> dict[str, Any]:
    return {
        "params": candidate_payload(item.params),
        **{key: value for key, value in asdict(item).items() if key != "params"},
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def clip(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


if __name__ == "__main__":
    raise SystemExit(main())
