"""Audit fresh OKX WebSocket data before forward-only strategy research."""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from microstructure_ws_collect import DEFAULT_CHANNELS, DEFAULT_INSTRUMENTS, OUTPUT_ROOT, safe_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check WebSocket coverage and refuse an immature forward-test sample."
    )
    parser.add_argument("--input-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--channel", action="append", default=[])
    parser.add_argument("--min-duration-hours", type=float, default=72.0)
    parser.add_argument("--max-staleness-seconds", type=float, default=180.0)
    parser.add_argument("--max-gap-seconds", type=float, default=3600.0)
    parser.add_argument("--max-invalid-pct", type=float, default=0.1)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def audit_root(
    input_root: Path,
    instruments: tuple[str, ...],
    required_channels: tuple[str, ...],
    *,
    min_duration_hours: float = 72.0,
    max_staleness_seconds: float = 180.0,
    max_gap_seconds: float = 3600.0,
    max_invalid_pct: float = 0.1,
    now_ts: int | None = None,
) -> dict[str, Any]:
    if not instruments or not required_channels:
        raise ValueError("instruments and required channels cannot be empty")
    if (
        min_duration_hours < 0
        or max_staleness_seconds < 0
        or max_gap_seconds < 0
        or max_invalid_pct < 0
    ):
        raise ValueError("audit thresholds must be nonnegative")
    now_ts = int(now_ts if now_ts is not None else time.time() * 1000)
    instrument_rows = []
    overall_ready = True
    for inst_id in instruments:
        channel_stats: dict[str, dict[str, Any]] = {
            channel: _empty_channel_stats() for channel in required_channels
        }
        invalid_lines = 0
        trailing_partial_lines = 0
        unexpected_events = 0
        files = sorted((input_root / safe_name(inst_id)).glob("*.jsonl"))
        for path in files:
            with path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    if not raw.endswith("\n"):
                        trailing_partial_lines += 1
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        invalid_lines += 1
                        continue
                    if not isinstance(event, dict) or str(event.get("instId") or "") != inst_id:
                        unexpected_events += 1
                        continue
                    channel = str(event.get("channel") or "")
                    if channel not in channel_stats:
                        continue
                    captured_ts = _positive_int(event.get("capturedTs"))
                    if captured_ts <= 0:
                        channel_stats[channel]["invalidPayloads"] += 1
                        continue
                    stats = channel_stats[channel]
                    previous_ts = int(stats["lastCapturedTs"] or 0)
                    if previous_ts > 0:
                        if captured_ts < previous_ts:
                            stats["outOfOrderEvents"] += 1
                        else:
                            stats["maxCaptureGapMs"] = max(
                                int(stats["maxCaptureGapMs"]), captured_ts - previous_ts
                            )
                    stats["events"] += 1
                    stats["firstCapturedTs"] = int(stats["firstCapturedTs"] or captured_ts)
                    stats["lastCapturedTs"] = max(previous_ts, captured_ts)
                    data = event.get("data")
                    if not _valid_payload(channel, data):
                        stats["invalidPayloads"] += 1
                    source_ts = _positive_int(data.get("ts")) if isinstance(data, dict) else 0
                    if source_ts > 0 and captured_ts >= source_ts:
                        stats["maxSourceLagMs"] = max(
                            int(stats["maxSourceLagMs"]), captured_ts - source_ts
                        )

        reasons: list[str] = []
        total_events = sum(int(item["events"]) for item in channel_stats.values())
        total_invalid = invalid_lines + unexpected_events + sum(
            int(item["invalidPayloads"]) for item in channel_stats.values()
        )
        observed_rows = total_events + invalid_lines + unexpected_events
        invalid_pct = total_invalid / max(observed_rows, 1) * 100.0
        for channel, stats in channel_stats.items():
            first_ts = int(stats["firstCapturedTs"] or 0)
            last_ts = int(stats["lastCapturedTs"] or 0)
            duration_hours = max(0.0, (last_ts - first_ts) / 3_600_000.0) if first_ts else 0.0
            staleness_seconds = max(0.0, (now_ts - last_ts) / 1000.0) if last_ts else None
            stats["durationHours"] = duration_hours
            stats["stalenessSeconds"] = staleness_seconds
            stats["firstCapturedAt"] = _iso(first_ts)
            stats["lastCapturedAt"] = _iso(last_ts)
            if not stats["events"]:
                reasons.append(f"missing {channel} events")
            elif duration_hours < min_duration_hours:
                reasons.append(
                    f"{channel} duration {duration_hours:.2f}h is below {min_duration_hours:.2f}h"
                )
            if staleness_seconds is not None and staleness_seconds > max_staleness_seconds:
                reasons.append(f"{channel} is stale by {staleness_seconds:.1f}s")
            if int(stats["maxCaptureGapMs"]) > max_gap_seconds * 1000.0:
                reasons.append(
                    f"{channel} maximum gap {int(stats['maxCaptureGapMs']) / 1000.0:.1f}s "
                    f"exceeds {max_gap_seconds:.1f}s"
                )
        if invalid_pct > max_invalid_pct:
            reasons.append(
                f"invalid event rate {invalid_pct:.4f}% exceeds {max_invalid_pct:.4f}%"
            )
        ready = not reasons
        overall_ready = overall_ready and ready
        instrument_rows.append(
            {
                "instId": inst_id,
                "ready": ready,
                "files": len(files),
                "events": total_events,
                "invalidLines": invalid_lines,
                "unexpectedEvents": unexpected_events,
                "trailingPartialLines": trailing_partial_lines,
                "invalidPct": invalid_pct,
                "channels": channel_stats,
                "reasons": reasons,
            }
        )
    return {
        "generatedAt": _iso(now_ts),
        "inputRoot": str(input_root),
        "status": "ready_for_forward_backtest" if overall_ready else "collecting",
        "ready": overall_ready,
        "requirements": {
            "minDurationHours": min_duration_hours,
            "maxStalenessSeconds": max_staleness_seconds,
            "maxGapSeconds": max_gap_seconds,
            "maxInvalidPct": max_invalid_pct,
            "channels": list(required_channels),
        },
        "instruments": instrument_rows,
    }


