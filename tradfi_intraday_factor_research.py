"""Read-only factor research for liquid OKX TRADFI stock contracts.

Signals are calculated solely from public US-underlying 5-minute or daily
OHLCV data. Orders are valued on the matching OKX perpetual contract candle.
Positions are only held during the NYSE regular session and are flattened
every session. This module has no account, private API, order, or service-start
path.
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
from datetime import date, datetime, time as clock_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from backtest.okx_grid_backtest import (
    Candle,
    fetch_okx_candle_rows,
    iso_time,
    parse_okx_candles,
    read_candles_csv,
    write_candles_csv,
)
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "tradfi_intraday"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "tradfi_intraday_factors"
NEW_YORK = ZoneInfo("America/New_York")
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# These names have an unambiguous US-listed underlying and an existing local
# public OKX candle cache.  SKHYNIX/SKHY are intentionally excluded because a
# matching US 5-minute underlying cannot be established without a vendor map.
DEFAULT_UNIVERSE = {
    "SOXL": "SOXL-USDT-SWAP",
    "NVDA": "NVDA-USDT-SWAP",
    "AMD": "AMD-USDT-SWAP",
    "MU": "MU-USDT-SWAP",
    "SNDK": "SNDK-USDT-SWAP",
    "TSM": "TSM-USDT-SWAP",
}

# Fixed before inspecting this experiment.  This is the same 1:2:4:8
# multi-horizon momentum shape used by the existing signal research, compressed
# to 15m--2h so both features and positions fit within one US cash session.
LOOKBACK_BARS = (3, 6, 12, 24)
VOLATILITY_BARS = 12
THRESHOLD_SIGMA = 0.10
MIN_VOTES = 2
YAHOO_INTERVAL = "5m"
YAHOO_RANGE = "60d"
MIN_FULL_SESSION_BARS = 72
MIN_RESEARCH_SESSIONS = 20
MIN_HISTORICAL_COVERAGE_SESSIONS = 40
SLOW_LOOKBACK_DAYS = (20, 60, 120)
SLOW_VOLATILITY_DAYS = 20
SLOW_YAHOO_INTERVAL = "1d"
SLOW_YAHOO_RANGE = "10y"


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    contract: str
    session: str
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    notional: float
    net_pnl: float
    exit_reason: str


@dataclass(frozen=True, slots=True)
class SimulationResult:
    return_pct: float
    profit_factor: float
    max_drawdown_pct: float
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    fees: float
    exposure_pct: float
    sessions: int
    final_equity: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only RTH factor research: Yahoo underlying signals, OKX TRADFI contract execution."
    )
    parser.add_argument("--symbol", action="append", default=[], help="US ticker, repeatable; defaults to liquid mapped universe")
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--contract-data-root", default=str(PROJECT_ROOT / "data" / "backtest"))
    parser.add_argument("--contract-limit", type=int, default=300)
    parser.add_argument("--contract-pages", type=int, default=30)
    parser.add_argument("--factor-mode", choices=("intraday", "slow_daily"), default="intraday")
    parser.add_argument("--refresh-underlyings", action="store_true")
    parser.add_argument("--refresh-contracts", action="store_true", help="Refresh public OKX candle caches; never uses account endpoints")
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--allocation-pct", type=float, default=20.0)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--fee-bps-per-side", type=float, default=5.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=5.0)
    parser.add_argument("--cost-stress-multiplier", type=float, default=2.0)
    parser.add_argument("--min-quote-turnover-usdt", type=float, default=5_000_000.0)
    parser.add_argument("--max-current-spread-bps", type=float, default=5.0)
    parser.add_argument("--min-sessions", type=int, default=MIN_RESEARCH_SESSIONS)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = tuple(dict.fromkeys(symbol.upper() for symbol in (args.symbol or list(DEFAULT_UNIVERSE))))
    unknown = [symbol for symbol in symbols if symbol not in DEFAULT_UNIVERSE]
    if unknown:
        raise SystemExit(f"No unambiguous contract mapping for: {unknown}")

    liquidity = fetch_contract_liquidity(
        {symbol: DEFAULT_UNIVERSE[symbol] for symbol in symbols},
        min_quote_turnover_usdt=args.min_quote_turnover_usdt,
        max_spread_bps=args.max_current_spread_bps,
    )
    eligible_symbols = tuple(symbol for symbol in symbols if liquidity[symbol]["eligible"])
    if len(eligible_symbols) < 3:
        raise SystemExit(f"Need at least 3 currently liquid TRADFI contracts, found {len(eligible_symbols)}")

    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_root = Path(args.data_root)
    contract_root = Path(args.contract_data_root)
    data_root.mkdir(parents=True, exist_ok=True)
    slow_daily = args.factor_mode == "slow_daily"

    instruments: dict[str, dict[str, Any]] = {}
    for symbol in eligible_symbols:
        contract = DEFAULT_UNIVERSE[symbol]
        underlying = load_or_download_yahoo_candles(
            symbol,
            data_root,
            refresh=args.refresh_underlyings,
            interval=SLOW_YAHOO_INTERVAL if slow_daily else YAHOO_INTERVAL,
            history_range=SLOW_YAHOO_RANGE if slow_daily else YAHOO_RANGE,
        )
        contract_candles = load_contract_candles(
            contract,
            contract_root,
            limit=args.contract_limit,
            pages=args.contract_pages,
            refresh=args.refresh_contracts,
        )
        if slow_daily:
            sessions, diagnostics = contract_regular_sessions(contract_candles)
            diagnostics["dailySignalBars"] = len(underlying)
        else:
            sessions, diagnostics = matched_regular_sessions(underlying, contract_candles)
        instruments[symbol] = {
            "contract": contract,
            "sessions": sessions,
            "diagnostics": diagnostics,
            "underlyingBars": len(underlying),
            "contractBars": len(contract_candles),
            "dailySides": slow_daily_sides(underlying, sorted(sessions)) if slow_daily else {},
        }

    shared_sessions = shared_session_dates(instruments)
    for instrument in instruments.values():
        instrument["sessions"] = {
            key: rows for key, rows in instrument["sessions"].items() if key in shared_sessions
        }
        if slow_daily:
            instrument["dailySides"] = {
                key: side for key, side in instrument["dailySides"].items() if key in shared_sessions
            }
    splits = chronological_splits(shared_sessions)
    executions = {
        "base": {
            "fee_bps_per_side": args.fee_bps_per_side,
            "slippage_bps_per_side": args.slippage_bps_per_side,
        },
        "cost_stress": {
            "fee_bps_per_side": args.fee_bps_per_side * args.cost_stress_multiplier,
            "slippage_bps_per_side": args.slippage_bps_per_side * args.cost_stress_multiplier,
        },
    }
    rows: list[dict[str, Any]] = []
    test_trades: list[dict[str, Any]] = []
    for symbol, item in instruments.items():
        for segment, session_dates in splits.items():
            session_rows = [item["sessions"][value] for value in session_dates]
            session_sides = (
                {value: item["dailySides"].get(value, 0) for value in session_dates}
                if slow_daily
                else None
            )
            for variant, costs in executions.items():
                if variant == "cost_stress" and segment not in {"test", "full"}:
                    continue
                result, trades = simulate_sessions(
                    symbol=symbol,
                    contract=item["contract"],
                    sessions=session_rows,
                    starting_equity=args.starting_equity,
                    allocation_pct=args.allocation_pct,
                    leverage=args.leverage,
                    fee_bps_per_side=costs["fee_bps_per_side"],
                    slippage_bps_per_side=costs["slippage_bps_per_side"],
                    session_sides=session_sides,
                )
                rows.append(result_row(symbol, item["contract"], segment, variant, result))
                if segment == "test" and variant == "base":
                    test_trades.extend(asdict(trade) for trade in trades)

    decision = decision_payload(rows, len(shared_sessions), args.min_sessions)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": f"read_only_tradfi_rth_{args.factor_mode}_momentum",
        "factorMode": args.factor_mode,
        "instruments": {
            symbol: {
                "contract": item["contract"],
                "underlyingBars": item["underlyingBars"],
                "contractBars": item["contractBars"],
                "matchedSessions": len(item["sessions"]),
                "alignment": item["diagnostics"],
                "dailySides": item["dailySides"],
            }
            for symbol, item in instruments.items()
        },
        "liquidityScreen": liquidity,
        "dataDefinition": {
            "signalSource": (
                "Yahoo Finance public chart endpoint, daily US-underlying OHLCV"
                if slow_daily
                else "Yahoo Finance public chart endpoint, 5-minute US-underlying OHLCV"
            ),
            "executionSource": "locally cached public OKX TRADFI perpetual 5-minute OHLCV",
            "signalSourceLimit": (
                "Yahoo daily history is long enough for slow-factor warmup but remains a public, non-institutional source"
                if slow_daily
                else "Yahoo supplies at most roughly 60 calendar days for 5-minute history"
            ),
            "executionLimitation": "OHLC cannot recreate OKX bid/ask, queue priority, historical spread, or liquidation fills",
            "alignment": (
                "each session uses the most recent completed underlying daily close strictly before that session; contract execution remains a complete NYSE RTH session"
                if slow_daily
                else "only exact matching 5-minute timestamps inside a complete NYSE regular session are used"
            ),
            "contractEligibility": "current public OKX snapshot requires live instCategory=3, configured maximum spread, and configured 24-hour quote turnover",
        },
        "strategyDefinition": {
            "factor": (
                "lagged volatility-normalized 20/60/120-day multi-horizon time-series momentum"
                if slow_daily
                else "lagged volatility-normalized multi-horizon time-series momentum"
            ),
            "lookbackBars": list(SLOW_LOOKBACK_DAYS if slow_daily else LOOKBACK_BARS),
            "barMinutes": 1440 if slow_daily else 5,
            "thresholdSigma": THRESHOLD_SIGMA,
            "minVotes": MIN_VOTES,
            "sourceRule": (
                "each session uses only the underlying daily close available before that session; the daily state persists through a vote dead zone"
                if slow_daily
                else "signal for bar i uses underlying closes through i-1 only and resets at every session"
            ),
            "sessionRule": "NYSE regular session only; entry is next contract-bar open; every position is flattened at the final regular-session close",
            "selectionRule": "fixed parameters; no symbol-specific or post-test parameter selection",
        },
        "period": {
            "sharedSessionDates": shared_sessions,
            "splits": splits,
        },
        "execution": {
            "startingEquity": args.starting_equity,
            "allocationPct": args.allocation_pct,
            "leverage": args.leverage,
            "base": executions["base"],
            "costStress": executions["cost_stress"],
            "minQuoteTurnoverUsdt": args.min_quote_turnover_usdt,
            "maxCurrentSpreadBps": args.max_current_spread_bps,
        },
        "rows": rows,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "test_trades.csv", test_trades)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"shared_sessions={len(shared_sessions)}")
    print(f"decision={decision}")
    return 0


def resolve_output_dir(value: str) -> Path:
    if value:
        return Path(value)
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("tradfi-rth-%Y%m%dT%H%M%SZ")


def yahoo_cache_path(data_root: Path, symbol: str, *, interval: str, history_range: str) -> Path:
    return data_root / f"{symbol}_{interval}_{history_range}.csv"


def load_or_download_yahoo_candles(
    symbol: str,
    data_root: Path,
    *,
    refresh: bool,
    interval: str = YAHOO_INTERVAL,
    history_range: str = YAHOO_RANGE,
) -> list[Candle]:
    path = yahoo_cache_path(data_root, symbol, interval=interval, history_range=history_range)
    if path.exists() and not refresh:
        return read_candles_csv(path)
    query = urlencode({"range": history_range, "interval": interval, "includePrePost": "false", "events": "div,splits"})
    request = Request(
        YAHOO_CHART_URL.format(symbol=symbol) + "?" + query,
        headers={"User-Agent": "Mozilla/5.0 (compatible; okx-quant-readonly-research/1.0)"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    candles = parse_yahoo_chart(payload)
    minimum = max(MIN_FULL_SESSION_BARS, max(SLOW_LOOKBACK_DAYS) + SLOW_VOLATILITY_DAYS)
    if len(candles) < minimum:
        raise ValueError(f"Yahoo returned insufficient {interval} candles for {symbol}: {len(candles)}")
    write_candles_csv(path, candles)
    # Sequential requests avoid treating an unofficial public endpoint as bulk infrastructure.
    time.sleep(0.35)
    return candles


def parse_yahoo_chart(payload: dict[str, Any]) -> list[Candle]:
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        error = (payload.get("chart") or {}).get("error") or {}
        raise ValueError(f"Yahoo chart response has no result: {error}")
    document = result[0]
    timestamps = document.get("timestamp") or []
    quote_rows = ((document.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote_rows.get("open") or []
    highs = quote_rows.get("high") or []
    lows = quote_rows.get("low") or []
    closes = quote_rows.get("close") or []
    volumes = quote_rows.get("volume") or []
    candles: list[Candle] = []
    for values in zip(timestamps, opens, highs, lows, closes, volumes):
        timestamp, open_px, high, low, close, volume = values
        numeric = (open_px, high, low, close)
        if any(value is None or not math.isfinite(float(value)) or float(value) <= 0 for value in numeric):
            continue
        candles.append(
            Candle(
                ts=int(timestamp) * 1000,
                open=Decimal(str(open_px)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=Decimal(str(volume or 0)),
            )
        )
    candles.sort(key=lambda item: item.ts)
    return candles


def load_contract_candles(
    contract: str, root: Path, *, limit: int, pages: int, refresh: bool
) -> list[Candle]:
    suffix = "" if pages <= 1 else f"x{pages}"
    path = root / f"{contract}_{YAHOO_INTERVAL}_{limit}{suffix}.csv"
    if refresh:
        # The client is constructed without .env so this is irrevocably a
        # public-candle request, not a signed account read.
        candles = parse_okx_candles(
            fetch_okx_candle_rows(OkxRestClient(), contract, YAHOO_INTERVAL, limit, pages)
        )
        if len(candles) < MIN_FULL_SESSION_BARS:
            raise ValueError(f"OKX returned insufficient public candles for {contract}: {len(candles)}")
        write_candles_csv(path, candles)
        return candles
    if not path.exists():
        raise FileNotFoundError(
            f"Missing public OKX execution cache: {path}. Collect it with the existing read-only candle loader first."
        )
    return read_candles_csv(path)


def quote_turnover_24h(ticker: dict[str, Any], *, last: float, contract_value: float) -> float:
    direct = number(ticker.get("volCcyQuote24h"))
    if direct > 0:
        return direct
    base = number(ticker.get("volCcy24h"))
    if base > 0 and last > 0:
        return base * last
    contracts = number(ticker.get("vol24h"))
    return contracts * contract_value * last if contracts > 0 and contract_value > 0 and last > 0 else 0.0


def number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def fetch_contract_liquidity(
    contracts: dict[str, str], *, min_quote_turnover_usdt: float, max_spread_bps: float
) -> dict[str, dict[str, Any]]:
    """Capture a public admission snapshot; it is never used as historical fill data."""
    client = OkxRestClient()
    instruments = client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"}).get("data", [])
    by_contract = {str(item.get("instId", "")): item for item in instruments}
    result: dict[str, dict[str, Any]] = {}
    for symbol, contract in contracts.items():
        instrument = by_contract.get(contract, {})
        ticker = client.get_ticker(contract).get("data", [{}])[0]
        bid = number(ticker.get("bidPx"))
        ask = number(ticker.get("askPx"))
        last = number(ticker.get("last"))
        midpoint = (bid + ask) / 2.0
        spread_bps = (ask - bid) / midpoint * 10_000.0 if midpoint > 0 and ask >= bid else math.inf
        quote_turnover = quote_turnover_24h(ticker, last=last, contract_value=number(instrument.get("ctVal")))
        state = str(instrument.get("state", ""))
        category = str(instrument.get("instCategory", ""))
        reasons: list[str] = []
        if state != "live":
            reasons.append("state_not_live")
        if category != "3":
            reasons.append("not_tradfi_stock_etf_category")
        if not math.isfinite(spread_bps) or spread_bps > max_spread_bps:
            reasons.append("spread_above_limit")
        if quote_turnover < min_quote_turnover_usdt:
            reasons.append("turnover_below_limit")
        result[symbol] = {
            "contract": contract,
            "capturedAt": iso_time(int(number(ticker.get("ts")))),
            "state": state,
            "instCategory": category,
            "last": last,
            "spreadBps": spread_bps if math.isfinite(spread_bps) else None,
            "quoteTurnover24hUsdt": quote_turnover,
            "eligible": not reasons,
            "reasons": reasons,
        }
    return result


def nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    value = date(year, month, 1)
    while value.weekday() != weekday:
        value += timedelta(days=1)
    return value + timedelta(days=7 * (occurrence - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        value = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        value = date(year, month + 1, 1) - timedelta(days=1)
    while value.weekday() != weekday:
        value -= timedelta(days=1)
    return value


def easter_sunday(year: int) -> date:
    """Gregorian computus, used only to exclude Good Friday from RTH."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def observed_holiday(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def is_nyse_holiday(value: date) -> bool:
    year = value.year
    holidays = {
        observed_holiday(date(year, 1, 1)),
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        easter_sunday(year) - timedelta(days=2),
        last_weekday(year, 5, 0),
        observed_holiday(date(year, 6, 19)),
        observed_holiday(date(year, 7, 4)),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
        observed_holiday(date(year, 12, 25)),
    }
    return value in holidays


