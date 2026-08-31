"""Read-only GEX estimates for OKX stock/ETF perpetual underlyings.

OKX's stock-style perpetuals do not expose an OKX option chain.  This module
uses the public CBOE delayed-quotes JSON endpoint, the same data path used by
the open-source ``Matteo-Ferrara/gex-tracker`` project.  CBOE publishes the
underlying price and option-level ``gamma``/``open_interest`` values, which
lets us calculate the usual heuristic:

    GEX per 1% move = gamma * OI contracts * 100 * spot**2 * 0.01

Calls are positive and puts are negative by convention.  The CBOE underlying
quote timestamp is treated as a hard freshness gate: a row older than 15
minutes never exposes numeric GEX values to the dashboard.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
import json
import math
import re
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


CBOE_OPTIONS_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
CBOE_SOURCE_NAME = "CBOE delayed quotes"
NASDAQ_OPTIONS_URL = "https://api.nasdaq.com/api/quote/{symbol}/option-chain?assetclass={asset_class}"
NASDAQ_SOURCE_NAME = "Nasdaq public option chain"
EQUITY_GEX_MAX_AGE_SECONDS = 15 * 60
EQUITY_GEX_CONTRACT_SIZE = 100
DEFAULT_EQUITY_EXPIRY_WINDOW_DAYS = 45
DEFAULT_EQUITY_TOP_N = 8
DEFAULT_MAX_WORKERS = 6
# These are always included when OKX currently lists the corresponding stock
# contract, even if a temporary turnover spike pushes them below the top-N.
DEFAULT_ALWAYS_SYMBOLS = ("SPCX", "SNDK", "SKHY", "SKHYNIX")
_OPTION_RE = re.compile(r"^(?P<root>[A-Z]+)(?P<date>\d{6})(?P<kind>[CP])(?P<strike>\d{8})$")
_EASTERN = ZoneInfo("America/New_York")


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clean(value: float | None, *, digits: int = 8) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _iso_from_ms(value: float | int | None) -> str:
    timestamp = _num(value)
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(timespec="seconds")


def _source_ms(value: Any) -> int:
    """Parse CBOE's naive Eastern timestamp into UTC milliseconds."""

    if isinstance(value, (int, float)):
        number = _num(value)
        if number > 10_000_000_000:
            return int(number)
        if number > 0:
            return int(number * 1000)
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_EASTERN)
    return int(parsed.timestamp() * 1000)


def parse_option_symbol(value: Any) -> tuple[date, str, float] | None:
    """Return expiration date, C/P kind and strike from a CBOE OPRA symbol."""

    match = _OPTION_RE.match(str(value or "").strip().upper())
    if not match:
        return None
    try:
        expiry = datetime.strptime(match.group("date"), "%y%m%d").date()
        strike = int(match.group("strike")) / 1000.0
    except ValueError:
        return None
    return expiry, match.group("kind"), strike


def _expiry_ms(expiry: date) -> int:
    # US equity options stop trading at 16:00 Eastern on the expiration date.
    return int(datetime.combine(expiry, time(16, 0), tzinfo=_EASTERN).timestamp() * 1000)


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _black_scholes_price(spot: float, strike: float, years: float, volatility: float, kind: str) -> float:
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        return 0.0
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * volatility * volatility * years) / (volatility * root_t)
    d2 = d1 - volatility * root_t
    if kind == "C":
        return spot * _normal_cdf(d1) - strike * _normal_cdf(d2)
    return strike * _normal_cdf(-d2) - spot * _normal_cdf(-d1)


def _implied_volatility(price: float, spot: float, strike: float, years: float, kind: str) -> float | None:
    """Solve IV from a Nasdaq bid/ask midpoint without third-party packages."""

    if price <= 0 or spot <= 0 or strike <= 0 or years <= 0:
        return None
    intrinsic = max(0.0, spot - strike) if kind == "C" else max(0.0, strike - spot)
    upper = spot if kind == "C" else strike
    # A midpoint outside no-arbitrage bounds is usually a stale/empty quote.
    if price < intrinsic - 1e-6 or price > upper + 1e-6 or price <= intrinsic + 1e-8:
        return None
    low, high = 1e-6, 8.0
    if _black_scholes_price(spot, strike, years, high, kind) < price:
        return None
    for _ in range(64):
        middle = (low + high) / 2.0
        model = _black_scholes_price(spot, strike, years, middle, kind)
        if model < price:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _black_scholes_gamma(spot: float, strike: float, years: float, volatility: float) -> float:
    if spot <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        return 0.0
    root_t = math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * volatility * volatility * years) / (volatility * root_t)
    return _normal_pdf(d1) / (spot * volatility * root_t)


