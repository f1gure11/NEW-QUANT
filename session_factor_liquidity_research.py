"""Read-only session-specialized factor and liquidity-provision research.

Americas regular hours use filtered short-horizon directional factors.  All
other timestamps use a separately selected slow-VWAP passive maker proxy.  The
two legs are selected independently on chronological data and are always flat
at their session boundary.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from backtest.okx_grid_backtest import BAR_MS, Candle, read_candles_csv
from expanded_factor_research import ExpandedSegment, prepare_segment
from factor_filter_cycle_research import (
    BASE_MAX_GAP_MS,
    MIN_SELECTION_TRADES_PER_INSTRUMENT,
    NEW_YORK,
    RIDGE_ALPHA,
    causal_ewma,
    causal_kalman,
    market_session,
    mrmr_select,
    parse_iso_time,
    period_boundaries,
    selection_score,
    stability_elasticnet_select,
    stable_ic_select,
    truncate_histories,
)
from orderflow_rr_research import (
    DEFAULT_INSTRUMENTS,
    INPUT_ROOT,
    OrderFlowSnapshot,
    StrategyCandidate,
    aggregate_rows,
    load_snapshot_history,
    result_row,
    simulate_strategy,
    time_slice,
)
from vwap_market_maker_research import (
    DATA_ROOT as MAKER_DATA_ROOT,
    MakerExecutionConfig,
    VwapMakerParams,
    aggregate_rows as aggregate_maker_rows,
    result_row as maker_result_row,
    rolling_vwap_features,
    run_market_maker_backtest,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "session_factor_liquidity"
FILTER_METHODS = ("all_ridge", "stable_ic", "mrmr", "stability_elasticnet")
SMOOTHERS = ("raw", "causal_ewma", "causal_kalman")
SHORT_MAX_FEATURES = 8
MAKER_BAR = "5m"
MAKER_CONTEXT_BARS = 600
MAKER_PREFILTER_COUNT = 12


@dataclass(frozen=True, slots=True)
class AmericasProfile:
    name: str
    max_lookback: int
    forecast_bars: int
    take_profit_bps: float
    stop_loss_bps: float
    max_hold_bars: int

    def strategy(self) -> StrategyCandidate:
        return StrategyCandidate(
            "trade_flow_momentum",
            0.15,
            self.take_profit_bps,
            self.stop_loss_bps,
            self.max_hold_bars,
        )


AMERICAS_PROFILES = (
    AmericasProfile("micro_15", 15, 10, 40.0, 25.0, 15),
    AmericasProfile("short_30", 30, 15, 60.0, 35.0, 30),
    AmericasProfile("short_60", 60, 30, 80.0, 45.0, 45),
    AmericasProfile("original_240_control", 240, 60, 100.0, 60.0, 90),
)


@dataclass(frozen=True, slots=True)
class AmericasCandidate:
    profile: AmericasProfile
    filter_method: str
    smoother: str

    @property
    def candidate_id(self) -> str:
        return f"{self.profile.name}__{self.filter_method}__{self.smoother}"


@dataclass(slots=True)
class AmericasBundle:
    candidate: AmericasCandidate
    selected_indices: np.ndarray
    selected_names: list[str]
    model: Any
    prediction_scale_bps: float
    normalized_coefficients: dict[str, float]
    diagnostics: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only session-specialized BTC/ETH research")
    parser.add_argument("--input-root", default=str(INPUT_ROOT))
    parser.add_argument("--maker-data-root", default=str(MAKER_DATA_ROOT))
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--end-time", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--allocation-pct", type=float, default=20.0)
    parser.add_argument("--fee-bps-per-side", type=float, default=5.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=1.0)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    return parser.parse_args()


def feature_lookback(name: str) -> int:
    windows = [int(value) for value in re.findall(r"\d+", name)]
    return max(windows, default=1)


def same_americas_window(
    snapshots: list[OrderFlowSnapshot],
    index: int,
    lookback: int,
    forecast_bars: int = 0,
) -> bool:
    left = index - lookback
    future = index + forecast_bars
    if left < 0 or future >= len(snapshots):
        return False
    current_time = datetime.fromtimestamp(snapshots[index].ts / 1_000.0, timezone.utc).astimezone(NEW_YORK)
    left_time = datetime.fromtimestamp(snapshots[left].ts / 1_000.0, timezone.utc).astimezone(NEW_YORK)
    future_time = datetime.fromtimestamp(snapshots[future].ts / 1_000.0, timezone.utc).astimezone(NEW_YORK)
    if not (
        market_session(snapshots[left].ts) == "americas"
        and market_session(snapshots[index].ts) == "americas"
        and market_session(snapshots[future].ts) == "americas"
        and left_time.date() == current_time.date() == future_time.date()
    ):
        return False
    lookback_elapsed = snapshots[index].ts - snapshots[left].ts
    forecast_elapsed = snapshots[future].ts - snapshots[index].ts
    return (
        0 < lookback_elapsed <= lookback * BASE_MAX_GAP_MS
        and (
            forecast_bars == 0
            or 0 < forecast_elapsed <= forecast_bars * BASE_MAX_GAP_MS
        )
    )


def prepare_snapshot_segments(
    histories: dict[str, list[OrderFlowSnapshot]],
    instruments: tuple[str, ...],
    boundaries: dict[str, tuple[int, int]],
) -> dict[str, dict[str, ExpandedSegment]]:
    return {
        inst_id: {
            segment: prepare_segment(
                time_slice(histories[inst_id], start, end),
                instrument_code=1.0 if inst_id.startswith("BTC") else 0.0,
            )
            for segment, (start, end) in boundaries.items()
        }
        for inst_id in instruments
    }


def americas_training_arrays(
    segments: dict[str, ExpandedSegment], profile: AmericasProfile
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    names = list(next(iter(segments.values())).feature_names)
    allowed = np.asarray(
        [index for index, name in enumerate(names) if feature_lookback(name) <= profile.max_lookback],
        dtype=int,
    )
    rows: list[tuple[int, np.ndarray, float]] = []
    for segment in segments.values():
        for position, index_value in enumerate(segment.indices):
            index = int(index_value)
            if not same_americas_window(
                segment.snapshots,
                index,
                profile.max_lookback,
                profile.forecast_bars,
            ):
                continue
            future = index + profile.forecast_bars
            target = math.log(segment.snapshots[future].mid / segment.snapshots[index].mid) * 10_000.0
            rows.append(
                (
                    segment.snapshots[index].ts,
                    segment.features[position, allowed],
                    max(-500.0, min(500.0, target)),
                )
            )
    if len(rows) < 1_000:
        raise ValueError(f"insufficient Americas training rows for {profile.name}: {len(rows)}")
    rows.sort(key=lambda item: item[0])
    minimum_ts, maximum_ts = rows[0][0], rows[-1][0]
    span = max(1, maximum_ts - minimum_ts)
    blocks = np.asarray(
        [min(3, int((timestamp - minimum_ts) * 4 / span)) for timestamp, _, _ in rows],
        dtype=int,
    )
    return (
        np.asarray([item[1] for item in rows], dtype=float),
        np.asarray([item[2] for item in rows], dtype=float),
        blocks,
        allowed,
        names,
    )


def filtered_indices(
    method: str, values: np.ndarray, targets: np.ndarray, blocks: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    limit = min(SHORT_MAX_FEATURES, values.shape[1])
    if method == "all_ridge":
        return np.arange(values.shape[1], dtype=int), {"selectedAllAllowed": True}
    if method == "stable_ic":
        return stable_ic_select(values, targets, blocks, max_features=limit)
    if method == "mrmr":
        return mrmr_select(values, targets, max_features=limit)
    if method == "stability_elasticnet":
        return stability_elasticnet_select(values, targets, blocks, max_features=limit)
    raise ValueError(f"unknown factor filter: {method}")


def fit_americas_bundle(
    candidate: AmericasCandidate, training: dict[str, ExpandedSegment]
) -> AmericasBundle:
    values, targets, blocks, allowed, names = americas_training_arrays(training, candidate.profile)
    local_indices, diagnostics = filtered_indices(candidate.filter_method, values, targets, blocks)
    selected_indices = allowed[local_indices]
    model = make_pipeline(StandardScaler(), Ridge(alpha=RIDGE_ALPHA))
    model.fit(values[:, local_indices], targets)
    predictions = model.predict(values[:, local_indices])
    scale = max(float(np.percentile(np.abs(predictions), 75)), 5.0)
    coefficients = np.asarray(model[-1].coef_, dtype=float)
    denominator = float(np.sum(np.abs(coefficients)))
    selected_names = [names[index] for index in selected_indices]
    normalized = {
        name: (float(value) / denominator if denominator > 0 else 0.0)
        for name, value in zip(selected_names, coefficients)
    }
    return AmericasBundle(
        candidate,
        selected_indices,
        selected_names,
        model,
        scale,
        normalized,
        {
            **diagnostics,
            "allowedFeatureCount": len(allowed),
            "selectedCount": len(selected_names),
            "trainingRows": len(targets),
        },
    )


def smooth_values(values: np.ndarray, method: str) -> np.ndarray:
    if method == "raw":
        return values
    if method == "causal_ewma":
        return causal_ewma(values)
    if method == "causal_kalman":
        return causal_kalman(values)
    raise ValueError(f"unknown smoother: {method}")


def score_americas_segment(
    segment: ExpandedSegment, bundle: AmericasBundle
) -> list[OrderFlowSnapshot]:
    if not len(segment.features):
        return list(segment.snapshots)
    predictions = bundle.model.predict(segment.features[:, bundle.selected_indices])
    raw = np.tanh(predictions / bundle.prediction_scale_bps)
    sessions: dict[str, list[tuple[int, int]]] = {}
    for position, index_value in enumerate(segment.indices):
        index = int(index_value)
        if not same_americas_window(
            segment.snapshots,
            index,
            bundle.candidate.profile.max_lookback,
        ):
            continue
        local = datetime.fromtimestamp(
            segment.snapshots[index].ts / 1_000.0, timezone.utc
        ).astimezone(NEW_YORK)
        sessions.setdefault(local.date().isoformat(), []).append((position, index))
    by_index: dict[int, float] = {}
    for pairs in sessions.values():
        smoothed = smooth_values(
            np.asarray([raw[position] for position, _ in pairs], dtype=float),
            bundle.candidate.smoother,
        )
        by_index.update(
            {index: float(smoothed[position]) for position, (_, index) in enumerate(pairs)}
        )
    return [replace(row, trade_imbalance=by_index.get(index, 0.0)) for index, row in enumerate(segment.snapshots)]


def americas_result_row(
    inst_id: str,
    segment: str,
    variant: str,
    result: Any,
    bundle: AmericasBundle,
) -> dict[str, Any]:
    profile = bundle.candidate.profile
    row = result_row(inst_id, segment, variant, profile.strategy(), result)
    row.update(
        {
            "candidate_id": bundle.candidate.candidate_id,
            "profile": profile.name,
            "max_lookback": profile.max_lookback,
            "forecast_bars": profile.forecast_bars,
            "filter_method": bundle.candidate.filter_method,
            "smoother": bundle.candidate.smoother,
            "selected_features": len(bundle.selected_names),
        }
    )
    return row


def americas_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregates = aggregate_rows(rows)
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    summaries = []
    for candidate_id in sorted({str(row["candidate_id"]) for row in rows}):
        selection_rows = [
            row for row in rows if row["segment"] == "selection" and row["variant"] == candidate_id
        ]
        if len(selection_rows) < 2:
            continue
        first = selection_rows[0]
        minimum_trades = min(int(row["trades"]) for row in selection_rows)
        item = {
            "candidateId": candidate_id,
            "profile": first["profile"],
            "maxLookback": int(first["max_lookback"]),
            "forecastBars": int(first["forecast_bars"]),
            "filterMethod": first["filter_method"],
            "smoother": first["smoother"],
            "selectedFeatures": int(first["selected_features"]),
            "minimumSelectionTrades": minimum_trades,
            "selectionEligible": minimum_trades >= MIN_SELECTION_TRADES_PER_INSTRUMENT,
            "selectionScore": selection_score(selection_rows),
        }
        for segment in ("selection", "validation", "test"):
            item[segment] = lookup[(segment, candidate_id)]
        summaries.append(item)
    summaries.sort(key=lambda item: item["selectionScore"], reverse=True)
    return summaries


def run_americas_research(
    prepared: dict[str, dict[str, ExpandedSegment]],
    instruments: tuple[str, ...],
    execution: dict[str, Any],
) -> dict[str, Any]:
    training = {inst_id: prepared[inst_id]["model_train"] for inst_id in instruments}
    rows: list[dict[str, Any]] = []
    bundles: dict[str, AmericasBundle] = {}
    active = lambda snapshot: market_session(snapshot.ts) == "americas"
    for profile in AMERICAS_PROFILES:
        for filter_method in FILTER_METHODS:
            for smoother in SMOOTHERS:
                candidate = AmericasCandidate(profile, filter_method, smoother)
                bundle = fit_americas_bundle(candidate, training)
                bundles[candidate.candidate_id] = bundle
                for segment_name in ("selection", "validation", "test"):
                    for inst_id in instruments:
                        scored = score_americas_segment(prepared[inst_id][segment_name], bundle)
                        simulation = simulate_strategy(
                            scored,
                            profile.strategy(),
                            **execution,
                            active_predicate=active,
                        )
                        rows.append(
                            americas_result_row(
                                inst_id,
                                segment_name,
                                candidate.candidate_id,
                                simulation,
                                bundle,
                            )
                        )
    summaries = americas_summaries(rows)
    selected = next((item for item in summaries if item["selectionEligible"]), None)
    stress_rows: list[dict[str, Any]] = []
    if selected is not None:
        bundle = bundles[selected["candidateId"]]
        profile = bundle.candidate.profile
        for inst_id in instruments:
            segment = prepared[inst_id]["test"]
            scored = score_americas_segment(segment, bundle)
            for variant, kwargs, latency in (
                (
                    "selected_cost_stress",
                    {**execution, "fee_bps_per_side": 8.0, "slippage_bps_per_side": 2.0},
                    0,
                ),
                ("selected_one_bar_latency", execution, 1),
            ):
                simulation = simulate_strategy(
                    scored,
                    profile.strategy(),
                    **kwargs,
                    latency_bars=latency,
                    active_predicate=active,
                )
                stress_rows.append(americas_result_row(inst_id, "test", variant, simulation, bundle))
        rows.extend(stress_rows)
    aggregates = aggregate_rows(rows)
    decision = americas_decision(rows, aggregates, selected)
    return {
        "candidateCount": len(summaries),
        "eligibleCandidateCount": sum(item["selectionEligible"] for item in summaries),
        "positiveValidationCandidateCount": sum(
            item["validation"]["median_return_pct"] > 0 for item in summaries
        ),
        "positiveTestCandidateCount": sum(
            item["test"]["median_return_pct"] > 0 for item in summaries
        ),
        "maximumMinimumSelectionTrades": max(
            (item["minimumSelectionTrades"] for item in summaries), default=0
        ),
        "exploratoryLeader": summaries[0] if summaries else None,
        "selectedCandidate": selected,
        "selectedFeatureNames": bundles[selected["candidateId"]].selected_names if selected else [],
        "selectedFeatureWeights": bundles[selected["candidateId"]].normalized_coefficients if selected else {},
        "selectedDiagnostics": bundles[selected["candidateId"]].diagnostics if selected else {},
        "candidateSummaries": summaries,
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }


def americas_decision(
    rows: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    selected: dict[str, Any] | None,
) -> dict[str, Any]:
    if selected is None:
        return {
            "status": "research_only",
            "quantitativeGatePassedOnReusedHistory": False,
            "reason": "no candidate met the minimum selection trades per instrument",
        }
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    candidate_id = selected["candidateId"]
    validation = lookup[("validation", candidate_id)]
    test = lookup[("test", candidate_id)]
    stress = lookup[("test", "selected_cost_stress")]
    latency = lookup[("test", "selected_one_bar_latency")]
    test_rows = [
        row for row in rows if row["segment"] == "test" and row["variant"] == candidate_id
    ]
    passed = (
        validation["positive"] == validation["count"]
        and validation["median_expectancy_bps"] > 0
        and test["positive"] == test["count"]
        and test["median_profit_factor"] >= 1.10
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and min(int(row["trades"]) for row in test_rows) >= 12
    )
    return {
        "status": "research_only",
        "quantitativeGatePassedOnReusedHistory": passed,
        "selectedCandidate": candidate_id,
        "validationMedianReturnPct": validation["median_return_pct"],
        "testMedianReturnPct": test["median_return_pct"],
        "testMedianProfitFactor": test["median_profit_factor"],
        "costStressMedianReturnPct": stress["median_return_pct"],
        "latencyMedianReturnPct": latency["median_return_pct"],
    }


def slow_maker_grid() -> list[VwapMakerParams]:
    return [
        VwapMakerParams(
            vwap_window=window,
            anchor_weight=anchor,
            min_half_spread_bps=half_spread,
            volatility_multiplier=volatility_multiplier,
            inventory_skew_bps=inventory_skew,
            max_vwap_slope_bps=max_slope,
        )
        for window, anchor, half_spread, volatility_multiplier, inventory_skew, max_slope in product(
            (144, 288, 576),
            (0.25, 0.50),
            (5.0, 10.0),
            (0.5, 1.0),
            (10.0, 25.0),
            (20.0, 50.0),
        )
    ]


def maker_candidate_id(params: VwapMakerParams) -> str:
    return (
        f"vwap_{params.vwap_window}__anchor_{params.anchor_weight:.2f}__"
        f"half_{params.min_half_spread_bps:.0f}__vol_{params.volatility_multiplier:.1f}__"
        f"skew_{params.inventory_skew_bps:.0f}__slope_{params.max_vwap_slope_bps:.0f}"
    )


def load_maker_histories(
    root: Path,
    instruments: tuple[str, ...],
    start_ms: int,
    end_ms: int,
) -> tuple[dict[str, list[Candle]], dict[str, str]]:
    histories: dict[str, list[Candle]] = {}
    sources: dict[str, str] = {}
    for inst_id in instruments:
        path = root / f"{inst_id}_{MAKER_BAR}_300x48.csv"
        if not path.exists():
            raise SystemExit(f"Missing frozen maker candle cache: {path}")
        rows = [row for row in read_candles_csv(path) if start_ms <= row.ts <= end_ms]
        if len(rows) < 4_000:
            raise SystemExit(f"Insufficient frozen maker candles for {inst_id}: {len(rows)}")
        histories[inst_id] = rows
        sources[inst_id] = str(path)
    common_start = max(rows[0].ts for rows in histories.values())
    common_end = min(rows[-1].ts for rows in histories.values())
    histories = {
        inst_id: [row for row in rows if common_start <= row.ts <= common_end]
        for inst_id, rows in histories.items()
    }
    return histories, sources


def maker_context(
    rows: list[Candle], start_ms: int, end_ms: int, context_bars: int = MAKER_CONTEXT_BARS
) -> list[Candle]:
    start_position = next((index for index, row in enumerate(rows) if row.ts >= start_ms), len(rows))
    context_start = max(0, start_position - context_bars)
    return [row for row in rows[context_start:] if row.ts <= end_ms]


def maker_active_predicate(start_ms: int, end_ms: int):
    return lambda candle: (
        start_ms <= candle.ts <= end_ms and market_session(candle.ts) == "non_americas"
    )


def stressed_maker_execution(execution: MakerExecutionConfig) -> MakerExecutionConfig:
    return replace(
        execution,
        maker_fee_bps=max(5.0, execution.maker_fee_bps * 2.5),
        taker_fee_bps=max(8.0, execution.taker_fee_bps * 1.6),
        taker_slippage_bps=max(2.0, execution.taker_slippage_bps * 2.0),
        holding_cost_bps_per_day=max(1.0, execution.holding_cost_bps_per_day * 2.0),
    )


def maker_metrics(
    params: VwapMakerParams,
    histories: dict[str, list[Candle]],
    instruments: tuple[str, ...],
    bounds: tuple[int, int],
    execution: MakerExecutionConfig,
) -> dict[str, Any]:
    start_ms, end_ms = bounds
    predicate = maker_active_predicate(start_ms, end_ms)
    stressed_params = replace(params, penetration_bps=max(2.0, params.penetration_bps))
    stressed_execution = stressed_maker_execution(execution)
    primary = []
    stressed = []
    for inst_id in instruments:
        candles = maker_context(histories[inst_id], start_ms, end_ms)
        primary.append(
            run_market_maker_backtest(
                candles,
                params,
                execution,
                bar_ms=BAR_MS[MAKER_BAR],
                features=rolling_vwap_features(candles, params),
                active_predicate=predicate,
            )[0]
        )
        stressed.append(
            run_market_maker_backtest(
                candles,
                stressed_params,
                stressed_execution,
                bar_ms=BAR_MS[MAKER_BAR],
                features=rolling_vwap_features(candles, stressed_params),
                active_predicate=predicate,
            )[0]
        )
    returns = [item.total_return_pct for item in primary]
    stressed_returns = [item.total_return_pct for item in stressed]
    drawdowns = [item.max_drawdown_pct for item in primary]
    median_return = statistics.median(returns)
    worst_return = min(returns)
    stressed_median = statistics.median(stressed_returns)
    stressed_worst = min(stressed_returns)
    return {
        "candidateId": maker_candidate_id(params),
        "params": asdict(params),
        "score": (
            median_return
            + 0.75 * worst_return
            + 0.50 * stressed_median
            + 0.25 * stressed_worst
            - 0.20 * statistics.median(drawdowns)
        ),
        "medianReturnPct": median_return,
        "worstReturnPct": worst_return,
        "stressedMedianReturnPct": stressed_median,
        "stressedWorstReturnPct": stressed_worst,
        "medianDrawdownPct": statistics.median(drawdowns),
        "minimumMakerFills": min(item.maker_fills for item in primary),
        "medianMakerFills": statistics.median(item.maker_fills for item in primary),
        "positiveInstruments": sum(value > 0 for value in returns),
    }


def run_maker_research(
    histories: dict[str, list[Candle]],
    instruments: tuple[str, ...],
    boundaries: dict[str, tuple[int, int]],
    execution: MakerExecutionConfig,
) -> dict[str, Any]:
    training_summaries = [
        maker_metrics(params, histories, instruments, boundaries["model_train"], execution)
        for params in slow_maker_grid()
    ]
    training_summaries.sort(key=lambda item: item["score"], reverse=True)
    prefiltered = training_summaries[:MAKER_PREFILTER_COUNT]
    params_lookup = {maker_candidate_id(params): params for params in slow_maker_grid()}
    selection_summaries = []
    for training_item in prefiltered:
        params = params_lookup[training_item["candidateId"]]
        selection_item = maker_metrics(
            params, histories, instruments, boundaries["selection"], execution
        )
        selection_item["selectionEligible"] = (
            selection_item["minimumMakerFills"] >= MIN_SELECTION_TRADES_PER_INSTRUMENT
        )
        selection_item["selectionAdvanceEligible"] = (
            selection_item["selectionEligible"]
            and selection_item["positiveInstruments"] == len(instruments)
            and selection_item["worstReturnPct"] > 0
            and selection_item["stressedWorstReturnPct"] > 0
        )
        selection_item["trainingRank"] = training_summaries.index(training_item) + 1
        selection_summaries.append(selection_item)
    selection_summaries.sort(key=lambda item: item["score"], reverse=True)
    selected_summary = next(
        (item for item in selection_summaries if item["selectionEligible"]), None
    )
    advancement_summary = next(
        (item for item in selection_summaries if item["selectionAdvanceEligible"]), None
    )
    rows: list[dict[str, Any]] = []
    if selected_summary is None:
        return {
            "gridCandidateCount": len(training_summaries),
            "prefilterCount": len(prefiltered),
            "trainingSummaries": training_summaries,
            "selectionSummaries": selection_summaries,
            "selectedCandidate": None,
            "advancementCandidate": None,
            "rows": [],
            "aggregates": [],
            "decision": {
                "status": "research_only",
                "quantitativePassOnReusedBarHistory": False,
                "reason": "no prefiltered maker candidate met the selection fill minimum",
            },
        }
    selected = params_lookup[selected_summary["candidateId"]]
    for segment_name in ("selection", "validation", "test"):
        start_ms, end_ms = boundaries[segment_name]
        predicate = maker_active_predicate(start_ms, end_ms)
        for inst_id in instruments:
            candles = maker_context(histories[inst_id], start_ms, end_ms)
            result = run_market_maker_backtest(
                candles,
                selected,
                execution,
                bar_ms=BAR_MS[MAKER_BAR],
                features=rolling_vwap_features(candles, selected),
                active_predicate=predicate,
            )[0]
            rows.append(maker_result_row(inst_id, segment_name, "selected", selected, result))
            if segment_name == "test":
                for variant, params, variant_execution in (
                    (
                        "cost_stress",
                        replace(selected, penetration_bps=max(2.0, selected.penetration_bps)),
                        stressed_maker_execution(execution),
                    ),
                    ("one_bar_latency", selected, replace(execution, latency_bars=1)),
                ):
                    variant_result = run_market_maker_backtest(
                        candles,
                        params,
                        variant_execution,
                        bar_ms=BAR_MS[MAKER_BAR],
                        features=rolling_vwap_features(candles, params),
                        active_predicate=predicate,
                    )[0]
                    rows.append(
                        maker_result_row(
                            inst_id, segment_name, variant, params, variant_result
                        )
                    )
    aggregates = aggregate_maker_rows(rows)
    decision = maker_decision(rows, aggregates, advancement_summary is not None)
    return {
        "gridCandidateCount": len(training_summaries),
        "prefilterCount": len(prefiltered),
        "trainingSummaries": training_summaries,
        "selectionSummaries": selection_summaries,
        "selectedCandidate": {**selected_summary, "params": asdict(selected)},
        "advancementCandidate": advancement_summary,
        "positiveTrainingCandidateCount": sum(
            item["positiveInstruments"] == len(instruments)
            and item["worstReturnPct"] > 0
            and item["stressedWorstReturnPct"] > 0
            for item in training_summaries
        ),
        "positiveSelectionCandidateCount": sum(
            item["selectionAdvanceEligible"] for item in selection_summaries
        ),
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }


def maker_decision(
    rows: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    selection_advance_eligible: bool,
) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "selected")]
    test = lookup[("test", "selected")]
    stress = lookup[("test", "cost_stress")]
    latency = lookup[("test", "one_bar_latency")]
    instrument_test = [
        row for row in rows if row["segment"] == "test" and row["variant"] == "selected"
    ]
    passed = (
        selection_advance_eligible
        and validation["positive"] == validation["count"]
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["profit_factor"]) >= 1.10 for row in instrument_test)
        and all(int(row["inventory_cycles"]) >= 30 for row in instrument_test)
        and test["worst_drawdown_pct"] <= 3.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedBarHistory": passed,
        "requiresFreshEventLevelQueueTest": True,
        "selectionAdvanceEligible": selection_advance_eligible,
        "validationMedianReturnPct": validation["median_return_pct"],
        "testMedianReturnPct": test["median_return_pct"],
        "testMedianProfitFactor": test["median_profit_factor"],
        "costStressMedianReturnPct": stress["median_return_pct"],
        "latencyMedianReturnPct": latency["median_return_pct"],
    }


def combined_audit(
    americas: dict[str, Any], maker: dict[str, Any], instruments: tuple[str, ...]
) -> list[dict[str, Any]]:
    if americas["selectedCandidate"] is None or maker["selectedCandidate"] is None:
        return []
    america_id = americas["selectedCandidate"]["candidateId"]
    rows = []
    for segment in ("selection", "validation", "test"):
        for inst_id in instruments:
            direction = next(
                row
                for row in americas["rows"]
                if row["segment"] == segment
                and row["variant"] == america_id
                and row["inst_id"] == inst_id
            )
            passive = next(
                row
                for row in maker["rows"]
                if row["segment"] == segment
                and row["variant"] == "selected"
                and row["inst_id"] == inst_id
            )
            rows.append(
                {
                    "segment": segment,
                    "inst_id": inst_id,
                    "americas_return_pct": direction["total_return_pct"],
                    "non_americas_return_pct": passive["total_return_pct"],
                    "capital_normalized_sum_return_pct": (
                        direction["total_return_pct"] + passive["total_return_pct"]
                    ),
                    "conservative_drawdown_bound_pct": (
                        direction["max_drawdown_pct"] + passive["max_drawdown_pct"]
                    ),
                }
            )
    return rows


def markdown_report(payload: dict[str, Any]) -> str:
    america = payload["americasDirectional"]
    maker = payload["nonAmericasLiquidityProvision"]
    america_pick = america["selectedCandidate"]
    maker_pick = maker["selectedCandidate"]
    lines = [
        "# BTC/ETH 分时段短因子与慢因子流动性研究",
        "",
        "> 只读复用历史研究；不读取账户、不发送订单、不修改实盘配置。",
        "",
        "## 固定设计",
        "",
        "- 美洲盘：纽约工作日09:30–16:00，短因子仅用同一美洲盘内的回看和预测标签；每日重置因果平滑，边界按可成交价平仓。",
        "- 非美洲盘：其余时间，使用12/24/48小时慢VWAP、波动与斜率过滤来提供被动流动性；进入美洲盘即用首根K线开盘代理价清库存。",
        f"- 美洲盘先在前40%拟合，再用随后10%选候选；非美洲盘先在前40%从{maker['gridCandidateCount']}个maker候选预筛12个，再用随后10%选择。之后25%验证，最后25%仅作复用测试。",
        "- Maker成交采用保守K线代理：下一根才生效、需穿价、同根双边触发只保留较差一边；仍无法识别真实排队优先级。",
        "",
        "## 美洲盘短因子",
        "",
        f"- 候选 {america['candidateCount']} 个，合格 {america['eligibleCandidateCount']} 个；选择段每标的交易数上限 {america['maximumMinimumSelectionTrades']}。验证/测试中位收益为正均为 {america['positiveValidationCandidateCount']}/{america['positiveTestCandidateCount']} 个。",
    ]
    if america_pick is None:
        lines.append("- 没有候选满足每标的12笔选择门槛。")
    else:
        lines.extend(
            [
                f"- 选择：`{america_pick['candidateId']}`，{america_pick['selectedFeatures']}个因子，选择段最少 {america_pick['minimumSelectionTrades']} 笔。",
                "",
                "| 区间 | 中位收益 | 中位期望 | PF | 最差回撤 | 交易 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for segment in ("selection", "validation", "test"):
            item = america_pick[segment]
            lines.append(
                f"| {segment} | {item['median_return_pct']:.4f}% | {item['median_expectancy_bps']:.3f} bps | "
                f"{item['median_profit_factor']:.3f} | {item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
            )
        america_lookup = {
            (item["segment"], item["variant"]): item for item in america["aggregates"]
        }
        for variant, label in (
            ("selected_cost_stress", "test_cost_stress"),
            ("selected_one_bar_latency", "test_one_bar_latency"),
        ):
            item = america_lookup[("test", variant)]
            lines.append(
                f"| {label} | {item['median_return_pct']:.4f}% | {item['median_expectancy_bps']:.3f} bps | "
                f"{item['median_profit_factor']:.3f} | {item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
            )
    lines.extend(["", "## 非美洲盘慢因子被动做市", ""])
    if maker_pick is None:
        lines.append("- 预筛候选中没有方案满足每标的12次maker成交。")
    else:
        params = maker_pick["params"]
        lines.extend(
            [
                f"- 训练网格中正式正收益候选 {maker['positiveTrainingCandidateCount']}/{maker['gridCandidateCount']}；预筛后选择段正式推进候选 {maker['positiveSelectionCandidateCount']}/{maker['prefilterCount']}。",
                f"- 为审计后续区间而锁定的最少亏损诊断方案：`{maker_pick['candidateId']}`；慢VWAP {params['vwap_window']} 根（{params['vwap_window'] * 5 / 60:.0f}小时），选择段最少 {maker_pick['minimumMakerFills']} 次maker成交。",
                "",
                "| 区间 | 中位收益 | PF | 最差回撤 | 中位maker成交 | 中位库存周期 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        lookup = {(item["segment"], item["variant"]): item for item in maker["aggregates"]}
        for segment, variant, label in (
            ("selection", "selected", "selection"),
            ("validation", "selected", "validation"),
            ("test", "selected", "test"),
            ("test", "cost_stress", "test_cost_stress"),
            ("test", "one_bar_latency", "test_one_bar_latency"),
        ):
            item = lookup[(segment, variant)]
            lines.append(
                f"| {label} | {item['median_return_pct']:.4f}% | {item['median_profit_factor']:.3f} | "
                f"{item['worst_drawdown_pct']:.3f}% | {item['median_maker_fills']:.1f} | "
                f"{item['median_inventory_cycles']:.1f} |"
            )
    if payload["combinedAudit"]:
        lines.extend(
            [
                "",
                "## 双时段资本归一化审计",
                "",
                "> 下表是两个不同时段独立回测收益在同一本金上的加总，不是同步逐笔权益曲线；回撤采用两腿回撤相加的保守上界。",
                "",
                "| 区间 | 标的 | 美洲盘 | 非美洲盘 | 收益和 | 回撤上界 |",
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in payload["combinedAudit"]:
            lines.append(
                f"| {row['segment']} | {row['inst_id']} | {row['americas_return_pct']:.4f}% | "
                f"{row['non_americas_return_pct']:.4f}% | {row['capital_normalized_sum_return_pct']:.4f}% | "
                f"{row['conservative_drawdown_bound_pct']:.4f}% |"
            )
    lines.extend(
        [
            "",
            "## 判定",
            "",
            f"- 美洲盘复用历史门禁：`{america['decision'].get('quantitativeGatePassedOnReusedHistory', False)}`。",
            f"- 非美洲盘复用K线门禁：`{maker['decision'].get('quantitativePassOnReusedBarHistory', False)}`。",
            "- 任一腿失败时都不应上线组合；maker即使通过K线数字，也必须先用全新逐事件数据验证排队与真实成交。",
            "- 不允许根据验证或测试表现事后改选周期、过滤器或时段。",
            "",
        ]
    )
    return "\n".join(lines)


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


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    histories = load_snapshot_history(Path(args.input_root), instruments)
    cutoff_ms = parse_iso_time(args.end_time) if args.end_time else None
    histories = truncate_histories(histories, cutoff_ms)
    if any(len(histories.get(inst_id, [])) < 12_000 for inst_id in instruments):
        raise SystemExit("Insufficient public snapshot history")
    boundaries, period = period_boundaries(histories, instruments)
    prepared = prepare_snapshot_segments(histories, instruments, boundaries)
    directional_execution = {
        "starting_equity": args.starting_equity,
        "allocation_pct": args.allocation_pct,
        "fee_bps_per_side": args.fee_bps_per_side,
        "slippage_bps_per_side": args.slippage_bps_per_side,
        "max_spread_bps": args.max_spread_bps,
        "max_gap_ms": BASE_MAX_GAP_MS,
    }
    americas = run_americas_research(prepared, instruments, directional_execution)

    start_ms = min(start for start, _ in boundaries.values())
    end_ms = max(end for _, end in boundaries.values())
    maker_histories, maker_sources = load_maker_histories(
        Path(args.maker_data_root), instruments, start_ms, end_ms
    )
    maker_execution = MakerExecutionConfig(starting_equity=args.starting_equity)
    maker = run_maker_research(
        maker_histories, instruments, boundaries, maker_execution
    )
    combined = combined_audit(americas, maker, instruments)
    median_interval_ms = statistics.median(
        histories[instruments[0]][index].ts - histories[instruments[0]][index - 1].ts
        for index in range(1, len(histories[instruments[0]]))
        if histories[instruments[0]][index].ts > histories[instruments[0]][index - 1].ts
    )
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_session_factor_and_liquidity_research",
        "instruments": list(instruments),
        "period": period,
        "dataDefinition": {
            "directionalSource": "locally collected OKX public REST snapshots",
            "directionalMedianSamplingSeconds": median_interval_ms / 1_000.0,
            "makerSource": maker_sources,
            "makerBar": MAKER_BAR,
            "explicitCutoff": args.end_time or None,
            "reusedHistory": True,
        },
        "sessionDefinition": {
            "americas": "America/New_York weekdays 09:30 inclusive to 16:00 exclusive, DST-aware",
            "nonAmericas": "all other timestamps",
            "boundaryAction": "each leg is flat outside its own session",
        },
        "americasProfiles": [asdict(item) for item in AMERICAS_PROFILES],
        "americasDirectional": americas,
        "nonAmericasLiquidityProvision": maker,
        "combinedAudit": combined,
        "decision": {
            "status": "research_only",
            "bothLegsPassedReusedHistory": (
                americas["decision"].get("quantitativeGatePassedOnReusedHistory", False)
                and maker["decision"].get("quantitativePassOnReusedBarHistory", False)
            ),
            "paperAuthorized": False,
            "liveAuthorized": False,
        },
    }
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_ROOT / datetime.now(timezone.utc).strftime("btc-eth-%Y%m%d")
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "americas_rows.csv", americas["rows"])
    write_csv(output_dir / "non_americas_maker_rows.csv", maker["rows"])
    write_csv(output_dir / "combined_audit.csv", combined)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(
        "americas_selected="
        + str(americas["selectedCandidate"]["candidateId"] if americas["selectedCandidate"] else None)
    )
    print(
        "maker_selected="
        + str(maker["selectedCandidate"]["candidateId"] if maker["selectedCandidate"] else None)
    )
    print(f"decision={json.dumps(payload['decision'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
