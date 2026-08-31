#!/usr/bin/env python3
"""Unified read-only data lake pipeline for the OKX quant project.

Layout (data_lake/, a symlink to data/data_lake on the data disk):
  candles/<INST>/<TIMEFRAME>/<YYYY>.parquet   -- OHLCV candles (one file per year)
  funding/<INST>/<YYYY>.parquet               -- funding rate history
  snapshots -> data/microstructure            -- single 30-min snapshot store
  events/<YYYYMMDD>.jsonl                     -- normalized point-in-time event observations
  events/raw/<SOURCE>/<DATE>/*.json            -- immutable public source responses
  research/<MODEL_ID>/<YYYYMMDD>.jsonl         -- frozen-model forward observations
  deribit/candles|funding|dvol                 -- public Deribit BTC/ETH perp, funding, DVOL
  manifest.json                               -- index: schema, coverage, checksum, source path

Commands:
  build    -- scan existing data/ sources, convert to parquet, write manifest
  collect  -- incremental fetch of candles/funding from OKX public endpoints
              plus a refresh of the locked QQQ Yahoo/SEC caches
              (no .env, no account access, read-only public market data)
  manifest -- rebuild manifest.json from current data_lake contents
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - pyarrow is a hard dep for parquet output
    pa = None  # type: ignore[assignment]
    pq = None  # type: ignore[assignment]

# Project roots -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data"
LAKE_ROOT = PROJECT_ROOT / "data_lake"
MANIFEST_PATH = LAKE_ROOT / "manifest.json"
TRADFI_TRACKING_PATH = PROJECT_ROOT / "config" / "tradfi_index_tracking.json"
LOCKED_QQQ_UNIVERSE_PATH = (
    PROJECT_ROOT / "reports" / "qqq_active_enhancement" / "qqq-pit-20260808-v5" / "universe.csv"
)
LOCKED_QQQ_DATA_ROOT = DATA_ROOT / "qqq_active_enhancement"
LOCKED_QQQ_INCREMENT_ROOT = DATA_ROOT / "qqq_active_enhancement_increment"
LOCKED_EQUITY_HISTORY_RANGE = "10y"

BASE_COLLECTION_INSTRUMENTS = (
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SKHY-USDT-SWAP",
    "SOXL-USDT-SWAP",
    "XAU-USDT-SWAP",
)
CORE_DAILY_INSTRUMENTS = (
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "XAU-USDT-SWAP",
)
CORE_DAILY_EXTRA_TIMEFRAMES = ("15m", "30m", "1h")

CANDLE_DIR = LAKE_ROOT / "candles"
FUNDING_DIR = LAKE_ROOT / "funding"
SNAPSHOT_DIR = LAKE_ROOT / "snapshots"
EVENT_DIR = LAKE_ROOT / "events"
RESEARCH_DIR = LAKE_ROOT / "research"

# Source layout in data/ ---------------------------------------------------------
CANDLE_SOURCE_DIR = DATA_ROOT / "backtest"          # "<INST>_<TF>_<300xN>.csv"
FUNDING_SOURCE_DIR = DATA_ROOT / "funding"          # "<INST>_funding_100.csv"
SNAPSHOT_SOURCE_DIR = DATA_ROOT / "microstructure"  # "<inst>/*.jsonl"
WS_SOURCE_DIR = DATA_ROOT / "microstructure_ws"     # "<inst>/*.jsonl" (raw ws)

# Canonical candle columns (aligned with existing backtest CSVs)
CANDLE_COLUMNS = ["ts", "time", "open", "high", "low", "close", "volume"]
CANDLE_TYPES = {
    "ts": "int64",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
}

# Funding CSV columns
FUNDING_COLUMNS = ["funding_time", "funding_rate", "realized_rate"]
FUNDING_TYPES = {
    "funding_time": "int64",
    "funding_rate": "float64",
    "realized_rate": "float64",
}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_inst(inst_id: str) -> str:
    return inst_id.lower().replace("-", "_")


def parse_candle_csv_name(name: str) -> tuple[str, str] | None:
    """Parse 'BTC-USDT-SWAP_5m_300x24.csv' -> ('BTC-USDT-SWAP', '5m')."""
    m = re.match(r"^(.*?)_(\d+[mH])_(?:\d+x\d+|\d+)\.csv$", name)
    if not m:
        return None
    inst, tf = m.group(1), m.group(2)
    return inst, tf


def normalize_timeframe(tf: str) -> str:
    """Normalize '1H' -> '1h', keep '5m', '15m' etc."""
    return tf.replace("H", "h").replace("D", "d")


def to_okx_bar(tf: str) -> str:
    """OKX history-candles uses 1H/1D, not 1h/1d."""
    tf = normalize_timeframe(tf)
    if tf.endswith("h"):
        return f"{tf[:-1]}H"
    if tf.endswith("d"):
        return f"{tf[:-1]}D"
    return tf


def tf_to_minutes(tf: str) -> int:
    tf = tf.lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    raise ValueError(f"unknown timeframe {tf}")


def load_csv_frame(path: Path, columns: list[str], dtypes: dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(path)
    # keep only known columns, reorder
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    df = df[columns].copy()
    for col, dt in dtypes.items():
        if col in df.columns:
            df[col] = df[col].astype(dt)
    return df


def read_candle_csv(path: Path) -> pd.DataFrame:
    df = load_csv_frame(path, CANDLE_COLUMNS, CANDLE_TYPES)
    df["inst_id"] = parse_candle_csv_name(path.name)[0]
    df["timeframe"] = normalize_timeframe(parse_candle_csv_name(path.name)[1])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    return df


def read_funding_csv(path: Path) -> pd.DataFrame:
    df = load_csv_frame(path, FUNDING_COLUMNS, FUNDING_TYPES)
    inst = path.name.replace("_funding_100.csv", "")
    df["inst_id"] = inst
    df["funding_time"] = pd.to_datetime(df["funding_time"], unit="ms", utc=True)
    df = df.sort_values("funding_time").drop_duplicates(subset=["funding_time"], keep="last")
    return df


# Parquet writers ----------------------------------------------------------------
def write_candle_parquet(df: pd.DataFrame, inst: str, tf: str) -> list[Path]:
    """Write one parquet per year under candles/<inst>/<tf>/. Returns written paths."""
    out_dir = CANDLE_DIR / safe_inst(inst) / tf
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if df.empty:
        return paths
    df = df.copy()
    df["year"] = df["time"].dt.year
    for year, group in df.groupby("year"):
        path = out_dir / f"{year}.parquet"
        cols = [c for c in CANDLE_COLUMNS if c != "ts"] + ["inst_id", "timeframe"]
        # ts (ms) derived from time
        g = group.copy()
        g["ts"] = (g["time"].astype("int64") // 10**6).astype("int64")
        g = g[["time", "ts", "open", "high", "low", "close", "volume", "inst_id", "timeframe"]]
        g.to_parquet(path, index=False)
        paths.append(path)
    return paths


def write_funding_parquet(df: pd.DataFrame, inst: str) -> list[Path]:
    out_dir = FUNDING_DIR / safe_inst(inst)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if df.empty:
        return paths
    df = df.copy()
    df["year"] = df["funding_time"].dt.year
    for year, group in df.groupby("year"):
        path = out_dir / f"{year}.parquet"
        g = group.copy()
        g["ts"] = (g["funding_time"].astype("int64") // 10**6).astype("int64")
        g = g[["funding_time", "ts", "funding_rate", "realized_rate", "inst_id"]]
        g.to_parquet(path, index=False)
        paths.append(path)
    return paths


# Source scanning -----------------------------------------------------------------
def scan_candle_sources() -> list[dict[str, Any]]:
    """Inventory data/backtest candle CSVs."""
    rows: list[dict[str, Any]] = []
    for path in sorted(CANDLE_SOURCE_DIR.glob("*.csv")):
        parsed = parse_candle_csv_name(path.name)
        if not parsed:
            continue
        inst, tf = parsed
        try:
            df = read_candle_csv(path)
        except Exception as exc:  # noqa: BLE001
            rows.append({"path": str(path), "error": str(exc), "inst": inst, "tf": tf})
            continue
        rows.append({
            "path": str(path),
            "inst": inst,
            "timeframe": normalize_timeframe(tf),
            "rows": int(len(df)),
            "first": df["time"].min().isoformat() if not df.empty else None,
            "last": df["time"].max().isoformat() if not df.empty else None,
        })
    return rows


def scan_funding_sources() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(FUNDING_SOURCE_DIR.glob("*_funding_*.csv")):
        inst = path.name.replace("_funding_100.csv", "")
        try:
            df = read_funding_csv(path)
        except Exception as exc:  # noqa: BLE001
            rows.append({"path": str(path), "inst": inst, "error": str(exc)})
            continue
        rows.append({
            "path": str(path),
            "inst": inst,
            "rows": int(len(df)),
            "first": df["funding_time"].min().isoformat() if not df.empty else None,
            "last": df["funding_time"].max().isoformat() if not df.empty else None,
        })
    return rows


def same_snapshot_store() -> bool:
    """True when lake snapshots and data/microstructure are the same directory."""

    try:
        return SNAPSHOT_DIR.resolve() == SNAPSHOT_SOURCE_DIR.resolve()
    except OSError:
        return False


def scan_snapshot_sources() -> list[dict[str, Any]]:
    rows = []
    for inst_dir in sorted(SNAPSHOT_SOURCE_DIR.iterdir()):
        if not inst_dir.is_dir():
            continue
        files = sorted(inst_dir.glob("*.jsonl"))
        if not files:
            continue
        total = 0
        for f in files:
            with open(f, encoding="utf-8", errors="replace") as fh:
                total += sum(1 for _ in fh)
        rows.append({
            "inst": inst_dir.name,
            "files": [f.name for f in files],
            "rows": total,
            "first_file": files[0].name,
            "last_file": files[-1].name,
        })
    return rows


def scan_ws_sources() -> list[dict[str, Any]]:
    rows = []
    for inst_dir in sorted(WS_SOURCE_DIR.iterdir()):
        if not inst_dir.is_dir():
            continue
        files = sorted(inst_dir.glob("*.jsonl"))
        total = 0
        for f in files:
            with open(f, encoding="utf-8", errors="replace") as fh:
                total += sum(1 for _ in fh)
        rows.append({
            "inst": inst_dir.name,
            "files": [f.name for f in files],
            "rows": total,
        })
    return rows


def scan_option_sources() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((DATA_ROOT / "options").glob("*.json")):
        rows.append({"path": str(path), "size_bytes": path.stat().st_size})
    return rows


def scan_equity_sources() -> list[dict[str, Any]]:
    """Yahoo daily/5m CSVs under data/tradfi_intraday and data/qqq_active_enhancement/prices."""
    rows = []
    for d in (DATA_ROOT / "tradfi_intraday", DATA_ROOT / "qqq_active_enhancement" / "prices"):
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.csv")):
            rows.append({"path": str(path), "size_bytes": path.stat().st_size})
    return rows


def scan_jsonl_dataset(root: Path) -> list[dict[str, Any]]:
    """Inventory append-only JSONL datasets without loading their payloads."""

    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.jsonl")):
        relative = path.relative_to(root)
        with path.open(encoding="utf-8", errors="replace") as handle:
            count = sum(1 for line in handle if line.strip())
        rows.append(
            {
                "path": str(path),
                "relativePath": str(relative),
                "rows": count,
                "sizeBytes": path.stat().st_size,
            }
        )
    return rows


# Manifest -------------------------------------------------------------------------
def _count_lake_parquet(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.parquet"))


def scan_lake_candle_coverage() -> dict[str, list[dict[str, Any]]]:
    """Build candle coverage from parquet files actually present in the lake."""

    coverage: dict[str, list[dict[str, Any]]] = {}
    if not CANDLE_DIR.is_dir():
        return coverage
    for path in sorted(CANDLE_DIR.glob("*/*/*.parquet")):
        try:
            frame = pd.read_parquet(path, columns=["time", "inst_id", "timeframe"])
            if frame.empty:
                continue
            times = pd.to_datetime(frame["time"], utc=True)
            inst_id = str(frame["inst_id"].iloc[-1])
            timeframe = normalize_timeframe(str(frame["timeframe"].iloc[-1]))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"failed to index candle parquet {path}: {exc}") from exc
        coverage.setdefault(f"{inst_id}/{timeframe}", []).append(
            {
                "rows": int(len(frame)),
                "first": times.min().isoformat(),
                "last": times.max().isoformat(),
                "parquet": str(path),
            }
        )
    return coverage


def scan_lake_funding_coverage() -> dict[str, list[dict[str, Any]]]:
    """Build funding coverage from parquet files actually present in the lake."""

    coverage: dict[str, list[dict[str, Any]]] = {}
    if not FUNDING_DIR.is_dir():
        return coverage
    for path in sorted(FUNDING_DIR.glob("*/*.parquet")):
        try:
            frame = pd.read_parquet(path, columns=["funding_time", "inst_id"])
            if frame.empty:
                continue
            times = pd.to_datetime(frame["funding_time"], utc=True)
            inst_id = str(frame["inst_id"].iloc[-1])
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"failed to index funding parquet {path}: {exc}") from exc
        coverage.setdefault(inst_id, []).append(
            {
                "rows": int(len(frame)),
                "first": times.min().isoformat(),
                "last": times.max().isoformat(),
                "parquet": str(path),
            }
        )
    return coverage


def build_manifest() -> dict[str, Any]:
    candle_sources = scan_candle_sources()
    funding_sources = scan_funding_sources()
    snapshot_sources = scan_snapshot_sources()
    ws_sources = scan_ws_sources()
    option_sources = scan_option_sources()
    equity_sources = scan_equity_sources()
    event_sources = scan_jsonl_dataset(EVENT_DIR)
    research_sources = scan_jsonl_dataset(RESEARCH_DIR)
    from deribit_collect import scan_deribit_coverage

    candle_coverage = scan_lake_candle_coverage()
    funding_coverage = scan_lake_funding_coverage()
    deribit_coverage = scan_deribit_coverage()

    return {
        "schemaVersion": 1,
        "generatedAt": utcnow_iso(),
        "lakeRoot": str(LAKE_ROOT),
        "sources": {
            "candles": candle_sources,
            "funding": funding_sources,
            "snapshots": snapshot_sources,
            "microstructure_ws": ws_sources,
            "options": option_sources,
            "equity": equity_sources,
            "events": event_sources,
            "research": research_sources,
            "deribit": deribit_coverage,
        },
        "coverage": {
            "candles": candle_coverage,
            "funding": funding_coverage,
        },
        "stats": {
            "candleFiles": _count_lake_parquet(CANDLE_DIR),
            "fundingInstruments": len(funding_coverage),
            "snapshotInstruments": len(snapshot_sources),
            "eventFiles": len(event_sources),
            "eventRows": sum(int(row["rows"]) for row in event_sources),
            "researchModels": len({Path(row["relativePath"]).parts[0] for row in research_sources}),
            "researchRows": sum(int(row["rows"]) for row in research_sources),
            "deribitCandleFiles": int(deribit_coverage.get("candleFiles") or 0),
            "deribitFundingFiles": int(deribit_coverage.get("fundingFiles") or 0),
            "deribitDvolFiles": int(deribit_coverage.get("dvolFiles") or 0),
        },
    }


def write_manifest(manifest: dict[str, Any]) -> None:
    LAKE_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    tmp.replace(MANIFEST_PATH)


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# Incremental collect ----------------------------------------------------------------
def okx_public_request(client: Any, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Use the OkxRestClient generic request against a public market endpoint."""
    resp = client.request("GET", path, params=params)
    data = resp.get("data", []) if isinstance(resp, dict) else []
    return data if isinstance(data, list) else []