def is_early_close(value: date) -> bool:
    thanksgiving = nth_weekday(value.year, 11, 3, 4)
    return value == thanksgiving + timedelta(days=1) or value == date(value.year, 12, 24) and value.weekday() < 5


def regular_session_date(timestamp_ms: int) -> str | None:
    local = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).astimezone(NEW_YORK)
    local_date = local.date()
    if local.weekday() >= 5 or is_nyse_holiday(local_date) or is_early_close(local_date):
        return None
    start = clock_time(9, 30)
    end = clock_time(16, 0)
    if start <= local.timetz().replace(tzinfo=None) < end:
        return local_date.isoformat()
    return None


def matched_regular_sessions(
    underlying: list[Candle], contract: list[Candle]
) -> tuple[dict[str, list[tuple[Candle, Candle]]], dict[str, int]]:
    underlying_by_ts = {row.ts: row for row in underlying if regular_session_date(row.ts)}
    contract_by_ts = {row.ts: row for row in contract if regular_session_date(row.ts)}
    matched: dict[str, list[tuple[Candle, Candle]]] = {}
    for timestamp in sorted(underlying_by_ts.keys() & contract_by_ts.keys()):
        key = regular_session_date(timestamp)
        if key:
            matched.setdefault(key, []).append((underlying_by_ts[timestamp], contract_by_ts[timestamp]))
    complete = {key: rows for key, rows in matched.items() if len(rows) >= MIN_FULL_SESSION_BARS}
    return complete, {
        "underlyingRthBars": len(underlying_by_ts),
        "contractRthBars": len(contract_by_ts),
        "exactTimestampMatches": sum(len(rows) for rows in matched.values()),
        "completeSessions": len(complete),
        "discardedPartialSessions": len(matched) - len(complete),
    }


