"""Read-only staged-fill and perpetual-hedge replay for OKX linear options.

The experiment models a realistic fallback for a two-leg passive entry: if one
option leg crosses its post-only limit first, buy that leg, hedge its public
Delta with the matching USDT perpetual, and keep the second option order alive
until the TTL. No account client and no order-placement path are present.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from microstructure_ws_collect import CollectorStats, collect
from option_passive_fill_research import (
    OUTPUT_ROOT,
    load_events,
    quote_from_event,
    select_structures,
    simulate_cohorts,
)
from option_spread_calibration import okx_public, optional_float
from option_strangle_backtest import greeks_from_price


YEAR_MS = 365.25 * 86_400_000
DEFAULT_OUTPUT = OUTPUT_ROOT / "staged-hedge-20260807"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only staged passive option fill and perp hedge research")
    parser.add_argument("--bases", nargs="+", choices=("BTC", "ETH"), default=["BTC", "ETH"])
    parser.add_argument("--duration-seconds", type=float, default=300.0)
    parser.add_argument("--cohort-interval-seconds", type=float, default=10.0)
    parser.add_argument("--order-ttl-seconds", type=float, default=60.0)
    parser.add_argument("--min-hours-to-expiry", type=float, default=20.0)
    parser.add_argument("--max-hours-to-expiry", type=float, default=240.0)
    parser.add_argument("--otm-target-pct", type=float, default=1.5)
    parser.add_argument("--max-quote-age-seconds", type=float, default=10.0)
    parser.add_argument("--hedge-quote-age-seconds", type=float, default=3.0)
    parser.add_argument("--option-fee-bps", type=float, default=3.0)
    parser.add_argument("--hedge-fee-bps", type=float, default=5.0)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--replay-dir", default="", help="Rebuild a completed run from its saved public raw events.")
    return parser.parse_args()


def resolve_output_dir(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else OUTPUT_ROOT / path


def option_deltas(structures: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Read public OKX Greeks and contract multipliers for selected legs."""
    result: dict[str, dict[str, float]] = {}
    by_base: dict[str, set[str]] = {}
    for structure in structures:
        for label in ("call", "put"):
            leg = structure[label]
            by_base.setdefault(structure["base"], set()).add(leg["instId"])
    for base, ids in by_base.items():
        rows = okx_public("/api/v5/public/opt-summary", {"uly": f"{base}-USD"})
        for row in rows:
            inst_id = row.get("instId")
            if inst_id not in ids:
                continue
            delta = optional_float(row.get("deltaBS"))
            if delta is None:
                delta = optional_float(row.get("delta"))
            if delta is not None:
                result[inst_id] = {"delta": delta}
    return result


def fallback_delta(spec: dict[str, Any], structure: dict[str, Any]) -> float:
    """Use a quote-implied Black-Scholes delta only if the public Greek is absent."""
    years = max((structure["expiryMs"] - int(datetime.now(timezone.utc).timestamp() * 1000)) / YEAR_MS, 1e-9)
    price_usd = float(spec["initialBid"] + spec["initialAsk"]) / 2.0
    return greeks_from_price(price_usd, structure["spot"], spec["strike"], years, spec["optionType"])[0]


def event_history(events: list[dict[str, Any]], inst_ids: set[str]) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    histories: dict[str, list[tuple[int, dict[str, Any]]]] = {inst_id: [] for inst_id in inst_ids}
    for event in events:
        inst_id = str(event.get("instId") or "")
        if inst_id not in histories:
            continue
        quote = quote_from_event(event)
        if quote is not None:
            histories[inst_id].append((quote["capturedTs"], quote))
    for values in histories.values():
        values.sort(key=lambda item: item[0])
    return histories


def quote_at(history: list[tuple[int, dict[str, Any]]], ts: int, max_age_ms: int) -> dict[str, Any] | None:
    if not history:
        return None
    index = bisect.bisect_right([item[0] for item in history], ts) - 1
    if index < 0 or ts - history[index][0] > max_age_ms:
        return None
    return history[index][1]