def history_candle_frame(data: list[Any], inst: str, timeframe: str) -> pd.DataFrame:
    rows = []
    for item in data:
        # OKX history-candles returns each candle as a list:
        # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        if isinstance(item, list):
            ts = int(item[0])
            open_, high, low, close, vol = float(item[1]), float(item[2]), float(item[3]), float(item[4]), float(item[5])
        else:
            ts = int(item["ts"])
            open_ = float(item["o"])
            high = float(item["h"])
            low = float(item["l"])
            close = float(item["c"])
            vol = float(item["vol"])
        rows.append({
            "ts": ts,
            "time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
            "inst_id": inst,
            "timeframe": timeframe,
        })
    return pd.DataFrame(rows)


def page_history_candles(
    client: Any,
    inst: str,
    timeframe: str,
    *,
    stop_at: datetime,
    page_after: datetime | None = None,
    limit: int = 300,
    max_pages: int = 200,
) -> list[pd.DataFrame]:
    """Walk /history-candles older via `after` until empty or oldest <= stop_at."""

    frames: list[pd.DataFrame] = []
    seen_oldest: set[int] = set()
    for _ in range(max_pages):
        params = {"instId": inst, "bar": to_okx_bar(timeframe), "limit": str(limit)}
        if page_after is not None:
            params["after"] = str(int(page_after.timestamp() * 1000))
        data = okx_public_request(client, "/api/v5/market/history-candles", params)
        if not data:
            break
        frame = history_candle_frame(data, inst, timeframe)
        if frame.empty:
            break
        frames.append(frame)
        oldest = int(frame["ts"].min())
        if oldest in seen_oldest:
            break
        seen_oldest.add(oldest)
        oldest_dt = datetime.fromtimestamp(oldest / 1000, tz=timezone.utc)
        if oldest_dt <= stop_at:
            break
        page_after = oldest_dt
        time.sleep(0.15)
    return frames


