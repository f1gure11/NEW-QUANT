"""Read-only factor filtering and cycle-length research.

The experiment applies training-only feature filters and causal score filters
to the existing 46-factor BTC/ETH snapshot model.  Resampling strides stretch
every factor horizon together, so cycle comparisons do not silently change the
factor definitions.  All candidate rankings use the selection segment only.
"""

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
from zoneinfo import ZoneInfo

import numpy as np
from scipy.stats import rankdata
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from expanded_factor_research import ExpandedSegment, prepare_segment
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
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "factor_filter_cycles"
FORECAST_BARS = 60
RIDGE_ALPHA = 1_000.0
MAX_FEATURES = 16
MIN_SELECTION_TRADES_PER_INSTRUMENT = 12
BASE_MAX_GAP_MS = 180_000
STRATEGY = StrategyCandidate("trade_flow_momentum", 0.15, 100.0, 60.0, 90)
FILTER_METHODS = ("all_ridge", "stable_ic", "mrmr", "stability_elasticnet")
SMOOTHERS = ("raw", "causal_ewma", "causal_kalman")
SESSION_SCOPES = ("all", "americas", "non_americas")
NEW_YORK = ZoneInfo("America/New_York")
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class CycleProfile:
    name: str
    stride: int


@dataclass(frozen=True, slots=True)
class FilterCandidate:
    cycle: str
    stride: int
    filter_method: str
    smoother: str

    @property
    def candidate_id(self) -> str:
        return f"{self.cycle}__{self.filter_method}__{self.smoother}"


@dataclass(slots=True)
class FilterBundle:
    candidate: FilterCandidate
    selected_indices: np.ndarray
    selected_names: list[str]
    model: Any
    prediction_scale_bps: float
    normalized_coefficients: dict[str, float]
    filter_diagnostics: dict[str, Any]


CYCLE_PROFILES = (
    CycleProfile("original_1x", 1),
    CycleProfile("moderate_3x", 3),
    CycleProfile("slow_6x", 6),
)


def market_session(timestamp_ms: int) -> str:
    local = datetime.fromtimestamp(timestamp_ms / 1_000.0, timezone.utc).astimezone(NEW_YORK)
    minutes = local.hour * 60 + local.minute
    if local.weekday() < 5 and 9 * 60 + 30 <= minutes < 16 * 60:
        return "americas"
    return "non_americas"


def candidate_variant(candidate_id: str, session_scope: str) -> str:
    if session_scope not in SESSION_SCOPES:
        raise ValueError(f"unknown session scope: {session_scope}")
    return candidate_id if session_scope == "all" else f"{candidate_id}__{session_scope}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only factor filtering and cycle research")
    parser.add_argument("--input-root", default=str(INPUT_ROOT))
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--allocation-pct", type=float, default=20.0)
    parser.add_argument("--fee-bps-per-side", type=float, default=5.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=1.0)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    parser.add_argument("--end-time", default="", help="Optional inclusive ISO-8601 research cutoff")
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def downsample_snapshots(rows: list[OrderFlowSnapshot], stride: int) -> list[OrderFlowSnapshot]:
    if stride < 1:
        raise ValueError("stride must be positive")
    return list(rows[::stride])


def parse_iso_time(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000)


def truncate_histories(
    histories: dict[str, list[OrderFlowSnapshot]], cutoff_ms: int | None
) -> dict[str, list[OrderFlowSnapshot]]:
    if cutoff_ms is None:
        return histories
    return {
        inst_id: [row for row in rows if row.ts <= cutoff_ms]
        for inst_id, rows in histories.items()
    }


def period_boundaries(histories: dict[str, list[OrderFlowSnapshot]], instruments: tuple[str, ...]) -> tuple[dict[str, tuple[int, int]], dict[str, str]]:
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
    }
    period = {
        "start": iso_time(common_start),
        "modelTrainEnd": iso_time(train_end),
        "selectionEnd": iso_time(selection_end),
        "validationEnd": iso_time(validation_end),
        "end": iso_time(common_end),
    }
    return boundaries, period


def prepare_cycles(
    histories: dict[str, list[OrderFlowSnapshot]],
    instruments: tuple[str, ...],
    boundaries: dict[str, tuple[int, int]],
) -> dict[str, dict[str, dict[str, ExpandedSegment]]]:
    prepared: dict[str, dict[str, dict[str, ExpandedSegment]]] = {}
    for profile in CYCLE_PROFILES:
        prepared[profile.name] = {}
        for inst_id in instruments:
            sampled = downsample_snapshots(histories[inst_id], profile.stride)
            prepared[profile.name][inst_id] = {
                segment: prepare_segment(
                    time_slice(sampled, start, end),
                    instrument_code=1.0 if inst_id.startswith("BTC") else 0.0,
                )
                for segment, (start, end) in boundaries.items()
            }
    return prepared