def contract_regular_sessions(contract: list[Candle]) -> tuple[dict[str, list[tuple[Candle, Candle]]], dict[str, int]]:
    """Return only complete executable RTH sessions when a factor is daily."""
    grouped: dict[str, list[tuple[Candle, Candle]]] = {}
    for candle in contract:
        key = regular_session_date(candle.ts)
        if key:
            grouped.setdefault(key, []).append((candle, candle))
    complete = {key: rows for key, rows in grouped.items() if len(rows) >= MIN_FULL_SESSION_BARS}
    return complete, {
        "underlyingRthBars": 0,
        "contractRthBars": sum(len(rows) for rows in grouped.values()),
        "exactTimestampMatches": 0,
        "completeSessions": len(complete),
        "discardedPartialSessions": len(grouped) - len(complete),
    }


def candle_date(candle: Candle) -> date:
    return datetime.fromtimestamp(candle.ts / 1000, timezone.utc).astimezone(NEW_YORK).date()


def slow_daily_sides(daily_candles: list[Candle], session_dates: list[str]) -> dict[str, int]:
    """Map each RTH session to a strictly prior daily-source trend state."""
    closes_by_date = {candle_date(candle): float(candle.close) for candle in daily_candles if candle.close > 0}
    dates = sorted(closes_by_date)
    closes = [closes_by_date[item] for item in dates]
    result: dict[str, int] = {}
    state = 0
    warmup = max(max(SLOW_LOOKBACK_DAYS), SLOW_VOLATILITY_DAYS)
    for value in session_dates:
        session_day = date.fromisoformat(value)
        index = bisect_left(dates, session_day) - 1
        if index < warmup:
            result[value] = 0
            continue
        daily_returns = [
            closes[position] / closes[position - 1] - 1.0
            for position in range(max(1, index - SLOW_VOLATILITY_DAYS + 1), index + 1)
            if closes[position - 1] > 0 and closes[position] > 0
        ]
        realized_volatility = statistics.pstdev(daily_returns) if len(daily_returns) >= 2 else 0.0
        votes = 0
        for lookback in SLOW_LOOKBACK_DAYS:
            before = closes[index - lookback]
            previous = closes[index]
            if before <= 0 or previous <= 0:
                continue
            momentum = previous / before - 1.0
            threshold = THRESHOLD_SIGMA * realized_volatility * math.sqrt(lookback)
            if momentum > threshold:
                votes += 1
            elif momentum < -threshold:
                votes -= 1
        if votes >= MIN_VOTES:
            state = 1
        elif votes <= -MIN_VOTES:
            state = -1
        result[value] = state
    return result


