"""Read-only contract test of daily-flat execution for the locked QQQ overlay.

The factor model and active weights are not changed.  Historical public OKX
5-minute candles execute the QQQ core and twelve locked stock contracts during
the US regular session.  Public realized funding history is charged whenever a
position crosses a funding timestamp.  No environment, account, private API,
order, or service path exists in this module.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from backtest.okx_grid_backtest import (
    Candle,
    fetch_okx_candle_rows,
    parse_okx_candles,
    read_candles_csv,
    write_candles_csv,
)
from okx_client import OkxRestClient
from tradfi_intraday_factor_research import NEW_YORK, regular_session_date


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "qqq_intraday_flat"
CONTRACT_ROOT = PROJECT_ROOT / "data" / "backtest"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "qqq_intraday_flat"
LOCK_ROOT = PROJECT_ROOT / "reports" / "qqq_active_enhancement" / "qqq-pit-20260808-v5"
LOCKED_MODEL_PATH = LOCK_ROOT / "locked_model.json"
WEIGHTS_PATH = LOCK_ROOT / "monthly_current_liquid_weights.csv"

BAR = "5m"
LIMIT = 300
PAGES = 60
BAR_MILLIS = 300_000
MIN_SESSION_BARS = 72
ENTRY_HOUR = 9
ENTRY_MINUTE = 45
EXIT_HOUR = 15
EXIT_MINUTE = 55
BASE_FEE_BPS_PER_SIDE = 5.0
BASE_SLIPPAGE_BPS_PER_SIDE = 5.0
STRESS_MULTIPLIER = 2.0


@dataclass(frozen=True, slots=True)
class FundingPoint:
    ts: int
    rate: float


@dataclass(frozen=True, slots=True)
class SessionExecution:
    session: str
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only daily-flat execution test for the locked QQQ active overlay."
    )
    parser.add_argument("--locked-model", default=str(LOCKED_MODEL_PATH))
    parser.add_argument("--weights", default=str(WEIGHTS_PATH))
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--contract-root", default=str(CONTRACT_ROOT))
    parser.add_argument("--pages", type=int, default=PAGES)
    parser.add_argument("--fetch-missing-contracts", action="store_true")
    parser.add_argument("--refresh-contracts", action="store_true")
    parser.add_argument("--refresh-funding", action="store_true")
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def resolve_output_dir(value: str) -> Path:
    if value:
        return Path(value)
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("daily-flat-%Y%m%dT%H%M%SZ")


def contract_cache_path(root: Path, contract: str, pages: int) -> Path:
    return root / f"{contract}_{BAR}_{LIMIT}x{pages}.csv"


def load_contract_candles(
    contract: str,
    root: Path,
    *,
    pages: int,
    fetch_missing: bool,
    refresh: bool,
) -> list[Candle]:
    path = contract_cache_path(root, contract, pages)
    if path.exists() and not refresh:
        return read_candles_csv(path)
    if not fetch_missing and not refresh:
        raise FileNotFoundError(f"Missing public contract cache: {path}")
    client = OkxRestClient()
    candles = parse_okx_candles(fetch_okx_candle_rows(client, contract, BAR, LIMIT, pages))
    if len(candles) < MIN_SESSION_BARS:
        raise ValueError(f"Only {len(candles)} candles returned for {contract}")
    write_candles_csv(path, candles)
    return candles


def funding_cache_path(data_root: Path, contract: str) -> Path:
    return data_root / "funding" / f"{contract}_funding.csv"


def read_funding_csv(path: Path) -> list[FundingPoint]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            FundingPoint(ts=int(row["ts"]), rate=float(row["rate"]))
            for row in csv.DictReader(handle)
            if row.get("ts") and row.get("rate")
        ]


def write_funding_csv(path: Path, points: Sequence[FundingPoint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("ts", "time", "rate"))
        writer.writeheader()
        for point in points:
            writer.writerow(
                {
                    "ts": point.ts,
                    "time": datetime.fromtimestamp(point.ts / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "rate": f"{point.rate:.12f}",
                }
            )


def fetch_funding_history(contract: str, *, pages: int = 6) -> list[FundingPoint]:
    client = OkxRestClient()
    after = ""
    points: dict[int, FundingPoint] = {}
    for _ in range(pages):
        params = {"instId": contract, "limit": "100"}
        if after:
            params["after"] = after
        rows = client.request("GET", "/api/v5/public/funding-rate-history", params=params).get("data", [])
        if not rows:
            break
        for row in rows:
            timestamp = int(row.get("fundingTime") or 0)
            if timestamp > 0:
                realized_value = row.get("realizedRate")
                rate = (
                    number(realized_value)
                    if realized_value not in (None, "")
                    else number(row.get("fundingRate"))
                )
                points[timestamp] = FundingPoint(timestamp, rate)
        oldest = min(point.ts for point in points.values())
        next_after = str(oldest - 1)
        if next_after == after:
            break
        after = next_after
        time.sleep(0.12)
    return sorted(points.values(), key=lambda item: item.ts)


def load_funding_history(contract: str, data_root: Path, *, refresh: bool) -> list[FundingPoint]:
    path = funding_cache_path(data_root, contract)
    if path.exists() and not refresh:
        return read_funding_csv(path)
    points = fetch_funding_history(contract)
    write_funding_csv(path, points)
    return points


def local_clock(candle: Candle) -> tuple[int, int]:
    value = datetime.fromtimestamp(candle.ts / 1000, timezone.utc).astimezone(NEW_YORK)
    return value.hour, value.minute


def executable_sessions(candles: Sequence[Candle]) -> dict[str, SessionExecution]:
    grouped: dict[str, list[Candle]] = {}
    for candle in candles:
        session = regular_session_date(candle.ts)
        if session:
            grouped.setdefault(session, []).append(candle)
    result: dict[str, SessionExecution] = {}
    for session, rows in grouped.items():
        rows.sort(key=lambda item: item.ts)
        if len(rows) < MIN_SESSION_BARS:
            continue
        entry = next((row for row in rows if local_clock(row) >= (ENTRY_HOUR, ENTRY_MINUTE)), None)
        exits = [row for row in rows if local_clock(row) <= (EXIT_HOUR, EXIT_MINUTE)]
        if entry is None or not exits:
            continue
        exit_candle = exits[-1]
        if local_clock(exit_candle) != (EXIT_HOUR, EXIT_MINUTE) or exit_candle.ts <= entry.ts:
            continue
        result[session] = SessionExecution(
            session=session,
            entry_ts=entry.ts,
            exit_ts=exit_candle.ts + BAR_MILLIS,
            entry_price=float(entry.open),
            exit_price=float(exit_candle.close),
        )
    return result


def shared_sessions(sessions: dict[str, dict[str, SessionExecution]]) -> list[str]:
    common: set[str] | None = None
    for rows in sessions.values():
        common = set(rows) if common is None else common & set(rows)
    return sorted(common or set())


def chronological_splits(values: Sequence[str]) -> dict[str, list[str]]:
    first = int(len(values) * 0.50)
    second = int(len(values) * 0.75)
    return {
        "train": list(values[:first]),
        "validation": list(values[first:second]),
        "test": list(values[second:]),
        "full": list(values),
    }


def load_weight_history(path: Path, symbols: Sequence[str]) -> dict[date, dict[str, float]]:
    grouped: dict[date, dict[str, float]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            signal_date = date.fromisoformat(row["signalDate"])
            grouped.setdefault(signal_date, {symbol: 0.0 for symbol in symbols})
            symbol = row["symbol"]
            if symbol in grouped[signal_date]:
                grouped[signal_date][symbol] = float(row["activeWeight"])
    return grouped


def weights_strictly_before(
    session: str,
    history: dict[date, dict[str, float]],
) -> tuple[date, dict[str, float]] | None:
    session_date = date.fromisoformat(session)
    dates = sorted(history)
    index = bisect_left(dates, session_date) - 1
    if index < 0:
        return None
    signal_date = dates[index]
    return signal_date, dict(history[signal_date])


def funding_pnl(
    points: Sequence[FundingPoint],
    start_ts: int,
    end_ts: int,
    weight: float,
) -> float:
    # Positive funding is paid by longs and received by shorts.
    return -weight * sum(point.rate for point in points if start_ts <= point.ts < end_ts)


def build_raw_session_frame(
    session_dates: Sequence[str],
    stock_symbols: Sequence[str],
    sessions: dict[str, dict[str, SessionExecution]],
    funding: dict[str, list[FundingPoint]],
    weight_history: dict[date, dict[str, float]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    previous_execution: dict[str, SessionExecution] | None = None
    previous_weights = {symbol: 0.0 for symbol in stock_symbols}
    for session in session_dates:
        selected = weights_strictly_before(session, weight_history)
        if selected is None:
            continue
        signal_date, current_weights = selected
        execution = {symbol: sessions[symbol][session] for symbol in ["QQQ", *stock_symbols]}
        intraday_returns = {
            symbol: item.exit_price / item.entry_price - 1.0
            for symbol, item in execution.items()
        }
        active_gross = sum(abs(current_weights[symbol]) for symbol in stock_symbols)
        flat_active_gross_return = sum(
            current_weights[symbol] * intraday_returns[symbol] for symbol in stock_symbols
        )
        flat_active_funding = sum(
            funding_pnl(
                funding[symbol],
                execution[symbol].entry_ts,
                execution[symbol].exit_ts,
                current_weights[symbol],
            )
            for symbol in stock_symbols
        )
        flat_core_funding = funding_pnl(
            funding["QQQ"],
            execution["QQQ"].entry_ts,
            execution["QQQ"].exit_ts,
            1.0,
        )

        if previous_execution is None:
            overnight_returns = {symbol: 0.0 for symbol in execution}
            continuous_active_gross_return = flat_active_gross_return
            continuous_core_gross_return = intraday_returns["QQQ"]
            continuous_active_funding = flat_active_funding
            continuous_core_funding = flat_core_funding
            continuous_active_turnover = active_gross
            continuous_core_turnover = 1.0
        else:
            overnight_returns = {
                symbol: execution[symbol].entry_price / previous_execution[symbol].exit_price - 1.0
                for symbol in execution
            }
            continuous_active_gross_return = sum(
                previous_weights[symbol] * overnight_returns[symbol]
                + current_weights[symbol] * intraday_returns[symbol]
                for symbol in stock_symbols
            )
            continuous_core_gross_return = (
                execution["QQQ"].exit_price / previous_execution["QQQ"].exit_price - 1.0
            )
            continuous_active_funding = sum(
                funding_pnl(
                    funding[symbol],
                    previous_execution[symbol].exit_ts,
                    execution[symbol].entry_ts,
                    previous_weights[symbol],
                )
                + funding_pnl(
                    funding[symbol],
                    execution[symbol].entry_ts,
                    execution[symbol].exit_ts,
                    current_weights[symbol],
                )
                for symbol in stock_symbols
            )
            continuous_core_funding = funding_pnl(
                funding["QQQ"],
                previous_execution["QQQ"].exit_ts,
                execution["QQQ"].exit_ts,
                1.0,
            )
            continuous_active_turnover = sum(
                abs(current_weights[symbol] - previous_weights[symbol]) for symbol in stock_symbols
            )
            continuous_core_turnover = 0.0

        rows.append(
            {
                "session": session,
                "signalDate": signal_date.isoformat(),
                "entryTime": datetime.fromtimestamp(
                    execution["QQQ"].entry_ts / 1000, timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "exitTime": datetime.fromtimestamp(
                    execution["QQQ"].exit_ts / 1000, timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "activeGross": active_gross,
                "flatActiveGrossReturn": flat_active_gross_return,
                "flatCoreGrossReturn": intraday_returns["QQQ"],
                "flatActiveFunding": flat_active_funding,
                "flatCoreFunding": flat_core_funding,
                "flatActiveTurnover": 2.0 * active_gross,
                "flatCoreTurnover": 2.0,
                "continuousActiveGrossReturn": continuous_active_gross_return,
                "continuousCoreGrossReturn": continuous_core_gross_return,
                "continuousActiveFunding": continuous_active_funding,
                "continuousCoreFunding": continuous_core_funding,
                "continuousActiveTurnover": continuous_active_turnover,
                "continuousCoreTurnover": continuous_core_turnover,
                "activeIntradayReturn": flat_active_gross_return,
                "activeOvernightReturn": sum(
                    previous_weights[symbol] * overnight_returns[symbol] for symbol in stock_symbols
                ),
                "qqqIntradayReturn": intraday_returns["QQQ"],
                "qqqOvernightReturn": overnight_returns["QQQ"],
            }
        )
        previous_execution = execution
        previous_weights = current_weights
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    # Close the continuously held book at the end of the observed sample.
    last_index = frame.index[-1]
    frame.loc[last_index, "continuousActiveTurnover"] += sum(abs(value) for value in previous_weights.values())
    frame.loc[last_index, "continuousCoreTurnover"] += 1.0
    return frame.set_index("session")


def apply_costs(raw: pd.DataFrame, *, cost_bps_per_side: float) -> pd.DataFrame:
    frame = raw.copy()
    cost_rate = cost_bps_per_side / 10_000.0
    for mode in ("flat", "continuous"):
        prefix = "flat" if mode == "flat" else "continuous"
        active_cost = frame[f"{prefix}ActiveTurnover"] * cost_rate
        core_cost = frame[f"{prefix}CoreTurnover"] * cost_rate
        frame[f"{prefix}ActiveCost"] = active_cost
        frame[f"{prefix}CoreCost"] = core_cost
        frame[f"{prefix}ActiveNetReturn"] = (
            frame[f"{prefix}ActiveGrossReturn"] + frame[f"{prefix}ActiveFunding"] - active_cost
        )
        frame[f"{prefix}CoreNetReturn"] = (
            frame[f"{prefix}CoreGrossReturn"] + frame[f"{prefix}CoreFunding"] - core_cost
        )
        frame[f"{prefix}PortfolioReturn"] = (
            frame[f"{prefix}ActiveNetReturn"] + frame[f"{prefix}CoreNetReturn"]
        )
    return frame


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    if equity.empty:
        return 0.0
    drawdown = equity / equity.cummax() - 1.0
    return float(-drawdown.min())


def result_metrics(frame: pd.DataFrame, mode: str) -> dict[str, Any]:
    if frame.empty:
        return {}
    prefix = "flat" if mode == "flat" else "continuous"
    active = frame[f"{prefix}ActiveNetReturn"]
    core = frame[f"{prefix}CoreNetReturn"]
    portfolio = frame[f"{prefix}PortfolioReturn"]
    days = len(frame)
    active_ann = float(active.mean() * 252.0)
    tracking_error = float(active.std(ddof=1) * math.sqrt(252.0)) if days > 1 else 0.0
    total = float((1.0 + portfolio).prod() - 1.0)
    core_total = float((1.0 + core).prod() - 1.0)
    years = days / 252.0
    annual = (1.0 + total) ** (1.0 / years) - 1.0 if years > 0 and total > -1 else -1.0
    core_annual = (1.0 + core_total) ** (1.0 / years) - 1.0 if years > 0 and core_total > -1 else -1.0
    return {
        "sessions": days,
        "start": str(frame.index[0]),
        "end": str(frame.index[-1]),
        "activeCumulativePct": float((1.0 + active).prod() - 1.0) * 100.0,
        "activeAnnualizedPct": active_ann * 100.0,
        "trackingErrorPct": tracking_error * 100.0,
        "informationRatio": active_ann / tracking_error if tracking_error > 0 else 0.0,
        "coreCumulativePct": core_total * 100.0,
        "coreAnnualizedPct": core_annual * 100.0,
        "portfolioCumulativePct": total * 100.0,
        "portfolioAnnualizedPct": annual * 100.0,
        "portfolioVolatilityPct": float(portfolio.std(ddof=1) * math.sqrt(252.0) * 100.0) if days > 1 else 0.0,
        "portfolioMaxDrawdownPct": max_drawdown(portfolio) * 100.0,
        "activeTradingCostPct": float(frame[f"{prefix}ActiveCost"].sum() * 100.0),
        "coreTradingCostPct": float(frame[f"{prefix}CoreCost"].sum() * 100.0),
        "activeFundingPct": float(frame[f"{prefix}ActiveFunding"].sum() * 100.0),
        "coreFundingPct": float(frame[f"{prefix}CoreFunding"].sum() * 100.0),
        "averageActiveGrossPct": float(frame["activeGross"].mean() * 100.0),
    }


def segmented_metrics(frame: pd.DataFrame, splits: dict[str, list[str]], mode: str) -> dict[str, Any]:
    return {
        name: result_metrics(frame.loc[dates], mode)
        for name, dates in splits.items()
        if dates
    }


def decomposition_metrics(raw: pd.DataFrame, dates: Sequence[str]) -> dict[str, float]:
    frame = raw.loc[list(dates)]
    return {
        "activeIntradayAnnualizedPct": float(frame["activeIntradayReturn"].mean() * 252.0 * 100.0),
        "activeOvernightAnnualizedPct": float(frame["activeOvernightReturn"].mean() * 252.0 * 100.0),
        "qqqIntradayAnnualizedPct": float(frame["qqqIntradayReturn"].mean() * 252.0 * 100.0),
        "qqqOvernightAnnualizedPct": float(frame["qqqOvernightReturn"].mean() * 252.0 * 100.0),
    }


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label="session")


def markdown_report(payload: dict[str, Any]) -> str:
    def pct(value: Any) -> str:
        return f"{number(value):.3f}%"

    lines = [
        "# QQQ 主动增强：每日决策、日内平仓合约测试",
        "",
        "> 只读研究。固定既有月频因子权重，只把执行改成每天 09:45 ET 入场、15:55 K线收盘退出。全部收益来自 OKX 公共合约 5m K线，资金费使用公共历史 realized rate；未访问账户、未下单、未改实盘配置。",
        "",
        "## 固定执行",
        "",
        "- 信号：沿用锁定模型，不重算或调参；每个交易日只使用严格早于当日的最近完成月末权重。",
        "- 日内版本：09:45 ET 合约 K 线开盘成交，15:55 ET K 线收盘成交，每日全部平仓。",
        "- 连续持有对照：QQQ 核心和主动 overlay 跨夜，只在月末权重变化时再平衡；首尾样本各计一次开平成本。",
        "- 基础成本：每边 5 bps 手续费 + 5 bps 不利滑点；压力成本翻倍。日内持仓跨过 16:00 UTC 资金费时仍按实际历史费率结算。",
        "",
        "## 数据覆盖",
        "",
        f"- 冻结模型：`{payload['modelId']}`；股票合约 {len(payload['symbols'])} 只，加 QQQ 共 {len(payload['symbols']) + 1} 只。",
        f"- 所有合约共同完整 RTH 交易日：{payload['period']['commonSessions']}，从 {payload['period']['start']} 至 {payload['period']['end']}。",
        f"- 顺序切分：训练 {payload['period']['splitCounts']['train']}、验证 {payload['period']['splitCounts']['validation']}、测试 {payload['period']['splitCounts']['test']} 日。",
        "",
        "## 日内平仓与连续持有",
        "",
        "| 成本 | 持有方式 | 区间 | 主动累计 | 主动年化 | TE | IR | 核心累计 | 组合累计 | 主动交易成本 | 核心交易成本 | 主动资金费 | 核心资金费 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in ("base", "stress"):
        for mode in ("flat", "continuous"):
            for segment in ("train", "validation", "test", "full"):
                item = payload["results"][variant][mode][segment]
                lines.append(
                    f"| {variant} | {mode} | {segment} | {pct(item['activeCumulativePct'])} | "
                    f"{pct(item['activeAnnualizedPct'])} | {pct(item['trackingErrorPct'])} | "
                    f"{item['informationRatio']:.3f} | {pct(item['coreCumulativePct'])} | "
                    f"{pct(item['portfolioCumulativePct'])} | {pct(item['activeTradingCostPct'])} | "
                    f"{pct(item['coreTradingCostPct'])} | {pct(item['activeFundingPct'])} | "
                    f"{pct(item['coreFundingPct'])} |"
                )
    decomposition = payload["decomposition"]
    comparison = payload["comparison"]
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 收益来源与资金费/成本交换",
            "",
            f"- 测试期主动日内毛收益年化：{pct(decomposition['test']['activeIntradayAnnualizedPct'])}；主动隔夜毛收益年化：{pct(decomposition['test']['activeOvernightAnnualizedPct'])}。",
            f"- 测试期 QQQ 日内毛收益年化：{pct(decomposition['test']['qqqIntradayAnnualizedPct'])}；QQQ 隔夜毛收益年化：{pct(decomposition['test']['qqqOvernightAnnualizedPct'])}。",
            f"- 全样本每日平仓相对连续持有节省资金费：主动 {pct(comparison['activeFundingSavedPct'])}、QQQ 核心 {pct(comparison['coreFundingSavedPct'])}。",
            f"- 但额外交易成本：主动 {pct(comparison['extraActiveTradingCostPct'])}、QQQ 核心 {pct(comparison['extraCoreTradingCostPct'])}。",
            "",
            "## 判定",
            "",
            f"- 日内主动 overlay 在测试期基础/压力成本后均为正：`{decision['positiveTestAfterBaseAndStress']}`。",
            f"- 日内主动 overlay 在全样本基础/压力成本后均为正：`{decision['positiveFullAfterBaseAndStress']}`。",
            f"- 每日同时平掉 QQQ 核心是否优于连续持有：`{decision['flatFullBookBeatsContinuous']}`。",
            f"- 状态：`{decision['status']}`；{decision['reason']}",
            "",
            "## 边界",
            "",
            "- 所有合约共同样本很短，测试段只有约十余个交易日；结果只能回答当前合约窗口，不能替代一年以上前瞻样本。",
            "- 5m OHLC 不能恢复盘口深度、排队或精确成交；每日两次交易的真实成本可能高于假设。",
            "- 日内持仓跨过 16:00 UTC 资金费，并非零资金费；若刻意在结算前后平开，会再增加成交成本和缺口风险。",
            "- 当前权重来自今天冻结的可执行子集，仍有当前流动性选择偏差。任何日内化结论都是新执行模型，不能改写原隔夜模型的历史结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    locked_model = json.loads(Path(args.locked_model).read_text(encoding="utf-8"))
    if locked_model.get("paperOrLiveAuthorized") is not False:
        raise RuntimeError("Locked model must explicitly remain unauthorized for paper/live trading")
    stock_symbols = list(locked_model["basis"]["symbols"])
    contracts = {symbol: f"{symbol}-USDT-SWAP" for symbol in ["QQQ", *stock_symbols]}
    contract_root = Path(args.contract_root)
    data_root = Path(args.data_root)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candles: dict[str, list[Candle]] = {}
    sessions: dict[str, dict[str, SessionExecution]] = {}
    coverage_rows: list[dict[str, Any]] = []
    for symbol, contract in contracts.items():
        rows = load_contract_candles(
            contract,
            contract_root,
            pages=args.pages,
            fetch_missing=args.fetch_missing_contracts,
            refresh=args.refresh_contracts,
        )
        executable = executable_sessions(rows)
        if not executable:
            raise RuntimeError(f"No complete RTH sessions for {contract}")
        candles[symbol] = rows
        sessions[symbol] = executable
        coverage_rows.append(
            {
                "symbol": symbol,
                "contract": contract,
                "candles": len(rows),
                "firstCandle": datetime.fromtimestamp(rows[0].ts / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lastCandle": datetime.fromtimestamp(rows[-1].ts / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "completeRthSessions": len(executable),
                "firstSession": min(executable),
                "lastSession": max(executable),
            }
        )

    funding: dict[str, list[FundingPoint]] = {}
    funding_rows: list[dict[str, Any]] = []
    for symbol, contract in contracts.items():
        points = load_funding_history(contract, data_root, refresh=args.refresh_funding)
        funding[symbol] = points
        funding_rows.append(
            {
                "symbol": symbol,
                "contract": contract,
                "points": len(points),
                "firstFunding": datetime.fromtimestamp(points[0].ts / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if points else "",
                "lastFunding": datetime.fromtimestamp(points[-1].ts / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if points else "",
                "meanRateBps": statistics.fmean(point.rate for point in points) * 10_000.0 if points else 0.0,
                "maxAbsRateBps": max(abs(point.rate) for point in points) * 10_000.0 if points else 0.0,
            }
        )

    common = shared_sessions(sessions)
    if len(common) < 20:
        raise RuntimeError(f"Only {len(common)} common complete contract sessions")
    weights = load_weight_history(Path(args.weights), stock_symbols)
    raw = build_raw_session_frame(common, stock_symbols, sessions, funding, weights)
    valid_sessions = list(raw.index)
    splits = chronological_splits(valid_sessions)
    base_cost = BASE_FEE_BPS_PER_SIDE + BASE_SLIPPAGE_BPS_PER_SIDE
    cost_variants = {
        "base": base_cost,
        "stress": base_cost * STRESS_MULTIPLIER,
    }
    costed: dict[str, pd.DataFrame] = {
        name: apply_costs(raw, cost_bps_per_side=value) for name, value in cost_variants.items()
    }
    results = {
        variant: {
            mode: segmented_metrics(frame, splits, mode)
            for mode in ("flat", "continuous")
        }
        for variant, frame in costed.items()
    }
    decomposition = {
        name: decomposition_metrics(raw, dates)
        for name, dates in splits.items()
        if dates
    }
    flat_base_full = results["base"]["flat"]["full"]
    continuous_base_full = results["base"]["continuous"]["full"]
    comparison = {
        "activeFundingSavedPct": flat_base_full["activeFundingPct"] - continuous_base_full["activeFundingPct"],
        "coreFundingSavedPct": flat_base_full["coreFundingPct"] - continuous_base_full["coreFundingPct"],
        "extraActiveTradingCostPct": flat_base_full["activeTradingCostPct"] - continuous_base_full["activeTradingCostPct"],
        "extraCoreTradingCostPct": flat_base_full["coreTradingCostPct"] - continuous_base_full["coreTradingCostPct"],
        "flatMinusContinuousPortfolioCumulativePct": (
            flat_base_full["portfolioCumulativePct"] - continuous_base_full["portfolioCumulativePct"]
        ),
    }
    test_flat_base = results["base"]["flat"]["test"]
    test_flat_stress = results["stress"]["flat"]["test"]
    full_flat_base = results["base"]["flat"]["full"]
    full_flat_stress = results["stress"]["flat"]["full"]
    checks = {
        "positiveTestAfterBaseAndStress": (
            test_flat_base["activeCumulativePct"] > 0 and test_flat_stress["activeCumulativePct"] > 0
        ),
        "positiveFullAfterBaseAndStress": (
            full_flat_base["activeCumulativePct"] > 0 and full_flat_stress["activeCumulativePct"] > 0
        ),
        "flatFullBookBeatsContinuous": (
            flat_base_full["portfolioCumulativePct"] > continuous_base_full["portfolioCumulativePct"]
        ),
    }
    if checks["positiveTestAfterBaseAndStress"] and checks["positiveFullAfterBaseAndStress"]:
        reason = (
            "日内主动 overlay 在这个短合约窗口内保留了成本后 alpha；只能进入独立的新日内前瞻样本，不能替代原锁定隔夜模型或直接仿真/实盘。"
        )
    else:
        reason = (
            "每日开平后主动 alpha 未能同时通过全样本和测试期成本压力；节省资金费不足以补偿丢失收益与新增交易成本，应停止日内化方案。"
        )
    decision = {
        "status": "research_only",
        **checks,
        "eligibleForPaperOrLive": False,
        "reason": reason,
    }
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_locked_qqq_daily_flat_contract_execution",
        "modelId": locked_model["modelId"],
        "sourceSignalDate": locked_model["latestSignalDate"],
        "symbols": stock_symbols,
        "config": {
            "entryNyTime": f"{ENTRY_HOUR:02d}:{ENTRY_MINUTE:02d}",
            "exitNyTime": f"{EXIT_HOUR:02d}:{EXIT_MINUTE:02d}",
            "bar": BAR,
            "contractPages": args.pages,
            "baseFeeBpsPerSide": BASE_FEE_BPS_PER_SIDE,
            "baseSlippageBpsPerSide": BASE_SLIPPAGE_BPS_PER_SIDE,
            "stressMultiplier": STRESS_MULTIPLIER,
            "fundingRule": "public_realized_rate_when_entry_ts_lte_funding_ts_lt_exit_ts",
            "signalRule": "latest_completed_month_end_strictly_before_session",
        },
        "period": {
            "commonSessions": len(valid_sessions),
            "start": valid_sessions[0],
            "end": valid_sessions[-1],
            "splits": splits,
            "splitCounts": {name: len(values) for name, values in splits.items()},
        },
        "contractCoverage": coverage_rows,
        "fundingCoverage": funding_rows,
        "results": results,
        "decomposition": decomposition,
        "comparison": comparison,
        "decision": decision,
        "limitations": [
            "short_common_contract_history",
            "five_minute_ohlc_has_no_historical_spread_depth_or_queue",
            "current_liquidity_selected_universe",
            "daily_rth_position_still_crosses_1600_utc_funding",
            "no_account_order_or_live_authorization",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "raw_session_returns.csv", raw)
    for variant, frame in costed.items():
        write_csv(output_dir / f"{variant}_session_returns.csv", frame)
    pd.DataFrame(coverage_rows).to_csv(output_dir / "contract_coverage.csv", index=False)
    pd.DataFrame(funding_rows).to_csv(output_dir / "funding_coverage.csv", index=False)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"common_sessions={len(valid_sessions)} period={valid_sessions[0]}..{valid_sessions[-1]}")
    print(f"decision={json.dumps(decision, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
