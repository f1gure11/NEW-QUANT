from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backtest.okx_grid_backtest import (
    DATA_DIR,
    Candle,
    GridBacktestConfig,
    read_candles_csv,
    round_to_tick,
    run_grid_backtest,
)
from market_regime import FEATURE_COLUMNS, LabelConfig, add_future_labels, read_candle_csv, signal_from_candles, training_matrix
from scoring import ScoreWeights, score_backtest


PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_DIR = PROJECT_ROOT / "reports" / "regime_model"
DEFAULT_CANDIDATES = PROJECT_ROOT / "reports" / "portfolio" / "latest-dashboard-account-run" / "candidates.json"
SCORE_FIELDS = [
    "rank",
    "variant",
    "inst_id",
    "score",
    "total_return_pct",
    "max_drawdown_pct",
    "profit_factor",
    "fills",
    "risk_events",
    "bars",
    "latest_signal",
    "latest_confidence",
    "latest_allowed_sides",
    "model_path",
    "error",
]


@dataclass(slots=True)
class CandidateMeta:
    inst_id: str
    last: Decimal
    ct_val: Decimal
    tick_sz: Decimal
    lot_sz: Decimal
    min_sz: Decimal


@dataclass(slots=True)
class ResearchConfig:
    data_dir: Path = DATA_DIR
    candidates_path: Path = DEFAULT_CANDIDATES
    output_dir: Path = REPORT_DIR
    limit_symbols: int = 0
    test_size_pct: Decimal = Decimal("35")
    label_horizon: int = 30
    min_trend_bps: Decimal = Decimal("45")
    trend_vol_multiplier: Decimal = Decimal("3.0")
    min_efficiency: Decimal = Decimal("0.28")
    rf_estimators: int = 160
    rf_max_depth: int = 7
    hmm_states: int = 3
    starting_equity: Decimal = Decimal("100")
    leverage: Decimal = Decimal("7")
    outer_range_bps: Decimal = Decimal("1200")
    grid_bps: Decimal = Decimal("10")
    order_margin_pct: Decimal = Decimal("25")
    max_margin_pct: Decimal = Decimal("75")
    max_open_orders_per_side: int = 5
    max_actions_per_bar: int = 12
    min_tp_bps: Decimal = Decimal("30")
    total_loss_sl_pct: Decimal = Decimal("4")
    total_loss_sl_cap: Decimal = Decimal("0.8")
    position_loss_sl_bps: Decimal = Decimal("700")
    risk_cooldown_bars: int = 1


def main() -> int:
    args = parse_args()
    config = config_from_args(args)
    output_dir = run_research(config)
    print(f"regime_report={output_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline market-regime research and model training from local OKX candle CSVs.")
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--candidates", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    parser.add_argument("--limit-symbols", type=int, default=0)
    parser.add_argument("--test-size-pct", default="35")
    parser.add_argument("--label-horizon", type=int, default=30)
    parser.add_argument("--min-trend-bps", default="45")
    parser.add_argument("--trend-vol-multiplier", default="3.0")
    parser.add_argument("--min-efficiency", default="0.28")
    parser.add_argument("--rf-estimators", type=int, default=160)
    parser.add_argument("--rf-max-depth", type=int, default=7)
    parser.add_argument("--hmm-states", type=int, default=3)
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> ResearchConfig:
    return ResearchConfig(
        data_dir=Path(args.data_dir),
        candidates_path=Path(args.candidates),
        output_dir=Path(args.output_dir),
        limit_symbols=args.limit_symbols,
        test_size_pct=dec(args.test_size_pct, Decimal("35")),
        label_horizon=args.label_horizon,
        min_trend_bps=dec(args.min_trend_bps, Decimal("45")),
        trend_vol_multiplier=dec(args.trend_vol_multiplier, Decimal("3.0")),
        min_efficiency=dec(args.min_efficiency, Decimal("0.28")),
        rf_estimators=args.rf_estimators,
        rf_max_depth=args.rf_max_depth,
        hmm_states=args.hmm_states,
    )


