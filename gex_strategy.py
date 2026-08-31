"""Paper-only 30m-6h GEX wall strategy research.

This is intentionally separate from ``strategy_signal_bot.py``.  It creates
signals and backtest reports, but it has no order, account, leverage, or
systemd-start functionality.

The rule set is adapted from the public GEX workflow used by
Kza56/OFK_Atas_GEX and the common regime interpretation in crypto GEX
dashboards:

* positive net GEX: look for rejection near the nearest Put/Call wall and
  mean-revert toward the middle;
* negative net GEX: look for volume-confirmed breakouts through a wall and
  follow the move;
* use lagged EMA/volume confirmation and a 6-72 bar holding window on 5m
  candles (30 minutes to 6 hours).

Historical validation is only allowed when point-in-time GEX snapshots exist.
The module refuses to treat today's GEX as historical data.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, parse_okx_candles, read_candles_csv
from gex_estimator import build_gex_snapshot
from okx_client import OkxRestClient, load_env


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "okx" / "gex_snapshots.jsonl"
DEFAULT_PAPER_LOG = PROJECT_ROOT / "data" / "okx" / "gex_paper_signals.jsonl"
REPORT_ROOT = PROJECT_ROOT / "reports" / "gex_strategy"


@dataclass(slots=True)
class StrategyConfig:
    entry_band_bps: float = 35.0
    breakout_buffer_bps: float = 8.0
    min_volume_ratio: float = 1.10
    fast_ema: int = 12
    slow_ema: int = 36
    atr_window: int = 14
    stop_atr_mult: float = 1.5
    take_profit_r: float = 1.5
    min_hold_bars: int = 6
    max_hold_bars: int = 72
    fee_bps_per_side: float = 5.0
    slippage_bps_per_side: float = 2.0
    max_gex_age_hours: float = 6.0


def number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def iso_ms(value: Any) -> str:
    timestamp = number(value)
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(timespec="seconds")


def ema(values: list[float], window: int) -> float:
    if not values:
        return math.nan
    alpha = 2.0 / (max(1, window) + 1.0)
    current = values[0]
    for value in values[1:]:
        current = alpha * value + (1.0 - alpha) * current
    return current


def atr(candles: list[Candle], window: int) -> float:
    if len(candles) < 2:
        return math.nan
    true_ranges: list[float] = []
    for index, candle in enumerate(candles):
        high = number(candle.high)
        low = number(candle.low)
        if index == 0:
            true_ranges.append(max(0.0, high - low))
        else:
            previous = number(candles[index - 1].close)
            true_ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    sample = true_ranges[-max(2, window) :]
    return statistics.fmean(sample) if sample else math.nan


def volume_ratio(candles: list[Candle], window: int = 24) -> float:
    if len(candles) < 3:
        return 1.0
    current = number(candles[-1].volume)
    sample = [number(candle.volume) for candle in candles[-1 - max(2, window) : -1]]
    sample = [value for value in sample if value > 0]
    baseline = statistics.median(sample) if sample else 0.0
    return current / baseline if baseline > 0 else 1.0


def _wall(row: dict[str, Any], name: str) -> float:
    wall = row.get(name) or {}
    return number(wall.get("strike")) if isinstance(wall, dict) else 0.0


def generate_signal(candles: list[Candle], gex_row: dict[str, Any], config: StrategyConfig | None = None) -> dict[str, Any]:
    """Generate a signal using only candles through the last completed bar."""

    config = config or StrategyConfig()
    if len(candles) < max(config.slow_ema + 2, config.atr_window + 2):
        return {"direction": 0, "status": "wait", "reason": "warmup"}
    price = number(candles[-1].close)
    if price <= 0:
        return {"direction": 0, "status": "wait", "reason": "invalid_price"}
    fast = ema([number(candle.close) for candle in candles], config.fast_ema)
    slow = ema([number(candle.close) for candle in candles], config.slow_ema)
    trend = 1 if fast > slow else -1 if fast < slow else 0
    vol_ratio = volume_ratio(candles)
    net_gex = number(gex_row.get("netGex"))
    call_wall = _wall(gex_row, "callWall")
    put_wall = _wall(gex_row, "putWall")
    band = config.entry_band_bps / 10000.0
    breakout = config.breakout_buffer_bps / 10000.0
    previous = candles[-1]
    bullish_bar = number(previous.close) >= number(previous.open) or number(previous.close) > number(candles[-2].close)
    bearish_bar = number(previous.close) <= number(previous.open) or number(previous.close) < number(candles[-2].close)
    direction = 0
    reason = "inside_walls"
    regime = "positive_gamma" if net_gex >= 0 else "negative_gamma"

    if call_wall > 0 and put_wall > 0:
        if net_gex >= 0:
            near_put = abs(price / put_wall - 1.0) <= band
            near_call = abs(price / call_wall - 1.0) <= band
            if near_put and bullish_bar and trend >= 0:
                direction, reason = 1, "positive_gamma_put_wall_rejection"
            elif near_call and bearish_bar and trend <= 0:
                direction, reason = -1, "positive_gamma_call_wall_rejection"
        else:
            if price > call_wall * (1.0 + breakout) and trend >= 0 and vol_ratio >= config.min_volume_ratio:
                direction, reason = 1, "negative_gamma_call_wall_breakout"
            elif price < put_wall * (1.0 - breakout) and trend <= 0 and vol_ratio >= config.min_volume_ratio:
                direction, reason = -1, "negative_gamma_put_wall_breakdown"

    stop_distance = max(number(atr(candles, config.atr_window)) * config.stop_atr_mult, price * 0.0015)
    stop = price - stop_distance if direction > 0 else price + stop_distance if direction < 0 else None
    target_distance = stop_distance * config.take_profit_r
    target = price + target_distance if direction > 0 else price - target_distance if direction < 0 else None
    return {
        "direction": direction,
        "status": "long" if direction > 0 else "short" if direction < 0 else "wait",
        "reason": reason,
        "regime": regime,
        "price": round(price, 12),
        "emaFast": round(fast, 12) if math.isfinite(fast) else None,
        "emaSlow": round(slow, 12) if math.isfinite(slow) else None,
        "trend": trend,
        "volumeRatio": round(vol_ratio, 4),
        "callWall": call_wall or None,
        "putWall": put_wall or None,
        "netGex": net_gex,
        "stop": round(stop, 12) if stop is not None else None,
        "takeProfit": round(target, 12) if target is not None else None,
        "minHoldBars": config.min_hold_bars,
        "maxHoldBars": config.max_hold_bars,
        "holdingWindow": "30m-6h on 5m bars",
    }


def load_snapshot_series(path: Path) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    # A dashboard restart can see the same five-minute snapshot again.  Keep
    # one point-in-time row per underlying/timestamp so the history count is
    # not inflated by harmless duplicate persistence.
    by_underlying: dict[str, dict[int, dict[str, Any]]] = {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
                payload = record.get("data", record)
                captured_at = record.get("capturedAt") or payload.get("updatedAt")
                if not captured_at:
                    continue
                timestamp = int(datetime.fromisoformat(str(captured_at).replace("Z", "+00:00")).timestamp() * 1000)
                for row in payload.get("underlyings", []):
                    base = str(row.get("underlying") or "")
                    if base:
                        by_underlying.setdefault(base, {})[timestamp] = row
            except (TypeError, ValueError, OverflowError, json.JSONDecodeError, OSError):
                continue
    series = {
        base: sorted(rows.items(), key=lambda item: item[0])
        for base, rows in by_underlying.items()
    }
    return series


def snapshot_item_before(
    series: list[tuple[int, dict[str, Any]]], timestamp: int
) -> tuple[int, dict[str, Any]] | None:
    if not series:
        return None
    timestamps = [item[0] for item in series]
    index = bisect.bisect_right(timestamps, timestamp) - 1
    return series[index] if index >= 0 else None


def snapshot_before(series: list[tuple[int, dict[str, Any]]], timestamp: int) -> dict[str, Any] | None:
    item = snapshot_item_before(series, timestamp)
    return item[1] if item is not None else None


def backtest(candles: list[Candle], series: list[tuple[int, dict[str, Any]]], config: StrategyConfig) -> dict[str, Any]:
    """Point-in-time backtest. GEX snapshot is always from before the entry bar."""

    if not series:
        return {"status": "insufficient_history", "reason": "no_point_in_time_gex_snapshots", "trades": []}
    if len(series) < 12:
        return {"status": "insufficient_history", "reason": f"only_{len(series)}_gex_snapshots_need_12", "trades": []}
    if not candles:
        return {"status": "insufficient_history", "reason": "no_candles", "trades": []}
    if series[0][0] > candles[-1].ts:
        return {
            "status": "insufficient_history",
            "reason": "point_in_time_gex_snapshots_do_not_overlap_candles",
            "trades": [],
            "firstSnapshot": iso_ms(series[0][0]),
            "lastCandle": iso_ms(candles[-1].ts),
        }
    position: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    equity = 100.0
    curve = [equity]
    warmup = max(config.slow_ema + 3, config.atr_window + 3)
    round_trip_cost_pct = 2.0 * (config.fee_bps_per_side + config.slippage_bps_per_side) / 100.0
    max_gex_age_ms = max(0, int(config.max_gex_age_hours * 60 * 60 * 1000))
    stale_snapshot_bars = 0
    for index in range(warmup, len(candles)):
        previous = candles[index - 1]
        snapshot_item = snapshot_item_before(series, previous.ts)
        row = snapshot_item[1] if snapshot_item is not None else None
        snapshot_fresh = (
            snapshot_item is not None
            and 0 <= previous.ts - snapshot_item[0] <= max_gex_age_ms
        )
        if snapshot_item is not None and not snapshot_fresh:
            stale_snapshot_bars += 1
        current = candles[index]
        if position:
            position["barsHeld"] += 1
            side = position["side"]
            exit_price = None
            exit_reason = ""
            if side > 0:
                if number(current.low) <= position["stop"]:
                    exit_price, exit_reason = position["stop"], "stop"
                elif number(current.high) >= position["target"]:
                    exit_price, exit_reason = position["target"], "take_profit"
            else:
                if number(current.high) >= position["stop"]:
                    exit_price, exit_reason = position["stop"], "stop"
                elif number(current.low) <= position["target"]:
                    exit_price, exit_reason = position["target"], "take_profit"
            if exit_price is None and position["barsHeld"] >= config.max_hold_bars:
                exit_price, exit_reason = number(current.open), "time_stop"
            # A hard stop is allowed to protect the paper position during the
            # minimum holding window.  Profit-taking remains gated by the
            # 30-minute minimum unless the six-hour time stop is reached.
            can_exit = exit_price is not None and (
                exit_reason == "stop" or position["barsHeld"] >= config.min_hold_bars
            )
            if can_exit:
                move_pct = side * (exit_price / position["entry"] - 1.0) * 100.0
                net_pct = move_pct - round_trip_cost_pct
                equity *= 1.0 + net_pct / 100.0
                trades.append(
                    {
                        "entryTs": iso_ms(position["entryTs"]),
                        "exitTs": iso_ms(current.ts),
                        "side": "long" if side > 0 else "short",
                        "entry": position["entry"],
                        "exit": round(exit_price, 12),
                        "barsHeld": position["barsHeld"],
                        "reason": exit_reason,
                        "returnPct": round(net_pct, 6),
                        "equity": round(equity, 8),
                    }
                )
                position = None
        if position is None and row is not None and snapshot_fresh:
            signal = generate_signal(candles[:index], row, config)
            if signal["direction"]:
                entry = number(current.open)
                distance = max(number(atr(candles[:index], config.atr_window)) * config.stop_atr_mult, entry * 0.0015)
                position = {
                    "side": signal["direction"],
                    "entry": entry,
                    "entryTs": current.ts,
                    "stop": entry - distance if signal["direction"] > 0 else entry + distance,
                    "target": entry + distance * config.take_profit_r if signal["direction"] > 0 else entry - distance * config.take_profit_r,
                    "barsHeld": 0,
                    "entryReason": signal["reason"],
                }
        curve.append(equity)
    if position and candles:
        # Do not silently drop an open trade when the data window ends.  Mark
        # it to the final close and charge the same exit-side cost.
        exit_price = number(candles[-1].close)
        side = position["side"]
        move_pct = side * (exit_price / position["entry"] - 1.0) * 100.0
        net_pct = move_pct - round_trip_cost_pct
        equity *= 1.0 + net_pct / 100.0
        trades.append(
            {
                "entryTs": iso_ms(position["entryTs"]),
                "exitTs": iso_ms(candles[-1].ts),
                "side": "long" if side > 0 else "short",
                "entry": position["entry"],
                "exit": round(exit_price, 12),
                "barsHeld": position["barsHeld"],
                "reason": "end_of_data",
                "returnPct": round(net_pct, 6),
                "equity": round(equity, 8),
            }
        )
    returns = [trade["returnPct"] for trade in trades]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    peak = 100.0
    max_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak * 100.0 if peak else 0.0)
    return {
        "status": "ok",
        "snapshotCount": len(series),
        "maxGexAgeHours": config.max_gex_age_hours,
        "staleSnapshotBars": stale_snapshot_bars,
        "candleCount": len(candles),
        "trades": trades,
        "tradeCount": len(trades),
        "returnPct": round((equity / 100.0 - 1.0) * 100.0, 6),
        "profitFactor": round(sum(wins) / abs(sum(losses)), 6) if losses and sum(losses) != 0 else 999.0 if wins else 0.0,
        "winRatePct": round(len(wins) / len(returns) * 100.0, 4) if returns else 0.0,
        "maxDrawdownPct": round(max_drawdown, 6),
        "firstCandle": iso_ms(candles[0].ts) if candles else "",
        "lastCandle": iso_ms(candles[-1].ts) if candles else "",
        "firstSnapshot": iso_ms(series[0][0]),
        "lastSnapshot": iso_ms(series[-1][0]),
    }


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def live_once(client: OkxRestClient, config: StrategyConfig, paper_log: Path) -> dict[str, Any]:
    payload = build_gex_snapshot(client)
    result: dict[str, Any] = {"capturedAt": payload.get("updatedAt"), "mode": "paper_only", "signals": []}
    for row in payload.get("underlyings", []):
        base = str(row.get("underlying") or "")
        if not base:
            continue
        inst_id = f"{base}-USDT-SWAP"
        candles = parse_okx_candles(
            client.request("GET", "/api/v5/market/candles", params={"instId": inst_id, "bar": "5m", "limit": "120"}).get("data", [])
        )
        signal = generate_signal(candles, row, config)
        signal.update({"underlying": base, "instId": inst_id, "asOf": iso_ms(candles[-1].ts) if candles else ""})
        result["signals"].append(signal)
    append_jsonl(paper_log, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only/paper GEX wall strategy for 30m-6h holding windows.")
    parser.add_argument("--once", action="store_true", help="Fetch current GEX and emit paper-only signals once.")
    parser.add_argument("--loop", action="store_true", help="Repeat paper-only signal generation; never places orders.")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--backtest", action="store_true", help="Backtest only when point-in-time GEX snapshots exist.")
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--candle-file", action="append", default=[], help="Optional inst_id=path pairs for backtest.")
    parser.add_argument("--snapshot-file", default=str(DEFAULT_SNAPSHOT_PATH))
    parser.add_argument("--paper-log", default=str(DEFAULT_PAPER_LOG))
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = StrategyConfig()
    if args.backtest:
        series = load_snapshot_series(Path(args.snapshot_file))
        file_map = {}
        for item in args.candle_file:
            if "=" not in item:
                continue
            inst_id, path = item.split("=", 1)
            file_map[inst_id] = Path(path)
        inst_ids = args.inst_id or list(file_map)
        results = []
        for inst_id in inst_ids:
            base = inst_id.split("-", 1)[0]
            candle_path = file_map.get(inst_id) or (PROJECT_ROOT / "data" / "backtest" / f"{inst_id}_5m_300x48.csv")
            if not candle_path.exists():
                results.append({"instId": inst_id, "status": "insufficient_history", "reason": f"missing_candle_file:{candle_path}"})
                continue
            result = backtest(read_candles_csv(candle_path), series.get(base, []), config)
            result["instId"] = inst_id
            results.append(result)
        payload = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": "read_only_gex_wall_backtest", "config": asdict(config), "snapshotFile": args.snapshot_file, "results": results}
        output_dir = Path(args.output_dir) if args.output_dir else REPORT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    load_env()
    client = OkxRestClient.from_env()
    while True:
        result = live_once(client, config, Path(args.paper_log))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.loop:
            return 0
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
