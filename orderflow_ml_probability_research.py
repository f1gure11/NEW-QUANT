from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from orderflow_rr_research import (
    INPUT_ROOT,
    DEFAULT_INSTRUMENTS,
    OrderFlowSnapshot,
    OrderFlowTrade,
    StrategyCandidate,
    factor_score,
    load_snapshot_history,
    simulate_strategy,
    summarize_trades,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "orderflow_ml_probability"


@dataclass(frozen=True, slots=True)
class BarrierPolicy:
    name: str
    take_profit_bps: float
    stop_loss_bps: float
    max_hold_bars: int


POLICIES = (
    BarrierPolicy("tp40_sl15_h20", 40.0, 15.0, 20),
    BarrierPolicy("tp60_sl20_h30", 60.0, 20.0, 30),
    BarrierPolicy("tp80_sl25_h60", 80.0, 25.0, 60),
    BarrierPolicy("tp100_sl30_h60", 100.0, 30.0, 60),
)


@dataclass(slots=True)
class PreparedSegment:
    snapshots: list[OrderFlowSnapshot]
    indices: np.ndarray
    features: np.ndarray
    feature_names: list[str]
    positions: dict[int, int]


@dataclass(frozen=True, slots=True)
class BarrierOutcome:
    net_pnl_bps: float
    exit_index: int
    exit_reason: str


@dataclass(slots=True)
class ProbabilityBundle:
    model_kind: str
    classifier: Any
    calibrator: IsotonicRegression | None
    win_model: Any | None
    loss_model: Any | None
    constant_win_bps: float
    constant_loss_bps: float


@dataclass(slots=True)
class ActionPrediction:
    probability: np.ndarray
    win_bps: np.ndarray
    loss_bps: np.ndarray
    payoff_ratio: np.ndarray
    expectancy_bps: np.ndarray


@dataclass(slots=True)
class MLTrade:
    trade: OrderFlowTrade
    policy: str
    predicted_probability: float
    predicted_win_bps: float
    predicted_loss_bps: float
    predicted_payoff_ratio: float
    predicted_expectancy_bps: float


@dataclass(slots=True)
class MLSimulation:
    base: Any
    mean_predicted_probability: float
    mean_predicted_payoff_ratio: float
    mean_predicted_expectancy_bps: float
    brier_score: float
    log_loss: float
    calibration_gap_pct: float
    policy_counts: dict[str, int]
    ml_trades: list[MLTrade]


@dataclass(frozen=True, slots=True)
class ModelSelection:
    model_kind: str
    min_expectancy_bps: float
    score: float
    median_return_pct: float
    worst_return_pct: float
    median_expectancy_bps: float
    median_profit_factor: float
    median_trades: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exploratory calibrated ML estimates of order-flow win probability and payoff."
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
    span = common_end - common_start
    model_train_end = common_start + int(span * 0.40)
    calibration_end = common_start + int(span * 0.50)
    validation_end = common_start + int(span * 0.75)
    boundaries = {
        "model_train": (common_start, model_train_end),
        "calibration": (model_train_end + 1, calibration_end),
        "validation": (calibration_end + 1, validation_end),
        "test": (validation_end + 1, common_end),
    }
    prepared = {
        inst_id: {
            segment: prepare_segment(
                [row for row in histories[inst_id] if start <= row.ts <= end],
                instrument_code=1.0 if inst_id.startswith("BTC") else 0.0,
            )
            for segment, (start, end) in boundaries.items()
        }
        for inst_id in instruments
    }
    execution = {
        "starting_equity": args.starting_equity,
        "allocation_pct": args.allocation_pct,
        "fee_bps_per_side": args.fee_bps_per_side,
        "slippage_bps_per_side": args.slippage_bps_per_side,
        "max_spread_bps": args.max_spread_bps,
        "max_gap_ms": int(args.max_gap_seconds * 1000),
    }

    bundles_by_kind: dict[str, dict[tuple[int, str], ProbabilityBundle]] = {}
    for model_kind in ("hist_gradient_dynamic", "logistic_static"):
        bundles: dict[tuple[int, str], ProbabilityBundle] = {}
        for side in (1, -1):
            for policy in POLICIES:
                train_x, train_pnl = action_dataset(
                    {inst_id: prepared[inst_id]["model_train"] for inst_id in instruments},
                    side,
                    policy,
                    execution,
                )
                calibration_x, calibration_pnl = action_dataset(
                    {inst_id: prepared[inst_id]["calibration"] for inst_id in instruments},
                    side,
                    policy,
                    execution,
                )
                bundles[(side, policy.name)] = fit_probability_bundle(
                    model_kind,
                    train_x,
                    train_pnl,
                    calibration_x,
                    calibration_pnl,
                )
        bundles_by_kind[model_kind] = bundles

    validation_predictions = {
        model_kind: {
            inst_id: predict_actions(
                prepared[inst_id]["validation"],
                bundles,
            )
            for inst_id in instruments
        }
        for model_kind, bundles in bundles_by_kind.items()
    }
    selections = select_model_and_threshold(
        {inst_id: prepared[inst_id]["validation"] for inst_id in instruments},
        validation_predictions,
        execution,
    )
    selected = selections[0]

    rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    for model_kind, bundles in bundles_by_kind.items():
        own_selection = next(item for item in selections if item.model_kind == model_kind)
        for segment in ("validation", "test"):
            for inst_id in instruments:
                segment_data = prepared[inst_id][segment]
                predictions = (
                    validation_predictions[model_kind][inst_id]
                    if segment == "validation"
                    else predict_actions(segment_data, bundles)
                )
                simulation = simulate_dynamic_strategy(
                    segment_data,
                    predictions,
                    min_expectancy_bps=own_selection.min_expectancy_bps,
                    **execution,
                    record_trades=segment == "test" and model_kind == selected.model_kind,
                )
                variant = "selected" if model_kind == selected.model_kind else model_kind
                rows.append(ml_result_row(inst_id, segment, variant, model_kind, own_selection, simulation))
                if segment == "test" and model_kind == selected.model_kind:
                    trade_rows.extend(ml_trade_payload(inst_id, item) for item in simulation.ml_trades)
                    policy_rows.extend(
                        {
                            "inst_id": inst_id,
                            "policy": policy,
                            "trades": count,
                        }
                        for policy, count in sorted(simulation.policy_counts.items())
                    )

    test_predictions = {
        inst_id: predict_actions(
            prepared[inst_id]["test"],
            bundles_by_kind[selected.model_kind],
        )
        for inst_id in instruments
    }
    for inst_id in instruments:
        segment_data = prepared[inst_id]["test"]
        predictions = test_predictions[inst_id]
        stressed = simulate_dynamic_strategy(
            segment_data,
            predictions,
            min_expectancy_bps=selected.min_expectancy_bps,
            **{
                **execution,
                "fee_bps_per_side": 8.0,
                "slippage_bps_per_side": 2.0,
            },
        )
        rows.append(ml_result_row(inst_id, "test", "cost_stress", selected.model_kind, selected, stressed))
        latency = simulate_dynamic_strategy(
            segment_data,
            predictions,
            min_expectancy_bps=selected.min_expectancy_bps,
            **execution,
            latency_bars=1,
        )
        rows.append(ml_result_row(inst_id, "test", "one_snapshot_latency", selected.model_kind, selected, latency))
        no_abstention = simulate_dynamic_strategy(
            segment_data,
            predictions,
            min_expectancy_bps=-1_000.0,
            **execution,
        )
        rows.append(ml_result_row(inst_id, "test", "no_abstention", selected.model_kind, selected, no_abstention))

        baseline = simulate_strategy(
            segment_data.snapshots,
            StrategyCandidate("trade_flow_reversal", 0.35, 100.0, 30.0, 60),
            **execution,
        )
        rows.append(baseline_result_row(inst_id, baseline))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, aggregates)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_exploratory_calibrated_orderflow_ml",
        "sampleWarning": (
            "The prior rule-based experiment already inspected this final period. ML results are exploratory "
            "reused-history evidence and cannot authorize paper or live trading."
        ),
        "instruments": list(instruments),
        "period": {
            "start": iso_time(common_start),
            "modelTrainEnd": iso_time(model_train_end),
            "calibrationEnd": iso_time(calibration_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "sampleCounts": {
            inst_id: {
                segment: len(value.snapshots)
                for segment, value in instrument_segments.items()
            }
            for inst_id, instrument_segments in prepared.items()
        },
        "featureNames": next(iter(prepared.values()))["model_train"].feature_names,
        "barrierPolicies": [asdict(policy) for policy in POLICIES],
        "openSourceEvaluation": [
            {
                "project": "scikit-learn/scikit-learn",
                "url": "https://github.com/scikit-learn/scikit-learn",
                "license": "BSD-3-Clause",
                "use": "implemented HistGradientBoosting, LogisticRegression and IsotonicRegression test",
            },
            {
                "project": "freqtrade/freqtrade FreqAI",
                "url": "https://github.com/freqtrade/freqtrade",
                "license": "GPL-3.0",
                "use": "reviewed; not used because the current task needs L2 event labels rather than candle-oriented live plumbing",
            },
            {
                "project": "nkaz001/hftbacktest",
                "url": "https://github.com/nkaz001/hftbacktest",
                "license": "MIT",
                "use": "reviewed for future event replay and queue-model tests; current REST snapshots are insufficient",
            },
            {
                "project": "nautechsystems/nautilus_trader",
                "url": "https://github.com/nautechsystems/nautilus_trader",
                "license": "LGPL-3.0",
                "use": "reviewed as a future event-driven pipeline; not introduced into this experiment",
            },
            {
                "project": "DeepLOB public reproductions",
                "license": "many repositories do not declare a license",
                "use": "not copied; dense event tensors and PyTorch are unavailable in the current REST dataset/environment",
            },
            {
                "project": "hudson-and-thames/mlfinlab",
                "license": "GitHub API reports NOASSERTION",
                "use": "triple-barrier concept reviewed; implementation here is independent and minimal",
            },
        ],
        "literature": [
            {"title": "DeepLOB", "doi": "10.1109/TSP.2019.2907260", "url": "https://doi.org/10.1109/TSP.2019.2907260"},
            {"title": "Deep Order Flow Imbalance", "doi": "10.1111/mafi.12413", "url": "https://doi.org/10.1111/mafi.12413"},
            {"title": "Predicting Good Probabilities with Supervised Learning", "doi": "10.1145/1102351.1102430", "url": "https://doi.org/10.1145/1102351.1102430"},
            {"title": "The Price Impact of Order Book Events", "doi": "10.1093/jjfinec/nbt003", "url": "https://doi.org/10.1093/jjfinec/nbt003"},
            {"title": "Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book", "doi": "10.1142/S2382626616500064", "url": "https://doi.org/10.1142/S2382626616500064"},
        ],
        "execution": execution,
        "modelSelections": [asdict(item) for item in selections],
        "selectedModel": asdict(selected),
        "rows": rows,
        "aggregates": aggregates,
        "policyCounts": policy_rows,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "trades.csv", trade_rows)
    write_csv(output_dir / "policy_counts.csv", policy_rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={asdict(selected)}")
    print(f"decision={decision}")
    for row in aggregates:
        if row["variant"] == "selected":
            print(
                f"segment={row['segment']} return={row['median_return_pct']:.6f}% "
                f"expectancy={row['median_expectancy_bps']:.4f}bps pf={row['median_profit_factor']:.4f}"
            )
    return 0


def prepare_segment(
    snapshots: list[OrderFlowSnapshot],
    *,
    instrument_code: float,
) -> PreparedSegment:
    feature_names = [
        "book", "trade", "ofi", "spread", "book_lag1", "trade_lag1", "ofi_lag1",
        "book_mean3", "trade_mean3", "ofi_mean3", "book_mean10", "trade_mean10",
        "ofi_mean10", "return_1_bps", "return_3_bps", "return_10_bps",
        "volatility_10_bps", "book_x_trade", "book_x_ofi", "trade_x_ofi",
        "hour_sin", "hour_cos", "is_btc",
    ]
    indices = []
    features = []
    mids = np.asarray([row.mid for row in snapshots], dtype=float)
    for index in range(10, len(snapshots)):
        current = snapshots[index]
        book3 = [snapshots[pos].book_imbalance for pos in range(index - 2, index + 1)]
        trade3 = [snapshots[pos].trade_imbalance for pos in range(index - 2, index + 1)]
        ofi3 = [snapshots[pos].ofi for pos in range(index - 2, index + 1)]
        book10 = [snapshots[pos].book_imbalance for pos in range(index - 9, index + 1)]
        trade10 = [snapshots[pos].trade_imbalance for pos in range(index - 9, index + 1)]
        ofi10 = [snapshots[pos].ofi for pos in range(index - 9, index + 1)]
        returns = np.diff(np.log(mids[index - 10 : index + 1])) * 10_000.0
        hour = (current.ts / 3_600_000.0) % 24.0
        features.append(
            [
                current.book_imbalance,
                current.trade_imbalance,
                current.ofi,
                current.spread_bps,
                snapshots[index - 1].book_imbalance,
                snapshots[index - 1].trade_imbalance,
                snapshots[index - 1].ofi,
                statistics.fmean(book3),
                statistics.fmean(trade3),
                statistics.fmean(ofi3),
                statistics.fmean(book10),
                statistics.fmean(trade10),
                statistics.fmean(ofi10),
                math.log(mids[index] / mids[index - 1]) * 10_000.0,
                math.log(mids[index] / mids[index - 3]) * 10_000.0,
                math.log(mids[index] / mids[index - 10]) * 10_000.0,
                float(np.std(returns)),
                current.book_imbalance * current.trade_imbalance,
                current.book_imbalance * current.ofi,
                current.trade_imbalance * current.ofi,
                math.sin(2.0 * math.pi * hour / 24.0),
                math.cos(2.0 * math.pi * hour / 24.0),
                instrument_code,
            ]
        )
        indices.append(index)
    index_array = np.asarray(indices, dtype=int)
    return PreparedSegment(
        snapshots,
        index_array,
        np.asarray(features, dtype=float),
        feature_names,
        {int(index): pos for pos, index in enumerate(index_array)},
    )


def barrier_outcome(
    snapshots: list[OrderFlowSnapshot],
    entry_index: int,
    side: int,
    policy: BarrierPolicy,
    *,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
    max_gap_ms: int | None = None,
) -> BarrierOutcome | None:
    if entry_index + policy.max_hold_bars >= len(snapshots):
        return None
    slip = slippage_bps_per_side / 10_000.0
    entry_snapshot = snapshots[entry_index]
    entry_price = (
        entry_snapshot.ask * (1.0 + slip)
        if side > 0
        else entry_snapshot.bid * (1.0 - slip)
    )
    exit_index = entry_index + policy.max_hold_bars
    reason = "time_exit"
    for index in range(entry_index + 1, exit_index + 1):
        if max_gap_ms is not None and snapshots[index].ts - snapshots[index - 1].ts > max_gap_ms:
            exit_index = index
            reason = "gap"
            break
        raw_exit = snapshots[index].bid if side > 0 else snapshots[index].ask
        move_bps = side * (raw_exit / entry_price - 1.0) * 10_000.0
        if move_bps >= policy.take_profit_bps:
            exit_index = index
            reason = "take_profit"
            break
        if move_bps <= -policy.stop_loss_bps:
            exit_index = index
            reason = "stop_loss"
            break
    raw_exit = snapshots[exit_index].bid if side > 0 else snapshots[exit_index].ask
    exit_price = raw_exit * (1.0 - slip * side)
    gross_bps = side * (exit_price / entry_price - 1.0) * 10_000.0
    exit_fee_bps = fee_bps_per_side * exit_price / entry_price
    net_bps = gross_bps - fee_bps_per_side - exit_fee_bps
    return BarrierOutcome(net_bps, exit_index, reason)


def action_dataset(
    segments: dict[str, PreparedSegment],
    side: int,
    policy: BarrierPolicy,
    execution: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    features = []
    pnl = []
    for segment in segments.values():
        for pos, index in enumerate(segment.indices):
            entry_index = int(index)
            entry = segment.snapshots[entry_index]
            if entry.spread_bps > float(execution["max_spread_bps"]):
                continue
            if (
                entry_index > 0
                and entry.ts - segment.snapshots[entry_index - 1].ts > int(execution["max_gap_ms"])
            ):
                continue
            outcome = barrier_outcome(
                segment.snapshots,
                entry_index,
                side,
                policy,
                fee_bps_per_side=float(execution["fee_bps_per_side"]),
                slippage_bps_per_side=float(execution["slippage_bps_per_side"]),
                max_gap_ms=int(execution["max_gap_ms"]),
            )
            if outcome is None:
                continue
            features.append(segment.features[pos])
            pnl.append(outcome.net_pnl_bps)
    return np.asarray(features, dtype=float), np.asarray(pnl, dtype=float)


def fit_probability_bundle(
    model_kind: str,
    train_x: np.ndarray,
    train_pnl: np.ndarray,
    calibration_x: np.ndarray,
    calibration_pnl: np.ndarray,
) -> ProbabilityBundle:
    train_y = (train_pnl > 0).astype(int)
    calibration_y = (calibration_pnl > 0).astype(int)
    if model_kind == "hist_gradient_dynamic":
        classifier = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=100,
            max_depth=3,
            min_samples_leaf=80,
            l2_regularization=2.0,
            random_state=7,
        )
    elif model_kind == "logistic_static":
        classifier = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=0.20, max_iter=500, random_state=7),
        )
    else:
        raise ValueError(f"unknown model kind: {model_kind}")
    classifier.fit(train_x, train_y)
    raw_calibration = classifier.predict_proba(calibration_x)[:, 1]
    calibrator = None
    if len(np.unique(calibration_y)) > 1 and len(np.unique(raw_calibration)) > 5:
        calibrator = IsotonicRegression(
            y_min=0.01,
            y_max=0.99,
            out_of_bounds="clip",
        )
        calibrator.fit(raw_calibration, calibration_y)
    positive = train_pnl[train_pnl > 0]
    negative = np.abs(train_pnl[train_pnl <= 0])
    constant_win = float(np.mean(positive)) if len(positive) else 0.1
    constant_loss = float(np.mean(negative)) if len(negative) else 0.1
    win_model = loss_model = None
    if model_kind == "hist_gradient_dynamic" and len(positive) >= 200 and len(negative) >= 200:
        win_model = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=80,
            max_depth=3,
            min_samples_leaf=80,
            l2_regularization=2.0,
            random_state=11,
        ).fit(train_x[train_y == 1], positive)
        loss_model = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=80,
            max_depth=3,
            min_samples_leaf=80,
            l2_regularization=2.0,
            random_state=13,
        ).fit(train_x[train_y == 0], negative)
    return ProbabilityBundle(
        model_kind,
        classifier,
        calibrator,
        win_model,
        loss_model,
        constant_win,
        constant_loss,
    )