def run_research(config: ResearchConfig) -> Path:
    output_dir = resolve_output_dir(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candles_by_symbol = load_symbol_frames(config)
    if not candles_by_symbol:
        raise RuntimeError(f"no local candle CSVs found under {config.data_dir}")

    label_config = LabelConfig(
        horizon=config.label_horizon,
        min_trend_bps=float(config.min_trend_bps),
        trend_vol_multiplier=float(config.trend_vol_multiplier),
        min_efficiency=float(config.min_efficiency),
    )
    train_frames, test_frames = split_frames(candles_by_symbol, config)
    rf_payload, rf_metrics = train_rf(train_frames, label_config, config)
    rf_path = output_dir / "regime_rf.joblib"
    joblib.dump(rf_payload, rf_path)
    hmm_payload, hmm_metrics = train_hmm(train_frames, label_config, config)
    hmm_path = output_dir / "regime_hmm.joblib"
    joblib.dump(hmm_payload, hmm_path)

    candidates = load_candidates(config.candidates_path)
    rows = []
    variants = [
        ("baseline", "off", ""),
        ("rules", "rules", ""),
        ("rf", "rf", str(rf_path)),
        ("hmm", "hmm", str(hmm_path)),
    ]
    for meta in candidates:
        frame = test_frames.get(meta.inst_id)
        if frame is None:
            frame = candles_by_symbol.get(meta.inst_id)
        if frame is None or len(frame) < 80:
            continue
        candles = frame_to_candles(frame)
        for variant, mode, model_path in variants:
            rows.append(backtest_variant(meta, candles, config, variant, mode, model_path))
    rows = rank_rows(rows)

    write_outputs(output_dir, config, rows, rf_metrics, hmm_metrics, rf_path, hmm_path)
    return output_dir


def load_symbol_frames(config: ResearchConfig) -> dict[str, pd.DataFrame]:
    selected: dict[str, tuple[int, Path]] = {}
    pattern = re.compile(r"(.+)_1m_(\d+)(?:x(\d+))?\.csv$")
    for path in config.data_dir.glob("*_1m_*.csv"):
        match = pattern.match(path.name)
        if not match:
            continue
        inst_id = match.group(1)
        bars = int(match.group(2)) * int(match.group(3) or "1")
        current = selected.get(inst_id)
        if current is None or bars > current[0] or (bars == current[0] and path.stat().st_mtime > current[1].stat().st_mtime):
            selected[inst_id] = (bars, path)
    items = sorted(selected.items())
    if config.limit_symbols > 0:
        items = items[: config.limit_symbols]
    return {inst_id: read_candle_csv(path) for inst_id, (_bars, path) in items}


def split_frames(frames: dict[str, pd.DataFrame], config: ResearchConfig) -> tuple[list[pd.DataFrame], dict[str, pd.DataFrame]]:
    train = []
    test: dict[str, pd.DataFrame] = {}
    test_ratio = max(Decimal("5"), min(Decimal("80"), config.test_size_pct)) / Decimal("100")
    for inst_id, frame in frames.items():
        split = int(len(frame) * float(Decimal("1") - test_ratio))
        split = max(80, min(split, len(frame) - 40))
        train.append(frame.iloc[:split].copy())
        test[inst_id] = frame.iloc[split:].copy()
    return train, test


def train_rf(
    frames: list[pd.DataFrame],
    label_config: LabelConfig,
    config: ResearchConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    x, y = training_matrix(frames, label_config)
    if x.empty or y.nunique() < 2:
        raise RuntimeError("not enough labeled classes to train RF regime model")
    stratify = y if y.value_counts().min() >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, random_state=7, stratify=stratify)
    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "rf",
                RandomForestClassifier(
                    n_estimators=config.rf_estimators,
                    max_depth=config.rf_max_depth,
                    random_state=7,
                    class_weight="balanced_subsample",
                    min_samples_leaf=4,
                    n_jobs=1,
                ),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)
    prediction = pipeline.predict(x_test)
    metrics = {
        "kind": "rf",
        "samples": int(len(x)),
        "classes": sorted(y.unique().tolist()),
        "label_counts": y.value_counts().to_dict(),
        "accuracy": float(accuracy_score(y_test, prediction)),
        "classification_report": classification_report(y_test, prediction, output_dict=True, zero_division=0),
    }
    return {"kind": "rf", "feature_columns": FEATURE_COLUMNS, "model": pipeline, "metrics": metrics}, metrics


