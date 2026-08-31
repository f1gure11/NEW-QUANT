"""Read-only OKX and public US-equity options gamma-exposure estimation.

The exchange does not publish a canonical dealer GEX number.  This module
joins OKX's public option instruments, option summary Greeks, and open
interest, then applies the common heuristic:

    GEX per 1% move = gamma * open_interest_in_underlying * spot**2 * 0.01

Calls are assigned a positive sign and puts a negative sign.  That sign is a
dealer-positioning assumption, not an observation of dealer inventory.  Stock
and ETF perpetuals are handled by :mod:`equity_gex`, with a strict 15-minute
source-age gate.  The module deliberately contains no order or account
methods.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from equity_gex import (
    DEFAULT_ALWAYS_SYMBOLS,
    DEFAULT_EQUITY_TOP_N,
    build_equity_gex_snapshot,
)


OPTION_FAMILY_BY_BASE = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
}
STABLE_QUOTES = {"USD", "USDT", "USDC", "USDG", "DAI"}
DEFAULT_TOP_N = 6
DEFAULT_EXPIRY_WINDOW_DAYS = 45


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


def _rows(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    data = response.get("data", [])
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _iso_from_ms(value: Any) -> str:
    timestamp = _num(value)
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat(timespec="seconds")


def _date_from_ms(value: Any) -> str:
    timestamp = _num(value)
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).date().isoformat()


def option_family_for_base(base: str) -> str:
    return OPTION_FAMILY_BY_BASE.get(str(base).upper(), "")


def market_base_and_quote(inst_id: str, inst_type: str) -> tuple[str, str]:
    parts = str(inst_id).split("-")
    if inst_type == "SPOT" and len(parts) == 2:
        return parts[0], parts[1]
    if inst_type == "SWAP" and len(parts) >= 3 and parts[-1] == "SWAP":
        return parts[0], parts[-2]
    return "", ""


def swap_turnover_usd(ticker: dict[str, Any], instrument: dict[str, Any]) -> float:
    """Estimate 24h quote turnover from contract volume and contract value."""

    last = _num(ticker.get("last"))
    contracts = _num(ticker.get("vol24h"))
    contract_value = _num(instrument.get("ctVal"), 1.0)
    if last <= 0 or contracts <= 0 or contract_value <= 0:
        return 0.0
    if str(instrument.get("ctType", "linear")) == "inverse":
        # Inverse contracts have a USD-denominated face value.
        return contracts * contract_value
    return contracts * contract_value * last


def spot_turnover_usd(ticker: dict[str, Any]) -> float:
    last = _num(ticker.get("last"))
    base_volume = _num(ticker.get("vol24h"))
    if last > 0 and base_volume > 0:
        return base_volume * last
    return _num(ticker.get("volCcy24h"))


def _rank_markets(
    rows: list[dict[str, Any]],
    *,
    inst_type: str,
    swap_instruments: dict[str, dict[str, Any]] | None = None,
    top_n: int = DEFAULT_TOP_N,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for ticker in rows:
        inst_id = str(ticker.get("instId", ""))
        base, quote = market_base_and_quote(inst_id, inst_type)
        if not base or quote not in STABLE_QUOTES:
            continue
        instrument = (swap_instruments or {}).get(inst_id, {})
        turnover = swap_turnover_usd(ticker, instrument) if inst_type == "SWAP" else spot_turnover_usd(ticker)
        if turnover <= 0:
            continue
        ranked.append(
            {
                "instType": inst_type,
                "instId": inst_id,
                "base": base,
                "quote": quote,
                "last": _clean(_num(ticker.get("last")), digits=12),
                "volume24h": _clean(_num(ticker.get("vol24h")), digits=8),
                "turnover24h": _clean(turnover, digits=2),
                "timestamp": _iso_from_ms(ticker.get("ts")),
                "optionFamily": option_family_for_base(base),
            }
        )
    ranked.sort(key=lambda row: _num(row.get("turnover24h")), reverse=True)
    for index, row in enumerate(ranked[:top_n], start=1):
        row["rank"] = index
        row["gexAvailable"] = bool(row.get("optionFamily"))
    return ranked[:top_n]


def _rank_equity_markets(
    rows: list[dict[str, Any]],
    *,
    swap_instruments: dict[str, dict[str, Any]],
    top_n: int = DEFAULT_EQUITY_TOP_N,
    always_symbols: tuple[str, ...] = DEFAULT_ALWAYS_SYMBOLS,
) -> list[dict[str, Any]]:
    """Rank OKX's stock/ETF perpetuals without querying CBOE for every symbol."""

    ranked: list[dict[str, Any]] = []
    for ticker in rows:
        inst_id = str(ticker.get("instId", ""))
        instrument = swap_instruments.get(inst_id, {})
        if str(instrument.get("instCategory", "")) != "3":
            continue
        base, quote = market_base_and_quote(inst_id, "SWAP")
        if not base or quote not in STABLE_QUOTES:
            continue
        turnover = swap_turnover_usd(ticker, instrument)
        ranked.append(
            {
                "instType": "SWAP",
                "instId": inst_id,
                "base": base,
                "quote": quote,
                "last": _clean(_num(ticker.get("last")), digits=12),
                "volume24h": _clean(_num(ticker.get("vol24h")), digits=8),
                "turnover24h": _clean(turnover, digits=2),
                "timestamp": _iso_from_ms(ticker.get("ts")),
                "gexAvailable": False,
            }
        )
    ranked.sort(key=lambda row: _num(row.get("turnover24h")), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    selected = ranked[: max(0, top_n)]
    selected_bases = {str(row.get("base", "")).upper() for row in selected}
    # Keep the examples visible even when their turnover falls out of the
    # top-N.  They still go through the same CBOE freshness/availability gate.
    for symbol in always_symbols:
        normalized = str(symbol).upper()
        if normalized in selected_bases:
            continue
        match = next((row for row in ranked if str(row.get("base", "")).upper() == normalized), None)
        if match is not None:
            selected.append(match)
            selected_bases.add(normalized)
    return selected


def _empty_profile() -> dict[float, dict[str, float]]:
    return {}


def _add_profile(profile: dict[float, dict[str, float]], strike: float, *, kind: str, value: float) -> None:
    bucket = profile.setdefault(strike, {"callGex": 0.0, "putGex": 0.0})
    bucket[kind] += value


def _gamma_flip(profile: list[dict[str, Any]]) -> float | None:
    if len(profile) < 2:
        return None
    previous_strike = _num(profile[0].get("strike"))
    previous_cumulative = _num(profile[0].get("netGex"))
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
    return {"strike": _clean(_num(row.get("strike")), digits=8), "gex": _clean(value, digits=2)}


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
        if put_strike:
            if put_strike < spot * 0.995:
                put_play = f"回踩 {put_strike:g} 附近出现止跌/放量再考虑轻仓低吸"
            elif put_strike > spot * 1.005:
                put_play = f"价格仍在 {put_strike:g} 下方，先等收复并回踩确认，不在墙下追多"
            else:
                put_play = f"围绕 {put_strike:g} 观察承接与假突破，确认后再轻仓"
        else:
            put_play = "回踩近端 Put 墙再观察低吸"
        if call_strike:
            if call_strike > spot * 1.005:
                call_play = f"反弹 {call_strike:g} 附近分批止盈，只有放量站稳才改变区间判断"
            elif call_strike < spot * 0.995:
                call_play = f"重新站回 {call_strike:g} 并放量，才考虑区间上沿被突破"
            else:
                call_play = f"接近 {call_strike:g} 先观察冲高回落，避免追价"
        else:
            call_play = "反弹近端 Call 墙附近先止盈"
        return {
            "level": level,
            "stance": "range",
            "title": "正 Gamma：偏震荡/均值回归",
            "summary": f"{location}，做市商对冲倾向压低短线波动；墙位附近更适合等反应，不追突破。",
            "playbook": [
                put_play,
                call_play,
            ],
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


def calculate_gex(
    *,
    underlying: str,
    option_family: str,
    spot_price: float,
    instruments: list[dict[str, Any]],
    open_interest: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    now_ms: int,
    expiry_window_days: int = DEFAULT_EXPIRY_WINDOW_DAYS,
) -> dict[str, Any]:
    """Calculate one option family's GEX from already-fetched public rows."""

    spot = _num(spot_price)
    if spot <= 0:
        raise ValueError(f"invalid spot price for {underlying}: {spot_price}")
    oi_by_id = {str(row.get("instId")): row for row in open_interest}
    summary_by_id = {str(row.get("instId")): row for row in summaries}
    now = _num(now_ms)
    window_ms = max(1, expiry_window_days) * 86_400_000
    all_profile = _empty_profile()
    near_profile = _empty_profile()
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
    nearest_expiry_ms = 0.0

    for instrument in instruments:
        inst_id = str(instrument.get("instId", ""))
        if not inst_id or instrument.get("state") not in {None, "live"}:
            continue
        expiry_ms = _num(instrument.get("expTime"))
        if expiry_ms <= now:
            continue
        strike = _num(instrument.get("stk"))
        if strike <= 0:
            continue
        oi_row = oi_by_id.get(inst_id, {})
        summary = summary_by_id.get(inst_id, {})
        oi_coin = _num(oi_row.get("oiCcy"))
        if oi_coin <= 0:
            oi_coin = _num(oi_row.get("oi")) * _num(instrument.get("ctMult"), 1.0)
        gamma = abs(_num(summary.get("gammaBS") or summary.get("gamma")))
        if oi_coin <= 0 or gamma <= 0:
            continue
        kind = "callGex" if str(instrument.get("optType", "")).upper() == "C" else "putGex"
        signed = 1.0 if kind == "callGex" else -1.0
        contribution = gamma * oi_coin * spot * spot * 0.01
        contribution *= signed
        in_near_term = expiry_ms - now <= window_ms
        option_count += 1
        if in_near_term:
            near_count += 1
        if nearest_expiry_ms <= 0 or expiry_ms < nearest_expiry_ms:
            nearest_expiry_ms = expiry_ms
        total_net += contribution
        total_abs += abs(contribution)
        total_oi_usd += oi_coin * spot
        if kind == "callGex":
            call_oi += oi_coin
        else:
            put_oi += oi_coin
        _add_profile(all_profile, strike, kind=kind, value=abs(contribution) if kind == "callGex" else -abs(contribution))
        expiry_key = _date_from_ms(expiry_ms)
        expiry_row = expiry_profile.setdefault(expiry_key, {"netGex": 0.0, "oiUsd": 0.0, "contracts": 0.0})
        expiry_row["netGex"] += contribution
        expiry_row["oiUsd"] += oi_coin * spot
        expiry_row["contracts"] += _num(oi_row.get("oi"))
        if in_near_term:
            near_net += contribution
            near_abs += abs(contribution)
            _add_profile(near_profile, strike, kind=kind, value=abs(contribution) if kind == "callGex" else -abs(contribution))

    selected_profile = near_profile if near_count >= 3 else all_profile
    profile: list[dict[str, Any]] = []
    cumulative = 0.0
    for strike in sorted(selected_profile):
        bucket = selected_profile[strike]
        net = bucket["callGex"] + bucket["putGex"]
        cumulative += net
        profile.append(
            {
                "strike": _clean(strike, digits=8),
                "callGex": _clean(bucket["callGex"], digits=2),
                "putGex": _clean(bucket["putGex"], digits=2),
                "netGex": _clean(net, digits=2),
                "cumulativeGex": _clean(cumulative, digits=2),
            }
        )
    selected_net = near_net if near_count >= 3 else total_net
    selected_abs = near_abs if near_count >= 3 else total_abs
    flip = _gamma_flip(profile)
    call_wall = _wall(profile, "callGex")
    put_wall = _wall(profile, "putGex", absolute=True)
    pcr = put_oi / call_oi if call_oi > 0 else None
    advice = _advice(
        net_gex=selected_net,
        spot=spot,
        gamma_flip=flip,
        call_wall=call_wall,
        put_wall=put_wall,
        option_count=near_count if near_count >= 3 else option_count,
        oi_usd=total_oi_usd,
    )
    expiries = [
        {
            "expiry": expiry,
            "netGex": _clean(values["netGex"], digits=2),
            "oiUsd": _clean(values["oiUsd"], digits=2),
            "contracts": _clean(values["contracts"], digits=4),
        }
        for expiry, values in sorted(expiry_profile.items())
    ]
    return {
        "underlying": underlying,
        "optionFamily": option_family,
        "spotPrice": _clean(spot, digits=8),
        "netGex": _clean(selected_net, digits=2),
        "allExpiryNetGex": _clean(total_net, digits=2),
        "grossGex": _clean(selected_abs, digits=2),
        "oiUsd": _clean(total_oi_usd, digits=2),
        "callOiUnderlying": _clean(call_oi, digits=8),
        "putOiUnderlying": _clean(put_oi, digits=8),
        "putCallOiRatio": _clean(pcr, digits=4),
        "optionCount": option_count,
        "nearTermOptionCount": near_count,
        "expiryWindowDays": expiry_window_days,
        "profileSource": "near_term" if near_count >= 3 else "all_expiries",
        "nearestExpiry": _iso_from_ms(nearest_expiry_ms),
        "gammaFlip": _clean(flip, digits=8),
        "callWall": call_wall,
        "putWall": put_wall,
        "regime": "positive_gamma" if selected_net >= 0 else "negative_gamma",
        "advice": advice,
        "profile": profile,
        "expiries": expiries,
    }


def _market_context(markets: list[dict[str, Any]], base: str) -> dict[str, Any]:
    for market in markets:
        if market.get("base") == base:
            return market
    return {}


def _fetch_family(client: Any, *, base: str, now_ms: int, expiry_window_days: int) -> dict[str, Any]:
    family = option_family_for_base(base)
    instruments = _rows(client.request("GET", "/api/v5/public/instruments", params={"instType": "OPTION", "uly": family}))
    open_interest = _rows(client.request("GET", "/api/v5/public/open-interest", params={"instType": "OPTION", "uly": family}))
    summaries = _rows(client.request("GET", "/api/v5/public/opt-summary", params={"uly": family}))
    index_rows = _rows(client.request("GET", "/api/v5/market/index-tickers", params={"instId": family}))
    spot = _num(index_rows[0].get("idxPx")) if index_rows else 0.0
    result = calculate_gex(
        underlying=base,
        option_family=family,
        spot_price=spot,
        instruments=instruments,
        open_interest=open_interest,
        summaries=summaries,
        now_ms=now_ms,
        expiry_window_days=expiry_window_days,
    )
    result["sourceTimestamp"] = max(
        [_iso_from_ms(row.get("ts")) for row in summaries + open_interest + index_rows if row.get("ts")],
        default="",
    )
    return result


def build_gex_snapshot(
    client: Any,
    *,
    top_n: int = DEFAULT_TOP_N,
    expiry_window_days: int = DEFAULT_EXPIRY_WINDOW_DAYS,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Fetch public OKX data and return a JSON-serialisable GEX dashboard payload."""

    now_ms = int(now_ms or datetime.now(timezone.utc).timestamp() * 1000)
    spot_tickers = _rows(client.request("GET", "/api/v5/market/tickers", params={"instType": "SPOT"}))
    swap_tickers = _rows(client.request("GET", "/api/v5/market/tickers", params={"instType": "SWAP"}))
    swap_rows = _rows(client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"}))
    swap_instruments = {str(row.get("instId")): row for row in swap_rows if row.get("instId")}
    spot_markets = _rank_markets(spot_tickers, inst_type="SPOT", top_n=top_n)
    swap_markets = _rank_markets(swap_tickers, inst_type="SWAP", swap_instruments=swap_instruments, top_n=top_n)
    equity_markets = _rank_equity_markets(
        swap_tickers,
        swap_instruments=swap_instruments,
        top_n=DEFAULT_EQUITY_TOP_N,
    )
    equity_snapshot = build_equity_gex_snapshot(equity_markets, now_ms=now_ms)
    spot_by_base = {row["base"]: row for row in spot_markets}
    swap_by_base = {row["base"]: row for row in swap_markets}
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for base in OPTION_FAMILY_BY_BASE:
        try:
            gex = _fetch_family(client, base=base, now_ms=now_ms, expiry_window_days=expiry_window_days)
            spot = spot_by_base.get(base, {})
            swap = swap_by_base.get(base, {})
            gex.update(
                {
                    "spotInstId": spot.get("instId", f"{base}-USDT"),
                    "swapInstId": swap.get("instId", f"{base}-USDT-SWAP"),
                    "spotTurnover24h": spot.get("turnover24h", 0),
                    "swapTurnover24h": swap.get("turnover24h", 0),
                    "totalTurnover24h": _clean(
                        _num(spot.get("turnover24h")) + _num(swap.get("turnover24h")), digits=2
                    ),
                }
            )
            rows.append(gex)
        except Exception as exc:
            errors.append({"underlying": base, "error": str(exc)[:240]})
    rows.sort(key=lambda row: _num(row.get("totalTurnover24h")), reverse=True)
    updated_at = datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(timespec="seconds")
    return {
        "ok": bool(rows),
        "updatedAt": updated_at,
        "cacheTtlSeconds": 300,
        "expiryWindowDays": expiry_window_days,
        "markets": {
            "spot": spot_markets,
            "swap": swap_markets,
            "equity": equity_snapshot["markets"],
        },
        "underlyings": rows,
        "equities": equity_snapshot["underlyings"],
        "errors": errors,
        "equityErrors": equity_snapshot["errors"],
        "methodology": {
            "formula": "gammaBS × OI_underlying × spot² × 0.01",
            "signConvention": "call + / put -",
            "oiUnit": "OI contracts × OKX ctMult",
            "source": "OKX public instruments, open-interest, opt-summary, index-tickers",
            "equitySource": equity_snapshot["methodology"],
            "warning": "dealer sign and inventory are inferred; this is an estimate, not exchange-published GEX；美股源时间超过 15 分钟不展示 GEX 数值",
        },
    }