def execute_hedge_change(
    change_base: float,
    quote: dict[str, Any],
    *,
    fee_bps: float,
) -> tuple[float, float]:
    """Return hedge cash flow and execution costs for a base-unit position change."""
    if change_base == 0:
        return 0.0, 0.0
    price = float(quote["ask"] if change_base > 0 else quote["bid"])
    mid = (float(quote["bid"]) + float(quote["ask"])) / 2.0
    cash_flow = -change_base * price
    fee = abs(change_base) * mid * fee_bps / 10_000.0
    return cash_flow, fee


def contract_multiplier(spec: dict[str, Any]) -> float:
    value = float(spec.get("ctVal", 1.0)) * float(spec.get("ctMult", 0.01))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("option contract multiplier must be positive")
    return value


def staged_rows(
    cohorts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    structures: list[dict[str, Any]],
    deltas: dict[str, dict[str, float]],
    *,
    option_fee_bps: float,
    hedge_fee_bps: float,
    hedge_quote_age_seconds: float,
) -> list[dict[str, Any]]:
    structure_by_name = {structure["name"]: structure for structure in structures}
    specs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for structure in structures:
        for label in ("call", "put"):
            spec = structure[label]
            specs[spec["instId"]] = (structure, spec)
    hedge_ids = {f"{structure['base']}-USDT-SWAP" for structure in structures}
    option_ids = set(specs)
    histories = event_history(events, option_ids | hedge_ids)
    rows: list[dict[str, Any]] = []
    max_age_ms = int(hedge_quote_age_seconds * 1000)
    for cohort in cohorts:
        structure = structure_by_name[cohort["structure"]]
        fills = [(label, leg["askTouchTs"]) for label, leg in cohort["legs"].items() if leg["askTouchTs"] is not None]
        fills.sort(key=lambda item: int(item[1]))
        hedge_id = f"{structure['base']}-USDT-SWAP"
        hedge_history = histories.get(hedge_id, [])
        current_hedge = 0.0
        hedge_cash = 0.0
        hedge_fees = 0.0
        hedge_missing = False
        option_cash = 0.0
        entry_option_premium = 0.0
        option_fees = 0.0
        filled_labels: list[str] = []
        first_fill_ts = int(fills[0][1]) if fills else None
        for label, fill_ts_value in fills:
            fill_ts = int(fill_ts_value)
            leg = cohort["legs"][label]
            spec = structure[label]
            multiplier = contract_multiplier(spec)
            option_cash -= float(leg["limitPx"]) * multiplier
            entry_option_premium += float(leg["limitPx"]) * multiplier
            option_fees += float(leg["limitPx"]) * multiplier * option_fee_bps / 10_000.0
            filled_labels.append(label)
            delta = deltas.get(spec["instId"], {}).get("delta")
            if delta is None:
                delta = fallback_delta(spec, structure)
            target_hedge = -sum(
                (deltas.get(structure[other]["instId"], {}).get("delta") if deltas.get(structure[other]["instId"], {}).get("delta") is not None else fallback_delta(structure[other], structure))
                * contract_multiplier(structure[other])
                for other in filled_labels
            )
            hedge_quote = quote_at(hedge_history, fill_ts, max_age_ms)
            if hedge_quote is None:
                hedge_missing = True
                continue
            cash, fee = execute_hedge_change(target_hedge - current_hedge, hedge_quote, fee_bps=hedge_fee_bps)
            hedge_cash += cash
            hedge_fees += fee
            current_hedge = target_hedge

        exit_ts = int(cohort["expiresTs"])
        for label in filled_labels:
            spec = structure[label]
            multiplier = contract_multiplier(spec)
            history = histories.get(spec["instId"], [])
            quote = quote_at(history, exit_ts, int(max(hedge_quote_age_seconds, 10.0) * 1000))
            if quote is None:
                hedge_missing = True
                continue
            exit_price = float(quote["bid"])
            option_cash += exit_price * multiplier
            option_fees += exit_price * multiplier * option_fee_bps / 10_000.0

        exit_hedge_quote = quote_at(hedge_history, exit_ts, int(max(hedge_quote_age_seconds, 10.0) * 1000))
        if current_hedge and exit_hedge_quote is not None:
            cash, fee = execute_hedge_change(-current_hedge, exit_hedge_quote, fee_bps=hedge_fee_bps)
            hedge_cash += cash
            hedge_fees += fee
            current_hedge = 0.0
        elif current_hedge:
            hedge_missing = True

        total_pnl = option_cash + hedge_cash - option_fees - hedge_fees if not hedge_missing else None
        rows.append(
            {
                "structure": cohort["structure"],
                "base": cohort["base"],
                "kind": cohort["kind"],
                "policy": cohort["policy"],
                "created_ts": cohort["createdTs"],
                "expires_ts": cohort["expiresTs"],
                "first_leg": fills[0][0] if fills else "",
                "filled_legs": len(filled_labels),
                "first_fill_wait_seconds": (first_fill_ts - cohort["createdTs"]) / 1000.0 if first_fill_ts is not None else None,
                "both_filled": len(filled_labels) == 2,
                "hedge_missing": hedge_missing,
                "entry_option_premium_usd": entry_option_premium,
                "option_cash_usd": option_cash,
                "hedge_cash_usd": hedge_cash,
                "option_fees_usd": option_fees,
                "hedge_fees_usd": hedge_fees,
                "total_pnl_usd": total_pnl,
                "return_on_entry_premium_pct": total_pnl / entry_option_premium * 100.0 if total_pnl is not None and entry_option_premium > 0 else None,
            }
        )
    return rows