def collect_candles(client: Any, inst_ids: list[str], timeframe: str = "5m",
                    *, lookback_days: int = 180, limit: int = 300,
                    backfill: bool = False) -> dict[str, int]:
    """Fetch candles into data_lake/candles/<inst>/<tf>/.

    Default is incremental from the newest public page down to the later of
    lookback or the latest stored bar. ``backfill=True`` also walks older
    than the earliest stored bar, down to the lookback cutoff.
    """
    counts: dict[str, int] = {}
    now = datetime.now(timezone.utc)
    start_cutoff = now - timedelta(days=lookback_days)
    max_pages = 400 if backfill else 200

    for inst in inst_ids:
        try:
            existing = load_candles(inst, timeframe)
        except Exception:  # noqa: BLE001
            existing = pd.DataFrame()
        existing_latest: datetime | None = None
        existing_earliest: datetime | None = None
        if not existing.empty:
            existing_latest = existing["time"].max().to_pydatetime().astimezone(timezone.utc)
            existing_earliest = existing["time"].min().to_pydatetime().astimezone(timezone.utc)
        increment_stop = max(start_cutoff, existing_latest) if existing_latest else start_cutoff

        frames = page_history_candles(
            client,
            inst,
            timeframe,
            stop_at=increment_stop,
            limit=limit,
            max_pages=max_pages,
        )
        if backfill and (existing_earliest is None or existing_earliest > start_cutoff):
            frames.extend(
                page_history_candles(
                    client,
                    inst,
                    timeframe,
                    stop_at=start_cutoff,
                    page_after=existing_earliest or now,
                    limit=limit,
                    max_pages=max_pages,
                )
            )

        if not frames:
            counts[inst] = 0
            continue
        new_df = pd.concat(frames, ignore_index=True)
        new_df = new_df[new_df["time"] >= pd.Timestamp(start_cutoff)]
        new_df = new_df.drop_duplicates(subset=["time"], keep="last")
        before = 0 if existing.empty else len(existing)
        merged = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
        merged = merged.drop_duplicates(subset=["time"], keep="last").sort_values("time")
        written = write_candle_parquet(merged, inst, timeframe)
        counts[inst] = max(0, int(len(merged) - before))
        print(f"  {inst} {timeframe}: +{counts[inst]} new rows, {len(written)} parquet file(s)")
    return counts