def shared_session_dates(instruments: dict[str, dict[str, Any]]) -> list[str]:
    common: set[str] | None = None
    for instrument in instruments.values():
        dates = set(instrument["sessions"])
        common = dates if common is None else common & dates
    return sorted(common or set())


def chronological_splits(session_dates: list[str]) -> dict[str, list[str]]:
    count = len(session_dates)
    train_end = int(count * 0.50)
    validation_end = int(count * 0.75)
    return {
        "train": session_dates[:train_end],
        "validation": session_dates[train_end:validation_end],
        "test": session_dates[validation_end:],
        "full": session_dates,
    }


def session_targets(rows: list[tuple[Candle, Candle]]) -> list[int]:
    closes = [float(underlying.close) for underlying, _ in rows]
    targets = [0] * len(rows)
    state = 0
    warmup = max(max(LOOKBACK_BARS), VOLATILITY_BARS) + 1
    for index in range(warmup, len(rows)):
        returns = [
            closes[position] / closes[position - 1] - 1.0
            for position in range(max(1, index - VOLATILITY_BARS), index)
            if closes[position - 1] > 0 and closes[position] > 0
        ]
        realized_volatility = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
        votes = 0
        for lookback in LOOKBACK_BARS:
            before = closes[index - 1 - lookback]
            previous = closes[index - 1]
            if before <= 0 or previous <= 0:
                continue
            momentum = previous / before - 1.0
            threshold = THRESHOLD_SIGMA * realized_volatility * math.sqrt(lookback)
            if momentum > threshold:
                votes += 1
            elif momentum < -threshold:
                votes -= 1
        if votes >= MIN_VOTES:
            state = 1
        elif votes <= -MIN_VOTES:
            state = -1
        targets[index] = state
    return targets