def summarize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for structure, policy in sorted({(row["structure"], row["policy"]) for row in rows}):
        items = [row for row in rows if row["structure"] == structure and row["policy"] == policy]
        filled_items = [row for row in items if row["filled_legs"]]
        waits = [row["first_fill_wait_seconds"] for row in items if row["first_fill_wait_seconds"] is not None]
        pnls = [row["total_pnl_usd"] for row in filled_items if row["total_pnl_usd"] is not None]
        returns = [row.get("return_on_entry_premium_pct") for row in filled_items if row.get("return_on_entry_premium_pct") is not None]
        result.append(
            {
                "structure": structure,
                "policy": policy,
                "cohorts": len(items),
                "firstLegCohorts": sum(row["filled_legs"] >= 1 for row in items),
                "bothFilled": sum(row["both_filled"] for row in items),
                "partialFilled": sum(row["filled_legs"] == 1 for row in items),
                "hedgeMissing": sum(row["hedge_missing"] for row in items if row["filled_legs"]),
                "medianFirstLegWaitSeconds": statistics.median(waits) if waits else None,
                "medianTotalPnlUsd": statistics.median(pnls) if pnls else None,
                "medianReturnOnEntryPremiumPct": statistics.median(returns) if returns else None,
                "medianOptionFeesUsd": statistics.median(row["option_fees_usd"] for row in filled_items) if filled_items else None,
                "medianHedgeFeesUsd": statistics.median(row["hedge_fees_usd"] for row in filled_items) if filled_items else None,
            }
        )
    return result


