"""Point-in-time research for a constrained QQQ active-enhancement overlay.

The cash QQQ/stock history is used only to test cross-sectional stock-selection
alpha.  Current OKX public TRADFI data is captured separately to describe the
forward execution universe.  This module never loads ``.env``, calls a private
endpoint, submits an order, or changes a service/runtime configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "qqq_active_enhancement"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "qqq_active_enhancement"
NASDAQ_100_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
OKX_INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
OKX_TICKERS_URL = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nasdaq.com/market-activity/quotes/nasdaq-ndx-index",
}
PUBLIC_HEADERS = {"User-Agent": "okx-quant-readonly-research/1.0"}
SEC_HEADERS = {
    "User-Agent": "okx-quant-research/1.0 research-contact@example.invalid",
    "Accept": "application/json",
}
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; okx-quant-readonly-research/1.0)"}

US_JURISDICTIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}
FOREIGN_SECURITY_MARKERS = (
    " american depositary",
    " ordinary shares",
    " registry shares",
    " plc",
    " n.v.",
    " subordinate voting shares",
)

MOMENTUM_LONG_DAYS = 252
MOMENTUM_SKIP_DAYS = 21
BETA_WINDOW_DAYS = 252
MIN_REGRESSION_DAYS = 126
COVARIANCE_DAYS = 252
MIN_PRICE_HISTORY_DAYS = 504
ACTIVE_GROSS_LIMIT = 0.20
SINGLE_STOCK_LIMIT = 0.015
TRACKING_ERROR_LIMIT = 0.03
BASE_TRANSACTION_COST_BPS = 5.0
BASE_SHORT_BORROW_BPS = 100.0
STRESS_TRANSACTION_COST_BPS = 10.0
STRESS_SHORT_BORROW_BPS = 300.0
MIN_FORWARD_STOCKS = 12
IC_FACTORS = (
    "momentum",
    "quality",
    "value",
    "low_residual_volatility",
    "composite",
    "neutralized_composite",
)

FLOW_TAGS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "gross_profit": ("GrossProfit",),
}
INSTANT_TAGS = {
    "assets": ("Assets",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
}
SHARE_TAGS = ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic")


@dataclass(frozen=True, slots=True)
class FundamentalSnapshot:
    as_of: str
    latest_filed: str
    fiscal_end: str
    market_cap: float
    size: float
    roa: float | None
    cash_roa: float | None
    accrual_quality: float | None
    gross_profitability: float | None
    book_to_market: float | None
    earnings_yield: float | None
    sales_to_market: float | None


@dataclass(frozen=True, slots=True)
class WeightDiagnostics:
    success: bool
    message: str
    gross: float
    ex_ante_tracking_error: float
    max_abs_weight: float
    dollar_residual: float
    beta_residual: float
    size_residual: float
    industry_residual: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only QQQ active-enhancement research using point-in-time SEC filings."
    )
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--refresh-universe", action="store_true")
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--refresh-sec", action="store_true")
    parser.add_argument("--history-range", default="10y")
    parser.add_argument("--min-price-history-days", type=int, default=MIN_PRICE_HISTORY_DAYS)
    parser.add_argument("--active-gross-limit", type=float, default=ACTIVE_GROSS_LIMIT)
    parser.add_argument("--single-stock-limit", type=float, default=SINGLE_STOCK_LIMIT)
    parser.add_argument("--tracking-error-limit", type=float, default=TRACKING_ERROR_LIMIT)
    parser.add_argument("--min-current-turnover-usdt", type=float, default=5_000_000.0)
    parser.add_argument("--max-current-spread-bps", type=float, default=5.0)
    return parser.parse_args()


def read_json_url(url: str, *, headers: dict[str, str], timeout: int = 30) -> Any:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def read_or_fetch_json(
    path: Path,
    url: str,
    *,
    headers: dict[str, str],
    refresh: bool,
    pause_seconds: float = 0.0,
) -> Any:
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    payload = read_json_url(url, headers=headers)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if pause_seconds > 0:
        time.sleep(pause_seconds)
    return payload


def number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def iso_millis(value: Any) -> str:
    timestamp = number(value)
    if not math.isfinite(timestamp) or timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalized_ticker(value: str) -> str:
    return value.strip().upper().replace(".", "-")


def parse_nasdaq_rows(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    outer = payload.get("data") or {}
    rows = ((outer.get("data") or {}).get("rows") or [])
    parsed = [dict(row) for row in rows if row.get("symbol")]
    if len(parsed) < 90:
        raise ValueError(f"Nasdaq-100 response had only {len(parsed)} rows")
    return str(outer.get("date") or ""), parsed


def sec_ticker_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in payload.values():
        ticker = normalized_ticker(str(item.get("ticker") or ""))
        if ticker:
            result[ticker] = dict(item)
    return result


def okx_public_snapshot(
    ndx_symbols: set[str],
    *,
    min_turnover_usdt: float,
    max_spread_bps: float,
) -> dict[str, dict[str, Any]]:
    instruments_payload = read_json_url(OKX_INSTRUMENTS_URL, headers=PUBLIC_HEADERS)
    tickers_payload = read_json_url(OKX_TICKERS_URL, headers=PUBLIC_HEADERS)
    instruments = instruments_payload.get("data") or []
    tickers = {str(row.get("instId") or ""): row for row in (tickers_payload.get("data") or [])}
    result: dict[str, dict[str, Any]] = {}
    wanted = set(ndx_symbols) | {"QQQ"}
    for instrument in instruments:
        contract = str(instrument.get("instId") or "")
        if not contract.endswith("-USDT-SWAP"):
            continue
        symbol = contract.removesuffix("-USDT-SWAP")
        if symbol not in wanted:
            continue
        ticker = tickers.get(contract, {})
        bid = number(ticker.get("bidPx"))
        ask = number(ticker.get("askPx"))
        last = number(ticker.get("last"))
        midpoint = (bid + ask) / 2.0 if math.isfinite(bid) and math.isfinite(ask) else math.nan
        spread = (ask - bid) / midpoint * 10_000.0 if midpoint > 0 and ask >= bid else math.inf
        base_volume = number(ticker.get("volCcy24h"))
        if not math.isfinite(base_volume) or base_volume <= 0:
            base_volume = number(ticker.get("vol24h"))
        contract_value = number(instrument.get("ctVal"))
        if not math.isfinite(contract_value) or contract_value <= 0:
            contract_value = 1.0
        turnover = base_volume * last * contract_value if base_volume > 0 and last > 0 else 0.0
        reasons: list[str] = []
        if instrument.get("state") != "live":
            reasons.append("state_not_live")
        if str(instrument.get("instCategory") or "") != "3":
            reasons.append("not_tradfi_category")
        if not math.isfinite(spread) or spread > max_spread_bps:
            reasons.append("spread_above_limit")
        if turnover < min_turnover_usdt:
            reasons.append("turnover_below_limit")
        funding_rate = math.nan
        next_funding = ""
        try:
            funding = read_json_url(
                OKX_FUNDING_URL + "?" + urlencode({"instId": contract}), headers=PUBLIC_HEADERS
            ).get("data") or []
            if funding:
                funding_rate = number(funding[0].get("fundingRate"))
                next_funding = iso_millis(funding[0].get("nextFundingTime"))
        except Exception:
            pass
        result[symbol] = {
            "symbol": symbol,
            "contract": contract,
            "state": str(instrument.get("state") or ""),
            "instCategory": str(instrument.get("instCategory") or ""),
            "listTime": iso_millis(instrument.get("listTime")),
            "capturedAt": iso_millis(ticker.get("ts")),
            "last": last if math.isfinite(last) else None,
            "spreadBps": spread if math.isfinite(spread) else None,
            "quoteTurnover24hUsdt": turnover,
            "fundingRate": funding_rate if math.isfinite(funding_rate) else None,
            "nextFundingTime": next_funding,
            "eligible": not reasons,
            "reasons": reasons,
        }
        time.sleep(0.04)
    return result


def industry_bucket(sic_value: Any) -> str:
    try:
        sic = int(str(sic_value or "0"))
    except ValueError:
        sic = 0
    if 2830 <= sic <= 2839 or 3840 <= sic <= 3859 or 8000 <= sic <= 8099:
        return "health_care"
    if 4810 <= sic <= 4899 or 7800 <= sic <= 7899:
        return "communication_media"
    if 3570 <= sic <= 3579 or 3660 <= sic <= 3699 or 7370 <= sic <= 7379 or sic == 7389:
        return "information_technology"
    if 5000 <= sic <= 5999 or 7000 <= sic <= 7299 or 3700 <= sic <= 3799:
        return "consumer"
    return "industrial_other"


def build_universe(
    data_root: Path,
    *,
    refresh_universe: bool,
    refresh_sec: bool,
    min_turnover_usdt: float,
    max_spread_bps: float,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    nasdaq_payload = read_or_fetch_json(
        data_root / "nasdaq100.json",
        NASDAQ_100_URL,
        headers=NASDAQ_HEADERS,
        refresh=refresh_universe,
    )
    sec_tickers_payload = read_or_fetch_json(
        data_root / "sec_company_tickers.json",
        SEC_TICKERS_URL,
        headers=SEC_HEADERS,
        refresh=refresh_universe,
    )
    nasdaq_date, ndx_rows = parse_nasdaq_rows(nasdaq_payload)
    ndx_by_symbol = {normalized_ticker(row["symbol"]): row for row in ndx_rows}
    sec_map = sec_ticker_map(sec_tickers_payload)
    contracts = okx_public_snapshot(
        set(ndx_by_symbol),
        min_turnover_usdt=min_turnover_usdt,
        max_spread_bps=max_spread_bps,
    )
    universe: dict[str, dict[str, Any]] = {}
    exclusions: dict[str, dict[str, Any]] = {}
    for symbol in sorted(set(ndx_by_symbol) & set(contracts)):
        sec_row = sec_map.get(symbol)
        reasons: list[str] = []
        submissions: dict[str, Any] = {}
        if not sec_row:
            reasons.append("missing_sec_ticker_mapping")
        else:
            cik = int(sec_row["cik_str"])
            try:
                submissions = read_or_fetch_json(
                    data_root / "sec" / f"CIK{cik:010d}_submissions.json",
                    SEC_SUBMISSIONS_URL.format(cik=cik),
                    headers=SEC_HEADERS,
                    refresh=refresh_sec,
                    pause_seconds=0.12,
                )
            except Exception as exc:
                reasons.append(f"sec_submissions_error:{type(exc).__name__}")
            jurisdiction = str(submissions.get("stateOfIncorporation") or "")
            mailing = ((submissions.get("addresses") or {}).get("mailing") or {})
            mailing_jurisdiction = str(mailing.get("stateOrCountry") or "")
            company_name = str(ndx_by_symbol[symbol].get("companyName") or "")
            foreign_name = any(marker in company_name.lower() for marker in FOREIGN_SECURITY_MARKERS)
            domestic_evidence = jurisdiction in US_JURISDICTIONS or (
                not jurisdiction and mailing_jurisdiction in US_JURISDICTIONS and not foreign_name
            )
            if submissions and not domestic_evidence:
                reasons.append(
                    f"foreign_or_unclear_incorporation:{jurisdiction or mailing_jurisdiction or 'missing'}"
                )
            if submissions and symbol not in {
                normalized_ticker(value) for value in (submissions.get("tickers") or [])
            }:
                reasons.append("ticker_not_in_current_sec_submission")
        row = {
            "symbol": symbol,
            "companyName": str(ndx_by_symbol[symbol].get("companyName") or ""),
            "nasdaqMarketCap": str(ndx_by_symbol[symbol].get("marketCap") or ""),
            "cik": int(sec_row["cik_str"]) if sec_row else None,
            "secEntityName": str(submissions.get("name") or ""),
            "stateOfIncorporation": str(submissions.get("stateOfIncorporation") or ""),
            "sic": str(submissions.get("sic") or ""),
            "sicDescription": str(submissions.get("sicDescription") or ""),
            "industry": industry_bucket(submissions.get("sic")),
            "contract": contracts[symbol]["contract"],
            "contractEligibleNow": bool(contracts[symbol]["eligible"]),
        }
        if reasons:
            exclusions[symbol] = {**row, "reasons": reasons}
        else:
            universe[symbol] = row
    metadata = {
        "nasdaqConstituentDate": nasdaq_date,
        "nasdaqConstituents": len(ndx_rows),
        "mappedTradfiContracts": len(set(ndx_by_symbol) & set(contracts)),
        "domesticSecMappedUniverse": len(universe),
        "excludedMappings": exclusions,
    }
    return universe, contracts, metadata


def yahoo_cache_path(data_root: Path, symbol: str, history_range: str) -> Path:
    return data_root / "prices" / f"{symbol}_1d_{history_range}.csv"


def parse_yahoo_daily(payload: dict[str, Any]) -> pd.DataFrame:
    result = ((payload.get("chart") or {}).get("result") or [])
    if not result:
        raise ValueError(f"Yahoo response has no result: {(payload.get('chart') or {}).get('error')}")
    document = result[0]
    timestamps = document.get("timestamp") or []
    quotes = (((document.get("indicators") or {}).get("quote") or [{}])[0])
    adjusted = (((document.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    closes = quotes.get("close") or []
    volumes = quotes.get("volume") or []
    length = min(len(timestamps), len(closes), len(adjusted) or len(closes))
    if not adjusted:
        adjusted = closes
    rows: list[dict[str, Any]] = []
    for index in range(length):
        close = number(closes[index])
        adj_close = number(adjusted[index])
        if close <= 0 or adj_close <= 0:
            continue
        value = pd.Timestamp(int(timestamps[index]), unit="s", tz="UTC").tz_convert("America/New_York")
        rows.append(
            {
                "date": value.date().isoformat(),
                "close": close,
                "adj_close": adj_close,
                "volume": number(volumes[index]) if index < len(volumes) else 0.0,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("Yahoo response contained no valid daily rows")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.drop_duplicates("date", keep="last").set_index("date").sort_index()


def load_yahoo_daily(
    symbol: str,
    data_root: Path,
    *,
    history_range: str,
    refresh: bool,
) -> pd.DataFrame:
    path = yahoo_cache_path(data_root, symbol, history_range)
    if path.exists() and not refresh:
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        return frame
    query = urlencode(
        {"range": history_range, "interval": "1d", "includePrePost": "false", "events": "div,splits"}
    )
    payload = read_json_url(YAHOO_CHART_URL.format(symbol=symbol) + "?" + query, headers=YAHOO_HEADERS)
    frame = parse_yahoo_daily(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label="date")
    time.sleep(0.18)
    return frame


def load_company_facts(cik: int, data_root: Path, *, refresh: bool) -> dict[str, Any]:
    return read_or_fetch_json(
        data_root / "sec" / f"CIK{cik:010d}_companyfacts.json",
        SEC_COMPANY_FACTS_URL.format(cik=cik),
        headers=SEC_HEADERS,
        refresh=refresh,
        pause_seconds=0.12,
    )


def fact_records(
    payload: dict[str, Any],
    tags: Sequence[str],
    *,
    units: Sequence[str],
    annual_only: bool,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    namespaces = payload.get("facts") or {}
    for namespace in ("us-gaap", "dei"):
        namespace_facts = namespaces.get(namespace) or {}
        for tag in tags:
            fact = namespace_facts.get(tag) or {}
            unit_rows = fact.get("units") or {}
            for unit in units:
                for row in unit_rows.get(unit, []) or []:
                    form = str(row.get("form") or "")
                    if annual_only and form not in {"10-K", "10-K/A"}:
                        continue
                    if not annual_only and form not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}:
                        continue
                    try:
                        filed = date.fromisoformat(str(row.get("filed")))
                        end = date.fromisoformat(str(row.get("end")))
                    except (TypeError, ValueError):
                        continue
                    start_value = row.get("start")
                    start: date | None = None
                    if start_value:
                        try:
                            start = date.fromisoformat(str(start_value))
                        except ValueError:
                            continue
                    duration = (end - start).days if start else None
                    if annual_only and duration is not None and not 270 <= duration <= 430:
                        continue
                    value = number(row.get("val"))
                    if not math.isfinite(value):
                        continue
                    result.append(
                        {
                            "tag": tag,
                            "unit": unit,
                            "value": value,
                            "filed": filed,
                            "start": start,
                            "end": end,
                            "duration": duration,
                            "form": form,
                            "fp": str(row.get("fp") or ""),
                            "accn": str(row.get("accn") or ""),
                        }
                    )
    return result


def latest_fact_asof(records: Sequence[dict[str, Any]], as_of: date) -> dict[str, Any] | None:
    available = [row for row in records if row["filed"] < as_of and row["end"] < as_of]
    if not available:
        return None
    return max(available, key=lambda row: (row["end"], row["filed"], row["duration"] or 0))


def latest_share_fact_asof(records: Sequence[dict[str, Any]], as_of: date) -> dict[str, Any] | None:
    available = [
        row
        for row in records
        if row["filed"] < as_of
        and row["end"] < as_of
        and row["duration"] is not None
        and 55 <= row["duration"] <= 430
        and row["value"] > 0
    ]
    if not available:
        return None
    latest_end = max(row["end"] for row in available)
    same_end = [row for row in available if row["end"] == latest_end]
    # Quarterly facts sometimes include both the quarter and year-to-date.  The
    # shortest duration is the least stale share count and is still consolidated.
    return min(same_end, key=lambda row: (row["duration"], -row["filed"].toordinal()))


def prepare_fundamental_records(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    prepared: dict[str, list[dict[str, Any]]] = {}
    for name, tags in FLOW_TAGS.items():
        prepared[name] = fact_records(payload, tags, units=("USD",), annual_only=True)
    for name, tags in INSTANT_TAGS.items():
        prepared[name] = fact_records(payload, tags, units=("USD",), annual_only=True)
    prepared["shares"] = fact_records(payload, SHARE_TAGS, units=("shares",), annual_only=False)
    return prepared


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def fundamental_snapshot_asof(
    records: dict[str, list[dict[str, Any]]],
    as_of: date,
    raw_price: float,
) -> FundamentalSnapshot | None:
    selected = {name: latest_fact_asof(rows, as_of) for name, rows in records.items() if name != "shares"}
    share_row = latest_share_fact_asof(records.get("shares", []), as_of)
    assets_row = selected.get("assets")
    if not share_row or not assets_row or raw_price <= 0:
        return None
    assets = float(assets_row["value"])
    shares = float(share_row["value"])
    market_cap = raw_price * shares
    if assets <= 0 or market_cap <= 0:
        return None

    def value(name: str) -> float | None:
        row = selected.get(name)
        return float(row["value"]) if row else None

    net_income = value("net_income")
    cash_flow = value("operating_cash_flow")
    gross_profit = value("gross_profit")
    equity = value("equity")
    revenue = value("revenue")
    filed_dates = [row["filed"] for row in selected.values() if row] + [share_row["filed"]]
    fiscal_ends = [row["end"] for row in selected.values() if row]
    return FundamentalSnapshot(
        as_of=as_of.isoformat(),
        latest_filed=max(filed_dates).isoformat(),
        fiscal_end=max(fiscal_ends).isoformat(),
        market_cap=market_cap,
        size=math.log(market_cap),
        roa=safe_ratio(net_income, assets),
        cash_roa=safe_ratio(cash_flow, assets),
        accrual_quality=safe_ratio((cash_flow - net_income) if cash_flow is not None and net_income is not None else None, assets),
        gross_profitability=safe_ratio(gross_profit, assets),
        book_to_market=safe_ratio(equity, market_cap),
        earnings_yield=safe_ratio(net_income, market_cap),
        sales_to_market=safe_ratio(revenue, market_cap),
    )


def winsorized_z(values: pd.Series, *, minimum: int = 5) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    valid = numeric.dropna()
    result = pd.Series(np.nan, index=values.index, dtype=float)
    if len(valid) < minimum:
        return result
    lower, upper = valid.quantile([0.05, 0.95])
    clipped = valid.clip(lower=lower, upper=upper)
    scale = float(clipped.std(ddof=0))
    if not math.isfinite(scale) or scale <= 1e-12:
        return result
    result.loc[clipped.index] = (clipped - float(clipped.mean())) / scale
    return result


def regression_characteristics(stock: pd.Series, benchmark: pd.Series) -> tuple[float, float] | None:
    aligned = pd.concat([stock.rename("stock"), benchmark.rename("benchmark")], axis=1).dropna()
    if len(aligned) < MIN_REGRESSION_DAYS:
        return None
    aligned = aligned.iloc[-BETA_WINDOW_DAYS:]
    x = aligned["benchmark"].to_numpy(dtype=float)
    y = aligned["stock"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x)), x])
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coefficients
    return float(coefficients[1]), float(np.std(residual, ddof=1) * math.sqrt(252.0))


def signal_frame_asof(
    as_of: pd.Timestamp,
    universe: dict[str, dict[str, Any]],
    prices: dict[str, pd.DataFrame],
    fundamentals: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    benchmark_history = prices["QQQ"].loc[:as_of, "adj_close"]
    benchmark_returns = benchmark_history.pct_change()
    rows: list[dict[str, Any]] = []
    exclusion_counts: dict[str, int] = {}

    def exclude(reason: str) -> None:
        exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1

    for symbol, metadata in universe.items():
        frame = prices.get(symbol)
        if frame is None:
            exclude("missing_price_frame")
            continue
        history = frame.loc[:as_of].dropna(subset=["close", "adj_close"])
        if len(history) <= MOMENTUM_LONG_DAYS:
            exclude("insufficient_momentum_history")
            continue
        long_price = float(history["adj_close"].iloc[-(MOMENTUM_LONG_DAYS + 1)])
        skip_price = float(history["adj_close"].iloc[-(MOMENTUM_SKIP_DAYS + 1)])
        momentum = skip_price / long_price - 1.0 if long_price > 0 else math.nan
        regression = regression_characteristics(history["adj_close"].pct_change(), benchmark_returns)
        if regression is None:
            exclude("insufficient_regression_history")
            continue
        beta, residual_volatility = regression
        raw_price = float(history["close"].iloc[-1])
        snapshot = fundamental_snapshot_asof(fundamentals[symbol], as_of.date(), raw_price)
        if snapshot is None:
            exclude("missing_point_in_time_fundamentals")
            continue
        rows.append(
            {
                "symbol": symbol,
                "industry": metadata["industry"],
                "momentum_raw": momentum,
                "low_residual_volatility_raw": -residual_volatility,
                "beta": beta,
                "size": snapshot.size,
                "market_cap": snapshot.market_cap,
                "latest_filed": snapshot.latest_filed,
                "fiscal_end": snapshot.fiscal_end,
                "roa": snapshot.roa,
                "cash_roa": snapshot.cash_roa,
                "accrual_quality": snapshot.accrual_quality,
                "gross_profitability": snapshot.gross_profitability,
                "book_to_market": snapshot.book_to_market,
                "earnings_yield": snapshot.earnings_yield,
                "sales_to_market": snapshot.sales_to_market,
            }
        )
    if not rows:
        return pd.DataFrame(), {"exclusionCounts": exclusion_counts, "rawEligible": 0, "factorComplete": 0}
    factors = pd.DataFrame(rows).set_index("symbol")
    quality_columns: list[str] = []
    for column in ("roa", "cash_roa", "accrual_quality", "gross_profitability"):
        name = f"{column}_z"
        factors[name] = winsorized_z(factors[column])
        quality_columns.append(name)
    value_columns: list[str] = []
    for column in ("book_to_market", "earnings_yield", "sales_to_market"):
        name = f"{column}_z"
        factors[name] = winsorized_z(factors[column])
        value_columns.append(name)
    factors["quality_raw"] = factors[quality_columns].mean(axis=1, skipna=True)
    factors.loc[factors[quality_columns].notna().sum(axis=1) < 2, "quality_raw"] = np.nan
    factors["quality"] = winsorized_z(factors["quality_raw"])
    factors["value_raw"] = factors[value_columns].mean(axis=1, skipna=True)
    factors.loc[factors[value_columns].notna().sum(axis=1) < 2, "value_raw"] = np.nan
    factors["value"] = winsorized_z(factors["value_raw"])
    factors["momentum"] = winsorized_z(factors["momentum_raw"])
    factors["low_residual_volatility"] = winsorized_z(factors["low_residual_volatility_raw"])
    composite_columns = ("momentum", "quality", "value", "low_residual_volatility")
    factors["composite"] = factors[list(composite_columns)].mean(axis=1, skipna=False)
    factors["size_z"] = winsorized_z(factors["size"])
    complete = factors.dropna(subset=[*composite_columns, "composite", "beta", "size_z"])
    diagnostics = {
        "exclusionCounts": exclusion_counts,
        "rawEligible": len(factors),
        "factorComplete": len(complete),
        "latestFiledMax": max(complete["latest_filed"], default=""),
    }
    return complete, diagnostics


def covariance_asof(
    as_of: pd.Timestamp,
    symbols: Sequence[str],
    prices: dict[str, pd.DataFrame],
) -> np.ndarray | None:
    series = {
        symbol: prices[symbol].loc[:as_of, "adj_close"].pct_change().rename(symbol)
        for symbol in symbols
    }
    aligned = pd.concat(series.values(), axis=1).dropna()
    if len(aligned) < MIN_REGRESSION_DAYS:
        return None
    aligned = aligned.iloc[-COVARIANCE_DAYS:]
    covariance = aligned.cov().to_numpy(dtype=float) * 252.0
    diagonal = np.diag(np.diag(covariance))
    shrunk = 0.75 * covariance + 0.25 * diagonal
    if not np.isfinite(shrunk).all():
        return None
    return shrunk


def neutrality_design(frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    industries = pd.get_dummies(frame["industry"], dtype=float)
    columns: list[np.ndarray] = []
    names: list[str] = []
    for name in industries.columns:
        columns.append(industries[name].to_numpy(dtype=float))
        names.append(f"industry:{name}")
    columns.append(frame["beta"].to_numpy(dtype=float))
    names.append("beta")
    columns.append(frame["size_z"].to_numpy(dtype=float))
    names.append("size")
    return np.column_stack(columns), names


def neutral_weights(
    frame: pd.DataFrame,
    covariance: np.ndarray,
    *,
    gross_limit: float = ACTIVE_GROSS_LIMIT,
    single_stock_limit: float = SINGLE_STOCK_LIMIT,
    tracking_error_limit: float = TRACKING_ERROR_LIMIT,
) -> tuple[pd.Series, WeightDiagnostics]:
    symbols = list(frame.index)
    if len(symbols) < 6 or covariance.shape != (len(symbols), len(symbols)):
        empty = pd.Series(0.0, index=symbols)
        return empty, WeightDiagnostics(False, "insufficient_dimension", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    design, names = neutrality_design(frame)
    score = frame["composite"].to_numpy(dtype=float)
    coefficients, *_ = np.linalg.lstsq(design, score, rcond=None)
    direction = score - design @ coefficients
    gross = float(np.abs(direction).sum())
    if gross <= 1e-12:
        empty = pd.Series(0.0, index=symbols)
        return empty, WeightDiagnostics(False, "zero_neutral_score", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    direction /= gross
    raw_te = float(math.sqrt(max(direction @ covariance @ direction, 0.0)))
    max_direction = float(np.abs(direction).max())
    scale_candidates = [gross_limit]
    if max_direction > 0:
        scale_candidates.append(single_stock_limit / max_direction)
    if raw_te > 0:
        scale_candidates.append(tracking_error_limit / raw_te)
    scale = max(0.0, min(scale_candidates))
    weights = direction * scale
    industry_values = design[:, : sum(name.startswith("industry:") for name in names)]
    diagnostics = WeightDiagnostics(
        success=True,
        message="residualized_equal_factor_score",
        gross=float(np.abs(weights).sum()),
        ex_ante_tracking_error=float(math.sqrt(max(weights @ covariance @ weights, 0.0))),
        max_abs_weight=float(np.abs(weights).max()),
        dollar_residual=float(abs(weights.sum())),
        beta_residual=float(abs(weights @ frame["beta"].to_numpy(dtype=float))),
        size_residual=float(abs(weights @ frame["size_z"].to_numpy(dtype=float))),
        industry_residual=float(np.max(np.abs(industry_values.T @ weights))) if industry_values.size else 0.0,
    )
    return pd.Series(weights, index=symbols), diagnostics


def rebalance_dates(calendar: pd.DatetimeIndex, mode: str) -> list[pd.Timestamp]:
    if mode == "monthly":
        series = pd.Series(calendar, index=calendar)
        completed = [
            pd.Timestamp(value)
            for value in series.groupby([calendar.year, calendar.month]).last().to_numpy()
        ]
        # The final observed month is not known to be complete until a later
        # month appears.  Dropping it prevents a mid-month run from treating
        # today's last row as a month-end rebalance.
        return completed[:-1]
    if mode == "biweekly":
        iso = calendar.isocalendar()
        series = pd.Series(calendar, index=calendar)
        weekly = [
            pd.Timestamp(value)
            for value in series.groupby([iso.year.to_numpy(), iso.week.to_numpy()]).last().to_numpy()
        ]
        # As with months, require a later week to confirm the final observed
        # week is complete.  This is conservative at a true Friday close.
        return weekly[:-1:2]
    raise ValueError(f"unsupported rebalance mode: {mode}")


def build_weight_history(
    mode: str,
    universe: dict[str, dict[str, Any]],
    prices: dict[str, pd.DataFrame],
    fundamentals: dict[str, dict[str, list[dict[str, Any]]]],
    *,
    gross_limit: float,
    single_stock_limit: float,
    tracking_error_limit: float,
) -> tuple[dict[pd.Timestamp, pd.Series], list[dict[str, Any]], dict[pd.Timestamp, pd.DataFrame]]:
    calendar = prices["QQQ"].index
    candidates = rebalance_dates(calendar, mode)
    weights: dict[pd.Timestamp, pd.Series] = {}
    diagnostics_rows: list[dict[str, Any]] = []
    signals: dict[pd.Timestamp, pd.DataFrame] = {}
    all_symbols = sorted(universe)
    for as_of in candidates:
        signal, coverage = signal_frame_asof(as_of, universe, prices, fundamentals)
        if len(signal) < 6:
            continue
        covariance = covariance_asof(as_of, list(signal.index), prices)
        if covariance is None:
            continue
        active, diagnostics = neutral_weights(
            signal,
            covariance,
            gross_limit=gross_limit,
            single_stock_limit=single_stock_limit,
            tracking_error_limit=tracking_error_limit,
        )
        if not diagnostics.success:
            continue
        full = pd.Series(0.0, index=all_symbols)
        full.loc[active.index] = active
        weights[as_of] = full
        signals[as_of] = signal.copy()
        diagnostics_rows.append(
            {
                "rebalanceDate": as_of.date().isoformat(),
                "mode": mode,
                "eligibleStocks": len(signal),
                **asdict(diagnostics),
                "latestFiledMax": coverage.get("latestFiledMax", ""),
                "exclusionCounts": json.dumps(coverage.get("exclusionCounts", {}), sort_keys=True),
            }
        )
    return weights, diagnostics_rows, signals


def aligned_return_panel(prices: dict[str, pd.DataFrame], symbols: Sequence[str]) -> pd.DataFrame:
    calendar = prices["QQQ"].index
    adjusted = pd.DataFrame(index=calendar)
    for symbol in ["QQQ", *symbols]:
        adjusted[symbol] = prices[symbol]["adj_close"].reindex(calendar).ffill(limit=5)
    return adjusted.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)


def simulate_overlay(
    return_panel: pd.DataFrame,
    weight_history: dict[pd.Timestamp, pd.Series],
    *,
    transaction_cost_bps: float,
    short_borrow_bps: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if not weight_history:
        return pd.DataFrame(), []
    symbols = list(next(iter(weight_history.values())).index)
    calendar = return_panel.index
    effective: dict[pd.Timestamp, tuple[pd.Timestamp, pd.Series]] = {}
    for signal_date, weights in weight_history.items():
        location = calendar.searchsorted(signal_date, side="right")
        if location < len(calendar):
            effective[calendar[location]] = (signal_date, weights)
    current = pd.Series(0.0, index=symbols)
    rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    for value in calendar:
        turnover = 0.0
        signal_date = None
        if value in effective:
            signal_date, target = effective[value]
            turnover = float((target - current).abs().sum())
            current = target.copy()
            trades.append(
                {
                    "effectiveDate": value.date().isoformat(),
                    "signalDate": signal_date.date().isoformat(),
                    "turnover": turnover,
                    "gross": float(current.abs().sum()),
                    "longGross": float(current.clip(lower=0).sum()),
                    "shortGross": float(-current.clip(upper=0).sum()),
                }
            )
        stock_return = return_panel.loc[value, symbols].to_numpy(dtype=float)
        active_gross = float(current.to_numpy(dtype=float) @ stock_return)
        transaction_cost = turnover * transaction_cost_bps / 10_000.0
        borrow_cost = float(-current.clip(upper=0).sum()) * short_borrow_bps / 10_000.0 / 252.0
        active_net = active_gross - transaction_cost - borrow_cost
        benchmark = float(return_panel.at[value, "QQQ"])
        rows.append(
            {
                "date": value,
                "benchmarkReturn": benchmark,
                "activeGrossReturn": active_gross,
                "transactionCost": transaction_cost,
                "shortBorrowCost": borrow_cost,
                "activeNetReturn": active_net,
                "portfolioReturn": benchmark + active_net,
                "gross": float(current.abs().sum()),
            }
        )
    frame = pd.DataFrame(rows).set_index("date")
    first_effective = min(effective)
    return frame.loc[first_effective:], trades


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return float(-drawdown.min()) if len(drawdown) else 0.0


def performance_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    days = len(frame)
    years = days / 252.0
    benchmark_total = float((1.0 + frame["benchmarkReturn"]).prod() - 1.0)
    portfolio_total = float((1.0 + frame["portfolioReturn"]).prod() - 1.0)
    benchmark_annual = (1.0 + benchmark_total) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    portfolio_annual = (1.0 + portfolio_total) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    active = frame["activeNetReturn"]
    tracking_error = float(active.std(ddof=1) * math.sqrt(252.0)) if len(active) > 1 else 0.0
    active_mean = float(active.mean() * 252.0)
    covariance = float(np.cov(frame["portfolioReturn"], frame["benchmarkReturn"], ddof=1)[0, 1])
    variance = float(frame["benchmarkReturn"].var(ddof=1))
    return {
        "days": days,
        "start": frame.index[0].date().isoformat(),
        "end": frame.index[-1].date().isoformat(),
        "benchmarkTotalReturnPct": benchmark_total * 100.0,
        "portfolioTotalReturnPct": portfolio_total * 100.0,
        "benchmarkAnnualReturnPct": benchmark_annual * 100.0,
        "portfolioAnnualReturnPct": portfolio_annual * 100.0,
        "annualizedActiveReturnPct": active_mean * 100.0,
        "realizedTrackingErrorPct": tracking_error * 100.0,
        "informationRatio": active_mean / tracking_error if tracking_error > 0 else 0.0,
        "benchmarkVolatilityPct": float(frame["benchmarkReturn"].std(ddof=1) * math.sqrt(252.0) * 100.0),
        "portfolioVolatilityPct": float(frame["portfolioReturn"].std(ddof=1) * math.sqrt(252.0) * 100.0),
        "benchmarkMaxDrawdownPct": max_drawdown(frame["benchmarkReturn"]) * 100.0,
        "portfolioMaxDrawdownPct": max_drawdown(frame["portfolioReturn"]) * 100.0,
        "portfolioBetaToQQQ": covariance / variance if variance > 0 else 0.0,
        "averageGrossPct": float(frame["gross"].mean() * 100.0),
        "transactionCostPct": float(frame["transactionCost"].sum() * 100.0),
        "shortBorrowCostPct": float(frame["shortBorrowCost"].sum() * 100.0),
        "positiveActiveDayPct": float((active > 0).mean() * 100.0),
    }


def chronological_segments(index: pd.DatetimeIndex) -> dict[str, pd.DatetimeIndex]:
    first = int(len(index) * 0.60)
    second = int(len(index) * 0.80)
    return {
        "train": index[:first],
        "validation": index[first:second],
        "test": index[second:],
        "full": index,
    }


def segment_metrics(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    return {
        name: performance_metrics(frame.loc[dates])
        for name, dates in chronological_segments(frame.index).items()
        if len(dates)
    }


def factor_ic_rows(
    signals: dict[pd.Timestamp, pd.DataFrame],
    prices: dict[str, pd.DataFrame],
    weights: dict[pd.Timestamp, pd.Series],
) -> list[dict[str, Any]]:
    dates = sorted(signals)
    rows: list[dict[str, Any]] = []
    for current, following in zip(dates, dates[1:]):
        signal = signals[current]
        forward: dict[str, float] = {}
        for symbol in signal.index:
            frame = prices[symbol]
            before = frame.loc[:current, "adj_close"]
            after = frame.loc[:following, "adj_close"]
            if before.empty or after.empty:
                continue
            first = float(before.iloc[-1])
            last = float(after.iloc[-1])
            if first > 0 and math.isfinite(last):
                forward[symbol] = last / first - 1.0
        future = pd.Series(forward, dtype=float)
        common = signal.index.intersection(future.index)
        if len(common) < 5:
            continue
        row: dict[str, Any] = {
            "signalDate": current.date().isoformat(),
            "nextRebalanceDate": following.date().isoformat(),
            "stocks": len(common),
        }
        for factor in ("momentum", "quality", "value", "low_residual_volatility", "composite"):
            correlation = spearmanr(signal.loc[common, factor], future.loc[common], nan_policy="omit").statistic
            row[factor] = float(correlation) if math.isfinite(correlation) else None
        active = weights[current].reindex(common).fillna(0.0)
        correlation = spearmanr(active, future.loc[common], nan_policy="omit").statistic
        row["neutralized_composite"] = float(correlation) if math.isfinite(correlation) else None
        row["activePeriodReturn"] = float(active @ future.loc[common])
        rows.append(row)
    return rows


def summarize_ic(rows: list[dict[str, Any]], start: str, end: str) -> dict[str, Any]:
    selected = [row for row in rows if start <= row["signalDate"] <= end]
    result: dict[str, Any] = {"periods": len(selected)}
    for factor in IC_FACTORS:
        values = [float(row[factor]) for row in selected if row.get(factor) is not None]
        mean = statistics.fmean(values) if values else 0.0
        std = statistics.stdev(values) if len(values) > 1 else 0.0
        result[factor] = {
            "meanIc": mean,
            "tStatistic": mean / (std / math.sqrt(len(values))) if std > 0 else 0.0,
            "positivePct": sum(value > 0 for value in values) / len(values) * 100.0 if values else 0.0,
            "observations": len(values),
        }
    return result


def bootstrap_active_return(frame: pd.DataFrame, *, samples: int = 4000) -> dict[str, float]:
    monthly = frame["activeNetReturn"].groupby(frame.index.to_period("M")).apply(lambda x: (1.0 + x).prod() - 1.0)
    values = monthly.to_numpy(dtype=float)
    if len(values) < 6:
        return {"lower95Pct": 0.0, "medianPct": 0.0, "upper95Pct": 0.0, "months": len(values)}
    rng = np.random.default_rng(20260808)
    annualized: list[float] = []
    block = min(3, len(values))
    for _ in range(samples):
        sample: list[float] = []
        while len(sample) < len(values):
            start = int(rng.integers(0, max(1, len(values) - block + 1)))
            sample.extend(values[start : start + block])
        chosen = np.asarray(sample[: len(values)], dtype=float)
        annualized.append(float((1.0 + chosen.mean()) ** 12 - 1.0))
    lower, median, upper = np.quantile(annualized, [0.025, 0.5, 0.975])
    return {
        "lower95Pct": float(lower * 100.0),
        "medianPct": float(median * 100.0),
        "upper95Pct": float(upper * 100.0),
        "months": len(values),
    }


def resolve_output_dir(value: str) -> Path:
    if value:
        return Path(value)
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("qqq-pit-%Y%m%dT%H%M%SZ")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def frame_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        rows.append({"date": pd.Timestamp(index).date().isoformat(), **{key: float(value) for key, value in row.items()}})
    return rows


def weight_rows(mode: str, weights: dict[pd.Timestamp, pd.Series]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for as_of, values in sorted(weights.items()):
        for symbol, value in values.items():
            if abs(float(value)) > 1e-10:
                rows.append(
                    {
                        "mode": mode,
                        "signalDate": as_of.date().isoformat(),
                        "symbol": symbol,
                        "activeWeight": float(value),
                    }
                )
    return rows


def percent(value: Any, digits: int = 2) -> str:
    parsed = number(value)
    return f"{parsed:.{digits}f}%" if math.isfinite(parsed) else "-"


def markdown_report(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    lines = [
        "# 受约束 QQQ 主动增强：Point-in-Time 研究",
        "",
        "> 隔离、只读研究。美股现货与 SEC 数据只验证选股 alpha；OKX 数据只形成当前合约前瞻准入快照。未读取账户、未下单、未改服务或实盘配置。",
        "",
        "## 固定协议",
        "",
        "- 核心：100% QQQ；单股仅为美元中性的主动多空偏离，因此组合净 beta 核心仍来自 QQQ。",
        "- 因子：12-1 动量、质量、价值、低残差波动率等权；不训练模型、不根据测试期选择因子或标的。",
        "- 财务数据：SEC Company Facts；年报事实只有在实际 `filed` 日期严格早于调仓日时才可用。价格因子只使用调仓日及以前收盘。",
        "- 约束：行业、beta、市值中性；单股绝对主动权重不超过 1.5%，主动 gross 不超过 20%，事前跟踪误差不超过 3%。",
        "- 调仓：月末为预注册主版本；双周只是频率敏感性诊断。持仓跨日，不做每日收盘清仓。",
        "- 成本：基础每次单边主动换手 5 bps、空头年化 1%；压力为 10 bps 和 3%。QQQ 使用复权总回报序列。",
        "",
        "## 宇宙与数据",
        "",
        f"- Nasdaq 官方成分日期：{payload['universe']['nasdaqConstituentDate']}；官方成分 {payload['universe']['nasdaqConstituents']} 只。",
        f"- 与 OKX TRADFI 合约交集：{payload['universe']['mappedTradfiContracts']}；SEC 国内注册且映射明确：{payload['universe']['domesticSecMappedUniverse']}。",
        f"- 满足至少 {payload['config']['minPriceHistoryDays']} 个现货交易日并成功取得 SEC 数据：{payload['universe']['backtestUniverse']}。",
        f"- 当前同时通过 5 bps 价差和 500 万 USDT 估算换手门槛的单股合约：{payload['universe']['currentlyLiquidStocks']}；QQQ 核心合约准入：{payload['universe']['qqqContractEligible']}。",
        "",
        "当前合约准入只是一次公共盘口快照，不会被伪装成历史流动性。",
        "",
        "## 组合结果",
        "",
        "| 调仓 | 成本 | 区间 | 主动年化 | 实现跟踪误差 | IR | 组合年化 | QQQ年化 | 组合最大回撤 | 平均gross |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("monthly", "biweekly"):
        for variant in ("base", "stress"):
            for segment in ("train", "validation", "test", "full"):
                item = payload["results"][mode][variant]["segments"].get(segment) or {}
                if not item:
                    continue
                lines.append(
                    f"| {mode} | {variant} | {segment} | {percent(item.get('annualizedActiveReturnPct'))} | "
                    f"{percent(item.get('realizedTrackingErrorPct'))} | {number(item.get('informationRatio')):.3f} | "
                    f"{percent(item.get('portfolioAnnualReturnPct'))} | {percent(item.get('benchmarkAnnualReturnPct'))} | "
                    f"{percent(item.get('portfolioMaxDrawdownPct'))} | {percent(item.get('averageGrossPct'))} |"
                )
    subset_base = payload["executionSubset"]["base"]["segments"]["test"]
    subset_stress = payload["executionSubset"]["stress"]["segments"]["test"]
    lines.extend(
        [
            "",
            "## 当前可执行子集诊断",
            "",
            "> 该子集冻结为报告生成时同时通过合约价差/换手门槛且具备研究历史的股票。它存在今天流动性选择偏差，只用于判断锁模后的合约前瞻组合是否可构造。",
            "",
            f"- 冻结股票数：{payload['executionSubset']['stocks']}；月频测试期基础成本主动年化 {percent(subset_base.get('annualizedActiveReturnPct'))}、跟踪误差 {percent(subset_base.get('realizedTrackingErrorPct'))}、IR `{number(subset_base.get('informationRatio')):.3f}`。",
            f"- 压力成本主动年化：{percent(subset_stress.get('annualizedActiveReturnPct'))}。",
            f"- 中性化综合测试 IC：`{payload['executionSubset']['ic']['test']['neutralized_composite']['meanIc']:.4f}`。",
        ]
    )
    lines.extend(
        [
            "",
            "## 因子样本外 IC",
            "",
            "| 调仓 | 因子 | 平均 Rank IC | t 值 | 正 IC 比例 | 期数 |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for mode in ("monthly", "biweekly"):
        summary = payload["results"][mode]["ic"]["test"]
        for factor in IC_FACTORS:
            item = summary[factor]
            lines.append(
                f"| {mode} | {factor} | {item['meanIc']:.4f} | {item['tStatistic']:.3f} | "
                f"{item['positivePct']:.1f}% | {item['observations']} |"
            )
    monthly_test = payload["results"]["monthly"]["base"]["segments"]["test"]
    monthly_stress = payload["results"]["monthly"]["stress"]["segments"]["test"]
    bootstrap = payload["results"]["monthly"]["base"]["testActiveBootstrap"]
    lines.extend(
        [
            "",
            "## 主版本判定",
            "",
            f"- 月频测试期基础成本主动年化：{percent(monthly_test.get('annualizedActiveReturnPct'))}，IR `{number(monthly_test.get('informationRatio')):.3f}`。",
            f"- 压力成本主动年化：{percent(monthly_stress.get('annualizedActiveReturnPct'))}。",
            f"- 测试期月收益三个月块 bootstrap 年化 95% 区间：{bootstrap['lower95Pct']:.2f}% 至 {bootstrap['upper95Pct']:.2f}%（中位数 {bootstrap['medianPct']:.2f}%）。",
            f"- 是否满足锁模进入全新合约前瞻观察的门槛：`{decision['eligibleForLockedForwardObservation']}`。",
            f"- 状态：`{decision['status']}`；仿真/实盘资格：`False`。",
            f"- 原因：{decision['reason']}",
            "",
            "## 不能从本回测推出的结论",
            "",
            "- 历史宇宙由今天的 Nasdaq-100 与今天存在的 OKX 合约交集构成，仍有当前成分/当前合约选择偏差；它不是完整的历史 Nasdaq-100 成分重建。",
            "- SEC `filed` 提供日期但不总提供可交易时刻；本研究用“严格早于调仓日”再滞后一日的规则保守处理。后续修订不会回填到首次披露日前。",
            "- Yahoo 复权价格适合验证慢选股信号，但不是机构级点时证券主文件；退市股、历史行业变更和历史借券可得性未被完整重建。",
            "- OKX 合约多数上市很短，历史 K 线不能恢复真实 bid/ask、深度、排队、资金费路径和基差成交。本报告只保留生成时的公开快照；任何执行结论必须来自锁模后的新前瞻样本。",
            "- 即使本次现货 alpha 为正，也不授权直接实盘；真正长期承载仍优先现金 QQQ/股票账户，TRADFI 仅作为小规模 overlay 候选。",
            "",
            "## 产物",
            "",
            "- `summary.json`：完整配置、样本、结果和判定。",
            "- `universe.csv` / `contract_snapshot.csv`：映射、排除与当前合约准入。",
            "- `*_daily.csv`、`*_weights.csv`、`*_factor_ic.csv`：可复核的日收益、主动权重和因子 IC。",
            "- `rebalance_diagnostics.csv`：每次调仓的约束残差、事前跟踪误差及 point-in-time 覆盖。",
        ]
    )
    if decision["eligibleForLockedForwardObservation"]:
        lines.extend(
            [
                "- `locked_model.json`：冻结的只读前瞻模型、可执行子集和最新完成月末权重；明确禁止仿真/实盘。",
                "- `forward_snapshot_0001.json`：锁模后的第一个公共合约价差、换手与资金费快照。",
            ]
        )
    return "\n".join(lines) + "\n"


def decision_payload(
    monthly_base: pd.DataFrame,
    monthly_stress: pd.DataFrame,
    monthly_ic: dict[str, Any],
    execution_base: pd.DataFrame,
    execution_stress: pd.DataFrame,
    execution_ic: dict[str, Any],
    *,
    current_liquid_stocks: int,
    qqq_contract_eligible: bool,
) -> dict[str, Any]:
    segments = chronological_segments(monthly_base.index)
    test_dates = segments["test"]
    base = performance_metrics(monthly_base.loc[test_dates])
    stress = performance_metrics(monthly_stress.loc[test_dates])
    composite_ic = monthly_ic["neutralized_composite"]
    execution_segments = chronological_segments(execution_base.index)
    execution_test_dates = execution_segments["test"]
    execution_base_test = performance_metrics(execution_base.loc[execution_test_dates])
    execution_stress_test = performance_metrics(execution_stress.loc[execution_test_dates])
    execution_composite_ic = execution_ic["neutralized_composite"]
    checks = {
        "positiveBaseTestActiveReturn": base.get("annualizedActiveReturnPct", 0.0) > 0,
        "positiveStressTestActiveReturn": stress.get("annualizedActiveReturnPct", 0.0) > 0,
        "positiveTestInformationRatio": base.get("informationRatio", 0.0) > 0,
        "positiveTestNeutralizedCompositeIc": composite_ic.get("meanIc", 0.0) > 0,
        "positiveExecutableSubsetBaseTest": execution_base_test.get("annualizedActiveReturnPct", 0.0) > 0,
        "positiveExecutableSubsetStressTest": execution_stress_test.get("annualizedActiveReturnPct", 0.0) > 0,
        "positiveExecutableSubsetNeutralizedIc": execution_composite_ic.get("meanIc", 0.0) > 0,
        "trackingErrorWithinFourPct": 0 < base.get("realizedTrackingErrorPct", 0.0) <= 4.0,
        "sufficientCurrentLiquidContracts": current_liquid_stocks >= MIN_FORWARD_STOCKS,
        "qqqCoreContractCurrentlyEligible": qqq_contract_eligible,
    }
    eligible = all(checks.values())
    if eligible:
        reason = (
            "现货代理的主版本通过预注册方向门槛，且当前合约覆盖达到最低数量；可锁定模型开始全新的公共盘口/资金费/基差前瞻观察，但仍不能仿真或实盘。"
        )
    else:
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        reason = f"尚未通过进入合约前瞻观察的全部门槛：{failed}。不得通过测试后调参或删标的补救。"
    return {
        "status": "research_only",
        "eligibleForLockedForwardObservation": eligible,
        "eligibleForPaperOrLive": False,
        "checks": checks,
        "reason": reason,
    }


def main() -> int:
    args = parse_args()
    data_root = Path(args.data_root)
    output_dir = resolve_output_dir(args.output_dir)
    data_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    universe, contracts, universe_metadata = build_universe(
        data_root,
        refresh_universe=args.refresh_universe,
        refresh_sec=args.refresh_sec,
        min_turnover_usdt=args.min_current_turnover_usdt,
        max_spread_bps=args.max_current_spread_bps,
    )

    prices: dict[str, pd.DataFrame] = {}
    price_exclusions: dict[str, str] = {}
    for symbol in ["QQQ", *sorted(universe)]:
        try:
            frame = load_yahoo_daily(
                symbol,
                data_root,
                history_range=args.history_range,
                refresh=args.refresh_prices,
            )
        except Exception as exc:
            price_exclusions[symbol] = f"{type(exc).__name__}:{exc}"
            continue
        prices[symbol] = frame
        if symbol in universe:
            universe[symbol]["priceRows"] = len(frame)
            universe[symbol]["priceStart"] = frame.index[0].date().isoformat()
            universe[symbol]["priceEnd"] = frame.index[-1].date().isoformat()
    if "QQQ" not in prices:
        raise RuntimeError(f"QQQ price history unavailable: {price_exclusions.get('QQQ')}")
    for symbol in list(universe):
        if symbol not in prices or len(prices[symbol]) < args.min_price_history_days:
            price_exclusions[symbol] = price_exclusions.get(symbol, "insufficient_price_history")
            universe.pop(symbol)

    fundamentals: dict[str, dict[str, list[dict[str, Any]]]] = {}
    sec_exclusions: dict[str, str] = {}
    for symbol in list(universe):
        try:
            payload = load_company_facts(int(universe[symbol]["cik"]), data_root, refresh=args.refresh_sec)
            prepared = prepare_fundamental_records(payload)
            if not prepared["assets"] or not prepared["shares"]:
                raise ValueError("missing assets or consolidated share facts")
            fundamentals[symbol] = prepared
        except Exception as exc:
            sec_exclusions[symbol] = f"{type(exc).__name__}:{exc}"
            universe.pop(symbol)

    if len(universe) < 8:
        raise RuntimeError(f"Only {len(universe)} stocks survived point-in-time data admission")
    prices = {symbol: frame for symbol, frame in prices.items() if symbol == "QQQ" or symbol in universe}
    return_panel = aligned_return_panel(prices, sorted(universe))

    mode_results: dict[str, Any] = {}
    daily_frames: dict[tuple[str, str], pd.DataFrame] = {}
    all_diagnostics: list[dict[str, Any]] = []
    for mode in ("monthly", "biweekly"):
        weights, diagnostics, signals = build_weight_history(
            mode,
            universe,
            prices,
            fundamentals,
            gross_limit=args.active_gross_limit,
            single_stock_limit=args.single_stock_limit,
            tracking_error_limit=args.tracking_error_limit,
        )
        if len(weights) < 12:
            raise RuntimeError(f"Only {len(weights)} valid {mode} rebalances")
        base_daily, base_trades = simulate_overlay(
            return_panel,
            weights,
            transaction_cost_bps=BASE_TRANSACTION_COST_BPS,
            short_borrow_bps=BASE_SHORT_BORROW_BPS,
        )
        stress_daily, stress_trades = simulate_overlay(
            return_panel,
            weights,
            transaction_cost_bps=STRESS_TRANSACTION_COST_BPS,
            short_borrow_bps=STRESS_SHORT_BORROW_BPS,
        )
        ic_rows = factor_ic_rows(signals, prices, weights)
        date_segments = chronological_segments(base_daily.index)
        ic_summary = {
            name: summarize_ic(
                ic_rows,
                dates[0].date().isoformat(),
                dates[-1].date().isoformat(),
            )
            for name, dates in date_segments.items()
            if len(dates)
        }
        mode_results[mode] = {
            "base": {
                "segments": segment_metrics(base_daily),
                "testActiveBootstrap": bootstrap_active_return(base_daily.loc[date_segments["test"]]),
                "rebalances": len(base_trades),
            },
            "stress": {"segments": segment_metrics(stress_daily), "rebalances": len(stress_trades)},
            "ic": ic_summary,
        }
        daily_frames[(mode, "base")] = base_daily
        daily_frames[(mode, "stress")] = stress_daily
        write_rows_csv(output_dir / f"{mode}_base_daily.csv", frame_rows(base_daily))
        write_rows_csv(output_dir / f"{mode}_stress_daily.csv", frame_rows(stress_daily))
        write_rows_csv(output_dir / f"{mode}_weights.csv", weight_rows(mode, weights))
        write_rows_csv(output_dir / f"{mode}_factor_ic.csv", ic_rows)
        all_diagnostics.extend(diagnostics)

    current_liquid = sum(
        bool(contracts.get(symbol, {}).get("eligible")) for symbol in universe
    )
    qqq_eligible = bool(contracts.get("QQQ", {}).get("eligible"))
    execution_universe = {
        symbol: metadata
        for symbol, metadata in universe.items()
        if contracts.get(symbol, {}).get("eligible")
    }
    execution_weights, execution_diagnostics, execution_signals = build_weight_history(
        "monthly",
        execution_universe,
        prices,
        fundamentals,
        gross_limit=args.active_gross_limit,
        single_stock_limit=args.single_stock_limit,
        tracking_error_limit=args.tracking_error_limit,
    )
    if len(execution_weights) < 12:
        raise RuntimeError(f"Only {len(execution_weights)} valid current-liquid monthly rebalances")
    execution_base, execution_base_trades = simulate_overlay(
        return_panel[["QQQ", *sorted(execution_universe)]],
        execution_weights,
        transaction_cost_bps=BASE_TRANSACTION_COST_BPS,
        short_borrow_bps=BASE_SHORT_BORROW_BPS,
    )
    execution_stress, execution_stress_trades = simulate_overlay(
        return_panel[["QQQ", *sorted(execution_universe)]],
        execution_weights,
        transaction_cost_bps=STRESS_TRANSACTION_COST_BPS,
        short_borrow_bps=STRESS_SHORT_BORROW_BPS,
    )
    execution_ic_rows = factor_ic_rows(execution_signals, prices, execution_weights)
    execution_segments = chronological_segments(execution_base.index)
    execution_ic = {
        name: summarize_ic(
            execution_ic_rows,
            dates[0].date().isoformat(),
            dates[-1].date().isoformat(),
        )
        for name, dates in execution_segments.items()
        if len(dates)
    }
    execution_result = {
        "stocks": len(execution_universe),
        "symbols": sorted(execution_universe),
        "base": {
            "segments": segment_metrics(execution_base),
            "testActiveBootstrap": bootstrap_active_return(execution_base.loc[execution_segments["test"]]),
            "rebalances": len(execution_base_trades),
        },
        "stress": {
            "segments": segment_metrics(execution_stress),
            "rebalances": len(execution_stress_trades),
        },
        "ic": execution_ic,
    }
    write_rows_csv(output_dir / "monthly_current_liquid_base_daily.csv", frame_rows(execution_base))
    write_rows_csv(output_dir / "monthly_current_liquid_stress_daily.csv", frame_rows(execution_stress))
    write_rows_csv(
        output_dir / "monthly_current_liquid_weights.csv",
        weight_rows("monthly_current_liquid", execution_weights),
    )
    write_rows_csv(output_dir / "monthly_current_liquid_factor_ic.csv", execution_ic_rows)
    all_diagnostics.extend(
        [{**row, "mode": "monthly_current_liquid"} for row in execution_diagnostics]
    )
    decision = decision_payload(
        daily_frames[("monthly", "base")],
        daily_frames[("monthly", "stress")],
        mode_results["monthly"]["ic"]["test"],
        execution_base,
        execution_stress,
        execution_ic["test"],
        current_liquid_stocks=current_liquid,
        qqq_contract_eligible=qqq_eligible,
    )
    # The primary frames above are deterministic; retain only summarized data in JSON.
    universe_metadata.update(
        {
            "backtestUniverse": len(universe),
            "currentlyLiquidStocks": current_liquid,
            "qqqContractEligible": qqq_eligible,
            "priceExclusions": price_exclusions,
            "secExclusions": sec_exclusions,
        }
    )
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_qqq_point_in_time_active_enhancement",
        "config": {
            "primaryRebalance": "monthly",
            "diagnosticRebalance": "biweekly",
            "factors": ["12-1_momentum", "quality", "value", "low_residual_volatility"],
            "factorWeights": "equal",
            "secAvailabilityRule": "filed_date_strictly_before_rebalance_date",
            "activeGrossLimitPct": args.active_gross_limit * 100.0,
            "singleStockLimitPct": args.single_stock_limit * 100.0,
            "trackingErrorLimitPct": args.tracking_error_limit * 100.0,
            "minPriceHistoryDays": args.min_price_history_days,
            "baseTransactionCostBps": BASE_TRANSACTION_COST_BPS,
            "baseShortBorrowBpsAnnual": BASE_SHORT_BORROW_BPS,
            "stressTransactionCostBps": STRESS_TRANSACTION_COST_BPS,
            "stressShortBorrowBpsAnnual": STRESS_SHORT_BORROW_BPS,
            "currentLiquidityMinimumTurnoverUsdt": args.min_current_turnover_usdt,
            "currentLiquidityMaximumSpreadBps": args.max_current_spread_bps,
        },
        "universe": universe_metadata,
        "researchUniverse": universe,
        "contractSnapshot": contracts,
        "results": mode_results,
        "executionSubset": execution_result,
        "decision": decision,
        "limitations": [
            "current_constituent_and_current_contract_selection_bias",
            "no_complete_historical_delisting_or_industry_master",
            "sec_filed_date_has_no_uniform_tradeable_timestamp",
            "yahoo_adjusted_daily_data_is_not_institutional_point_in_time_security_master",
            "contract_execution_funding_basis_spread_depth_and_queue_require_new_forward_sample",
        ],
    }
    safe_payload = json_safe(payload)
    (output_dir / "summary.json").write_text(
        json.dumps(safe_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    universe_rows = [
        {**row, "exclusion": ""}
        for row in universe.values()
    ] + [
        {**row, "exclusion": ",".join(row.get("reasons", []))}
        for row in universe_metadata["excludedMappings"].values()
    ]
    write_rows_csv(output_dir / "universe.csv", universe_rows)
    write_rows_csv(output_dir / "contract_snapshot.csv", list(contracts.values()))
    write_rows_csv(output_dir / "rebalance_diagnostics.csv", all_diagnostics)
    if decision["eligibleForLockedForwardObservation"]:
        latest_date = max(execution_weights)
        latest_weights = execution_weights[latest_date]
        latest_signal = execution_signals[latest_date]
        lock_basis = {
            "primaryRebalance": "monthly",
            "factorWeights": "equal",
            "factors": ["12-1_momentum", "quality", "value", "low_residual_volatility"],
            "secAvailabilityRule": "filed_date_strictly_before_rebalance_date",
            "grossLimit": args.active_gross_limit,
            "singleStockLimit": args.single_stock_limit,
            "trackingErrorLimit": args.tracking_error_limit,
            "symbols": sorted(execution_universe),
        }
        model_id = hashlib.sha256(
            json.dumps(lock_basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        locked_model = {
            "modelId": f"qqq-pit-{model_id}",
            "lockedAt": safe_payload["generatedAt"],
            "status": "public_forward_observation_only",
            "paperOrLiveAuthorized": False,
            "qqqCoreWeight": 1.0,
            "basis": lock_basis,
            "latestSignalDate": latest_date.date().isoformat(),
            "activeWeights": {
                symbol: float(value)
                for symbol, value in latest_weights.items()
                if abs(float(value)) > 1e-10
            },
            "latestFactors": {
                symbol: {
                    key: json_safe(row[key])
                    for key in (
                        "momentum", "quality", "value", "low_residual_volatility", "composite",
                        "beta", "size_z", "latest_filed", "fiscal_end", "industry",
                    )
                }
                for symbol, row in latest_signal.iterrows()
            },
        }
        (output_dir / "locked_model.json").write_text(
            json.dumps(locked_model, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        forward_snapshot = {
            "modelId": locked_model["modelId"],
            "capturedAt": safe_payload["generatedAt"],
            "observationNumber": 1,
            "ordersOrAccountAccess": False,
            "contracts": {
                symbol: contracts[symbol]
                for symbol in ["QQQ", *sorted(execution_universe)]
                if symbol in contracts
            },
        }
        (output_dir / "forward_snapshot_0001.json").write_text(
            json.dumps(json_safe(forward_snapshot), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (output_dir / "report.md").write_text(markdown_report(safe_payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"backtest_universe={len(universe)} current_liquid_stocks={current_liquid}")
    print(f"decision={json.dumps(decision, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