def simulate_sessions(
    *,
    symbol: str,
    contract: str,
    sessions: list[list[tuple[Candle, Candle]]],
    starting_equity: float,
    allocation_pct: float,
    leverage: float,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
    session_sides: dict[str, int] | None = None,
) -> tuple[SimulationResult, list[Trade]]:
    cash = starting_equity
    peak_equity = cash
    max_drawdown = 0.0
    fees = 0.0
    active_bars = 0
    observed_bars = 0
    trades: list[Trade] = []
    side = 0
    quantity = 0.0
    entry_price = 0.0
    entry_fee = 0.0
    entry_time = ""
    entry_session = ""
    entry_notional = 0.0
    fee_rate = max(0.0, fee_bps_per_side) / 10_000.0
    slip_rate = max(0.0, slippage_bps_per_side) / 10_000.0

    def close_position(candle: Candle, session: str, reason: str, *, at_close: bool = False) -> None:
        nonlocal cash, fees, side, quantity, entry_price, entry_fee, entry_time, entry_session, entry_notional
        if not side:
            return
        raw_price = float(candle.close if at_close else candle.open)
        exit_price = raw_price * (1.0 - slip_rate if side > 0 else 1.0 + slip_rate)
        gross_pnl = side * quantity * (exit_price - entry_price)
        exit_fee = abs(quantity * exit_price) * fee_rate
        net_pnl = gross_pnl - entry_fee - exit_fee
        cash += gross_pnl - exit_fee
        fees += exit_fee
        trades.append(
            Trade(
                symbol=symbol,
                contract=contract,
                session=session,
                side="long" if side > 0 else "short",
                entry_time=entry_time,
                exit_time=iso_time(candle.ts),
                entry_price=entry_price,
                exit_price=exit_price,
                notional=entry_notional,
                net_pnl=net_pnl,
                exit_reason=reason,
            )
        )
        side = 0
        quantity = 0.0
        entry_price = 0.0
        entry_fee = 0.0
        entry_time = ""
        entry_session = ""
        entry_notional = 0.0

    def open_position(desired: int, candle: Candle, session: str) -> None:
        nonlocal cash, fees, side, quantity, entry_price, entry_fee, entry_time, entry_session, entry_notional
        if not desired or cash <= 0:
            return
        raw_price = float(candle.open)
        entry_price = raw_price * (1.0 + slip_rate if desired > 0 else 1.0 - slip_rate)
        entry_notional = max(0.0, cash * allocation_pct / 100.0 * leverage)
        quantity = entry_notional / entry_price if entry_price > 0 else 0.0
        entry_fee = abs(quantity * entry_price) * fee_rate
        cash -= entry_fee
        fees += entry_fee
        side = desired
        entry_time = iso_time(candle.ts)
        entry_session = session

    for session_rows in sessions:
        if not session_rows:
            continue
        session = regular_session_date(session_rows[0][0].ts) or ""
        targets = (
            [session_sides.get(session, 0)] * len(session_rows)
            if session_sides is not None
            else session_targets(session_rows)
        )
        for index, (_, candle) in enumerate(session_rows):
            observed_bars += 1
            desired = targets[index]
            if desired != side:
                close_position(candle, session, "factor_flip")
                open_position(desired, candle, session)
            if side:
                active_bars += 1
            mark_price = float(candle.close)
            equity = cash + (side * quantity * (mark_price - entry_price) if side else 0.0)
            peak_equity = max(peak_equity, equity)
            if peak_equity > 0:
                max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100.0)
        close_position(session_rows[-1][1], session, "session_flatten", at_close=True)
        peak_equity = max(peak_equity, cash)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - cash) / peak_equity * 100.0)

    net_pnls = [trade.net_pnl for trade in trades]
    gross_profit = sum(value for value in net_pnls if value > 0)
    gross_loss = abs(sum(value for value in net_pnls if value < 0))
    profit_factor = gross_profit / gross_loss if gross_loss else (999.0 if gross_profit else 0.0)
    wins = sum(1 for value in net_pnls if value > 0)
    losses = sum(1 for value in net_pnls if value < 0)
    return (
        SimulationResult(
            return_pct=(cash / starting_equity - 1.0) * 100.0 if starting_equity > 0 else 0.0,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown,
            trades=len(trades),
            wins=wins,
            losses=losses,
            win_rate_pct=wins / len(trades) * 100.0 if trades else 0.0,
            fees=fees,
            exposure_pct=active_bars / observed_bars * 100.0 if observed_bars else 0.0,
            sessions=len(sessions),
            final_equity=cash,
        ),
        trades,
    )