def _profile_value(profile: dict[float, dict[str, float]], strike: float, *, kind: str, value: float) -> None:
    bucket = profile.setdefault(strike, {"callGex": 0.0, "putGex": 0.0})
    bucket[kind] += value


def _profile_rows(profile: dict[float, dict[str, float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cumulative = 0.0
    for strike in sorted(profile):
        bucket = profile[strike]
        net = bucket["callGex"] + bucket["putGex"]
        cumulative += net
        rows.append(
            {
                "strike": _clean(strike),
                "callGex": _clean(bucket["callGex"], digits=2),
                "putGex": _clean(bucket["putGex"], digits=2),
                "netGex": _clean(net, digits=2),
                "cumulativeGex": _clean(cumulative, digits=2),
            }
        )
    return rows


def _gamma_flip(profile: list[dict[str, Any]]) -> float | None:
    if len(profile) < 2:
        return None
    previous_strike = _num(profile[0].get("strike"))
    previous_cumulative = _num(profile[0].get("cumulativeGex"))
    if previous_cumulative == 0:
        return previous_strike
    for row in profile[1:]:
        strike = _num(row.get("strike"))
        cumulative = _num(row.get("cumulativeGex"))
        if cumulative == 0:
            return strike
        if (previous_cumulative < 0 < cumulative) or (previous_cumulative > 0 > cumulative):
            span = strike - previous_strike
            if span == 0:
                return strike
            fraction = abs(previous_cumulative) / (abs(previous_cumulative) + abs(cumulative))
            return previous_strike + span * fraction
        previous_strike = strike
        previous_cumulative = cumulative
    return None


def _wall(profile: list[dict[str, Any]], field: str, *, absolute: bool = False) -> dict[str, Any] | None:
    if not profile:
        return None
    row = max(profile, key=lambda item: abs(_num(item.get(field))) if absolute else _num(item.get(field)))
    value = _num(row.get(field))
    if value == 0:
        return None
    return {"strike": _clean(_num(row.get("strike"))), "gex": _clean(value, digits=2)}


def _advice(
    *,
    net_gex: float,
    spot: float,
    gamma_flip: float | None,
    call_wall: dict[str, Any] | None,
    put_wall: dict[str, Any] | None,
    option_count: int,
    oi_usd: float,
) -> dict[str, Any]:
    if option_count < 3 or oi_usd <= 0 or spot <= 0:
        return {
            "level": "low",
            "stance": "wait",
            "title": "期权样本不足，观望",
            "summary": "当前可用 OI/Greeks 太少，GEX 只能作提示，暂不据此交易。",
            "playbook": ["先用价格结构、成交量和止损计划确认方向"],
            "invalidations": ["期权链恢复流动性前，不把单一墙位当作支撑或阻力"],
        }

    level = "medium" if oi_usd >= 1_000_000 else "low"
    location = ""
    if gamma_flip is not None:
        location = "在 Gamma Flip 上方" if spot >= gamma_flip else "在 Gamma Flip 下方"
    call_strike = call_wall.get("strike") if call_wall else None
    put_strike = put_wall.get("strike") if put_wall else None
    if net_gex >= 0:
        put_play = (
            f"回踩 {put_strike:g} 附近出现止跌/放量再考虑轻仓低吸"
            if put_strike
            else "回踩近端 Put 墙再观察低吸"
        )
        call_play = (
            f"反弹 {call_strike:g} 附近分批止盈，只有放量站稳才改变区间判断"
            if call_strike
            else "反弹近端 Call 墙附近先止盈"
        )
        return {
            "level": level,
            "stance": "range",
            "title": "正 Gamma：偏震荡/均值回归",
            "summary": f"{location}，对冲流倾向压低短线波动；墙位附近更适合等反应，不追突破。",
            "playbook": [put_play, call_play],
            "invalidations": ["有效放量突破墙位并连续收在 Gamma Flip 外侧", "现货与合约同步出现趋势性成交量"],
        }
    return {
        "level": level,
        "stance": "breakout",
        "title": "负 Gamma：偏趋势/波动扩张",
        "summary": f"{location}，对冲流可能顺着价格变化，短线不宜在区间中间反复摸顶抄底。",
        "playbook": [
            f"上破 {call_strike:g} 且成交量确认后才考虑顺势做多" if call_strike else "上破近端 Call 墙且成交量确认后再考虑做多",
            f"跌破 {put_strike:g} 且反抽不过后才考虑顺势做空" if put_strike else "跌破近端 Put 墙且反抽不过后再考虑做空",
        ],
        "invalidations": ["重新回到墙位之间并出现快速缩量", "止损距离超过单笔风险预算"],
    }


def _base_row(
    *,
    underlying: str,
    inst_id: str,
    option_symbol: str,
    status: str,
    reason: str = "",
    spot_price: float | None = None,
    source_ms: int = 0,
    now_ms: int,
    source: str = CBOE_SOURCE_NAME,
) -> dict[str, Any]:
    age = None if source_ms <= 0 else max(0.0, (now_ms - source_ms) / 1000.0)
    return {
        "underlying": underlying,
        "instId": inst_id,
        "optionSymbol": option_symbol,
        "market": "equity",
        "source": source,
        "sourceTimestamp": _iso_from_ms(source_ms),
        "sourceAgeSeconds": _clean(age, digits=1),
        "maxSourceAgeSeconds": EQUITY_GEX_MAX_AGE_SECONDS,
        "fresh": status == "ok",
        "status": status,
        "gexAvailable": status == "ok",
        "reason": reason,
        "spotPrice": _clean(spot_price, digits=8) if spot_price and spot_price > 0 else None,
    }


def calculate_equity_gex(
    *,
    underlying: str,
    inst_id: str,
    option_symbol: str,
    source_data: dict[str, Any],
    now_ms: int,
    expiry_window_days: int = DEFAULT_EQUITY_EXPIRY_WINDOW_DAYS,
    max_age_seconds: int = EQUITY_GEX_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Calculate a fresh public-chain-backed stock/ETF GEX row."""

    data = source_data.get("data") if isinstance(source_data, dict) else None
    source_name = str(source_data.get("source") or CBOE_SOURCE_NAME) if isinstance(source_data, dict) else CBOE_SOURCE_NAME
    if not isinstance(data, dict):
        return _base_row(
            underlying=underlying,
            inst_id=inst_id,
            option_symbol=option_symbol,
            status="unavailable",
            reason=f"{source_name} 返回中没有 data",
            now_ms=now_ms,
            source=source_name,
        )

    source_ms = _source_ms(data.get("last_trade_time"))
    age = None if source_ms <= 0 else max(0.0, (now_ms - source_ms) / 1000.0)
    base = _base_row(
        underlying=underlying,
        inst_id=inst_id,
        option_symbol=option_symbol,
        status="stale" if age is None or age > min(EQUITY_GEX_MAX_AGE_SECONDS, max_age_seconds) else "ok",
        reason=(
            f"{source_name} 标的行情没有可验证时间戳"
            if age is None
            else f"{source_name} 数据已超过 {min(EQUITY_GEX_MAX_AGE_SECONDS, max_age_seconds)} 秒"
            if age > min(EQUITY_GEX_MAX_AGE_SECONDS, max_age_seconds)
            else ""
        ),
        spot_price=_num(data.get("current_price")),
        source_ms=source_ms,
        now_ms=now_ms,
        source=source_name,
    )
    base["asOf"] = _iso_from_ms(source_ms)
    if base["status"] != "ok":
        # A stale quote may still contain old values.  Do not expose those as
        # actionable GEX to the UI.
        return base

    spot = _num(data.get("current_price"))
    if spot <= 0:
        base["status"] = "unavailable"
        base["fresh"] = False
        base["gexAvailable"] = False
        base["reason"] = f"{source_name} 没有有效标的价格"
        base["spotPrice"] = None
        return base

    now = _num(now_ms)
    window_ms = max(1, expiry_window_days) * 86_400_000
    all_profile: dict[float, dict[str, float]] = {}
    near_profile: dict[float, dict[str, float]] = {}
    expiry_profile: dict[str, dict[str, float]] = {}
    total_net = 0.0
    near_net = 0.0
    total_abs = 0.0
    near_abs = 0.0
    call_oi = 0.0
    put_oi = 0.0
    total_oi_usd = 0.0
    option_count = 0
    near_count = 0
    nearest_expiry_ms = 0

    options = data.get("options") if isinstance(data.get("options"), list) else []
    for option in options:
        if not isinstance(option, dict):
            continue
        parsed = parse_option_symbol(option.get("option"))
        if parsed is None:
            continue
        expiry, kind, strike = parsed
        expiry_ms = _expiry_ms(expiry)
        if expiry_ms <= now or strike <= 0:
            continue
        open_interest = _num(option.get("open_interest"))
        gamma = abs(_num(option.get("gamma")))
        if gamma <= 0:
            years = (expiry_ms - now) / (365.0 * 86_400_000.0)
            price = _num(option.get("price"))
            volatility = _implied_volatility(price, spot, strike, years, kind)
            gamma = _black_scholes_gamma(spot, strike, years, volatility or 0.0)
        if open_interest <= 0 or gamma <= 0:
            continue

        contribution = gamma * open_interest * EQUITY_GEX_CONTRACT_SIZE * spot * spot * 0.01
        if kind == "P":
            contribution = -contribution
            put_oi += open_interest
            profile_kind = "putGex"
        else:
            call_oi += open_interest
            profile_kind = "callGex"
        near_term = expiry_ms - now <= window_ms
        option_count += 1
        near_count += int(near_term)
        if nearest_expiry_ms <= 0 or expiry_ms < nearest_expiry_ms:
            nearest_expiry_ms = expiry_ms
        total_net += contribution
        total_abs += abs(contribution)
        total_oi_usd += open_interest * EQUITY_GEX_CONTRACT_SIZE * spot
        _profile_value(all_profile, strike, kind=profile_kind, value=abs(contribution) if kind == "C" else -abs(contribution))
        expiry_key = expiry.isoformat()
        expiry_row = expiry_profile.setdefault(expiry_key, {"netGex": 0.0, "oiUsd": 0.0, "contracts": 0.0})
        expiry_row["netGex"] += contribution
        expiry_row["oiUsd"] += open_interest * EQUITY_GEX_CONTRACT_SIZE * spot
        expiry_row["contracts"] += open_interest
        if near_term:
            near_net += contribution
            near_abs += abs(contribution)
            _profile_value(near_profile, strike, kind=profile_kind, value=abs(contribution) if kind == "C" else -abs(contribution))

    if option_count <= 0:
        base["status"] = "unavailable"
        base["fresh"] = False
        base["gexAvailable"] = False
        base["reason"] = "CBOE 期权链没有可用 OI/Gamma"
        return base

    selected_profile = near_profile if near_count >= 3 else all_profile
    profile = _profile_rows(selected_profile)
    selected_net = near_net if near_count >= 3 else total_net
    selected_abs = near_abs if near_count >= 3 else total_abs
    gamma_flip = _gamma_flip(profile)
    call_wall = _wall(profile, "callGex")
    put_wall = _wall(profile, "putGex", absolute=True)
    pcr = put_oi / call_oi if call_oi > 0 else None
    base.update(
        {
            "optionCount": option_count,
            "nearTermOptionCount": near_count,
            "expiryWindowDays": expiry_window_days,
            "profileSource": "near_term" if near_count >= 3 else "all_expiries",
            "nearestExpiry": _iso_from_ms(nearest_expiry_ms),
            "netGex": _clean(selected_net, digits=2),
            "allExpiryNetGex": _clean(total_net, digits=2),
            "grossGex": _clean(selected_abs, digits=2),
            "oiUsd": _clean(total_oi_usd, digits=2),
            "callOiContracts": _clean(call_oi, digits=2),
            "putOiContracts": _clean(put_oi, digits=2),
            "putCallOiRatio": _clean(pcr, digits=4),
            "gammaFlip": _clean(gamma_flip),
            "callWall": call_wall,
            "putWall": put_wall,
            "regime": "positive_gamma" if selected_net >= 0 else "negative_gamma",
            "advice": _advice(
                net_gex=selected_net,
                spot=spot,
                gamma_flip=gamma_flip,
                call_wall=call_wall,
                put_wall=put_wall,
                option_count=near_count if near_count >= 3 else option_count,
                oi_usd=total_oi_usd,
            ),
            "profile": profile,
            "expiries": [
                {
                    "expiry": expiry,
                    "netGex": _clean(values["netGex"], digits=2),
                    "oiUsd": _clean(values["oiUsd"], digits=2),
                    "contracts": _clean(values["contracts"], digits=2),
                }
                for expiry, values in sorted(expiry_profile.items())
            ],
            "contractSize": EQUITY_GEX_CONTRACT_SIZE,
        }
    )
    return base


def fetch_cboe_data(symbol: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Fetch one public CBOE delayed option-chain document."""

    url = CBOE_OPTIONS_URL.format(symbol=quote(symbol.upper(), safe=""))
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "okx-quant/1.0 (read-only GEX research)",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


def _text_number(value: Any) -> float:
    text = str(value or "").strip().replace(",", "").replace("$", "")
    if not text or text in {"--", "-", "N/A", "NA"}:
        return 0.0
    return _num(text)


def _parse_nasdaq_as_of(value: Any) -> tuple[float, int]:
    text = str(value or "")
    price_match = re.search(r"\$\s*([0-9,]+(?:\.\d+)?)", text)
    price = _text_number(price_match.group(1)) if price_match else 0.0
    as_of_match = re.search(r"AS OF\s+(.+?)\s+ET", text, flags=re.IGNORECASE)
    if not as_of_match:
        return price, 0
    raw = as_of_match.group(1).strip()
    parsed = None
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return price, 0
    parsed = parsed.replace(tzinfo=_EASTERN)
    return price, int(parsed.timestamp() * 1000)


def _parse_nasdaq_expiry(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _nasdaq_document(raw: dict[str, Any], *, symbol: str, asset_class: str) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("Nasdaq 返回中没有 data")
    status = raw.get("status") or {}
    if _num(status.get("rCode")) != 200:
        message = (status.get("bCodeMessage") or [{}])[0]
        detail = message.get("errorMessage") if isinstance(message, dict) else "symbol not found"
        raise RuntimeError(str(detail or "Nasdaq option chain unavailable"))
    table = data.get("table") if isinstance(data.get("table"), dict) else {}
    raw_rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    if not raw_rows:
        raise RuntimeError("Nasdaq option chain is empty")
    spot, source_ms = _parse_nasdaq_as_of(data.get("lastTrade"))
    options: list[dict[str, Any]] = []
    current_expiry: date | None = None
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        grouped_expiry = _parse_nasdaq_expiry(row.get("expirygroup"))
        if grouped_expiry is not None and not row.get("strike"):
            current_expiry = grouped_expiry
            continue
        strike = _text_number(row.get("strike"))
        if strike <= 0 or current_expiry is None:
            continue
        for kind, prefix in (("C", "c"), ("P", "p")):
            open_interest = _text_number(row.get(f"{prefix}_Openinterest"))
            if open_interest <= 0:
                continue
            bid = _text_number(row.get(f"{prefix}_Bid"))
            ask = _text_number(row.get(f"{prefix}_Ask"))
            last = _text_number(row.get(f"{prefix}_Last"))
            if bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
            else:
                price = bid or ask or last
            option_code = f"{symbol.upper()}{current_expiry:%y%m%d}{kind}{int(round(strike * 1000)):08d}"
            options.append(
                {
                    "option": option_code,
                    "price": price,
                    "open_interest": open_interest,
                    "bid": bid,
                    "ask": ask,
                    "last": last,
                }
            )
    if spot <= 0 or source_ms <= 0:
        raise RuntimeError("Nasdaq chain has no verifiable last-trade timestamp")
    return {
        "source": NASDAQ_SOURCE_NAME,
        "sourceUrl": NASDAQ_OPTIONS_URL.format(symbol=symbol.upper(), asset_class=asset_class),
        "data": {
            "current_price": spot,
            "last_trade_time": _iso_from_ms(source_ms),
            "options": options,
        },
    }


def fetch_nasdaq_data(symbol: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Fetch the public Nasdaq chain, trying stocks and then ETFs."""

    errors: list[str] = []
    for asset_class in ("stocks", "etf"):
        url = NASDAQ_OPTIONS_URL.format(symbol=quote(symbol.upper(), safe=""), asset_class=asset_class)
        request = Request(
            url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 okx-quant/1.0",
            },
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = json.load(response)
            return _nasdaq_document(raw, symbol=symbol, asset_class=asset_class)
        except Exception as exc:
            errors.append(f"{asset_class}: {str(exc)[:120]}")
    raise RuntimeError("; ".join(errors))


def fetch_equity_data(symbol: str, *, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Use the timestamped Nasdaq chain first, then the CBOE fallback."""

    try:
        return fetch_nasdaq_data(symbol, timeout_seconds=timeout_seconds)
    except Exception as nasdaq_exc:
        try:
            return fetch_cboe_data(symbol, timeout_seconds=timeout_seconds)
        except Exception as cboe_exc:
            raise RuntimeError(f"Nasdaq: {nasdaq_exc}; CBOE: {cboe_exc}") from cboe_exc


def _unavailable_row(*, market: dict[str, Any], option_symbol: str, reason: str, now_ms: int) -> dict[str, Any]:
    return _base_row(
        underlying=str(market.get("base") or ""),
        inst_id=str(market.get("instId") or ""),
        option_symbol=option_symbol,
        status="unavailable",
        reason=reason,
        spot_price=_num(market.get("last")),
        now_ms=now_ms,
    )


def _load_one(
    market: dict[str, Any],
    *,
    now_ms: int,
    expiry_window_days: int,
    fetcher: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(market.get("base") or "").upper()
    try:
        document = fetcher(symbol)
    except Exception as exc:
        return _unavailable_row(market=market, option_symbol=symbol, reason=f"CBOE 请求失败：{str(exc)[:180]}", now_ms=now_ms)
    row = calculate_equity_gex(
        underlying=symbol,
        inst_id=str(market.get("instId") or ""),
        option_symbol=symbol,
        source_data=document,
        now_ms=now_ms,
        expiry_window_days=expiry_window_days,
    )
    return row


def build_equity_gex_snapshot(
    markets: list[dict[str, Any]],
    *,
    now_ms: int,
    expiry_window_days: int = DEFAULT_EQUITY_EXPIRY_WINDOW_DAYS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    fetcher: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch and calculate GEX for the selected OKX stock/ETF markets."""

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for market in markets:
        base = str(market.get("base") or "").upper()
        if not base or base in seen:
            continue
        seen.add(base)
        selected.append(market)
    fetch = fetcher or (lambda symbol: fetch_equity_data(symbol))
    rows: list[dict[str, Any]] = []
    if selected:
        workers = max(1, min(max_workers, len(selected)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _load_one,
                    market,
                    now_ms=now_ms,
                    expiry_window_days=expiry_window_days,
                    fetcher=fetch,
                ): market
                for market in selected
            }
            for future in as_completed(futures):
                market = futures[future]
                try:
                    rows.append(future.result())
                except Exception as exc:  # defensive: one bad symbol must not hide the rest
                    rows.append(
                        _unavailable_row(
                            market=market,
                            option_symbol=str(market.get("base") or ""),
                            reason=f"GEX 计算失败：{str(exc)[:180]}",
                            now_ms=now_ms,
                        )
                    )

    order = {str(market.get("base") or "").upper(): index for index, market in enumerate(selected)}
    rows.sort(key=lambda row: order.get(str(row.get("underlying") or "").upper(), 999))
    status_by_base = {str(row.get("underlying") or "").upper(): row for row in rows}
    market_rows: list[dict[str, Any]] = []
    for market in selected:
        row = dict(market)
        result = status_by_base.get(str(market.get("base") or "").upper(), {})
        row["gexAvailable"] = result.get("status") == "ok"
        row["gexStatus"] = result.get("status", "unavailable")
        row["gexReason"] = result.get("reason", "")
        row["optionSymbol"] = result.get("optionSymbol", row.get("base", ""))
        row["sourceAgeSeconds"] = result.get("sourceAgeSeconds")
        market_rows.append(row)
    errors = [
        {"underlying": row.get("underlying", ""), "status": row.get("status"), "error": row.get("reason", "")}
        for row in rows
        if row.get("status") != "ok"
    ]
    return {
        "underlyings": rows,
        "markets": market_rows,
        "errors": errors,
        "methodology": {
            "formula": "Black–Scholes gamma × OI contracts × 100 × spot² × 0.01",
            "signConvention": "call + / put -",
            "oiUnit": "public-chain open_interest contracts × 100 shares",
            "source": f"{NASDAQ_SOURCE_NAME}; fallback {CBOE_SOURCE_NAME}",
            "sourceUrl": NASDAQ_OPTIONS_URL,
            "maxSourceAgeSeconds": EQUITY_GEX_MAX_AGE_SECONDS,
            "warning": "Nasdaq 期权链时间戳超过 15 分钟的标的不展示 GEX 数值；dealer sign 仍是估算约定",
        },
    }
