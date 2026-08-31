"""Read-only Deribit option-information factor research.

The option surface is observed before a short perpetual holding period.  No
account endpoint or order path is imported.  Historical option trade bars are
used as noisy information inputs, not as executable bid/ask quotes.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from option_long_dte_research import realized_volatility
from option_strangle_backtest import (
    DEFAULT_CACHE,
    HOUR_MS,
    YEAR_MS,
    BacktestConfig,
    Bar,
    DeribitHistory,
    OptionPair,
    expiry_code,
    greeks_from_price,
    implied_volatility,
    iso_ms,
    run_trade,
    strike_step,
    traded_observation,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "options"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "deribit_factors"
FACTOR_CACHE = DATA_ROOT / "deribit_factor_hourly_cache.json"
BASES = ("BTC", "ETH")
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class FactorConfig:
    entry_hours_before_expiry: int = 72
    holding_hours: int = 24
    realized_lookback_hours: int = 168
    max_option_staleness_hours: int = 6
    strike_range_pct: float = 6.0
    directional_allocation_per_asset: float = 0.10
    option_premium_budget_per_asset: float = 0.005
    perpetual_round_trip_bps: float = 12.0
    stressed_perpetual_round_trip_bps: float = 24.0
    strict_staleness_hours: float = 2.0

    def __post_init__(self) -> None:
        if self.entry_hours_before_expiry <= self.holding_hours:
            raise ValueError("entry DTE must exceed the holding period")
        if min(
            self.holding_hours,
            self.realized_lookback_hours,
            self.max_option_staleness_hours,
            self.strike_range_pct,
        ) <= 0:
            raise ValueError("windows and strike range must be positive")
        if not 0 < self.directional_allocation_per_asset <= 0.5:
            raise ValueError("directional allocation must be in (0, 0.5]")
        if not 0 < self.option_premium_budget_per_asset <= 0.1:
            raise ValueError("option premium budget must be in (0, 0.1]")


@dataclass(frozen=True, slots=True)
class SurfaceLeg:
    name: str
    option_type: str
    strike: float
    iv: float
    delta: float
    stale_hours: float
    trailing_volume: float
    bars: tuple[Bar, ...]


@dataclass(frozen=True, slots=True)
class FactorObservation:
    underlying: str
    expiry_ts: int
    expiry: str
    sample: str
    entry_ts: int
    entry_time: str
    entry_spot: float
    exit_spot: float
    latency_entry_spot: float
    latency_exit_spot: float
    realized_vol_7d: float
    atm_iv: float
    iv_rv_ratio: float
    variance_risk_premium: float
    atm_call_put_iv_spread: float
    risk_reversal_25d: float
    butterfly_25d: float
    call_put_volume_log_ratio: float
    momentum_24h: float
    momentum_7d: float
    max_surface_stale_hours: float
    atm_strike: float
    call_25d_strike: float
    put_25d_strike: float
    future_return_24h: float
    future_realized_vol_24h: float
    long_straddle_return_on_premium_pct: float | None
    long_straddle_stress_return_on_premium_pct: float | None


@dataclass(frozen=True, slots=True)
class StrategyResult:
    sample: str
    strategy: str
    variant: str
    observations: int
    trades: int
    positive_trades: int
    total_return_pct: float
    profit_factor: float
    max_endpoint_drawdown_pct: float
    median_trade_net_bps: float
    mean_trade_net_bps: float
    cost_drag_pct: float


class LayeredHistory:
    """Read the large legacy cache but persist new requests separately."""

    def __init__(
        self,
        legacy_path: Path,
        factor_path: Path,
        *,
        workers: int,
        cached_only: bool,
    ) -> None:
        self.legacy = DeribitHistory(legacy_path, workers=workers)
        self.factor = DeribitHistory(factor_path, workers=workers)
        self.cached_only = cached_only

    def fetch_many(
        self, instruments: Iterable[str], start_ms: int, end_ms: int
    ) -> dict[str, tuple[Bar, ...]]:
        unique = sorted(set(instruments))
        missing = []
        for name in unique:
            key = DeribitHistory.key(name, start_ms, end_ms)
            if key not in self.factor.cache and key not in self.legacy.cache:
                missing.append(name)
        if missing and not self.cached_only:
            self.factor.fetch_many(missing, start_ms, end_ms)
        result: dict[str, tuple[Bar, ...]] = {}
        for name in unique:
            key = DeribitHistory.key(name, start_ms, end_ms)
            raw = self.factor.cache.get(key)
            if raw is None:
                raw = self.legacy.cache.get(key, [])
            result[name] = tuple(
                Bar(int(row["ts"]), float(row["close"]), float(row["volume"]))
                for row in raw
            )
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Deribit option-information factor backtest"
    )
    parser.add_argument("--start-month", default="2023-01")
    parser.add_argument("--end-month", default="2026-06")
    parser.add_argument("--legacy-cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--factor-cache", default=str(FACTOR_CACHE))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cached-only", action="store_true")
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def month_range(start: str, end: str) -> list[tuple[int, int]]:
    start_dt = datetime.strptime(start, "%Y-%m")
    end_dt = datetime.strptime(end, "%Y-%m")
    if start_dt > end_dt:
        raise ValueError("start month must not follow end month")
    result = []
    year, month = start_dt.year, start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        result.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def monthly_expiries(start: str, end: str) -> list[int]:
    result = []
    for year, month in month_range(start, end):
        day = calendar.monthrange(year, month)[1]
        while datetime(year, month, day).weekday() != calendar.FRIDAY:
            day -= 1
        result.append(
            int(datetime(year, month, day, 8, tzinfo=timezone.utc).timestamp() * 1000)
        )
    return result


def factor_strikes(base: str, spot: float, range_pct: float) -> list[float]:
    step = strike_step(base, spot)
    low = math.floor(spot * (1.0 - range_pct / 100.0) / step) * step
    high = math.ceil(spot * (1.0 + range_pct / 100.0) / step) * step
    return [low + index * step for index in range(int(round((high - low) / step)) + 1)]


def exact_bar(bars: tuple[Bar, ...], ts: int) -> Bar | None:
    return next((bar for bar in bars if bar.ts == ts), None)


def trailing_volume(bars: tuple[Bar, ...], ts: int, hours: int = 24) -> float:
    start = ts - hours * HOUR_MS
    return sum(max(0.0, bar.volume) for bar in bars if start < bar.ts <= ts)


def infer_leg(
    name: str,
    option_type: str,
    strike: float,
    bars: tuple[Bar, ...],
    *,
    timestamp: int,
    spot: float,
    years: float,
    max_stale_hours: int,
) -> SurfaceLeg | None:
    observation = traded_observation(bars, timestamp, max_stale_hours)
    if observation is None:
        return None
    price_usd = observation[0].close * spot
    iv = implied_volatility(price_usd, spot, strike, years, option_type)
    if iv is None or not math.isfinite(iv) or iv <= 0:
        return None
    delta = greeks_from_price(price_usd, spot, strike, years, option_type)[0]
    return SurfaceLeg(
        name=name,
        option_type=option_type,
        strike=strike,
        iv=iv,
        delta=delta,
        stale_hours=observation[1],
        trailing_volume=trailing_volume(bars, timestamp),
        bars=bars,
    )


def surface_legs(
    base: str,
    expiry_ts: int,
    entry_ts: int,
    spot: float,
    charts: dict[str, tuple[Bar, ...]],
    config: FactorConfig,
) -> tuple[SurfaceLeg, SurfaceLeg, SurfaceLeg, SurfaceLeg] | None:
    years = max((expiry_ts - entry_ts) / YEAR_MS, 1e-9)
    calls: list[SurfaceLeg] = []
    puts: list[SurfaceLeg] = []
    code = expiry_code(expiry_ts)
    for strike in factor_strikes(base, spot, config.strike_range_pct):
        for option_type, target in (("C", calls), ("P", puts)):
            name = f"{base}-{code}-{strike:g}-{option_type}"
            leg = infer_leg(
                name,
                option_type,
                strike,
                charts.get(name, ()),
                timestamp=entry_ts,
                spot=spot,
                years=years,
                max_stale_hours=config.max_option_staleness_hours,
            )
            if leg is not None:
                target.append(leg)
    call_by_strike = {leg.strike: leg for leg in calls}
    put_by_strike = {leg.strike: leg for leg in puts}
    common = sorted(set(call_by_strike) & set(put_by_strike))
    if not common:
        return None
    atm_strike = min(common, key=lambda strike: abs(strike / spot - 1.0))
    otm_calls = [leg for leg in calls if leg.strike >= spot]
    otm_puts = [leg for leg in puts if leg.strike <= spot]
    if not otm_calls or not otm_puts:
        return None
    call_25d = min(otm_calls, key=lambda leg: abs(leg.delta - 0.25))
    put_25d = min(otm_puts, key=lambda leg: abs(leg.delta + 0.25))
    return call_by_strike[atm_strike], put_by_strike[atm_strike], call_25d, put_25d


def future_realized_volatility(bars: tuple[Bar, ...], start_ts: int, hours: int) -> float:
    end_ts = start_ts + hours * HOUR_MS
    closes = [bar.close for bar in bars if start_ts <= bar.ts <= end_ts and bar.close > 0]
    returns = [
        math.log(current / previous)
        for previous, current in zip(closes, closes[1:])
        if previous > 0 and current > 0
    ]
    if len(returns) < 2:
        return 0.0
    return statistics.pstdev(returns) * math.sqrt(24.0 * 365.25)


def sample_labels(expiries: list[int]) -> dict[int, str]:
    train_end = len(expiries) // 2
    validation_end = train_end + len(expiries) // 4
    return {
        expiry: "train" if index < train_end else "validation" if index < validation_end else "test"
        for index, expiry in enumerate(expiries)
    }


def collect_observations(
    history: LayeredHistory,
    expiries: list[int],
    config: FactorConfig,
) -> list[FactorObservation]:
    labels = sample_labels(expiries)
    result: list[FactorObservation] = []
    median_option_spread = {"BTC": 435.0, "ETH": 364.0}
    stressed_option_spread = {"BTC": 494.0, "ETH": 426.0}
    for expiry_index, expiry_ts in enumerate(expiries, 1):
        entry_ts = expiry_ts - config.entry_hours_before_expiry * HOUR_MS
        exit_ts = entry_ts + config.holding_hours * HOUR_MS
        latency_entry_ts = entry_ts + HOUR_MS
        latency_exit_ts = exit_ts + HOUR_MS
        start_ms = expiry_ts - (
            config.entry_hours_before_expiry + config.realized_lookback_hours + 4
        ) * HOUR_MS
        for base in BASES:
            underlying_name = f"{base}-PERPETUAL"
            underlying = history.fetch_many([underlying_name], start_ms, expiry_ts).get(
                underlying_name, ()
            )
            entry_bar = exact_bar(underlying, entry_ts)
            exit_bar = exact_bar(underlying, exit_ts)
            latency_entry_bar = exact_bar(underlying, latency_entry_ts)
            latency_exit_bar = exact_bar(underlying, latency_exit_ts)
            prior_24h = exact_bar(underlying, entry_ts - 24 * HOUR_MS)
            prior_7d = exact_bar(underlying, entry_ts - 168 * HOUR_MS)
            if not all((entry_bar, exit_bar, latency_entry_bar, latency_exit_bar, prior_24h, prior_7d)):
                continue
            assert entry_bar and exit_bar and latency_entry_bar and latency_exit_bar and prior_24h and prior_7d
            strikes = factor_strikes(base, entry_bar.close, config.strike_range_pct)
            code = expiry_code(expiry_ts)
            instruments = [
                f"{base}-{code}-{strike:g}-{option_type}"
                for strike in strikes
                for option_type in ("C", "P")
            ]
            charts = history.fetch_many(instruments, start_ms, expiry_ts)
            surface = surface_legs(
                base, expiry_ts, entry_ts, entry_bar.close, charts, config
            )
            rv = realized_volatility(
                underlying, entry_ts, lookback_hours=config.realized_lookback_hours
            )
            if surface is None or rv is None or rv <= 0:
                continue
            atm_call, atm_put, call_25d, put_25d = surface
            atm_iv = (atm_call.iv + atm_put.iv) / 2.0
            option_pair = OptionPair(
                call_name=atm_call.name,
                put_name=atm_put.name,
                call_strike=atm_call.strike,
                put_strike=atm_put.strike,
                target_otm_pct=0.0,
                actual_call_otm_pct=(atm_call.strike / entry_bar.close - 1.0) * 100.0,
                actual_put_otm_pct=(1.0 - atm_put.strike / entry_bar.close) * 100.0,
                call_bars=atm_call.bars,
                put_bars=atm_put.bars,
            )

            def long_option_return(option_slippage_bps: float) -> float | None:
                row = run_trade(
                    base,
                    expiry_ts,
                    underlying,
                    option_pair,
                    BacktestConfig(
                        option_slippage_bps=option_slippage_bps,
                        hedge_cost_bps=5.0,
                        delta_threshold_pct=10.0,
                        hedge_interval_hours=6,
                        max_rehedges=4,
                        entry_hours_before_expiry=config.entry_hours_before_expiry,
                        exit_hours_before_expiry=(
                            config.entry_hours_before_expiry - config.holding_hours
                        ),
                        max_quote_staleness_hours=config.max_option_staleness_hours,
                    ),
                    labels[expiry_ts],
                    "threshold10_24h",
                )
                return None if row is None else row.return_on_premium_pct

            result.append(
                FactorObservation(
                    underlying=base,
                    expiry_ts=expiry_ts,
                    expiry=iso_ms(expiry_ts),
                    sample=labels[expiry_ts],
                    entry_ts=entry_ts,
                    entry_time=iso_ms(entry_ts),
                    entry_spot=entry_bar.close,
                    exit_spot=exit_bar.close,
                    latency_entry_spot=latency_entry_bar.close,
                    latency_exit_spot=latency_exit_bar.close,
                    realized_vol_7d=rv,
                    atm_iv=atm_iv,
                    iv_rv_ratio=atm_iv / rv,
                    variance_risk_premium=atm_iv * atm_iv - rv * rv,
                    atm_call_put_iv_spread=atm_call.iv - atm_put.iv,
                    risk_reversal_25d=call_25d.iv - put_25d.iv,
                    butterfly_25d=(call_25d.iv + put_25d.iv) / 2.0 - atm_iv,
                    call_put_volume_log_ratio=math.log(
                        (call_25d.trailing_volume + 0.1)
                        / (put_25d.trailing_volume + 0.1)
                    ),
                    momentum_24h=entry_bar.close / prior_24h.close - 1.0,
                    momentum_7d=entry_bar.close / prior_7d.close - 1.0,
                    max_surface_stale_hours=max(
                        atm_call.stale_hours,
                        atm_put.stale_hours,
                        call_25d.stale_hours,
                        put_25d.stale_hours,
                    ),
                    atm_strike=atm_call.strike,
                    call_25d_strike=call_25d.strike,
                    put_25d_strike=put_25d.strike,
                    future_return_24h=exit_bar.close / entry_bar.close - 1.0,
                    future_realized_vol_24h=future_realized_volatility(
                        underlying, entry_ts, config.holding_hours
                    ),
                    long_straddle_return_on_premium_pct=long_option_return(
                        median_option_spread[base]
                    ),
                    long_straddle_stress_return_on_premium_pct=long_option_return(
                        stressed_option_spread[base]
                    ),
                )
            )
        print(
            f"expiry={expiry_index}/{len(expiries)} date={iso_ms(expiry_ts)[:10]} observations={len(result)}",
            flush=True,
        )
    return result


def sign(value: float, tolerance: float = 1e-12) -> int:
    return 1 if value > tolerance else -1 if value < -tolerance else 0


def training_thresholds(observations: list[FactorObservation]) -> dict[str, float]:
    train = [row for row in observations if row.sample == "train"]
    if not train:
        raise ValueError("training observations are required")
    return {
        "vrp_median": statistics.median(row.variance_risk_premium for row in train),
        "iv_rv_median": statistics.median(row.iv_rv_ratio for row in train),
        "abs_rr_median": statistics.median(abs(row.risk_reversal_25d) for row in train),
        "butterfly_median": statistics.median(row.butterfly_25d for row in train),
    }


def directional_signal(
    row: FactorObservation, strategy: str, thresholds: dict[str, float], config: FactorConfig
) -> int:
    iv_side = sign(row.atm_call_put_iv_spread)
    rr_side = sign(row.risk_reversal_25d)
    volume_side = sign(row.call_put_volume_log_ratio)
    if strategy == "spot_momentum_baseline":
        return sign(row.momentum_24h)
    if strategy == "atm_iv_spread":
        return iv_side
    if strategy == "risk_reversal_25d":
        return rr_side
    if strategy == "option_volume":
        return volume_side
    if strategy == "iv_volume_consensus":
        return iv_side if iv_side and iv_side == volume_side else 0
    if strategy == "rr_volume_consensus":
        return rr_side if rr_side and rr_side == volume_side else 0
    if strategy == "paper_majority":
        return sign(iv_side + rr_side + volume_side)
    if strategy == "strict_paper_majority":
        return (
            sign(iv_side + rr_side + volume_side)
            if row.max_surface_stale_hours <= config.strict_staleness_hours
            else 0
        )
    if strategy == "variance_risk_premium":
        return sign(row.variance_risk_premium - thresholds["vrp_median"])
    raise ValueError(f"unknown directional strategy: {strategy}")


DIRECTIONAL_STRATEGIES = (
    "spot_momentum_baseline",
    "atm_iv_spread",
    "risk_reversal_25d",
    "option_volume",
    "iv_volume_consensus",
    "rr_volume_consensus",
    "paper_majority",
    "strict_paper_majority",
    "variance_risk_premium",
)


def directional_trade_return(
    row: FactorObservation,
    side: int,
    variant: str,
    config: FactorConfig,
) -> tuple[float, float]:
    if not side:
        return 0.0, 0.0
    if variant == "latency_1h":
        gross = side * (row.latency_exit_spot / row.latency_entry_spot - 1.0)
        cost = config.perpetual_round_trip_bps / 10_000.0
    elif variant == "cost_stress":
        gross = side * row.future_return_24h
        cost = config.stressed_perpetual_round_trip_bps / 10_000.0
    elif variant == "normal":
        gross = side * row.future_return_24h
        cost = config.perpetual_round_trip_bps / 10_000.0
    else:
        raise ValueError(f"unknown variant: {variant}")
    return gross - cost, cost


def evaluate_directional(
    observations: list[FactorObservation],
    sample: str,
    strategy: str,
    variant: str,
    thresholds: dict[str, float],
    config: FactorConfig,
) -> StrategyResult:
    rows = [row for row in observations if sample == "full" or row.sample == sample]
    grouped: dict[int, list[FactorObservation]] = {}
    for row in rows:
        grouped.setdefault(row.expiry_ts, []).append(row)
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    contributions: list[float] = []
    net_trade_returns: list[float] = []
    cost_drag = 0.0
    for expiry_ts in sorted(grouped):
        event_return = 0.0
        for row in grouped[expiry_ts]:
            side = directional_signal(row, strategy, thresholds, config)
            if not side:
                continue
            net, cost = directional_trade_return(row, side, variant, config)
            contribution = config.directional_allocation_per_asset * net
            event_return += contribution
            contributions.append(contribution)
            net_trade_returns.append(net)
            cost_drag += config.directional_allocation_per_asset * cost
        equity *= max(EPSILON, 1.0 + event_return)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    gross_profit = sum(value for value in contributions if value > 0)
    gross_loss = abs(sum(value for value in contributions if value < 0))
    return StrategyResult(
        sample=sample,
        strategy=strategy,
        variant=variant,
        observations=len(rows),
        trades=len(contributions),
        positive_trades=sum(value > 0 for value in contributions),
        total_return_pct=(equity - 1.0) * 100.0,
        profit_factor=(
            gross_profit / gross_loss
            if gross_loss > EPSILON
            else 999.0 if gross_profit > 0 else 0.0
        ),
        max_endpoint_drawdown_pct=drawdown * 100.0,
        median_trade_net_bps=(
            statistics.median(net_trade_returns) * 10_000.0 if net_trade_returns else 0.0
        ),
        mean_trade_net_bps=(
            statistics.fmean(net_trade_returns) * 10_000.0 if net_trade_returns else 0.0
        ),
        cost_drag_pct=cost_drag * 100.0,
    )


def long_option_active(
    row: FactorObservation, strategy: str, thresholds: dict[str, float]
) -> bool:
    if strategy == "long_all":
        return True
    if strategy == "long_iv_discount":
        return row.iv_rv_ratio <= 1.0
    if strategy == "long_low_vrp":
        return row.iv_rv_ratio <= thresholds["iv_rv_median"]
    if strategy == "long_high_abs_rr":
        return abs(row.risk_reversal_25d) >= thresholds["abs_rr_median"]
    if strategy == "long_high_butterfly":
        return row.butterfly_25d >= thresholds["butterfly_median"]
    raise ValueError(f"unknown long-option strategy: {strategy}")


LONG_OPTION_STRATEGIES = (
    "long_all",
    "long_iv_discount",
    "long_low_vrp",
    "long_high_abs_rr",
    "long_high_butterfly",
)


def evaluate_long_option(
    observations: list[FactorObservation],
    sample: str,
    strategy: str,
    variant: str,
    thresholds: dict[str, float],
    config: FactorConfig,
) -> StrategyResult:
    rows = [row for row in observations if sample == "full" or row.sample == sample]
    grouped: dict[int, list[FactorObservation]] = {}
    for row in rows:
        grouped.setdefault(row.expiry_ts, []).append(row)
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    contributions: list[float] = []
    trade_returns: list[float] = []
    for expiry_ts in sorted(grouped):
        event_return = 0.0
        for row in grouped[expiry_ts]:
            if not long_option_active(row, strategy, thresholds):
                continue
            value = (
                row.long_straddle_stress_return_on_premium_pct
                if variant == "cost_stress"
                else row.long_straddle_return_on_premium_pct
            )
            if value is None:
                continue
            net = value / 100.0
            contribution = config.option_premium_budget_per_asset * net
            event_return += contribution
            contributions.append(contribution)
            trade_returns.append(net)
        equity *= max(EPSILON, 1.0 + event_return)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    gross_profit = sum(value for value in contributions if value > 0)
    gross_loss = abs(sum(value for value in contributions if value < 0))
    return StrategyResult(
        sample=sample,
        strategy=strategy,
        variant=variant,
        observations=len(rows),
        trades=len(contributions),
        positive_trades=sum(value > 0 for value in contributions),
        total_return_pct=(equity - 1.0) * 100.0,
        profit_factor=(
            gross_profit / gross_loss
            if gross_loss > EPSILON
            else 999.0 if gross_profit > 0 else 0.0
        ),
        max_endpoint_drawdown_pct=drawdown * 100.0,
        median_trade_net_bps=(
            statistics.median(trade_returns) * 10_000.0 if trade_returns else 0.0
        ),
        mean_trade_net_bps=(
            statistics.fmean(trade_returns) * 10_000.0 if trade_returns else 0.0
        ),
        cost_drag_pct=0.0,
    )


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        rank = (index + end - 1) / 2.0 + 1.0
        for location in order[index:end]:
            result[location] = rank
        index = end
    return result


def correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 3 or len(left) != len(right):
        return 0.0
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left)
        * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator > EPSILON else 0.0


def factor_information_coefficients(
    observations: list[FactorObservation], sample: str
) -> list[dict[str, Any]]:
    rows = [row for row in observations if sample == "full" or row.sample == sample]
    factors = {
        "atm_call_put_iv_spread": [row.atm_call_put_iv_spread for row in rows],
        "risk_reversal_25d": [row.risk_reversal_25d for row in rows],
        "call_put_volume_log_ratio": [row.call_put_volume_log_ratio for row in rows],
        "variance_risk_premium": [row.variance_risk_premium for row in rows],
        "butterfly_25d": [row.butterfly_25d for row in rows],
    }
    future_return = average_ranks([row.future_return_24h for row in rows])
    future_volatility = average_ranks([row.future_realized_vol_24h for row in rows])
    return [
        {
            "sample": sample,
            "factor": name,
            "count": len(rows),
            "return_spearman_ic": correlation(average_ranks(values), future_return),
            "future_vol_spearman_ic": correlation(average_ranks(values), future_volatility),
        }
        for name, values in factors.items()
    ]


def select_directional(rows: list[StrategyResult]) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row.sample == "train"
        and row.variant == "normal"
        and row.strategy != "spot_momentum_baseline"
    ]
    eligible = [
        row
        for row in candidates
        if row.trades >= 12 and row.total_return_pct > 0 and row.profit_factor >= 1.05
    ]
    pool = eligible or candidates
    best = max(pool, key=lambda row: (row.total_return_pct, row.profit_factor, row.trades))
    return {
        "strategy": best.strategy,
        "trainingEligible": bool(eligible),
        "trainingTrades": best.trades,
        "trainingReturnPct": best.total_return_pct,
        "trainingProfitFactor": best.profit_factor,
    }


def select_long_option(rows: list[StrategyResult]) -> dict[str, Any]:
    candidates = [row for row in rows if row.sample == "train" and row.variant == "normal"]
    eligible = [
        row
        for row in candidates
        if row.trades >= 8 and row.total_return_pct > 0 and row.profit_factor >= 1.05
    ]
    pool = eligible or candidates
    best = max(pool, key=lambda row: (row.total_return_pct, row.profit_factor, row.trades))
    return {
        "strategy": best.strategy,
        "trainingEligible": bool(eligible),
        "trainingTrades": best.trades,
        "trainingReturnPct": best.total_return_pct,
        "trainingProfitFactor": best.profit_factor,
    }


def decision_payload(
    directional_rows: list[StrategyResult], selected: dict[str, Any]
) -> dict[str, Any]:
    lookup = {
        (row.sample, row.strategy, row.variant): row for row in directional_rows
    }
    name = str(selected["strategy"])
    validation = lookup[("validation", name, "normal")]
    test = lookup[("test", name, "normal")]
    stress = lookup[("test", name, "cost_stress")]
    latency = lookup[("test", name, "latency_1h")]
    passed = (
        bool(selected["trainingEligible"])
        and validation.total_return_pct > 0
        and test.total_return_pct > 0
        and stress.total_return_pct > 0
        and latency.total_return_pct > 0
        and test.profit_factor >= 1.10
        and test.trades >= 10
        and test.max_endpoint_drawdown_pct <= 3.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedHistory": passed,
        "paperAuthorized": False,
        "liveAuthorized": False,
        "shortTermResearchRecommendation": "continue_fresh_forward_only" if passed else "stop_short_term_strategy_research",
        "rule": (
            "training candidate, validation, test, test cost stress and test one-hour latency must all be positive; "
            "test PF>=1.10, >=10 trades and endpoint DD<=3%"
        ),
    }


def result_payload(row: StrategyResult) -> dict[str, Any]:
    return asdict(row)


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedDirectional"]
    selected_long = payload["selectedLongOption"]
    decision = payload["decision"]
    directional = payload["directionalResults"]
    long_option = payload["longOptionResults"]
    lines = [
        "# Deribit 期权信息因子与短周期回测",
        "",
        "> 只读取 Deribit 公共历史行情；不读取账户、不下单、不修改实盘。",
        "",
        "## 预注册依据",
        "",
        "- Alexander & Imeraj (2020), *The Bitcoin VIX and Its Variance Risk Premium*, DOI `10.3905/jai.2020.1.112`：Deribit 期权可构造比特币隐含方差与方差风险溢价。",
        "- Zulfiqar & Gulzar (2021), *Implied volatility estimation of bitcoin options and the stylized facts of option pricing*, DOI `10.1186/s40854-021-00280-y`：短期限 BTC 期权存在远期偏斜/微笑。",
        "- Cremers & Weinbaum (2010), *Deviations from Put-Call Parity and Stock Return Predictability*, DOI `10.1017/S002210901000013X`：同执行价 Call-Put IV 差包含方向信息。",
        "- Pan & Poteshman (2006), *The Information in Option Volume for Future Stock Prices*, DOI `10.1093/rfs/hhj024`：期权 Put-Call 成交量包含短期价格信息。",
        "- Bollerslev, Tauchen & Zhou (2009), *Expected Stock Returns and Variance Risk Premia*, DOI `10.1093/rfs/hhp008`：方差风险溢价可与预期收益相关。",
        "",
        "## 数据与边界",
        "",
        f"- 月度到期：{payload['period']['startExpiry'][:10]} 至 {payload['period']['endExpiry'][:10]}，共 {payload['period']['requestedExpiries']} 个；按到期日 50%/25%/25% 划分训练、验证、测试。",
        f"- 有效 BTC/ETH 横截面观察共 {payload['dataQuality']['observations']} 个；期权长权利金结果覆盖 {payload['dataQuality']['longOptionOutcomes']} 个。",
        "- 每个因子只使用到入场时为止、最多陈旧 6 小时的期权成交；持有 Deribit 永续 24 小时。",
        "- 永续主成本为双边共 12 bps，压力为 24 bps；每资产使用 10% 权益，无杠杆。",
        "- 期权历史只有成交 OHLC、没有逐时 bid/ask；因此期权只作为信息源。长权利金对照使用此前 Tardis 的 72h ATM 经验半价差，BTC/ETH 每边 4.35%/3.64%。",
        "- Pan–Poteshman 使用买方发起的新开仓量；Deribit 图表接口只有总成交量，无法区分方向和开平仓，因此这里的 Call/Put 总量比只是较弱代理。",
        "",
        "## 因子 Rank IC",
        "",
        "| 样本 | 因子 | 数量 | 对未来24h收益 IC | 对未来24h波动 IC |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in payload["factorIC"]:
        lines.append(
            f"| {row['sample']} | {row['factor']} | {row['count']} | "
            f"{row['return_spearman_ic']:+.3f} | {row['future_vol_spearman_ic']:+.3f} |"
        )
    lines.extend(
        [
            "",
            "## 训练选择后的方向策略",
            "",
            f"训练选择：`{selected['strategy']}`；训练资格：`{selected['trainingEligible']}`。账户收益按每资产 10% 权益计算。",
            "",
            "| 样本/压力 | 交易 | 正收益 | 账户收益 | PF | 端点回撤 | 单笔中位净收益 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for sample, variant in (
        ("train", "normal"),
        ("validation", "normal"),
        ("test", "normal"),
        ("test", "cost_stress"),
        ("test", "latency_1h"),
        ("full", "normal"),
    ):
        row = next(
            item
            for item in directional
            if item["strategy"] == selected["strategy"]
            and item["sample"] == sample
            and item["variant"] == variant
        )
        lines.append(
            f"| {sample}/{variant} | {row['trades']} | {row['positive_trades']} | "
            f"{row['total_return_pct']:+.4f}% | {row['profit_factor']:.3f} | "
            f"{row['max_endpoint_drawdown_pct']:.3f}% | {row['median_trade_net_bps']:+.1f} bps |"
        )
    hindsight = max(
        (
            item
            for item in directional
            if item["sample"] == "test"
            and item["variant"] == "normal"
            and item["strategy"] != "spot_momentum_baseline"
        ),
        key=lambda item: item["total_return_pct"],
    )
    hindsight_train = next(
        item
        for item in directional
        if item["sample"] == "train"
        and item["variant"] == "normal"
        and item["strategy"] == hindsight["strategy"]
    )
    hindsight_validation = next(
        item
        for item in directional
        if item["sample"] == "validation"
        and item["variant"] == "normal"
        and item["strategy"] == hindsight["strategy"]
    )
    hindsight_full = next(
        item
        for item in directional
        if item["sample"] == "full"
        and item["variant"] == "normal"
        and item["strategy"] == hindsight["strategy"]
    )
    lines.extend(
        [
            "",
            "### 防止测试段反选",
            "",
            f"测试段事后最好的 `{hindsight['strategy']}` 为 {hindsight['total_return_pct']:+.4f}%，"
            f"但它训练/验证/全样本分别为 {hindsight_train['total_return_pct']:+.4f}%/"
            f"{hindsight_validation['total_return_pct']:+.4f}%/{hindsight_full['total_return_pct']:+.4f}%。"
            "看到测试结果后不能改选它。",
        ]
    )
    lines.extend(
        [
            "",
            "## 有界长权利金对照",
            "",
            f"训练选择：`{selected_long['strategy']}`；训练资格：`{selected_long['trainingEligible']}`。每资产最多支付 0.5% 权益权利金。",
            "",
            "| 样本/压力 | 交易 | 正收益 | 账户收益 | PF |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for sample, variant in (
        ("train", "normal"),
        ("validation", "normal"),
        ("test", "normal"),
        ("test", "cost_stress"),
        ("full", "normal"),
    ):
        row = next(
            item
            for item in long_option
            if item["strategy"] == selected_long["strategy"]
            and item["sample"] == sample
            and item["variant"] == variant
        )
        lines.append(
            f"| {sample}/{variant} | {row['trades']} | {row['positive_trades']} | "
            f"{row['total_return_pct']:+.4f}% | {row['profit_factor']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 决策",
            "",
            f"- 数量门禁：`{decision['quantitativePassOnReusedHistory']}`。",
            f"- 状态：`{decision['status']}`；建议：`{decision['shortTermResearchRecommendation']}`。",
            "- 即使通过，这些月份也已被本次检查，只能要求一个预注册的新鲜前向期；当前结果不授权仿真或实盘。",
            "- 最大回撤只按月度事件端点计算，不能替代逐小时账户保证金压力。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    config = FactorConfig()
    expiries = monthly_expiries(args.start_month, args.end_month)
    history = LayeredHistory(
        Path(args.legacy_cache),
        Path(args.factor_cache),
        workers=max(1, args.workers),
        cached_only=args.cached_only,
    )
    observations = collect_observations(history, expiries, config)
    if len(observations) < 20:
        raise RuntimeError(f"insufficient factor observations: {len(observations)}")
    thresholds = training_thresholds(observations)
    directional_results = [
        evaluate_directional(
            observations, sample, strategy, variant, thresholds, config
        )
        for strategy in DIRECTIONAL_STRATEGIES
        for sample in ("train", "validation", "test", "full")
        for variant in ("normal", "cost_stress", "latency_1h")
    ]
    long_option_results = [
        evaluate_long_option(
            observations, sample, strategy, variant, thresholds, config
        )
        for strategy in LONG_OPTION_STRATEGIES
        for sample in ("train", "validation", "test", "full")
        for variant in ("normal", "cost_stress")
    ]
    selected = select_directional(directional_results)
    selected_long = select_long_option(long_option_results)
    decision = decision_payload(directional_results, selected)
    factor_ic = [
        row
        for sample in ("train", "validation", "test", "full")
        for row in factor_information_coefficients(observations, sample)
    ]
    quality = {
        "observations": len(observations),
        "bySample": {
            sample: sum(row.sample == sample for row in observations)
            for sample in ("train", "validation", "test")
        },
        "byUnderlying": {
            base: sum(row.underlying == base for row in observations) for base in BASES
        },
        "longOptionOutcomes": sum(
            row.long_straddle_return_on_premium_pct is not None for row in observations
        ),
        "medianSurfaceStalenessHours": statistics.median(
            row.max_surface_stale_hours for row in observations
        ),
    }
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_deribit_option_information_factor_research",
        "config": asdict(config),
        "period": {
            "startExpiry": iso_ms(expiries[0]),
            "endExpiry": iso_ms(expiries[-1]),
            "requestedExpiries": len(expiries),
            "split": "50% train, 25% validation, 25% reused-history test by expiry",
        },
        "dataSources": {
            "deribit": "https://www.deribit.com/api/v2/public/get_tradingview_chart_data",
            "legacyCache": str(Path(args.legacy_cache).resolve()),
            "factorCache": str(Path(args.factor_cache).resolve()),
            "accountData": False,
        },
        "papers": [
            {"doi": "10.3905/jai.2020.1.112", "factor": "variance risk premium"},
            {"doi": "10.1186/s40854-021-00280-y", "factor": "risk reversal and smile"},
            {"doi": "10.1017/S002210901000013X", "factor": "call-put IV spread"},
            {"doi": "10.1093/rfs/hhj024", "factor": "call-put option volume"},
            {"doi": "10.1093/rfs/hhp008", "factor": "variance premium and expected return"},
        ],
        "trainingThresholds": thresholds,
        "dataQuality": quality,
        "factorIC": factor_ic,
        "selectedDirectional": selected,
        "selectedLongOption": selected_long,
        "directionalResults": [result_payload(row) for row in directional_results],
        "longOptionResults": [result_payload(row) for row in long_option_results],
        "observations": [asdict(row) for row in observations],
        "decision": decision,
    }
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else OUTPUT_ROOT / datetime.now(timezone.utc).strftime("monthly-%Y%m%d")
    )
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    write_csv(output_dir / "observations.csv", [asdict(row) for row in observations])
    write_csv(
        output_dir / "directional_results.csv",
        [result_payload(row) for row in directional_results],
    )
    write_csv(
        output_dir / "long_option_results.csv",
        [result_payload(row) for row in long_option_results],
    )
    print(f"output_dir={output_dir}")
    print(f"observations={len(observations)} quality={json.dumps(quality, sort_keys=True)}")
    print(f"selected_directional={json.dumps(selected, sort_keys=True)}")
    print(f"selected_long_option={json.dumps(selected_long, sort_keys=True)}")
    print(f"decision={json.dumps(decision, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