def spearman_correlation(left: np.ndarray, right: np.ndarray) -> float:
    if len(left) < 3 or len(right) != len(left):
        return 0.0
    left_rank = rankdata(left)
    right_rank = rankdata(right)
    if np.std(left_rank) <= EPSILON or np.std(right_rank) <= EPSILON:
        return 0.0
    value = float(np.corrcoef(left_rank, right_rank)[0, 1])
    return value if math.isfinite(value) else 0.0


def training_arrays(
    segments: dict[str, ExpandedSegment],
    *,
    stride: int,
    forecast_bars: int = FORECAST_BARS,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    blocks_x: list[np.ndarray] = []
    targets: list[float] = []
    time_blocks: list[int] = []
    names = next(iter(segments.values())).feature_names
    for segment in segments.values():
        usable: list[tuple[np.ndarray, float, int]] = []
        for position, index_value in enumerate(segment.indices):
            index = int(index_value)
            future_index = index + forecast_bars
            if future_index >= len(segment.snapshots):
                continue
            elapsed = segment.snapshots[future_index].ts - segment.snapshots[index].ts
            if elapsed <= 0 or elapsed > forecast_bars * BASE_MAX_GAP_MS * stride:
                continue
            target = math.log(segment.snapshots[future_index].mid / segment.snapshots[index].mid) * 10_000.0
            usable.append((segment.features[position], max(-500.0, min(500.0, target)), index))
        if not usable:
            continue
        length = len(usable)
        for position, (features, target, _) in enumerate(usable):
            blocks_x.append(features)
            targets.append(target)
            time_blocks.append(min(3, position * 4 // max(1, length)))
    if len(targets) < 1_000:
        raise ValueError("insufficient training rows after resampling")
    return np.asarray(blocks_x, dtype=float), np.asarray(targets, dtype=float), np.asarray(time_blocks, dtype=int), list(names)


def absolute_correlation_matrix(values: np.ndarray) -> np.ndarray:
    matrix = np.abs(np.corrcoef(values, rowvar=False))
    return np.nan_to_num(matrix, nan=0.0, posinf=1.0, neginf=1.0)


def stable_ic_select(
    values: np.ndarray,
    targets: np.ndarray,
    blocks: np.ndarray,
    max_features: int = MAX_FEATURES,
) -> tuple[np.ndarray, dict[str, Any]]:
    block_ids = sorted(set(int(item) for item in blocks))
    block_ics = np.zeros((len(block_ids), values.shape[1]), dtype=float)
    for block_position, block_id in enumerate(block_ids):
        mask = blocks == block_id
        for feature in range(values.shape[1]):
            block_ics[block_position, feature] = spearman_correlation(values[mask, feature], targets[mask])
    median_ic = np.median(block_ics, axis=0)
    consistency = np.abs(np.mean(np.sign(block_ics), axis=0))
    ranking = sorted(
        range(values.shape[1]),
        key=lambda index: (consistency[index] >= 0.50, abs(median_ic[index]) * consistency[index]),
        reverse=True,
    )
    correlations = absolute_correlation_matrix(values)
    selected: list[int] = []
    for feature in ranking:
        if consistency[feature] < 0.50 and len(selected) >= max_features // 2:
            continue
        if any(correlations[feature, prior] >= 0.85 for prior in selected):
            continue
        selected.append(feature)
        if len(selected) >= max_features:
            break
    if not selected:
        selected = ranking[:max_features]
    diagnostics = {
        "medianIc": {str(index): float(median_ic[index]) for index in selected},
        "signConsistency": {str(index): float(consistency[index]) for index in selected},
        "correlationPruneThreshold": 0.85,
    }
    return np.asarray(selected, dtype=int), diagnostics


def mrmr_select(
    values: np.ndarray,
    targets: np.ndarray,
    max_features: int = MAX_FEATURES,
) -> tuple[np.ndarray, dict[str, Any]]:
    relevance = np.asarray(
        [abs(spearman_correlation(values[:, index], targets)) for index in range(values.shape[1])],
        dtype=float,
    )
    redundancy = absolute_correlation_matrix(values)
    selected = [int(np.argmax(relevance))]
    scores = {selected[0]: float(relevance[selected[0]])}
    while len(selected) < min(max_features, values.shape[1]):
        best_feature = -1
        best_score = -math.inf
        for feature in range(values.shape[1]):
            if feature in selected:
                continue
            score = float(relevance[feature] - np.mean(redundancy[feature, selected]))
            if score > best_score:
                best_feature, best_score = feature, score
        if best_feature < 0:
            break
        selected.append(best_feature)
        scores[best_feature] = best_score
    return np.asarray(selected, dtype=int), {
        "relevance": {str(index): float(relevance[index]) for index in selected},
        "mrmrScoreAtSelection": {str(index): scores[index] for index in selected},
    }


def stability_elasticnet_select(
    values: np.ndarray,
    targets: np.ndarray,
    blocks: np.ndarray,
    max_features: int = MAX_FEATURES,
) -> tuple[np.ndarray, dict[str, Any]]:
    coefficient_rows: list[np.ndarray] = []
    block_pairs = ((0, 1), (1, 2), (2, 3), (3, 0), (0, 2), (1, 3))
    for pair in block_pairs:
        mask = np.isin(blocks, pair)
        scaler = StandardScaler()
        train_x = scaler.fit_transform(values[mask])
        train_y = targets[mask]
        target_scale = max(float(np.std(train_y)), EPSILON)
        model = ElasticNet(alpha=0.05, l1_ratio=0.80, max_iter=10_000, random_state=0)
        model.fit(train_x, (train_y - float(np.mean(train_y))) / target_scale)
        coefficient_rows.append(np.asarray(model.coef_, dtype=float))
    coefficients = np.asarray(coefficient_rows)
    frequency = np.mean(np.abs(coefficients) > 1e-8, axis=0)
    magnitude = np.mean(np.abs(coefficients), axis=0)
    ranking = sorted(range(values.shape[1]), key=lambda index: (frequency[index], magnitude[index]), reverse=True)
    selected = ranking[:max_features]
    return np.asarray(selected, dtype=int), {
        "selectionFrequency": {str(index): float(frequency[index]) for index in selected},
        "meanAbsCoefficient": {str(index): float(magnitude[index]) for index in selected},
        "subsamples": len(block_pairs),
        "elasticNetAlpha": 0.05,
        "elasticNetL1Ratio": 0.80,
    }


def select_features(
    method: str,
    values: np.ndarray,
    targets: np.ndarray,
    blocks: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    if method == "all_ridge":
        indices = np.arange(values.shape[1], dtype=int)
        return indices, {"selectedAll": True}
    if method == "stable_ic":
        return stable_ic_select(values, targets, blocks)
    if method == "mrmr":
        return mrmr_select(values, targets)
    if method == "stability_elasticnet":
        return stability_elasticnet_select(values, targets, blocks)
    raise ValueError(f"unknown factor filter: {method}")


def fit_filter_bundle(
    candidate: FilterCandidate,
    training: dict[str, ExpandedSegment],
) -> FilterBundle:
    values, targets, blocks, names = training_arrays(training, stride=candidate.stride)
    selected, diagnostics = select_features(candidate.filter_method, values, targets, blocks)
    model = make_pipeline(StandardScaler(), Ridge(alpha=RIDGE_ALPHA))
    model.fit(values[:, selected], targets)
    predictions = model.predict(values[:, selected])
    scale = max(float(np.percentile(np.abs(predictions), 75)), 5.0)
    coefficients = np.asarray(model[-1].coef_, dtype=float)
    denominator = float(np.sum(np.abs(coefficients)))
    selected_names = [names[index] for index in selected]
    normalized = {
        name: (float(value) / denominator if denominator > 0 else 0.0)
        for name, value in zip(selected_names, coefficients)
    }
    diagnostics = {**diagnostics, "selectedCount": len(selected_names)}
    return FilterBundle(candidate, selected, selected_names, model, scale, normalized, diagnostics)


def causal_ewma(values: Iterable[float], span: int = 10) -> np.ndarray:
    rows = np.asarray(list(values), dtype=float)
    if not len(rows):
        return rows
    alpha = 2.0 / (max(1, span) + 1.0)
    result = np.empty_like(rows)
    state = float(rows[0])
    for index, observation in enumerate(rows):
        state = observation if index == 0 else alpha * observation + (1.0 - alpha) * state
        result[index] = state
    return result


def causal_kalman(values: Iterable[float], process_variance: float = 0.05, observation_variance: float = 1.0) -> np.ndarray:
    rows = np.asarray(list(values), dtype=float)
    if not len(rows):
        return rows
    result = np.empty_like(rows)
    state = float(rows[0])
    variance = 1.0
    for index, observation in enumerate(rows):
        if index:
            variance += process_variance
            gain = variance / (variance + observation_variance)
            state += gain * (float(observation) - state)
            variance *= 1.0 - gain
        result[index] = state
    return result


def smooth_scores(values: np.ndarray, method: str) -> np.ndarray:
    if method == "raw":
        return np.asarray(values, dtype=float)
    if method == "causal_ewma":
        return causal_ewma(values)
    if method == "causal_kalman":
        return causal_kalman(values)
    raise ValueError(f"unknown score smoother: {method}")


def score_segment(
    segment: ExpandedSegment,
    bundle: FilterBundle,
    session_scope: str = "all",
) -> list[OrderFlowSnapshot]:
    if session_scope not in SESSION_SCOPES:
        raise ValueError(f"unknown session scope: {session_scope}")
    if len(segment.features):
        predictions = bundle.model.predict(segment.features[:, bundle.selected_indices])
        raw_scores = np.tanh(predictions / bundle.prediction_scale_bps)
        scores = smooth_scores(raw_scores, bundle.candidate.smoother)
    else:
        scores = np.asarray([], dtype=float)
    by_index = {
        int(index): float(scores[position])
        for position, index in enumerate(segment.indices)
        if session_scope == "all"
        or market_session(segment.snapshots[int(index)].ts) == session_scope
    }
    return [replace(row, trade_imbalance=by_index.get(index, 0.0)) for index, row in enumerate(segment.snapshots)]


def enriched_result_row(
    inst_id: str,
    segment: str,
    variant: str,
    result: Any,
    bundle: FilterBundle,
) -> dict[str, Any]:
    row = result_row(inst_id, segment, variant, STRATEGY, result)
    row.update(
        {
            "candidate_id": bundle.candidate.candidate_id,
            "cycle": bundle.candidate.cycle,
            "stride": bundle.candidate.stride,
            "filter_method": bundle.candidate.filter_method,
            "smoother": bundle.candidate.smoother,
            "selected_features": len(bundle.selected_names),
        }
    )
    return row


def selection_score(items: list[dict[str, Any]]) -> float:
    expectancies = [float(item["expectancy_bps"]) for item in items]
    drawdowns = [float(item["max_drawdown_pct"]) for item in items]
    positive = sum(value > 0 for value in expectancies)
    return (
        statistics.median(expectancies)
        + 0.75 * min(expectancies)
        - 0.25 * statistics.median(drawdowns)
        + positive
        - len(items) / 2.0
    )


def candidate_summaries(
    rows: list[dict[str, Any]], session_scope: str = "all"
) -> list[dict[str, Any]]:
    if session_scope not in SESSION_SCOPES:
        raise ValueError(f"unknown session scope: {session_scope}")
    aggregates = aggregate_rows(rows)
    aggregate_lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    candidates = sorted({str(row["candidate_id"]) for row in rows})
    summaries = []
    for candidate_id in candidates:
        variant_id = candidate_variant(candidate_id, session_scope)
        selected_rows = [
            row
            for row in rows
            if row["segment"] == "selection" and row["variant"] == variant_id
        ]
        if len(selected_rows) < 2:
            continue
        first = selected_rows[0]
        minimum_trades = min(int(row["trades"]) for row in selected_rows)
        item = {
            "candidateId": candidate_id,
            "variantId": variant_id,
            "sessionScope": session_scope,
            "cycle": first["cycle"],
            "stride": int(first["stride"]),
            "filterMethod": first["filter_method"],
            "smoother": first["smoother"],
            "selectedFeatures": int(first["selected_features"]),
            "selectionScore": selection_score(selected_rows),
            "minimumSelectionTrades": minimum_trades,
            "selectionEligible": minimum_trades >= MIN_SELECTION_TRADES_PER_INSTRUMENT,
        }
        for segment in ("selection", "validation", "test"):
            aggregate = aggregate_lookup[(segment, variant_id)]
            item[segment] = aggregate
        summaries.append(item)
    summaries.sort(key=lambda item: item["selectionScore"], reverse=True)
    return summaries


def selected_stress_rows(
    selected_bundle: FilterBundle,
    selected_segments: dict[str, ExpandedSegment],
    execution: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    for inst_id, segment in selected_segments.items():
        scored = score_segment(segment, selected_bundle)
        for variant, kwargs, latency in (
            ("selected_cost_stress", {**execution, "fee_bps_per_side": 8.0, "slippage_bps_per_side": 2.0}, 0),
            ("selected_one_bar_latency", execution, 1),
        ):
            simulation = simulate_strategy(scored, STRATEGY, **kwargs, latency_bars=latency)
            rows.append(enriched_result_row(inst_id, "test", variant, simulation, selected_bundle))
    return rows


def decision_payload(
    rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    selected_id: str,
) -> dict[str, Any]:
    aggregates = aggregate_rows(rows)
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", selected_id)]
    test = lookup[("test", selected_id)]
    stress = lookup[("test", "selected_cost_stress")]
    latency = lookup[("test", "selected_one_bar_latency")]
    test_rows = [row for row in rows if row["segment"] == "test" and row["variant"] == selected_id]
    passed = (
        validation["median_expectancy_bps"] > 0
        and validation["positive"] == validation["count"]
        and test["median_return_pct"] > 0
        and test["positive"] == test["count"]
        and test["median_profit_factor"] >= 1.10
        and stress["median_return_pct"] > 0
        and latency["median_return_pct"] > 0
        and min(int(row["trades"]) for row in test_rows) >= 12
    )
    return {
        "status": "research_only" if not passed else "forward_confirmation_required",
        "quantitativeGatePassedOnReusedHistory": passed,
        "selectedCandidate": selected_id,
        "selectionRank": next(index + 1 for index, item in enumerate(summaries) if item["candidateId"] == selected_id),
        "validationMedianReturnPct": validation["median_return_pct"],
        "testMedianReturnPct": test["median_return_pct"],
        "testMedianProfitFactor": test["median_profit_factor"],
        "testWorstDrawdownPct": test["worst_drawdown_pct"],
        "costStressMedianReturnPct": stress["median_return_pct"],
        "latencyMedianReturnPct": latency["median_return_pct"],
        "note": "The final period is reused history and cannot authorize paper or live trading even if the numerical gate passes.",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedCandidate"]
    selected_id = selected["candidateId"]
    aggregates = {(item["segment"], item["variant"]): item for item in payload["aggregates"]}
    lines = [
        "# BTC/ETH 因子过滤与周期选择研究",
        "",
        "> 只读复用历史研究；不读取账户、不发送订单、不改变实盘配置。",
        "",
        "## 论文与开源依据",
        "",
        "- Peng、Long、Ding（2005），mRMR：最大相关性同时最小化因子冗余，DOI `10.1109/TPAMI.2005.159`。",
        "- Meinshausen、Bühlmann（2010），Stability Selection：在重复子样本中保留稳定入选变量并控制假发现，DOI `10.1111/j.1467-9868.2010.00740.x`。",
        "- Benjamini、Hochberg（1995），FDR：大量因子同时检验时控制假发现比例，DOI `10.1111/j.2517-6161.1995.tb02031.x`。",
        "- Kalman（1960），递归线性过滤：只用当前及过去观测更新状态，DOI `10.1115/1.3662552`。",
        "- Harvey、Liu、Zhu（2016）说明大量因子搜索需要更高统计门槛，DOI `10.1093/rfs/hhv059`。",
        "- 开源参考：scikit-learn（BSD-3-Clause）的 Ridge/ElasticNet/feature selection；tsfresh（MIT）的 FDR 特征选择；mrmr-selection（MIT）；pykalman 的递归实现仅作接口参考。本实验没有新增依赖或复制其实现。",
        "",
        "## 无前视设计",
        "",
        "- 前40%只用于因子筛选和 Ridge 拟合；随后10%只负责候选排名；再后25%验证；最后25%是已复用测试。",
        "- 三个周期保持46个因子公式不变，只把采样步长固定为1/3/6倍；预测期均为60根，避免为每个周期单独调目标。",
        "- 因子层比较全部 Ridge、稳定 IC+相关性剪枝、mRMR、分块 ElasticNet 稳定选择；信号层比较 raw、单边 EWMA、单边 Kalman。",
        "- 整段双边滤波、小波和 Savitzky–Golay 没有进入回测，因为直接作用于完整序列会包含未来数据。",
        "- 执行统一采用可成交 bid/ask、每端5 bps手续费和1 bps滑点、20%权益、无杠杆；退出固定100/60 bps TP/SL和90根最长持有。",
        "- 美洲盘定义为纽约本地工作日09:30–16:00（自动处理夏令时）；非美洲盘为其余时间。分盘策略在会话边界将信号归零，并在首个边界外可成交快照平仓。",
        "",
        "## 周期换算",
        "",
        "| 周期 | 采样步长 | 中位每根 | 最长因子窗 | 预测期 | 最长持有 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["cycleTiming"]:
        lines.append(
            f"| {item['name']} | {item['stride']}x | {item['medianBarMinutes']:.2f}m | "
            f"{item['maxFactorHours']:.2f}h | {item['forecastHours']:.2f}h | {item['maxHoldHours']:.2f}h |"
        )
    lines.extend(
        [
            "",
            "## 选择段探索排名前十五",
            "",
            "| 排名 | 资格 | 最少交易 | 周期 | 因子过滤 | 信号过滤 | 因子数 | 选择分 | 选择收益 | 验证收益 | 测试收益 | 测试PF |",
            "| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for rank, item in enumerate(payload["candidateSummaries"][:15], start=1):
        lines.append(
            f"| {rank} | {str(item['selectionEligible']).lower()} | {item['minimumSelectionTrades']} | "
            f"{item['cycle']} | {item['filterMethod']} | {item['smoother']} | {item['selectedFeatures']} | "
            f"{item['selectionScore']:.3f} | {item['selection']['median_return_pct']:.4f}% | "
            f"{item['validation']['median_return_pct']:.4f}% | {item['test']['median_return_pct']:.4f}% | "
            f"{item['test']['median_profit_factor']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 各周期按选择段固定后的最佳方案",
            "",
            "| 周期 | 因子过滤 | 信号过滤 | 选择收益 | 验证收益 | 测试收益 | 测试期望 | 测试PF |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["bestByCycle"]:
        lines.append(
            f"| {item['cycle']} | {item['filterMethod']} | {item['smoother']} | "
            f"{item['selection']['median_return_pct']:.4f}% | {item['validation']['median_return_pct']:.4f}% | "
            f"{item['test']['median_return_pct']:.4f}% | {item['test']['median_expectancy_bps']:.3f} bps | "
            f"{item['test']['median_profit_factor']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 美洲盘与非美洲盘分离选择",
            "",
            "| 时段 | 类型 | 资格 | 最少交易 | 周期 | 因子过滤 | 信号过滤 | 选择收益 | 验证收益 | 测试收益 | 测试PF |",
            "| --- | --- | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    session_labels = {"americas": "美洲盘", "non_americas": "非美洲盘"}
    for session_scope in ("americas", "non_americas"):
        session = payload["sessionSelections"][session_scope]
        for kind, item in (("探索第一", session["exploratoryLeader"]), ("合格第一", session["eligibleSelection"])):
            if item is None:
                lines.append(f"| {session_labels[session_scope]} | {kind} | false | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
                continue
            lines.append(
                f"| {session_labels[session_scope]} | {kind} | {str(item['selectionEligible']).lower()} | {item['minimumSelectionTrades']} | "
                f"{item['cycle']} | {item['filterMethod']} | {item['smoother']} | "
                f"{item['selection']['median_return_pct']:.4f}% | {item['validation']['median_return_pct']:.4f}% | "
                f"{item['test']['median_return_pct']:.4f}% | {item['test']['median_profit_factor']:.3f} |"
            )
    lines.extend(["", "分盘候选数量审计：", ""])
    for session_scope in ("americas", "non_americas"):
        session = payload["sessionSelections"][session_scope]
        lines.append(
            f"- {session_labels[session_scope]}：共 {session['candidateCount']} 个候选，"
            f"{session['eligibleCandidateCount']} 个满足每标的12笔；选择段每标的交易数上限为 "
            f"{session['maximumMinimumSelectionTrades']}。验证/测试中位收益为正分别有 "
            f"{session['positiveValidationCandidates']}/{session['positiveTestCandidates']} 个，"
            f"其中具备样本资格的分别只有 "
            f"{session['eligiblePositiveValidationCandidates']}/"
            f"{session['eligiblePositiveTestCandidates']} 个。"
        )
    lines.extend(
        [
            "",
            "## 训练选择方案",
            "",
            f"- 候选：`{selected_id}`；选择了 {selected['selectedFeatures']} 个因子。",
            f"- 因子：{', '.join(payload['selectedFeatureNames'])}。",
            "",
            "| 区间/压力 | 正收益 | 中位收益 | 中位期望 | 中位PF | 最差回撤 | 交易 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for segment, variant, label in (
        ("selection", selected_id, "选择"),
        ("validation", selected_id, "验证"),
        ("test", selected_id, "复用测试"),
        ("test", "selected_cost_stress", "成本压力"),
        ("test", "selected_one_bar_latency", "延迟一根"),
    ):
        item = aggregates[(segment, variant)]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            f"- 数值准入通过：`{str(decision['quantitativeGatePassedOnReusedHistory']).lower()}`；状态：`{decision['status']}`。",
            f"- 候选只由选择段排名，并要求每个标的至少 {payload['minimumSelectionTradesPerInstrument']} 笔；不合格的小样本冠军仅保留作探索诊断。",
            "- 报告不会在看到验证/测试后换成事后更好的过滤器或周期。",
            "- 最后一段已被以前的研究反复查看，即使数字通过也只能进入新的预注册前向确认，不能直接授权仿真或实盘。",
            "- 约65秒 REST 快照不是无损事件流；采样放慢能压低微观噪声，也会丢失路径信息，结果必须结合新鲜前向数据解释。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    histories = load_snapshot_history(Path(args.input_root), instruments)
    histories = truncate_histories(histories, parse_iso_time(args.end_time) if args.end_time else None)
    missing = [inst_id for inst_id in instruments if len(histories.get(inst_id, [])) < 12_000]
    if missing:
        raise SystemExit(f"Insufficient snapshots for {missing}")
    boundaries, period = period_boundaries(histories, instruments)
    prepared = prepare_cycles(histories, instruments, boundaries)
    execution_by_cycle = {
        profile.name: {
            "starting_equity": args.starting_equity,
            "allocation_pct": args.allocation_pct,
            "fee_bps_per_side": args.fee_bps_per_side,
            "slippage_bps_per_side": args.slippage_bps_per_side,
            "max_spread_bps": args.max_spread_bps,
            "max_gap_ms": BASE_MAX_GAP_MS * profile.stride,
        }
        for profile in CYCLE_PROFILES
    }

    bundles: dict[str, FilterBundle] = {}
    rows: list[dict[str, Any]] = []
    for profile in CYCLE_PROFILES:
        training = {
            inst_id: prepared[profile.name][inst_id]["model_train"] for inst_id in instruments
        }
        for filter_method in FILTER_METHODS:
            for smoother in SMOOTHERS:
                candidate = FilterCandidate(profile.name, profile.stride, filter_method, smoother)
                bundle = fit_filter_bundle(candidate, training)
                bundles[candidate.candidate_id] = bundle
                for segment_name in boundaries:
                    for inst_id in instruments:
                        segment = prepared[profile.name][inst_id][segment_name]
                        for session_scope in SESSION_SCOPES:
                            scored = score_segment(segment, bundle, session_scope)
                            active_predicate = None
                            if session_scope != "all":
                                active_predicate = (
                                    lambda snapshot, scope=session_scope: market_session(snapshot.ts) == scope
                                )
                            simulation = simulate_strategy(
                                scored,
                                STRATEGY,
                                **execution_by_cycle[profile.name],
                                active_predicate=active_predicate,
                            )
                            rows.append(
                                enriched_result_row(
                                    inst_id,
                                    segment_name,
                                    candidate_variant(candidate.candidate_id, session_scope),
                                    simulation,
                                    bundle,
                                )
                            )

    summaries = candidate_summaries(rows, "all")
    if not summaries:
        raise SystemExit("No filter/cycle candidate produced enough selection trades")
    selected_summary = next((item for item in summaries if item["selectionEligible"]), None)
    if selected_summary is None:
        raise SystemExit("No factor-filter candidate met the minimum per-instrument selection trades")
    selected_id = selected_summary["candidateId"]
    selected_bundle = bundles[selected_id]
    selected_profile = selected_bundle.candidate.cycle
    stress_rows = selected_stress_rows(
        selected_bundle,
        {inst_id: prepared[selected_profile][inst_id]["test"] for inst_id in instruments},
        execution_by_cycle[selected_profile],
    )
    rows.extend(stress_rows)
    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, summaries, selected_id)
    session_summaries = {
        session_scope: candidate_summaries(rows, session_scope)
        for session_scope in ("americas", "non_americas")
    }
    session_selections = {}
    for session_scope, items in session_summaries.items():
        session_selections[session_scope] = {
            "candidateCount": len(items),
            "eligibleCandidateCount": sum(item["selectionEligible"] for item in items),
            "maximumMinimumSelectionTrades": max(
                (item["minimumSelectionTrades"] for item in items), default=0
            ),
            "positiveValidationCandidates": sum(item["validation"]["median_return_pct"] > 0 for item in items),
            "positiveTestCandidates": sum(item["test"]["median_return_pct"] > 0 for item in items),
            "eligiblePositiveValidationCandidates": sum(
                item["selectionEligible"] and item["validation"]["median_return_pct"] > 0
                for item in items
            ),
            "eligiblePositiveTestCandidates": sum(
                item["selectionEligible"] and item["test"]["median_return_pct"] > 0
                for item in items
            ),
            "exploratoryLeader": items[0] if items else None,
            "eligibleSelection": next((item for item in items if item["selectionEligible"]), None),
        }

    selected_test_trades: list[dict[str, Any]] = []
    for inst_id in instruments:
        segment = prepared[selected_profile][inst_id]["test"]
        scored = score_segment(segment, selected_bundle)
        simulation = simulate_strategy(
            scored,
            STRATEGY,
            **execution_by_cycle[selected_profile],
            record_trades=True,
        )
        selected_test_trades.extend(trade_payload(inst_id, trade) for trade in simulation.trade_rows)

    median_interval_ms = statistics.median(
        histories[instruments[0]][index].ts - histories[instruments[0]][index - 1].ts
        for index in range(1, len(histories[instruments[0]]))
        if histories[instruments[0]][index].ts > histories[instruments[0]][index - 1].ts
    )
    cycle_timing = []
    for profile in CYCLE_PROFILES:
        bar_hours = median_interval_ms * profile.stride / 3_600_000.0
        cycle_timing.append(
            {
                "name": profile.name,
                "stride": profile.stride,
                "medianBarMinutes": bar_hours * 60.0,
                "maxFactorHours": bar_hours * 240.0,
                "forecastHours": bar_hours * FORECAST_BARS,
                "maxHoldHours": bar_hours * STRATEGY.max_hold_bars,
            }
        )
    best_by_cycle = [
        next(
            (item for item in summaries if item["cycle"] == profile.name and item["selectionEligible"]),
            next(item for item in summaries if item["cycle"] == profile.name),
        )
        for profile in CYCLE_PROFILES
        if any(item["cycle"] == profile.name for item in summaries)
    ]
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_factor_filter_and_cycle_research",
        "instruments": list(instruments),
        "period": period,
        "dataDefinition": {
            "source": "locally collected OKX public REST snapshots",
            "medianSamplingSeconds": median_interval_ms / 1_000.0,
            "reusedHistory": True,
            "limitation": "not a lossless websocket feed; final period was previously inspected",
            "explicitCutoff": args.end_time or None,
        },
        "cycleProfiles": [asdict(item) for item in CYCLE_PROFILES],
        "cycleTiming": cycle_timing,
        "filterMethods": list(FILTER_METHODS),
        "smoothers": list(SMOOTHERS),
        "sessionDefinition": {
            "americas": "America/New_York weekdays 09:30 inclusive to 16:00 exclusive, DST-aware",
            "nonAmericas": "all other timestamps",
            "fitScope": "same chronological all-hours training fit; execution and candidate ranking are split by session",
            "boundaryAction": "score forced to zero; open position closes on the first executable snapshot outside the session",
        },
        "strategy": asdict(STRATEGY),
        "forecastBars": FORECAST_BARS,
        "ridgeAlpha": RIDGE_ALPHA,
        "maxSelectedFeatures": MAX_FEATURES,
        "minimumSelectionTradesPerInstrument": MIN_SELECTION_TRADES_PER_INSTRUMENT,
        "selectedCandidate": selected_summary,
        "selectedFeatureNames": selected_bundle.selected_names,
        "selectedFeatureWeights": selected_bundle.normalized_coefficients,
        "selectedFilterDiagnostics": selected_bundle.filter_diagnostics,
        "candidateSummaries": summaries,
        "sessionCandidateSummaries": session_summaries,
        "sessionSelections": session_selections,
        "bestByCycle": best_by_cycle,
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_ROOT / datetime.now(timezone.utc).strftime("btc-eth-%Y%m%d")
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "selected_test_trades.csv", selected_test_trades)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={selected_id} features={len(selected_bundle.selected_names)}")
    print(f"decision={json.dumps(decision, sort_keys=True)}")
    for segment in ("selection", "validation", "test"):
        item = next(row for row in aggregates if row["segment"] == segment and row["variant"] == selected_id)
        print(
            f"segment={segment} median_return={item['median_return_pct']:.6f}% "
            f"median_expectancy={item['median_expectancy_bps']:.4f}bps "
            f"median_pf={item['median_profit_factor']:.4f} worst_dd={item['worst_drawdown_pct']:.4f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
