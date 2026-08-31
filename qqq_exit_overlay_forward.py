#!/usr/bin/env python3
"""Forward-only exit-overlay study for the locked QQQ active book.

The observer reads completed public candles, realized funding, and append-only
QQQ signal decisions from the unified data lake. It has no account client,
order API, or live execution mode. All variants start strictly after their
preregistered forward boundary and execute close-based decisions at a later
5-minute open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from data_pipeline import RESEARCH_DIR, load_candles, load_funding


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "config" / "qqq_exit_overlay_forward_preregistration.json"
DEFAULT_REPORT_ROOT = PROJECT_ROOT / "reports" / "qqq_exit_overlay_forward"
NY_TZ = ZoneInfo("America/New_York")
BAR_DELTA = timedelta(minutes=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return as_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derived_id(prefix: str, basis: dict[str, Any]) -> str:
    return f"{prefix}-{sha256_bytes(canonical_json(basis))[:16]}"


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def validate_registry(registry: dict[str, Any], *, now: datetime | None = None) -> None:
    required = {"schemaVersion", "registryId", "frozenAt", "protocol", "study"}
    missing = required - set(registry)
    if missing:
        raise ValueError(f"registry missing fields: {sorted(missing)}")
    basis = {key: registry[key] for key in ("frozenAt", "protocol", "study")}
    if registry["registryId"] != derived_id("qqq-exit-registry", basis):
        raise ValueError("registryId does not match frozen registry content")
    study = registry["study"]
    if study.get("paperOrLiveAuthorized") is not False:
        raise ValueError("forward exit study cannot authorize paper or live trading")
    boundary = parse_time(str(study["forwardBoundary"]))
    if boundary > as_utc(now or utcnow()) + timedelta(minutes=5):
        raise ValueError("forward boundary is unexpectedly in the future")
    if study.get("modelId") != derived_id("qqq-exit", study["basis"]):
        raise ValueError("modelId does not match the frozen study basis")
    for artifact in study.get("artifacts", []):
        path = PROJECT_ROOT / str(artifact["path"])
        if not path.is_file() or sha256_file(path) != artifact["sha256"]:
            raise ValueError(f"frozen artifact changed or is missing: {path}")
    variants = study["basis"].get("variants", [])
    if len({str(row.get("key")) for row in variants}) != len(variants):
        raise ValueError("variant keys must be unique")
    if not variants or variants[0].get("key") != "monthly_control":
        raise ValueError("monthly_control must remain the first variant")


def observation_path(model_id: str, captured_at: datetime) -> Path:
    return RESEARCH_DIR / model_id / f"{captured_at:%Y%m%d}.jsonl"


def already_observed_today(model_id: str, captured_at: datetime) -> bool:
    day = captured_at.date().isoformat()
    return any(
        str(row.get("observationDate")) == day
        and str(row.get("observationType")) == "exit_overlay_state"
        for row in read_jsonl(RESEARCH_DIR / model_id)
    )


@dataclass(frozen=True)
class SignalCohort:
    signal_date: str
    available_at: datetime
    weights: dict[str, float]


@dataclass
class Position:
    inst_id: str
    signal_date: str
    side: int
    weight: float
    entry_time: datetime
    entry_price: float
    entry_base_cost: float
    entry_stress_cost: float
    funding: float = 0.0
    peak_favorable_bps: float = 0.0
    pending_exit_reason: str | None = None
    pending_exit_index: int | None = None


@dataclass
class SimulationState:
    positions: dict[str, Position] = field(default_factory=dict)
    realized_gross: float = 0.0
    realized_funding: float = 0.0
    realized_base_cost: float = 0.0
    realized_stress_cost: float = 0.0
    trades: list[dict[str, Any]] = field(default_factory=list)
    entries: int = 0
    turnover: float = 0.0
    session_closes: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    curve: list[dict[str, Any]] = field(default_factory=list)


def active_instrument(symbol: str) -> str:
    return symbol if symbol.endswith("-USDT-SWAP") else f"{symbol}-USDT-SWAP"


def load_signal_cohorts(study: dict[str, Any]) -> list[SignalCohort]:
    basis = study["basis"]
    boundary = parse_time(str(study["forwardBoundary"]))
    lock_path = PROJECT_ROOT / str(study["artifacts"][0]["path"])
    locked = read_json(lock_path)
    allowed = {str(symbol) for symbol in basis["symbols"]}

    def weights_from(payload: dict[str, Any]) -> dict[str, float]:
        return {
            active_instrument(str(symbol)): float(value)
            for symbol, value in payload.items()
            if str(symbol) in allowed and abs(float(value)) > 1e-12
        }

    cohorts = [
        SignalCohort(
            signal_date=str(locked["latestSignalDate"]),
            available_at=boundary,
            weights=weights_from(locked.get("activeWeights", {})),
        )
    ]
    source_model = str(basis["sourceModelId"])
    for row in read_jsonl(RESEARCH_DIR / source_model):
        if row.get("observationType") != "signal_decision" or not isinstance(row.get("activeWeights"), dict):
            continue
        captured = parse_time(str(row["capturedAt"]))
        if captured < boundary:
            continue
        cohorts.append(
            SignalCohort(
                signal_date=str(row["signalDate"]),
                available_at=captured,
                weights=weights_from(row["activeWeights"]),
            )
        )
    unique: dict[str, SignalCohort] = {}
    for cohort in sorted(cohorts, key=lambda row: (row.available_at, row.signal_date)):
        unique[cohort.signal_date] = cohort
    return sorted(unique.values(), key=lambda row: (row.available_at, row.signal_date))


def is_entry_bar(value: pd.Timestamp) -> bool:
    local = value.to_pydatetime().astimezone(NY_TZ)
    return local.weekday() < 5 and local.hour == 9 and local.minute == 35


def is_session_close_bar(value: pd.Timestamp) -> bool:
    local = value.to_pydatetime().astimezone(NY_TZ)
    return local.weekday() < 5 and local.hour == 15 and local.minute == 55


def effective_cohorts(index: pd.DatetimeIndex, cohorts: list[SignalCohort]) -> dict[pd.Timestamp, SignalCohort]:
    effective: dict[pd.Timestamp, SignalCohort] = {}
    for cohort in cohorts:
        selected = next(
            (
                value
                for value in index
                if value.to_pydatetime() > cohort.available_at and is_entry_bar(value)
            ),
            None,
        )
        if selected is not None:
            effective[selected] = cohort
    return effective


def build_market_panel(
    instruments: list[str],
    boundary: datetime,
    captured_at: datetime,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    series: list[pd.DataFrame] = []
    individual_rows: dict[str, int] = {}
    cutoff = pd.Timestamp(captured_at - BAR_DELTA)
    for inst_id in instruments:
        frame = load_candles(inst_id, "5m", start=iso_utc(boundary))
        if frame.empty:
            individual_rows[inst_id] = 0
            continue
        frame = frame.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame[(frame["time"] >= pd.Timestamp(boundary)) & (frame["time"] <= cutoff)]
        frame = frame.set_index("time")[["open", "close"]].astype(float)
        individual_rows[inst_id] = len(frame)
        frame.columns = pd.MultiIndex.from_product([[inst_id], frame.columns])
        series.append(frame)
    if len(series) != len(instruments):
        missing = sorted(inst for inst in instruments if individual_rows.get(inst, 0) == 0)
        return pd.DataFrame(), {
            "instrumentCoverage": (len(instruments) - len(missing)) / len(instruments) if instruments else 0.0,
            "commonBarCoverage": 0.0,
            "missingInstruments": missing,
            "individualRows": individual_rows,
        }
    panel = pd.concat(series, axis=1, join="inner").sort_index()
    maximum = max(individual_rows.values(), default=0)
    return panel, {
        "instrumentCoverage": 1.0,
        "commonBarCoverage": len(panel) / maximum if maximum else 0.0,
        "missingInstruments": [],
        "individualRows": individual_rows,
        "commonRows": len(panel),
    }


def load_funding_maps(
    instruments: list[str], boundary: datetime, captured_at: datetime
) -> dict[str, list[tuple[datetime, float]]]:
    result: dict[str, list[tuple[datetime, float]]] = {}
    for inst_id in instruments:
        frame = load_funding(inst_id, start=iso_utc(boundary), end=iso_utc(captured_at))
        result[inst_id] = [
            (as_utc(value.to_pydatetime()), float(rate))
            for value, rate in zip(frame.get("funding_time", []), frame.get("realized_rate", []))
        ]
    return result


def favorable_return_bps(position: Position, price: float) -> float:
    return position.side * (price / position.entry_price - 1.0) * 10_000.0


def close_position(
    state: SimulationState,
    position: Position,
    exit_time: datetime,
    exit_price: float,
    reason: str,
    costs: dict[str, float],
    *,
    exit_turnover_weight: float | None = None,
) -> None:
    gross = position.weight * position.side * (exit_price / position.entry_price - 1.0)
    exit_turnover = position.weight if exit_turnover_weight is None else exit_turnover_weight
    base_exit = exit_turnover * float(costs["basePerSideBps"]) / 10_000.0
    stress_exit = exit_turnover * float(costs["stressPerSideBps"]) / 10_000.0
    base_cost = position.entry_base_cost + base_exit
    stress_cost = position.entry_stress_cost + stress_exit
    net = gross + position.funding - base_cost
    state.realized_gross += gross
    state.realized_funding += position.funding
    state.realized_base_cost += base_cost
    state.realized_stress_cost += stress_cost
    state.turnover += exit_turnover
    state.trades.append(
        {
            "instId": position.inst_id,
            "signalDate": position.signal_date,
            "side": position.side,
            "weight": position.weight,
            "entryTime": iso_utc(position.entry_time),
            "exitTime": iso_utc(exit_time),
            "entryPrice": position.entry_price,
            "exitPrice": exit_price,
            "reason": reason,
            "grossContribution": gross,
            "fundingContribution": position.funding,
            "baseCostContribution": base_cost,
            "netContribution": net,
        }
    )
    state.positions.pop(position.inst_id, None)


def open_cohort(
    state: SimulationState,
    cohort: SignalCohort,
    at: datetime,
    row: pd.Series,
    costs: dict[str, float],
    *,
    entry_turnover_weights: dict[str, float] | None = None,
) -> None:
    entry_turnover = entry_turnover_weights or {
        inst_id: abs(float(signed_weight))
        for inst_id, signed_weight in cohort.weights.items()
    }
    for inst_id, signed_weight in cohort.weights.items():
        price = float(row[(inst_id, "open")])
        weight = abs(float(signed_weight))
        turnover = float(entry_turnover.get(inst_id, 0.0))
        state.positions[inst_id] = Position(
            inst_id=inst_id,
            signal_date=cohort.signal_date,
            side=1 if signed_weight > 0 else -1,
            weight=weight,
            entry_time=at,
            entry_price=price,
            entry_base_cost=turnover * float(costs["basePerSideBps"]) / 10_000.0,
            entry_stress_cost=turnover * float(costs["stressPerSideBps"]) / 10_000.0,
        )
        state.entries += 1
        state.turnover += turnover


def rebalance_turnover(prior_signed: float, target_signed: float) -> tuple[float, float]:
    prior = abs(prior_signed)
    target = abs(target_signed)
    if prior <= 1e-12:
        return 0.0, target
    if target <= 1e-12:
        return prior, 0.0
    if prior_signed * target_signed < 0.0:
        return prior, target
    if target < prior:
        return prior - target, 0.0
    return 0.0, target - prior


def rebalance_cohort(
    state: SimulationState,
    cohort: SignalCohort,
    at: datetime,
    row: pd.Series,
    costs: dict[str, float],
) -> None:
    prior = {
        inst_id: position.side * position.weight
        for inst_id, position in state.positions.items()
    }
    targets = cohort.weights
    entry_turnover: dict[str, float] = {}
    for inst_id in set(prior) | set(targets):
        _, entry_turnover[inst_id] = rebalance_turnover(
            float(prior.get(inst_id, 0.0)),
            float(targets.get(inst_id, 0.0)),
        )
    for position in list(state.positions.values()):
        exit_turnover, _ = rebalance_turnover(
            float(prior[position.inst_id]),
            float(targets.get(position.inst_id, 0.0)),
        )
        close_position(
            state,
            position,
            at,
            float(row[(position.inst_id, "open")]),
            "monthly_signal_rebalance",
            costs,
            exit_turnover_weight=exit_turnover,
        )
    open_cohort(state, cohort, at, row, costs, entry_turnover_weights=entry_turnover)


def apply_funding(
    state: SimulationState,
    funding_maps: dict[str, list[tuple[datetime, float]]],
    previous: datetime | None,
    current: datetime,
) -> None:
    lower = previous or current
    for inst_id, position in list(state.positions.items()):
        for funding_time, rate in funding_maps.get(inst_id, []):
            if lower < funding_time <= current:
                position.funding += position.weight * (-position.side * rate)


def schedule_exit(position: Position, reason: str, current_index: int, delay_bars: int) -> None:
    if position.pending_exit_reason is None:
        position.pending_exit_reason = reason
        position.pending_exit_index = current_index + delay_bars


def evaluate_exit(
    position: Position,
    close_price: float,
    variant: dict[str, Any],
    current_index: int,
    delay_bars: int,
) -> None:
    current = favorable_return_bps(position, close_price)
    position.peak_favorable_bps = max(position.peak_favorable_bps, current)
    if current <= -float(variant["stopLossBps"]):
        schedule_exit(position, "stop_loss", current_index, delay_bars)
        return
    if variant["type"] == "fixed_take_profit" and current >= float(variant["takeProfitBps"]):
        schedule_exit(position, "take_profit", current_index, delay_bars)
        return
    if variant["type"] == "trailing_take_profit":
        activated = position.peak_favorable_bps >= float(variant["activationBps"])
        giveback = position.peak_favorable_bps - current
        if activated and giveback >= float(variant["givebackBps"]):
            schedule_exit(position, "trailing_take_profit", current_index, delay_bars)


def evaluate_trend_review(
    state: SimulationState,
    row: pd.Series,
    variant: dict[str, Any],
    current_index: int,
    delay_bars: int,
) -> None:
    lookback = int(variant["lookbackSessions"])
    cadence = int(variant["reviewEverySessions"])
    for inst_id, position in list(state.positions.items()):
        history = state.session_closes.get(inst_id, [])
        if len(history) < lookback or (len(history) - lookback) % cadence != 0:
            continue
        reference = history[-lookback][1]
        current = history[-1][1]
        aligned_return = position.side * (current / reference - 1.0)
        if aligned_return <= 0.0:
            schedule_exit(position, "biweekly_trend_review", current_index, delay_bars)


def record_session_closes(state: SimulationState, row: pd.Series) -> None:
    for inst_id in sorted(set(row.index.get_level_values(0))):
        state.session_closes.setdefault(str(inst_id), []).append(
            (str(row.name.date()), float(row[(inst_id, "close")]))
        )


def curve_point(state: SimulationState, at: datetime, row: pd.Series) -> dict[str, Any]:
    open_gross = 0.0
    open_funding = 0.0
    open_base_cost = 0.0
    open_stress_cost = 0.0
    for inst_id, position in state.positions.items():
        close = float(row[(inst_id, "close")])
        open_gross += position.weight * position.side * (close / position.entry_price - 1.0)
        open_funding += position.funding
        open_base_cost += position.entry_base_cost
        open_stress_cost += position.entry_stress_cost
    gross = state.realized_gross + open_gross
    funding = state.realized_funding + open_funding
    base_cost = state.realized_base_cost + open_base_cost
    stress_cost = state.realized_stress_cost + open_stress_cost
    return {
        "time": at,
        "gross": gross,
        "funding": funding,
        "baseCost": base_cost,
        "stressCost": stress_cost,
        "net": gross + funding - base_cost,
        "stressNet": gross + funding - stress_cost,
    }


def max_drawdown_pct(curve: list[dict[str, Any]], key: str = "net") -> float:
    peak = 1.0
    worst = 0.0
    for point in curve:
        equity = 1.0 + float(point[key])
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return worst * 100.0


def worst_daily_return_pct(curve: list[dict[str, Any]]) -> float | None:
    if not curve:
        return None
    frame = pd.DataFrame(curve).set_index("time")
    daily = (1.0 + frame["net"]).resample("1D").last().dropna()
    if daily.empty:
        return None
    returns = daily.pct_change().dropna()
    if returns.empty:
        return float(daily.iloc[-1] - 1.0) * 100.0
    return float(returns.min()) * 100.0


def profit_factor(trades: list[dict[str, Any]]) -> float | None:
    profits = sum(max(float(row["netContribution"]), 0.0) for row in trades)
    losses = -sum(min(float(row["netContribution"]), 0.0) for row in trades)
    if losses <= 0.0:
        return None
    return profits / losses


def summarize_state(state: SimulationState) -> dict[str, Any]:
    latest = state.curve[-1] if state.curve else {
        "gross": 0.0,
        "funding": 0.0,
        "baseCost": 0.0,
        "stressCost": 0.0,
        "net": 0.0,
        "stressNet": 0.0,
    }
    reasons = Counter(str(row["reason"]) for row in state.trades)
    return {
        "grossReturnPct": float(latest["gross"]) * 100.0,
        "fundingReturnPct": float(latest["funding"]) * 100.0,
        "baseCostPct": float(latest["baseCost"]) * 100.0,
        "netReturnPct": float(latest["net"]) * 100.0,
        "doubleCostReturnPct": float(latest["stressNet"]) * 100.0,
        "maxDrawdownPct": max_drawdown_pct(state.curve),
        "worstDailyReturnPct": worst_daily_return_pct(state.curve),
        "profitFactor": profit_factor(state.trades),
        "turnoverPct": state.turnover * 100.0,
        "entryCount": state.entries,
        "closedTradeCount": len(state.trades),
        "openLegs": len(state.positions),
        "exitReasons": dict(sorted(reasons.items())),
        "openInstruments": sorted(state.positions),
        "trades": state.trades,
    }


def simulate_variant(
    panel: pd.DataFrame,
    funding_maps: dict[str, list[tuple[datetime, float]]],
    cohorts: list[SignalCohort],
    variant: dict[str, Any],
    costs: dict[str, float],
    *,
    exit_delay_bars: int = 1,
) -> dict[str, Any]:
    state = SimulationState()
    effective = effective_cohorts(panel.index, cohorts)
    previous: datetime | None = None
    for index_number, (timestamp, row) in enumerate(panel.iterrows()):
        at = as_utc(timestamp.to_pydatetime())
        apply_funding(state, funding_maps, previous, at)

        for position in list(state.positions.values()):
            if position.pending_exit_index is not None and index_number >= position.pending_exit_index:
                close_position(
                    state,
                    position,
                    at,
                    float(row[(position.inst_id, "open")]),
                    str(position.pending_exit_reason),
                    costs,
                )

        cohort = effective.get(timestamp)
        if cohort is not None:
            rebalance_cohort(state, cohort, at, row, costs)

        for inst_id, position in list(state.positions.items()):
            evaluate_exit(
                position,
                float(row[(inst_id, "close")]),
                variant,
                index_number,
                exit_delay_bars,
            )

        if variant["type"] == "biweekly_trend_review" and is_session_close_bar(timestamp):
            record_session_closes(state, row)
            evaluate_trend_review(state, row, variant, index_number, exit_delay_bars)

        state.curve.append(curve_point(state, at, row))
        previous = at
    return summarize_state(state)


def collect_observation(
    registry: dict[str, Any], captured_at: datetime, *, force: bool = False
) -> dict[str, Any]:
    validate_registry(registry, now=captured_at)
    study = registry["study"]
    model_id = str(study["modelId"])
    if not force and already_observed_today(model_id, captured_at):
        return {"status": "already_observed_today", "modelId": model_id}
    boundary = parse_time(str(study["forwardBoundary"]))
    instruments = [active_instrument(symbol) for symbol in study["basis"]["symbols"]]
    panel, coverage = build_market_panel(instruments, boundary, captured_at)
    cohorts = load_signal_cohorts(study)
    variants: dict[str, Any] = {}
    status = "waiting_for_post_boundary_entry_bar"
    data_cutoff = None
    if not panel.empty:
        data_cutoff = iso_utc(panel.index[-1].to_pydatetime())
        effective = effective_cohorts(panel.index, cohorts)
        if effective:
            funding_maps = load_funding_maps(instruments, boundary, captured_at)
            costs = study["costs"]
            for variant in study["basis"]["variants"]:
                base = simulate_variant(panel, funding_maps, cohorts, variant, costs, exit_delay_bars=1)
                latency = simulate_variant(panel, funding_maps, cohorts, variant, costs, exit_delay_bars=2)
                base["oneExtraBarExitLatencyNetReturnPct"] = latency["netReturnPct"]
                variants[str(variant["key"])] = base
            status = "collecting"
    observation = {
        "schemaVersion": 1,
        "registryId": registry["registryId"],
        "modelId": model_id,
        "strategyKey": study["strategyKey"],
        "capturedAt": iso_utc(captured_at),
        "observationDate": captured_at.date().isoformat(),
        "observationType": "exit_overlay_state",
        "forwardBoundary": study["forwardBoundary"],
        "dataCutoff": data_cutoff,
        "status": status,
        "historyReplayUsed": False,
        "ordersOrAccountAccess": False,
        "paperOrLiveAuthorized": False,
        "coverage": coverage,
        "signalCohortsSeen": [row.signal_date for row in cohorts],
        "variants": variants,
    }
    append_jsonl(observation_path(model_id, captured_at), observation)
    write_status(registry, observation)
    return observation


def maturity(registry: dict[str, Any], latest: dict[str, Any]) -> dict[str, Any]:
    study = registry["study"]
    gate = study["maturity"]
    rows = [
        row
        for row in read_jsonl(RESEARCH_DIR / str(study["modelId"]))
        if row.get("observationType") == "exit_overlay_state"
        and parse_time(str(row["capturedAt"])) >= parse_time(str(study["forwardBoundary"]))
    ]
    days = 0
    if len(rows) >= 2:
        days = (parse_time(str(rows[-1]["capturedAt"])).date() - parse_time(str(rows[0]["capturedAt"])).date()).days
    signal_dates = sorted({date for row in rows for date in row.get("signalCohortsSeen", [])})
    control = latest.get("variants", {}).get("monthly_control", {})
    candidate_exit_events = 0
    closed_legs = 0
    for key, summary in latest.get("variants", {}).items():
        if key == "monthly_control":
            continue
        closed_legs += int(summary.get("closedTradeCount") or 0)
        candidate_exit_events += sum(
            int(count)
            for reason, count in summary.get("exitReasons", {}).items()
            if reason not in {"monthly_signal_rebalance", "stop_loss"}
        )
    complete = sum(float(row.get("coverage", {}).get("commonBarCoverage") or 0.0) >= 0.90 for row in rows)
    ratio = complete / len(rows) if rows else 0.0
    checks = {
        "forwardDays": days >= int(gate["minimumForwardDays"]),
        "monthlyCohorts": len(signal_dates) >= int(gate["minimumMonthlyCohorts"]),
        "closedCandidateLegs": closed_legs >= int(gate["minimumClosedCandidateLegs"]),
        "candidateExitEvents": candidate_exit_events >= int(gate["minimumCandidateExitEvents"]),
        "marketCoverage": ratio >= float(gate["minimumCompleteMarketObservationRatio"]),
    }
    return {
        "status": "mature_for_single_frozen_evaluation" if all(checks.values()) else "collecting",
        "checks": checks,
        "forwardDays": days,
        "monthlyCohorts": signal_dates,
        "closedCandidateLegs": closed_legs,
        "candidateExitEvents": candidate_exit_events,
        "completeMarketObservationRatio": ratio,
        "controlClosedTrades": int(control.get("closedTradeCount") or 0),
    }


def status_markdown(registry: dict[str, Any], latest: dict[str, Any], gate: dict[str, Any]) -> str:
    lines = [
        "# QQQ Exit Overlay Forward Study",
        "",
        f"Updated: `{latest['capturedAt']}`",
        f"Boundary: `{latest['forwardBoundary']}`",
        f"Status: `{latest['status']}` / `{gate['status']}`",
        "",
        "> Public forward observation only. No history replay, account access, orders, paper authorization, or live authorization.",
        "",
        "| Variant | Gross | Funding | Cost | Net | Double cost | Latency +1 bar |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in registry["study"]["basis"]["variants"]:
        summary = latest.get("variants", {}).get(variant["key"], {})
        lines.append(
            f"| {variant['key']} | {summary.get('grossReturnPct', 0):.4f}% | "
            f"{summary.get('fundingReturnPct', 0):.4f}% | {summary.get('baseCostPct', 0):.4f}% | "
            f"{summary.get('netReturnPct', 0):.4f}% | {summary.get('doubleCostReturnPct', 0):.4f}% | "
            f"{summary.get('oneExtraBarExitLatencyNetReturnPct', 0):.4f}% |"
        )
    lines.extend(
        [
            "",
            "| Variant | Turnover | PF | Drawdown | Worst day | Closed | Open | Exit reasons |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for variant in registry["study"]["basis"]["variants"]:
        summary = latest.get("variants", {}).get(variant["key"], {})
        reasons = ", ".join(f"{key}:{value}" for key, value in summary.get("exitReasons", {}).items()) or "-"
        profit_factor_value = summary.get("profitFactor")
        profit_factor_text = "-" if profit_factor_value is None else f"{profit_factor_value:.3f}"
        worst_day_value = summary.get("worstDailyReturnPct")
        worst_day_text = "-" if worst_day_value is None else f"{worst_day_value:.4f}%"
        lines.append(
            f"| {variant['key']} | {summary.get('turnoverPct', 0):.4f}% | {profit_factor_text} | "
            f"{summary.get('maxDrawdownPct', 0):.4f}% | {worst_day_text} | "
            f"{summary.get('closedTradeCount', 0)} | {summary.get('openLegs', 0)} | {reasons} |"
        )
    lines.extend(["", "## Maturity", ""])
    for key, value in gate["checks"].items():
        lines.append(f"- {key}: {'pass' if value else 'wait'}")
    return "\n".join(lines) + "\n"


def write_status(registry: dict[str, Any], latest: dict[str, Any]) -> None:
    DEFAULT_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    gate = maturity(registry, latest)
    payload = {
        "schemaVersion": 1,
        "registryId": registry["registryId"],
        "modelId": registry["study"]["modelId"],
        "updatedAt": latest["capturedAt"],
        "evaluationAuthorized": False,
        "paperOrLiveAuthorized": False,
        "latestObservation": latest,
        "maturity": gate,
    }
    atomic_write_json(DEFAULT_REPORT_ROOT / "status.json", payload)
    (DEFAULT_REPORT_ROOT / "report.md").write_text(
        status_markdown(registry, latest, gate), encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect frozen QQQ exit-overlay forward observations")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--at", default="", help="UTC timestamp for deterministic testing")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = read_json(Path(args.registry))
    captured_at = parse_time(args.at) if args.at else utcnow()
    result = collect_observation(registry, captured_at, force=bool(args.force))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
