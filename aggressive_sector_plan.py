#!/usr/bin/env python3
"""Build a read-only, reviewable plan for a manually declared sector view.

The tool deliberately stops at a plan. It does not read private account state,
does not place orders, and does not start a bot. Sector baskets and risk rules
are loaded from config/aggressive_sector_playbook.json and are not selected from
the current day's winners.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from data_pipeline import load_candles
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PLAYBOOK = PROJECT_ROOT / "config" / "aggressive_sector_playbook.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "aggressive_sector_plan"
NEW_YORK = "America/New_York"


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def plain(value: Decimal | Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def normalize_inst_id(value: str) -> str:
    text = str(value).strip().upper().replace("_", "-")
    if not text:
        return ""
    return text if text.endswith("-USDT-SWAP") else f"{text}-USDT-SWAP"


def round_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def round_up(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_UP) * step


def load_playbook(path: Path = DEFAULT_PLAYBOOK) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValueError("aggressive sector playbook schemaVersion must be 1")
    if payload.get("status") != "research_only":
        raise ValueError("aggressive sector playbook must remain research_only")
    if payload.get("mode") != "manual_subjective_sector_plan":
        raise ValueError("aggressive sector playbook mode must remain manual_subjective_sector_plan")
    data = payload.get("data", {})
    risk = payload.get("risk", {})
    execution = payload.get("execution", {})
    if str(data.get("timeframe")) != "5m":
        raise ValueError("aggressive sector playbook timeframe must remain 5m")
    _parse_clock(str(data.get("sessionOpen", "")))
    _parse_clock(str(data.get("sessionClose", "")))
    if int(data.get("minSessionBars", 0)) <= 0 or int(data.get("atrWindow", 0)) <= 0:
        raise ValueError("aggressive sector playbook data windows must be positive")
    min_leverage = dec(risk.get("minLeverage"))
    max_leverage = dec(risk.get("maxLeverage"))
    default_leverage = dec(risk.get("defaultLeverage"))
    if min_leverage <= 0 or max_leverage < min_leverage or not min_leverage <= default_leverage <= max_leverage:
        raise ValueError("aggressive sector playbook leverage bounds are invalid")
    for field in ("defaultRiskPct", "costBufferPct", "maxMarginPct", "takeProfit1R", "takeProfit2R"):
        if dec(risk.get(field)) <= 0:
            raise ValueError(f"aggressive sector playbook {field} must be positive")
    close_pct = dec(risk.get("takeProfit1ClosePct"))
    if close_pct <= 0 or close_pct >= 100:
        raise ValueError("aggressive sector playbook takeProfit1ClosePct must be between 0 and 100")
    if dec(risk.get("takeProfit2R")) <= dec(risk.get("takeProfit1R")):
        raise ValueError("aggressive sector playbook takeProfit2R must exceed takeProfit1R")
    for field in ("minMinutesAfterOpen", "minMinutesBeforeClose", "openingRangeMinutes", "maxEntryDeviationBps"):
        if int(execution.get(field, 0)) <= 0:
            raise ValueError(f"aggressive sector playbook {field} must be positive")
    for field in (
        "requireVwapConfirmation",
        "requireOpeningRangeConfirmation",
        "flatBeforeUsClose",
        "allowAveragingDown",
        "allowStopReentry",
        "allowOvernight",
    ):
        if not isinstance(execution.get(field), bool):
            raise ValueError(f"aggressive sector playbook {field} must be boolean")
    sectors = payload.get("sectors")
    if not isinstance(sectors, dict) or not sectors:
        raise ValueError("aggressive sector playbook has no sectors")
    for sector_name, sector in sectors.items():
        legs = sector.get("legs") if isinstance(sector, dict) else None
        if not isinstance(legs, list) or not legs:
            raise ValueError(f"sector {sector_name} has no legs")
        weights = [dec(leg.get("riskWeight")) for leg in legs if isinstance(leg, dict)]
        if any(weight <= 0 for weight in weights) or sum(weights, Decimal("0")) != Decimal("1"):
            raise ValueError(f"sector {sector_name} risk weights must be positive and sum to 1")
        if len(legs) > int(payload.get("risk", {}).get("maxLegs", 2)):
            raise ValueError(f"sector {sector_name} exceeds maxLegs")
        inst_ids = [normalize_inst_id(leg.get("instId", "")) for leg in legs]
        if any(not inst_id for inst_id in inst_ids) or len(set(inst_ids)) != len(inst_ids):
            raise ValueError(f"sector {sector_name} instrument ids must be non-empty and unique")
        atr_multiplier = dec(sector.get("atrMultiplier"))
        stop_floor = dec(sector.get("stopFloorPct"))
        stop_cap = dec(sector.get("stopCapPct"))
        if atr_multiplier <= 0 or stop_floor <= 0 or stop_cap < stop_floor:
            raise ValueError(f"sector {sector_name} stop configuration is invalid")
        session = sector.get("session")
        if session is not None:
            if not isinstance(session, dict):
                raise ValueError(f"sector {sector_name} session override must be an object")
            if session.get("open") is not None:
                _parse_clock(str(session.get("open")))
            if session.get("close") is not None:
                _parse_clock(str(session.get("close")))
            if session.get("minSessionBars") is not None and int(session.get("minSessionBars") or 0) <= 0:
                raise ValueError(f"sector {sector_name} minSessionBars must be positive")
    return payload


def _parse_clock(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid session clock {value!r}") from exc


def resolve_sector_data_config(playbook: Mapping[str, Any], sector_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = dict(playbook.get("data", {}))
    session = (sector_config or {}).get("session") if isinstance(sector_config, Mapping) else None
    if isinstance(session, Mapping):
        if session.get("timezone"):
            data["sessionTimezone"] = str(session["timezone"])
        if session.get("open"):
            data["sessionOpen"] = str(session["open"])
        if session.get("close"):
            data["sessionClose"] = str(session["close"])
        if session.get("minSessionBars") is not None:
            data["minSessionBars"] = int(session["minSessionBars"])
    return data


def session_is_overnight(session_open: time, session_close: time) -> bool:
    return session_open >= session_close


def session_bounds(
    session_date: date,
    session_open: time,
    session_close: time,
    session_timezone: str,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(session_timezone)
    close_at = datetime.combine(session_date, session_close, tzinfo=tz)
    if session_is_overnight(session_open, session_close):
        open_at = datetime.combine(session_date - timedelta(days=1), session_open, tzinfo=tz)
    else:
        open_at = datetime.combine(session_date, session_open, tzinfo=tz)
    return open_at, close_at


def active_session_date(
    now: datetime,
    *,
    session_timezone: str = NEW_YORK,
    session_open: time = time(9, 30),
    session_close: time = time(16, 0),
) -> date | None:
    local = _as_utc(now).astimezone(ZoneInfo(session_timezone))
    current = local.time().replace(tzinfo=None)
    day = local.date()
    weekday = local.weekday()
    if not session_is_overnight(session_open, session_close):
        if weekday >= 5 or current < session_open or current >= session_close:
            return None
        return day
    if weekday == 5:
        return None
    if weekday == 6:
        return day + timedelta(days=1) if current >= session_open else None
    if weekday == 4:
        return day if current < session_close else None
    if current >= session_open:
        return day + timedelta(days=1)
    if current < session_close:
        return day
    return None


def _timeframe_minutes(value: str) -> int:
    text = str(value).strip().lower()
    if text.endswith("m") and text[:-1].isdigit() and int(text[:-1]) > 0:
        return int(text[:-1])
    raise ValueError(f"unsupported sector-plan timeframe {value!r}")


def _as_utc(value: datetime | None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _playbook_id(playbook: Mapping[str, Any]) -> str:
    encoded = json.dumps(playbook, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"aggressive-sector-playbook-{hashlib.sha256(encoded).hexdigest()[:16]}"


def parse_entry_prices(values: list[str]) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"--entry-price must be INST=PRICE, got {raw!r}")
        inst_raw, price_raw = raw.split("=", 1)
        inst_id = normalize_inst_id(inst_raw)
        price = dec(price_raw)
        if not inst_id or price <= 0:
            raise ValueError(f"invalid entry price {raw!r}")
        if inst_id in prices:
            raise ValueError(f"duplicate entry price for {inst_id}")
        prices[inst_id] = price
    return prices


def _session_rows(
    candles: pd.DataFrame,
    *,
    min_session_bars: int,
    session_timezone: str = NEW_YORK,
    session_open: time = time(9, 30),
    session_close: time = time(16, 0),
    timeframe_minutes: int = 5,
) -> list[dict[str, Any]]:
    if candles is None or candles.empty:
        return []
    frame = candles.copy()
    if "time" not in frame.columns:
        return []
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"]).sort_values("time")
    session_dates: list[date] = []
    for timestamp in frame["time"]:
        assigned = active_session_date(
            timestamp.to_pydatetime(),
            session_timezone=session_timezone,
            session_open=session_open,
            session_close=session_close,
        )
        session_dates.append(assigned)
    frame["session_date"] = session_dates
    frame = frame[frame["session_date"].notna()].copy()
    if frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    for session_date, group in frame.groupby("session_date", sort=True):
        open_at, close_at = session_bounds(session_date, session_open, session_close, session_timezone)
        expected_last_start = close_at - timedelta(minutes=timeframe_minutes)
        first_bar = group["time"].iloc[0].to_pydatetime()
        last_bar = group["time"].iloc[-1].to_pydatetime()
        if first_bar.tzinfo is None:
            first_bar = first_bar.replace(tzinfo=timezone.utc)
        if last_bar.tzinfo is None:
            last_bar = last_bar.replace(tzinfo=timezone.utc)
        if (
            len(group) < min_session_bars
            or first_bar > open_at
            or last_bar < expected_last_start
        ):
            continue
        rows.append(
            {
                "date": session_date.isoformat(),
                "open": dec(group["open"].iloc[0]),
                "high": max(dec(value) for value in group["high"]),
                "low": min(dec(value) for value in group["low"]),
                "close": dec(group["close"].iloc[-1]),
                "volume": sum((dec(value) for value in group.get("volume", [])), Decimal("0")),
                "bars": len(group),
            }
        )
    return rows


def parse_public_candles(rows: list[Any], inst_id: str, timeframe: str) -> pd.DataFrame:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            if isinstance(row, list):
                if len(row) < 6 or (len(row) > 8 and str(row[8]) != "1"):
                    continue
                ts, open_, high, low, close, volume = row[:6]
            elif isinstance(row, Mapping):
                if str(row.get("confirm", "1")) != "1":
                    continue
                ts = row.get("ts")
                open_, high, low, close, volume = (
                    row.get("o"),
                    row.get("h"),
                    row.get("l"),
                    row.get("c"),
                    row.get("vol"),
                )
            else:
                continue
            timestamp_ms = int(str(ts))
            parsed.append(
                {
                    "time": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                    "ts": timestamp_ms,
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": float(volume),
                    "inst_id": inst_id,
                    "timeframe": timeframe,
                }
            )
        except (TypeError, ValueError):
            continue
    if not parsed:
        return pd.DataFrame(columns=["time", "ts", "open", "high", "low", "close", "volume", "inst_id", "timeframe"])
    return pd.DataFrame(parsed).sort_values("time").drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)


def fetch_public_session_candles(
    inst_ids: list[str],
    timeframe: str,
    *,
    client: OkxRestClient | None = None,
) -> dict[str, pd.DataFrame]:
    """Read recent confirmed candles from OKX public market data only."""

    public_client = client or OkxRestClient()
    result: dict[str, pd.DataFrame] = {}
    for inst_id in inst_ids:
        try:
            response = public_client.request(
                "GET",
                "/api/v5/market/candles",
                params={"instId": inst_id, "bar": timeframe, "limit": "300"},
            )
            rows = response.get("data", []) if isinstance(response, dict) else []
            result[inst_id] = parse_public_candles(rows if isinstance(rows, list) else [], inst_id, timeframe)
        except Exception:  # noqa: BLE001 - a public API outage must fail the gate closed
            result[inst_id] = pd.DataFrame()
    return result


def intraday_confirmation(
    candles: pd.DataFrame,
    *,
    direction: str,
    as_of: datetime,
    data_config: Mapping[str, Any],
    execution_config: Mapping[str, Any],
) -> dict[str, Any]:
    session_timezone = str(data_config.get("sessionTimezone", NEW_YORK))
    session_open = _parse_clock(str(data_config.get("sessionOpen", "09:30")))
    session_close = _parse_clock(str(data_config.get("sessionClose", "16:00")))
    timeframe = str(data_config.get("timeframe", "5m"))
    timeframe_minutes = _timeframe_minutes(timeframe)
    as_of_utc = _as_utc(as_of)
    local_now = as_of_utc.astimezone(ZoneInfo(session_timezone))
    session_date = active_session_date(
        as_of_utc,
        session_timezone=session_timezone,
        session_open=session_open,
        session_close=session_close,
    )
    if session_date is None:
        reason = "outside_us_weekday_session"
        if session_is_overnight(session_open, session_close):
            reason = "outside_session"
        return {
            "status": "blocked",
            "reason": reason,
            "asOf": as_of_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sessionDate": local_now.date().isoformat(),
            "entryWindowStart": "",
            "entryWindowEnd": "",
            "dataSource": "OKX public confirmed 5m candles",
        }
    open_at, close_at = session_bounds(session_date, session_open, session_close, session_timezone)
    entry_start = open_at + timedelta(minutes=int(execution_config.get("minMinutesAfterOpen", 15)))
    entry_end = close_at - timedelta(minutes=int(execution_config.get("minMinutesBeforeClose", 60)))
    base: dict[str, Any] = {
        "status": "blocked",
        "reason": "",
        "asOf": as_of_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sessionDate": session_date.isoformat(),
        "entryWindowStart": entry_start.isoformat(),
        "entryWindowEnd": entry_end.isoformat(),
        "dataSource": "OKX public confirmed 5m candles",
    }
    if local_now < entry_start:
        return {**base, "reason": "entry_window_not_open"}
    if local_now >= entry_end:
        return {**base, "reason": "entry_window_closed"}
    if candles is None or candles.empty or "time" not in candles.columns:
        return {**base, "reason": "current_session_candles_missing"}

    frame = candles.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time"]).sort_values("time")
    assigned = [
        active_session_date(
            timestamp.to_pydatetime(),
            session_timezone=session_timezone,
            session_open=session_open,
            session_close=session_close,
        )
        for timestamp in frame["time"]
    ]
    candle_close = frame["time"] + pd.to_timedelta(timeframe_minutes, unit="m")
    frame = frame[(pd.Series(assigned, index=frame.index) == session_date) & (candle_close <= local_now)].copy()
    if frame.empty:
        return {**base, "reason": "no_completed_current_session_candles"}

    opening_range_minutes = int(execution_config.get("openingRangeMinutes", 15))
    opening_range_end = open_at + timedelta(minutes=opening_range_minutes)
    frame_local = frame["time"].dt.tz_convert(session_timezone)
    opening_range = frame[(frame_local >= open_at) & (frame_local < opening_range_end)]
    required_opening_bars = (opening_range_minutes + timeframe_minutes - 1) // timeframe_minutes
    if len(opening_range) < required_opening_bars:
        return {**base, "reason": "opening_range_incomplete", "completedBars": len(frame)}

    volume = frame["volume"].map(dec)
    total_volume = sum(volume, Decimal("0"))
    if total_volume <= 0:
        return {**base, "reason": "session_volume_missing", "completedBars": len(frame)}
    typical = (frame["high"].map(dec) + frame["low"].map(dec) + frame["close"].map(dec)) / Decimal("3")
    session_vwap = sum((price * vol for price, vol in zip(typical, volume)), Decimal("0")) / total_volume
    latest_close = dec(frame["close"].iloc[-1])
    opening_high = max(dec(value) for value in opening_range["high"])
    opening_low = min(dec(value) for value in opening_range["low"])
    vwap_pass = latest_close > session_vwap if direction == "long" else latest_close < session_vwap
    opening_range_pass = latest_close > opening_high if direction == "long" else latest_close < opening_low
    require_vwap = bool(execution_config.get("requireVwapConfirmation", True))
    require_opening = bool(execution_config.get("requireOpeningRangeConfirmation", True))
    confirmed = (vwap_pass or not require_vwap) and (opening_range_pass or not require_opening)
    return {
        **base,
        "status": "confirmed" if confirmed else "blocked",
        "reason": "direction_confirmed" if confirmed else "direction_not_confirmed",
        "completedBars": len(frame),
        "latestCandleAt": frame["time"].iloc[-1].isoformat(),
        "latestClose": latest_close,
        "sessionVwap": session_vwap,
        "openingRangeHigh": opening_high,
        "openingRangeLow": opening_low,
        "checks": {
            "vwapRequired": require_vwap,
            "vwapPassed": vwap_pass,
            "openingRangeRequired": require_opening,
            "openingRangePassed": opening_range_pass,
        },
    }


def atr14_from_sessions(sessions: list[dict[str, Any]], window: int = 14) -> dict[str, Any]:
    if not sessions:
        return {"status": "blocked", "reason": "no_complete_us_sessions", "atr": Decimal("0"), "atrPct": Decimal("0")}
    if len(sessions) < window + 1:
        return {
            "status": "blocked",
            "reason": f"need_at_least_{window + 1}_complete_us_sessions",
            "sessions": len(sessions),
            "atr": Decimal("0"),
            "atrPct": Decimal("0"),
        }
    true_ranges: list[Decimal] = []
    for index, row in enumerate(sessions):
        high = dec(row["high"])
        low = dec(row["low"])
        if index == 0:
            true_range = high - low
        else:
            previous_close = dec(sessions[index - 1]["close"])
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
    latest = sessions[-1]
    close = dec(latest["close"])
    atr_value = sum(true_ranges[-window:], Decimal("0")) / Decimal(window)
    atr_pct = atr_value / close * Decimal("100") if close > 0 else Decimal("0")
    return {
        "status": "ok" if atr_value > 0 and close > 0 else "blocked",
        "reason": "" if atr_value > 0 and close > 0 else "invalid_atr_or_close",
        "sessions": len(sessions),
        "asOf": latest["date"],
        "close": close,
        "atr": atr_value,
        "atrPct": atr_pct,
    }


def fetch_public_metadata(inst_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Read public contract metadata only; no account credentials are loaded."""

    client = OkxRestClient()
    result: dict[str, dict[str, Any]] = {}
    for inst_id in inst_ids:
        try:
            response = client.request(
                "GET",
                "/api/v5/public/instruments",
                params={"instType": "SWAP", "instId": inst_id},
            )
            data = response.get("data", []) if isinstance(response, dict) else []
            item = data[0] if data and isinstance(data[0], dict) else {}
            result[inst_id] = {
                "state": item.get("state", ""),
                "ctVal": item.get("ctVal", ""),
                "lotSz": item.get("lotSz", ""),
                "minSz": item.get("minSz", ""),
                "tickSz": item.get("tickSz", ""),
            }
        except Exception as exc:  # noqa: BLE001 - a public API outage is a review block
            result[inst_id] = {"error": str(exc)}
    return result