def predict_bundle(bundle: ProbabilityBundle, features: np.ndarray) -> ActionPrediction:
    raw_probability = bundle.classifier.predict_proba(features)[:, 1]
    probability = (
        bundle.calibrator.predict(raw_probability)
        if bundle.calibrator is not None
        else raw_probability
    )
    probability = np.clip(probability, 0.01, 0.99)
    if bundle.win_model is not None:
        win_bps = np.clip(bundle.win_model.predict(features), 0.1, 300.0)
        loss_bps = np.clip(bundle.loss_model.predict(features), 0.1, 300.0)
    else:
        win_bps = np.full(len(features), bundle.constant_win_bps)
        loss_bps = np.full(len(features), bundle.constant_loss_bps)
    payoff = win_bps / loss_bps
    expectancy = probability * win_bps - (1.0 - probability) * loss_bps
    return ActionPrediction(probability, win_bps, loss_bps, payoff, expectancy)


def predict_actions(
    segment: PreparedSegment,
    bundles: dict[tuple[int, str], ProbabilityBundle],
) -> dict[tuple[int, str], ActionPrediction]:
    return {
        action: predict_bundle(bundle, segment.features)
        for action, bundle in bundles.items()
    }


def select_model_and_threshold(
    validation: dict[str, PreparedSegment],
    predictions_by_kind: dict[str, dict[str, dict[tuple[int, str], ActionPrediction]]],
    execution: dict[str, Any],
) -> list[ModelSelection]:
    selections = []
    for model_kind, instrument_predictions in predictions_by_kind.items():
        candidates = []
        for threshold in (-20.0, -12.0, -8.0, -4.0, 0.0, 2.0, 4.0, 6.0, 8.0, 12.0):
            results = [
                simulate_dynamic_strategy(
                    validation[inst_id],
                    instrument_predictions[inst_id],
                    min_expectancy_bps=threshold,
                    **execution,
                ).base
                for inst_id in validation
            ]
            if min(result.trades for result in results) < 20:
                continue
            returns = [result.total_return_pct for result in results]
            expectancies = [result.expectancy_bps for result in results]
            score = (
                statistics.median(expectancies)
                + 0.75 * min(expectancies)
                - 0.25 * statistics.median(result.max_drawdown_pct for result in results)
            )
            candidates.append(
                ModelSelection(
                    model_kind,
                    threshold,
                    score,
                    statistics.median(returns),
                    min(returns),
                    statistics.median(expectancies),
                    statistics.median(result.profit_factor for result in results),
                    statistics.median(result.trades for result in results),
                )
            )
        if not candidates:
            raise ValueError(f"no validation threshold produced enough trades for {model_kind}")
        nonnegative_candidates = [item for item in candidates if item.min_expectancy_bps >= 0.0]
        selections.append(max(nonnegative_candidates or candidates, key=lambda item: item.score))
    selections.sort(
        key=lambda item: (item.min_expectancy_bps >= 0.0, item.score),
        reverse=True,
    )
    return selections


