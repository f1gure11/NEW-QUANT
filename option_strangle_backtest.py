"""Backtest short-dated BTC/ETH long straddles and OTM strangles.

The source is Deribit's public TradingView OHLC endpoint.  Historical option
bars are quoted in the underlying coin, so each mark is converted to USD at
the contemporaneous perpetual price.  Historical bid/ask and Greeks are not
available from this endpoint: the backtest infers Black-Scholes Greeks from
the observed option price and applies explicit option slippage stress.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "option_strangle_backtest"
DEFAULT_CACHE = PROJECT_ROOT / "data" / "options" / "deribit_hourly_cache.json"
DERIBIT_BASE = "https://www.deribit.com/api/v2/public"
YEAR_MS = 365.25 * 86_400_000
HOUR_MS = 3_600_000
OTM_PCTS = (0.0, 1.0, 2.0, 3.0, 5.0)
SLIPPAGE_BPS = (50.0, 100.0, 200.0)
HEDGE_VARIANTS = (
    ("baseline", 5.0, 6, 4),
    ("threshold10", 10.0, 6, 4),
    ("threshold10_sparse", 10.0, 12, 2),
    ("threshold20_sparse", 20.0, 12, 2),
    ("threshold20_daily", 20.0, 24, 1),
    ("entry_only", 100.0, 24, 0),
)
DEFAULT_EXPIRIES = (
    "2022-09-30T08:00:00Z",
    "2023-03-31T08:00:00Z",
    "2023-09-29T08:00:00Z",
    "2024-03-29T08:00:00Z",
    "2024-09-27T08:00:00Z",
    "2025-03-28T08:00:00Z",
    "2025-09-26T08:00:00Z",
    "2026-03-27T08:00:00Z",
)


@dataclass(frozen=True, slots=True)
class Bar:
    ts: int
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class OptionPair:
    call_name: str
    put_name: str
    call_strike: float
    put_strike: float
    target_otm_pct: float
    actual_call_otm_pct: float
    actual_put_otm_pct: float
    call_bars: tuple[Bar, ...]
    put_bars: tuple[Bar, ...]


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    option_slippage_bps: float = 100.0
    option_fee_rate: float = 0.0003
    option_fee_cap_pct: float = 12.5
    hedge_cost_bps: float = 5.0
    delta_threshold_pct: float = 5.0
    hedge_interval_hours: int = 6
    max_rehedges: int = 4
    entry_hours_before_expiry: int = 24
    exit_hours_before_expiry: int = 1
    max_quote_staleness_hours: int = 6


@dataclass(slots=True)
class BacktestRow:
    underlying: str
    expiry: str
    sample: str
    target_otm_pct: float
    actual_call_otm_pct: float
    actual_put_otm_pct: float
    call_name: str
    put_name: str
    entry_time: str
    exit_time: str
    entry_spot: float
    exit_spot: float
    price_return_pct: float
    path_variation_pct: float
    entry_premium_usd: float
    entry_premium_pct_spot: float
    entry_theta_day_usd: float
    theta_pct_premium: float
    entry_gamma: float
    entry_option_delta: float
    exit_option_value_usd: float
    option_pnl_usd: float
    hedge_pnl_usd: float
    option_fees_usd: float
    hedge_cost_usd: float
    total_pnl_usd: float
    return_on_premium_pct: float
    rehedges: int
    max_abs_net_delta_pct: float
    option_slippage_bps: float
    hedge_variant: str
    delta_threshold_pct: float
    hedge_interval_hours: int
    max_rehedges_allowed: int
    entry_call_stale_hours: float
    entry_put_stale_hours: float
    exit_call_stale_hours: float
    exit_put_stale_hours: float


class DeribitHistory:
    def __init__(self, cache_path: Path, workers: int = 12) -> None:
        self.cache_path = cache_path
        self.workers = workers
        self._lock = Lock()
        self.cache: dict[str, list[dict[str, float]]] = {}
        if cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.cache = loaded
            except (OSError, json.JSONDecodeError):
                self.cache = {}

    @staticmethod
    def key(instrument: str, start_ms: int, end_ms: int) -> str:
        return f"{instrument}|{start_ms}|{end_ms}|60"

    def fetch_many(self, instruments: list[str], start_ms: int, end_ms: int) -> dict[str, tuple[Bar, ...]]:
        unique = sorted(set(instruments))
        missing = [item for item in unique if self.key(item, start_ms, end_ms) not in self.cache]
        if missing:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = {pool.submit(self._fetch_chart, item, start_ms, end_ms): item for item in missing}
                for future in as_completed(futures):
                    item = futures[future]
                    rows = future.result()
                    with self._lock:
                        self.cache[self.key(item, start_ms, end_ms)] = rows
            self.save()
        return {
            item: tuple(Bar(int(row["ts"]), float(row["close"]), float(row["volume"])) for row in self.cache.get(self.key(item, start_ms, end_ms), []))
            for item in unique
        }

    def _fetch_chart(self, instrument: str, start_ms: int, end_ms: int) -> list[dict[str, float]]:
        params = urllib.parse.urlencode(
            {
                "instrument_name": instrument,
                "start_timestamp": start_ms,
                "end_timestamp": end_ms,
                "resolution": "60",
            }
        )
        url = f"{DERIBIT_BASE}/get_tradingview_chart_data?{params}"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "okx-quant-research/1.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.load(response)
                result = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(result, dict) or result.get("status") != "ok":
                    return []
                ticks = result.get("ticks", [])
                closes = result.get("close", [])
                volumes = result.get("volume", [])
                rows = []
                for ts, close, volume in zip(ticks, closes, volumes):
                    close_value = finite(close)
                    if close_value <= 0:
                        continue
                    rows.append({"ts": int(ts), "close": close_value, "volume": finite(volume)})
                return rows
            except HTTPError as exc:
                if exc.code == 400:
                    return []
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
            except Exception as exc:  # Network retries are bounded and remain public/read-only.
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
        raise RuntimeError(f"Deribit history request failed for {instrument}: {last_error}")

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.cache_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.cache, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.cache_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest ATM/OTM BTC and ETH delta-hedged long options")
    parser.add_argument("--cache-file", default=str(DEFAULT_CACHE))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--expiry", action="append", dest="expiries", default=[])
    return parser.parse_args()


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def iso_ms(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000.0, timezone.utc).isoformat(timespec="seconds")


def parse_iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def expiry_code(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000.0, timezone.utc).strftime("%d%b%y").upper()


def strike_step(base: str, spot: float) -> float:
    if base == "BTC":
        return 250.0 if spot < 30_000 else 500.0 if spot < 50_000 else 1_000.0
    return 25.0 if spot < 2_500 else 50.0


def candidate_strikes(base: str, spot: float) -> list[float]:
    step = strike_step(base, spot)
    low = math.floor(spot * 0.92 / step) * step
    high = math.ceil(spot * 1.08 / step) * step
    return [low + index * step for index in range(int(round((high - low) / step)) + 1)]


def direct_bar(bars: tuple[Bar, ...], ts: int) -> Bar | None:
    return next((item for item in bars if item.ts == ts), None)


def traded_observation(bars: tuple[Bar, ...], ts: int, max_stale_hours: int) -> tuple[Bar, float] | None:
    candidates = [item for item in bars if item.ts <= ts and item.volume > 0]
    if not candidates:
        return None
    item = candidates[-1]
    stale = (ts - item.ts) / HOUR_MS
    return (item, stale) if stale <= max_stale_hours else None


def nearest_pair(
    base: str,
    expiry_ms: int,
    spot: float,
    target_otm_pct: float,
    charts: dict[str, tuple[Bar, ...]],
    entry_ts: int,
    exit_ts: int,
    max_stale_hours: int,
) -> OptionPair | None:
    code = expiry_code(expiry_ms)
    calls: list[tuple[float, str, tuple[Bar, ...]]] = []
    puts: list[tuple[float, str, tuple[Bar, ...]]] = []
    for strike in candidate_strikes(base, spot):
        strike_text = f"{strike:g}"
        for option_type, target in (("C", calls), ("P", puts)):
            name = f"{base}-{code}-{strike_text}-{option_type}"
            bars = charts.get(name, ())
            if not bars:
                continue
            if traded_observation(bars, entry_ts, max_stale_hours) is None:
                continue
            if traded_observation(bars, exit_ts, max_stale_hours) is None:
                continue
            target.append((strike, name, bars))
    if target_otm_pct == 0:
        call_by_strike = {item[0]: item for item in calls}
        common = [strike for strike in call_by_strike if any(item[0] == strike for item in puts)]
        if not common:
            return None
        strike = min(common, key=lambda value: abs(value / spot - 1.0))
        call = call_by_strike[strike]
        put = next(item for item in puts if item[0] == strike)
    else:
        valid_calls = [item for item in calls if item[0] >= spot]
        valid_puts = [item for item in puts if item[0] <= spot]
        if not valid_calls or not valid_puts:
            return None
        call_target = spot * (1.0 + target_otm_pct / 100.0)
        put_target = spot * (1.0 - target_otm_pct / 100.0)
        call = min(valid_calls, key=lambda item: abs(item[0] - call_target))
        put = min(valid_puts, key=lambda item: abs(item[0] - put_target))
    return OptionPair(
        call_name=call[1],
        put_name=put[1],
        call_strike=call[0],
        put_strike=put[0],
        target_otm_pct=target_otm_pct,
        actual_call_otm_pct=(call[0] / spot - 1.0) * 100.0,
        actual_put_otm_pct=(1.0 - put[0] / spot) * 100.0,
        call_bars=call[2],
        put_bars=put[2],
    )


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def bs_price(spot: float, strike: float, years: float, volatility: float, option_type: str) -> float:
    if years <= 0 or volatility <= 0:
        return max(0.0, spot - strike) if option_type == "C" else max(0.0, strike - spot)
    root = volatility * math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * volatility * volatility * years) / root
    d2 = d1 - root
    if option_type == "C":
        return spot * normal_cdf(d1) - strike * normal_cdf(d2)
    return strike * normal_cdf(-d2) - spot * normal_cdf(-d1)


def implied_volatility(price: float, spot: float, strike: float, years: float, option_type: str) -> float | None:
    intrinsic = max(0.0, spot - strike) if option_type == "C" else max(0.0, strike - spot)
    if price < intrinsic - max(0.01, spot * 1e-5) or price <= 0 or years <= 0:
        return None
    low, high = 1e-4, 5.0
    if bs_price(spot, strike, years, high, option_type) < price:
        return None
    for _ in range(60):
        mid = (low + high) / 2.0
        if bs_price(spot, strike, years, mid, option_type) < price:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def greeks_from_price(price: float, spot: float, strike: float, years: float, option_type: str) -> tuple[float, float, float]:
    iv = implied_volatility(price, spot, strike, years, option_type)
    intrinsic_delta = 1.0 if option_type == "C" and spot > strike else -1.0 if option_type == "P" and spot < strike else 0.0
    if iv is None or years <= 0:
        return intrinsic_delta, 0.0, 0.0
    root = iv * math.sqrt(years)
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * years) / root
    delta = normal_cdf(d1) if option_type == "C" else normal_cdf(d1) - 1.0
    gamma = normal_pdf(d1) / (spot * root)
    theta_day = -spot * normal_pdf(d1) * iv / (2.0 * math.sqrt(years)) / 365.25
    return delta, gamma, theta_day


def option_fee(price_usd: float, spot: float, config: BacktestConfig) -> float:
    return min(config.option_fee_rate * spot, config.option_fee_cap_pct / 100.0 * price_usd)


def run_trade(
    base: str,
    expiry_ms: int,
    underlying: tuple[Bar, ...],
    pair: OptionPair,
    config: BacktestConfig,
    sample: str,
    hedge_variant: str = "baseline",
) -> BacktestRow | None:
    entry_ts = expiry_ms - config.entry_hours_before_expiry * HOUR_MS
    exit_ts = expiry_ms - config.exit_hours_before_expiry * HOUR_MS
    path = [bar for bar in underlying if entry_ts <= bar.ts <= exit_ts]
    if len(path) < config.entry_hours_before_expiry - config.exit_hours_before_expiry:
        return None
    spot_by_ts = {bar.ts: bar.close for bar in path}
    entry_spot = spot_by_ts.get(entry_ts)
    exit_spot = spot_by_ts.get(exit_ts)
    if not entry_spot or not exit_spot:
        return None
    entry_call = traded_observation(pair.call_bars, entry_ts, config.max_quote_staleness_hours)
    entry_put = traded_observation(pair.put_bars, entry_ts, config.max_quote_staleness_hours)
    exit_call = traded_observation(pair.call_bars, exit_ts, config.max_quote_staleness_hours)
    exit_put = traded_observation(pair.put_bars, exit_ts, config.max_quote_staleness_hours)
    if not all((entry_call, entry_put, exit_call, exit_put)):
        return None
    assert entry_call is not None and entry_put is not None and exit_call is not None and exit_put is not None

    slip = config.option_slippage_bps / 10_000.0
    raw_call_usd = entry_call[0].close * entry_spot
    raw_put_usd = entry_put[0].close * entry_spot
    entry_call_usd = raw_call_usd * (1.0 + slip)
    entry_put_usd = raw_put_usd * (1.0 + slip)
    entry_premium = entry_call_usd + entry_put_usd
    entry_fees = option_fee(entry_call_usd, entry_spot, config) + option_fee(entry_put_usd, entry_spot, config)
    years = max((expiry_ms - entry_ts) / YEAR_MS, 1e-9)
    call_delta, call_gamma, call_theta = greeks_from_price(raw_call_usd, entry_spot, pair.call_strike, years, "C")
    put_delta, put_gamma, put_theta = greeks_from_price(raw_put_usd, entry_spot, pair.put_strike, years, "P")
    option_delta = call_delta + put_delta
    hedge_units = -option_delta
    hedge_cost = abs(hedge_units) * entry_spot * config.hedge_cost_bps / 10_000.0
    hedge_pnl = 0.0
    last_spot = entry_spot
    last_hedge_ts = entry_ts
    rehedges = 0
    max_abs_net_delta_pct = 0.0

    call_history = tuple(sorted(pair.call_bars, key=lambda item: item.ts))
    put_history = tuple(sorted(pair.put_bars, key=lambda item: item.ts))
    for bar in path[1:]:
        hedge_pnl += hedge_units * (bar.close - last_spot)
        last_spot = bar.close
        if bar.ts >= exit_ts:
            continue
        call_obs = traded_observation(call_history, bar.ts, config.max_quote_staleness_hours)
        put_obs = traded_observation(put_history, bar.ts, config.max_quote_staleness_hours)
        if call_obs is None or put_obs is None:
            continue
        remaining = max((expiry_ms - bar.ts) / YEAR_MS, 1e-9)
        current_call_usd = call_obs[0].close * bar.close
        current_put_usd = put_obs[0].close * bar.close
        current_call_delta = greeks_from_price(current_call_usd, bar.close, pair.call_strike, remaining, "C")[0]
        current_put_delta = greeks_from_price(current_put_usd, bar.close, pair.put_strike, remaining, "P")[0]
        current_option_delta = current_call_delta + current_put_delta
        net_delta = current_option_delta + hedge_units
        max_abs_net_delta_pct = max(max_abs_net_delta_pct, abs(net_delta) * 100.0)
        threshold = config.delta_threshold_pct / 100.0
        scheduled = bar.ts - last_hedge_ts >= config.hedge_interval_hours * HOUR_MS
        if rehedges < config.max_rehedges and (abs(net_delta) > threshold or scheduled):
            target = -current_option_delta
            change = target - hedge_units
            hedge_cost += abs(change) * bar.close * config.hedge_cost_bps / 10_000.0
            hedge_units = target
            last_hedge_ts = bar.ts
            rehedges += 1

    hedge_cost += abs(hedge_units) * exit_spot * config.hedge_cost_bps / 10_000.0
    exit_call_usd = exit_call[0].close * exit_spot * (1.0 - slip)
    exit_put_usd = exit_put[0].close * exit_spot * (1.0 - slip)
    exit_value = max(0.0, exit_call_usd) + max(0.0, exit_put_usd)
    exit_fees = option_fee(exit_call_usd, exit_spot, config) + option_fee(exit_put_usd, exit_spot, config)
    option_fees = entry_fees + exit_fees
    option_pnl = exit_value - entry_premium - option_fees
    total_pnl = option_pnl + hedge_pnl - hedge_cost
    log_returns = [math.log(current.close / previous.close) for previous, current in zip(path, path[1:]) if previous.close > 0 and current.close > 0]
    return BacktestRow(
        underlying=base,
        expiry=iso_ms(expiry_ms),
        sample=sample,
        target_otm_pct=pair.target_otm_pct,
        actual_call_otm_pct=pair.actual_call_otm_pct,
        actual_put_otm_pct=pair.actual_put_otm_pct,
        call_name=pair.call_name,
        put_name=pair.put_name,
        entry_time=iso_ms(entry_ts),
        exit_time=iso_ms(exit_ts),
        entry_spot=entry_spot,
        exit_spot=exit_spot,
        price_return_pct=(exit_spot / entry_spot - 1.0) * 100.0,
        path_variation_pct=sum(abs(item) for item in log_returns) * 100.0,
        entry_premium_usd=entry_premium + entry_fees,
        entry_premium_pct_spot=(entry_premium + entry_fees) / entry_spot * 100.0,
        entry_theta_day_usd=call_theta + put_theta,
        theta_pct_premium=abs(call_theta + put_theta) / max(entry_premium + entry_fees, 1e-12) * 100.0,
        entry_gamma=call_gamma + put_gamma,
        entry_option_delta=option_delta,
        exit_option_value_usd=exit_value,
        option_pnl_usd=option_pnl,
        hedge_pnl_usd=hedge_pnl,
        option_fees_usd=option_fees,
        hedge_cost_usd=hedge_cost,
        total_pnl_usd=total_pnl,
        return_on_premium_pct=total_pnl / max(entry_premium + entry_fees, 1e-12) * 100.0,
        rehedges=rehedges,
        max_abs_net_delta_pct=max_abs_net_delta_pct,
        option_slippage_bps=config.option_slippage_bps,
        hedge_variant=hedge_variant,
        delta_threshold_pct=config.delta_threshold_pct,
        hedge_interval_hours=config.hedge_interval_hours,
        max_rehedges_allowed=config.max_rehedges,
        entry_call_stale_hours=entry_call[1],
        entry_put_stale_hours=entry_put[1],
        exit_call_stale_hours=exit_call[1],
        exit_put_stale_hours=exit_put[1],
    )


def collect_rows(history: DeribitHistory, expiries: list[int]) -> list[BacktestRow]:
    rows: list[BacktestRow] = []
    for base in ("BTC", "ETH"):
        boundary = len(expiries) // 2
        for index, expiry_ms in enumerate(expiries):
            start_ms = expiry_ms - 40 * HOUR_MS
            underlying_name = f"{base}-PERPETUAL"
            underlying = history.fetch_many([underlying_name], start_ms, expiry_ms).get(underlying_name, ())
            entry_ts = expiry_ms - 24 * HOUR_MS
            entry_bar = direct_bar(underlying, entry_ts)
            if entry_bar is None:
                continue
            code = expiry_code(expiry_ms)
            instruments = [
                f"{base}-{code}-{strike:g}-{option_type}"
                for strike in candidate_strikes(base, entry_bar.close)
                for option_type in ("C", "P")
            ]
            charts = history.fetch_many(instruments, start_ms, expiry_ms)
            sample = "train" if index < boundary else "test"
            for otm_pct in OTM_PCTS:
                pair = nearest_pair(base, expiry_ms, entry_bar.close, otm_pct, charts, entry_ts, expiry_ms - HOUR_MS, 6)
                if pair is None:
                    continue
                for variant, threshold, interval, max_rehedges in HEDGE_VARIANTS:
                    for slippage in SLIPPAGE_BPS:
                        config = BacktestConfig(
                            option_slippage_bps=slippage,
                            delta_threshold_pct=threshold,
                            hedge_interval_hours=interval,
                            max_rehedges=max_rehedges,
                        )
                        row = run_trade(base, expiry_ms, underlying, pair, config, sample, variant)
                        if row is not None:
                            rows.append(row)
    return rows


def summarize(rows: list[BacktestRow]) -> list[dict[str, Any]]:
    result = []
    for base in ("BTC", "ETH"):
        for sample in ("train", "test"):
            for slippage in SLIPPAGE_BPS:
                for variant, threshold, interval, max_rehedges in HEDGE_VARIANTS:
                    for otm_pct in OTM_PCTS:
                        items = [row for row in rows if row.underlying == base and row.sample == sample and row.option_slippage_bps == slippage and row.target_otm_pct == otm_pct and row.hedge_variant == variant]
                        if not items:
                            continue
                        returns = [row.return_on_premium_pct for row in items]
                        result.append(
                            {
                                "underlying": base,
                                "sample": sample,
                                "option_slippage_bps": slippage,
                                "target_otm_pct": otm_pct,
                                "hedge_variant": variant,
                                "delta_threshold_pct": threshold,
                                "hedge_interval_hours": interval,
                                "max_rehedges": max_rehedges,
                                "count": len(items),
                                "positive": sum(value > 0 for value in returns),
                                "median_return_on_premium_pct": statistics.median(returns),
                                "mean_return_on_premium_pct": statistics.fmean(returns),
                                "worst_return_on_premium_pct": min(returns),
                                "median_premium_pct_spot": statistics.median(row.entry_premium_pct_spot for row in items),
                                "median_theta_pct_premium": statistics.median(row.theta_pct_premium for row in items),
                                "median_rehedges": statistics.median(row.rehedges for row in items),
                                "median_path_variation_pct": statistics.median(row.path_variation_pct for row in items),
                            }
                        )
    return result


def selected_by_training(summary: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for base in ("BTC", "ETH"):
        candidates = [item for item in summary if item["underlying"] == base and item["sample"] == "train" and item["option_slippage_bps"] == 100.0 and item["count"] >= 2]
        if candidates:
            best = max(candidates, key=lambda item: (item["median_return_on_premium_pct"], item["mean_return_on_premium_pct"]))
            selected[base] = {
                "targetOtmPct": float(best["target_otm_pct"]),
                "hedgeVariant": str(best["hedge_variant"]),
                "deltaThresholdPct": float(best["delta_threshold_pct"]),
                "hedgeIntervalHours": int(best["hedge_interval_hours"]),
                "maxRehedges": int(best["max_rehedges"]),
                "trainingMedianReturnOnPremiumPct": float(best["median_return_on_premium_pct"]),
            }
    return selected


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# BTC/ETH 短到期期权：ATM 与 OTM Delta 对冲回测",
        "",
        "> Deribit 公共历史成交价研究；不读取账户、不发送订单。",
        "",
        "## 数据与规则",
        "",
        f"- 到期日：{', '.join(item[:10] for item in payload['expiries'])}。前半段训练，后半段样本外测试。",
        "- 每笔在到期前 24 小时买入、到期前 1 小时平仓；比较 ATM 跨式和双边 1%/2%/3%/5% OTM 跨式。",
        "- 主表使用 Delta 5%、6 小时、最多 4 次的基准；优化表搜索更宽 Delta 容忍带和更低频率，永续成本 5 bps。",
        "- 期权历史接口只有成交价 OHLC，没有 bid/ask；主结果在买入和卖出两端各施加 1% 滑点，并报告 0.5%/2% 压力。",
        "- 入场/离场成交价必须来自 6 小时内有成交量的 K 线；Greeks 由成交价反推 Black-Scholes IV。",
        "",
        "## 样本外主结果（期权每边 1% 滑点）",
        "",
        "| 标的 | 结构 | 窗口 | 正收益 | 中位权利金 | Theta/日占权利金 | 中位收益/权利金 | 平均收益/权利金 | 最差收益 | 中位对冲次数 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["summary"]:
        if item["sample"] != "test" or item["option_slippage_bps"] != 100.0 or item["hedge_variant"] != "baseline":
            continue
        label = "ATM" if item["target_otm_pct"] == 0 else f"OTM {item['target_otm_pct']:g}%"
        lines.append(
            f"| {item['underlying']} | {label} | {item['count']} | {item['positive']}/{item['count']} | "
            f"{item['median_premium_pct_spot']:.2f}% | {item['median_theta_pct_premium']:.1f}% | "
            f"{item['median_return_on_premium_pct']:.1f}% | {item['mean_return_on_premium_pct']:.1f}% | "
            f"{item['worst_return_on_premium_pct']:.1f}% | {item['median_rehedges']:.1f} |"
        )
    lines.extend(["", "## 训练选择后的样本外结果", "", "结构只用前半段到期日选择；下表不再重新挑样本外参数。", "", "| 标的 | 训练选择 | 滑点 | 样本外窗口 | 中位收益/权利金 | 平均收益/权利金 | 正收益 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for base, selected in payload["selectedByTraining"].items():
        otm_pct = selected["targetOtmPct"]
        variant = selected["hedgeVariant"]
        for slippage in SLIPPAGE_BPS:
            items = [item for item in payload["summary"] if item["underlying"] == base and item["sample"] == "test" and item["target_otm_pct"] == otm_pct and item["hedge_variant"] == variant and item["option_slippage_bps"] == slippage]
            if not items:
                continue
            item = items[0]
            label = "ATM" if otm_pct == 0 else f"OTM {otm_pct:g}%"
            lines.append(f"| {base} | {label} / {variant} ({selected['deltaThresholdPct']:g}%/{selected['hedgeIntervalHours']}h/{selected['maxRehedges']}次) | {slippage / 100:.1f}%/边 | {item['count']} | {item['median_return_on_premium_pct']:.1f}% | {item['mean_return_on_premium_pct']:.1f}% | {item['positive']}/{item['count']} |")
    lines.extend(["", "## ATM 对冲频率对照（样本外，1%/边）", "", "| 标的 | 对冲变体 | Delta/间隔/上限 | 中位收益/权利金 | 平均收益/权利金 | 正收益 |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for base in ("BTC", "ETH"):
        items = [item for item in payload["summary"] if item["underlying"] == base and item["sample"] == "test" and item["target_otm_pct"] == 0.0 and item["option_slippage_bps"] == 100.0]
        for item in items:
            lines.append(f"| {base} | {item['hedge_variant']} | {item['delta_threshold_pct']:g}%/{item['hedge_interval_hours']}h/{item['max_rehedges']} | {item['median_return_on_premium_pct']:.1f}% | {item['mean_return_on_premium_pct']:.1f}% | {item['positive']}/{item['count']} |")
    lines.extend(["", "## 结论边界", "", "- OTM 会降低绝对权利金和绝对 Theta，但更容易把收益变成少数大波动窗口贡献的右偏分布；Theta 占权利金的比例不一定降低。", "- 本数据是 Deribit 反向期权成交价，OKX `_UM` 线性期权的盘口、乘数和结算币种不同，结果只能用于筛选结构，不能直接迁移收益率。", "- 样本较小且没有历史 bid/ask；任何正收益都必须在更长的逐笔/盘口数据上复核。", ""])
    return "\n".join(lines)


def write_csv(path: Path, rows: list[BacktestRow]) -> None:
    fields = list(asdict(rows[0])) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    args = parse_args()
    expiries_text = args.expiries or list(DEFAULT_EXPIRIES)
    expiries = sorted(parse_iso_ms(item) for item in expiries_text)
    history = DeribitHistory(Path(args.cache_file), workers=args.workers)
    rows = collect_rows(history, expiries)
    if not rows:
        raise SystemExit("No option backtest rows passed the liquidity and alignment checks")
    summary = summarize(rows)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_deribit_public_hourly_option_backtest",
        "source": {
            "name": "Deribit public TradingView chart API",
            "url": f"{DERIBIT_BASE}/get_tradingview_chart_data",
            "fields": "hourly close and volume",
            "cacheFile": str(Path(args.cache_file).resolve()),
        },
        "expiries": [iso_ms(item) for item in expiries],
        "otmPcts": list(OTM_PCTS),
        "slippageBps": list(SLIPPAGE_BPS),
        "hedgeVariants": [
            {"name": name, "deltaThresholdPct": threshold, "hedgeIntervalHours": interval, "maxRehedges": max_rehedges}
            for name, threshold, interval, max_rehedges in HEDGE_VARIANTS
        ],
        "baseConfig": asdict(BacktestConfig()),
        "selectedByTraining": selected_by_training(summary),
        "summary": summary,
        "rows": [asdict(row) for row in rows],
    }
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "trades.csv", rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"rows={len(rows)} cache_series={len(history.cache)} selected={payload['selectedByTraining']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
