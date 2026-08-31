from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from orderflow_rr_research import (
    DEFAULT_INSTRUMENTS,
    INPUT_ROOT,
    OrderFlowSnapshot,
    StrategyCandidate,
    aggregate_rows,
    iso_time,
    load_snapshot_history,
    result_row,
    simulate_strategy,
    time_slice,
    trade_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "expanded_factors"
MAX_LOOKBACK = 240
FORECAST_HORIZONS = (30, 60, 120, 240)
RIDGE_ALPHAS = (1.0, 10.0, 100.0, 1_000.0)


@dataclass(slots=True)
class ExpandedSegment:
    snapshots: list[OrderFlowSnapshot]
    indices: np.ndarray
    features: np.ndarray
    feature_names: list[str]
    positions: dict[int, int]
    orderflow: np.ndarray


@dataclass(slots=True)
class ModelBundle:
    forecast_horizon: int
    alpha: float
    model: Any
    prediction_scale_bps: float
    feature_names: list[str]
    normalized_coefficients: dict[str, float]


@dataclass(frozen=True, slots=True)
class ExpandedCandidate:
    forecast_horizon: int
    alpha: float
    orderflow_weight: float
    threshold: float
    take_profit_bps: float
    stop_loss_bps: float
    max_hold_bars: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.orderflow_weight <= 0.10:
            raise ValueError("order-flow confirmation weight must be in [0, 0.10]")

    def execution_candidate(self) -> StrategyCandidate:
        return StrategyCandidate(
            "trade_flow_momentum",
            self.threshold,
            self.take_profit_bps,
            self.stop_loss_bps,
            self.max_hold_bars,
        )


@dataclass(slots=True)
class ExpandedCandidateScore:
    params: ExpandedCandidate
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
        description="Read-only expanded multi-factor BTC/ETH research with learned weights."
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
    missing = [inst_id for inst_id in instruments if len(histories.get(inst_id, [])) < 2_000]
    if missing:
        raise SystemExit(f"Insufficient snapshots for {missing}")

    common_start = max(histories[inst_id][0].ts for inst_id in instruments)
    common_end = min(histories[inst_id][-1].ts for inst_id in instruments)
    span = common_end - common_start
    train_end = common_start + int(span * 0.40)
    selection_end = common_start + int(span * 0.50)
    validation_end = common_start + int(span * 0.75)
    boundaries = {
        "model_train": (common_start, train_end),
        "selection": (train_end + 1, selection_end),
        "validation": (selection_end + 1, validation_end),
        "test": (validation_end + 1, common_end),
        "full": (common_start, common_end),
    }
    prepared = {
        inst_id: {
            segment: prepare_segment(
                time_slice(rows, start, end),
                instrument_code=1.0 if inst_id.startswith("BTC") else 0.0,
            )
            for segment, (start, end) in boundaries.items()
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
    training = {inst_id: values["model_train"] for inst_id, values in prepared.items()}
    bundles = {
        (horizon, alpha): fit_bundle(training, horizon, alpha)
        for horizon in FORECAST_HORIZONS
        for alpha in RIDGE_ALPHAS
    }
    selection = {inst_id: values["selection"] for inst_id, values in prepared.items()}
    candidate_scores = select_candidate(selection, bundles, execution)
    if not candidate_scores:
        raise SystemExit("No expanded-factor candidate generated enough selection trades")
    selected = candidate_scores[0].params
    bundle = bundles[(selected.forecast_horizon, selected.alpha)]

    rows: list[dict[str, Any]] = []
    selected_test_trades: list[dict[str, Any]] = []
    for inst_id in instruments:
        for segment in boundaries:
            prepared_segment = prepared[inst_id][segment]
            scored = scored_snapshots(prepared_segment, bundle, selected.orderflow_weight)
            simulation = simulate_strategy(
                scored,
                selected.execution_candidate(),
                **execution,
                record_trades=segment == "test",
            )
            rows.append(expanded_result_row(inst_id, segment, "selected", selected, simulation))
            if segment == "test":
                selected_test_trades.extend(
                    trade_payload(inst_id, trade) for trade in simulation.trade_rows
                )
                rows.extend(test_variants(inst_id, prepared_segment, selected, bundle, execution))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, aggregates)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_expanded_non_orderflow_core_factor_research",
        "instruments": list(instruments),
        "dataDefinition": {
            "source": "locally collected OKX public REST snapshots",
            "sampling": "approximately 65 seconds",
            "limitation": "reuses previously inspected history and is not a lossless websocket event stream",
        },
        "strategyDefinition": {
            "learnedFactors": bundle.feature_names,
            "model": "StandardScaler plus L2-regularized Ridge regression",
            "target": "future mid-price log return at a contained forecast horizon",
            "orderFlowConstraint": "excluded from learned features; capped at 10% as an external confirmation overlay",
            "execution": "marketable bid/ask, per-side taker fee and adverse slippage",
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
            "modelTrainEnd": iso_time(train_end),
            "selectionEnd": iso_time(selection_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "sampleCounts": {
            inst_id: {segment: len(value.snapshots) for segment, value in values.items()}
            for inst_id, values in prepared.items()
        },
        "selectedParameters": asdict(selected),
        "selectedFeatureWeights": bundle.normalized_coefficients,
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
    print(f"selected={asdict(selected)}")
    print(f"decision={decision}")
    lookup = {(item['segment'], item['variant']): item for item in aggregates}
    for segment in boundaries:
        item = lookup[(segment, "selected")]
        print(
            f"segment={segment} median_return={item['median_return_pct']:.6f}% "
            f"median_expectancy={item['median_expectancy_bps']:.4f}bps "
            f"median_pf={item['median_profit_factor']:.4f}"
        )
    return 0


def prepare_segment(snapshots: list[OrderFlowSnapshot], *, instrument_code: float) -> ExpandedSegment:
    names = feature_names()
    indices: list[int] = []
    values: list[list[float]] = []
    flow: list[float] = []
    log_mids = np.log(np.asarray([row.mid for row in snapshots], dtype=float))
    open_interest = np.asarray([row.open_interest for row in snapshots], dtype=float)
    for index in range(MAX_LOOKBACK, len(snapshots)):
        features = feature_row(log_mids, open_interest, snapshots, index, instrument_code)
        if not all(math.isfinite(value) for value in features):
            continue
        row = snapshots[index]
        indices.append(index)
        values.append(features)
        flow.append(clip((row.book_imbalance + row.trade_imbalance + row.ofi) / 3.0))
    index_array = np.asarray(indices, dtype=int)
    return ExpandedSegment(
        snapshots,
        index_array,
        np.asarray(values, dtype=float),
        names,
        {int(index): position for position, index in enumerate(index_array)},
        np.asarray(flow, dtype=float),
    )


def feature_names() -> list[str]:
    names = [f"return_{window}_bps" for window in (1, 3, 5, 10, 30, 60, 120, 240)]
    names += ["acceleration_5_30", "acceleration_30_120"]
    names += [f"price_z_{window}" for window in (20, 60, 240)]
    names += [f"breakout_{window}" for window in (30, 120, 240)]
    names += [f"rsi_{window}" for window in (14, 60)]
    names += [f"volatility_{window}_bps" for window in (10, 30, 120, 240)]
    names += ["vol_ratio_10_120", "vol_ratio_30_240"]
    names += [f"trend_efficiency_{window}" for window in (30, 120, 240)]
    names += [f"autocorrelation_{window}" for window in (30, 120)]
    names += ["autocorr_x_return_30", "autocorr_x_return_120"]
    names += [f"return_skew_{window}" for window in (30, 120)]
    names += [f"semivol_balance_{window}" for window in (30, 120)]
    names += ["spread_bps"]
    names += [f"open_interest_change_{window}_bps" for window in (30, 120, 240)]
    names += ["price_oi_confirmation_30", "price_oi_confirmation_120"]
    names += ["funding_rate_bps", "funding_premium_bps", "hour_sin", "hour_cos", "is_btc"]
    return names


def feature_row(
    log_mids: np.ndarray,
    open_interest: np.ndarray,
    snapshots: list[OrderFlowSnapshot],
    index: int,
    instrument_code: float,
) -> list[float]:
    returns = {
        window: float((log_mids[index] - log_mids[index - window]) * 10_000.0)
        for window in (1, 3, 5, 10, 30, 60, 120, 240)
    }
    features = [returns[window] for window in (1, 3, 5, 10, 30, 60, 120, 240)]
    features += [returns[5] - returns[30] / 6.0, returns[30] - returns[120] / 4.0]
    for window in (20, 60, 240):
        levels = log_mids[index - window : index + 1]
        features.append(
            float((log_mids[index] - float(np.mean(levels))) / max(float(np.std(levels)), 1e-9))
        )
    for window in (30, 120, 240):
        levels = log_mids[index - window : index + 1]
        low, high = float(np.min(levels)), float(np.max(levels))
        features.append(0.0 if high <= low else 2.0 * (log_mids[index] - low) / (high - low) - 1.0)
    one_bar = np.diff(log_mids[index - MAX_LOOKBACK : index + 1])
    features += [rsi_centered(one_bar[-window:]) for window in (14, 60)]
    vol = {
        window: max(float(np.std(one_bar[-window:]) * 10_000.0), 1e-6)
        for window in (10, 30, 120, 240)
    }
    features += [vol[window] for window in (10, 30, 120, 240)]
    features += [math.log(vol[10] / vol[120]), math.log(vol[30] / vol[240])]
    for window in (30, 120, 240):
        window_returns = one_bar[-window:]
        path = float(np.sum(np.abs(window_returns)))
        features.append(float(np.sum(window_returns)) / path if path > 1e-12 else 0.0)
    autocorrelations = {window: autocorrelation(one_bar[-window:]) for window in (30, 120)}
    features += [autocorrelations[30], autocorrelations[120]]
    features += [
        autocorrelations[30] * math.tanh(returns[30] / 50.0),
        autocorrelations[120] * math.tanh(returns[120] / 100.0),
    ]
    for window in (30, 120):
        window_returns = one_bar[-window:]
        scale = max(float(np.std(window_returns)), 1e-9)
        features.append(float(np.mean(((window_returns - np.mean(window_returns)) / scale) ** 3)))
    for window in (30, 120):
        window_returns = one_bar[-window:]
        up = float(np.sum(np.square(window_returns[window_returns > 0])))
        down = float(np.sum(np.square(window_returns[window_returns < 0])))
        features.append((up - down) / (up + down) if up + down > 1e-18 else 0.0)
    row = snapshots[index]
    features.append(row.spread_bps)
    oi_changes = {
        window: log_change_bps(open_interest[index], open_interest[index - window])
        for window in (30, 120, 240)
    }
    features += [oi_changes[window] for window in (30, 120, 240)]
    features += [
        math.tanh(returns[30] / 50.0) * math.tanh(oi_changes[30] / 100.0),
        math.tanh(returns[120] / 100.0) * math.tanh(oi_changes[120] / 200.0),
    ]
    hour = (row.ts / 3_600_000.0) % 24.0
    features += [
        row.funding_rate * 10_000.0,
        row.funding_premium * 10_000.0,
        math.sin(2.0 * math.pi * hour / 24.0),
        math.cos(2.0 * math.pi * hour / 24.0),
        instrument_code,
    ]
    return features


def fit_bundle(
    segments: dict[str, ExpandedSegment], forecast_horizon: int, alpha: float
) -> ModelBundle:
    feature_blocks: list[np.ndarray] = []
    targets: list[float] = []
    for segment in segments.values():
        for position, index_value in enumerate(segment.indices):
            index = int(index_value)
            future_index = index + forecast_horizon
            if future_index >= len(segment.snapshots):
                continue
            if segment.snapshots[future_index].ts - segment.snapshots[index].ts > forecast_horizon * 180_000:
                continue
            future_return = math.log(
                segment.snapshots[future_index].mid / segment.snapshots[index].mid
            ) * 10_000.0
            feature_blocks.append(segment.features[position])
            targets.append(max(-500.0, min(500.0, future_return)))
    if len(targets) < 1_000:
        raise ValueError("insufficient model training rows")
    train_x = np.asarray(feature_blocks, dtype=float)
    train_y = np.asarray(targets, dtype=float)
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    model.fit(train_x, train_y)
    predictions = model.predict(train_x)
    scale = max(float(np.percentile(np.abs(predictions), 75)), 5.0)
    coefficients = np.asarray(model[-1].coef_, dtype=float)
    denominator = float(np.sum(np.abs(coefficients)))
    names = next(iter(segments.values())).feature_names
    normalized = {
        name: (float(value) / denominator if denominator > 0 else 0.0)
        for name, value in zip(names, coefficients)
    }
    return ModelBundle(forecast_horizon, alpha, model, scale, list(names), normalized)


def scored_snapshots(
    segment: ExpandedSegment, bundle: ModelBundle, orderflow_weight: float
) -> list[OrderFlowSnapshot]:
    if not 0.0 <= orderflow_weight <= 0.10:
        raise ValueError("order-flow confirmation weight must be in [0, 0.10]")
    predictions = bundle.model.predict(segment.features) if len(segment.features) else np.asarray([])
    price_scores = np.tanh(predictions / bundle.prediction_scale_bps)
    scores = (1.0 - orderflow_weight) * price_scores + orderflow_weight * segment.orderflow
    by_index = {int(index): float(scores[pos]) for pos, index in enumerate(segment.indices)}
    return [replace(row, trade_imbalance=by_index.get(index, 0.0)) for index, row in enumerate(segment.snapshots)]


def candidate_grid() -> list[ExpandedCandidate]:
    exits = ((100.0, 60.0, 90), (150.0, 80.0, 180), (250.0, 120.0, 360))
    return [
        ExpandedCandidate(horizon, alpha, flow, threshold, take_profit, stop_loss, hold)
        for horizon in FORECAST_HORIZONS
        for alpha in RIDGE_ALPHAS
        for flow in (0.0, 0.05, 0.10)
        for threshold in (0.15, 0.30, 0.45)
        for take_profit, stop_loss, hold in exits
    ]


def select_candidate(
    segments: dict[str, ExpandedSegment],
    bundles: dict[tuple[int, float], ModelBundle],
    execution: dict[str, Any],
) -> list[ExpandedCandidateScore]:
    score_cache: dict[tuple[str, int, float, float], list[OrderFlowSnapshot]] = {}
    scores = []
    for candidate in candidate_grid():
        bundle = bundles[(candidate.forecast_horizon, candidate.alpha)]
        simulations = []
        for inst_id, segment in segments.items():
            key = (inst_id, candidate.forecast_horizon, candidate.alpha, candidate.orderflow_weight)
            if key not in score_cache:
                score_cache[key] = scored_snapshots(segment, bundle, candidate.orderflow_weight)
            simulations.append(
                simulate_strategy(score_cache[key], candidate.execution_candidate(), **execution)
            )
        if not simulations or min(item.trades for item in simulations) < 12:
            continue
        expectancies = [item.expectancy_bps for item in simulations]
        returns = [item.total_return_pct for item in simulations]
        drawdowns = [item.max_drawdown_pct for item in simulations]
        positive = sum(value > 0 for value in expectancies)
        median_expectancy = statistics.median(expectancies)
        worst_expectancy = min(expectancies)
        score = (
            median_expectancy
            + 0.75 * worst_expectancy
            - 0.25 * statistics.median(drawdowns)
            + positive - len(simulations) / 2.0
        )
        scores.append(
            ExpandedCandidateScore(
                candidate,
                score,
                median_expectancy,
                worst_expectancy,
                statistics.median(item.profit_factor for item in simulations),
                statistics.median(returns),
                statistics.median(drawdowns),
                statistics.median(item.trades for item in simulations),
                positive,
                len(simulations),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def test_variants(
    inst_id: str,
    segment: ExpandedSegment,
    selected: ExpandedCandidate,
    bundle: ModelBundle,
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    scored = scored_snapshots(segment, bundle, selected.orderflow_weight)
    for name, kwargs, latency in (
        ("cost_stress", {**execution, "fee_bps_per_side": 8.0, "slippage_bps_per_side": 2.0}, 0),
        ("one_snapshot_latency", execution, 1),
    ):
        simulation = simulate_strategy(
            scored, selected.execution_candidate(), **kwargs, latency_bars=latency
        )
        rows.append(expanded_result_row(inst_id, "test", name, selected, simulation))
    price_only = replace(selected, orderflow_weight=0.0)
    simulation = simulate_strategy(
        scored_snapshots(segment, bundle, 0.0), selected.execution_candidate(), **execution
    )
    rows.append(expanded_result_row(inst_id, "test", "price_state_only", price_only, simulation))
    return rows


def expanded_result_row(
    inst_id: str, segment: str, variant: str, candidate: ExpandedCandidate, result: Any
) -> dict[str, Any]:
    row = result_row(inst_id, segment, variant, candidate.execution_candidate(), result)
    row.update(
        {
            "forecast_horizon": candidate.forecast_horizon,
            "ridge_alpha": candidate.alpha,
            "learned_factor_weight": 1.0 - candidate.orderflow_weight,
            "orderflow_weight": candidate.orderflow_weight,
        }
    )
    return row


def decision_payload(rows: list[dict[str, Any]], aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation, test = lookup[("validation", "selected")], lookup[("test", "selected")]
    stress, latency = lookup[("test", "cost_stress")], lookup[("test", "one_snapshot_latency")]
    test_rows = [row for row in rows if row["segment"] == "test" and row["variant"] == "selected"]
    passed = (
        validation["median_return_pct"] > 0
        and validation["median_expectancy_bps"] > 0
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["profit_factor"]) >= 1.10 and int(row["trades"]) >= 30 for row in test_rows)
        and test["worst_drawdown_pct"] <= 3.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedHistory": passed,
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
    weights = payload["selectedFeatureWeights"]
    ranked = sorted(weights.items(), key=lambda item: abs(item[1]), reverse=True)
    lines = [
        "# BTC/ETH 扩展多因子权重研究",
        "",
        "> 只读探索性研究；复用已检查历史，不授权仿真或实盘。",
        "",
        "## 方法",
        "",
        f"- 使用 {len(weights)} 个严格因果特征，覆盖收益、加速度、z-score、突破、RSI、波动率结构、趋势效率、自相关、偏度、上下行波动差、价差、OI、资金费率、溢价和时段。",
        "- 订单流不进入学习模型，只能作为0%/5%/10%的外层确认项；模型因子始终占至少90%。",
        "- 前40%拟合权重，随后10%选择模型与执行参数，再25%验证，最后25%作复用测试。",
        "- 执行使用可成交bid/ask、双边Taker费和滑点；每笔20%权益、无杠杆。",
        "",
        "## 训练选择",
        "",
        f"- 预测周期 {selected['forecast_horizon']} 张，Ridge alpha {selected['alpha']:.0f}，订单流确认 {selected['orderflow_weight']:.0%}，阈值 {selected['threshold']:.2f}。",
        f"- 止盈 {selected['take_profit_bps']:.0f} bps，止损 {selected['stop_loss_bps']:.0f} bps，最长持有 {selected['max_hold_bars']} 张。",
        "",
        "| 主要因子 | 归一化有符号系数 |",
        "| --- | ---: |",
    ]
    lines += [f"| `{name}` | {value:+.4f} |" for name, value in ranked[:15]]
    lines += [
        "",
        "## 跨时间结果",
        "",
        "| 区间 | 正收益 | 中位收益 | 中位期望 | 中位PF | 最差回撤 | 交易 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for segment, label in (("model_train", "模型训练"), ("selection", "训练内选择"), ("validation", "验证"), ("test", "复用测试"), ("full", "完整")):
        item = lookup[(segment, "selected")]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    lines += [
        "",
        "## 复用测试压力",
        "",
        "| 版本 | 正收益 | 中位收益 | 中位期望 | 中位PF | 最差回撤 | 交易 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant, label in (("selected", "扩展多因子"), ("price_state_only", "移除订单流确认"), ("cost_stress", "成本压力"), ("one_snapshot_latency", "延迟一张")):
        item = lookup[("test", variant)]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    lines += [
        "",
        "## 复用测试逐标的",
        "",
        "| 标的 | 交易 | 收益 | 胜率 | 盈亏比 | 期望 | PF | 最大连亏 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in [row for row in payload["rows"] if row["segment"] == "test" and row["variant"] == "selected"]:
        lines.append(
            f"| {row['inst_id']} | {row['trades']} | {row['total_return_pct']:.4f}% | "
            f"{row['win_rate_pct']:.2f}% | {row['payoff_ratio']:.3f} | {row['expectancy_bps']:.3f} bps | "
            f"{row['profit_factor']:.3f} | {row['max_consecutive_losses']} |"
        )
    decision = payload["decision"]
    validation, test = lookup[("validation", "selected")], lookup[("test", "selected")]
    lines += [
        "",
        "## 判定",
        "",
        "- **仅研究**。",
        f"- 验证中位收益 {validation['median_return_pct']:.4f}%，复用测试中位收益 {test['median_return_pct']:.4f}%。",
        "- 增加因子改善了验证段，但没有解决最后区间的跨期失效，不能据此继续增加模型复杂度或杠杆。",
        f"- 复用历史量化准入：`{str(decision['quantitativePassOnReusedHistory']).lower()}`。",
        f"- {decision['rule']}",
        "- 没有读取账户、启动服务或发送订单。",
    ]
    return "\n".join(lines) + "\n"


def score_payload(item: ExpandedCandidateScore) -> dict[str, Any]:
    return {
        "params": asdict(item.params),
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


def rsi_centered(returns: np.ndarray) -> float:
    gains = float(np.mean(np.maximum(returns, 0.0)))
    losses = float(np.mean(np.maximum(-returns, 0.0)))
    return 0.0 if gains + losses <= 1e-18 else (gains - losses) / (gains + losses)


def autocorrelation(values: np.ndarray) -> float:
    if len(values) < 3 or float(np.std(values)) <= 1e-12:
        return 0.0
    value = float(np.corrcoef(values[:-1], values[1:])[0, 1])
    return value if math.isfinite(value) else 0.0


def log_change_bps(current: float, previous: float) -> float:
    return 0.0 if current <= 0 or previous <= 0 else math.log(current / previous) * 10_000.0


def clip(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


if __name__ == "__main__":
    raise SystemExit(main())
