"""Forward-only passive fill research for OKX BTC/ETH linear options.

The script selects public `_UM` ATM straddles and light-OTM strangles, records
`bbo-tbt` and `trades` WebSocket events, and simulates rolling post-only buy
orders.  It has no account client and no order-placement path.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from microstructure_ws_collect import CollectorStats, collect
from option_spread_calibration import OKX_CURRENT_EXCHANGE, okx_public, optional_float


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "delta_neutral_options"
DEFAULT_EDGE_REPORT = PROJECT_ROOT / "reports" / "option_strangle_backtest" / "spread-calibrated-20260807" / "summary.json"
POLICIES = {"join_bid": 0.0, "improve25": 0.25, "midpoint": 0.5}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only OKX _UM passive option fill research")
    parser.add_argument("--bases", nargs="+", choices=("BTC", "ETH"), default=["BTC", "ETH"])
    parser.add_argument("--duration-seconds", type=float, default=180.0)
    parser.add_argument("--cohort-interval-seconds", type=float, default=10.0)
    parser.add_argument("--order-ttl-seconds", type=float, default=60.0)
    parser.add_argument("--min-hours-to-expiry", type=float, default=20.0)
    parser.add_argument("--max-hours-to-expiry", type=float, default=240.0)
    parser.add_argument("--otm-target-pct", type=float, default=1.5)
    parser.add_argument("--max-quote-age-seconds", type=float, default=10.0)
    parser.add_argument("--edge-report", default=str(DEFAULT_EDGE_REPORT))
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def valid_ticker(ticker: dict[str, Any]) -> bool:
    bid = optional_float(ticker.get("bidPx")) or 0.0
    ask = optional_float(ticker.get("askPx")) or 0.0
    bid_size = optional_float(ticker.get("bidSz")) or 0.0
    ask_size = optional_float(ticker.get("askSz")) or 0.0
    return bid > 0 and ask > bid and bid_size > 0 and ask_size > 0


def leg_from_rows(instrument: dict[str, Any], ticker: dict[str, Any]) -> dict[str, Any]:
    return {
        "instId": instrument["instId"],
        "optionType": instrument["optType"],
        "strike": float(instrument["stk"]),
        "expiryMs": int(instrument["expTime"]),
        "tickSize": float(instrument["tickSz"]),
        "ctVal": float(instrument.get("ctVal") or 1.0),
        "ctMult": float(instrument.get("ctMult") or 1.0),
        "ctValCcy": str(instrument.get("ctValCcy") or ""),
        "initialBid": float(ticker["bidPx"]),
        "initialAsk": float(ticker["askPx"]),
        "initialBidSize": float(ticker["bidSz"]),
        "initialAskSize": float(ticker["askSz"]),
    }


def select_structures(
    bases: list[str],
    *,
    now_ms: int,
    min_hours: float,
    max_hours: float,
    otm_target_pct: float,
) -> list[dict[str, Any]]:
    structures: list[dict[str, Any]] = []
    for base in bases:
        underlying_id = f"{base}-USD"
        family = f"{base}-USD_UM"
        instruments = okx_public("/api/v5/public/instruments", {"instType": "OPTION", "instFamily": family})
        tickers = okx_public("/api/v5/market/tickers", {"instType": "OPTION", "uly": underlying_id})
        index_rows = okx_public("/api/v5/market/index-tickers", {"instId": underlying_id})
        spot = optional_float(index_rows[0].get("idxPx")) if index_rows else None
        if spot is None or spot <= 0:
            raise ValueError(f"{base}: public index unavailable")
        ticker_by_id = {row.get("instId"): row for row in tickers if "_UM-" in row.get("instId", "") and valid_ticker(row)}
        by_expiry: dict[int, dict[str, list[dict[str, Any]]]] = {}
        for instrument in instruments:
            inst_id = instrument.get("instId")
            ticker = ticker_by_id.get(inst_id)
            if ticker is None or instrument.get("state") != "live":
                continue
            expiry = int(float(instrument.get("expTime") or 0))
            hours = (expiry - now_ms) / 3_600_000.0
            option_type = instrument.get("optType")
            if not min_hours <= hours <= max_hours or option_type not in {"C", "P"}:
                continue
            by_expiry.setdefault(expiry, {"C": [], "P": []})[option_type].append(leg_from_rows(instrument, ticker))

        chosen: tuple[int, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
        for expiry in sorted(by_expiry):
            calls = by_expiry[expiry]["C"]
            puts = by_expiry[expiry]["P"]
            call_by_strike = {leg["strike"]: leg for leg in calls}
            put_by_strike = {leg["strike"]: leg for leg in puts}
            common = sorted(set(call_by_strike) & set(put_by_strike))
            otm_calls = [leg for leg in calls if leg["strike"] >= spot]
            otm_puts = [leg for leg in puts if leg["strike"] <= spot]
            if not common or not otm_calls or not otm_puts:
                continue
            atm_strike = min(common, key=lambda strike: abs(strike / spot - 1.0))
            call_target = spot * (1.0 + otm_target_pct / 100.0)
            put_target = spot * (1.0 - otm_target_pct / 100.0)
            otm_call = min(otm_calls, key=lambda leg: abs(leg["strike"] - call_target))
            otm_put = min(otm_puts, key=lambda leg: abs(leg["strike"] - put_target))
            chosen = expiry, call_by_strike[atm_strike], put_by_strike[atm_strike], otm_call, otm_put
            break
        if chosen is None:
            raise ValueError(f"{base}: no executable _UM ATM/OTM pair in requested DTE range")
        expiry, atm_call, atm_put, otm_call, otm_put = chosen
        hours = (expiry - now_ms) / 3_600_000.0
        structures.extend(
            [
                {
                    "name": f"{base}_atm",
                    "base": base,
                    "kind": "atm",
                    "spot": spot,
                    "expiryMs": expiry,
                    "hoursToExpiry": hours,
                    "targetOtmPct": 0.0,
                    "actualCallOtmPct": (atm_call["strike"] / spot - 1.0) * 100.0,
                    "actualPutOtmPct": (1.0 - atm_put["strike"] / spot) * 100.0,
                    "call": atm_call,
                    "put": atm_put,
                },
                {
                    "name": f"{base}_otm",
                    "base": base,
                    "kind": "light_otm",
                    "spot": spot,
                    "expiryMs": expiry,
                    "hoursToExpiry": hours,
                    "targetOtmPct": otm_target_pct,
                    "actualCallOtmPct": (otm_call["strike"] / spot - 1.0) * 100.0,
                    "actualPutOtmPct": (1.0 - otm_put["strike"] / spot) * 100.0,
                    "call": otm_call,
                    "put": otm_put,
                },
            ]
        )
    return structures


def passive_limit(bid: float, ask: float, tick_size: float, policy: str) -> float:
    if policy not in POLICIES or bid <= 0 or ask <= bid or tick_size <= 0:
        raise ValueError("invalid quote, tick, or passive policy")
    raw = bid + POLICIES[policy] * (ask - bid)
    rounded = math.floor((raw + tick_size * 1e-9) / tick_size) * tick_size
    maximum_post_only = ask - tick_size
    return max(bid, min(rounded, maximum_post_only))


def load_events(raw_root: Path) -> list[dict[str, Any]]:
    events = []
    for path in sorted(raw_root.rglob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("channel") in {"bbo-tbt", "trades"}:
                    events.append(event)
    return sorted(events, key=lambda item: (int(item.get("capturedTs") or 0), item.get("instId", "")))


def quote_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("channel") != "bbo-tbt" or not isinstance(event.get("data"), dict):
        return None
    data = event["data"]
    bids = data.get("bids") if isinstance(data.get("bids"), list) else []
    asks = data.get("asks") if isinstance(data.get("asks"), list) else []
    if not bids or not asks:
        return None
    bid = optional_float(bids[0][0])
    ask = optional_float(asks[0][0])
    bid_size = optional_float(bids[0][1])
    ask_size = optional_float(asks[0][1])
    if bid is None or ask is None or bid_size is None or ask_size is None or bid <= 0 or ask <= bid:
        return None
    return {"bid": bid, "ask": ask, "bidSize": bid_size, "askSize": ask_size, "capturedTs": int(event["capturedTs"])}


def create_cohort(structure: dict[str, Any], quotes: dict[str, dict[str, Any]], policy: str, created_ts: int, ttl_ms: int) -> dict[str, Any]:
    legs = {}
    for label in ("call", "put"):
        spec = structure[label]
        quote = quotes[spec["instId"]]
        limit = passive_limit(quote["bid"], quote["ask"], spec["tickSize"], policy)
        legs[label] = {
            "instId": spec["instId"],
            "limitPx": limit,
            "initialBid": quote["bid"],
            "initialAsk": quote["ask"],
            "askTouchTs": None,
            "tradeTouchTs": None,
        }
    ask_sum = sum(leg["initialAsk"] for leg in legs.values())
    bid_sum = sum(leg["initialBid"] for leg in legs.values())
    limit_sum = sum(leg["limitPx"] for leg in legs.values())
    mid_sum = (ask_sum + bid_sum) / 2.0
    return {
        "structure": structure["name"],
        "base": structure["base"],
        "kind": structure["kind"],
        "hoursToExpiry": structure["hoursToExpiry"],
        "policy": policy,
        "createdTs": created_ts,
        "expiresTs": created_ts + ttl_ms,
        "legs": legs,
        "priceImprovementVsAskPct": (ask_sum - limit_sum) / ask_sum * 100.0,
        "executionCostVsMidPct": (limit_sum - mid_sum) / mid_sum * 100.0,
    }


def simulate_cohorts(
    events: list[dict[str, Any]],
    structures: list[dict[str, Any]],
    *,
    cohort_interval_seconds: float,
    ttl_seconds: float,
    max_quote_age_seconds: float,
) -> list[dict[str, Any]]:
    if not events or min(cohort_interval_seconds, ttl_seconds, max_quote_age_seconds) <= 0:
        return []
    latest_quotes: dict[str, dict[str, Any]] = {}
    cohorts: list[dict[str, Any]] = []
    next_cohort: dict[str, int] = {structure["name"]: 0 for structure in structures}
    ttl_ms = int(ttl_seconds * 1000)
    interval_ms = int(cohort_interval_seconds * 1000)
    max_age_ms = int(max_quote_age_seconds * 1000)
    last_ts = max(int(event.get("capturedTs") or 0) for event in events)
    structure_by_leg: dict[str, list[dict[str, Any]]] = {}
    for structure in structures:
        for label in ("call", "put"):
            structure_by_leg.setdefault(structure[label]["instId"], []).append(structure)

    for event in events:
        event_ts = int(event.get("capturedTs") or 0)
        inst_id = str(event.get("instId") or "")
        quote = quote_from_event(event)
        if quote is not None:
            latest_quotes[inst_id] = quote

        for structure in structure_by_leg.get(inst_id, []):
            if event_ts > last_ts - ttl_ms or event_ts < next_cohort[structure["name"]]:
                continue
            leg_ids = [structure["call"]["instId"], structure["put"]["instId"]]
            if not all(leg_id in latest_quotes and event_ts - latest_quotes[leg_id]["capturedTs"] <= max_age_ms for leg_id in leg_ids):
                continue
            for policy in POLICIES:
                cohorts.append(create_cohort(structure, latest_quotes, policy, event_ts, ttl_ms))
            next_cohort[structure["name"]] = event_ts + interval_ms

        if not inst_id:
            continue
        for cohort in cohorts:
            if not cohort["createdTs"] < event_ts <= cohort["expiresTs"]:
                continue
            for leg in cohort["legs"].values():
                if leg["instId"] != inst_id:
                    continue
                if quote is not None and quote["ask"] <= leg["limitPx"] and leg["askTouchTs"] is None:
                    leg["askTouchTs"] = event_ts
                if event.get("channel") == "trades" and isinstance(event.get("data"), dict):
                    data = event["data"]
                    trade_px = optional_float(data.get("px"))
                    if data.get("side") == "sell" and trade_px is not None and trade_px <= leg["limitPx"] and leg["tradeTouchTs"] is None:
                        leg["tradeTouchTs"] = event_ts
    return cohorts


def cohort_rows(cohorts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for cohort in cohorts:
        ask_times = [leg["askTouchTs"] for leg in cohort["legs"].values()]
        optimistic_times = [
            min(value for value in (leg["askTouchTs"], leg["tradeTouchTs"]) if value is not None)
            if leg["askTouchTs"] is not None or leg["tradeTouchTs"] is not None
            else None
            for leg in cohort["legs"].values()
        ]
        ask_filled = sum(value is not None for value in ask_times)
        optimistic_filled = sum(value is not None for value in optimistic_times)
        rows.append(
            {
                "structure": cohort["structure"],
                "base": cohort["base"],
                "kind": cohort["kind"],
                "hours_to_expiry": cohort["hoursToExpiry"],
                "policy": cohort["policy"],
                "created_ts": cohort["createdTs"],
                "expires_ts": cohort["expiresTs"],
                "price_improvement_vs_ask_pct": cohort["priceImprovementVsAskPct"],
                "execution_cost_vs_mid_pct": cohort["executionCostVsMidPct"],
                "ask_touch_legs": ask_filled,
                "ask_touch_both": ask_filled == 2,
                "optimistic_touch_legs": optimistic_filled,
                "optimistic_touch_both": optimistic_filled == 2,
                "optimistic_partial": optimistic_filled == 1,
                "ask_touch_wait_seconds": (max(ask_times) - cohort["createdTs"]) / 1000.0 if ask_filled == 2 else None,
                "optimistic_wait_seconds": (max(optimistic_times) - cohort["createdTs"]) / 1000.0 if optimistic_filled == 2 else None,
                "call_inst_id": cohort["legs"]["call"]["instId"],
                "put_inst_id": cohort["legs"]["put"]["instId"],
                "call_limit_px": cohort["legs"]["call"]["limitPx"],
                "put_limit_px": cohort["legs"]["put"]["limitPx"],
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    keys = sorted({(row["structure"], row["policy"]) for row in rows})
    for structure, policy in keys:
        items = [row for row in rows if row["structure"] == structure and row["policy"] == policy]
        ask_waits = [row["ask_touch_wait_seconds"] for row in items if row["ask_touch_wait_seconds"] is not None]
        optimistic_waits = [row["optimistic_wait_seconds"] for row in items if row["optimistic_wait_seconds"] is not None]
        result.append(
            {
                "structure": structure,
                "base": items[0]["base"],
                "kind": items[0]["kind"],
                "policy": policy,
                "cohorts": len(items),
                "askTouchBoth": sum(bool(row["ask_touch_both"]) for row in items),
                "askTouchBothPct": sum(bool(row["ask_touch_both"]) for row in items) / len(items) * 100.0,
                "optimisticTouchBoth": sum(bool(row["optimistic_touch_both"]) for row in items),
                "optimisticTouchBothPct": sum(bool(row["optimistic_touch_both"]) for row in items) / len(items) * 100.0,
                "optimisticPartial": sum(bool(row["optimistic_partial"]) for row in items),
                "optimisticPartialPct": sum(bool(row["optimistic_partial"]) for row in items) / len(items) * 100.0,
                "medianAskTouchWaitSeconds": statistics.median(ask_waits) if ask_waits else None,
                "medianOptimisticWaitSeconds": statistics.median(optimistic_waits) if optimistic_waits else None,
                "medianPriceImprovementVsAskPct": statistics.median(row["price_improvement_vs_ask_pct"] for row in items),
                "medianExecutionCostVsMidPct": statistics.median(row["execution_cost_vs_mid_pct"] for row in items),
            }
        )
    return result


def dte_label(hours: float) -> str:
    return "24h" if hours <= 48 else "72h" if hours <= 120 else "168h"


def break_even_lookup(path: Path, base: str, hours: float) -> float | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    target = int(dte_label(hours).removesuffix("h"))
    item = next((row for row in payload.get("executionEdgeSummary", []) if row.get("underlying") == base and row.get("entry_hours_before_expiry") == target), None)
    value = item.get("break_even_half_spread_bps") if item else None
    return optional_float(value)


def markdown_report(payload: dict[str, Any]) -> str:
    stats = payload["collectorStats"]
    lines = [
        "# OKX `_UM` 期权被动限价成交纸面研究",
        "",
        "> 仅使用 OKX 公共 REST/WebSocket；没有账户读取，没有委托或成交。",
        "",
        "## 采集规则",
        "",
        f"- 采集 {payload['config']['durationSeconds']:.0f} 秒；每 {payload['config']['cohortIntervalSeconds']:.0f} 秒生成一批纸面买单，TTL {payload['config']['orderTtlSeconds']:.0f} 秒。",
        "- join_bid 挂在最佳买价，improve25 从 bid 向 ask 改善 25%，midpoint 挂中间价；全部按 tick 向下取整并保持 post-only。",
        "- 保守成交要求后续 ask ≤ 限价；乐观上界还接受卖方公开成交价 ≤ 限价，但未扣除排队位置。",
        f"- WebSocket 事件：{stats['events_written']}；分频道 {stats['channel_events']}；重连 {stats['reconnects']}；错误 {len(stats['errors'])}。",
        "",
        "## 选定结构",
        "",
        "| 结构 | DTE | Call/Put 行权价 | 实际 OTM | 初始 Call/Put bid-ask | ATM Delta10 盈亏平衡半价差 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for structure in payload["structures"]:
        break_even = structure.get("breakEvenHalfSpreadBps")
        break_text = "n/a" if break_even is None else f"{break_even / 100:.2f}%"
        lines.append(
            f"| {structure['name']} | {structure['hoursToExpiry']:.1f}h | {structure['call']['strike']:g}/{structure['put']['strike']:g} | "
            f"{structure['actualCallOtmPct']:.2f}%/{structure['actualPutOtmPct']:.2f}% | "
            f"{structure['call']['initialBid']:g}-{structure['call']['initialAsk']:g} / {structure['put']['initialBid']:g}-{structure['put']['initialAsk']:g} | "
            f"{break_text if structure['kind'] == 'atm' else 'n/a'} |"
        )
    lines.extend([
        "",
        "## 纸面成交结果",
        "",
        "| 结构 | 策略 | 批次 | 保守双腿成交 | 乐观双腿上界 | 乐观单腿风险 | 中位等待 | 相对主动买入改善 | 成交价相对中间价 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for item in payload["summary"]:
        wait = item["medianOptimisticWaitSeconds"]
        wait_text = "n/a" if wait is None else f"{wait:.1f}s"
        lines.append(
            f"| {item['structure']} | {item['policy']} | {item['cohorts']} | {item['askTouchBothPct']:.1f}% ({item['askTouchBoth']}) | "
            f"{item['optimisticTouchBothPct']:.1f}% ({item['optimisticTouchBoth']}) | {item['optimisticPartialPct']:.1f}% ({item['optimisticPartial']}) | "
            f"{wait_text} | {item['medianPriceImprovementVsAskPct']:.1f}% | {item['medianExecutionCostVsMidPct']:.1f}% |"
        )
    lines.extend([
        "",
        "## 解释边界",
        "",
        "- 卖方成交触及限价只代表乐观上界；真实排队位置未知，实际成交率不会高于该值。",
        "- 本轮只研究双腿入场；退出也需要被动成交，会进一步降低完整往返的成功率。",
        "- 短时样本只能验证采集与微观结构，不能据此部署资金；需要跨不同时段持续采集。",
        "",
    ])
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("passive-fill-%Y%m%dT%H%M%SZ")


async def run(args: argparse.Namespace) -> tuple[dict[str, Any], CollectorStats]:
    if args.duration_seconds <= args.order_ttl_seconds or min(args.cohort_interval_seconds, args.order_ttl_seconds, args.max_quote_age_seconds) <= 0:
        raise ValueError("duration must exceed TTL and all timing values must be positive")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    structures = select_structures(
        args.bases,
        now_ms=now_ms,
        min_hours=args.min_hours_to_expiry,
        max_hours=args.max_hours_to_expiry,
        otm_target_pct=args.otm_target_pct,
    )
    edge_path = Path(args.edge_report)
    for structure in structures:
        structure["breakEvenHalfSpreadBps"] = break_even_lookup(edge_path, structure["base"], structure["hoursToExpiry"])
    output_dir = resolve_output_dir(args.output_dir)
    raw_root = output_dir / "raw"
    instruments = tuple(dict.fromkeys(structure[label]["instId"] for structure in structures for label in ("call", "put")))
    stats = await collect(
        instruments=instruments,
        channels=("bbo-tbt", "trades"),
        url="wss://ws.okx.com:8443/ws/v5/public",
        output_root=raw_root,
        duration_seconds=args.duration_seconds,
        heartbeat_seconds=15.0,
        min_free_gb=0.0,
    )
    events = load_events(raw_root)
    cohorts = simulate_cohorts(
        events,
        structures,
        cohort_interval_seconds=args.cohort_interval_seconds,
        ttl_seconds=args.order_ttl_seconds,
        max_quote_age_seconds=args.max_quote_age_seconds,
    )
    rows = cohort_rows(cohorts)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_okx_public_websocket_passive_fill_research",
        "execution": "no account reads and no orders",
        "config": {
            "durationSeconds": args.duration_seconds,
            "cohortIntervalSeconds": args.cohort_interval_seconds,
            "orderTtlSeconds": args.order_ttl_seconds,
            "minHoursToExpiry": args.min_hours_to_expiry,
            "maxHoursToExpiry": args.max_hours_to_expiry,
            "otmTargetPct": args.otm_target_pct,
            "maxQuoteAgeSeconds": args.max_quote_age_seconds,
        },
        "collectorStats": asdict(stats),
        "structures": structures,
        "eventCount": len(events),
        "cohortCount": len(rows),
        "summary": summarize(rows),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "paper_orders.csv", rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    return {"outputDir": str(output_dir), "events": len(events), "cohorts": len(rows)}, stats


def main() -> int:
    args = parse_args()
    result, stats = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["events"] > 0 and result["cohorts"] > 0 and not stats.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
