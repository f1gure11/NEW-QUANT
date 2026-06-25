from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange


FEATURE_COLUMNS = [
    "ret_1_bps",
    "ret_3_bps",
    "ret_8_bps",
    "ret_20_bps",
    "ma_gap_8_20_bps",
    "vol_bps_20",
    "avg_abs_bps_20",
    "range_bps_20",
    "atr_bps_14",
    "adx_14",
    "plus_di_14",
    "minus_di_14",
    "chop_14",
    "efficiency_20",
    "body_bps",
    "volume_z_20",
]

REGIME_STATES = {"trend_up", "trend_down", "range", "mixed", "unknown"}


@dataclass(slots=True)
class RegimeSignal:
    state: str
    direction: str
    confidence: float
    source: str
    allowed_open_sides: list[str]
    note: str
    metrics: dict[str, float]


@dataclass(slots=True)
class LabelConfig:
    horizon: int = 30
    min_trend_bps: float = 45.0
    trend_vol_multiplier: float = 3.0
    min_efficiency: float = 0.28


@dataclass(slots=True)
class RuleConfig:
    lookback: int = 30
    min_trend_bps: float = 35.0
    adx_threshold: float = 22.0
    max_trend_chop: float = 58.0
    range_chop: float = 61.8
    confidence_threshold: float = 0.55


