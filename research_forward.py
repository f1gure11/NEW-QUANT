#!/usr/bin/env python3
"""Preregister and collect public forward observations for frozen strategies.

This module is deliberately separated from every executor. It never loads
``.env``, never calls a private endpoint, and cannot place or cancel orders.
Historical data may be used to reproduce a frozen signal, but maturity counts
only observations captured after each model's preregistered forward boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from data_pipeline import EVENT_DIR, RESEARCH_DIR, load_candles
from macro_calendar import macro_calendar_snapshot
from microstructure_collect import fetch_microstructure_snapshot
from okx_client import OkxRestClient
from qqq_active_enhancement_research import (
    build_weight_history,
    load_company_facts,
    load_yahoo_daily,
    prepare_fundamental_records,
)
from strategy_search import multi_horizon_momentum_targets


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "config" / "research_preregistrations.json"
DEFAULT_STATUS_ROOT = PROJECT_ROOT / "reports" / "forward_research"
QQQ_LOCK_PATH = PROJECT_ROOT / "reports" / "qqq_active_enhancement" / "qqq-pit-20260808-v5" / "locked_model.json"
MOMENTUM_CANDIDATE_PATH = PROJECT_ROOT / "reports" / "strategy_candidates" / "gate-20260710-evidence-live" / "approved_candidates.json"
QQQ_UNIVERSE_PATH = QQQ_LOCK_PATH.parent / "universe.csv"
QQQ_UNIVERSE_SHA256 = "5f13b20e5f36776225f7f7a7b8cc73b28f4719f96e9d67fea6bc610cbf2dda72"
TRADINGVIEW_URL = "https://economic-calendar.tradingview.com/events"
PUBLIC_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.tradingview.com",
    "User-Agent": "okx-quant-readonly-forward-research/1.0",
}
EVENT_SOURCE_SPECS = {
    "cpi": {"ticker": "ECONOMICS:USIRYY", "scale": 0.1, "unit": "percentage_points"},
    "nfp": {"ticker": "ECONOMICS:USNFP", "scale": 50_000.0, "unit": "persons"},
    "pce": {"ticker": "ECONOMICS:USCPCEPIAC", "scale": 0.1, "unit": "percentage_points"},
    "gdp-advance": {"ticker": "ECONOMICS:USGDPQQ", "scale": 0.3, "unit": "percentage_points"},
    "fomc": {"ticker": "ECONOMICS:USINTR", "scale": 0.25, "unit": "percentage_points"},
}
EVENT_PRE_HOURS = 24
EVENT_POST_HOURS = 6


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return as_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_time(value: str) -> datetime:
    return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def json_compatible(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_compatible(item) for item in value]
    if hasattr(value, "item"):
        return json_compatible(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derived_model_id(prefix: str, basis: dict[str, Any]) -> str:
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


def relative_project_path(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT))


def linked_artifact(path: Path) -> dict[str, str]:
    return {"path": relative_project_path(path), "sha256": sha256_file(path)}


def build_registry(frozen_at: str) -> dict[str, Any]:
    frozen_time = parse_time(frozen_at)
    qqq_lock = read_json(QQQ_LOCK_PATH)
    candidates = read_json(MOMENTUM_CANDIDATE_PATH).get("approvedCandidates", [])
    momentum = next(
        (
            item
            for item in candidates
            if item.get("instId") == "SPCX-USDT-SWAP"
            and item.get("strategy") == "multi_horizon_momentum"
        ),
        None,
    )
    if not isinstance(momentum, dict):
        raise ValueError("frozen SPCX multi-horizon candidate is missing")

    event_basis = {
        "instrument": "QQQ-USDT-SWAP",
        "bar": "5m",
        "eventFamilies": EVENT_SOURCE_SPECS,
        "preEventRangeBars": 12,
        "breakoutConfirmationBars": 3,
        "reversalBreachBars": 3,
        "reversalInsideBars": 3,
        "significantSurpriseScore": 1.0,
        "decisionRule": {
            "breakout": "first_three_post_event_closes_all_outside_same_pre_event_boundary",
            "reversal": "boundary_breach_in_first_three_bars_then_next_three_closes_inside_range",
            "nonSignificant": "no_trade",
            "otherwise": "no_trade",
        },
    }
    momentum_basis = {
        "instrument": momentum["instId"],
        "strategy": momentum["strategy"],
        "bar": str(momentum.get("bar") or "1H"),
        "params": momentum["params"],
        "allowedRegimes": ["all"],
        "fundingRule": "observe_only_no_new_veto_threshold",
        "executionRule": "observe_public_post_only_and_taker_cost_inputs_without_orders",
    }
    qqq_boundary = str(qqq_lock.get("lockedAt") or frozen_at)
    models = [
        {
            "strategyKey": "qqq_monthly_active_enhancement",
            "modelId": str(qqq_lock["modelId"]),
            "status": "forward_observation_only",
            "paperOrLiveAuthorized": False,
            "forwardBoundary": qqq_boundary,
            "basis": qqq_lock["basis"],
            "artifacts": [linked_artifact(QQQ_LOCK_PATH)],
            "costs": {
                "baseTransactionCostPerSideBps": 5.0,
                "baseShortBorrowAnnualBps": 100.0,
                "stressTransactionCostPerSideBps": 10.0,
                "stressShortBorrowAnnualBps": 300.0,
                "funding": "realized_point_in_time",
            },
            "maturity": {
                "minimumNewSignalDates": 6,
                "preferredNewSignalDates": 12,
                "minimumForwardDays": 180,
                "minimumCompleteMarketObservationRatio": 0.90,
            },
        },
        {
            "strategyKey": "qqq_event_breakout_reversal_gate",
            "modelId": derived_model_id("event-gate", event_basis),
            "status": "preregistered_collecting",
            "paperOrLiveAuthorized": False,
            "forwardBoundary": iso_utc(frozen_time),
            "basis": event_basis,
            "artifacts": [linked_artifact(PROJECT_ROOT / "macro_calendar.py")],
            "costs": {
                "feePerSideBps": 5.0,
                "slippagePerSideBps": 3.0,
                "spread": "observed_point_in_time",
                "costStressMultiplier": 2.0,
                "funding": "realized_point_in_time",
            },
            "maturity": {
                "minimumCompleteEvents": 30,
                "minimumEventsPerFamily": 3,
                "minimumDirectionalDecisions": 10,
            },
        },
        {
            "strategyKey": "spcx_1h_multi_horizon_momentum",
            "modelId": derived_model_id("spcx-mhm", momentum_basis),
            "status": "preregistered_collecting",
            "paperOrLiveAuthorized": False,
            "forwardBoundary": iso_utc(frozen_time),
            "basis": momentum_basis,
            "artifacts": [linked_artifact(MOMENTUM_CANDIDATE_PATH)],
            "costs": {
                "feePerSideBps": 5.0,
                "slippagePerSideBps": 2.0,
                "spread": "observed_point_in_time",
                "costStressMultiplier": 2.0,
                "funding": "realized_point_in_time",
            },
            "maturity": {
                "minimumForwardDays": 56,
                "minimumSignalTransitions": 30,
                "minimumCompleteMarketObservations": 56,
                "minimumFundingObservations": 20,
            },
        },
    ]
    protocol = {
        "historyReusePolicy": "2026-06-18_and_later_is_development_only_not_new_evidence",
        "evaluationSplit": {"train": 0.50, "validation": 0.25, "test": 0.25},
        "selection": "training_only_no_post_validation_or_test_tuning",
        "requiredMetrics": [
            "gross_return",
            "net_return",
            "double_cost_return",
            "funding",
            "latency",
            "trade_count",
            "profit_factor",
            "max_drawdown",
            "worst_window",
        ],
        "reversalMechanicalGate": "gross_loss_N_must_be_less_than_minus_2C_before_mechanical_reversal_is_considered",
        "promotion": "research_only_to_forward_observation_to_paper_review_to_explicit_live_approval",
    }
    registry_basis = {"frozenAt": iso_utc(frozen_time), "protocol": protocol, "models": models}
    return {
        "schemaVersion": 1,
        "registryId": derived_model_id("preregistry", registry_basis),
        **registry_basis,
    }


def validate_registry(registry: dict[str, Any]) -> None:
    required = {"schemaVersion", "registryId", "frozenAt", "protocol", "models"}
    missing = required - set(registry)
    if missing:
        raise ValueError(f"registry missing fields: {sorted(missing)}")
    basis = {key: registry[key] for key in ("frozenAt", "protocol", "models")}
    if registry["registryId"] != derived_model_id("preregistry", basis):
        raise ValueError("registryId does not match frozen registry content")
    model_ids: set[str] = set()
    for model in registry["models"]:
        model_id = str(model.get("modelId") or "")
        if not model_id or model_id in model_ids:
            raise ValueError(f"invalid or duplicate modelId: {model_id}")
        model_ids.add(model_id)
        if model.get("paperOrLiveAuthorized") is not False:
            raise ValueError(f"forward registry cannot authorize trading: {model_id}")
        if parse_time(str(model["forwardBoundary"])) > utcnow() + timedelta(minutes=5):
            raise ValueError(f"forward boundary is unexpectedly in the future: {model_id}")
        for artifact in model.get("artifacts", []):
            path = PROJECT_ROOT / str(artifact["path"])
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                raise ValueError(f"frozen artifact changed or is missing: {path}")


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


def observation_path(model_id: str, captured_at: datetime) -> Path:
    return RESEARCH_DIR / model_id / f"{captured_at:%Y%m%d}.jsonl"


def already_observed_today(
    model_id: str,
    captured_at: datetime,
    observation_type: str = "market",
) -> bool:
    path = observation_path(model_id, captured_at)
    if not path.is_file():
        return False
    day = captured_at.date().isoformat()
    return any(
        str(row.get("observationDate")) == day
        and str(row.get("observationType") or "market") == observation_type
        for row in read_jsonl(path.parent)
    )


def compact_okx_market(client: OkxRestClient, inst_id: str, captured_at: str) -> dict[str, Any]:
    try:
        return fetch_microstructure_snapshot(
            client,
            inst_id,
            books_size=10,
            trades_limit=50,
            captured_at=captured_at,
        )
    except Exception as exc:  # noqa: BLE001
        return {"capturedAt": captured_at, "instId": inst_id, "ok": False, "error": str(exc)[:400]}


def collect_qqq_observation(
    model: dict[str, Any],
    client: OkxRestClient,
    captured_at: datetime,
) -> dict[str, Any]:
    lock_path = PROJECT_ROOT / model["artifacts"][0]["path"]
    locked = read_json(lock_path)
    latest_decision = latest_qqq_decision(str(model["modelId"]))
    signal_date = latest_decision.get("signalDate") or locked.get("latestSignalDate")
    active_weights = latest_decision.get("activeWeights") or locked.get("activeWeights", {})
    symbols = ["QQQ", *list(locked["basis"].get("symbols", []))]
    markets = {
        f"{symbol}-USDT-SWAP": compact_okx_market(client, f"{symbol}-USDT-SWAP", iso_utc(captured_at))
        for symbol in symbols
    }
    complete = sum(1 for row in markets.values() if row.get("ok") is True)
    return {
        "schemaVersion": 1,
        "modelId": model["modelId"],
        "strategyKey": model["strategyKey"],
        "capturedAt": iso_utc(captured_at),
        "observationDate": captured_at.date().isoformat(),
        "forwardBoundary": model["forwardBoundary"],
        "ordersOrAccountAccess": False,
        "observationType": "market",
        "signalDate": signal_date,
        "activeWeightsSha256": sha256_bytes(canonical_json(active_weights)),
        "marketCoverage": complete / len(markets) if markets else 0.0,
        "markets": markets,
    }


def latest_qqq_decision(model_id: str) -> dict[str, Any]:
    decisions = [
        row
        for row in read_jsonl(RESEARCH_DIR / model_id)
        if row.get("observationType") == "signal_decision" and row.get("signalDate")
    ]
    return max(decisions, key=lambda row: str(row["signalDate"]), default={})


def frozen_qqq_universe(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if sha256_file(QQQ_UNIVERSE_PATH) != QQQ_UNIVERSE_SHA256:
        raise ValueError("frozen QQQ universe metadata checksum changed")
    required = set(str(symbol) for symbol in model["basis"]["symbols"])
    rows: dict[str, dict[str, Any]] = {}
    with QQQ_UNIVERSE_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol") or "")
            if symbol in required:
                rows[symbol] = row
    missing = required - set(rows)
    if missing:
        raise ValueError(f"frozen QQQ universe metadata missing: {sorted(missing)}")
    return rows


def archive_qqq_inputs(data_root: Path, model_id: str, captured_at: datetime) -> list[dict[str, str]]:
    archive = RESEARCH_DIR / model_id / "inputs" / f"{captured_at:%Y%m%dT%H%M%SZ}"
    artifacts: list[dict[str, str]] = []
    for source in sorted((data_root / "prices").glob("*.csv")) + sorted((data_root / "sec").glob("*.json")):
        relative = source.relative_to(data_root)
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        artifacts.append(
            {
                "path": str(destination.relative_to(PROJECT_ROOT / "data_lake")),
                "sha256": sha256_file(destination),
            }
        )
    return artifacts


def generate_qqq_forward_decision(model: dict[str, Any], captured_at: datetime) -> dict[str, Any]:
    """Apply the frozen QQQ rule to newly available public monthly data."""

    if captured_at < parse_time(str(model["forwardBoundary"])):
        raise ValueError("QQQ decision capture time precedes the frozen forward boundary")
    basis = model["basis"]
    universe = frozen_qqq_universe(model)
    data_root = RESEARCH_DIR / str(model["modelId"]) / "working_inputs"
    prices: dict[str, pd.DataFrame] = {}
    for symbol in ["QQQ", *sorted(universe)]:
        prices[symbol] = load_yahoo_daily(
            symbol,
            data_root,
            history_range="10y",
            refresh=True,
        )
    fundamentals: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for symbol, metadata in universe.items():
        payload = load_company_facts(int(str(metadata["cik"]).replace(",", "")), data_root, refresh=True)
        fundamentals[symbol] = prepare_fundamental_records(payload)
    weights, diagnostics, signals = build_weight_history(
        "monthly",
        universe,
        prices,
        fundamentals,
        gross_limit=float(basis["grossLimit"]),
        single_stock_limit=float(basis["singleStockLimit"]),
        tracking_error_limit=float(basis["trackingErrorLimit"]),
    )
    if not weights:
        raise RuntimeError("frozen QQQ rule produced no complete monthly decision")
    signal_date = max(weights)
    previous = latest_qqq_decision(str(model["modelId"]))
    if not previous:
        locked = read_json(PROJECT_ROOT / model["artifacts"][0]["path"])
        previous = {"signalDate": locked.get("latestSignalDate", "")}
    if signal_date.date().isoformat() <= str(previous.get("signalDate") or ""):
        return {
            "status": "no_new_completed_month",
            "signalDate": signal_date.date().isoformat(),
            "previousSignalDate": previous.get("signalDate"),
        }
    signal = signals[signal_date]
    active = weights[signal_date]
    diagnostic = next(
        (row for row in diagnostics if row.get("rebalanceDate") == signal_date.date().isoformat()),
        {},
    )
    input_artifacts = archive_qqq_inputs(data_root, str(model["modelId"]), captured_at)
    expected_artifacts = 1 + 2 * len(universe)
    if len(input_artifacts) != expected_artifacts:
        raise RuntimeError(
            f"QQQ input archive is incomplete: expected {expected_artifacts}, got {len(input_artifacts)}"
        )
    decision = {
        "schemaVersion": 1,
        "modelId": model["modelId"],
        "strategyKey": model["strategyKey"],
        "observationType": "signal_decision",
        "capturedAt": iso_utc(captured_at),
        "observationDate": captured_at.date().isoformat(),
        "forwardBoundary": model["forwardBoundary"],
        "signalDate": signal_date.date().isoformat(),
        "activeWeights": {
            symbol: float(value)
            for symbol, value in active.items()
            if abs(float(value)) > 1e-10
        },
        "latestFactors": {
            symbol: {
                key: json_compatible(row.get(key))
                for key in (
                    "momentum",
                    "quality",
                    "value",
                    "low_residual_volatility",
                    "composite",
                    "beta",
                    "size_z",
                    "latest_filed",
                    "fiscal_end",
                    "industry",
                )
            }
            for symbol, row in signal.iterrows()
        },
        "diagnostics": json_compatible(diagnostic),
        "inputArtifacts": input_artifacts,
        "ordersOrAccountAccess": False,
        "paperOrLiveAuthorized": False,
    }
    decision = json_compatible(decision)
    append_jsonl(observation_path(str(model["modelId"]), captured_at), decision)
    return {"status": "recorded", "signalDate": decision["signalDate"], "artifacts": len(input_artifacts)}


def hourly_closes_from_lake(inst_id: str, now: datetime) -> tuple[list[float], str]:
    candles = load_candles(inst_id, "5m")
    if candles.empty:
        return [], ""
    frame = candles.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    current_hour = pd.Timestamp(now).floor("h")
    frame = frame[frame["time"] < current_hour]
    if frame.empty:
        return [], ""
    grouped = frame.set_index("time").resample("1h", label="left", closed="left")
    hours = grouped.agg(close=("close", "last"), bars=("close", "count"))
    hours = hours[hours["bars"] == 12].dropna(subset=["close"])
    if hours.empty:
        return [], ""
    return [float(value) for value in hours["close"]], hours.index[-1].isoformat()


def frozen_momentum_signal(model: dict[str, Any], now: datetime) -> dict[str, Any]:
    basis = model["basis"]
    closes, last_hour = hourly_closes_from_lake(str(basis["instrument"]), now)
    params = basis["params"]
    required = max([int(value) for value in params["lookbacks"]] + [int(params["vol_window"])]) + 2
    if len(closes) < required:
        return {"ok": False, "reason": "insufficient_complete_1h_bars", "bars": len(closes)}
    targets = multi_horizon_momentum_targets(
        [*closes, closes[-1]],
        [int(value) for value in params["lookbacks"]],
        int(params["vol_window"]),
        float(params["threshold_sigma"]),
        int(params["min_votes"]),
    )
    return {"ok": True, "side": int(targets[-1]), "bars": len(closes), "lastCompleteHour": last_hour}


def collect_momentum_observation(
    model: dict[str, Any],
    client: OkxRestClient,
    captured_at: datetime,
) -> dict[str, Any]:
    inst_id = str(model["basis"]["instrument"])
    market = compact_okx_market(client, inst_id, iso_utc(captured_at))
    return {
        "schemaVersion": 1,
        "modelId": model["modelId"],
        "strategyKey": model["strategyKey"],
        "capturedAt": iso_utc(captured_at),
        "observationDate": captured_at.date().isoformat(),
        "forwardBoundary": model["forwardBoundary"],
        "ordersOrAccountAccess": False,
        "observationType": "market",
        "signal": frozen_momentum_signal(model, captured_at),
        "market": market,
    }


def event_family(event_id: str) -> str | None:
    for family in EVENT_SOURCE_SPECS:
        if event_id.startswith(f"{family}-"):
            return family
    return None


def event_in_collection_window(event: dict[str, Any], now: datetime) -> bool:
    scheduled = parse_time(str(event["scheduledAt"]))
    return scheduled - timedelta(hours=EVENT_PRE_HOURS) <= now <= scheduled + timedelta(hours=EVENT_POST_HOURS)


def tradingview_query_window(event: dict[str, Any]) -> tuple[str, str]:
    scheduled = parse_time(str(event["scheduledAt"]))
    return iso_utc(scheduled - timedelta(days=1)), iso_utc(scheduled + timedelta(days=1))


def fetch_tradingview_calendar(event: dict[str, Any]) -> tuple[dict[str, Any], str]:
    start, end = tradingview_query_window(event)
    url = f"{TRADINGVIEW_URL}?{urlencode({'from': start, 'to': end, 'countries': 'US'})}"
    request = Request(url, headers=PUBLIC_HEADERS)
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("TradingView calendar returned a non-object payload")
    return payload, url


def store_raw_event_payload(payload: dict[str, Any], source_date: str) -> tuple[str, str]:
    content = canonical_json(payload)
    digest = sha256_bytes(content)
    path = EVENT_DIR / "raw" / "tradingview" / source_date / f"{digest}.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content + b"\n")
    return str(path.relative_to(PROJECT_ROOT / "data_lake")), digest


def match_tradingview_event(payload: dict[str, Any], event: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    family = event_family(str(event["id"]))
    if not family:
        return None, "unsupported_event_family"
    ticker = EVENT_SOURCE_SPECS[family]["ticker"]
    rows = payload.get("result", [])
    matches = [row for row in rows if isinstance(row, dict) and row.get("ticker") == ticker]
    if not matches:
        return None, "source_event_not_found"
    scheduled = parse_time(str(event["scheduledAt"]))
    ranked = sorted(matches, key=lambda row: abs((parse_time(str(row["date"])) - scheduled).total_seconds()))
    if len(ranked) > 1:
        first_gap = abs((parse_time(str(ranked[0]["date"])) - scheduled).total_seconds())
        second_gap = abs((parse_time(str(ranked[1]["date"])) - scheduled).total_seconds())
        if first_gap == second_gap:
            return None, "ambiguous_source_event"
    if abs((parse_time(str(ranked[0]["date"])) - scheduled).total_seconds()) > 6 * 3600:
        return None, "source_release_time_mismatch"
    return ranked[0], "matched"


def source_number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def first_previous_value(event_id: str) -> float | None:
    for row in read_jsonl(EVENT_DIR):
        if row.get("eventId") == event_id:
            value = row.get("previous")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def normalize_event_observation(
    event: dict[str, Any],
    payload: dict[str, Any],
    *,
    captured_at: datetime,
    source_url: str,
    raw_path: str,
    raw_sha256: str,
    market_candles: list[dict[str, Any]],
) -> dict[str, Any]:
    event_id = str(event["id"])
    family = event_family(event_id)
    matched, match_status = match_tradingview_event(payload, event)
    matched = matched or {}
    actual = source_number(matched, "actualRaw")
    consensus = source_number(matched, "forecastRaw")
    previous = source_number(matched, "previousRaw")
    initial_previous = first_previous_value(event_id)
    revision = previous - initial_previous if previous is not None and initial_previous is not None else None
    spec = EVENT_SOURCE_SPECS.get(str(family), {})
    scale = float(spec.get("scale") or 0.0)
    surprise = actual - consensus if actual is not None and consensus is not None else None
    surprise_score = surprise / scale if surprise is not None and scale > 0 else None
    gate = classify_event_gate(event, market_candles, surprise_score=surprise_score)
    complete = actual is not None and consensus is not None and previous is not None and match_status == "matched"
    return {
        "schemaVersion": 1,
        "eventId": event_id,
        "family": family,
        "capturedAt": iso_utc(captured_at),
        "scheduledAt": event["scheduledAt"],
        "releaseAt": matched.get("date") or event["scheduledAt"],
        "actualFirstObservedAt": iso_utc(captured_at) if actual is not None else None,
        "consensus": consensus,
        "actual": actual,
        "previous": previous,
        "previousInitial": initial_previous,
        "revision": revision,
        "surprise": surprise,
        "surpriseScale": scale or None,
        "surpriseScaleUnit": spec.get("unit"),
        "surpriseScore": surprise_score,
        "dataComplete": complete,
        "matchStatus": match_status,
        "source": {
            "provider": "TradingView Economic Calendar",
            "url": source_url,
            "sourceEventId": matched.get("id"),
            "sourceTicker": matched.get("ticker"),
            "sourceTimestamp": matched.get("date"),
            "sourceName": matched.get("source"),
            "sourceUrl": matched.get("source_url"),
            "period": matched.get("period"),
            "referenceDate": matched.get("referenceDate"),
            "rawPath": raw_path,
            "rawSha256": raw_sha256,
        },
        "gate": gate,
        "market": {"instrument": "QQQ-USDT-SWAP", "bar": "5m", "candles": market_candles},
        "ordersOrAccountAccess": False,
    }


def fetch_recent_candles(client: OkxRestClient, inst_id: str, limit: int = 100) -> list[dict[str, Any]]:
    response = client.request(
        "GET",
        "/api/v5/market/candles",
        params={"instId": inst_id, "bar": "5m", "limit": str(limit)},
    )
    rows: list[dict[str, Any]] = []
    for raw in response.get("data", []):
        if not isinstance(raw, list) or len(raw) < 6:
            continue
        rows.append(
            {
                "ts": int(raw[0]),
                "time": iso_utc(datetime.fromtimestamp(int(raw[0]) / 1000, tz=timezone.utc)),
                "open": float(raw[1]),
                "high": float(raw[2]),
                "low": float(raw[3]),
                "close": float(raw[4]),
                "volume": float(raw[5]),
                "confirm": str(raw[8]) if len(raw) > 8 else "",
            }
        )
    return sorted(rows, key=lambda row: row["ts"])


def classify_event_gate(
    event: dict[str, Any],
    candles: list[dict[str, Any]],
    *,
    surprise_score: float | None,
) -> dict[str, Any]:
    scheduled_ms = int(parse_time(str(event["scheduledAt"])).timestamp() * 1000)
    completed = [row for row in candles if str(row.get("confirm", "1")) == "1"]
    pre = [row for row in completed if int(row["ts"]) < scheduled_ms][-12:]
    post = [row for row in completed if int(row["ts"]) >= scheduled_ms]
    if len(pre) < 12:
        return {"status": "waiting", "reason": "insufficient_pre_event_bars", "decision": "no_trade"}
    high = max(float(row["high"]) for row in pre)
    low = min(float(row["low"]) for row in pre)
    if surprise_score is None:
        return {"status": "waiting", "reason": "event_data_incomplete", "decision": "no_trade", "rangeHigh": high, "rangeLow": low}
    if abs(surprise_score) < 1.0:
        return {"status": "resolved", "reason": "surprise_below_frozen_threshold", "decision": "no_trade", "rangeHigh": high, "rangeLow": low}
    if len(post) < 3:
        return {"status": "waiting", "reason": "insufficient_breakout_confirmation_bars", "decision": "no_trade", "rangeHigh": high, "rangeLow": low}
    first_three = post[:3]
    if all(float(row["close"]) > high for row in first_three):
        return {"status": "resolved", "reason": "confirmed_above_range", "decision": "breakout_long", "rangeHigh": high, "rangeLow": low}
    if all(float(row["close"]) < low for row in first_three):
        return {"status": "resolved", "reason": "confirmed_below_range", "decision": "breakout_short", "rangeHigh": high, "rangeLow": low}
    breached_up = any(float(row["high"]) > high for row in first_three)
    breached_down = any(float(row["low"]) < low for row in first_three)
    if not breached_up and not breached_down:
        return {"status": "resolved", "reason": "no_boundary_breach", "decision": "no_trade", "rangeHigh": high, "rangeLow": low}
    if len(post) < 6:
        return {"status": "waiting", "reason": "insufficient_reversal_confirmation_bars", "decision": "no_trade", "rangeHigh": high, "rangeLow": low}
    inside = all(low <= float(row["close"]) <= high for row in post[3:6])
    if inside and breached_up != breached_down:
        decision = "reversal_short" if breached_up else "reversal_long"
        return {"status": "resolved", "reason": "breach_then_three_closes_inside", "decision": decision, "rangeHigh": high, "rangeLow": low}
    return {"status": "resolved", "reason": "frozen_confirmation_not_met", "decision": "no_trade", "rangeHigh": high, "rangeLow": low}


def collect_event_observations(
    model: dict[str, Any],
    client: OkxRestClient,
    captured_at: datetime,
    fetcher: Callable[[dict[str, Any]], tuple[dict[str, Any], str]] = fetch_tradingview_calendar,
) -> list[dict[str, Any]]:
    calendar = macro_calendar_snapshot(now=captured_at)
    eligible = [
        event
        for event in calendar["events"]
        if event_family(str(event["id"]))
        and parse_time(str(event["scheduledAt"])) >= parse_time(str(model["forwardBoundary"]))
        and event_in_collection_window(event, captured_at)
    ]
    observations: list[dict[str, Any]] = []
    market_candles = fetch_recent_candles(client, "QQQ-USDT-SWAP") if eligible else []
    for event in eligible:
        try:
            payload, source_url = fetcher(event)
            raw_path, raw_sha = store_raw_event_payload(payload, str(event["sourceDate"]))
            observation = normalize_event_observation(
                event,
                payload,
                captured_at=captured_at,
                source_url=source_url,
                raw_path=raw_path,
                raw_sha256=raw_sha,
                market_candles=market_candles,
            )
        except Exception as exc:  # noqa: BLE001
            observation = {
                "schemaVersion": 1,
                "eventId": event["id"],
                "family": event_family(str(event["id"])),
                "capturedAt": iso_utc(captured_at),
                "scheduledAt": event["scheduledAt"],
                "dataComplete": False,
                "matchStatus": "collector_error",
                "error": str(exc)[:400],
                "gate": {"status": "waiting", "reason": "collector_error", "decision": "no_trade"},
                "ordersOrAccountAccess": False,
            }
        append_jsonl(EVENT_DIR / f"{captured_at:%Y%m%d}.jsonl", observation)
        observations.append(observation)
    return observations


def post_boundary(rows: list[dict[str, Any]], boundary: str) -> list[dict[str, Any]]:
    threshold = parse_time(boundary)
    result = []
    for row in rows:
        try:
            captured = parse_time(str(row["capturedAt"]))
        except (KeyError, TypeError, ValueError):
            continue
        if captured >= threshold:
            result.append(row)
    return sorted(result, key=lambda row: str(row["capturedAt"]))


def elapsed_forward_days(rows: list[dict[str, Any]]) -> int:
    if len(rows) < 2:
        return 0
    first = parse_time(str(rows[0]["capturedAt"]))
    last = parse_time(str(rows[-1]["capturedAt"]))
    return max(0, (last.date() - first.date()).days)


def qqq_maturity(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = post_boundary(rows, str(model["forwardBoundary"]))
    market_rows = [
        row for row in relevant if str(row.get("observationType") or "market") == "market"
    ]
    decision_rows = [row for row in relevant if row.get("observationType") == "signal_decision"]
    signal_dates = sorted(
        {
            str(row["signalDate"])
            for row in decision_rows
            if row.get("signalDate") and parse_time(f"{row['signalDate']}T00:00:00Z") >= parse_time(str(model["forwardBoundary"]))
        }
    )
    complete = sum(float(row.get("marketCoverage") or 0.0) >= 0.90 for row in market_rows)
    ratio = complete / len(market_rows) if market_rows else 0.0
    gate = model["maturity"]
    checks = {
        "newSignalDates": len(signal_dates) >= int(gate["minimumNewSignalDates"]),
        "forwardDays": elapsed_forward_days(market_rows) >= int(gate["minimumForwardDays"]),
        "marketCoverage": ratio >= float(gate["minimumCompleteMarketObservationRatio"]),
    }
    return {
        "status": "mature_for_single_frozen_evaluation" if all(checks.values()) else "collecting",
        "checks": checks,
        "observations": len(market_rows),
        "signalDecisionObservations": len(decision_rows),
        "newSignalDates": signal_dates,
        "forwardDays": elapsed_forward_days(market_rows),
        "completeMarketObservationRatio": ratio,
    }


def momentum_maturity(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = post_boundary(rows, str(model["forwardBoundary"]))
    sides = [int(row["signal"]["side"]) for row in relevant if row.get("signal", {}).get("ok") is True]
    transitions = sum(current != previous for previous, current in zip(sides, sides[1:]))
    complete_market = sum(row.get("market", {}).get("ok") is True for row in relevant)
    funding = sum(bool(row.get("market", {}).get("funding")) for row in relevant)
    gate = model["maturity"]
    checks = {
        "forwardDays": elapsed_forward_days(relevant) >= int(gate["minimumForwardDays"]),
        "signalTransitions": transitions >= int(gate["minimumSignalTransitions"]),
        "completeMarketObservations": complete_market >= int(gate["minimumCompleteMarketObservations"]),
        "fundingObservations": funding >= int(gate["minimumFundingObservations"]),
    }
    return {
        "status": "mature_for_single_frozen_evaluation" if all(checks.values()) else "collecting",
        "checks": checks,
        "observations": len(relevant),
        "forwardDays": elapsed_forward_days(relevant),
        "signalTransitions": transitions,
        "completeMarketObservations": complete_market,
        "fundingObservations": funding,
    }


def event_maturity(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = post_boundary(rows, str(model["forwardBoundary"]))
    latest: dict[str, dict[str, Any]] = {}
    for row in relevant:
        latest[str(row.get("eventId"))] = row
    complete = [row for row in latest.values() if row.get("dataComplete") is True and row.get("gate", {}).get("status") == "resolved"]
    family_counts = Counter(str(row.get("family")) for row in complete)
    directional = sum(str(row.get("gate", {}).get("decision", "")).startswith(("breakout_", "reversal_")) for row in complete)
    gate = model["maturity"]
    required_families = set(EVENT_SOURCE_SPECS)
    checks = {
        "completeEvents": len(complete) >= int(gate["minimumCompleteEvents"]),
        "eventsPerFamily": all(family_counts[family] >= int(gate["minimumEventsPerFamily"]) for family in required_families),
        "directionalDecisions": directional >= int(gate["minimumDirectionalDecisions"]),
    }
    return {
        "status": "mature_for_single_frozen_evaluation" if all(checks.values()) else "collecting",
        "checks": checks,
        "observations": len(relevant),
        "uniqueEvents": len(latest),
        "completeEvents": len(complete),
        "eventsPerFamily": dict(sorted(family_counts.items())),
        "directionalDecisions": directional,
    }


def maturity_status(registry: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current = now or utcnow()
    research_rows = read_jsonl(RESEARCH_DIR)
    event_rows = read_jsonl(EVENT_DIR)
    models: list[dict[str, Any]] = []
    for model in registry["models"]:
        rows = [row for row in research_rows if row.get("modelId") == model["modelId"]]
        if model["strategyKey"] == "qqq_monthly_active_enhancement":
            maturity = qqq_maturity(model, rows)
        elif model["strategyKey"] == "spcx_1h_multi_horizon_momentum":
            maturity = momentum_maturity(model, rows)
        else:
            maturity = event_maturity(model, event_rows)
        models.append(
            {
                "strategyKey": model["strategyKey"],
                "modelId": model["modelId"],
                "forwardBoundary": model["forwardBoundary"],
                "paperOrLiveAuthorized": False,
                "maturity": maturity,
            }
        )
    return {
        "schemaVersion": 1,
        "registryId": registry["registryId"],
        "generatedAt": iso_utc(current),
        "evaluationAuthorized": False,
        "paperOrLiveAuthorized": False,
        "models": models,
    }


def maturity_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Frozen Forward Research Status",
        "",
        f"Generated: `{payload['generatedAt']}`",
        "",
        "> Collection only. Maturity permits one frozen evaluation; it never permits paper or live trading.",
        "",
        "| Strategy | Model | Status | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for model in payload["models"]:
        maturity = model["maturity"]
        evidence = ", ".join(f"{key}={value}" for key, value in maturity.items() if key not in {"status", "checks"})
        lines.append(f"| {model['strategyKey']} | `{model['modelId']}` | {maturity['status']} | {evidence} |")
    lines.extend(["", "## Checks", ""])
    for model in payload["models"]:
        checks = model["maturity"]["checks"]
        rendered = ", ".join(f"{key}: {'pass' if value else 'wait'}" for key, value in checks.items())
        lines.append(f"- `{model['modelId']}`: {rendered}")
    return "\n".join(lines) + "\n"


def write_status(payload: dict[str, Any], root: Path = DEFAULT_STATUS_ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(root / "status.json", payload)
    (root / "report.md").write_text(maturity_markdown(payload), encoding="utf-8")


def model_by_key(registry: dict[str, Any], key: str) -> dict[str, Any]:
    return next(model for model in registry["models"] if model["strategyKey"] == key)


def collect(registry: dict[str, Any], captured_at: datetime, *, force_daily: bool = False) -> dict[str, Any]:
    validate_registry(registry)
    client = OkxRestClient()
    client.timeout = 12.0
    collected: list[str] = []
    skipped: list[str] = []
    for key, collector in (
        ("qqq_monthly_active_enhancement", collect_qqq_observation),
        ("spcx_1h_multi_horizon_momentum", collect_momentum_observation),
    ):
        model = model_by_key(registry, key)
        if not force_daily and already_observed_today(str(model["modelId"]), captured_at):
            skipped.append(key)
            continue
        observation = collector(model, client, captured_at)
        append_jsonl(observation_path(str(model["modelId"]), captured_at), observation)
        collected.append(key)
    event_model = model_by_key(registry, "qqq_event_breakout_reversal_gate")
    events = collect_event_observations(event_model, client, captured_at)
    status = maturity_status(registry, now=captured_at)
    write_status(status)
    return {"collected": collected, "skipped": skipped, "eventObservations": len(events), "status": status}


def collect_qqq_signal(registry: dict[str, Any], captured_at: datetime) -> dict[str, Any]:
    validate_registry(registry)
    model = model_by_key(registry, "qqq_monthly_active_enhancement")
    decision = generate_qqq_forward_decision(model, captured_at)
    status = maturity_status(registry, now=captured_at)
    write_status(status)
    return {"decision": decision, "status": status}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze and collect public-only forward research observations.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="write the immutable preregistration registry")
    freeze.add_argument("--frozen-at", default="")
    freeze.add_argument("--force", action="store_true")
    collect_parser = sub.add_parser("collect", help="append public forward observations")
    collect_parser.add_argument("--force-daily", action="store_true")
    collect_parser.add_argument("--at", default="", help="UTC timestamp for deterministic operations/testing")
    signal_parser = sub.add_parser("qqq-signal", help="record a new completed-month frozen QQQ decision")
    signal_parser.add_argument("--at", default="", help="UTC timestamp for deterministic operations/testing")
    sub.add_parser("status", help="rebuild maturity status from collected observations")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    if args.command == "freeze":
        if registry_path.exists() and not args.force:
            raise FileExistsError(f"registry already exists: {registry_path}")
        frozen_at = args.frozen_at or iso_utc(utcnow())
        registry = build_registry(frozen_at)
        atomic_write_json(registry_path, registry)
        print(json.dumps({"registry": str(registry_path), "registryId": registry["registryId"], "models": [row["modelId"] for row in registry["models"]]}, ensure_ascii=False))
        return 0
    registry = read_json(registry_path)
    validate_registry(registry)
    if args.command == "collect":
        captured_at = parse_time(args.at) if args.at else utcnow()
        result = collect(registry, captured_at, force_daily=bool(args.force_daily))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "qqq-signal":
        captured_at = parse_time(args.at) if args.at else utcnow()
        result = collect_qqq_signal(registry, captured_at)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    status = maturity_status(registry)
    write_status(status)
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