def train_hmm(
    frames: list[pd.DataFrame],
    label_config: LabelConfig,
    config: ResearchConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    feature_frames = []
    labels = []
    lengths = []
    for frame in frames:
        labeled = add_future_labels(frame, label_config).dropna(subset=FEATURE_COLUMNS + ["regime_label"])
        if labeled.empty:
            continue
        feature_frames.append(labeled[FEATURE_COLUMNS].astype(float))
        labels.append(labeled["regime_label"].astype(str))
        lengths.append(len(labeled))
    if not feature_frames:
        raise RuntimeError("not enough data to train HMM regime model")
    x = pd.concat(feature_frames, ignore_index=True)
    y = pd.concat(labels, ignore_index=True)
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)
    states = max(2, min(config.hmm_states, len(x) // 30))
    model = GaussianHMM(n_components=states, covariance_type="diag", n_iter=200, random_state=7)
    model.fit(x_scaled, lengths)
    hidden = model.predict(x_scaled)
    state_map: dict[str, str] = {}
    state_confidence: dict[str, float] = {}
    for state in range(states):
        labels_for_state = y[hidden == state]
        if labels_for_state.empty:
            state_map[str(state)] = "mixed"
            state_confidence[str(state)] = 0.0
            continue
        counts = labels_for_state.value_counts()
        state_map[str(state)] = str(counts.index[0])
        state_confidence[str(state)] = float(counts.iloc[0] / counts.sum())
    mapped = [state_map[str(item)] for item in hidden]
    metrics = {
        "kind": "hmm",
        "samples": int(len(x)),
        "states": states,
        "state_map": state_map,
        "state_confidence": state_confidence,
        "accuracy_vs_weak_labels": float(accuracy_score(y, mapped)),
        "label_counts": y.value_counts().to_dict(),
    }
    return {
        "kind": "hmm",
        "feature_columns": FEATURE_COLUMNS,
        "scaler": scaler,
        "model": model,
        "state_map": state_map,
        "state_confidence": state_confidence,
        "metrics": metrics,
    }, metrics


def backtest_variant(
    meta: CandidateMeta,
    candles: list[Candle],
    config: ResearchConfig,
    variant: str,
    mode: str,
    model_path: str,
) -> dict[str, Any]:
    try:
        signal = signal_from_candles(candles, mode=mode, model_path=model_path)
        result, _, _ = run_grid_backtest(candles, grid_config(meta, candles, config, mode, model_path))
        score = score_backtest(result, ScoreWeights())
        return {
            "rank": "",
            "variant": variant,
            "inst_id": meta.inst_id,
            "score": score.score,
            "total_return_pct": result.total_return_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "profit_factor": result.profit_factor,
            "fills": result.fills,
            "risk_events": result.risk_events,
            "bars": result.bars,
            "latest_signal": signal.state,
            "latest_confidence": Decimal(str(round(signal.confidence, 6))),
            "latest_allowed_sides": ",".join(signal.allowed_open_sides),
            "model_path": model_path,
            "error": "",
        }
    except Exception as exc:
        return {
            "rank": "",
            "variant": variant,
            "inst_id": meta.inst_id,
            "score": Decimal("-999999"),
            "total_return_pct": "",
            "max_drawdown_pct": "",
            "profit_factor": "",
            "fills": "",
            "risk_events": "",
            "bars": "",
            "latest_signal": "",
            "latest_confidence": "",
            "latest_allowed_sides": "",
            "model_path": model_path,
            "error": str(exc),
        }


def grid_config(
    meta: CandidateMeta,
    candles: list[Candle],
    config: ResearchConfig,
    mode: str,
    model_path: str,
) -> GridBacktestConfig:
    mark_px = candles[0].close if candles else meta.last
    half_width = config.outer_range_bps / Decimal("20000")
    lower = round_to_tick(mark_px * (Decimal("1") - half_width), meta.tick_sz)
    upper = round_to_tick(mark_px * (Decimal("1") + half_width), meta.tick_sz)
    order_sz = contract_size_for_margin(
        equity=config.starting_equity,
        margin_pct=config.order_margin_pct,
        leverage=config.leverage,
        mark_px=mark_px,
        ct_val=meta.ct_val,
        lot_sz=meta.lot_sz,
        min_sz=meta.min_sz,
    )
    max_position = contract_size_for_margin(
        equity=config.starting_equity,
        margin_pct=config.max_margin_pct,
        leverage=config.leverage,
        mark_px=mark_px,
        ct_val=meta.ct_val,
        lot_sz=meta.lot_sz,
        min_sz=meta.min_sz,
    )
    return GridBacktestConfig(
        inst_id=meta.inst_id,
        lower=lower,
        upper=upper,
        leverage=config.leverage,
        grid_bps=config.grid_bps,
        soft_bps=Decimal("35"),
        hard_bps=Decimal("60"),
        order_sz=order_sz,
        max_position=max(max_position, order_sz),
        max_open_orders_per_side=config.max_open_orders_per_side,
        max_actions_per_bar=config.max_actions_per_bar,
        adaptive_width_bps=Decimal("420"),
        adaptive_min_width_bps=Decimal("260"),
        adaptive_max_width_bps=Decimal("1200"),
        adaptive_vol_multiplier=Decimal("12"),
        range_drift_weight_bps=Decimal("2500"),
        range_drift_max_bps=Decimal("250"),
        starting_equity=config.starting_equity,
        ct_val=meta.ct_val,
        tick_sz=meta.tick_sz,
        lot_sz=meta.lot_sz,
        min_sz=meta.min_sz,
        min_tp_bps=config.min_tp_bps,
        total_loss_sl_pct=config.total_loss_sl_pct,
        total_loss_sl_cap=config.total_loss_sl_cap,
        position_loss_sl_bps=config.position_loss_sl_bps,
        risk_cooldown_bars=config.risk_cooldown_bars,
        regime_filter="off",
        trend_filter="off",
        one_way_open=False,
        market_regime_filter=mode,
        market_regime_model_path=model_path,
    )


def contract_size_for_margin(
    *,
    equity: Decimal,
    margin_pct: Decimal,
    leverage: Decimal,
    mark_px: Decimal,
    ct_val: Decimal,
    lot_sz: Decimal,
    min_sz: Decimal,
) -> Decimal:
    if equity <= 0 or margin_pct <= 0 or leverage <= 0 or mark_px <= 0 or ct_val <= 0:
        return min_sz
    raw_size = equity * margin_pct / Decimal("100") * leverage / (mark_px * ct_val)
    size = (raw_size / lot_sz).to_integral_value(rounding=ROUND_DOWN) * lot_sz if lot_sz > 0 else raw_size
    return max(size, min_sz)


def load_candidates(path: Path) -> list[CandidateMeta]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = []
    for item in payload.get("candidates", []):
        candidates.append(
            CandidateMeta(
                inst_id=str(item["inst_id"]),
                last=dec(item.get("last"), Decimal("0")),
                ct_val=dec(item.get("ct_val"), Decimal("1")),
                tick_sz=dec(item.get("tick_sz"), Decimal("0.0001")),
                lot_sz=dec(item.get("lot_sz"), Decimal("1")),
                min_sz=dec(item.get("min_sz"), Decimal("1")),
            )
        )
    return candidates


def frame_to_candles(frame: pd.DataFrame) -> list[Candle]:
    return [
        Candle(
            ts=int(row.ts),
            open=dec(row.open),
            high=dec(row.high),
            low=dec(row.low),
            close=dec(row.close),
            volume=dec(row.volume),
        )
        for row in frame.itertuples(index=False)
    ]


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_variant.setdefault(str(row.get("variant", "")), []).append(row)
    ranked = []
    for _variant, items in by_variant.items():
        ordered = sorted(items, key=lambda row: dec(row.get("score"), Decimal("-999999")), reverse=True)
        for index, row in enumerate(ordered, start=1):
            row["rank"] = index if not row.get("error") else ""
            ranked.append(row)
    return ranked


def write_outputs(
    output_dir: Path,
    config: ResearchConfig,
    rows: list[dict[str, Any]],
    rf_metrics: dict[str, Any],
    hmm_metrics: dict[str, Any],
    rf_path: Path,
    hmm_path: Path,
) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (output_dir / "config.json").write_text(json.dumps(jsonable(asdict(config)), indent=2), encoding="utf-8")
    (output_dir / "model_metrics.json").write_text(
        json.dumps({"generatedAt": generated_at, "rf": rf_metrics, "hmm": hmm_metrics}, indent=2, default=str),
        encoding="utf-8",
    )
    with (output_dir / "scores.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in SCORE_FIELDS})
    write_summary(output_dir / "summary.md", generated_at, rows, rf_metrics, hmm_metrics, rf_path, hmm_path)


def write_summary(
    path: Path,
    generated_at: str,
    rows: list[dict[str, Any]],
    rf_metrics: dict[str, Any],
    hmm_metrics: dict[str, Any],
    rf_path: Path,
    hmm_path: Path,
) -> None:
    lines = [
        "# Market Regime Research",
        "",
        f"- Generated: `{generated_at}`",
        f"- RF model: `{rf_path}`",
        f"- HMM model: `{hmm_path}`",
        f"- RF weak-label accuracy: `{rf_metrics.get('accuracy')}`",
        f"- HMM weak-label accuracy: `{hmm_metrics.get('accuracy_vs_weak_labels')}`",
        "",
        "## Variant Averages",
        "",
        "| Variant | Symbols | Avg Return % | Avg Max DD % | Avg Score | Total Fills | Total Risk Events |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in sorted({str(row.get("variant", "")) for row in rows}):
        items = [row for row in rows if row.get("variant") == variant and not row.get("error")]
        if not items:
            continue
        avg_return = sum((dec(row.get("total_return_pct")) for row in items), Decimal("0")) / Decimal(len(items))
        avg_dd = sum((dec(row.get("max_drawdown_pct")) for row in items), Decimal("0")) / Decimal(len(items))
        avg_score = sum((dec(row.get("score")) for row in items), Decimal("0")) / Decimal(len(items))
        total_fills = sum(int(row.get("fills") or 0) for row in items)
        total_risk = sum(int(row.get("risk_events") or 0) for row in items)
        lines.append(f"| {variant} | {len(items)} | {plain(avg_return)} | {plain(avg_dd)} | {plain(avg_score)} | {total_fills} | {total_risk} |")
    lines.extend(["", "## Top Rows", "", "| Variant | Rank | Instrument | Score | Return % | DD % | Fills | Risk | Latest |", "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |"])
    for row in sorted([item for item in rows if not item.get("error")], key=lambda item: (str(item.get("variant")), int(item.get("rank") or 999)))[:48]:
        lines.append(
            f"| {row.get('variant')} | {row.get('rank')} | {row.get('inst_id')} | {csv_value(row.get('score'))} | "
            f"{csv_value(row.get('total_return_pct'))} | {csv_value(row.get('max_drawdown_pct'))} | "
            f"{row.get('fills')} | {row.get('risk_events')} | {row.get('latest_signal')} |"
        )
    errors = [row for row in rows if row.get("error")]
    if errors:
        lines.extend(["", "## Errors", ""])
        for row in errors[:20]:
            lines.append(f"- `{row.get('variant')}` `{row.get('inst_id')}`: {row.get('error')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_output_dir(path: Path) -> Path:
    if path.name != "regime_model":
        return path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path / timestamp


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def csv_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    return value


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


if __name__ == "__main__":
    raise SystemExit(main())