def simulate_dynamic_strategy(
    segment: PreparedSegment,
    predictions: dict[tuple[int, str], ActionPrediction],
    *,
    min_expectancy_bps: float,
    starting_equity: float,
    allocation_pct: float,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
    max_spread_bps: float,
    max_gap_ms: int,
    latency_bars: int = 0,
    record_trades: bool = False,
) -> MLSimulation:
    snapshots = segment.snapshots
    policies = {policy.name: policy for policy in POLICIES}
    fee_rate = fee_bps_per_side / 10_000.0
    slip_rate = slippage_bps_per_side / 10_000.0
    cash_equity = starting_equity
    peak_equity = starting_equity
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    cooldown_until = -1
    ml_trades: list[MLTrade] = []

    def mark_equity(snapshot: OrderFlowSnapshot) -> float:
        if position is None:
            return cash_equity
        raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
        exit_price = raw_exit * (1.0 - slip_rate * position["side"])
        gross = position["side"] * (exit_price - position["entry_price"]) * position["units"]
        return cash_equity + gross - exit_price * position["units"] * fee_rate

    def update_drawdown(snapshot: OrderFlowSnapshot) -> None:
        nonlocal peak_equity, max_drawdown
        equity = mark_equity(snapshot)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100.0)

    def close(index: int, reason: str) -> None:
        nonlocal position, cash_equity, cooldown_until
        if position is None:
            return
        snapshot = snapshots[index]
        raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
        exit_price = raw_exit * (1.0 - slip_rate * position["side"])
        gross = position["side"] * (exit_price - position["entry_price"]) * position["units"]
        exit_fee = exit_price * position["units"] * fee_rate
        cash_equity += gross - exit_fee
        net_bps = (gross - exit_fee - position["entry_fee"]) / position["notional"] * 10_000.0
        trade = OrderFlowTrade(
            position["entry_ts"],
            snapshot.ts,
            position["side"],
            position["predicted_probability"],
            position["entry_price"],
            exit_price,
            reason,
            index - position["entry_index"],
            net_bps,
            position["mae_bps"],
            position["mfe_bps"],
        )
        ml_trades.append(
            MLTrade(
                trade,
                position["policy"].name,
                position["predicted_probability"],
                position["predicted_win_bps"],
                position["predicted_loss_bps"],
                position["predicted_payoff_ratio"],
                position["predicted_expectancy_bps"],
            )
        )
        position = None
        cooldown_until = index + 1

    for index, snapshot in enumerate(snapshots):
        gap = snapshot.ts - snapshots[index - 1].ts if index > 0 else 0
        if position is not None:
            raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
            move_bps = position["side"] * (raw_exit / position["entry_price"] - 1.0) * 10_000.0
            position["mae_bps"] = min(position["mae_bps"], move_bps)
            position["mfe_bps"] = max(position["mfe_bps"], move_bps)
            reason = ""
            if index > position["entry_index"] and gap > max_gap_ms:
                reason = "gap"
            elif move_bps >= position["policy"].take_profit_bps:
                reason = "take_profit"
            elif move_bps <= -position["policy"].stop_loss_bps:
                reason = "stop_loss"
            elif index - position["entry_index"] >= position["policy"].max_hold_bars:
                reason = "time_exit"
            if reason:
                close(index, reason)
        update_drawdown(snapshot)
        if position is not None or index >= len(snapshots) - 1 or index < cooldown_until:
            continue
        signal_index = index - latency_bars
        signal_pos = segment.positions.get(signal_index)
        if signal_pos is None or (index > 0 and gap > max_gap_ms):
            continue
        if snapshot.ts - snapshots[signal_index].ts > max_gap_ms:
            continue
        if snapshot.spread_bps > max_spread_bps:
            continue
        choices = []
        for (side, policy_name), prediction in predictions.items():
            expectancy = float(prediction.expectancy_bps[signal_pos])
            if expectancy < min_expectancy_bps:
                continue
            choices.append((expectancy, side, policy_name, prediction))
        if not choices:
            continue
        expectancy, side, policy_name, prediction = max(choices, key=lambda item: item[0])
        policy = policies[policy_name]
        entry_price = snapshot.ask * (1.0 + slip_rate) if side > 0 else snapshot.bid * (1.0 - slip_rate)
        notional = cash_equity * allocation_pct / 100.0
        if entry_price <= 0 or notional <= 0:
            continue
        entry_fee = notional * fee_rate
        cash_equity -= entry_fee
        position = {
            "side": side,
            "policy": policy,
            "entry_index": index,
            "entry_ts": snapshot.ts,
            "entry_price": entry_price,
            "notional": notional,
            "units": notional / entry_price,
            "entry_fee": entry_fee,
            "predicted_probability": float(prediction.probability[signal_pos]),
            "predicted_win_bps": float(prediction.win_bps[signal_pos]),
            "predicted_loss_bps": float(prediction.loss_bps[signal_pos]),
            "predicted_payoff_ratio": float(prediction.payoff_ratio[signal_pos]),
            "predicted_expectancy_bps": expectancy,
            "mae_bps": 0.0,
            "mfe_bps": 0.0,
        }
        update_drawdown(snapshot)
    if position is not None:
        close(len(snapshots) - 1, "time_exit")
        update_drawdown(snapshots[-1])

    base = summarize_trades(
        [item.trade for item in ml_trades],
        starting_equity,
        cash_equity,
        max_drawdown,
        record_trades=record_trades,
    )
    probabilities = [item.predicted_probability for item in ml_trades]
    outcomes = [1.0 if item.trade.net_pnl_bps > 0 else 0.0 for item in ml_trades]
    clipped = [min(0.999, max(0.001, value)) for value in probabilities]
    brier = statistics.fmean((probability - outcome) ** 2 for probability, outcome in zip(clipped, outcomes)) if outcomes else 0.0
    log_loss = -statistics.fmean(
        outcome * math.log(probability) + (1.0 - outcome) * math.log(1.0 - probability)
        for probability, outcome in zip(clipped, outcomes)
    ) if outcomes else 0.0
    policy_counts: dict[str, int] = {}
    for item in ml_trades:
        policy_counts[item.policy] = policy_counts.get(item.policy, 0) + 1
    return MLSimulation(
        base,
        statistics.fmean(probabilities) if probabilities else 0.0,
        statistics.fmean(item.predicted_payoff_ratio for item in ml_trades) if ml_trades else 0.0,
        statistics.fmean(item.predicted_expectancy_bps for item in ml_trades) if ml_trades else 0.0,
        brier,
        log_loss,
        ((statistics.fmean(probabilities) - statistics.fmean(outcomes)) * 100.0) if outcomes else 0.0,
        policy_counts,
        ml_trades if record_trades else [],
    )


