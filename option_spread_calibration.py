"""Calibrate BTC/ETH option slippage from public Tardis bid/ask snapshots.

Tardis makes the first day of each month available without an API key.  Full
daily files are several gigabytes, so this script streams only the first ten
seconds of each options-chain file, retains one cross-sectional quote per
symbol, and closes the response.  The resulting empirical half-spreads are
then applied to the existing quarterly Deribit backtest as transaction-cost
stress tests.  No account or trading endpoints are used.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = PROJECT_ROOT / "data" / "options" / "tardis_option_chain_snapshots.json"
DEFAULT_SOURCE_TRADES = PROJECT_ROOT / "reports" / "option_strangle_backtest" / "long-dte-quarterly-20260807" / "trades.csv"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "option_strangle_backtest"
TARDIS_DATASETS = "https://datasets.tardis.dev/v1"
EXCHANGES = ("deribit", "okex-options")
OKX_CURRENT_EXCHANGE = "okx-um-current"
SAMPLE_DATES = (
    "2023-03-01",
    "2023-06-01",
    "2023-09-01",
    "2023-12-01",
    "2024-03-01",
    "2024-06-01",
    "2024-09-01",
    "2024-12-01",
    "2025-03-01",
    "2025-06-01",
    "2025-09-01",
    "2025-12-01",
    "2026-03-01",
    "2026-06-01",
)
WINDOW_SECONDS = 10
REQUEST_INTERVAL_SECONDS = 7.0


class PublicRateLimit(RuntimeError):
    def __init__(self, exchange: str, sample_date: str, retry_after: float) -> None:
        super().__init__(f"{exchange} {sample_date} public rate limit; retry after {retry_after:g}s")
        self.retry_after = retry_after


def optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def base_from_symbol(symbol: str) -> str | None:
    prefix = symbol.split("-", 1)[0].upper()
    return prefix if prefix in {"BTC", "ETH"} else None


def dte_bucket(hours: float) -> str | None:
    if 8.0 <= hours <= 48.0:
        return "24h"
    if 48.0 < hours <= 120.0:
        return "72h"
    if 120.0 < hours <= 240.0:
        return "168h"
    return None


def option_otm_pct(option_type: str, strike: float, underlying: float) -> float:
    if option_type == "call":
        return (strike / underlying - 1.0) * 100.0
    return (1.0 - strike / underlying) * 100.0


def moneyness_bucket(otm_pct: float) -> str | None:
    if -0.75 <= otm_pct <= 0.75:
        return "atm"
    if 0.75 < otm_pct <= 2.5:
        return "light_otm"
    if 2.5 < otm_pct <= 5.0:
        return "deep_otm"
    return None


def half_spread_bps(bid: float, ask: float) -> float | None:
    if bid <= 0 or ask <= bid:
        return None
    return (ask - bid) / (ask + bid) * 10_000.0


def compact_row(exchange: str, sample_date: str, row: dict[str, str]) -> dict[str, Any] | None:
    symbol = row.get("symbol", "")
    base = base_from_symbol(symbol)
    timestamp = optional_float(row.get("timestamp"))
    expiration = optional_float(row.get("expiration"))
    strike = optional_float(row.get("strike_price"))
    underlying = optional_float(row.get("underlying_price"))
    option_type = row.get("type", "")
    if base is None or timestamp is None or expiration is None or strike is None or underlying is None or underlying <= 0:
        return None
    hours = (expiration - timestamp) / 3_600_000_000.0
    dte = dte_bucket(hours)
    money = moneyness_bucket(option_otm_pct(option_type, strike, underlying))
    if dte is None or money is None:
        return None
    return {
        "exchange": exchange,
        "sample_date": sample_date,
        "symbol": symbol,
        "timestamp": int(timestamp),
        "local_timestamp": int(optional_float(row.get("local_timestamp")) or timestamp),
        "base": base,
        "type": option_type,
        "strike_price": strike,
        "expiration": int(expiration),
        "underlying_price": underlying,
        "dte_hours": hours,
        "dte_bucket": dte,
        "otm_pct": option_otm_pct(option_type, strike, underlying),
        "moneyness_bucket": money,
        "bid_price": optional_float(row.get("bid_price")),
        "bid_amount": optional_float(row.get("bid_amount")),
        "ask_price": optional_float(row.get("ask_price")),
        "ask_amount": optional_float(row.get("ask_amount")),
        "mark_iv": optional_float(row.get("mark_iv")),
    }


def stream_snapshot(exchange: str, sample_date: str, window_seconds: int = WINDOW_SECONDS) -> list[dict[str, Any]]:
    date_path = sample_date.replace("-", "/")
    url = f"{TARDIS_DATASETS}/{exchange}/options_chain/{date_path}/OPTIONS.csv.gz"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "okx-quant-research/1.0"})
            by_symbol: dict[str, dict[str, Any]] = {}
            first_local: int | None = None
            with urllib.request.urlopen(request, timeout=30) as response:
                with gzip.GzipFile(fileobj=response) as compressed:
                    with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                        for source in csv.DictReader(text):
                            local = int(optional_float(source.get("local_timestamp")) or 0)
                            if local <= 0:
                                continue
                            first_local = local if first_local is None else first_local
                            if local - first_local > window_seconds * 1_000_000:
                                break
                            item = compact_row(exchange, sample_date, source)
                            if item is not None:
                                by_symbol[item["symbol"]] = item
            return list(by_symbol.values())
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                retry_after = optional_float(exc.headers.get("Retry-After")) or 5.0 * (attempt + 1)
                print(f"rate_limited={exchange}|{sample_date} retry_after_seconds={retry_after:g}", flush=True)
                if retry_after > 60.0:
                    raise PublicRateLimit(exchange, sample_date, retry_after) from exc
                time.sleep(retry_after)
            else:
                time.sleep(0.5 * (attempt + 1))
        except Exception as exc:  # Public downloads are retried and remain read-only.
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"failed to stream {exchange} {sample_date}: {last_error}")


def save_cache(path: Path, snapshots: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"snapshots": snapshots}, separators=(",", ":")), encoding="utf-8")
    temp.replace(path)


def load_snapshots(path: Path, dates: Iterable[str], exchanges: Iterable[str], cached_only: bool = False) -> list[dict[str, Any]]:
    snapshots: dict[str, list[dict[str, Any]]] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            loaded = payload.get("snapshots", {}) if isinstance(payload, dict) else {}
            if isinstance(loaded, dict):
                snapshots = loaded
        except (OSError, json.JSONDecodeError):
            snapshots = {}
    for exchange in exchanges:
        for sample_date in dates:
            key = f"{exchange}|{sample_date}|{WINDOW_SECONDS}"
            if key in snapshots:
                continue
            if cached_only:
                continue
            try:
                rows = stream_snapshot(exchange, sample_date)
            except PublicRateLimit as exc:
                print(f"using_partial_cache=true reason={exc}", flush=True)
                requested = {f"{item_exchange}|{item_date}|{WINDOW_SECONDS}" for item_exchange in exchanges for item_date in dates}
                return [row for item_key, item_rows in snapshots.items() if item_key in requested for row in item_rows]
            snapshots[key] = rows
            save_cache(path, snapshots)
            two_sided = sum(half_spread_bps(item.get("bid_price") or 0.0, item.get("ask_price") or 0.0) is not None for item in rows)
            print(f"snapshot={key} eligible={len(rows)} two_sided={two_sided}", flush=True)
            time.sleep(REQUEST_INTERVAL_SECONDS)
    requested = {f"{exchange}|{sample_date}|{WINDOW_SECONDS}" for exchange in exchanges for sample_date in dates}
    return [row for key, rows in snapshots.items() if key in requested for row in rows]


def okx_public(path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"https://www.okx.com{path}?{query}", headers={"User-Agent": "okx-quant-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != "0" or not isinstance(payload.get("data"), list):
        raise RuntimeError(f"OKX public API error: {payload.get('code')} {payload.get('msg')}")
    return payload["data"]


def current_okx_um_snapshot() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for base in ("BTC", "ETH"):
        underlying_id = f"{base}-USD"
        family = f"{base}-USD_UM"
        tickers = okx_public("/api/v5/market/tickers", {"instType": "OPTION", "uly": underlying_id})
        instruments = okx_public("/api/v5/public/instruments", {"instType": "OPTION", "instFamily": family})
        index_rows = okx_public("/api/v5/market/index-tickers", {"instId": underlying_id})
        index_price = optional_float(index_rows[0].get("idxPx")) if index_rows else None
        ticker_by_id = {row.get("instId"): row for row in tickers if "_UM-" in row.get("instId", "")}
        if index_price is None or index_price <= 0:
            continue
        for instrument in instruments:
            ticker = ticker_by_id.get(instrument.get("instId"))
            expiration_ms = optional_float(instrument.get("expTime"))
            strike = optional_float(instrument.get("stk"))
            timestamp_ms = optional_float(ticker.get("ts")) if ticker else None
            if ticker is None or expiration_ms is None or strike is None or timestamp_ms is None:
                continue
            hours = (expiration_ms - timestamp_ms) / 3_600_000.0
            dte = dte_bucket(hours)
            option_type = "call" if instrument.get("optType") == "C" else "put"
            otm_pct = option_otm_pct(option_type, strike, index_price)
            money = moneyness_bucket(otm_pct)
            if dte is None or money is None:
                continue
            result.append(
                {
                    "exchange": OKX_CURRENT_EXCHANGE,
                    "sample_date": datetime.fromtimestamp(timestamp_ms / 1000.0, timezone.utc).date().isoformat(),
                    "symbol": instrument["instId"],
                    "timestamp": int(timestamp_ms * 1000),
                    "local_timestamp": int(timestamp_ms * 1000),
                    "base": base,
                    "type": option_type,
                    "strike_price": strike,
                    "expiration": int(expiration_ms * 1000),
                    "underlying_price": index_price,
                    "dte_hours": hours,
                    "dte_bucket": dte,
                    "otm_pct": otm_pct,
                    "moneyness_bucket": money,
                    "bid_price": optional_float(ticker.get("bidPx")),
                    "bid_amount": optional_float(ticker.get("bidSz")),
                    "ask_price": optional_float(ticker.get("askPx")),
                    "ask_amount": optional_float(ticker.get("askSz")),
                    "mark_iv": None,
                }
            )
    return result


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def summarize_spreads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["exchange"], row["base"], row["dte_bucket"], row["moneyness_bucket"])].append(row)
    result = []
    for (exchange, base, dte, money), items in sorted(grouped.items()):
        spreads = [
            value
            for item in items
            if (value := half_spread_bps(item.get("bid_price") or 0.0, item.get("ask_price") or 0.0)) is not None
            and (item.get("bid_amount") or 0.0) > 0
            and (item.get("ask_amount") or 0.0) > 0
        ]
        if not spreads:
            continue
        result.append(
            {
                "exchange": exchange,
                "base": base,
                "dte_bucket": dte,
                "moneyness_bucket": money,
                "eligible_quotes": len(items),
                "two_sided_quotes": len(spreads),
                "two_sided_coverage_pct": len(spreads) / len(items) * 100.0,
                "median_half_spread_bps": statistics.median(spreads),
                "p75_half_spread_bps": percentile(spreads, 0.75),
                "p90_half_spread_bps": percentile(spreads, 0.90),
                "sample_dates": len({item["sample_date"] for item in items}),
            }
        )
    return result


def strategy_money_bucket(target_otm_pct: float) -> str:
    if target_otm_pct == 0:
        return "atm"
    return "light_otm" if target_otm_pct <= 2.5 else "deep_otm"


def fitted_value(rows: list[dict[str, str]], field: str, slippage_bps: float) -> float:
    xs = [float(row["option_slippage_bps"]) for row in rows]
    ys = [float(row[field]) for row in rows]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator <= 0:
        return mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return mean_y + slope * (slippage_bps - mean_x)


def spread_lookup(summary: list[dict[str, Any]], exchange: str, base: str, dte: str, money: str, field: str) -> float | None:
    item = next((row for row in summary if row["exchange"] == exchange and row["base"] == base and row["dte_bucket"] == dte and row["moneyness_bucket"] == money), None)
    return float(item[field]) if item is not None else None


def reprice_trades(source_path: Path, spread_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with source_path.open(encoding="utf-8", newline="") as handle:
        source_rows = [row for row in csv.DictReader(handle) if row.get("vol_filter") == "all"]
    keys = (
        "underlying",
        "expiry",
        "sample",
        "target_otm_pct",
        "call_name",
        "put_name",
        "entry_time",
        "exit_time",
        "hedge_variant",
        "delta_threshold_pct",
        "hedge_interval_hours",
        "max_rehedges_allowed",
        "entry_hours_before_expiry",
        "vol_filter",
    )
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    result: list[dict[str, Any]] = []
    calibration_exchanges = sorted({row["exchange"] for row in spread_summary})
    for key, rows in grouped.items():
        if len({row["option_slippage_bps"] for row in rows}) < 2:
            continue
        meta = dict(zip(keys, key))
        hours = int(float(meta["entry_hours_before_expiry"]))
        dte = f"{hours}h"
        target_otm = float(meta["target_otm_pct"])
        money = strategy_money_bucket(target_otm)
        for exchange in calibration_exchanges:
            for quantile, field in (("median", "median_half_spread_bps"), ("p75", "p75_half_spread_bps")):
                slippage = spread_lookup(spread_summary, exchange, meta["underlying"], dte, money, field)
                if slippage is None:
                    continue
                premium = fitted_value(rows, "entry_premium_usd", slippage)
                pnl = fitted_value(rows, "total_pnl_usd", slippage)
                if premium <= 0:
                    continue
                result.append(
                    {
                        **meta,
                        "entry_hours_before_expiry": hours,
                        "target_otm_pct": target_otm,
                        "calibration_exchange": exchange,
                        "spread_quantile": quantile,
                        "empirical_half_spread_bps": slippage,
                        "repriced_entry_premium_usd": premium,
                        "repriced_total_pnl_usd": pnl,
                        "repriced_return_on_premium_pct": pnl / premium * 100.0,
                    }
                )
    return result


def summarize_repriced(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["calibration_exchange"],
            row["spread_quantile"],
            row["underlying"],
            row["sample"],
            row["entry_hours_before_expiry"],
            row["target_otm_pct"],
            row["hedge_variant"],
        )
        grouped[key].append(row)
    result = []
    for key, items in sorted(grouped.items()):
        values = [row["repriced_return_on_premium_pct"] for row in items]
        result.append(
            {
                "calibration_exchange": key[0],
                "spread_quantile": key[1],
                "underlying": key[2],
                "sample": key[3],
                "entry_hours_before_expiry": key[4],
                "target_otm_pct": key[5],
                "hedge_variant": key[6],
                "count": len(values),
                "positive": sum(value > 0 for value in values),
                "median_return_on_premium_pct": statistics.median(values),
                "mean_return_on_premium_pct": statistics.fmean(values),
                "worst_return_on_premium_pct": min(values),
                "empirical_half_spread_bps": statistics.median(row["empirical_half_spread_bps"] for row in items),
            }
        )
    return result


def fixed_slippage_summary(source_path: Path) -> dict[tuple[str, int], dict[str, Any]]:
    with source_path.open(encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("sample") == "test"
            and row.get("vol_filter") == "all"
            and float(row.get("target_otm_pct", 0)) == 0
            and row.get("hedge_variant") == "baseline"
            and float(row.get("option_slippage_bps", 0)) == 100.0
        ]
    result = {}
    for base in ("BTC", "ETH"):
        for hours in (24, 72, 168):
            items = [row for row in rows if row["underlying"] == base and int(float(row["entry_hours_before_expiry"])) == hours]
            values = [float(row["return_on_premium_pct"]) for row in items]
            if values:
                result[(base, hours)] = {"count": len(values), "positive": sum(value > 0 for value in values), "median": statistics.median(values)}
    return result


def execution_edge_summary(source_path: Path) -> list[dict[str, Any]]:
    with source_path.open(encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("vol_filter") == "all"
            and float(row.get("target_otm_pct", 0)) == 0
            and row.get("hedge_variant") == "threshold10"
        ]
    result = []
    for base in ("BTC", "ETH"):
        for hours in (24, 72, 168):
            training = [
                float(row["return_on_premium_pct"])
                for row in rows
                if row["underlying"] == base
                and row["sample"] == "train"
                and int(float(row["entry_hours_before_expiry"])) == hours
                and float(row["option_slippage_bps"]) == 100.0
            ]
            test_rows = [
                row
                for row in rows
                if row["underlying"] == base
                and row["sample"] == "test"
                and int(float(row["entry_hours_before_expiry"])) == hours
            ]
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in test_rows:
                grouped[row["expiry"]].append(row)

            def median_at(slippage_bps: float) -> float:
                values = []
                for items in grouped.values():
                    premium = fitted_value(items, "entry_premium_usd", slippage_bps)
                    pnl = fitted_value(items, "total_pnl_usd", slippage_bps)
                    if premium > 0:
                        values.append(pnl / premium * 100.0)
                return statistics.median(values)

            if not training or not grouped:
                continue
            zero_cost_median = median_at(0.0)
            break_even: float | None = None
            if zero_cost_median > 0:
                low, high = 0.0, 10_000.0
                if median_at(high) > 0:
                    break_even = math.inf
                else:
                    for _ in range(50):
                        middle = (low + high) / 2.0
                        if median_at(middle) > 0:
                            low = middle
                        else:
                            high = middle
                    break_even = (low + high) / 2.0
            result.append(
                {
                    "underlying": base,
                    "entry_hours_before_expiry": hours,
                    "training_median_fixed_1pct": statistics.median(training),
                    "test_count": len(grouped),
                    "test_zero_cost_median": zero_cost_median,
                    "break_even_half_spread_bps": break_even,
                }
            )
    return result


def markdown_report(payload: dict[str, Any], source_path: Path) -> str:
    fixed = fixed_slippage_summary(source_path)
    lines = [
        "# BTC/ETH 期权真实 bid/ask 价差校准",
        "",
        "> Tardis 每月首日公开 options_chain 样本；只读取公开数据，不读取账户、不发送订单。",
        "",
        "## 数据与方法",
        "",
        f"- 请求的 Tardis 采样日：{', '.join(payload['requestedSampleDates'])}。实际历史横截面：" + ", ".join(f"{key} {value} 日" for key, value in payload["historicalSamplesByExchange"].items()) + "。",
        "- Tardis 每个样本日流式读取开头 10 秒，保留每个活跃合约最后一次链快照后立即断开，不下载数 GB 的整日文件。",
        "- 另取 OKX 官方公共 API 当前 `_UM` 线性期权完整链，仅作为目标场所实时横截面，不冒充历史数据。",
        "- 半价差成本 = `(ask-bid)/(ask+bid)`；只保留 bid/ask 与两侧数量均有效的报价。",
        "- DTE 桶为 8–48h、48–120h、120–240h；ATM 为 ±0.75%，轻度 OTM 为 0.75%–2.5%。",
        "- 回灌使用此前 0.5%/1%/2% 滑点结果拟合美元 PnL 与权利金，再外推到经验中位及 75 分位半价差。",
        "",
        "## 真实半价差",
        "",
        "| 交易所 | 标的 | DTE | ATM 双边覆盖 | ATM 中位/P75 | 轻度 OTM 双边覆盖 | 轻度 OTM 中位/P75 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for exchange in payload["calibrationExchanges"]:
        for base in ("BTC", "ETH"):
            for dte in ("24h", "72h", "168h"):
                atm = next((row for row in payload["spreadSummary"] if row["exchange"] == exchange and row["base"] == base and row["dte_bucket"] == dte and row["moneyness_bucket"] == "atm"), None)
                light = next((row for row in payload["spreadSummary"] if row["exchange"] == exchange and row["base"] == base and row["dte_bucket"] == dte and row["moneyness_bucket"] == "light_otm"), None)
                if atm is None or light is None:
                    continue
                lines.append(
                    f"| {exchange} | {base} | {dte} | {atm['two_sided_coverage_pct']:.1f}% ({atm['two_sided_quotes']}) | "
                    f"{atm['median_half_spread_bps'] / 100:.2f}% / {atm['p75_half_spread_bps'] / 100:.2f}% | "
                    f"{light['two_sided_coverage_pct']:.1f}% ({light['two_sided_quotes']}) | "
                    f"{light['median_half_spread_bps'] / 100:.2f}% / {light['p75_half_spread_bps'] / 100:.2f}% |"
                )
    lines.extend([
        "",
        "## 真实价差回灌：ATM 基准策略样本外",
        "",
        "收益为初始权利金百分比；固定 1% 列是旧模型，其他列使用相应交易所经验半价差。",
        "",
        "| 标的 | DTE | 固定 1% | Deribit 历史中位/P75 | OKX `_UM` 当前中位/P75 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for base in ("BTC", "ETH"):
        for hours in (24, 72, 168):
            old = fixed.get((base, hours))
            if old is None:
                continue
            values: dict[tuple[str, str], dict[str, Any]] = {}
            for exchange in ("deribit", OKX_CURRENT_EXCHANGE):
                for quantile in ("median", "p75"):
                    item = next((row for row in payload["repricedSummary"] if row["calibration_exchange"] == exchange and row["spread_quantile"] == quantile and row["underlying"] == base and row["sample"] == "test" and row["entry_hours_before_expiry"] == hours and row["target_otm_pct"] == 0 and row["hedge_variant"] == "baseline"), None)
                    if item is not None:
                        values[(exchange, quantile)] = item
            def cell(exchange: str) -> str:
                median = values.get((exchange, "median"))
                p75 = values.get((exchange, "p75"))
                return "n/a" if median is None or p75 is None else f"{median['median_return_on_premium_pct']:.1f}% / {p75['median_return_on_premium_pct']:.1f}%"
            lines.append(f"| {base} | {hours}h | {old['median']:.1f}% ({old['positive']}/{old['count']}) | {cell('deribit')} | {cell(OKX_CURRENT_EXCHANGE)} |")
    lines.extend([
        "",
        "## Delta 10% 候选的执行盈亏平衡",
        "",
        "这是此前样本外最接近盈利的固定候选；盈亏平衡半价差用样本外美元 PnL 曲线求解，不重新选择到期日。",
        "",
        "| 标的 | DTE | 训练期中位收益（固定1%） | 零价差样本外 | 盈亏平衡半价差 | Deribit中位价差回灌 | OKX `_UM` 当前中位回灌 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for edge in payload["executionEdgeSummary"]:
        base = edge["underlying"]
        hours = edge["entry_hours_before_expiry"]
        def repriced_cell(exchange: str) -> str:
            item = next((row for row in payload["repricedSummary"] if row["calibration_exchange"] == exchange and row["spread_quantile"] == "median" and row["underlying"] == base and row["sample"] == "test" and row["entry_hours_before_expiry"] == hours and row["target_otm_pct"] == 0 and row["hedge_variant"] == "threshold10"), None)
            return "n/a" if item is None else f"{item['median_return_on_premium_pct']:.1f}% ({item['positive']}/{item['count']})"
        break_even = edge["break_even_half_spread_bps"]
        break_even_text = "不存在" if break_even is None else ">100%" if math.isinf(break_even) else f"{break_even / 100:.2f}%"
        lines.append(
            f"| {base} | {hours}h | {edge['training_median_fixed_1pct']:.1f}% | {edge['test_zero_cost_median']:.1f}% | {break_even_text} | "
            f"{repriced_cell('deribit')} | {repriced_cell(OKX_CURRENT_EXCHANGE)} |"
        )
    lines.extend([
        "",
        "## 边界",
        "",
        "- Tardis 公开额度在 8 个 Deribit 快照后触发约 24 小时限速；报告只使用已缓存的实际样本，不把未下载月份计入。",
        "- 公开样本只覆盖每月首日的短时间横截面，OKX `_UM` 也只有当前横截面；两者都不等同于完整逐笔盘口路径。",
        "- 回灌对超过 2% 的经验半价差使用线性外推；它适合成本压力测试，不替代真正的 bid/ask 路径回测。",
        "- OKX 样本用于评估目标交易场所的成本水平；原始收益路径仍来自 Deribit 反向期权，不能当成 OKX 可实现收益。",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate BTC/ETH option spreads from public Tardis chain snapshots")
    parser.add_argument("--cache-file", default=str(DEFAULT_CACHE))
    parser.add_argument("--source-trades", default=str(DEFAULT_SOURCE_TRADES))
    parser.add_argument("--output-dir", default="spread-calibrated-20260807")
    parser.add_argument("--date", action="append", dest="dates", default=[])
    parser.add_argument("--cached-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dates = args.dates or list(SAMPLE_DATES)
    cache_path = Path(args.cache_file)
    source_path = Path(args.source_trades)
    historical_snapshots = load_snapshots(cache_path, dates, EXCHANGES, cached_only=args.cached_only)
    okx_current = current_okx_um_snapshot()
    snapshots = historical_snapshots + okx_current
    spread_summary = summarize_spreads(snapshots)
    repriced = reprice_trades(source_path, spread_summary)
    repriced_summary = summarize_repriced(repriced)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_public_tardis_spread_calibration",
        "source": {
            "documentation": "https://docs.tardis.dev/downloadable-csv-files/overview",
            "datasetPattern": f"{TARDIS_DATASETS}/{{exchange}}/options_chain/YYYY/MM/01/OPTIONS.csv.gz",
            "windowSeconds": WINDOW_SECONDS,
            "cacheFile": str(cache_path.resolve()),
            "sourceTrades": str(source_path.resolve()),
        },
        "requestedSampleDates": dates,
        "historicalSamplesByExchange": {
            exchange: len({row["sample_date"] for row in historical_snapshots if row["exchange"] == exchange})
            for exchange in EXCHANGES
            if any(row["exchange"] == exchange for row in historical_snapshots)
        },
        "okxCurrentSampleDate": next((row["sample_date"] for row in okx_current), None),
        "calibrationExchanges": sorted({row["exchange"] for row in snapshots}),
        "snapshotRows": len(snapshots),
        "spreadSummary": spread_summary,
        "repricedSummary": repriced_summary,
        "executionEdgeSummary": execution_edge_summary(source_path),
    }
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = OUTPUT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "repriced_trades.csv", repriced)
    (output_dir / "report.md").write_text(markdown_report(payload, source_path), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"snapshot_rows={len(snapshots)} spread_groups={len(spread_summary)} repriced_rows={len(repriced)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
