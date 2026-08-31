"""Persist public OKX WebSocket market events for forward-only research."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from websockets.asyncio.client import connect
except ImportError as exc:  # pragma: no cover - exercised by startup environments
    raise SystemExit(
        "Missing WebSocket dependency. Install with: .venv/bin/pip install 'websockets>=13,<16>'"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "data" / "microstructure_ws"
DEFAULT_URL = "wss://ws.okx.com:8443/ws/v5/public"
DEFAULT_INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
DEFAULT_CHANNELS = ("books5", "trades", "tickers")


@dataclass(slots=True)
class CollectorStats:
    connected_at: str = ""
    disconnected_at: str = ""
    events_written: int = 0
    reconnects: int = 0
    channel_events: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect public OKX order-book/trade/ticker WebSocket events. No account access or orders."
    )
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--channel", action="append", default=[])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--duration-seconds", type=float, default=0.0, help="0 runs until interrupted.")
    parser.add_argument("--heartbeat-seconds", type=float, default=20.0)
    parser.add_argument("--min-free-gb", type=float, default=10.0)
    return parser.parse_args()


def subscription_args(instruments: tuple[str, ...], channels: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {"channel": channel, "instId": inst_id}
        for inst_id in instruments
        for channel in channels
    ]


def event_rows(payload: dict[str, Any], *, captured_at: str, captured_ts: int) -> list[dict[str, Any]]:
    arg = payload.get("arg") if isinstance(payload.get("arg"), dict) else {}
    channel = str(arg.get("channel") or "")
    inst_id = str(arg.get("instId") or "")
    data = payload.get("data")
    if not channel or not inst_id or not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        event_inst_id = str(item.get("instId") or inst_id)
        rows.append(
            {
                "capturedAt": captured_at,
                "capturedTs": captured_ts,
                "source": "okx_public_websocket",
                "instId": event_inst_id,
                "channel": channel,
                "action": str(payload.get("action") or "snapshot"),
                "data": item,
            }
        )
    return rows


def append_event(output_root: Path, event: dict[str, Any]) -> Path:
    inst_id = safe_name(str(event.get("instId") or "unknown"))
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = output_root / inst_id / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n")
    return path


async def collect(
    *,
    instruments: tuple[str, ...],
    channels: tuple[str, ...],
    url: str,
    output_root: Path,
    duration_seconds: float,
    heartbeat_seconds: float,
    min_free_gb: float,
) -> CollectorStats:
    if not instruments:
        raise ValueError("at least one instrument is required")
    if not channels:
        raise ValueError("at least one channel is required")
    if duration_seconds < 0 or heartbeat_seconds <= 0 or min_free_gb < 0:
        raise ValueError("duration/min-free must be nonnegative and heartbeat must be positive")
    deadline = time.monotonic() + duration_seconds if duration_seconds > 0 else None
    stats = CollectorStats()
    delay = 1.0
    while deadline is None or time.monotonic() < deadline:
        if free_gb(output_root) < min_free_gb:
            stats.errors.append(f"disk free space below {min_free_gb:.1f} GB")
            break
        try:
            async with connect(url, ping_interval=None, max_size=8 * 1024 * 1024, open_timeout=20) as socket:
                stats.connected_at = stats.connected_at or now_iso()
                await socket.send(json.dumps({"op": "subscribe", "args": subscription_args(instruments, channels)}))
                delay = 1.0
                while deadline is None or time.monotonic() < deadline:
                    timeout = heartbeat_seconds
                    if deadline is not None:
                        timeout = min(timeout, max(0.01, deadline - time.monotonic()))
                    try:
                        raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        await socket.send("ping")
                        continue
                    if raw == "pong":
                        continue
                    try:
                        payload = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        stats.errors.append("received non-JSON WebSocket payload")
                        continue
                    captured_at = now_iso()
                    rows = event_rows(payload, captured_at=captured_at, captured_ts=now_ms())
                    for row in rows:
                        append_event(output_root, row)
                        stats.events_written += 1
                        channel = str(row["channel"])
                        stats.channel_events[channel] = stats.channel_events.get(channel, 0) + 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            stats.errors.append(str(exc))
            if deadline is not None and time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(delay, 30.0))
            delay = min(delay * 2.0, 30.0)
            stats.reconnects += 1
    stats.disconnected_at = now_iso()
    return stats


def free_gb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free / (1024**3)


def safe_name(value: str) -> str:
    return value.lower().replace("-", "_").replace("/", "_")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


async def run_from_args(args: argparse.Namespace) -> CollectorStats:
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    channels = tuple(dict.fromkeys(args.channel or DEFAULT_CHANNELS))
    return await collect(
        instruments=instruments,
        channels=channels,
        url=args.url,
        output_root=Path(args.output_root),
        duration_seconds=args.duration_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
        min_free_gb=args.min_free_gb,
    )


def main() -> int:
    args = parse_args()
    stats = asyncio.run(run_from_args(args))
    print(json.dumps({"microstructureWebSocketCollector": asdict(stats)}, ensure_ascii=False, indent=2))
    return 0 if not stats.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