def ml_result_row(
    inst_id: str,
    segment: str,
    variant: str,
    model_kind: str,
    selection: ModelSelection,
    simulation: MLSimulation,
) -> dict[str, Any]:
    base = simulation.base
    return {
        "inst_id": inst_id,
        "segment": segment,
        "variant": variant,
        "model_kind": model_kind,
        "min_expectancy_bps": selection.min_expectancy_bps,
        "trades": base.trades,
        "win_rate_pct": base.win_rate_pct,
        "average_win_bps": base.average_win_bps,
        "average_loss_bps": base.average_loss_bps,
        "payoff_ratio": base.payoff_ratio,
        "breakeven_win_rate_pct": base.breakeven_win_rate_pct,
        "expectancy_bps": base.expectancy_bps,
        "profit_factor": base.profit_factor,
        "total_return_pct": base.total_return_pct,
        "max_drawdown_pct": base.max_drawdown_pct,
        "max_consecutive_losses": base.max_consecutive_losses,
        "mean_predicted_probability_pct": simulation.mean_predicted_probability * 100.0,
        "mean_predicted_payoff_ratio": simulation.mean_predicted_payoff_ratio,
        "mean_predicted_expectancy_bps": simulation.mean_predicted_expectancy_bps,
        "brier_score": simulation.brier_score,
        "log_loss": simulation.log_loss,
        "calibration_gap_pct": simulation.calibration_gap_pct,
    }


