"""Feasibility of book-aware VWAP quotes on existing BTC/ETH snapshots.

Inherits the published VWAP market-maker parameters. Does not search a grid.
The inspected July-August snapshot window is diagnostic only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from data_pipeline import SNAPSHOT_SOURCE_DIR, load_candles, safe_inst
from vwap_market_maker_research import (
    MakerExecutionConfig,
    VwapMakerParams,
    desired_quotes,
    quote_levels,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = PROJECT_ROOT / "config" / "vwap_book_feasibility_preregistration.json"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "vwap_book_feasibility"
EPSILON = 1e-12


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("study", {}).get("paperOrLiveAuthorized") is not False:
        raise ValueError("feasibility registry must remain trading-disabled")
    return payload


def inherited_params(registry: dict[str, Any]) -> tuple[VwapMakerParams, MakerExecutionConfig]:
    raw = registry["study"]["inheritedParameters"]
    params = VwapMakerParams(
        vwap_window=int(raw["vwapWindow5m"]),
        anchor_weight=float(raw["anchorWeight"]),
        min_half_spread_bps=float(raw["minHalfSpreadBps"]),
        volatility_multiplier=float(raw["volatilityMultiplier"]),
        inventory_skew_bps=float(raw["inventorySkewBps"]),
        trend_lookback=int(raw["trendLookback"]),
        max_vwap_slope_bps=float(raw["maxVwapSlopeBps"]),
        volatility_window=int(raw["volatilityWindow"]),
        quote_notional_pct=float(raw["quoteNotionalPct"]),
        max_inventory_pct=float(raw["maxInventoryPct"]),
        max_inventory_bars=int(raw["maxInventoryBars"]),
        inventory_stop_bps=float(raw["inventoryStopBps"]),
        penetration_bps=float(raw["penetrationBps"]),
    )
    execution = MakerExecutionConfig(
        starting_equity=float(raw["startingEquity"]),
        maker_fee_bps=float(raw["makerFeeBps"]),
        taker_fee_bps=float(raw["takerFeeBps"]),
        taker_slippage_bps=float(raw["takerSlippageBps"]),
    )
    return params, execution


def iter_snapshots(inst_id: str) -> list[dict[str, Any]]:
    root = SNAPSHOT_SOURCE_DIR / safe_inst(inst_id)
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict) or not payload.get("ok"):
                    continue
                ticker = payload.get("ticker") if isinstance(payload.get("ticker"), dict) else {}
                book = payload.get("book") if isinstance(payload.get("book"), dict) else {}
                bids = book.get("bids") if isinstance(book.get("bids"), list) else []
                asks = book.get("asks") if isinstance(book.get("asks"), list) else []
                captured = payload.get("capturedAt")
                if not captured:
                    continue
                bid = float(ticker.get("bidPx") or (bids[0][0] if bids else 0) or 0)
                ask = float(ticker.get("askPx") or (asks[0][0] if asks else 0) or 0)
                last = float(ticker.get("last") or 0)
                if bid <= 0 or ask <= 0 or ask < bid:
                    continue
                rows.append(
                    {
                        "capturedAt": pd.Timestamp(captured, tz="UTC"),
                        "bid": bid,
                        "ask": ask,
                        "last": last if last > 0 else (bid + ask) / 2.0,
                        "mid": (bid + ask) / 2.0,
                        "spread_bps": (ask / bid - 1.0) * 10_000.0,
                        "dataComplete": bool(payload.get("dataComplete")),
                    }
                )
    rows.sort(key=lambda item: item["capturedAt"])
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = row["capturedAt"].isoformat()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def candle_features(inst_id: str, params: VwapMakerParams) -> pd.DataFrame:
    candles = load_candles(inst_id, "5m")
    if candles.empty:
        return candles
    frame = candles.copy()
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    frame["pv"] = typical * frame["volume"]
    window = int(params.vwap_window)
    vol_sum = frame["volume"].rolling(window, min_periods=window).sum()
    pv_sum = frame["pv"].rolling(window, min_periods=window).sum()
    frame["vwap"] = pv_sum / vol_sum
    prior = frame["vwap"].shift(int(params.trend_lookback))
    frame["vwap_slope_bps"] = (frame["vwap"] / prior - 1.0) * 10_000.0
    ret = frame["close"].pct_change()
    frame["volatility_bps"] = ret.rolling(int(params.volatility_window), min_periods=int(params.volatility_window)).std() * 10_000.0
    return frame.dropna(subset=["vwap", "vwap_slope_bps", "volatility_bps"]).reset_index(drop=True)


def attach_vwap(snapshots: list[dict[str, Any]], features: pd.DataFrame) -> list[dict[str, Any]]:
    if features.empty or not snapshots:
        return []
    times = pd.to_datetime(features["time"], utc=True)
    cursor = 0
    attached: list[dict[str, Any]] = []
    for snap in snapshots:
        while cursor + 1 < len(times) and times.iloc[cursor + 1] < snap["capturedAt"]:
            cursor += 1
        if times.iloc[cursor] >= snap["capturedAt"]:
            continue
        row = features.iloc[cursor]
        item = dict(snap)
        item["vwap"] = float(row["vwap"])
        item["close"] = float(row["close"])
        item["vwap_slope_bps"] = float(row["vwap_slope_bps"])
        item["volatility_bps"] = float(row["volatility_bps"])
        item["regime_active"] = (
            abs(item["vwap_slope_bps"]) <= 50.0 and item["volatility_bps"] <= 30.0
        )
        attached.append(item)
    return attached


def interval_trade_range(
    candles: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    fallback_last: float,
) -> tuple[float, float, int]:
    bar_open = candles["time"] - pd.Timedelta(minutes=5)
    mask = (candles["time"] > start) & (candles["time"] <= end) & (bar_open > start)
    window = candles.loc[mask]
    if window.empty:
        return fallback_last, fallback_last, 0
    return float(window["low"].min()), float(window["high"].max()), int(len(window))


def simulate(inst_id: str, snapshots: list[dict[str, Any]], candles: pd.DataFrame,
             params: VwapMakerParams, execution: MakerExecutionConfig) -> dict[str, Any]:
    cash = execution.starting_equity
    inventory = 0.0
    average = 0.0
    maker_fills = 0
    taker_exits = 0
    quotes = 0
    both_sides = 0
    joined = len(snapshots)
    inside_spread = 0
    wider_than_book = 0

    class Feature:
        def __init__(self, snap: dict[str, Any]) -> None:
            self.close = snap["close"]
            self.vwap = snap["vwap"]
            self.volatility_bps = snap["volatility_bps"]
            self.vwap_slope_bps = snap["vwap_slope_bps"]
            self.half_spread_bps = max(params.min_half_spread_bps, snap["volatility_bps"] * params.volatility_multiplier)
            self.regime_active = snap["regime_active"]

    def mark(price: float) -> float:
        return cash if abs(inventory) <= EPSILON else cash + (price - average) * inventory

    def fill(side: str, price: float, quantity: float, fee_bps: float) -> None:
        nonlocal cash, inventory, average, maker_fills
        if quantity <= EPSILON or price <= 0:
            return
        fee = price * quantity * fee_bps / 10_000.0
        if side == "buy":
            new_qty = inventory + quantity
            if new_qty > EPSILON:
                average = price if inventory <= EPSILON else (average * inventory + price * quantity) / new_qty
            inventory = new_qty
            cash -= price * quantity + fee
        else:
            cash += price * quantity - fee
            inventory -= quantity
            if abs(inventory) <= EPSILON:
                inventory = 0.0
                average = 0.0
        maker_fills += 1

    for index, snap in enumerate(snapshots[:-1]):
        nxt = snapshots[index + 1]
        feature = Feature(snap)
        live_quotes = desired_quotes(
            feature,  # type: ignore[arg-type]
            params,
            inventory=inventory,
            equity=max(mark(snap["mid"]), 1.0),
        )
        if not live_quotes:
            continue
        quotes += 1
        _, bid, ask = quote_levels(feature, params, inventory=inventory, max_inventory=execution.starting_equity * params.max_inventory_pct / 100.0 / snap["close"])
        if snap["bid"] <= bid <= snap["ask"] or snap["bid"] <= ask <= snap["ask"]:
            inside_spread += 1
        if (ask - bid) / snap["mid"] * 10_000.0 > snap["spread_bps"]:
            wider_than_book += 1
        low, high, bars = interval_trade_range(candles, snap["capturedAt"], nxt["capturedAt"], nxt["last"])
        pen = params.penetration_bps / 10_000.0
        hits = []
        for quote in live_quotes:
            if quote.side == "buy" and low <= quote.price * (1.0 - pen):
                hits.append(quote)
            elif quote.side == "sell" and high >= quote.price * (1.0 + pen):
                hits.append(quote)
        if len(hits) > 1:
            both_sides += 1
            marked = [(item, (nxt["mid"] - item.price) * (1 if item.side == "buy" else -1)) for item in hits]
            hits = [min(marked, key=lambda pair: pair[1])[0]]
        for quote in hits:
            fill(quote.side, quote.price, quote.quantity, execution.maker_fee_bps)
        if abs(inventory) > EPSILON:
            stop = average * (1.0 - params.inventory_stop_bps / 10_000.0) if inventory > 0 else average * (1.0 + params.inventory_stop_bps / 10_000.0)
            if (inventory > 0 and nxt["last"] <= stop) or (inventory < 0 and nxt["last"] >= stop):
                exit_px = nxt["last"] * (1.0 - execution.taker_slippage_bps / 10_000.0 if inventory > 0 else 1.0 + execution.taker_slippage_bps / 10_000.0)
                fill("sell" if inventory > 0 else "buy", exit_px, abs(inventory), execution.taker_fee_bps)
                taker_exits += 1
    if abs(inventory) > EPSILON:
        last = snapshots[-1]["last"]
        fill("sell" if inventory > 0 else "buy", last, abs(inventory), execution.taker_fee_bps)
        taker_exits += 1
    terminal = mark(snapshots[-1]["mid"] if snapshots else 0.0)
    return {
        "instId": inst_id,
        "snapshotsJoined": joined,
        "quoteIntervals": quotes,
        "makerFills": maker_fills,
        "takerExits": taker_exits,
        "bothSidesTouched": both_sides,
        "quotesInsideBookSpread": inside_spread,
        "quotesWiderThanBook": wider_than_book,
        "terminalEquity": terminal,
        "returnPct": (terminal / execution.starting_equity - 1.0) * 100.0 if execution.starting_equity else 0.0,
    }


def coverage_summary(inst_id: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if not snapshots:
        return {"instId": inst_id, "snapshots": 0}
    deltas = [
        (snapshots[index + 1]["capturedAt"] - snapshots[index]["capturedAt"]).total_seconds()
        for index in range(len(snapshots) - 1)
    ]
    return {
        "instId": inst_id,
        "snapshots": len(snapshots),
        "first": snapshots[0]["capturedAt"].isoformat(),
        "last": snapshots[-1]["capturedAt"].isoformat(),
        "medianGapSeconds": float(pd.Series(deltas).median()) if deltas else None,
        "completeBookRatio": sum(1 for row in snapshots if row["bid"] > 0 and row["ask"] > row["bid"]) / len(snapshots),
        "medianSpreadBps": float(pd.Series([row["spread_bps"] for row in snapshots]).median()),
    }


def method_viable(coverages: list[dict[str, Any]], results: list[dict[str, Any]]) -> bool:
    if len(coverages) < 2 or any(int(item.get("snapshots") or 0) < 500 for item in coverages):
        return False
    if any(float(item.get("completeBookRatio") or 0) < 0.95 for item in coverages):
        return False
    if any(int(item.get("snapshotsJoined") or 0) < 500 for item in results):
        return False
    return True


def run(registry_path: Path, output_dir: Path) -> dict[str, Any]:
    registry = load_registry(registry_path)
    params, execution = inherited_params(registry)
    coverages = []
    results = []
    for inst_id in registry["study"]["universe"]:
        snaps = iter_snapshots(inst_id)
        coverages.append(coverage_summary(inst_id, snaps))
        features = candle_features(inst_id, params)
        candles = load_candles(inst_id, "5m")
        joined = attach_vwap(snaps, features)
        results.append(simulate(inst_id, joined, candles, params, execution) if joined else {
            "instId": inst_id,
            "snapshotsJoined": 0,
            "quoteIntervals": 0,
            "makerFills": 0,
            "returnPct": 0.0,
        })
    viable = method_viable(coverages, results)
    payload = {
        "generatedAt": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "classification": "development_feasibility_inspected_window",
        "paperOrLiveAuthorized": False,
        "newValidation": False,
        "methodViableForForwardFreeze": viable,
        "registryPath": str(registry_path),
        "registrySha256": sha256_path(registry_path),
        "inheritedParameters": registry["study"]["inheritedParameters"],
        "coverage": coverages,
        "diagnosticResults": results,
        "note": "Diagnostic PnL cannot select parameters or authorize paper/live trading.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(payload), encoding="utf-8")
    return payload


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# BTC/ETH VWAP + 盘口快照可行性",
        "",
        "> 继承已发表的 VWAP 做市参数，不新搜网格。2026-07-02 至当前快照窗口只做方法诊断，不能选参或上实盘。",
        "",
        f"- 生成时间：`{payload['generatedAt']}`",
        f"- 方法可否冻结为前向：`{payload['methodViableForForwardFreeze']}`",
        "",
        "## 覆盖",
        "",
        "| 合约 | 快照 | 起 | 止 | 中位间隔秒 | 盘口完整率 | 中位价差bps |",
        "|---|---:|---|---|---:|---:|---:|",
    ]
    for row in payload["coverage"]:
        lines.append(
            f"| {row.get('instId')} | {row.get('snapshots')} | {row.get('first')} | {row.get('last')} | "
            f"{row.get('medianGapSeconds')} | {row.get('completeBookRatio')} | {row.get('medianSpreadBps')} |"
        )
    lines.extend(["", "## 诊断结果（不可选参）", "", "| 合约 | 接上VWAP | 报价区间 | maker成交 | 双边穿越 | 收益% |", "|---|---:|---:|---:|---:|---:|"])
    for row in payload["diagnosticResults"]:
        lines.append(
            f"| {row.get('instId')} | {row.get('snapshotsJoined')} | {row.get('quoteIntervals')} | "
            f"{row.get('makerFills')} | {row.get('bothSidesTouched')} | {row.get('returnPct'):.4f} |"
        )
    lines.extend(["", "## 决策", "", "- 状态：`research_only` / 可行性诊断。", "- 若方法成立，只能冻结一条只用边界之后快照的前向规则。", ""])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Book-aware VWAP feasibility on existing snapshots")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output_dir) if args.output_dir else OUTPUT_ROOT / utcnow().strftime("feasibility-%Y%m%dT%H%M%SZ")
    payload = run(Path(args.registry), output)
    print(json.dumps({
        "output": str(output),
        "viable": payload["methodViableForForwardFreeze"],
        "coverage": payload["coverage"],
        "diagnosticResults": payload["diagnosticResults"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