def _empty_channel_stats() -> dict[str, Any]:
    return {
        "events": 0,
        "firstCapturedTs": 0,
        "lastCapturedTs": 0,
        "maxCaptureGapMs": 0,
        "maxSourceLagMs": 0,
        "invalidPayloads": 0,
        "outOfOrderEvents": 0,
    }


def _valid_payload(channel: str, data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if channel == "books5":
        bids = data.get("bids")
        asks = data.get("asks")
        if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
            return False
        bid = _positive_float(bids[0][0]) if isinstance(bids[0], list) and bids[0] else 0.0
        ask = _positive_float(asks[0][0]) if isinstance(asks[0], list) and asks[0] else 0.0
        return bid > 0 and ask > bid
    if channel == "trades":
        return (
            str(data.get("side") or "") in {"buy", "sell"}
            and _positive_float(data.get("px")) > 0
            and _positive_float(data.get("sz")) > 0
            and bool(str(data.get("tradeId") or ""))
        )
    if channel == "tickers":
        bid = _positive_float(data.get("bidPx"))
        ask = _positive_float(data.get("askPx"))
        return bid > 0 and ask >= bid
    return False


def _positive_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) and parsed > 0 else 0.0


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _iso(timestamp_ms: int) -> str:
    if timestamp_ms <= 0:
        return ""
    return datetime.fromtimestamp(timestamp_ms / 1000.0, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    channels = tuple(dict.fromkeys(args.channel or DEFAULT_CHANNELS))
    result = audit_root(
        Path(args.input_root),
        instruments,
        channels,
        min_duration_hours=args.min_duration_hours,
        max_staleness_seconds=args.max_staleness_seconds,
        max_gap_seconds=args.max_gap_seconds,
        max_invalid_pct=args.max_invalid_pct,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