def baseline_result_row(inst_id: str, result: Any) -> dict[str, Any]:
    return {
        "inst_id": inst_id,
        "segment": "test",
        "variant": "fixed_rule_baseline",
        "model_kind": "none",
        "min_expectancy_bps": 0.0,
        "trades": result.trades,
        "win_rate_pct": result.win_rate_pct,
        "average_win_bps": result.average_win_bps,
        "average_loss_bps": result.average_loss_bps,
        "payoff_ratio": result.payoff_ratio,
        "breakeven_win_rate_pct": result.breakeven_win_rate_pct,
        "expectancy_bps": result.expectancy_bps,
        "profit_factor": result.profit_factor,
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "max_consecutive_losses": result.max_consecutive_losses,
        "mean_predicted_probability_pct": 0.0,
        "mean_predicted_payoff_ratio": 0.0,
        "mean_predicted_expectancy_bps": 0.0,
        "brier_score": 0.0,
        "log_loss": 0.0,
        "calibration_gap_pct": 0.0,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["segment"], row["variant"]), []).append(row)
    result = []
    for (segment, variant), items in grouped.items():
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "count": len(items),
                "positive": sum(float(item["total_return_pct"]) > 0 for item in items),
                "median_return_pct": statistics.median(float(item["total_return_pct"]) for item in items),
                "worst_return_pct": min(float(item["total_return_pct"]) for item in items),
                "median_expectancy_bps": statistics.median(float(item["expectancy_bps"]) for item in items),
                "median_profit_factor": statistics.median(float(item["profit_factor"]) for item in items),
                "median_win_rate_pct": statistics.median(float(item["win_rate_pct"]) for item in items),
                "median_payoff_ratio": statistics.median(float(item["payoff_ratio"]) for item in items),
                "median_predicted_probability_pct": statistics.median(float(item["mean_predicted_probability_pct"]) for item in items),
                "median_predicted_payoff_ratio": statistics.median(float(item["mean_predicted_payoff_ratio"]) for item in items),
                "median_predicted_expectancy_bps": statistics.median(float(item["mean_predicted_expectancy_bps"]) for item in items),
                "median_brier_score": statistics.median(float(item["brier_score"]) for item in items),
                "median_calibration_gap_pct": statistics.median(float(item["calibration_gap_pct"]) for item in items),
                "worst_drawdown_pct": max(float(item["max_drawdown_pct"]) for item in items),
                "total_trades": sum(int(item["trades"]) for item in items),
            }
        )
    result.sort(key=lambda item: (item["segment"], item["variant"]))
    return result


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
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["min_expectancy_bps"]) >= 0.0 for row in test_rows)
        and all(float(row["profit_factor"]) >= 1.10 for row in test_rows)
        and all(abs(float(row["calibration_gap_pct"])) <= 5.0 for row in test_rows)
        and all(int(row["trades"]) >= 30 for row in test_rows)
        and test["worst_drawdown_pct"] <= 3.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedHistory": quantitative_pass,
        "requiresFreshWebSocketForwardData": True,
        "liveAuthorized": False,
        "rule": (
            "复用历史不能授权仿真或实盘。未来WebSocket点时样本还必须满足验证、测试、成本和延迟均盈利，"
            "PF>=1.10、概率校准误差不超过5个百分点、每标的不少于30笔且最差回撤<=3%。"
        ),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedModel"]
    lookup = {(item["segment"], item["variant"]): item for item in payload["aggregates"]}
    period = payload["period"]
    lines = [
        "# BTC/ETH 订单流机器学习动态胜率与盈亏比",
        "",
        "> 探索性复用历史；前一轮已看过同一最终区间，因此本报告不能授权仿真或实盘。",
        "",
        "## 方法",
        "",
        "- 每个方向和四组 TP/SL/持有期分别建立三重障碍标签；分类器估计净盈利概率。",
        "- 梯度提升版本另行估计条件平均盈利和条件平均亏损，动态盈亏比为 `E[win|x]/E[loss|x]`。",
        "- 动态净期望为 `p*E[win|x]-(1-p)*E[loss|x]`；低于验证选定门槛时不交易。",
        "- 前40%拟合、随后10%只做概率校准、再25%选择模型与期望门槛、最后25%作探索性复用测试。",
        "- 交易仍按可成交 bid/ask、双边Taker费和滑点计算；每笔20%权益、无杠杆。",
        "",
        "## 论文与开源方案",
        "",
        "- DeepLOB，DOI `10.1109/TSP.2019.2907260`：适合密集L2事件张量；当前REST数据与环境不满足。",
        "- Deep Order Flow Imbalance，DOI `10.1111/mafi.12413`：支持多尺度OFI，但仍依赖事件级数据。",
        "- Niculescu-Mizil and Caruana，DOI `10.1145/1102351.1102430`：概率校准依据。",
        "- Price Impact of Order Book Events，DOI `10.1093/jjfinec/nbt003`；Queue Imbalance，DOI `10.1142/S2382626616500064`：解释OFI/队列不平衡的短期价格影响。",
        "- scikit-learn（BSD-3-Clause）：实际测试梯度提升、逻辑回归和Isotonic校准。",
        "- FreqAI（GPL-3.0）适合交易管线，但不能补足当前缺失的逐事件L2数据，未引入运行时。",
        "- hftbacktest（MIT）适合未来逐事件回放和队列模型；NautilusTrader（LGPL-3.0）可作为后续事件驱动管线。",
        "- 多数DeepLOB复现仓库未声明许可证；没有复制其代码。mlfinlab仅借鉴三重障碍概念。",
        "",
        "## 数据与选择",
        "",
        f"- 区间：`{period['start']}` 至 `{period['end']}`。",
        f"- 验证选择：`{selected['model_kind']}`，最低预测净期望 {selected['min_expectancy_bps']:.1f} bps。",
        "- 如果该门槛为负，表示非负预测期望下没有足够交易；结果仅是强制交易诊断，不构成策略。",
        f"- 验证中位收益 {selected['median_return_pct']:.4f}%，中位实际期望 {selected['median_expectancy_bps']:.3f} bps，PF {selected['median_profit_factor']:.3f}。",
        "",
        "## 主模型",
        "",
        "| 区间 | 正收益 | 中位收益 | 实际胜率 | 实际盈亏比 | 实际期望 | PF | 预测胜率 | 预测盈亏比 | 预测期望 | 校准差 | Brier | 交易 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for segment, label in (("validation", "验证"), ("test", "复用测试")):
        item = lookup[(segment, "selected")]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_win_rate_pct']:.2f}% | {item['median_payoff_ratio']:.3f} | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | "
            f"{item['median_predicted_probability_pct']:.2f}% | {item['median_predicted_payoff_ratio']:.3f} | "
            f"{item['median_predicted_expectancy_bps']:.3f} bps | {item['median_calibration_gap_pct']:.2f} pct | "
            f"{item['median_brier_score']:.4f} | {item['total_trades']} |"
        )
    lines.extend(
        [
            "",
            "## 复用测试比较",
            "",
            "| 版本 | 正收益 | 中位收益 | 实际期望 | PF | 胜率 | 盈亏比 | 预测期望 | 校准差 | 最差回撤 | 交易 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    variants = [
        ("selected", "动态概率+动态盈亏比"),
        ("logistic_static", "校准逻辑回归+静态盈亏比"),
        ("hist_gradient_dynamic", "校准梯度提升+动态盈亏比"),
        ("cost_stress", "成本压力"),
        ("one_snapshot_latency", "延迟一张快照"),
        ("no_abstention", "不允许空仓"),
        ("fixed_rule_baseline", "原固定规则"),
    ]
    seen = set()
    for variant, label in variants:
        key = ("test", variant)
        if key not in lookup or variant in seen:
            continue
        seen.add(variant)
        item = lookup[key]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_profit_factor']:.3f} | "
            f"{item['median_win_rate_pct']:.2f}% | {item['median_payoff_ratio']:.3f} | "
            f"{item['median_predicted_expectancy_bps']:.3f} bps | {item['median_calibration_gap_pct']:.2f} pct | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    test_rows = [row for row in payload["rows"] if row["segment"] == "test" and row["variant"] == "selected"]
    lines.extend(
        [
            "",
            "## 复用测试逐标的",
            "",
            "| 标的 | 交易 | 收益 | 实际胜率 | 预测胜率 | 实际盈亏比 | 预测盈亏比 | 实际期望 | 预测期望 | PF | 校准差 | 最大连亏 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in test_rows:
        lines.append(
            f"| {row['inst_id']} | {row['trades']} | {row['total_return_pct']:.4f}% | "
            f"{row['win_rate_pct']:.2f}% | {row['mean_predicted_probability_pct']:.2f}% | "
            f"{row['payoff_ratio']:.3f} | {row['mean_predicted_payoff_ratio']:.3f} | "
            f"{row['expectancy_bps']:.3f} bps | {row['mean_predicted_expectancy_bps']:.3f} bps | "
            f"{row['profit_factor']:.3f} | {row['calibration_gap_pct']:.2f} pct | {row['max_consecutive_losses']} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            "- **仅研究**。",
            f"- 复用历史量化准入：`{str(decision['quantitativePassOnReusedHistory']).lower()}`。",
            f"- {decision['rule']}",
            "- 没有读取账户、启动服务、安装未经审核的第三方交易框架或发送订单。",
        ]
    )
    return "\n".join(lines) + "\n"


def ml_trade_payload(inst_id: str, item: MLTrade) -> dict[str, Any]:
    return {
        "inst_id": inst_id,
        "entry": iso_time(item.trade.entry_ts),
        "exit": iso_time(item.trade.exit_ts),
        "side": "long" if item.trade.side > 0 else "short",
        "policy": item.policy,
        "predicted_probability": item.predicted_probability,
        "predicted_win_bps": item.predicted_win_bps,
        "predicted_loss_bps": item.predicted_loss_bps,
        "predicted_payoff_ratio": item.predicted_payoff_ratio,
        "predicted_expectancy_bps": item.predicted_expectancy_bps,
        "realized_net_pnl_bps": item.trade.net_pnl_bps,
        "exit_reason": item.trade.exit_reason,
        "hold_bars": item.trade.hold_bars,
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


def iso_time(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
