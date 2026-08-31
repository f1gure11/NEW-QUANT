"""Development-only Monte Carlo stress test for the pure QQQ stock overlay.

The locked point-in-time stock weights are scaled to 100% factor gross and
sampled together with their following monthly underlying return paths.  OKX
funding is read through the data-lake loader.  The forced 0.01 quantity step,
contract value, margin tiers, and daily execution are synthetic assumptions;
this module has no account, order, paper, or live-trading path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from data_pipeline import load_funding


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT / "config" / "qqq_pure_stock_monte_carlo_preregistration.json"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "reports" / "qqq_pure_stock_monte_carlo"
UTC = timezone.utc

STOP_EXIT = 1
FIXED_PROFIT_EXIT = 2
TRAILING_PROFIT_EXIT = 3
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class EpisodePanel:
    symbols: tuple[str, ...]
    signal_dates: tuple[str, ...]
    ratios: np.ndarray
    valid: np.ndarray
    weights: np.ndarray
    raw_gross: np.ndarray
    initial_prices: np.ndarray
    source_dates: tuple[tuple[str, ...], ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FundingPanel:
    rates: np.ndarray
    dates: tuple[str, ...]
    observed_counts: np.ndarray
    source_start: str
    source_end: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class BootstrapDraws:
    episodes: np.ndarray
    funding: np.ndarray


@dataclass(slots=True)
class PathResults:
    terminal_equity: np.ndarray
    gross_return_pct: np.ndarray
    net_return_pct: np.ndarray
    max_drawdown_pct: np.ndarray
    ruined: np.ndarray
    liquidated: np.ndarray
    stop_exits: np.ndarray
    fixed_profit_exits: np.ndarray
    trailing_profit_exits: np.ndarray
    transaction_cost_usdt: np.ndarray
    liquidation_penalty_usdt: np.ndarray
    funding_pnl_usdt: np.ndarray
    price_pnl_usdt: np.ndarray
    turnover_usdt: np.ndarray
    mean_rebalance_gross_multiple: np.ndarray
    mean_rebalance_positions: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the frozen development-only pure-stock Monte Carlo study."
    )
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def registry_id(study: dict[str, Any]) -> str:
    canonical = json.dumps(
        study, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return "qqq-pure-stock-mc-registry-" + hashlib.sha256(canonical).hexdigest()[:16]


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("schemaVersion") != 1:
        raise ValueError("Unsupported registry schemaVersion")
    study = registry.get("study")
    if not isinstance(study, dict):
        raise ValueError("Registry study is missing")
    expected_id = registry_id(study)
    if registry.get("registryId") != expected_id:
        raise ValueError(f"registryId mismatch: expected {expected_id}")
    if study.get("paperOrLiveAuthorized") is not False:
        raise ValueError("The study must remain paperOrLiveAuthorized=false")
    if study.get("status") != "preregistered_development_only":
        raise ValueError("The study must remain preregistered_development_only")

    portfolio = study["portfolio"]
    if portfolio.get("qqqOrSpyCoreWeight") != 0.0:
        raise ValueError("Index core must be zero")
    if portfolio.get("factorGrossTarget") != 1.0:
        raise ValueError("factorGrossTarget must remain 1.0")
    if portfolio.get("leverageScenarios") != [2.0, 3.0, 5.0, 10.0]:
        raise ValueError("Frozen leverage scenarios changed")
    if portfolio.get("syntheticQuantityIncrement") != 0.01:
        raise ValueError("Synthetic quantity increment changed")

    exits = study["exits"]
    if exits.get("hardStopLossPct") != 15.0:
        raise ValueError("Frozen stop changed")
    variants = exits.get("variants")
    if not isinstance(variants, list) or [row.get("key") for row in variants] != [
        "fixed_take_profit_10pct",
        "trailing_profit_6pct_4pct",
    ]:
        raise ValueError("Frozen exit family changed")
    monte_carlo = study["monteCarlo"]
    if monte_carlo.get("paths") != 4000 or monte_carlo.get("horizonMonths") != 24:
        raise ValueError("Frozen Monte Carlo dimensions changed")

    source = study["source"]
    for path_key, hash_key in (
        ("weightsPath", "weightsSha256"),
        ("lockedModelPath", "lockedModelSha256"),
        ("trackingPath", "trackingSha256"),
    ):
        path = resolve_project_path(str(source[path_key]))
        if sha256_path(path) != source[hash_key]:
            raise ValueError(f"Frozen artifact changed: {path_key}")

    symbols = study["universe"]["symbols"]
    if len(symbols) != 29 or len(set(symbols)) != len(symbols) or "DASH" in symbols:
        raise ValueError("Frozen 29-symbol equity universe changed")
    tracking = read_json(resolve_project_path(source["trackingPath"]))
    tracked = set(tracking.get("trackedInstruments", []))
    missing = [symbol for symbol in symbols if f"{symbol}-USDT-SWAP" not in tracked]
    if missing:
        raise ValueError(f"Symbols missing from validated tracking set: {missing}")


def load_price_panel(price_root: Path, symbols: Sequence[str]) -> pd.DataFrame:
    series: list[pd.Series] = []
    for symbol in symbols:
        path = price_root / f"{symbol}_1d_10y.csv"
        frame = pd.read_csv(path, parse_dates=["date"])
        if "adj_close" not in frame:
            raise ValueError(f"adj_close missing from {path}")
        values = (
            frame.drop_duplicates("date", keep="last")
            .set_index("date")["adj_close"]
            .astype(float)
            .rename(symbol)
        )
        if (values <= 0).any():
            raise ValueError(f"Non-positive adjusted close in {path}")
        series.append(values)
    panel = pd.concat(series, axis=1).sort_index().ffill(limit=5)
    if panel.empty:
        raise ValueError("Price panel is empty")
    return panel


def next_month(value: pd.Timestamp) -> tuple[int, int]:
    month = value.month + 1
    year = value.year
    if month == 13:
        month = 1
        year += 1
    return year, month


def build_episode_panel(registry: dict[str, Any]) -> EpisodePanel:
    study = registry["study"]
    source = study["source"]
    symbols = tuple(study["universe"]["symbols"])
    weights_frame = pd.read_csv(resolve_project_path(source["weightsPath"]))
    selected = weights_frame[
        (weights_frame["mode"] == "monthly")
        & (weights_frame["signalDate"] >= source["signalStart"])
        & (weights_frame["signalDate"] <= source["signalEnd"])
        & (weights_frame["symbol"].isin(symbols))
    ].copy()
    pivot = selected.pivot(index="signalDate", columns="symbol", values="activeWeight")
    pivot = pivot.reindex(columns=symbols).fillna(0.0).sort_index()
    expected_episodes = int(source["sourceEpisodes"])
    if len(pivot) != expected_episodes:
        raise ValueError(f"Expected {expected_episodes} signal episodes, found {len(pivot)}")
    raw_gross = pivot.abs().sum(axis=1).to_numpy(dtype=float)
    if np.any(raw_gross <= EPSILON):
        raise ValueError("A source signal has zero gross after exclusions")
    normalized = pivot.to_numpy(dtype=float) / raw_gross[:, None]

    price_panel = load_price_panel(resolve_project_path(source["priceRoot"]), symbols)
    ratios = price_panel.pct_change().add(1.0)
    episode_frames: list[pd.DataFrame] = []
    source_dates: list[tuple[str, ...]] = []
    for signal_text in pivot.index:
        signal = pd.Timestamp(signal_text)
        year, month = next_month(signal)
        mask = (
            (ratios.index.year == year)
            & (ratios.index.month == month)
            & (ratios.index >= pd.Timestamp(source["returnStart"]))
            & (ratios.index <= pd.Timestamp(source["returnEnd"]))
        )
        frame = ratios.loc[mask, list(symbols)].dropna(how="any")
        if len(frame) < 15:
            raise ValueError(f"Incomplete following-month price episode for {signal_text}")
        episode_frames.append(frame)
        source_dates.append(tuple(value.date().isoformat() for value in frame.index))

    max_days = max(len(frame) for frame in episode_frames)
    ratio_cube = np.ones((len(episode_frames), max_days, len(symbols)), dtype=float)
    valid = np.zeros((len(episode_frames), max_days), dtype=bool)
    for index, frame in enumerate(episode_frames):
        length = len(frame)
        ratio_cube[index, :length, :] = frame.to_numpy(dtype=float)
        valid[index, :length] = True

    initial_at = pd.Timestamp(source["initialPriceDate"])
    initial_rows = price_panel.loc[:initial_at]
    if initial_rows.empty or initial_rows.index[-1] != initial_at:
        raise ValueError("Frozen initialPriceDate is unavailable")
    initial_prices = initial_rows.iloc[-1].to_numpy(dtype=float)
    digest = hashlib.sha256()
    digest.update("|".join(symbols).encode("ascii"))
    digest.update("|".join(pivot.index).encode("ascii"))
    digest.update(np.ascontiguousarray(ratio_cube).tobytes())
    digest.update(np.ascontiguousarray(normalized).tobytes())

    return EpisodePanel(
        symbols=symbols,
        signal_dates=tuple(str(value) for value in pivot.index),
        ratios=ratio_cube,
        valid=valid,
        weights=normalized,
        raw_gross=raw_gross,
        initial_prices=initial_prices,
        source_dates=tuple(source_dates),
        fingerprint=digest.hexdigest(),
    )


def load_funding_panel(registry: dict[str, Any], symbols: Sequence[str]) -> FundingPanel:
    minimum_ratio = float(
        registry["study"]["monteCarlo"]["fundingMinimumSymbolCoverageRatio"]
    )
    daily_rates: list[pd.Series] = []
    daily_observed: list[pd.Series] = []
    for symbol in symbols:
        frame = load_funding(f"{symbol}-USDT-SWAP")
        if frame.empty:
            rates = pd.Series(dtype=float, name=symbol)
            observed = pd.Series(dtype=int, name=symbol)
        else:
            day = frame["funding_time"].dt.floor("D")
            rates = frame.groupby(day)["realized_rate"].sum().astype(float).rename(symbol)
            observed = frame.groupby(day).size().gt(0).astype(int).rename(symbol)
        daily_rates.append(rates)
        daily_observed.append(observed)
    rates_frame = pd.concat(daily_rates, axis=1).sort_index()
    observed_frame = pd.concat(daily_observed, axis=1).fillna(0).astype(int).sort_index()
    minimum_symbols = int(math.ceil(len(symbols) * minimum_ratio))
    observed_counts = observed_frame.sum(axis=1)
    eligible_dates = observed_counts[observed_counts >= minimum_symbols].index
    rates_frame = rates_frame.reindex(eligible_dates).fillna(
        float(registry["study"]["monteCarlo"]["missingFundingFill"])
    )
    if rates_frame.empty:
        raise ValueError("No funding dates satisfy the frozen coverage rule")
    values = rates_frame.reindex(columns=symbols).to_numpy(dtype=float)
    digest = hashlib.sha256()
    digest.update("|".join(value.date().isoformat() for value in eligible_dates).encode("ascii"))
    digest.update(np.ascontiguousarray(values).tobytes())
    return FundingPanel(
        rates=values,
        dates=tuple(value.date().isoformat() for value in eligible_dates),
        observed_counts=observed_counts.loc[eligible_dates].to_numpy(dtype=int),
        source_start=eligible_dates[0].date().isoformat(),
        source_end=eligible_dates[-1].date().isoformat(),
        fingerprint=digest.hexdigest(),
    )


def generate_draws(
    *,
    paths: int,
    months: int,
    max_days: int,
    episodes: int,
    funding_days: int,
    seed: int,
) -> BootstrapDraws:
    rng = np.random.default_rng(seed)
    return BootstrapDraws(
        episodes=rng.integers(0, episodes, size=(paths, months), dtype=np.int16),
        funding=rng.integers(
            0, funding_days, size=(paths, months, max_days), dtype=np.int16
        ),
    )


def ordered_draws(panel: EpisodePanel) -> BootstrapDraws:
    episode_rows = np.arange(len(panel.signal_dates), dtype=np.int16)[None, :]
    funding_rows = np.zeros(
        (1, len(panel.signal_dates), panel.ratios.shape[1]), dtype=np.int16
    )
    return BootstrapDraws(episodes=episode_rows, funding=funding_rows)


def floor_quantities(
    weights: np.ndarray,
    equity: np.ndarray,
    prices: np.ndarray,
    *,
    leverage: float,
    increment: float,
) -> np.ndarray:
    desired_notional = equity[:, None] * leverage * weights
    raw = np.divide(
        np.abs(desired_notional),
        prices,
        out=np.zeros_like(prices),
        where=prices > 0,
    )
    lots = np.floor(raw / increment + EPSILON)
    return np.sign(desired_notional) * lots * increment


def update_drawdown(
    equity: np.ndarray, peak_equity: np.ndarray, max_drawdown: np.ndarray
) -> None:
    np.maximum(peak_equity, equity, out=peak_equity)
    drawdown = np.divide(
        peak_equity - equity,
        peak_equity,
        out=np.zeros_like(equity),
        where=peak_equity > 0,
    )
    np.maximum(max_drawdown, drawdown, out=max_drawdown)


def simulate_paths(
    panel: EpisodePanel,
    funding_rates: np.ndarray,
    draws: BootstrapDraws,
    *,
    initial_equity: float,
    leverage: float,
    quantity_increment: float,
    per_side_bps: float,
    funding_multiplier: float,
    maintenance_margin_fraction: float,
    liquidation_penalty_bps: float,
    hard_stop_fraction: float,
    exit_variant: dict[str, Any],
) -> PathResults:
    paths, months = draws.episodes.shape
    if months != draws.funding.shape[1]:
        raise ValueError("Episode and funding draw dimensions differ")
    if draws.funding.shape[2] != panel.ratios.shape[1]:
        raise ValueError("Funding draws do not match episode day dimension")
    if funding_rates.shape[1] != len(panel.symbols):
        raise ValueError("Funding rates do not match episode symbols")

    prices = np.tile(panel.initial_prices, (paths, 1)).astype(float)
    quantities = np.zeros_like(prices)
    entry_prices = np.zeros_like(prices)
    peak_favorable = np.zeros_like(prices)
    pending_exit = np.zeros(prices.shape, dtype=np.int8)
    equity = np.full(paths, initial_equity, dtype=float)
    peak_equity = equity.copy()
    max_drawdown = np.zeros(paths, dtype=float)
    done = np.zeros(paths, dtype=bool)
    ruined = np.zeros(paths, dtype=bool)
    liquidated = np.zeros(paths, dtype=bool)
    stop_exits = np.zeros(paths, dtype=np.int32)
    fixed_profit_exits = np.zeros(paths, dtype=np.int32)
    trailing_profit_exits = np.zeros(paths, dtype=np.int32)
    transaction_cost = np.zeros(paths, dtype=float)
    liquidation_penalty = np.zeros(paths, dtype=float)
    funding_pnl = np.zeros(paths, dtype=float)
    price_pnl = np.zeros(paths, dtype=float)
    turnover = np.zeros(paths, dtype=float)
    gross_sum = np.zeros(paths, dtype=float)
    position_sum = np.zeros(paths, dtype=float)
    rebalance_count = np.zeros(paths, dtype=np.int32)

    cost_rate = per_side_bps / 10_000.0
    liquidation_rate = liquidation_penalty_bps / 10_000.0
    variant_type = str(exit_variant["type"])
    profit_code = (
        FIXED_PROFIT_EXIT
        if variant_type == "fixed_take_profit"
        else TRAILING_PROFIT_EXIT
    )

    for month in range(months):
        choices = draws.episodes[:, month]
        alive = ~done
        pending_exit[alive, :] = 0
        target_weights = panel.weights[choices]
        target_quantities = floor_quantities(
            target_weights,
            np.maximum(equity, 0.0),
            prices,
            leverage=leverage,
            increment=quantity_increment,
        )
        target_quantities[~alive, :] = 0.0
        trade_notional_by_symbol = np.abs(target_quantities - quantities) * prices
        traded = trade_notional_by_symbol.sum(axis=1)
        costs = traded * cost_rate
        equity[alive] -= costs[alive]
        transaction_cost += costs
        turnover += traded
        quantities = target_quantities
        entry_prices = np.where(np.abs(quantities) > EPSILON, prices, 0.0)
        peak_favorable.fill(0.0)
        gross = (np.abs(quantities) * prices).sum(axis=1)
        positive_equity = np.maximum(equity, EPSILON)
        gross_sum[alive] += gross[alive] / positive_equity[alive]
        position_sum[alive] += np.count_nonzero(
            np.abs(quantities[alive]) > EPSILON, axis=1
        )
        rebalance_count[alive] += 1
        ruined_now = alive & (equity <= 0.0)
        if ruined_now.any():
            ruined[ruined_now] = True
            done[ruined_now] = True
            quantities[ruined_now, :] = 0.0
        update_drawdown(equity, peak_equity, max_drawdown)

        for day in range(panel.ratios.shape[1]):
            observed = panel.valid[choices, day] & ~done
            if not observed.any():
                continue
            ratios = panel.ratios[choices, day, :]
            old_prices = prices.copy()
            prices[observed, :] *= ratios[observed, :]
            pnl = (quantities * (prices - old_prices)).sum(axis=1)
            equity[observed] += pnl[observed]
            price_pnl[observed] += pnl[observed]

            sampled_funding = funding_rates[draws.funding[:, month, day]]
            funding_flow = -(
                quantities * prices * sampled_funding
            ).sum(axis=1) * funding_multiplier
            equity[observed] += funding_flow[observed]
            funding_pnl[observed] += funding_flow[observed]

            gross = (np.abs(quantities) * prices).sum(axis=1)
            ruined_now = observed & (equity <= 0.0)
            if ruined_now.any():
                ruined[ruined_now] = True
                done[ruined_now] = True
                quantities[ruined_now, :] = 0.0

            maintenance_breach = (
                observed
                & ~done
                & (gross > EPSILON)
                & (equity <= gross * maintenance_margin_fraction)
            )
            if maintenance_breach.any():
                close_cost = gross * cost_rate
                penalty = gross * liquidation_rate
                equity[maintenance_breach] -= (
                    close_cost[maintenance_breach] + penalty[maintenance_breach]
                )
                transaction_cost[maintenance_breach] += close_cost[maintenance_breach]
                liquidation_penalty[maintenance_breach] += penalty[maintenance_breach]
                turnover[maintenance_breach] += gross[maintenance_breach]
                liquidated[maintenance_breach] = True
                ruined[maintenance_breach] |= equity[maintenance_breach] <= 0.0
                done[maintenance_breach] = True
                quantities[maintenance_breach, :] = 0.0
                pending_exit[maintenance_breach, :] = 0

            closable = observed[:, None] & ~done[:, None] & (pending_exit > 0)
            if closable.any():
                close_notional_by_symbol = np.where(
                    closable, np.abs(quantities) * prices, 0.0
                )
                close_notional = close_notional_by_symbol.sum(axis=1)
                close_cost = close_notional * cost_rate
                equity -= close_cost
                transaction_cost += close_cost
                turnover += close_notional
                stop_exits += np.count_nonzero(
                    closable & (pending_exit == STOP_EXIT), axis=1
                )
                fixed_profit_exits += np.count_nonzero(
                    closable & (pending_exit == FIXED_PROFIT_EXIT), axis=1
                )
                trailing_profit_exits += np.count_nonzero(
                    closable & (pending_exit == TRAILING_PROFIT_EXIT), axis=1
                )
                quantities[closable] = 0.0
                entry_prices[closable] = 0.0
                peak_favorable[closable] = 0.0
                pending_exit[closable] = 0
                ruined_after_exit = observed & (equity <= 0.0)
                if ruined_after_exit.any():
                    ruined[ruined_after_exit] = True
                    done[ruined_after_exit] = True
                    quantities[ruined_after_exit, :] = 0.0

            active = (
                observed[:, None]
                & ~done[:, None]
                & (np.abs(quantities) > EPSILON)
            )
            side = np.sign(quantities)
            favorable = np.zeros_like(prices)
            np.divide(
                prices,
                entry_prices,
                out=favorable,
                where=active & (entry_prices > 0),
            )
            favorable = side * (favorable - 1.0)
            hard_stop = active & (favorable <= -hard_stop_fraction)
            if variant_type == "fixed_take_profit":
                profit = active & (
                    favorable >= float(exit_variant["takeProfitPct"]) / 100.0
                )
            elif variant_type == "trailing_take_profit":
                np.maximum(peak_favorable, favorable, out=peak_favorable, where=active)
                activation = float(exit_variant["activationPct"]) / 100.0
                giveback = float(exit_variant["givebackPercentagePoints"]) / 100.0
                profit = (
                    active
                    & (peak_favorable >= activation)
                    & (favorable <= peak_favorable - giveback)
                )
            else:
                raise ValueError(f"Unsupported exit type: {variant_type}")
            pending_exit[hard_stop] = STOP_EXIT
            pending_exit[profit & ~hard_stop] = profit_code
            update_drawdown(equity, peak_equity, max_drawdown)

    terminal_alive = ~done
    terminal_notional = (np.abs(quantities) * prices).sum(axis=1)
    terminal_cost = terminal_notional * cost_rate
    equity[terminal_alive] -= terminal_cost[terminal_alive]
    transaction_cost[terminal_alive] += terminal_cost[terminal_alive]
    turnover[terminal_alive] += terminal_notional[terminal_alive]
    quantities[terminal_alive, :] = 0.0
    ruined |= equity <= 0.0
    update_drawdown(equity, peak_equity, max_drawdown)
    counts = np.maximum(rebalance_count, 1)

    return PathResults(
        terminal_equity=equity,
        gross_return_pct=price_pnl / initial_equity * 100.0,
        net_return_pct=(equity / initial_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown * 100.0,
        ruined=ruined,
        liquidated=liquidated,
        stop_exits=stop_exits,
        fixed_profit_exits=fixed_profit_exits,
        trailing_profit_exits=trailing_profit_exits,
        transaction_cost_usdt=transaction_cost,
        liquidation_penalty_usdt=liquidation_penalty,
        funding_pnl_usdt=funding_pnl,
        price_pnl_usdt=price_pnl,
        turnover_usdt=turnover,
        mean_rebalance_gross_multiple=gross_sum / counts,
        mean_rebalance_positions=position_sum / counts,
    )


def percentile_dict(values: np.ndarray) -> dict[str, float]:
    quantiles = np.quantile(values, [0.01, 0.05, 0.50, 0.95, 0.99])
    return {
        "p01": float(quantiles[0]),
        "p05": float(quantiles[1]),
        "p50": float(quantiles[2]),
        "p95": float(quantiles[3]),
        "p99": float(quantiles[4]),
    }


def summarize_paths(result: PathResults) -> dict[str, Any]:
    return {
        "paths": int(len(result.terminal_equity)),
        "terminalEquityUsdt": percentile_dict(result.terminal_equity),
        "grossReturnPct": percentile_dict(result.gross_return_pct),
        "netReturnPct": percentile_dict(result.net_return_pct),
        "maxDrawdownPct": percentile_dict(result.max_drawdown_pct),
        "ruinProbabilityPct": float(result.ruined.mean() * 100.0),
        "liquidationProbabilityPct": float(result.liquidated.mean() * 100.0),
        "drawdownAtLeast50ProbabilityPct": float(
            (result.max_drawdown_pct >= 50.0).mean() * 100.0
        ),
        "drawdownAtLeast90ProbabilityPct": float(
            (result.max_drawdown_pct >= 90.0).mean() * 100.0
        ),
        "meanStopExits": float(result.stop_exits.mean()),
        "meanFixedProfitExits": float(result.fixed_profit_exits.mean()),
        "meanTrailingProfitExits": float(result.trailing_profit_exits.mean()),
        "meanTransactionCostUsdt": float(result.transaction_cost_usdt.mean()),
        "meanLiquidationPenaltyUsdt": float(result.liquidation_penalty_usdt.mean()),
        "meanFundingPnlUsdt": float(result.funding_pnl_usdt.mean()),
        "meanPricePnlUsdt": float(result.price_pnl_usdt.mean()),
        "meanTurnoverUsdt": float(result.turnover_usdt.mean()),
        "meanRebalanceGrossMultiple": float(
            result.mean_rebalance_gross_multiple.mean()
        ),
        "meanRebalancePositions": float(result.mean_rebalance_positions.mean()),
        "accountingResidualMaxAbsUsdt": float(
            np.max(
                np.abs(
                    result.terminal_equity
                    - (
                        100.0
                        + result.price_pnl_usdt
                        + result.funding_pnl_usdt
                        - result.transaction_cost_usdt
                        - result.liquidation_penalty_usdt
                    )
                )
            )
        ),
    }


def source_split_diagnostics(
    panel: EpisodePanel, split: dict[str, list[str] | str]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    ranges = {
        "train": split["trainSignalDates"],
        "validation": split["validationSignalDates"],
        "test": split["testSignalDates"],
    }
    for key, bounds in ranges.items():
        start, end = str(bounds[0]), str(bounds[1])
        daily: list[float] = []
        episode_returns: list[float] = []
        for index, signal in enumerate(panel.signal_dates):
            if not start <= signal <= end:
                continue
            valid = panel.valid[index]
            returns = (panel.ratios[index, valid, :] - 1.0) @ panel.weights[index]
            daily.extend(returns.tolist())
            episode_returns.append(float(np.prod(1.0 + returns) - 1.0))
        values = np.asarray(daily, dtype=float)
        curve = np.cumprod(1.0 + values) if len(values) else np.asarray([1.0])
        peaks = np.maximum.accumulate(np.concatenate(([1.0], curve)))
        curve_with_start = np.concatenate(([1.0], curve))
        drawdown = 1.0 - curve_with_start / peaks
        total = float(curve[-1] - 1.0) if len(values) else 0.0
        annualized = (
            float((1.0 + total) ** (252.0 / len(values)) - 1.0)
            if len(values) and total > -1.0
            else -1.0
        )
        result[key] = {
            "signalStart": start,
            "signalEnd": end,
            "episodes": len(episode_returns),
            "tradingDays": int(len(values)),
            "factorGrossOneTotalReturnPct": total * 100.0,
            "factorGrossOneAnnualizedReturnPct": annualized * 100.0,
            "annualizedVolatilityPct": float(values.std(ddof=1) * math.sqrt(252) * 100.0)
            if len(values) > 1
            else 0.0,
            "maxDrawdownPct": float(drawdown.max() * 100.0),
            "positiveEpisodePct": float(np.mean(np.asarray(episode_returns) > 0) * 100.0)
            if episode_returns
            else 0.0,
        }
    return result


def scenario_row(scenario: dict[str, Any]) -> dict[str, Any]:
    mc = scenario["monteCarlo"]
    historical = scenario["chronologicalReplay"]
    return {
        "exitVariant": scenario["exitVariant"],
        "leverage": scenario["leverage"],
        "costProfile": scenario["costProfile"],
        "perSideBps": scenario["perSideBps"],
        "grossReturnP50Pct": mc["grossReturnPct"]["p50"],
        "netReturnP01Pct": mc["netReturnPct"]["p01"],
        "netReturnP05Pct": mc["netReturnPct"]["p05"],
        "netReturnP50Pct": mc["netReturnPct"]["p50"],
        "netReturnP95Pct": mc["netReturnPct"]["p95"],
        "netReturnP99Pct": mc["netReturnPct"]["p99"],
        "terminalEquityP50Usdt": mc["terminalEquityUsdt"]["p50"],
        "ruinProbabilityPct": mc["ruinProbabilityPct"],
        "liquidationProbabilityPct": mc["liquidationProbabilityPct"],
        "drawdown50ProbabilityPct": mc["drawdownAtLeast50ProbabilityPct"],
        "drawdown90ProbabilityPct": mc["drawdownAtLeast90ProbabilityPct"],
        "maxDrawdownP50Pct": mc["maxDrawdownPct"]["p50"],
        "maxDrawdownP95Pct": mc["maxDrawdownPct"]["p95"],
        "meanStopExits": mc["meanStopExits"],
        "meanProfitExits": mc["meanFixedProfitExits"] + mc["meanTrailingProfitExits"],
        "meanTransactionCostUsdt": mc["meanTransactionCostUsdt"],
        "meanFundingPnlUsdt": mc["meanFundingPnlUsdt"],
        "meanTurnoverUsdt": mc["meanTurnoverUsdt"],
        "meanRebalanceGrossMultiple": mc["meanRebalanceGrossMultiple"],
        "meanRebalancePositions": mc["meanRebalancePositions"],
        "chronologicalReplayNetReturnPct": historical["netReturnPct"]["p50"],
        "chronologicalReplayMaxDrawdownPct": historical["maxDrawdownPct"]["p50"],
        "chronologicalReplayLiquidated": historical["liquidationProbabilityPct"] > 0,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value:.2f}%"


def render_report(payload: dict[str, Any]) -> str:
    study = payload["study"]
    data = payload["data"]
    lines = [
        "# Pure-stock factor Monte Carlo (development only)",
        "",
        f"Registry: `{payload['registryId']}`. Generated: `{payload['generatedAt']}`.",
        "",
        "This is a risk stress test on inspected history, not new validation and not paper/live authorization. "
        "The book has no QQQ or SPY core. Locked factor weights are normalized to 100% gross, then leverage sets notional gross.",
        "",
        "## Frozen model and data",
        "",
        f"- Universe: {data['symbols']} validated equity mappings; DASH crypto is excluded.",
        f"- Source: {data['episodes']} completed monthly signal/return episodes, {data['sourceTradingDays']} underlying daily closes.",
        f"- Monte Carlo: {study['monteCarlo']['paths']} paths x {study['monteCarlo']['horizonMonths']} sampled months, seed {study['monteCarlo']['seed']}.",
        f"- Funding proxy: {data['fundingDays']} synchronized OKX daily vectors from {data['fundingStart']} through {data['fundingEnd']}; missing symbol-days are zero and trading-day funding is multiplied by {study['monteCarlo']['tradingDayToCalendarFundingMultiplier']:.1f}.",
        "- Position increment: synthetic 0.01 underlying share with contract value 1. This overrides real ctVal/lotSz/minSz and is not executable sizing proof.",
        "- Exit trigger: completed daily close; execution: next completed daily close. Intraday touches and true OKX liquidation marks are unavailable.",
        "",
        "## Monte Carlo results",
        "",
        "| Exit | Lev | Cost/side | Actual gross | Gross P50 | Net P1 | Net P5 | Net P50 | Net P95 | Net P99 | Ruin | Liq proxy | DD>=50 | DD>=90 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario in payload["scenarios"]:
        mc = scenario["monteCarlo"]
        lines.append(
            "| {exit} | {leverage:.0f}x | {cost:.0f} bps | {actual_gross:.2f}x | {gross_p50} | {p01} | {p05} | {p50} | {p95} | {p99} | {ruin} | {liq} | {dd50} | {dd90} |".format(
                exit=scenario["exitVariant"],
                leverage=scenario["leverage"],
                cost=scenario["perSideBps"],
                actual_gross=mc["meanRebalanceGrossMultiple"],
                gross_p50=pct(mc["grossReturnPct"]["p50"]),
                p01=pct(mc["netReturnPct"]["p01"]),
                p05=pct(mc["netReturnPct"]["p05"]),
                p50=pct(mc["netReturnPct"]["p50"]),
                p95=pct(mc["netReturnPct"]["p95"]),
                p99=pct(mc["netReturnPct"]["p99"]),
                ruin=pct(mc["ruinProbabilityPct"]),
                liq=pct(mc["liquidationProbabilityPct"]),
                dd50=pct(mc["drawdownAtLeast50ProbabilityPct"]),
                dd90=pct(mc["drawdownAtLeast90ProbabilityPct"]),
            )
        )
    lines.extend(
        [
            "",
            "`Liq proxy` uses cross-margin liquidation when completed-close equity is at or below 5% of gross notional, plus a 50 bps gross penalty. "
            "Actual OKX tiering, mark price, intraday liquidation, ADL, and insurance behavior can differ materially.",
            "",
            "## Activity and friction",
            "",
            "| Exit | Lev | Cost/side | Positions | Stops | Profit exits | Cost | Funding PnL | Turnover |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario in payload["scenarios"]:
        mc = scenario["monteCarlo"]
        profit_exits = mc["meanFixedProfitExits"] + mc["meanTrailingProfitExits"]
        lines.append(
            f"| {scenario['exitVariant']} | {scenario['leverage']:.0f}x | {scenario['perSideBps']:.0f} bps | "
            f"{mc['meanRebalancePositions']:.1f} | {mc['meanStopExits']:.1f} | {profit_exits:.1f} | "
            f"{mc['meanTransactionCostUsdt']:.2f} USDT | {mc['meanFundingPnlUsdt']:.2f} USDT | "
            f"{mc['meanTurnoverUsdt']:.0f} USDT |"
        )
    lines.extend(
        [
            "",
            "## Source stability (no leverage, exits, costs, or funding)",
            "",
            "| Split | Episodes | Return | Annualized | Volatility | Max DD | Positive months |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for key in ("train", "validation", "test"):
        row = payload["sourceSplitDiagnostics"][key]
        lines.append(
            f"| {key} | {row['episodes']} | {pct(row['factorGrossOneTotalReturnPct'])} | "
            f"{pct(row['factorGrossOneAnnualizedReturnPct'])} | {pct(row['annualizedVolatilityPct'])} | "
            f"{pct(row['maxDrawdownPct'])} | {pct(row['positiveEpisodePct'])} |"
        )
    lines.extend(
        [
            "",
            "## Reading the result",
            "",
            "- Gross return is price PnL before transaction cost, funding, and liquidation penalty. Net return includes all modeled items.",
            "- P1/P5 are downside percentiles across the same frozen random paths used for every scenario. They are empirical bootstrap tails, not guarantees.",
            "- A leg stopped or profit-exited remains flat until the next sampled monthly factor rebalance.",
            "- The direct chronological replay in `scenario_rows.csv` is descriptive only and uses the mean available funding vector; it is not a separate validation sample.",
            "- Parameters must not be changed after reading this report and then retested on the same source window.",
            "",
        ]
    )
    return "\n".join(lines)


def run_study(registry_path: Path, output_dir: Path) -> dict[str, Any]:
    registry = read_json(registry_path)
    validate_registry(registry)
    study = registry["study"]
    panel = build_episode_panel(registry)
    funding = load_funding_panel(registry, panel.symbols)
    monte_carlo = study["monteCarlo"]
    draws = generate_draws(
        paths=int(monte_carlo["paths"]),
        months=int(monte_carlo["horizonMonths"]),
        max_days=panel.ratios.shape[1],
        episodes=len(panel.signal_dates),
        funding_days=len(funding.dates),
        seed=int(monte_carlo["seed"]),
    )
    historical_draws = ordered_draws(panel)
    historical_funding = funding.rates.mean(axis=0, keepdims=True)
    scenarios: list[dict[str, Any]] = []
    portfolio = study["portfolio"]
    margin = study["margin"]
    exits = study["exits"]
    for exit_variant in exits["variants"]:
        for leverage in portfolio["leverageScenarios"]:
            for cost_profile in study["costs"]["profiles"]:
                common = {
                    "initial_equity": float(portfolio["initialEquityUsdt"]),
                    "leverage": float(leverage),
                    "quantity_increment": float(
                        portfolio["syntheticQuantityIncrement"]
                    ),
                    "per_side_bps": float(cost_profile["perSideBps"]),
                    "funding_multiplier": float(
                        monte_carlo["tradingDayToCalendarFundingMultiplier"]
                    ),
                    "maintenance_margin_fraction": float(
                        margin["maintenanceMarginPctOfGross"]
                    )
                    / 100.0,
                    "liquidation_penalty_bps": float(
                        margin["liquidationPenaltyBpsOfGross"]
                    ),
                    "hard_stop_fraction": float(exits["hardStopLossPct"]) / 100.0,
                    "exit_variant": exit_variant,
                }
                result = simulate_paths(panel, funding.rates, draws, **common)
                historical = simulate_paths(
                    panel,
                    historical_funding,
                    historical_draws,
                    **common,
                )
                scenarios.append(
                    {
                        "exitVariant": exit_variant["key"],
                        "leverage": float(leverage),
                        "costProfile": cost_profile["key"],
                        "perSideBps": float(cost_profile["perSideBps"]),
                        "monteCarlo": summarize_paths(result),
                        "chronologicalReplay": summarize_paths(historical),
                    }
                )

    payload = {
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_development_only_pure_stock_monte_carlo",
        "registryId": registry["registryId"],
        "registrySha256": sha256_path(registry_path),
        "study": study,
        "data": {
            "symbols": len(panel.symbols),
            "symbolList": list(panel.symbols),
            "episodes": len(panel.signal_dates),
            "signalDates": list(panel.signal_dates),
            "sourceTradingDays": int(panel.valid.sum()),
            "episodeTradingDaysMin": int(panel.valid.sum(axis=1).min()),
            "episodeTradingDaysMax": int(panel.valid.sum(axis=1).max()),
            "rawFactorGrossMin": float(panel.raw_gross.min()),
            "rawFactorGrossMax": float(panel.raw_gross.max()),
            "normalizedMaxSingleNameWeightPct": float(
                np.abs(panel.weights).max() * 100.0
            ),
            "episodeFingerprint": panel.fingerprint,
            "fundingDays": len(funding.dates),
            "fundingStart": funding.source_start,
            "fundingEnd": funding.source_end,
            "fundingObservedSymbolsMin": int(funding.observed_counts.min()),
            "fundingObservedSymbolsMax": int(funding.observed_counts.max()),
            "fundingFingerprint": funding.fingerprint,
        },
        "sourceSplitDiagnostics": source_split_diagnostics(
            panel, registry["protocol"]["chronologicalSourceSplit"]
        ),
        "scenarios": scenarios,
        "decision": {
            "classification": "development_only",
            "newValidation": False,
            "paperOrLiveAuthorized": False,
            "parameterSelectionAllowed": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    write_csv(output_dir / "scenario_rows.csv", [scenario_row(row) for row in scenarios])
    (output_dir / "report.md").write_text(render_report(payload), encoding="utf-8")
    return payload


def resolve_output_dir(value: str) -> Path:
    if value:
        return Path(value)
    stamp = datetime.now(UTC).strftime("pure-stock-mc-%Y%m%dT%H%M%SZ")
    return DEFAULT_OUTPUT_ROOT / stamp


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    payload = run_study(Path(args.registry), output_dir)
    print(
        json.dumps(
            {
                "outputDir": str(output_dir),
                "registryId": payload["registryId"],
                "scenarios": len(payload["scenarios"]),
                "classification": payload["decision"]["classification"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