def fee_sensitivity(
    cohorts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    structures: list[dict[str, Any]],
    deltas: dict[str, dict[str, float]],
    *,
    option_fee_bps: float,
    hedge_fee_values: tuple[float, ...],
    hedge_quote_age_seconds: float,
) -> list[dict[str, Any]]:
    result = []
    for hedge_fee_bps in sorted(set(hedge_fee_values)):
        rows = staged_rows(
            cohorts,
            events,
            structures,
            deltas,
            option_fee_bps=option_fee_bps,
            hedge_fee_bps=hedge_fee_bps,
            hedge_quote_age_seconds=hedge_quote_age_seconds,
        )
        filled = [row for row in rows if row["filled_legs"] and row["total_pnl_usd"] is not None]
        returns = [row["return_on_entry_premium_pct"] for row in filled if row["return_on_entry_premium_pct"] is not None]
        result.append(
            {
                "hedgeFeeBps": hedge_fee_bps,
                "filledSamples": len(filled),
                "medianTotalPnlUsd": statistics.median(row["total_pnl_usd"] for row in filled) if filled else None,
                "medianReturnOnEntryPremiumPct": statistics.median(returns) if returns else None,
                "positiveSamples": sum(row["total_pnl_usd"] > 0 for row in filled),
            }
        )
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(output_dir: Path, payload: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "staged_orders.csv", rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def replay_directory(source_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    source = json.loads((source_dir / "summary.json").read_text(encoding="utf-8"))
    config = source["config"]
    structures = source["structures"]
    delta_map = source["deltaByInstId"]
    events = load_events(source_dir / "raw")
    cohorts = simulate_cohorts(
        events,
        structures,
        cohort_interval_seconds=float(config["cohort_interval_seconds"]),
        ttl_seconds=float(config["order_ttl_seconds"]),
        max_quote_age_seconds=float(config["max_quote_age_seconds"]),
    )
    rows = staged_rows(
        cohorts,
        events,
        structures,
        delta_map,
        option_fee_bps=float(config["option_fee_bps"]),
        hedge_fee_bps=float(config["hedge_fee_bps"]),
        hedge_quote_age_seconds=float(config["hedge_quote_age_seconds"]),
    )
    payload = dict(source)
    payload["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["eventCount"] = len(events)
    payload["cohortCount"] = len(rows)
    payload["summary"] = summarize_rows(rows)
    payload["feeSensitivity"] = fee_sensitivity(
        cohorts,
        events,
        structures,
        delta_map,
        option_fee_bps=float(config["option_fee_bps"]),
        hedge_fee_values=(0.0, 2.0, float(config["hedge_fee_bps"])),
        hedge_quote_age_seconds=float(config["hedge_quote_age_seconds"]),
    )
    target = output_dir or source_dir
    write_outputs(target, payload, rows)
    return {"outputDir": str(target), "events": len(events), "cohorts": len(rows)}


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# OKX `_UM` 首腿成交后永续对冲纸面研究",
        "",
        "> 仅使用 OKX 公共 REST/WebSocket；没有账户读取、委托或真实成交。",
        "",
        "## 模型",
        "",
        "- 两腿仍按 post-only ask 穿价判定；首腿触发后按 OKX 公共 Delta 计算基础币敞口。",
        "- 永续对冲按当时 bid/ask 执行，记录盘口半价差和手续费；第二腿在 TTL 内触发则调整目标对冲。",
        "- TTL 到期时已成交期权按最后可用 bid 纸面退出，永续按相反方向平仓。",
        "- 单腿订单没有成交时不虚构盈亏；缺少永续盘口或退出报价的样本单独标记。",
        f"- 采集 {payload['config']['duration_seconds']:.0f} 秒；行情事件 {payload['eventCount']}；纸面订单 {payload['cohortCount']}。",
        "",
        "## 结果",
        "",
        "| 结构 | 策略 | 纸面订单 | 首腿触发 | 双腿触发 | 单腿触发 | 中位首腿等待 | 中位 PnL | 相对首腿权利金 | 中位永续费 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["summary"]:
        wait = "n/a" if item["medianFirstLegWaitSeconds"] is None else f"{item['medianFirstLegWaitSeconds']:.1f}s"
        pnl = "n/a" if item["medianTotalPnlUsd"] is None else f"{item['medianTotalPnlUsd']:.6f}"
        return_pct = "n/a" if item["medianReturnOnEntryPremiumPct"] is None else f"{item['medianReturnOnEntryPremiumPct']:.1f}%"
        hedge_fee = "n/a" if item["medianHedgeFeesUsd"] is None else f"{item['medianHedgeFeesUsd']:.6f}"
        lines.append(
            f"| {item['structure']} | {item['policy']} | {item['cohorts']} | {item['firstLegCohorts']} | "
            f"{item['bothFilled']} | {item['partialFilled']} | {wait} | {pnl} | {return_pct} | {hedge_fee} |"
        )
    lines.extend([
        "",
        "## 永续手续费敏感性",
        "",
        "| 永续单边费率 | 已触发样本 | 中位 PnL | 相对首腿权利金 | 正收益 |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ])
    for item in payload.get("feeSensitivity", []):
        pnl = "n/a" if item["medianTotalPnlUsd"] is None else f"{item['medianTotalPnlUsd']:.6f}"
        return_pct = "n/a" if item["medianReturnOnEntryPremiumPct"] is None else f"{item['medianReturnOnEntryPremiumPct']:.1f}%"
        lines.append(
            f"| {item['hedgeFeeBps']:.1f} bps | {item['filledSamples']} | {pnl} | {return_pct} | {item['positiveSamples']} |"
        )
    lines.extend([
        "",
        "## 边界",
        "",
        "- 这是成交与成本模型，不是实盘成交记录；队列位置、订单大小和资金费率未建模。",
        "- 公共 Greeks 是采集时快照，历史期间用固定 Delta 近似；应在跨时段采集时同步保存 Greeks。",
        "- 首腿被动穿价通常代表标的向该方向移动，永续对冲只能降低 Delta，不能消除跳价和期权流动性风险。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.replay_dir:
        source_dir = resolve_output_dir(args.replay_dir)
        target_dir = resolve_output_dir(args.output_dir) if args.output_dir else source_dir
        result = replay_directory(source_dir, target_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["events"] and result["cohorts"] else 1
    if args.duration_seconds <= args.order_ttl_seconds or min(args.cohort_interval_seconds, args.order_ttl_seconds, args.max_quote_age_seconds, args.hedge_quote_age_seconds) <= 0:
        raise ValueError("duration must exceed TTL and timing values must be positive")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    structures = select_structures(
        args.bases,
        now_ms=now_ms,
        min_hours=args.min_hours_to_expiry,
        max_hours=args.max_hours_to_expiry,
        otm_target_pct=args.otm_target_pct,
    )
    delta_map = option_deltas(structures)
    output_dir = resolve_output_dir(args.output_dir) if args.output_dir else DEFAULT_OUTPUT
    raw_root = output_dir / "raw"
    option_ids = tuple(dict.fromkeys(structure[label]["instId"] for structure in structures for label in ("call", "put")))
    hedge_ids = tuple(f"{base}-USDT-SWAP" for base in dict.fromkeys(structure["base"] for structure in structures))
    import asyncio
    stats: CollectorStats = asyncio.run(
        collect(
            instruments=option_ids + hedge_ids,
            channels=("bbo-tbt", "trades"),
            url="wss://ws.okx.com:8443/ws/v5/public",
            output_root=raw_root,
            duration_seconds=args.duration_seconds,
            heartbeat_seconds=15.0,
            min_free_gb=0.0,
        )
    )
    events = load_events(raw_root)
    cohorts = simulate_cohorts(events, structures, cohort_interval_seconds=args.cohort_interval_seconds, ttl_seconds=args.order_ttl_seconds, max_quote_age_seconds=args.max_quote_age_seconds)
    staged = staged_rows(cohorts, events, structures, delta_map, option_fee_bps=args.option_fee_bps, hedge_fee_bps=args.hedge_fee_bps, hedge_quote_age_seconds=args.hedge_quote_age_seconds)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_okx_public_websocket_staged_option_fill_perp_hedge_research",
        "execution": "no account reads and no orders",
        "config": vars(args),
        "collectorStats": asdict(stats),
        "structures": structures,
        "deltaByInstId": delta_map,
        "eventCount": len(events),
        "cohortCount": len(staged),
        "summary": summarize_rows(staged),
        "feeSensitivity": fee_sensitivity(
            cohorts,
            events,
            structures,
            delta_map,
            option_fee_bps=args.option_fee_bps,
            hedge_fee_values=(0.0, 2.0, args.hedge_fee_bps),
            hedge_quote_age_seconds=args.hedge_quote_age_seconds,
        ),
    }
    write_outputs(output_dir, payload, staged)
    print(json.dumps({"outputDir": str(output_dir), "events": len(events), "cohorts": len(staged)}, ensure_ascii=False))
    return 0 if events and staged and not stats.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
