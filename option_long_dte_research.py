"""Research longer-DTE BTC/ETH long strangles with an IV/realized-vol filter.

This deliberately lives beside the original short-dated backtest so the
published 24-hour baseline remains unchanged.  It reuses the same Deribit
hourly cache, Black-Scholes inference, liquidity checks, option slippage and
perpetual delta-hedging simulator.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from option_strangle_backtest import (
    DEFAULT_CACHE,
    HOUR_MS,
    SLIPPAGE_BPS,
    BacktestConfig,
    DeribitHistory,
    candidate_strikes,
    expiry_code,
    implied_volatility,
    iso_ms,
    nearest_pair,
    parse_iso_ms,
    run_trade,
    traded_observation,
)


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "option_strangle_backtest"
ENTRY_WINDOWS_HOURS = (24, 72, 168)
OTM_PCTS = (0.0, 0.5, 1.0, 1.5, 2.0)
REALIZED_LOOKBACK_HOURS = 168
HEDGE_VARIANTS = (
    ("baseline", 5.0, 6, 4),
    ("threshold10", 10.0, 6, 4),
    ("threshold20_daily", 20.0, 24, 1),
)
VOL_FILTERS = ("all", "iv_rv_le_1.0", "iv_rv_le_1.2", "iv_rv_gt_1.2")
QUARTERLY_EXPIRIES = (
    "2022-09-30T08:00:00Z",
    "2022-12-30T08:00:00Z",
    "2023-03-31T08:00:00Z",
    "2023-06-30T08:00:00Z",
    "2023-09-29T08:00:00Z",
    "2023-12-29T08:00:00Z",
    "2024-03-29T08:00:00Z",
    "2024-06-28T08:00:00Z",
    "2024-09-27T08:00:00Z",
    "2024-12-27T08:00:00Z",
    "2025-03-28T08:00:00Z",
    "2025-06-27T08:00:00Z",
    "2025-09-26T08:00:00Z",
    "2025-12-26T08:00:00Z",
    "2026-03-27T08:00:00Z",
    "2026-06-26T08:00:00Z",
)


def realized_volatility(underlying: tuple[Any, ...], entry_ts: int, lookback_hours: int = REALIZED_LOOKBACK_HOURS) -> float | None:
    """Annualized hourly close-to-close volatility before entry."""
    start = entry_ts - lookback_hours * HOUR_MS
    closes = [bar.close for bar in underlying if start <= bar.ts <= entry_ts and bar.close > 0]
    if len(closes) < 25:
        return None
    returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:]) if previous > 0 and current > 0]
    if len(returns) < 24:
        return None
    return statistics.stdev(returns) * math.sqrt(24.0 * 365.25)


def entry_volatility(pair: Any, spot: float, entry_ts: int, entry_hours: int) -> float | None:
    """Average IV inferred from the call and put entry observations."""
    call = traded_observation(pair.call_bars, entry_ts, 6)
    put = traded_observation(pair.put_bars, entry_ts, 6)
    if call is None or put is None:
        return None
    years = max(entry_hours / (365.25 * 24.0), 1e-9)
    call_iv = implied_volatility(call[0].close * spot, spot, pair.call_strike, years, "C")
    put_iv = implied_volatility(put[0].close * spot, spot, pair.put_strike, years, "P")
    if call_iv is None or put_iv is None:
        return None
    return (call_iv + put_iv) / 2.0


def passes_filter(name: str, iv_rv_ratio: float) -> bool:
    if name == "all":
        return True
    if name == "iv_rv_le_1.0":
        return iv_rv_ratio <= 1.0
    if name == "iv_rv_le_1.2":
        return iv_rv_ratio <= 1.2
    if name == "iv_rv_gt_1.2":
        return iv_rv_ratio > 1.2
    raise ValueError(f"unknown volatility filter: {name}")


def collect_rows(history: DeribitHistory, expiries: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for base in ("BTC", "ETH"):
        boundary = len(expiries) // 2
        for index, expiry_ms in enumerate(expiries):
            sample = "train" if index < boundary else "test"
            for entry_hours in ENTRY_WINDOWS_HOURS:
                entry_ts = expiry_ms - entry_hours * HOUR_MS
                exit_ts = expiry_ms - HOUR_MS
                start_ms = expiry_ms - (entry_hours + REALIZED_LOOKBACK_HOURS + 4) * HOUR_MS
                underlying_name = f"{base}-PERPETUAL"
                underlying = history.fetch_many([underlying_name], start_ms, expiry_ms).get(underlying_name, ())
                entry_bar = next((bar for bar in underlying if bar.ts == entry_ts), None)
                if entry_bar is None:
                    continue
                code = expiry_code(expiry_ms)
                # Strikes are selected at each DTE's entry spot, then held fixed.
                instruments = [
                    f"{base}-{code}-{strike:g}-{option_type}"
                    for strike in candidate_strikes(base, entry_bar.close)
                    for option_type in ("C", "P")
                ]
                charts = history.fetch_many(instruments, start_ms, expiry_ms)
                rv = realized_volatility(underlying, entry_ts)
                if rv is None or rv <= 0:
                    continue
                for otm_pct in OTM_PCTS:
                    pair = nearest_pair(base, expiry_ms, entry_bar.close, otm_pct, charts, entry_ts, exit_ts, 6)
                    if pair is None:
                        continue
                    iv = entry_volatility(pair, entry_bar.close, entry_ts, entry_hours)
                    if iv is None or iv <= 0:
                        continue
                    iv_rv_ratio = iv / rv
                    for vol_filter in VOL_FILTERS:
                        if not passes_filter(vol_filter, iv_rv_ratio):
                            continue
                        for variant, threshold, interval, max_rehedges_per_day in HEDGE_VARIANTS:
                            for slippage in SLIPPAGE_BPS:
                                max_rehedges = max_rehedges_per_day * max(1, math.ceil(entry_hours / 24))
                                config = BacktestConfig(
                                    option_slippage_bps=slippage,
                                    delta_threshold_pct=threshold,
                                    hedge_interval_hours=interval,
                                    max_rehedges=max_rehedges,
                                    entry_hours_before_expiry=entry_hours,
                                )
                                row = run_trade(base, expiry_ms, underlying, pair, config, sample, variant)
                                if row is None:
                                    continue
                                item = asdict(row)
                                item.update(
                                    {
                                        "entry_hours_before_expiry": entry_hours,
                                        "vol_filter": vol_filter,
                                        "entry_iv": iv,
                                        "realized_vol_7d": rv,
                                        "iv_rv_ratio": iv_rv_ratio,
                                    }
                                )
                                rows.append(item)
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for base in ("BTC", "ETH"):
        for sample in ("train", "test"):
            for entry_hours in ENTRY_WINDOWS_HOURS:
                for vol_filter in VOL_FILTERS:
                    for slippage in SLIPPAGE_BPS:
                        for variant, threshold, interval, max_rehedges_per_day in HEDGE_VARIANTS:
                            for otm_pct in OTM_PCTS:
                                items = [
                                    row
                                    for row in rows
                                    if row["underlying"] == base
                                    and row["sample"] == sample
                                    and row["entry_hours_before_expiry"] == entry_hours
                                    and row["vol_filter"] == vol_filter
                                    and row["option_slippage_bps"] == slippage
                                    and row["hedge_variant"] == variant
                                    and row["target_otm_pct"] == otm_pct
                                ]
                                if not items:
                                    continue
                                returns = [row["return_on_premium_pct"] for row in items]
                                result.append(
                                    {
                                        "underlying": base,
                                        "sample": sample,
                                        "entry_hours_before_expiry": entry_hours,
                                        "vol_filter": vol_filter,
                                        "option_slippage_bps": slippage,
                                        "target_otm_pct": otm_pct,
                                        "hedge_variant": variant,
                                        "delta_threshold_pct": threshold,
                                        "hedge_interval_hours": interval,
                                        "max_rehedges": max_rehedges_per_day * max(1, math.ceil(entry_hours / 24)),
                                        "count": len(items),
                                        "positive": sum(value > 0 for value in returns),
                                        "median_return_on_premium_pct": statistics.median(returns),
                                        "mean_return_on_premium_pct": statistics.fmean(returns),
                                        "worst_return_on_premium_pct": min(returns),
                                        "median_premium_pct_spot": statistics.median(row["entry_premium_pct_spot"] for row in items),
                                        "median_theta_pct_premium": statistics.median(row["theta_pct_premium"] for row in items),
                                        "median_iv_pct": statistics.median(row["entry_iv"] for row in items) * 100.0,
                                        "median_realized_vol_7d_pct": statistics.median(row["realized_vol_7d"] for row in items) * 100.0,
                                        "median_iv_rv_ratio": statistics.median(row["iv_rv_ratio"] for row in items),
                                        "median_rehedges": statistics.median(row["rehedges"] for row in items),
                                    }
                                )
    return result


def selected_by_training(summary: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for base in ("BTC", "ETH"):
        base_candidates = [
            item
            for item in summary
            if item["underlying"] == base
            and item["sample"] == "train"
            and item["option_slippage_bps"] == 100.0
        ]
        if not base_candidates:
            continue
        maximum_count = max(item["count"] for item in base_candidates if item["vol_filter"] == "all")
        minimum_count = max(2, math.ceil(maximum_count * 0.75))
        candidates = [item for item in base_candidates if item["count"] >= minimum_count]
        if not candidates:
            continue
        best = max(candidates, key=lambda item: (item["median_return_on_premium_pct"], item["mean_return_on_premium_pct"]))
        training_median = float(best["median_return_on_premium_pct"])
        selected[base] = {
            "entryHoursBeforeExpiry": int(best["entry_hours_before_expiry"]),
            "targetOtmPct": float(best["target_otm_pct"]),
            "volFilter": best["vol_filter"],
            "hedgeVariant": best["hedge_variant"],
            "deltaThresholdPct": float(best["delta_threshold_pct"]),
            "hedgeIntervalHours": int(best["hedge_interval_hours"]),
            "maxRehedges": int(best["max_rehedges"]),
            "trainingCount": int(best["count"]),
            "minimumTrainingCount": minimum_count,
            "trainingMedianReturnOnPremiumPct": training_median,
            "decision": "candidate" if training_median > 0 else "reject_no_positive_training_edge",
        }
    return selected


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# BTC/ETH 长 DTE、轻度 OTM 与 IV/RV 过滤研究",
        "",
        "> Deribit 公共历史成交价研究；不读取账户、不发送订单。收益均为初始权利金的百分比。",
        "",
        "## 规则",
        "",
        f"- 到期日：{', '.join(item[:10] for item in payload['expiries'])}；前半段训练，后半段样本外。",
        "- 比较到期前 24/72/168 小时入场、到期前 1 小时退出；OTM 为 0/0.5/1/1.5/2%。",
        "- 对冲变体为 Delta 5%/6 小时/每 24h 最多 4 次、Delta 10%/6 小时/每 24h 最多 4 次、Delta 20%/24 小时/每 24h 最多 1 次。",
        "- IV 由入场成交价反推，RV 为入场前 7 日小时收益年化波动率；过滤条件为全部、IV/RV≤1.0、IV/RV≤1.2、IV/RV>1.2。",
        "- 期权滑点报告 0.5%/1%/2% 每端，永续对冲成本 5 bps；没有历史 bid/ask。",
        "",
        "## 无 IV/RV 过滤的样本外结果（期权每端 1% 滑点）",
        "",
        "| 标的 | 入场 DTE | ATM | OTM 0.5% | OTM 1% | OTM 1.5% | OTM 2% |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for base in ("BTC", "ETH"):
        for hours in ENTRY_WINDOWS_HOURS:
            values = []
            for otm in OTM_PCTS:
                item = next((item for item in payload["summary"] if item["underlying"] == base and item["sample"] == "test" and item["entry_hours_before_expiry"] == hours and item["vol_filter"] == "all" and item["option_slippage_bps"] == 100.0 and item["hedge_variant"] == "baseline" and item["target_otm_pct"] == otm), None)
                values.append("n/a" if item is None else f"{item['median_return_on_premium_pct']:.1f}% ({item['positive']}/{item['count']})")
            lines.append(f"| {base} | {hours}h | " + " | ".join(values) + " |")
    lines.extend([
        "",
        "## 训练选择后的样本外结果（每端 1% 滑点）",
        "",
        "| 标的 | 训练选择 | 决策 | 训练样本 | 训练中位收益 | 样本外窗口 | 样本外中位收益 | 样本外平均收益 | 正收益 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for base, selected in payload["selectedByTraining"].items():
        item = next((item for item in payload["summary"] if item["underlying"] == base and item["sample"] == "test" and item["entry_hours_before_expiry"] == selected["entryHoursBeforeExpiry"] and item["target_otm_pct"] == selected["targetOtmPct"] and item["vol_filter"] == selected["volFilter"] and item["hedge_variant"] == selected["hedgeVariant"] and item["option_slippage_bps"] == 100.0), None)
        if item is None:
            continue
        structure = f"{selected['entryHoursBeforeExpiry']}h/{selected['targetOtmPct']:g}%/{selected['volFilter']}/{selected['hedgeVariant']}"
        decision = "候选" if selected["decision"] == "candidate" else "拒绝：训练期无正优势"
        lines.append(f"| {base} | {structure} | {decision} | {selected['trainingCount']} (最低 {selected['minimumTrainingCount']}) | {selected['trainingMedianReturnOnPremiumPct']:.1f}% | {item['count']} | {item['median_return_on_premium_pct']:.1f}% | {item['mean_return_on_premium_pct']:.1f}% | {item['positive']}/{item['count']} |")
    lines.extend([
        "",
        "## IV/RV 过滤对照（样本外，基准 24h ATM）",
        "",
        "| 标的 | 过滤 | 窗口 | 中位收益/权利金 | 平均收益/权利金 | 正收益 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for base in ("BTC", "ETH"):
        for filter_name in VOL_FILTERS:
            item = next((item for item in payload["summary"] if item["underlying"] == base and item["sample"] == "test" and item["entry_hours_before_expiry"] == 24 and item["target_otm_pct"] == 0.0 and item["vol_filter"] == filter_name and item["hedge_variant"] == "baseline" and item["option_slippage_bps"] == 100.0), None)
            if item is not None:
                lines.append(f"| {base} | {filter_name} | {item['count']} | {item['median_return_on_premium_pct']:.1f}% | {item['mean_return_on_premium_pct']:.1f}% | {item['positive']}/{item['count']} |")
    lines.extend([
        "",
        "## 边界",
        "",
        "- 长 DTE 可以降低单位时间 Theta，但样本中的远期成交更稀疏，必须把成交新鲜度和真实 bid/ask 纳入验证。",
        "- IV/RV 过滤会减少交易次数；若训练样本不足，任何看似改善都可能只是筛选偏差。",
        "- 请求的 0.5%/1%/1.5% OTM 会受实际行权价间隔限制；多个目标档位可能选择到同一组期权，不能当作独立样本。",
        "- Deribit 反向期权与 OKX `_UM` 线性期权在盘口、乘数和结算币种上不同，不能直接迁移收益率。",
        "",
    ])
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research longer DTE and IV/RV filters for BTC/ETH options")
    parser.add_argument("--cache-file", default=str(DEFAULT_CACHE))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--expiry", action="append", dest="expiries", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expiries = sorted(parse_iso_ms(item) for item in (args.expiries or list(QUARTERLY_EXPIRIES)))
    history = DeribitHistory(Path(args.cache_file), workers=args.workers)
    rows = collect_rows(history, expiries)
    if not rows:
        raise SystemExit("No long-DTE research rows passed liquidity and volatility checks")
    summary = summarize(rows)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_deribit_long_dte_iv_rv_research",
        "source": {
            "name": "Deribit public TradingView chart API",
            "url": "https://www.deribit.com/api/v2/public/get_tradingview_chart_data",
            "fields": "hourly close and volume",
            "cacheFile": str(Path(args.cache_file).resolve()),
        },
        "expiries": [iso_ms(item) for item in expiries],
        "entryWindowsHours": list(ENTRY_WINDOWS_HOURS),
        "otmPcts": list(OTM_PCTS),
        "realizedLookbackHours": REALIZED_LOOKBACK_HOURS,
        "volFilters": list(VOL_FILTERS),
        "hedgeVariants": [
            {"name": name, "deltaThresholdPct": threshold, "hedgeIntervalHours": interval, "maxRehedgesPer24h": max_rehedges_per_day}
            for name, threshold, interval, max_rehedges_per_day in HEDGE_VARIANTS
        ],
        "slippageBps": list(SLIPPAGE_BPS),
        "selectedByTraining": selected_by_training(summary),
        "summary": summary,
    }
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_ROOT / datetime.now(timezone.utc).strftime("long-dte-iv-rv-%Y%m%d")
    if not output_dir.is_absolute():
        output_dir = OUTPUT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "trades.csv", rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"rows={len(rows)} cache_series={len(history.cache)} selected={payload['selectedByTraining']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