def result_row(symbol: str, contract: str, segment: str, variant: str, result: SimulationResult) -> dict[str, Any]:
    return {"symbol": symbol, "contract": contract, "segment": segment, "variant": variant, **asdict(result)}


def decision_payload(rows: list[dict[str, Any]], sessions: int, minimum_sessions: int) -> dict[str, Any]:
    test_base = [row for row in rows if row["segment"] == "test" and row["variant"] == "base"]
    test_stress = [row for row in rows if row["segment"] == "test" and row["variant"] == "cost_stress"]
    required = lambda row: (
        row["return_pct"] > 0
        and row["profit_factor"] >= 1.10
        and row["trades"] >= 8
        and row["max_drawdown_pct"] <= 3.0
    )
    base_pass = bool(test_base) and all(required(row) for row in test_base)
    stress_pass = bool(test_stress) and all(required(row) for row in test_stress)
    return {
        "status": "research_only",
        "minimumResearchSessionsMet": sessions >= minimum_sessions,
        "minimumHistoricalCoverageMet": sessions >= MIN_HISTORICAL_COVERAGE_SESSIONS,
        "allContractsPassBaseTest": base_pass,
        "allContractsPassStressedTest": stress_pass,
        "eligibleForPaperOrLive": False,
        "reason": (
            "No promotion path: the available public contract-execution history is bounded, historical contract spreads are unavailable, "
            "and the experiment must be followed by a separately preregistered forward sample even if its historical rows pass."
        ),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    slow_daily = payload["factorMode"] == "slow_daily"
    title = "TRADFI 美股合约盘中慢因子研究" if slow_daily else "TRADFI 美股合约盘中多周期动量研究"
    factor_line = (
        "- 因子：前一交易日收盘已知的 20/60/120 日、波动率归一化多周期动量；至少两票同向，阈值 0.1 sigma。"
        if slow_daily
        else "- 因子：15/30/60/120 分钟、波动率归一化的多周期时间序列动量；至少两票同向，阈值 0.1 sigma。"
    )
    source_line = (
        "- 数据：Yahoo Finance 公开日线美股 OHLCV 只用于信号；每日信号严格使用早于当日的最近一个已完成收盘。OKX TRADFI 5m OHLCV 只用于执行。"
        if slow_daily
        else "- 数据：Yahoo Finance 公开 5m 美股 OHLCV 只用于信号；同时间戳 OKX TRADFI 永续 5m OHLCV 只用于执行。"
    )
    lines = [
        f"# {title}",
        "",
        "> 只读研究。信号来自公开美股现货数据，执行按 OKX TRADFI 合约 K 线模拟；不读取账户、不发送订单、不修改服务或实盘配置。",
        "",
        "## 固定设计",
        "",
        factor_line,
        "- 时间：仅纽约常规交易日 09:30–16:00；最后一根常规时段 K 线收盘强平，绝不持隔夜。",
        source_line + "缺失、非交易日、早收市和不完整交易日全部排除。",
        "- 执行：下一根合约 K 线开盘成交，默认每边 5 bps 手续费 + 5 bps 不利滑点；压力为双倍。没有根据训练、验证或测试结果调整周期、阈值或标的参数。",
        "",
        "## 样本",
        "",
        f"- 所有合约共同完整交易日：{len(payload['period']['sharedSessionDates'])}。",
        f"- 切分：训练 {len(payload['period']['splits']['train'])} 日，验证 {len(payload['period']['splits']['validation'])} 日，测试 {len(payload['period']['splits']['test'])} 日。",
        "",
        (
            "| 标的 | OKX 合约 | 交易日 | 日线因子K线 | 合约 RTH K线 | 做多日 | 做空日 | 空仓日 |"
            if slow_daily
            else "| 标的 | OKX 合约 | 匹配交易日 | 现货 RTH K线 | 合约 RTH K线 | 精确时间戳匹配 |"
        ),
        (
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"
            if slow_daily
            else "| --- | --- | ---: | ---: | ---: | ---: |"
        ),
    ]
    for symbol, item in payload["instruments"].items():
        alignment = item["alignment"]
        if slow_daily:
            sides = item.get("dailySides", {}).values()
            longs = sum(value == 1 for value in sides)
            sides = item.get("dailySides", {}).values()
            shorts = sum(value == -1 for value in sides)
            sides = item.get("dailySides", {}).values()
            flats = sum(value == 0 for value in sides)
            lines.append(
                f"| {symbol} | {item['contract']} | {item['matchedSessions']} | {alignment['dailySignalBars']} | "
                f"{alignment['contractRthBars']} | {longs} | {shorts} | {flats} |"
            )
        else:
            lines.append(
                f"| {symbol} | {item['contract']} | {item['matchedSessions']} | {alignment['underlyingRthBars']} | "
                f"{alignment['contractRthBars']} | {alignment['exactTimestampMatches']} |"
            )
    lines.extend([
        "",
        "## 当前合约流动性准入",
        "",
        "> 这是报告生成时的 OKX 公共快照，只用于决定后续研究宇宙，不能代表历史每一根 K 线的真实盘口。",
        "",
        "| 标的 | 合约 | 状态 | 价差 | 24h 估算换手 | 准入 | 原因 |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ])
    for symbol, item in payload["liquidityScreen"].items():
        spread = item["spreadBps"]
        lines.append(
            f"| {symbol} | {item['contract']} | {item['state']}/{item['instCategory']} | "
            f"{spread:.3f} bps" if spread is not None else f"| {symbol} | {item['contract']} | {item['state']}/{item['instCategory']} | unavailable"
        )
        if spread is not None:
            lines[-1] += (
                f" | {item['quoteTurnover24hUsdt']:.0f} USDT | {item['eligible']} | {', '.join(item['reasons']) or '-'} |"
            )
    lines.extend([
        "",
        "## 样本外结果",
        "",
        "| 标的 | 版本 | 收益 | PF | 最大回撤 | 交易 | 胜率 | 暴露 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in payload["rows"]:
        if row["segment"] == "test":
            lines.append(
                f"| {row['symbol']} | {row['variant']} | {row['return_pct']:.4f}% | {row['profit_factor']:.3f} | "
                f"{row['max_drawdown_pct']:.4f}% | {row['trades']} | {row['win_rate_pct']:.2f}% | {row['exposure_pct']:.2f}% |"
            )
    lines.extend([
        "",
        "## 判定",
        "",
        f"- 状态：`{decision['status']}`。",
        f"- 最低研究样本：`{decision['minimumResearchSessionsMet']}`；40 个共同交易日的历史覆盖要求：`{decision['minimumHistoricalCoverageMet']}`。",
        f"- 全部合约通过基础测试：`{decision['allContractsPassBaseTest']}`；通过压力测试：`{decision['allContractsPassStressedTest']}`。",
        f"- {decision['reason']}",
        "",
        "## 数据边界",
        "",
        "- 免费或公开不等于可直接实盘：Yahoo 是公开接口而非机构级逐笔/盘口源；日线能拉长因子历史，但合约执行样本仍然有限。"
        if slow_daily else "- 免费或公开不等于可直接实盘：Yahoo 是公开接口而非机构级逐笔/盘口源；其 5 分钟历史窗口很短。",
        "- OHLC 无法恢复合约历史 bid/ask、盘口深度、资金费、强平或挂单排队。实际进场前仍须以 OKX 实时合约盘口筛选流动性，并做全新、不再调参的前瞻记录。",
    ])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