def _metadata_ready(metadata: Mapping[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(metadata, Mapping):
        return False, "public_contract_metadata_missing"
    if metadata.get("error"):
        return False, "public_contract_metadata_error"
    for field in ("ctVal", "lotSz", "minSz", "tickSz"):
        if dec(metadata.get(field)) <= 0:
            return False, f"invalid_contract_metadata_{field}"
    if metadata.get("state") not in (None, "", "live"):
        return False, f"contract_state_{metadata.get('state')}"
    return True, ""


def _price_levels(
    entry: Decimal,
    stop_pct: Decimal,
    direction: str,
    tick_sz: Decimal,
    take_profit_1_r: Decimal,
    take_profit_2_r: Decimal,
) -> dict[str, Decimal]:
    stop_fraction = stop_pct / Decimal("100")
    sign = Decimal("1") if direction == "long" else Decimal("-1")
    stop_raw = entry * (Decimal("1") - sign * stop_fraction)
    tp1_raw = entry * (Decimal("1") + sign * stop_fraction * take_profit_1_r)
    tp2_raw = entry * (Decimal("1") + sign * stop_fraction * take_profit_2_r)
    if direction == "long":
        return {
            "stopLossPrice": round_down(stop_raw, tick_sz),
            "takeProfit1Price": round_up(tp1_raw, tick_sz),
            "takeProfit2Price": round_up(tp2_raw, tick_sz),
        }
    return {
        "stopLossPrice": round_up(stop_raw, tick_sz),
        "takeProfit1Price": round_down(tp1_raw, tick_sz),
        "takeProfit2Price": round_down(tp2_raw, tick_sz),
    }


def build_sector_plan(
    *,
    sector: str,
    direction: str,
    equity: Decimal,
    leverage: Decimal,
    entry_prices: Mapping[str, Decimal] | None = None,
    playbook: Mapping[str, Any] | None = None,
    candles_loader: Callable[[str, str], pd.DataFrame] | None = None,
    market_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    current_session_candles: Mapping[str, pd.DataFrame] | None = None,
    as_of: datetime | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config = dict(playbook or load_playbook())
    sectors = config.get("sectors", {})
    risk_config = config.get("risk", {})
    data_config = config.get("data", {})
    execution_config = config.get("execution", {})
    entry_prices = {normalize_inst_id(key): dec(value) for key, value in (entry_prices or {}).items()}
    direction = str(direction).lower()
    equity = dec(equity)
    leverage = dec(leverage)
    as_of = _as_utc(as_of)
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    common = {
        "generatedAt": generated_at,
        "playbookId": _playbook_id(config),
        "mode": "manual_subjective_sector_plan",
        "researchStatus": "research_only",
        "sector": sector,
        "direction": direction,
        "dataSource": "data_lake via data_pipeline.load_candles",
        "execution": execution_config,
    }

    if sector not in sectors:
        return {**common, "status": "blocked", "reason": f"unknown_sector_{sector}", "items": []}
    if direction not in ("long", "short"):
        return {**common, "status": "blocked", "reason": "direction_must_be_long_or_short", "items": []}
    if equity <= 0:
        return {**common, "status": "blocked", "reason": "equity_must_be_positive", "items": []}
    min_leverage = dec(risk_config.get("minLeverage"), Decimal("2"))
    max_leverage = dec(risk_config.get("maxLeverage"), Decimal("5"))
    if leverage < min_leverage or leverage > max_leverage:
        return {
            **common,
            "status": "blocked",
            "reason": f"leverage_must_be_between_{plain(min_leverage)}_and_{plain(max_leverage)}",
            "items": [],
        }

    sector_config = sectors[sector]
    data_config = resolve_sector_data_config(config, sector_config)
    common["sectorLabel"] = sector_config.get("label", sector)
    common["thesis"] = sector_config.get("thesis", "")
    common["session"] = {
        "timezone": data_config.get("sessionTimezone"),
        "open": data_config.get("sessionOpen"),
        "close": data_config.get("sessionClose"),
    }
    legs = sector_config.get("legs", [])
    inst_ids = [normalize_inst_id(leg.get("instId", "")) for leg in legs]
    allowed = set(inst_ids)
    extras = sorted(set(entry_prices) - allowed)
    if extras:
        return {**common, "status": "blocked", "reason": f"entry_price_for_unknown_leg_{extras[0]}", "items": []}

    loader = candles_loader or load_candles
    min_bars = int(data_config.get("minSessionBars", 60))
    atr_window = int(data_config.get("atrWindow", 14))
    timeframe = str(data_config.get("timeframe", "5m"))
    session_timezone = str(data_config.get("sessionTimezone", NEW_YORK))
    session_open = _parse_clock(str(data_config.get("sessionOpen", "09:30")))
    session_close = _parse_clock(str(data_config.get("sessionClose", "16:00")))
    timeframe_minutes = _timeframe_minutes(timeframe)
    atr_by_inst: dict[str, dict[str, Any]] = {}
    for inst_id in inst_ids:
        try:
            candles = loader(inst_id, timeframe)
            sessions = _session_rows(
                candles,
                min_session_bars=min_bars,
                session_timezone=session_timezone,
                session_open=session_open,
                session_close=session_close,
                timeframe_minutes=timeframe_minutes,
            )
            atr_by_inst[inst_id] = atr14_from_sessions(sessions, atr_window)
        except Exception as exc:  # noqa: BLE001 - data gaps should block review
            atr_by_inst[inst_id] = {"status": "blocked", "reason": f"candle_load_error_{type(exc).__name__}"}

    price_risk_budget = equity * dec(risk_config.get("defaultRiskPct"), Decimal("2")) / Decimal("100")
    cost_buffer = equity * dec(risk_config.get("costBufferPct"), Decimal("0.5")) / Decimal("100")
    total_planned_budget = price_risk_budget + cost_buffer
    items: list[dict[str, Any]] = []
    total_margin = Decimal("0")
    total_actual_risk = Decimal("0")
    atr_multiplier = dec(sector_config.get("atrMultiplier"))
    stop_floor = dec(sector_config.get("stopFloorPct"))
    stop_cap = dec(sector_config.get("stopCapPct"))
    take_profit_1_r = dec(risk_config.get("takeProfit1R"), Decimal("1"))
    take_profit_2_r = dec(risk_config.get("takeProfit2R"), Decimal("1.5"))
    take_profit_1_close_fraction = dec(risk_config.get("takeProfit1ClosePct"), Decimal("50")) / Decimal("100")
    for leg in legs:
        inst_id = normalize_inst_id(leg.get("instId", ""))
        weight = dec(leg.get("riskWeight"))
        atr_info = atr_by_inst[inst_id]
        item: dict[str, Any] = {
            "instId": inst_id,
            "riskWeight": weight,
            "atr": atr_info.get("atr", Decimal("0")),
            "atr14Pct": atr_info.get("atrPct", Decimal("0")),
            "atrAsOf": atr_info.get("asOf", ""),
            "referencePrice": atr_info.get("close", Decimal("0")),
            "status": "reference_only" if not entry_prices else "blocked",
            "reason": atr_info.get("reason", ""),
        }
        if atr_info.get("status") != "ok":
            item["status"] = "blocked"
            items.append(item)
            continue
        stop_pct = min(max(atr_multiplier * dec(atr_info["atrPct"]), stop_floor), stop_cap)
        item["stopDistancePct"] = stop_pct
        item["legPriceRiskBudget"] = price_risk_budget * weight
        entry = entry_prices.get(inst_id)
        if entry is None:
            item["reason"] = "actual_entry_price_required_after_manual_confirmation"
            items.append(item)
            continue
        item["entryPrice"] = entry
        confirmation = intraday_confirmation(
            current_session_candles.get(inst_id, pd.DataFrame()) if current_session_candles else pd.DataFrame(),
            direction=direction,
            as_of=as_of,
            data_config=data_config,
            execution_config=execution_config,
        )
        item["entryGate"] = confirmation
        if confirmation.get("status") != "confirmed":
            item["reason"] = f"entry_gate_{confirmation.get('reason', 'blocked')}"
            items.append(item)
            continue
        latest_close = dec(confirmation.get("latestClose"))
        entry_deviation_bps = abs(entry / latest_close - Decimal("1")) * Decimal("10000") if latest_close > 0 else Decimal("0")
        item["entryDeviationBps"] = entry_deviation_bps
        max_entry_deviation_bps = dec(execution_config.get("maxEntryDeviationBps"), Decimal("100"))
        if latest_close <= 0 or entry_deviation_bps > max_entry_deviation_bps:
            item["reason"] = "entry_price_too_far_from_latest_public_close"
            items.append(item)
            continue
        metadata = market_metadata.get(inst_id) if market_metadata else None
        metadata_ok, metadata_reason = _metadata_ready(metadata)
        if not metadata_ok:
            item["reason"] = metadata_reason
            items.append(item)
            continue
        ct_val = dec(metadata["ctVal"])
        lot_sz = dec(metadata["lotSz"])
        min_sz = dec(metadata["minSz"])
        tick_sz = dec(metadata["tickSz"])
        target_notional = item["legPriceRiskBudget"] / (stop_pct / Decimal("100"))
        target_size = target_notional / (entry * ct_val)
        size = round_down(target_size, lot_sz)
        actual_notional = size * entry * ct_val
        actual_risk = actual_notional * stop_pct / Decimal("100")
        margin = actual_notional / leverage
        take_profit_1_size = round_down(size * take_profit_1_close_fraction, lot_sz)
        take_profit_2_size = size - take_profit_1_size
        levels = _price_levels(entry, stop_pct, direction, tick_sz, take_profit_1_r, take_profit_2_r)
        item.update(
            {
                "metadata": {key: metadata.get(key, "") for key in ("state", "ctVal", "lotSz", "minSz", "tickSz")},
                "targetNotional": target_notional,
                "targetSize": target_size,
                "size": size,
                "actualNotional": actual_notional,
                "actualPriceRisk": actual_risk,
                "margin": margin,
                "takeProfit1Size": take_profit_1_size,
                "takeProfit2Size": take_profit_2_size,
                **levels,
            }
        )
        if size < min_sz:
            item["status"] = "blocked"
            item["reason"] = "minimum_contract_exceeds_risk_budget"
        elif take_profit_1_size < min_sz or take_profit_2_size < min_sz:
            item["status"] = "blocked"
            item["reason"] = "lot_size_cannot_split_position_into_two_profit_targets"
        else:
            item["status"] = "ready_for_review"
            item["reason"] = "manual_entry_gate_and_account_preflight_required"
            total_margin += margin
            total_actual_risk += actual_risk
        items.append(item)

    max_margin = equity * dec(risk_config.get("maxMarginPct"), Decimal("50")) / Decimal("100")
    complete_entry = bool(entry_prices) and all(item.get("entryPrice") is not None for item in items)
    item_blocked = any(item.get("status") == "blocked" for item in items)
    if not entry_prices:
        status = "reference_only" if not item_blocked else "blocked"
    elif item_blocked or not complete_entry or total_margin > max_margin:
        status = "blocked"
        if total_margin > max_margin:
            common["reason"] = "aggregate_margin_exceeds_margin_cap"
    else:
        status = "ready_for_review"
    common.update(
        {
            "status": status,
            "risk": {
                "equity": equity,
                "priceRiskBudget": price_risk_budget,
                "costBuffer": cost_buffer,
                "totalPlannedBudget": total_planned_budget,
                "actualPriceRisk": total_actual_risk,
                "remainingPriceRiskBudget": max(Decimal("0"), price_risk_budget - total_actual_risk),
                "leverage": leverage,
                "totalMargin": total_margin,
                "marginPct": total_margin / equity * Decimal("100"),
                "maxMarginPct": dec(risk_config.get("maxMarginPct"), Decimal("50")),
                "takeProfit1R": take_profit_1_r,
                "takeProfit2R": take_profit_2_r,
                "takeProfit1ClosePct": dec(risk_config.get("takeProfit1ClosePct"), Decimal("50")),
            },
            "items": items,
            "reviewChecklist": [
                f"Wait at least {int(execution_config.get('minMinutesAfterOpen', 15))} minutes after the session open ({data_config.get('sessionOpen')} {data_config.get('sessionTimezone')}).",
                f"Require the computed public-candle VWAP and {int(execution_config.get('openingRangeMinutes', 15))}-minute opening-range gates to confirm the declared direction.",
                f"Reject an entered price more than {plain(dec(execution_config.get('maxEntryDeviationBps'), Decimal('100')))} bps from the latest completed public candle.",
                "Verify available equity, existing positions, pending orders, and contract metadata before any manual action.",
                "Use exchange-side protection orders where supported; do not average down or re-enter after a stop.",
                f"Flatten before the session close ({data_config.get('sessionClose')} {data_config.get('sessionTimezone')}); this plan does not authorize holding through the session break.",
            ],
            "warnings": [
                "This is a subjective beta execution template, not validated alpha; research_only.",
                "The size is risk-budgeted before fees/slippage. The costBuffer is disclosed separately and can consume additional equity.",
                "ready_for_review does not mean ready to trade and does not create a live command.",
            ],
        }
    )
    return jsonable(common)


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def markdown_report(payload: Mapping[str, Any]) -> str:
    risk = payload.get("risk", {})
    lines = [
        "# Aggressive Sector Plan",
        "",
        f"- Status: `{payload.get('status', '')}`",
        f"- Sector: `{payload.get('sector', '')}`",
        f"- Direction: `{payload.get('direction', '')}`",
        f"- Generated: `{payload.get('generatedAt', '')}`",
        f"- Playbook: `{payload.get('playbookId', '')}`",
        f"- Research status: `{payload.get('researchStatus', '')}`",
        "",
        "## Risk",
        "",
        f"- Equity: `{risk.get('equity', '')}`",
        f"- Price-stop risk budget: `{risk.get('priceRiskBudget', '')}`",
        f"- Cost/slippage buffer: `{risk.get('costBuffer', '')}`",
        f"- Total planned budget: `{risk.get('totalPlannedBudget', '')}`",
        f"- Leverage: `{risk.get('leverage', '')}x`",
        f"- Estimated margin: `{risk.get('totalMargin', '')}` ({risk.get('marginPct', '')}%)",
        "",
        "## Legs",
        "",
        "| Instrument | ATR14 | Stop | Entry | VWAP gate | OR gate | Size | Notional | Margin | TP1 | TP2 | Status |",
        "|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in payload.get("items", []):
        lines.append(
            "| {inst} | {atr}% | {stop}% | {entry} | {vwap} | {opening} | {size} | {notional} | {margin} | {tp1} | {tp2} | {status} |".format(
                inst=item.get("instId", ""),
                atr=item.get("atr14Pct", ""),
                stop=item.get("stopDistancePct", ""),
                entry=item.get("entryPrice", item.get("referencePrice", "")),
                vwap=item.get("entryGate", {}).get("checks", {}).get("vwapPassed", ""),
                opening=item.get("entryGate", {}).get("checks", {}).get("openingRangePassed", ""),
                size=f"{item.get('size', '')} ({item.get('takeProfit1Size', '')}/{item.get('takeProfit2Size', '')})",
                notional=item.get("actualNotional", ""),
                margin=item.get("margin", ""),
                tp1=item.get("takeProfit1Price", ""),
                tp2=item.get("takeProfit2Price", ""),
                status=item.get("status", ""),
            )
        )
    lines.extend(["", "## Review Checklist", ""])
    lines.extend(f"- {item}" for item in payload.get("reviewChecklist", []))
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in payload.get("warnings", []))
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a read-only manual sector plan; never places orders.")
    parser.add_argument("--sector", required=True, help="Fixed sector key, e.g. semiconductor or cloud_ai.")
    parser.add_argument("--direction", required=True, choices=("long", "short"))
    parser.add_argument("--equity", required=True, help="Account equity in USDT, used for risk math only.")
    parser.add_argument("--leverage", default="", help="Requested leverage; defaults to the playbook value.")
    parser.add_argument("--entry-price", action="append", default=[], metavar="INST=PRICE", help="Actual post-open entry price; repeat once per basket leg.")
    parser.add_argument("--playbook", default=str(DEFAULT_PLAYBOOK))
    parser.add_argument("--output-dir", default="", help="Output directory. Default creates a timestamped directory under reports/aggressive_sector_plan/.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        playbook = load_playbook(Path(args.playbook))
        entries = parse_entry_prices(args.entry_price)
        leverage = dec(args.leverage or playbook.get("risk", {}).get("defaultLeverage"))
        sectors = playbook.get("sectors", {})
        inst_ids = [normalize_inst_id(item["instId"]) for item in sectors.get(args.sector, {}).get("legs", [])]
        metadata = fetch_public_metadata(inst_ids) if entries else {}
        current_session_candles = fetch_public_session_candles(inst_ids, str(playbook.get("data", {}).get("timeframe", "5m"))) if entries else {}
        generated_at = datetime.now(timezone.utc)
        payload = build_sector_plan(
            sector=args.sector,
            direction=args.direction,
            equity=dec(args.equity),
            leverage=leverage,
            entry_prices=entries,
            playbook=playbook,
            market_metadata=metadata,
            current_session_candles=current_session_candles,
            as_of=generated_at,
            generated_at=generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR / generated_at.strftime("%Y%m%dT%H%M%SZ")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "sector_plan.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "sector_plan.md").write_text(markdown_report(payload), encoding="utf-8")
        print(f"sector_plan={output_dir}")
        print(f"sector_plan_status={payload.get('status')}")
        return 0 if payload.get("status") in ("reference_only", "ready_for_review") else 2
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"sector_plan_error={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