def candles_to_frame(candles: list[Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(candles):
        row = candle_to_row(item, index)
        if row:
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    frame = pd.DataFrame(rows)
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame[frame["close"] > 0].copy()
    frame = frame.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)
    return frame


def candle_to_row(item: Any, index: int) -> dict[str, Any] | None:
    if hasattr(item, "open") and hasattr(item, "high") and hasattr(item, "low") and hasattr(item, "close"):
        return {
            "ts": int(getattr(item, "ts", index)),
            "open": safe_float(getattr(item, "open", np.nan)),
            "high": safe_float(getattr(item, "high", np.nan)),
            "low": safe_float(getattr(item, "low", np.nan)),
            "close": safe_float(getattr(item, "close", np.nan)),
            "volume": safe_float(getattr(item, "volume", 0.0)),
        }
    if isinstance(item, dict):
        return {
            "ts": int(safe_float(item.get("ts", item.get("time", index)))),
            "open": safe_float(item.get("open")),
            "high": safe_float(item.get("high")),
            "low": safe_float(item.get("low")),
            "close": safe_float(item.get("close")),
            "volume": safe_float(item.get("volume", item.get("vol", 0.0))),
        }
    if isinstance(item, (list, tuple)) and len(item) >= 6:
        return {
            "ts": int(safe_float(item[0], index)),
            "open": safe_float(item[1]),
            "high": safe_float(item[2]),
            "low": safe_float(item[3]),
            "close": safe_float(item[4]),
            "volume": safe_float(item[5]),
        }
    return None


def read_candle_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    rename = {"vol": "volume"}
    frame = frame.rename(columns={key: value for key, value in rename.items() if key in frame.columns})
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    needed = ["ts", "open", "high", "low", "close", "volume"]
    missing = [column for column in needed if column not in frame.columns]
    if missing:
        raise ValueError(f"missing candle columns in {path}: {','.join(missing)}")
    frame = frame[needed].copy()
    for column in needed:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["ts", "open", "high", "low", "close"])
    frame = frame[frame["close"] > 0].copy()
    return frame.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="coerce").astype(float)
    close = data["close"]
    high = data["high"]
    low = data["low"]
    open_ = data["open"]
    volume = data["volume"].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    for window in (1, 3, 8, 20):
        data[f"ret_{window}_bps"] = close.pct_change(window) * 10000.0
    data["ma_gap_8_20_bps"] = (close.rolling(8).mean() / close.rolling(20).mean() - 1.0) * 10000.0
    data["vol_bps_20"] = data["ret_1_bps"].rolling(20).std()
    data["avg_abs_bps_20"] = data["ret_1_bps"].abs().rolling(20).mean()
    low_min = low.rolling(20).min()
    data["range_bps_20"] = np.where(low_min > 0, (high.rolling(20).max() / low_min - 1.0) * 10000.0, np.nan)
    data["body_bps"] = np.where(open_ > 0, (close / open_ - 1.0) * 10000.0, 0.0)

    atr = AverageTrueRange(high=high, low=low, close=close, window=14, fillna=False).average_true_range()
    data["atr_bps_14"] = np.where(close > 0, atr / close * 10000.0, np.nan)
    adx = ADXIndicator(high=high, low=low, close=close, window=14, fillna=False)
    data["adx_14"] = adx.adx()
    data["plus_di_14"] = adx.adx_pos()
    data["minus_di_14"] = adx.adx_neg()
    data["chop_14"] = choppiness_index(high, low, close, period=14)

    path_bps = data["ret_1_bps"].abs().rolling(20).sum()
    data["efficiency_20"] = np.where(path_bps > 0, data["ret_20_bps"].abs() / path_bps, 0.0)

    volume_mean = volume.rolling(20).mean()
    volume_std = volume.rolling(20).std()
    data["volume_z_20"] = np.where(volume_std > 0, (volume - volume_mean) / volume_std, 0.0)

    data[FEATURE_COLUMNS] = data[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    return data


def choppiness_index(high: pd.Series, low: pd.Series, close: pd.Series, *, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    high_max = high.rolling(period).max()
    low_min = low.rolling(period).min()
    denom = high_max - low_min
    raw = true_range.rolling(period).sum() / denom
    return 100.0 * np.log10(raw.where(raw > 0)) / math.log10(period)


def add_future_labels(frame: pd.DataFrame, config: LabelConfig | None = None) -> pd.DataFrame:
    config = config or LabelConfig()
    data = add_features(frame)
    close = data["close"]
    future_close = close.shift(-config.horizon)
    future_ret_bps = (future_close / close - 1.0) * 10000.0
    future_high = data["high"].shift(-1).rolling(config.horizon).max().shift(-(config.horizon - 1))
    future_low = data["low"].shift(-1).rolling(config.horizon).min().shift(-(config.horizon - 1))
    future_range_bps = np.where(data["close"] > 0, (future_high / future_low - 1.0) * 10000.0, np.nan)
    future_efficiency = np.where(future_range_bps > 0, np.abs(future_ret_bps) / future_range_bps, 0.0)
    dynamic_threshold = np.maximum(config.min_trend_bps, data["vol_bps_20"].fillna(0.0) * config.trend_vol_multiplier)
    is_trend = (np.abs(future_ret_bps) >= dynamic_threshold) & (future_efficiency >= config.min_efficiency)
    labels = np.where(is_trend & (future_ret_bps > 0), "trend_up", np.where(is_trend & (future_ret_bps < 0), "trend_down", "range"))
    data["future_ret_bps"] = future_ret_bps
    data["future_range_bps"] = future_range_bps
    data["future_efficiency"] = future_efficiency
    data["regime_label"] = labels
    return data


def training_matrix(frames: list[pd.DataFrame], label_config: LabelConfig | None = None) -> tuple[pd.DataFrame, pd.Series]:
    rows = []
    for frame in frames:
        labeled = add_future_labels(frame, label_config)
        labeled = labeled.dropna(subset=FEATURE_COLUMNS + ["future_ret_bps", "regime_label"])
        rows.append(labeled)
    if not rows:
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=str)
    data = pd.concat(rows, ignore_index=True)
    return data[FEATURE_COLUMNS].astype(float), data["regime_label"].astype(str)


def latest_feature_row(candles: list[Any] | pd.DataFrame) -> pd.Series | None:
    frame = candles if isinstance(candles, pd.DataFrame) else candles_to_frame(candles)
    if len(frame) < 30:
        return None
    features = add_features(frame)
    valid = features.dropna(subset=FEATURE_COLUMNS)
    if valid.empty:
        return None
    return valid.iloc[-1]


def rules_signal(candles: list[Any] | pd.DataFrame, config: RuleConfig | None = None) -> RegimeSignal:
    config = config or RuleConfig()
    row = latest_feature_row(candles)
    if row is None:
        return RegimeSignal("unknown", "flat", 0.0, "rules", [], "insufficient candles", {})

    lookback_key = "ret_20_bps" if config.lookback <= 30 else "ret_20_bps"
    move_bps = float(row.get(lookback_key, 0.0) or 0.0)
    if abs(move_bps) < config.min_trend_bps and abs(float(row.get("ma_gap_8_20_bps", 0.0) or 0.0)) > config.min_trend_bps:
        move_bps = float(row.get("ma_gap_8_20_bps", 0.0) or 0.0)
    adx = float(row.get("adx_14", 0.0) or 0.0)
    chop = float(row.get("chop_14", 100.0) or 100.0)
    efficiency = float(row.get("efficiency_20", 0.0) or 0.0)
    plus_di = float(row.get("plus_di_14", 0.0) or 0.0)
    minus_di = float(row.get("minus_di_14", 0.0) or 0.0)

    trend_score = (
        0.35 * scale(adx, config.adx_threshold - 6.0, config.adx_threshold + 15.0)
        + 0.25 * scale(config.max_trend_chop - chop, 0.0, 18.0)
        + 0.25 * scale(efficiency, 0.16, 0.55)
        + 0.15 * scale(abs(move_bps), config.min_trend_bps, config.min_trend_bps * 3.0)
    )
    range_score = max(
        scale(chop, config.max_trend_chop, config.range_chop + 8.0),
        1.0 - scale(adx, config.adx_threshold - 8.0, config.adx_threshold + 5.0),
    )

    direction = "up" if move_bps > 0 else "down" if move_bps < 0 else "flat"
    if plus_di > minus_di * 1.08:
        direction = "up"
    elif minus_di > plus_di * 1.08:
        direction = "down"

    metrics = {
        "move_bps": move_bps,
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "chop": chop,
        "efficiency": efficiency,
        "trend_score": trend_score,
        "range_score": range_score,
    }
    if (
        trend_score >= config.confidence_threshold
        and adx >= config.adx_threshold
        and chop <= config.max_trend_chop
        and abs(move_bps) >= config.min_trend_bps
        and direction in {"up", "down"}
    ):
        state = "trend_up" if direction == "up" else "trend_down"
        confidence = min(0.99, trend_score)
        return RegimeSignal(state, direction, confidence, "rules", sides_for_state(state), "rules trend", metrics)
    if range_score >= config.confidence_threshold:
        return RegimeSignal("range", "flat", min(0.99, range_score), "rules", sides_for_state("range"), "rules range", metrics)
    return RegimeSignal("mixed", direction, max(trend_score, range_score), "rules", [], "rules mixed", metrics)


def model_signal(
    candles: list[Any] | pd.DataFrame,
    *,
    model_path: str | Path,
    min_confidence: float = 0.52,
) -> RegimeSignal:
    if not model_path:
        return RegimeSignal("unknown", "flat", 0.0, "model", [], "missing model path", {})
    path = Path(model_path)
    if not path.exists():
        return RegimeSignal("unknown", "flat", 0.0, "model", [], f"model not found: {path}", {})
    row = latest_feature_row(candles)
    if row is None:
        return RegimeSignal("unknown", "flat", 0.0, "model", [], "insufficient candles", {})
    payload = load_model_payload(str(path))
    columns = payload.get("feature_columns", FEATURE_COLUMNS)
    x = row[columns].astype(float).to_frame().T
    kind = payload.get("kind", "rf")
    if kind == "rf":
        model = payload["model"]
        label = str(model.predict(x)[0])
        confidence = 1.0
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(x)[0]
            confidence = float(np.max(probabilities))
        if confidence < min_confidence:
            label = "mixed"
        return RegimeSignal(label, direction_for_state(label), confidence, "rf", sides_for_state(label), f"rf {label}", row_metrics(row))

    if kind == "hmm":
        scaler = payload["scaler"]
        model = payload["model"]
        state_map = {str(key): value for key, value in payload.get("state_map", {}).items()}
        hidden_state = int(model.predict(scaler.transform(x))[0])
        label = str(state_map.get(str(hidden_state), "mixed"))
        confidence = float(payload.get("state_confidence", {}).get(str(hidden_state), 0.55))
        if confidence < min_confidence:
            label = "mixed"
        return RegimeSignal(label, direction_for_state(label), confidence, "hmm", sides_for_state(label), f"hmm state={hidden_state} {label}", row_metrics(row))

    return RegimeSignal("unknown", "flat", 0.0, str(kind), [], f"unsupported model kind: {kind}", row_metrics(row))


def signal_from_candles(
    candles: list[Any] | pd.DataFrame,
    *,
    mode: str = "off",
    model_path: str | Path = "",
    min_confidence: float = 0.52,
    rule_config: RuleConfig | None = None,
) -> RegimeSignal:
    if mode == "off":
        return RegimeSignal("off", "flat", 1.0, "off", [], "off", {})
    if mode == "rules":
        return rules_signal(candles, rule_config)
    if mode in {"rf", "hmm"}:
        return model_signal(candles, model_path=model_path, min_confidence=min_confidence)
    return RegimeSignal("unknown", "flat", 0.0, mode, [], f"unknown mode: {mode}", {})


def sides_for_state(state: str) -> list[str]:
    if state == "trend_up":
        return ["long"]
    if state == "trend_down":
        return ["short"]
    if state == "range":
        return ["long", "short"]
    return []


def direction_for_state(state: str) -> str:
    if state == "trend_up":
        return "up"
    if state == "trend_down":
        return "down"
    return "flat"


def signal_to_dict(signal: RegimeSignal) -> dict[str, Any]:
    return asdict(signal)


def row_metrics(row: pd.Series) -> dict[str, float]:
    keys = ["ret_20_bps", "ma_gap_8_20_bps", "adx_14", "plus_di_14", "minus_di_14", "chop_14", "efficiency_20", "atr_bps_14"]
    return {key: float(row.get(key, 0.0) or 0.0) for key in keys}


@lru_cache(maxsize=8)
def load_model_payload(path: str) -> dict[str, Any]:
    return joblib.load(path)


def scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def safe_float(value: Any, default: float = np.nan) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default