def collect_funding(client: Any, inst_ids: list[str], *, limit: int = 300) -> dict[str, int]:
    """Incrementally fetch funding history (8h cadence) into data_lake/funding/<inst>/."""
    path = "/api/v5/public/funding-rate-history"
    counts: dict[str, int] = {}
    for inst in inst_ids:
        try:
            existing = load_funding(inst)
        except Exception:  # noqa: BLE001
            existing = pd.DataFrame()
        before = None
        if not existing.empty:
            before = existing["funding_time"].max().to_pydatetime().replace(tzinfo=timezone.utc)

        params = {"instId": inst, "limit": str(limit)}
        if before:
            params["before"] = str(int(before.timestamp() * 1000) + 1)
        data = okx_public_request(client, path, params)
        rows = []
        for d in data:
            rows.append({
                "funding_time": pd.to_datetime(int(d["fundingTime"]), unit="ms", utc=True),
                "ts": int(d["fundingTime"]),
                "funding_rate": float(d["fundingRate"]),
                "realized_rate": float(d.get("realizedRate") or d["fundingRate"]),
                "inst_id": inst,
            })
        new_df = pd.DataFrame(rows)
        if not new_df.empty:
            new_df = new_df.drop_duplicates(subset=["funding_time"], keep="last")
        merged = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
        merged = merged.drop_duplicates(subset=["funding_time"], keep="last").sort_values("funding_time")
        written = write_funding_parquet(merged, inst)
        counts[inst] = int(len(new_df))
        print(f"  {inst}: +{len(new_df)} new funding rows, {len(written)} parquet file(s)")
    return counts


