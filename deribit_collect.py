"""Public Deribit increment for the data lake.

BTC/ETH perpetual candles, funding, and DVOL only. Deribit has no gold
contract. This module never loads .env or touches accounts/orders.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError

import pandas as pd

import data_pipeline as dp


DERIBIT_BASE = "https://www.deribit.com/api/v2/public"
DEFAULT_PERPS = ("BTC-PERPETUAL", "ETH-PERPETUAL")
DEFAULT_DVOL = ("BTC", "ETH")
USER_AGENT = "okx-quant-deribit-lake/1.0"
CANDLE_RESOLUTION = "60"
DVOL_RESOLUTION = "3600"
WINDOW_MS = 80 * 86_400_000
HTTPGetter = Callable[[str], dict[str, Any]]


def deribit_dir() -> Path:
    return dp.LAKE_ROOT / "deribit"


def utc_ms(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def from_ms(ts: int) -> datetime:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)


def default_http_get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise RuntimeError("Deribit response is not an object")
            if payload.get("error"):
                raise RuntimeError(f"Deribit error: {payload['error']}")
            return payload
        except HTTPError as exc:
            last_error = exc
            if exc.code == 400:
                return {"result": {}}
            time.sleep(0.25 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"Deribit request failed: {last_error}")


def public_get(path: str, params: dict[str, Any], *, http_get: HTTPGetter) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{DERIBIT_BASE}/{path}?{query}"
    return http_get(url)


def parse_chart(payload: dict[str, Any]) -> pd.DataFrame:
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or not result.get("ticks"):
        return pd.DataFrame()
    ticks = result.get("ticks") or []
    opens = result.get("open") or []
    highs = result.get("high") or []
    lows = result.get("low") or []
    closes = result.get("close") or []
    volumes = result.get("volume") or []
    rows = []
    for index, ts in enumerate(ticks):
        close = float(closes[index]) if index < len(closes) else 0.0
        if close <= 0:
            continue
        rows.append(
            {
                "ts": int(ts),
                "time": from_ms(int(ts)),
                "open": float(opens[index]) if index < len(opens) else close,
                "high": float(highs[index]) if index < len(highs) else close,
                "low": float(lows[index]) if index < len(lows) else close,
                "close": close,
                "volume": float(volumes[index]) if index < len(volumes) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def parse_funding(payload: dict[str, Any]) -> pd.DataFrame:
    result = payload.get("result") if isinstance(payload, dict) else None
    rows = result if isinstance(result, list) else []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        ts = int(item.get("timestamp") or 0)
        if ts <= 0:
            continue
        rate = float(item.get("interest_8h") or item.get("interest_1h") or 0.0)
        out.append(
            {
                "ts": ts,
                "funding_time": from_ms(ts),
                "funding_rate": rate,
                "realized_rate": rate,
            }
        )
    return pd.DataFrame(out)


def parse_dvol(payload: dict[str, Any]) -> pd.DataFrame:
    result = payload.get("result") if isinstance(payload, dict) else None
    data = result.get("data") if isinstance(result, dict) else result
    if not isinstance(data, list):
        return pd.DataFrame()
    rows = []
    for item in data:
        if not isinstance(item, (list, tuple)) or len(item) < 5:
            continue
        ts = int(item[0])
        close = float(item[4])
        if close <= 0:
            continue
        rows.append(
            {
                "ts": ts,
                "time": from_ms(ts),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": close,
            }
        )
    return pd.DataFrame(rows)


def _read_parquet_dir(root: Path) -> pd.DataFrame:
    if not root.is_dir():
        return pd.DataFrame()
    frames = [pd.read_parquet(path) for path in sorted(root.glob("*.parquet"))]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_deribit_candles(inst_id: str, timeframe: str = "1h",
                         start: str | None = None, end: str | None = None) -> pd.DataFrame:
    frame = _read_parquet_dir(deribit_dir() / "candles" / dp.safe_inst(inst_id) / dp.normalize_timeframe(timeframe))
    if frame.empty:
        return frame
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    if start:
        frame = frame[frame["time"] >= pd.to_datetime(start, utc=True)]
    if end:
        frame = frame[frame["time"] <= pd.to_datetime(end, utc=True)]
    return frame.reset_index(drop=True)


def load_deribit_funding(inst_id: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    frame = _read_parquet_dir(deribit_dir() / "funding" / dp.safe_inst(inst_id))
    if frame.empty:
        return frame
    frame["funding_time"] = pd.to_datetime(frame["funding_time"], utc=True)
    frame = frame.sort_values("funding_time").drop_duplicates(subset=["funding_time"], keep="last")
    if start:
        frame = frame[frame["funding_time"] >= pd.to_datetime(start, utc=True)]
    if end:
        frame = frame[frame["funding_time"] <= pd.to_datetime(end, utc=True)]
    return frame.reset_index(drop=True)


def load_deribit_dvol(currency: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    frame = _read_parquet_dir(deribit_dir() / "dvol" / currency.lower())
    if frame.empty:
        return frame
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    if start:
        frame = frame[frame["time"] >= pd.to_datetime(start, utc=True)]
    if end:
        frame = frame[frame["time"] <= pd.to_datetime(end, utc=True)]
    return frame.reset_index(drop=True)


def _write_yearly(frame: pd.DataFrame, root: Path, time_col: str, columns: list[str]) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    if frame.empty:
        return []
    written: list[Path] = []
    copy = frame.copy()
    copy["year"] = copy[time_col].dt.year
    for year, group in copy.groupby("year"):
        path = root / f"{int(year)}.parquet"
        existing = pd.read_parquet(path) if path.exists() else pd.DataFrame()
        if not existing.empty:
            existing[time_col] = pd.to_datetime(existing[time_col], utc=True)
        merged = pd.concat([existing, group[columns]], ignore_index=True)
        merged = merged.sort_values(time_col).drop_duplicates(subset=[time_col], keep="last")
        merged.to_parquet(path, index=False)
        written.append(path)
    return written


def _windows(start: datetime, end: datetime) -> list[tuple[int, int]]:
    cursor = utc_ms(start)
    stop = utc_ms(end)
    out: list[tuple[int, int]] = []
    while cursor < stop:
        nxt = min(cursor + WINDOW_MS, stop)
        out.append((cursor, nxt))
        cursor = nxt
    return out


def collect_deribit_candles(
    inst_ids: tuple[str, ...] = DEFAULT_PERPS,
    *,
    lookback_days: int = 400,
    http_get: HTTPGetter = default_http_get,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    start_floor = now - timedelta(days=lookback_days)
    counts: dict[str, int] = {}
    for inst in inst_ids:
        existing = load_deribit_candles(inst, "1h")
        begin = start_floor
        if not existing.empty:
            begin = max(start_floor, existing["time"].max().to_pydatetime().astimezone(timezone.utc) - timedelta(hours=2))
        frames = []
        for start_ms, end_ms in _windows(begin, now):
            payload = public_get(
                "get_tradingview_chart_data",
                {
                    "instrument_name": inst,
                    "start_timestamp": start_ms,
                    "end_timestamp": end_ms,
                    "resolution": CANDLE_RESOLUTION,
                },
                http_get=http_get,
            )
            frame = parse_chart(payload)
            if not frame.empty:
                frame["inst_id"] = inst
                frame["timeframe"] = "1h"
                frames.append(frame)
            time.sleep(0.12)
        if not frames:
            counts[inst] = 0
            continue
        new_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["time"], keep="last")
        before = 0 if existing.empty else len(existing)
        _write_yearly(
            new_df,
            deribit_dir() / "candles" / dp.safe_inst(inst) / "1h",
            "time",
            ["time", "ts", "open", "high", "low", "close", "volume", "inst_id", "timeframe"],
        )
        counts[inst] = max(0, len(load_deribit_candles(inst, "1h")) - before)
    return counts


def collect_deribit_funding(
    inst_ids: tuple[str, ...] = DEFAULT_PERPS,
    *,
    lookback_days: int = 400,
    http_get: HTTPGetter = default_http_get,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    start_floor = now - timedelta(days=lookback_days)
    counts: dict[str, int] = {}
    for inst in inst_ids:
        existing = load_deribit_funding(inst)
        begin = start_floor
        if not existing.empty:
            begin = max(start_floor, existing["funding_time"].max().to_pydatetime().astimezone(timezone.utc) - timedelta(hours=8))
        frames = []
        for start_ms, end_ms in _windows(begin, now):
            payload = public_get(
                "get_funding_rate_history",
                {
                    "instrument_name": inst,
                    "start_timestamp": start_ms,
                    "end_timestamp": end_ms,
                },
                http_get=http_get,
            )
            frame = parse_funding(payload)
            if not frame.empty:
                frame["inst_id"] = inst
                frames.append(frame)
            time.sleep(0.12)
        if not frames:
            counts[inst] = 0
            continue
        new_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["funding_time"], keep="last")
        before = 0 if existing.empty else len(existing)
        _write_yearly(
            new_df,
            deribit_dir() / "funding" / dp.safe_inst(inst),
            "funding_time",
            ["funding_time", "ts", "funding_rate", "realized_rate", "inst_id"],
        )
        counts[inst] = max(0, len(load_deribit_funding(inst)) - before)
    return counts


def collect_deribit_dvol(
    currencies: tuple[str, ...] = DEFAULT_DVOL,
    *,
    lookback_days: int = 400,
    http_get: HTTPGetter = default_http_get,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    start_floor = now - timedelta(days=lookback_days)
    counts: dict[str, int] = {}
    for currency in currencies:
        existing = load_deribit_dvol(currency)
        begin = start_floor
        if not existing.empty:
            begin = max(start_floor, existing["time"].max().to_pydatetime().astimezone(timezone.utc) - timedelta(hours=2))
        frames = []
        for start_ms, end_ms in _windows(begin, now):
            payload = public_get(
                "get_volatility_index_data",
                {
                    "currency": currency,
                    "start_timestamp": start_ms,
                    "end_timestamp": end_ms,
                    "resolution": DVOL_RESOLUTION,
                },
                http_get=http_get,
            )
            frame = parse_dvol(payload)
            if not frame.empty:
                frame["currency"] = currency
                frames.append(frame)
            time.sleep(0.12)
        if not frames:
            counts[currency] = 0
            continue
        new_df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["time"], keep="last")
        before = 0 if existing.empty else len(existing)
        _write_yearly(
            new_df,
            deribit_dir() / "dvol" / currency.lower(),
            "time",
            ["time", "ts", "open", "high", "low", "close", "currency"],
        )
        counts[currency] = max(0, len(load_deribit_dvol(currency)) - before)
    return counts


def collect_deribit(
    *,
    lookback_days: int = 400,
    http_get: HTTPGetter = default_http_get,
) -> dict[str, Any]:
    """Increment BTC/ETH Deribit public series into data_lake/deribit/."""

    return {
        "candles": collect_deribit_candles(lookback_days=lookback_days, http_get=http_get),
        "funding": collect_deribit_funding(lookback_days=lookback_days, http_get=http_get),
        "dvol": collect_deribit_dvol(lookback_days=lookback_days, http_get=http_get),
    }


def scan_deribit_coverage() -> dict[str, Any]:
    root = deribit_dir()
    if not root.is_dir():
        return {"candleFiles": 0, "fundingFiles": 0, "dvolFiles": 0, "latest": None}
    candle_files = list(root.glob("candles/*/*/*.parquet"))
    funding_files = list(root.glob("funding/*/*.parquet"))
    dvol_files = list(root.glob("dvol/*/*.parquet"))
    latest = None
    for path in candle_files + funding_files + dvol_files:
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if latest is None or stamp > latest:
            latest = stamp
    return {
        "candleFiles": len(candle_files),
        "fundingFiles": len(funding_files),
        "dvolFiles": len(dvol_files),
        "latest": latest.isoformat() if latest else None,
    }
