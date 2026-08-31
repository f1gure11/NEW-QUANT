#!/usr/bin/env python3
"""Frozen development-only US-equity mean-reversion portfolio research."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data_pipeline import load_funding


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "config" / "us_equity_mean_reversion_preregistration.json"
DEFAULT_REPORT_ROOT = PROJECT_ROOT / "reports" / "us_equity_mean_reversion"
EPSILON = 1e-12


@dataclass(slots=True)
class SimulationResult:
    strategy: str
    split: str
    leverage: int
    cost_profile: str
    start: str
    end: str
    sessions: int
    initial_equity: float
    terminal_equity: float
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe: float
    profit_factor: float
    max_drawdown_pct: float
    turnover_usd: float
    trade_orders: int
    average_realized_gross: float
    maximum_realized_gross: float
    transaction_cost_usd: float
    financing_cost_usd: float
    short_borrow_cost_usd: float
    liquidation_penalty_usd: float
    price_pnl_usd: float
    liquidated: bool
    ruined: bool


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def derived_id(prefix: str, value: dict[str, Any]) -> str:
    return f"{prefix}-{hashlib.sha256(canonical_json(value)).hexdigest()[:16]}"


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def price_path(root: Path, symbol: str) -> Path:
    return root / f"{symbol}_1d_10y.csv"


def price_bundle_matches_contract(root: Path, symbols: list[str], data: dict[str, Any]) -> bool:
    """Require the frozen date window and row count, not rolling Yahoo 10y bytes."""

    start = pd.Timestamp(str(data["commonStart"]))
    end = pd.Timestamp(str(data["commonEnd"]))
    expected_rows = int(data["commonRows"])
    for symbol in symbols:
        path = price_path(root, symbol)
        if not path.exists():
            return False
        frame = pd.read_csv(path, parse_dates=["date"]).drop_duplicates("date", keep="last").sort_values("date")
        window = frame[(frame["date"] >= start) & (frame["date"] <= end)]
        if len(window) != expected_rows:
            return False
        values = window["adj_close"].astype(float)
        if values.isna().any() or (values <= 0).any():
            return False
    return True


def price_bundle_sha256(root: Path, symbols: list[str]) -> str:
    digest = hashlib.sha256()
    for symbol in sorted(symbols):
        content = price_path(root, symbol).read_bytes()
        digest.update(symbol.encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_registry(registry: dict[str, Any]) -> None:
    required = {"schemaVersion", "registryId", "frozenAt", "protocol", "study"}
    missing = required - set(registry)
    if missing:
        raise ValueError(f"registry missing fields: {sorted(missing)}")
    study = registry["study"]
    model_basis = {key: value for key, value in study.items() if key != "modelId"}
    if study.get("modelId") != derived_id("us-equity-mr", model_basis):
        raise ValueError("modelId does not match frozen study content")
    registry_basis = {key: registry[key] for key in ("frozenAt", "protocol", "study")}
    if registry.get("registryId") != derived_id("us-equity-mr-registry", registry_basis):
        raise ValueError("registryId does not match frozen registry content")
    if study.get("status") != "preregistered_development_only":
        raise ValueError("study must remain preregistered_development_only")
    if study.get("paperOrLiveAuthorized") is not False:
        raise ValueError("study cannot authorize paper or live trading")
    symbols = study["universe"]["symbols"]
    if len(symbols) != 26 or symbols != sorted(set(symbols)) or "QQQ" in symbols:
        raise ValueError("frozen universe must contain 26 sorted unique equities")
    if study["portfolio"]["grossLeverageScenarios"] != list(range(2, 11)):
        raise ValueError("frozen leverage scenarios changed")
    if study["portfolio"]["fractionalShareIncrement"] != 0.01:
        raise ValueError("fractional-share increment changed")
    splits = study["split"]
    if [splits[key]["rows"] for key in ("train", "validation", "test")] != [1131, 565, 566]:
        raise ValueError("frozen chronological split changed")
    if [row["key"] for row in study["portfolios"]] != [
        "cross_sectional_5d_reversal",
        "market_residual_5d_reversal",
        "distance_pairs_252_126",
    ]:
        raise ValueError("frozen portfolio family changed")
    root = PROJECT_ROOT / study["data"]["priceRoot"]
    bundle_symbols = [*symbols, study["universe"]["marketProxy"]]
    if not price_bundle_matches_contract(root, bundle_symbols, study["data"]):
        raise ValueError("frozen price bundle changed")


def load_price_panel(registry: dict[str, Any]) -> pd.DataFrame:
    study = registry["study"]
    root = PROJECT_ROOT / study["data"]["priceRoot"]
    symbols = [*study["universe"]["symbols"], study["universe"]["marketProxy"]]
    series: list[pd.Series] = []
    for symbol in symbols:
        frame = pd.read_csv(price_path(root, symbol), parse_dates=["date"])
        start = pd.Timestamp(str(study["data"]["commonStart"]))
        end = pd.Timestamp(str(study["data"]["commonEnd"]))
        frame = frame.drop_duplicates("date", keep="last").sort_values("date")
        frame = frame[(frame["date"] >= start) & (frame["date"] <= end)]
        values = frame.set_index("date")["adj_close"].astype(float)
        if len(values) != int(study["data"]["commonRows"]) or values.isna().any() or (values <= 0).any():
            raise ValueError(f"invalid frozen price series: {symbol}")
        series.append(values.rename(symbol))
    panel = pd.concat(series, axis=1, join="inner").sort_index()
    if len(panel) != int(study["data"]["commonRows"]):
        raise ValueError("common price panel row count changed")
    if panel.index[0].date().isoformat() != study["data"]["commonStart"]:
        raise ValueError("common price panel start changed")
    if panel.index[-1].date().isoformat() != study["data"]["commonEnd"]:
        raise ValueError("common price panel end changed")
    return panel


def split_locations(panel: pd.DataFrame, study: dict[str, Any]) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for key in ("train", "validation", "test"):
        spec = study["split"][key]
        mask = (panel.index >= pd.Timestamp(spec["start"])) & (panel.index <= pd.Timestamp(spec["end"]))
        locations = np.flatnonzero(mask)
        if len(locations) != int(spec["rows"]):
            raise ValueError(f"split row count changed: {key}")
        result[key] = locations
    return result


def equal_tail_weights(scores: np.ndarray, tail_names: int) -> np.ndarray:
    if len(scores) < tail_names * 2 or not np.isfinite(scores).all():
        return np.zeros(len(scores), dtype=float)
    order = np.argsort(scores, kind="stable")
    weights = np.zeros(len(scores), dtype=float)
    weights[order[:tail_names]] = 0.5 / tail_names
    weights[order[-tail_names:]] = -0.5 / tail_names
    return weights


def cross_sectional_targets(
    prices: np.ndarray,
    locations: np.ndarray,
    config: dict[str, Any],
) -> dict[int, np.ndarray]:
    formation = int(config["formationSessions"])
    interval = int(config["rebalanceEverySessions"])
    tails = int(config["tailNamesPerSide"])
    targets: dict[int, np.ndarray] = {}
    for offset, location in enumerate(locations):
        if offset % interval != 0 or location < formation:
            continue
        scores = prices[location] / prices[location - formation] - 1.0
        targets[int(location)] = equal_tail_weights(scores, tails)
    return targets


def residual_targets(
    stock_prices: np.ndarray,
    market_prices: np.ndarray,
    locations: np.ndarray,
    config: dict[str, Any],
) -> dict[int, np.ndarray]:
    lookback = int(config["betaLookbackSessions"])
    formation = int(config["residualFormationSessions"])
    interval = int(config["rebalanceEverySessions"])
    tails = int(config["tailNamesPerSide"])
    stock_returns = stock_prices[1:] / stock_prices[:-1] - 1.0
    market_returns = market_prices[1:] / market_prices[:-1] - 1.0
    targets: dict[int, np.ndarray] = {}
    for offset, location in enumerate(locations):
        if offset % interval != 0 or location < lookback:
            continue
        start = location - lookback
        y = stock_returns[start:location]
        x = market_returns[start:location]
        x_centered = x - x.mean()
        denominator = float(np.dot(x_centered, x_centered))
        if denominator <= EPSILON:
            continue
        y_means = y.mean(axis=0)
        betas = (x_centered[:, None] * (y - y_means)).sum(axis=0) / denominator
        alphas = y_means - betas * x.mean()
        residuals = y[-formation:] - alphas - x[-formation:, None] * betas
        scores = residuals.sum(axis=0)
        targets[int(location)] = equal_tail_weights(scores, tails)
    return targets


def select_distance_pairs(formation_prices: np.ndarray, pair_count: int) -> list[tuple[int, int, float, float, float, float]]:
    normalized = formation_prices / formation_prices[0]
    ranked: list[tuple[float, int, int]] = []
    for left, right in combinations(range(normalized.shape[1]), 2):
        spread = normalized[:, left] - normalized[:, right]
        ranked.append((float(np.dot(spread, spread)), left, right))
    selected: list[tuple[int, int, float, float, float, float]] = []
    used: set[int] = set()
    for _, left, right in sorted(ranked):
        if left in used or right in used:
            continue
        spread = normalized[:, left] - normalized[:, right]
        standard_deviation = float(spread.std(ddof=0))
        if standard_deviation <= EPSILON:
            continue
        selected.append(
            (
                left,
                right,
                float(formation_prices[0, left]),
                float(formation_prices[0, right]),
                float(spread.mean()),
                standard_deviation,
            )
        )
        used.update((left, right))
        if len(selected) == pair_count:
            break
    if len(selected) != pair_count:
        raise ValueError("not enough disjoint distance pairs")
    return selected


def distance_pair_targets(
    prices: np.ndarray,
    locations: np.ndarray,
    config: dict[str, Any],
) -> tuple[dict[int, np.ndarray], list[dict[str, Any]]]:
    formation = int(config["formationSessions"])
    trading = int(config["tradingSessions"])
    pair_count = int(config["pairCount"])
    entry_z = float(config["entryZ"])
    targets: dict[int, np.ndarray] = {}
    selections: list[dict[str, Any]] = []
    pairs: list[tuple[int, int, float, float, float, float]] = []
    states = np.zeros(pair_count, dtype=np.int8)
    previous_weights = np.zeros(prices.shape[1], dtype=float)
    sleeve_leg_weight = 0.5 / pair_count
    for offset, location in enumerate(locations):
        if offset % trading == 0:
            if location < formation:
                continue
            pairs = select_distance_pairs(prices[location - formation:location], pair_count)
            states[:] = 0
            selections.append({"location": int(location), "pairs": [(left, right) for left, right, *_ in pairs]})
        if not pairs:
            continue
        weights = np.zeros(prices.shape[1], dtype=float)
        for pair_index, (left, right, left_base, right_base, mean, std) in enumerate(pairs):
            spread = prices[location, left] / left_base - prices[location, right] / right_base
            z_score = (spread - mean) / std
            state = int(states[pair_index])
            if state == 0:
                if z_score >= entry_z:
                    state = -1
                elif z_score <= -entry_z:
                    state = 1
            elif state == -1 and spread <= mean:
                state = 0
            elif state == 1 and spread >= mean:
                state = 0
            states[pair_index] = state
            if state:
                weights[left] += state * sleeve_leg_weight
                weights[right] -= state * sleeve_leg_weight
        if not np.array_equal(weights, previous_weights):
            targets[int(location)] = weights.copy()
            previous_weights = weights.copy()
    return targets, selections


def floor_target_quantities(
    weights: np.ndarray,
    prices: np.ndarray,
    equity: float,
    leverage: int,
    increment: float,
) -> np.ndarray:
    target_notional = np.abs(weights) * max(equity, 0.0) * leverage
    units = np.floor(target_notional / prices / increment + 1e-10)
    return np.sign(weights) * units * increment


def simulate(
    *,
    strategy: str,
    split: str,
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    locations: np.ndarray,
    targets: dict[int, np.ndarray],
    leverage: int,
    cost_profile: dict[str, Any],
    portfolio: dict[str, Any],
) -> SimulationResult:
    initial_equity = float(portfolio["initialEquityUsd"])
    equity = initial_equity
    quantity_increment = float(portfolio["fractionalShareIncrement"])
    maintenance = float(portfolio["marginProxy"]["maintenanceMarginPctOfGross"]) / 100.0
    liquidation_rate = float(portfolio["marginProxy"]["liquidationPenaltyBpsOfGross"]) / 10_000.0
    transaction_rate = float(cost_profile["transactionPerSideBps"]) / 10_000.0
    financing_rate = float(cost_profile["annualLongFinancingPct"]) / 100.0 / 252.0
    borrow_rate = float(cost_profile["annualShortBorrowPct"]) / 100.0 / 252.0
    quantities = np.zeros(prices.shape[1], dtype=float)
    pending: np.ndarray | None = None
    peak = initial_equity
    max_drawdown = 0.0
    daily_pnl: list[float] = []
    gross_ratios: list[float] = []
    turnover = 0.0
    trade_orders = 0
    transaction_cost = 0.0
    financing_cost = 0.0
    borrow_cost = 0.0
    liquidation_penalty = 0.0
    price_pnl = 0.0
    liquidated = False
    ruined = False
    previous_prices: np.ndarray | None = None

    def apply_liquidation(current_prices: np.ndarray) -> None:
        nonlocal equity, quantities, turnover, trade_orders, transaction_cost
        nonlocal liquidation_penalty, liquidated, ruined
        gross = float(np.dot(np.abs(quantities), current_prices))
        close_cost = gross * transaction_rate
        penalty = gross * liquidation_rate
        changed = int(np.count_nonzero(np.abs(quantities) > EPSILON))
        equity -= close_cost + penalty
        turnover += gross
        trade_orders += changed
        transaction_cost += close_cost
        liquidation_penalty += penalty
        quantities[:] = 0.0
        liquidated = True
        ruined = equity <= 0.0

    for location in locations:
        current_prices = prices[location]
        start_equity = equity
        if previous_prices is not None:
            pnl = float(np.dot(quantities, current_prices - previous_prices))
            equity += pnl
            price_pnl += pnl
            long_notional = float(np.dot(np.clip(quantities, 0.0, None), current_prices))
            short_notional = float(np.dot(np.clip(-quantities, 0.0, None), current_prices))
            financing = max(long_notional - max(equity, 0.0), 0.0) * financing_rate
            borrow = short_notional * borrow_rate
            equity -= financing + borrow
            financing_cost += financing
            borrow_cost += borrow
        gross_before = float(np.dot(np.abs(quantities), current_prices))
        if quantities.any() and (equity <= 0.0 or equity <= gross_before * maintenance):
            apply_liquidation(current_prices)
        if not liquidated and pending is not None:
            target_quantities = floor_target_quantities(
                pending,
                current_prices,
                equity,
                leverage,
                quantity_increment,
            )
            changes = target_quantities - quantities
            changed = int(np.count_nonzero(np.abs(changes) > EPSILON))
            traded = float(np.dot(np.abs(changes), current_prices))
            cost = traded * transaction_rate
            equity -= cost
            turnover += traded
            trade_orders += changed
            transaction_cost += cost
            quantities = target_quantities
            pending = None
            gross_after = float(np.dot(np.abs(quantities), current_prices))
            if quantities.any() and (equity <= 0.0 or equity <= gross_after * maintenance):
                apply_liquidation(current_prices)
        if not liquidated and int(location) in targets:
            pending = targets[int(location)]
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
        gross = float(np.dot(np.abs(quantities), current_prices))
        gross_ratios.append(gross / equity if equity > 0 else math.inf)
        daily_pnl.append(equity - start_equity)
        previous_prices = current_prices
        if liquidated:
            remaining = len(locations) - len(daily_pnl)
            daily_pnl.extend([0.0] * remaining)
            gross_ratios.extend([0.0] * remaining)
            break

    if not liquidated and quantities.any():
        current_prices = prices[locations[-1]]
        gross = float(np.dot(np.abs(quantities), current_prices))
        changed = int(np.count_nonzero(np.abs(quantities) > EPSILON))
        cost = gross * transaction_rate
        equity -= cost
        turnover += gross
        trade_orders += changed
        transaction_cost += cost
        quantities[:] = 0.0
        daily_pnl[-1] -= cost
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
        ruined = equity <= 0.0

    returns = np.asarray(daily_pnl, dtype=float) / np.maximum(
        initial_equity + np.cumsum(np.asarray([0.0, *daily_pnl[:-1]], dtype=float)),
        EPSILON,
    )
    finite_returns = returns[np.isfinite(returns)]
    volatility = float(finite_returns.std(ddof=1) * math.sqrt(252.0)) if len(finite_returns) > 1 else 0.0
    sharpe = (
        float(finite_returns.mean() / finite_returns.std(ddof=1) * math.sqrt(252.0))
        if len(finite_returns) > 1 and finite_returns.std(ddof=1) > EPSILON
        else 0.0
    )
    positive = sum(value for value in daily_pnl if value > 0)
    negative = abs(sum(value for value in daily_pnl if value < 0))
    profit_factor = positive / negative if negative > EPSILON else (999.0 if positive > 0 else 0.0)
    total_return = equity / initial_equity - 1.0
    years = len(locations) / 252.0
    annualized = (equity / initial_equity) ** (1.0 / years) - 1.0 if equity > 0 and years > 0 else -1.0
    finite_gross = [value for value in gross_ratios if math.isfinite(value)]
    return SimulationResult(
        strategy=strategy,
        split=split,
        leverage=leverage,
        cost_profile=str(cost_profile["key"]),
        start=dates[locations[0]].date().isoformat(),
        end=dates[locations[-1]].date().isoformat(),
        sessions=len(locations),
        initial_equity=initial_equity,
        terminal_equity=equity,
        total_return_pct=total_return * 100.0,
        annualized_return_pct=annualized * 100.0,
        annualized_volatility_pct=volatility * 100.0,
        sharpe=sharpe,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown * 100.0,
        turnover_usd=turnover,
        trade_orders=trade_orders,
        average_realized_gross=float(np.mean(finite_gross)) if finite_gross else 0.0,
        maximum_realized_gross=max(finite_gross, default=0.0),
        transaction_cost_usd=transaction_cost,
        financing_cost_usd=financing_cost,
        short_borrow_cost_usd=borrow_cost,
        liquidation_penalty_usd=liquidation_penalty,
        price_pnl_usd=price_pnl,
        liquidated=liquidated,
        ruined=ruined,
    )


def funding_coverage(symbols: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        frame = load_funding(f"{symbol}-USDT-SWAP")
        rows.append(
            {
                "symbol": symbol,
                "rows": int(len(frame)),
                "start": frame["funding_time"].min().isoformat() if not frame.empty else None,
                "end": frame["funding_time"].max().isoformat() if not frame.empty else None,
            }
        )
    starts = [row["start"] for row in rows if row["start"]]
    return {
        "source": "data_pipeline.load_funding",
        "includedInHistoricalReturns": False,
        "reason": "coverage_starts_in_2026_and_cannot_be_backfilled_over_2016_2026_without_temporal_bias",
        "instrumentCount": len(rows),
        "instrumentsWithRows": sum(row["rows"] > 0 for row in rows),
        "earliestStart": min(starts, default=None),
        "rows": rows,
    }


def training_selection(results: list[SimulationResult], study: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        row
        for row in results
        if row.split == "train" and row.leverage == 2 and row.cost_profile == "base"
    ]
    eligibility = study["selection"]["eligibility"]
    eligible = [
        row
        for row in candidates
        if row.sessions >= int(eligibility["minimumCompletedSessions"])
        and row.trade_orders >= int(eligibility["minimumTradeOrders"])
        and row.total_return_pct > float(eligibility["minimumNetTotalReturnPct"])
        and row.profit_factor >= float(eligibility["minimumProfitFactor"])
        and row.max_drawdown_pct <= float(eligibility["maximumDrawdownPct"])
        and not row.liquidated
    ]
    selected = max(
        eligible,
        key=lambda row: (row.sharpe, row.annualized_return_pct, -row.max_drawdown_pct),
        default=None,
    )
    validation = next(
        (
            row
            for row in results
            if selected
            and row.strategy == selected.strategy
            and row.split == "validation"
            and row.leverage == 2
            and row.cost_profile == "base"
        ),
        None,
    )
    validation_passed = bool(
        validation
        and validation.total_return_pct > 0
        and validation.profit_factor >= 1.0
        and validation.max_drawdown_pct <= 35.0
        and not validation.liquidated
    )
    return {
        "eligibleTrainingCandidates": [row.strategy for row in eligible],
        "selectedPortfolio": selected.strategy if selected else None,
        "selectionMetrics": asdict(selected) if selected else None,
        "validationMetrics": asdict(validation) if validation else None,
        "validationPassed": validation_passed,
        "status": "validation_passed_research_only" if validation_passed else "failed_validation_research_only",
    }


def result_row(result: SimulationResult) -> dict[str, Any]:
    payload = asdict(result)
    for key, value in list(payload.items()):
        if isinstance(value, float):
            payload[key] = round(value, 10)
    return payload


def markdown_report(payload: dict[str, Any]) -> str:
    study = payload["study"]
    selection = payload["selection"]
    rows = payload["results"]
    lines = [
        "# US equity mean-reversion portfolios",
        "",
        f"Registry: `{payload['registryId']}`. Model: `{payload['modelId']}`. Generated: `{payload['generatedAt']}`.",
        "",
        "This is a development-only historical test on an inspected, current-survivor universe. It is not new validation and cannot authorize paper or live trading.",
        "",
        "## Frozen design",
        "",
        f"- Universe: {len(study['universe']['symbols'])} current OKX-mapped US equities with complete 2016-08-08 through 2026-08-07 adjusted-close history.",
        f"- Capital and sizing: ${study['portfolio']['initialEquityUsd']:.0f}, {study['portfolio']['fractionalShareIncrement']:.2f}-share increments, leverage 2x through 10x.",
        "- Splits: train 2017-08-08 to 2022-02-02; validation 2022-02-03 to 2024-05-03; test 2024-05-06 to 2026-08-07.",
        "- Costs: gross/no carry, base 10 bps per side + 5% long financing + 1% short borrow, stress 20 bps + 8% + 3%.",
        "- Margin proxy: daily-close cross-margin liquidation at equity <= 5% of gross, plus 50 bps of gross penalty.",
        "- OKX funding is excluded: data-lake coverage begins only in 2026 and cannot be backfilled over this history without temporal bias.",
        "",
        "## Training selection",
        "",
        f"- Eligible training candidates: {', '.join(selection['eligibleTrainingCandidates']) or 'none'}.",
        f"- Selected portfolio: `{selection['selectedPortfolio'] or 'none'}` using training 2x base-cost results only.",
        f"- Validation status: `{selection['status']}`.",
        "",
        "## Base-cost results",
        "",
        "| Strategy | Split | Lev | Terminal $ | Return | Ann. | Sharpe | PF | Max DD | Avg gross | Turnover $ | Orders | Liq |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        if row["cost_profile"] != "base":
            continue
        lines.append(
            f"| {row['strategy']} | {row['split']} | {row['leverage']}x | {row['terminal_equity']:.2f} | "
            f"{row['total_return_pct']:.2f}% | {row['annualized_return_pct']:.2f}% | {row['sharpe']:.2f} | "
            f"{row['profit_factor']:.2f} | {row['max_drawdown_pct']:.2f}% | {row['average_realized_gross']:.2f}x | "
            f"{row['turnover_usd']:.0f} | {row['trade_orders']} | {'yes' if row['liquidated'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Cost comparison at 2x",
            "",
            "| Strategy | Split | Gross | Base | Stress | Base costs $ | Stress costs $ |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    indexed = {(row["strategy"], row["split"], row["leverage"], row["cost_profile"]): row for row in rows}
    for strategy in [row["key"] for row in study["portfolios"]]:
        for split in ("train", "validation", "test"):
            gross = indexed[(strategy, split, 2, "gross")]
            base = indexed[(strategy, split, 2, "base")]
            stress = indexed[(strategy, split, 2, "stress")]
            base_cost = base["transaction_cost_usd"] + base["financing_cost_usd"] + base["short_borrow_cost_usd"]
            stress_cost = stress["transaction_cost_usd"] + stress["financing_cost_usd"] + stress["short_borrow_cost_usd"]
            lines.append(
                f"| {strategy} | {split} | {gross['total_return_pct']:.2f}% | {base['total_return_pct']:.2f}% | "
                f"{stress['total_return_pct']:.2f}% | {base_cost:.2f} | {stress_cost:.2f} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- The universe is selected using current contract availability and complete surviving price histories; delisted names and later listings are absent.",
            "- Adjusted underlying closes do not reproduce OKX contract basis, intraday path, spreads, depth, funding, margin tiers, or liquidation marks.",
            "- Every portfolio and leverage row is reported. Validation/test results must not be used to alter thresholds, pairs, symbols, or choose a test-only winner.",
            "- In liquidated paths, a higher-cost scenario can retain more terminal cash because it breaches the daily-close margin proxy earlier and stops taking risk. Such non-monotonic terminal values are liquidation timing artifacts, not evidence that higher costs help.",
            "- A positive row remains research-only. New forward data and explicit approval are required before paper or live use.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(registry_path: Path, output_dir: Path) -> dict[str, Any]:
    registry = read_json(registry_path)
    validate_registry(registry)
    study = registry["study"]
    panel = load_price_panel(registry)
    stock_symbols = study["universe"]["symbols"]
    stock_prices = panel[stock_symbols].to_numpy(dtype=float)
    market_prices = panel[study["universe"]["marketProxy"]].to_numpy(dtype=float)
    locations_by_split = split_locations(panel, study)
    configs = {row["key"]: row for row in study["portfolios"]}
    all_results: list[SimulationResult] = []
    pair_selections: dict[str, list[dict[str, Any]]] = {}
    for split, locations in locations_by_split.items():
        targets_by_strategy: dict[str, dict[int, np.ndarray]] = {
            "cross_sectional_5d_reversal": cross_sectional_targets(
                stock_prices, locations, configs["cross_sectional_5d_reversal"]
            ),
            "market_residual_5d_reversal": residual_targets(
                stock_prices, market_prices, locations, configs["market_residual_5d_reversal"]
            ),
        }
        pair_targets, selections = distance_pair_targets(
            stock_prices, locations, configs["distance_pairs_252_126"]
        )
        targets_by_strategy["distance_pairs_252_126"] = pair_targets
        pair_selections[split] = [
            {
                "date": panel.index[row["location"]].date().isoformat(),
                "pairs": [[stock_symbols[left], stock_symbols[right]] for left, right in row["pairs"]],
            }
            for row in selections
        ]
        for strategy, targets in targets_by_strategy.items():
            for leverage in study["portfolio"]["grossLeverageScenarios"]:
                for cost_profile in study["costProfiles"]:
                    all_results.append(
                        simulate(
                            strategy=strategy,
                            split=split,
                            prices=stock_prices,
                            dates=panel.index,
                            locations=locations,
                            targets=targets,
                            leverage=int(leverage),
                            cost_profile=cost_profile,
                            portfolio=study["portfolio"],
                        )
                    )
    split_order = {"train": 0, "validation": 1, "test": 2}
    cost_order = {"gross": 0, "base": 1, "stress": 2}
    all_results.sort(
        key=lambda row: (
            row.strategy,
            split_order[row.split],
            row.leverage,
            cost_order[row.cost_profile],
        )
    )
    selection = training_selection(all_results, study)
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registryId": registry["registryId"],
        "modelId": study["modelId"],
        "mode": "development_only_historical_mean_reversion_research",
        "paperOrLiveAuthorized": False,
        "study": study,
        "fundingCoverage": funding_coverage(stock_symbols),
        "pairSelections": pair_selections,
        "selection": selection,
        "results": [result_row(row) for row in all_results],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "scenario_rows.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(payload["results"][0]))
        writer.writeheader()
        writer.writerows(payload["results"])
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Frozen development-only US-equity mean-reversion research")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_ROOT / "mr-2016-2026-v1"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run(Path(args.registry), Path(args.output_dir))
    print(
        json.dumps(
            {
                "registryId": payload["registryId"],
                "modelId": payload["modelId"],
                "scenarios": len(payload["results"]),
                "selection": payload["selection"],
                "outputDir": args.output_dir,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