# Access API -------------------------------------------------------------------------
def load_candles(inst_id: str, timeframe: str = "5m",
                 start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Load candles for one instrument/timeframe from the lake.

    start/end are ISO timestamps (UTC). Returns a DataFrame sorted by time
    with columns: time, ts, open, high, low, close, volume, inst_id, timeframe.
    """
    inst_dir = CANDLE_DIR / safe_inst(inst_id) / normalize_timeframe(timeframe)
    frames: list[pd.DataFrame] = []
    if inst_dir.is_dir():
        for p in sorted(inst_dir.glob("*.parquet")):
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame(columns=["time", "ts", "open", "high", "low", "close", "volume", "inst_id", "timeframe"])
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").drop_duplicates(subset=["time"], keep="last")
    if start:
        df = df[df["time"] >= pd.to_datetime(start, utc=True)]
    if end:
        df = df[df["time"] <= pd.to_datetime(end, utc=True)]
    return df.reset_index(drop=True)


def load_funding(inst_id: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    inst_dir = FUNDING_DIR / safe_inst(inst_id)
    frames: list[pd.DataFrame] = []
    if inst_dir.is_dir():
        for p in sorted(inst_dir.glob("*.parquet")):
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame(columns=["funding_time", "ts", "funding_rate", "realized_rate", "inst_id"])
    df = pd.concat(frames, ignore_index=True)
    df["funding_time"] = pd.to_datetime(df["funding_time"], utc=True)
    df = df.sort_values("funding_time").drop_duplicates(subset=["funding_time"], keep="last")
    if start:
        df = df[df["funding_time"] >= pd.to_datetime(start, utc=True)]
    if end:
        df = df[df["funding_time"] <= pd.to_datetime(end, utc=True)]
    return df.reset_index(drop=True)


def load_snapshots(inst_id: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Load 30-min microstructure snapshots (JSONL) for one instrument."""
    inst_dir = SNAPSHOT_DIR / safe_inst(inst_id)
    if not inst_dir.is_dir():
        return pd.DataFrame()
    rows = []
    for p in sorted(inst_dir.glob("*.jsonl")):
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if not rows:
        return pd.DataFrame()
    df = pd.json_normalize(rows)
    if "capturedAt" in df.columns:
        df["capturedAt"] = pd.to_datetime(df["capturedAt"], utc=True)
    if start and "capturedAt" in df.columns:
        df = df[df["capturedAt"] >= pd.to_datetime(start, utc=True)]
    if end and "capturedAt" in df.columns:
        df = df[df["capturedAt"] <= pd.to_datetime(end, utc=True)]
    return df.reset_index(drop=True)


def _load_jsonl_rows(root: Path) -> list[dict[str, Any]]:
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


def _filter_observation_times(
    frame: pd.DataFrame,
    *,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    if frame.empty or "capturedAt" not in frame.columns:
        return frame.reset_index(drop=True)
    frame = frame.copy()
    frame["capturedAt"] = pd.to_datetime(frame["capturedAt"], utc=True, errors="coerce")
    if start:
        frame = frame[frame["capturedAt"] >= pd.to_datetime(start, utc=True)]
    if end:
        frame = frame[frame["capturedAt"] <= pd.to_datetime(end, utc=True)]
    return frame.sort_values("capturedAt").reset_index(drop=True)


def load_events(
    event_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load normalized point-in-time event observations from the data lake."""

    frame = pd.json_normalize(_load_jsonl_rows(EVENT_DIR))
    if frame.empty:
        return frame
    if event_id and "eventId" in frame.columns:
        frame = frame[frame["eventId"] == event_id]
    return _filter_observation_times(frame, start=start, end=end)


def load_research_observations(
    model_id: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load append-only observations for one frozen research model."""

    frame = pd.json_normalize(_load_jsonl_rows(RESEARCH_DIR / model_id))
    return _filter_observation_times(frame, start=start, end=end)


def available_instruments(dataset: str = "candles") -> list[str]:
    """List instruments present in the lake for a dataset: candles|funding|snapshots."""
    root = {"candles": CANDLE_DIR, "funding": FUNDING_DIR, "snapshots": SNAPSHOT_DIR}[dataset]
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def available_timeframes(inst_id: str) -> list[str]:
    inst_dir = CANDLE_DIR / safe_inst(inst_id)
    if not inst_dir.is_dir():
        return []
    return sorted(p.name for p in inst_dir.iterdir() if p.is_dir())


def locked_equity_refresh_targets(path: Path = LOCKED_QQQ_UNIVERSE_PATH) -> list[dict[str, Any]]:
    """QQQ plus the locked point-in-time universe. Does not invent new names."""

    targets = [{"symbol": "QQQ", "cik": None}]
    seen = {"QQQ"}
    if not path.exists():
        return targets
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            cik_raw = str(row.get("cik") or "").strip()
            cik = int(cik_raw) if cik_raw.isdigit() else None
            targets.append({"symbol": symbol, "cik": cik})
    return targets


def collect_equity_caches(
    *,
    data_root: Path = LOCKED_QQQ_INCREMENT_ROOT,
    universe_path: Path = LOCKED_QQQ_UNIVERSE_PATH,
    history_range: str = LOCKED_EQUITY_HISTORY_RANGE,
    price_loader: Callable[..., Any] | None = None,
    sec_loader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Refresh locked Yahoo daily prices and SEC company facts. Public HTTP only."""

    if price_loader is None or sec_loader is None:
        from qqq_active_enhancement_research import load_company_facts, load_yahoo_daily

        price_loader = price_loader or load_yahoo_daily
        sec_loader = sec_loader or load_company_facts
    counts = {"prices": 0, "sec": 0, "errors": []}
    for item in locked_equity_refresh_targets(universe_path):
        try:
            price_loader(item["symbol"], data_root, history_range=history_range, refresh=True)
            counts["prices"] += 1
        except Exception as exc:  # noqa: BLE001
            counts["errors"].append(f"{item['symbol']} price: {exc}")
        if item.get("cik"):
            try:
                sec_loader(int(item["cik"]), data_root, refresh=True)
                counts["sec"] += 1
            except Exception as exc:  # noqa: BLE001
                counts["errors"].append(f"{item['symbol']} sec: {exc}")
    return counts


def configured_collection_instruments(path: Path = TRADFI_TRACKING_PATH) -> list[str]:
    """Return base instruments plus the audited index-contract tracking set."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"tracking configuration is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"tracking configuration is invalid JSON: {path}") from exc
    if payload.get("schemaVersion") != 1:
        raise ValueError("tracking configuration schemaVersion must be 1")

    list_keys = (
        "indexProxyInstruments",
        "nasdaq100Instruments",
        "sp500Instruments",
        "trackedInstruments",
    )
    collections: dict[str, list[str]] = {}
    for key in list_keys:
        values = payload.get(key)
        if not isinstance(values, list) or not values:
            raise ValueError(f"tracking configuration {key} must be a non-empty list")
        if any(not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]+-USDT-SWAP", value) for value in values):
            raise ValueError(f"tracking configuration {key} contains an invalid instrument")
        if values != sorted(set(values)):
            raise ValueError(f"tracking configuration {key} must be sorted and unique")
        collections[key] = values

    expected = sorted(set(collections["indexProxyInstruments"])
                      | set(collections["nasdaq100Instruments"])
                      | set(collections["sp500Instruments"]))
    if collections["trackedInstruments"] != expected:
        raise ValueError("trackedInstruments must equal the union of proxies and index intersections")
    return sorted(set(BASE_COLLECTION_INSTRUMENTS) | set(expected))


# CLI ----------------------------------------------------------------------------------
def cmd_build(args: argparse.Namespace) -> int:
    print("Building data lake from existing data/ sources...")
    # candles: group by (inst, timeframe), merge all overlapping CSVs, dedupe
    candle_groups: dict[tuple[str, str], list[Path]] = {}
    for row in scan_candle_sources():
        if "error" in row:
            print(f"  [skip] {row['inst']} {row['tf']}: {row['error']}")
            continue
        candle_groups.setdefault((row["inst"], row["timeframe"]), []).append(Path(row["path"]))

    for (inst, tf), paths in sorted(candle_groups.items()):
        frames = []
        for p in paths:
            try:
                frames.append(read_candle_csv(p))
            except Exception as exc:  # noqa: BLE001
                print(f"  [skip] {inst} {tf} {p.name}: {exc}")
        if not frames:
            continue
        merged = pd.concat(frames, ignore_index=True)
        merged = merged.drop_duplicates(subset=["time"], keep="last").sort_values("time")
        written = write_candle_parquet(merged, inst, tf)
        print(f"  candles {inst} {tf}: {len(merged)} rows (merged {len(paths)} CSV) -> {len(written)} file(s)")
    # funding
    for row in scan_funding_sources():
        if "error" in row:
            print(f"  [skip] {row['inst']}: {row['error']}")
            continue
        df = read_funding_csv(Path(row["path"]))
        paths = write_funding_parquet(df, row["inst"])
        print(f"  funding {row['inst']}: {len(df)} rows -> {len(paths)} file(s)")
    # snapshots: copy JSONL into the lake only when it is a separate store
    if same_snapshot_store():
        print("  snapshots: source and lake resolve to the same directory; skip copy")
    else:
        for row in scan_snapshot_sources():
            inst = row["inst"]
            out_dir = SNAPSHOT_DIR / inst
            out_dir.mkdir(parents=True, exist_ok=True)
            copied = 0
            for fname in row["files"]:
                src = SNAPSHOT_SOURCE_DIR / inst / fname
                dst = out_dir / fname
                if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                    dst.write_bytes(src.read_bytes())
                    copied += 1
            print(f"  snapshots {inst}: {row['rows']} rows, {row['files'][0]}..{row['files'][-1]} ({copied} copied)")
    manifest = build_manifest()
    write_manifest(manifest)
    print(f"Manifest written: {MANIFEST_PATH}")
    print(f"Stats: {manifest['stats']}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from okx_client import OkxRestClient  # local import, no .env needed for public
    client = OkxRestClient(base_url=os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/"))
    insts = args.inst_ids or configured_collection_instruments()
    print(f"Tracking {len(insts)} instrument(s) from explicit args or the audited default universe.")
    print(f"Collecting candles ({args.timeframe}, lookback {args.lookback_days}d)...")
    collect_candles(
        client,
        insts,
        args.timeframe,
        lookback_days=args.lookback_days,
        backfill=bool(getattr(args, "backfill", False)),
    )
    print("Collecting funding...")
    collect_funding(client, insts)
    if not getattr(args, "skip_core_extra", False):
        print(
            f"Collecting extra {', '.join(CORE_DAILY_EXTRA_TIMEFRAMES)} candles for "
            f"{', '.join(CORE_DAILY_INSTRUMENTS)}..."
        )
        for inst in CORE_DAILY_INSTRUMENTS:
            for timeframe in CORE_DAILY_EXTRA_TIMEFRAMES:
                collect_candles(client, [inst], timeframe, lookback_days=args.lookback_days)
    if not getattr(args, "skip_equity", False):
        print("Refreshing locked QQQ Yahoo/SEC caches...")
        equity = collect_equity_caches()
        print(f"  equity prices={equity['prices']} sec={equity['sec']} errors={len(equity['errors'])}")
        for error in equity["errors"][:8]:
            print(f"  equity warning: {error}")
    if not getattr(args, "skip_deribit", False):
        from deribit_collect import collect_deribit

        print("Collecting Deribit public BTC/ETH perp, funding and DVOL...")
        deribit = collect_deribit()
        print(f"  deribit {deribit}")
    manifest = build_manifest()
    write_manifest(manifest)
    print(f"Manifest updated: {MANIFEST_PATH}")
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    manifest = build_manifest()
    write_manifest(manifest)
    print(json.dumps(manifest["stats"], indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified data lake pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build", help="scan data/ and build lake")
    p_build.set_defaults(func=cmd_build)
    p_collect = sub.add_parser("collect", help="incremental fetch from OKX public")
    p_collect.add_argument("--inst-id", dest="inst_ids", action="append", default=[])
    p_collect.add_argument("--timeframe", default="5m")
    p_collect.add_argument("--lookback-days", type=int, default=180)
    p_collect.add_argument("--skip-equity", action="store_true", help="do not refresh Yahoo/SEC caches")
    p_collect.add_argument("--skip-deribit", action="store_true", help="do not refresh Deribit public BTC/ETH series")
    p_collect.add_argument("--skip-core-extra", action="store_true", help="do not refresh BTC/ETH/XAU 15m/30m/1h extras")
    p_collect.add_argument("--backfill", action="store_true", help="also walk older than the earliest stored bar")
    p_collect.set_defaults(func=cmd_collect)
    p_manifest = sub.add_parser("manifest", help="rebuild manifest")
    p_manifest.set_defaults(func=cmd_manifest)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
