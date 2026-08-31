"""Read-only discrete-lot research for a 100 USDT QQQ contract portfolio.

The locked point-in-time factor signals are not retrained or selected on OKX
contract returns.  At each completed month end, this module converts the
continuous active weights into actual OKX swap lot sizes subject to a small
account's gross, dollar, beta, industry, and tracking-error constraints.  It
then tests continuous holding with public 5-minute candles and realized public
funding rates.  No private endpoint, account state, order, or service path is
used.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from qqq_active_enhancement_research import (
    OKX_INSTRUMENTS_URL,
    OKX_TICKERS_URL,
    PUBLIC_HEADERS,
    read_json_url,
)
from qqq_intraday_flat_research import (
    BASE_FEE_BPS_PER_SIDE,
    BASE_SLIPPAGE_BPS_PER_SIDE,
    STRESS_MULTIPLIER,
    FundingPoint,
    SessionExecution,
    chronological_splits,
    contract_cache_path,
    executable_sessions,
    load_contract_candles,
    load_funding_history,
    load_weight_history,
    shared_sessions,
    weights_strictly_before,
)


PROJECT_ROOT = Path(__file__).resolve().parent
LOCK_ROOT = PROJECT_ROOT / "reports" / "qqq_active_enhancement" / "qqq-pit-20260808-v5"
LOCKED_MODEL_PATH = LOCK_ROOT / "locked_model.json"
WEIGHTS_PATH = LOCK_ROOT / "monthly_current_liquid_weights.csv"
UNIVERSE_PATH = LOCK_ROOT / "universe.csv"
PRICE_ROOT = PROJECT_ROOT / "data" / "qqq_active_enhancement" / "prices"
CONTRACT_ROOT = PROJECT_ROOT / "data" / "backtest"
FUNDING_ROOT = PROJECT_ROOT / "data" / "qqq_intraday_flat"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "qqq_small_account_contract"

INITIAL_EQUITY = 100.0
GROSS_CAPS = (1.2, 1.5)
ACTIVE_GROSS_LIMIT = 0.20
SINGLE_STOCK_LIMIT = 0.015
DOLLAR_RESIDUAL_LIMIT = 0.02
BETA_RESIDUAL_LIMIT = 0.01
INDUSTRY_RESIDUAL_LIMIT = 0.02
TRACKING_ERROR_LIMIT = 0.03
BETA_WINDOW_DAYS = 252
COVARIANCE_DAYS = 252
MIN_REGRESSION_DAYS = 126


@dataclass(frozen=True, slots=True)
class ContractRule:
    symbol: str
    contract: str
    ct_val: float
    lot_sz: float
    min_sz: float
    last: float
    max_leverage: float
    captured_at: str

    def lot_notional(self, price: float) -> float:
        return self.lot_sz * self.ct_val * price

    def min_notional(self, price: float) -> float:
        return self.min_sz * self.ct_val * price


@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    symbols: tuple[str, ...]
    beta: dict[str, float]
    covariance: np.ndarray


@dataclass(frozen=True, slots=True)
class DiscreteBook:
    feasible: bool
    contracts: dict[str, float]
    notionals: dict[str, float]
    active_gross: float
    active_net: float
    beta_residual: float
    industry_residuals: dict[str, float]
    ex_ante_tracking_error: float
    target_deviation_tracking_error: float
    selected_positions: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only 100 USDT discrete-lot QQQ contract research."
    )
    parser.add_argument("--locked-model", default=str(LOCKED_MODEL_PATH))
    parser.add_argument("--weights", default=str(WEIGHTS_PATH))
    parser.add_argument("--universe", default=str(UNIVERSE_PATH))
    parser.add_argument("--price-root", default=str(PRICE_ROOT))
    parser.add_argument("--contract-root", default=str(CONTRACT_ROOT))
    parser.add_argument("--funding-root", default=str(FUNDING_ROOT))
    parser.add_argument("--initial-equity", type=float, default=INITIAL_EQUITY)
    parser.add_argument("--pages", type=int, default=60)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def resolve_output_dir(value: str) -> Path:
    if value:
        return Path(value)
    stamp = datetime.now(timezone.utc).strftime("small-100-%Y%m%dT%H%M%SZ")
    return OUTPUT_ROOT / stamp


def iso_millis(value: Any) -> str:
    try:
        timestamp = int(str(value or "0"))
    except ValueError:
        return ""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp / 1000.0, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def contract_rules_from_payloads(
    instruments_payload: dict[str, Any],
    tickers_payload: dict[str, Any],
    symbols: Sequence[str],
) -> dict[str, ContractRule]:
    wanted = {f"{symbol}-USDT-SWAP": symbol for symbol in symbols}
    instruments = {
        str(row.get("instId") or ""): row
        for row in instruments_payload.get("data", [])
        if str(row.get("instId") or "") in wanted
    }
    tickers = {
        str(row.get("instId") or ""): row
        for row in tickers_payload.get("data", [])
        if str(row.get("instId") or "") in wanted
    }
    result: dict[str, ContractRule] = {}
    for contract, symbol in wanted.items():
        instrument = instruments.get(contract)
        ticker = tickers.get(contract)
        if not instrument or not ticker:
            raise ValueError(f"Missing public OKX rule or ticker for {contract}")
        if instrument.get("state") != "live":
            raise ValueError(f"Contract is not live: {contract}")
        ct_val = float(instrument.get("ctVal") or 0.0)
        lot_sz = float(instrument.get("lotSz") or 0.0)
        min_sz = float(instrument.get("minSz") or 0.0)
        last = float(ticker.get("last") or 0.0)
        if min(ct_val, lot_sz, min_sz, last) <= 0:
            raise ValueError(f"Invalid public OKX sizing fields for {contract}")
        result[symbol] = ContractRule(
            symbol=symbol,
            contract=contract,
            ct_val=ct_val,
            lot_sz=lot_sz,
            min_sz=min_sz,
            last=last,
            max_leverage=float(instrument.get("lever") or 0.0),
            captured_at=iso_millis(ticker.get("ts")),
        )
    return result


def fetch_contract_rules(symbols: Sequence[str]) -> dict[str, ContractRule]:
    instruments = read_json_url(OKX_INSTRUMENTS_URL, headers=PUBLIC_HEADERS)
    tickers = read_json_url(OKX_TICKERS_URL, headers=PUBLIC_HEADERS)
    return contract_rules_from_payloads(instruments, tickers, symbols)


def load_price_series(root: Path, symbols: Sequence[str]) -> dict[str, pd.Series]:
    result: dict[str, pd.Series] = {}
    for symbol in symbols:
        path = root / f"{symbol}_1d_10y.csv"
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        result[symbol] = frame["adj_close"].astype(float).rename(symbol)
    return result


def load_industries(path: Path, symbols: Sequence[str]) -> dict[str, str]:
    wanted = set(symbols)
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = {
            row["symbol"]: row["industry"]
            for row in csv.DictReader(handle)
            if row.get("symbol") in wanted
        }
    missing = wanted - set(rows)
    if missing:
        raise ValueError(f"Missing industries for: {sorted(missing)}")
    return rows


def risk_snapshot_asof(
    signal_date: date,
    symbols: Sequence[str],
    prices: dict[str, pd.Series],
) -> RiskSnapshot:
    as_of = pd.Timestamp(signal_date)
    benchmark = prices["QQQ"].loc[:as_of].pct_change()
    betas: dict[str, float] = {}
    stock_returns: list[pd.Series] = []
    for symbol in symbols:
        returns = prices[symbol].loc[:as_of].pct_change().rename(symbol)
        aligned = pd.concat(
            [returns.rename("stock"), benchmark.rename("benchmark")], axis=1
        ).dropna()
        if len(aligned) < MIN_REGRESSION_DAYS:
            raise ValueError(f"Insufficient beta history for {symbol} at {signal_date}")
        aligned = aligned.iloc[-BETA_WINDOW_DAYS:]
        design = np.column_stack(
            [np.ones(len(aligned)), aligned["benchmark"].to_numpy(dtype=float)]
        )
        coefficients, *_ = np.linalg.lstsq(
            design, aligned["stock"].to_numpy(dtype=float), rcond=None
        )
        betas[symbol] = float(coefficients[1])
        stock_returns.append(returns)
    covariance_frame = pd.concat(stock_returns, axis=1).dropna().iloc[-COVARIANCE_DAYS:]
    if len(covariance_frame) < MIN_REGRESSION_DAYS:
        raise ValueError(f"Insufficient covariance history at {signal_date}")
    sample = covariance_frame.cov().to_numpy(dtype=float) * 252.0
    covariance = 0.75 * sample + 0.25 * np.diag(np.diag(sample))
    return RiskSnapshot(tuple(symbols), betas, covariance)


def position_options(
    rule: ContractRule,
    price: float,
    equity: float,
    *,
    single_stock_limit: float = SINGLE_STOCK_LIMIT,
) -> list[int]:
    unit = rule.lot_notional(price)
    minimum_lots = max(1, int(math.ceil(rule.min_sz / rule.lot_sz - 1e-12)))
    minimum_notional = minimum_lots * unit
    # A name may breach the original 1.5% cap only by the unavoidable amount
    # required for exactly one exchange-minimum order.
    cap = max(single_stock_limit * equity, minimum_notional)
    maximum_lots = int(math.floor(cap / unit + 1e-12))
    if maximum_lots < minimum_lots:
        return [0]
    return [0, *range(minimum_lots, maximum_lots + 1)]


def optimize_active_book(
    target_weights: dict[str, float],
    prices: dict[str, float],
    equity: float,
    rules: dict[str, ContractRule],
    risk: RiskSnapshot,
    industries: dict[str, str],
    *,
    active_gross_limit: float = ACTIVE_GROSS_LIMIT,
    single_stock_limit: float = SINGLE_STOCK_LIMIT,
    dollar_residual_limit: float = DOLLAR_RESIDUAL_LIMIT,
    beta_residual_limit: float = BETA_RESIDUAL_LIMIT,
    industry_residual_limit: float = INDUSTRY_RESIDUAL_LIMIT,
    tracking_error_limit: float = TRACKING_ERROR_LIMIT,
) -> DiscreteBook:
    if equity <= 0:
        raise ValueError("equity must be positive")
    symbols = list(risk.symbols)
    choices: list[list[int]] = []
    for symbol in symbols:
        if abs(target_weights.get(symbol, 0.0)) <= 1e-15:
            choices.append([0])
        else:
            choices.append(
                position_options(
                    rules[symbol],
                    prices[symbol],
                    equity,
                    single_stock_limit=single_stock_limit,
                )
            )
    target = np.array([target_weights.get(symbol, 0.0) for symbol in symbols], dtype=float)
    industry_names = sorted(set(industries.values()))
    candidates: list[tuple[tuple[float, ...], DiscreteBook]] = []
    for lot_counts in itertools.product(*choices):
        contracts: dict[str, float] = {}
        notionals: dict[str, float] = {}
        for symbol, count in zip(symbols, lot_counts):
            direction = 1.0 if target_weights.get(symbol, 0.0) > 0 else -1.0
            size = direction * count * rules[symbol].lot_sz
            contracts[symbol] = size
            notionals[symbol] = size * rules[symbol].ct_val * prices[symbol]
        longs = sum(max(value, 0.0) for value in notionals.values())
        shorts = sum(max(-value, 0.0) for value in notionals.values())
        gross = longs + shorts
        if longs <= 0 or shorts <= 0 or gross > active_gross_limit * equity + 1e-9:
            continue
        net = sum(notionals.values())
        beta_residual = sum(
            notionals[symbol] * risk.beta[symbol] for symbol in symbols
        )
        industry_residuals = {
            industry: sum(
                notionals[symbol]
                for symbol in symbols
                if industries[symbol] == industry
            )
            for industry in industry_names
        }
        if abs(net) > dollar_residual_limit * equity + 1e-9:
            continue
        if abs(beta_residual) > beta_residual_limit * equity + 1e-9:
            continue
        if max(abs(value) for value in industry_residuals.values()) > industry_residual_limit * equity + 1e-9:
            continue
        weights = np.array([notionals[symbol] / equity for symbol in symbols], dtype=float)
        tracking_error = float(
            math.sqrt(max(weights @ risk.covariance @ weights, 0.0))
        )
        if tracking_error > tracking_error_limit + 1e-12:
            continue
        difference = weights - target
        deviation = float(
            math.sqrt(max(difference @ risk.covariance @ difference, 0.0))
        )
        selected = sum(abs(value) > 1e-15 for value in contracts.values())
        book = DiscreteBook(
            feasible=True,
            contracts=contracts,
            notionals=notionals,
            active_gross=gross,
            active_net=net,
            beta_residual=beta_residual,
            industry_residuals=industry_residuals,
            ex_ante_tracking_error=tracking_error,
            target_deviation_tracking_error=deviation,
            selected_positions=selected,
        )
        # The target-risk deviation is the pre-registered primary objective.
        # The remaining terms are deterministic tie breakers toward neutrality.
        objective = (
            deviation,
            abs(beta_residual) / equity,
            abs(net) / equity,
            max(abs(value) for value in industry_residuals.values()) / equity,
            gross / equity,
        )
        candidates.append((objective, book))
    if not candidates:
        return DiscreteBook(
            feasible=False,
            contracts={symbol: 0.0 for symbol in symbols},
            notionals={symbol: 0.0 for symbol in symbols},
            active_gross=0.0,
            active_net=0.0,
            beta_residual=0.0,
            industry_residuals={industry: 0.0 for industry in industry_names},
            ex_ante_tracking_error=0.0,
            target_deviation_tracking_error=0.0,
            selected_positions=0,
        )
    return min(candidates, key=lambda item: item[0])[1]


def all_minimum_active_book(
    target_weights: dict[str, float],
    prices: dict[str, float],
    equity: float,
    rules: dict[str, ContractRule],
    risk: RiskSnapshot,
    industries: dict[str, str],
) -> DiscreteBook:
    """Keep every non-zero locked direction at exactly one OKX minimum size."""
    if equity <= 0:
        raise ValueError("equity must be positive")
    symbols = list(risk.symbols)
    contracts: dict[str, float] = {}
    notionals: dict[str, float] = {}
    for symbol in symbols:
        target = target_weights.get(symbol, 0.0)
        if abs(target) <= 1e-15:
            contracts[symbol] = 0.0
            notionals[symbol] = 0.0
            continue
        direction = 1.0 if target > 0 else -1.0
        contracts[symbol] = direction * rules[symbol].min_sz
        notionals[symbol] = (
            contracts[symbol] * rules[symbol].ct_val * prices[symbol]
        )
    weights = np.array([notionals[symbol] / equity for symbol in symbols], dtype=float)
    target = np.array([target_weights.get(symbol, 0.0) for symbol in symbols], dtype=float)
    industries_names = sorted(set(industries.values()))
    industry_residuals = {
        industry: sum(
            notionals[symbol]
            for symbol in symbols
            if industries[symbol] == industry
        )
        for industry in industries_names
    }
    difference = weights - target
    return DiscreteBook(
        feasible=any(value > 0 for value in notionals.values())
        and any(value < 0 for value in notionals.values()),
        contracts=contracts,
        notionals=notionals,
        active_gross=sum(abs(value) for value in notionals.values()),
        active_net=sum(notionals.values()),
        beta_residual=sum(
            notionals[symbol] * risk.beta[symbol] for symbol in symbols
        ),
        industry_residuals=industry_residuals,
        ex_ante_tracking_error=float(
            math.sqrt(max(weights @ risk.covariance @ weights, 0.0))
        ),
        target_deviation_tracking_error=float(
            math.sqrt(max(difference @ risk.covariance @ difference, 0.0))
        ),
        selected_positions=sum(abs(value) > 1e-15 for value in contracts.values()),
    )


def core_contract_size(
    rule: ContractRule,
    price: float,
    equity: float,
    active_gross: float,
    gross_cap: float,
) -> float:
    available = max(0.0, gross_cap * equity - active_gross)
    lot_notional = rule.lot_notional(price)
    maximum_lots = int(math.floor(available / lot_notional + 1e-12))
    minimum_lots = max(1, int(math.ceil(rule.min_sz / rule.lot_sz - 1e-12)))
    if maximum_lots < minimum_lots:
        return 0.0
    return maximum_lots * rule.lot_sz


def funding_cash_pnl(
    points: Sequence[FundingPoint],
    start_ts: int,
    end_ts: int,
    contracts: float,
    contract_value: float,
    reference_price: float,
) -> float:
    rate = sum(point.rate for point in points if start_ts <= point.ts < end_ts)
    return -contracts * contract_value * reference_price * rate


def price_pnl(
    contracts: float,
    contract_value: float,
    start_price: float,
    end_price: float,
) -> float:
    return contracts * contract_value * (end_price - start_price)


def segmented_metrics(frame: pd.DataFrame, splits: dict[str, list[str]]) -> dict[str, Any]:
    def metrics(rows: pd.DataFrame) -> dict[str, float]:
        if rows.empty:
            return {}
        returns = rows["portfolioReturn"]
        active = rows["activeReturn"]
        equity_curve = (1.0 + returns).cumprod()
        drawdown = equity_curve / equity_curve.cummax() - 1.0
        total = float(equity_curve.iloc[-1] - 1.0)
        return {
            "sessions": len(rows),
            "cumulativePct": total * 100.0,
            "activeCumulativePct": float((1.0 + active).prod() - 1.0) * 100.0,
            "annualizedPct": ((1.0 + total) ** (252.0 / len(rows)) - 1.0) * 100.0
            if total > -1
            else -100.0,
            "volatilityPct": float(returns.std(ddof=1) * math.sqrt(252.0) * 100.0)
            if len(rows) > 1
            else 0.0,
            "maxDrawdownPct": float(-drawdown.min() * 100.0),
            "fundingPct": float((rows["activeFunding"] + rows["coreFunding"]).sum() * 100.0),
            "tradingCostPct": float((rows["activeCost"] + rows["coreCost"]).sum() * 100.0),
            "averageGrossPct": float(rows["grossExposure"].mean() * 100.0),
            "maximumGrossPct": float(rows["grossExposure"].max() * 100.0),
            "averageNetPct": float(rows["netExposure"].mean() * 100.0),
        }

    return {
        name: metrics(frame.loc[dates])
        for name, dates in splits.items()
        if dates
    }


def backtest_book(
    session_dates: Sequence[str],
    stock_symbols: Sequence[str],
    sessions: dict[str, dict[str, SessionExecution]],
    funding: dict[str, list[FundingPoint]],
    weight_history: dict[date, dict[str, float]],
    risks: dict[date, RiskSnapshot],
    industries: dict[str, str],
    rules: dict[str, ContractRule],
    *,
    initial_equity: float,
    gross_cap: float,
    cost_bps_per_side: float,
    active_mode: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, dict[str, float]]]:
    if active_mode not in {"optimized", "all_minimum", "none"}:
        raise ValueError(f"Unknown active mode: {active_mode}")
    symbols = ["QQQ", *stock_symbols]
    positions = {symbol: 0.0 for symbol in symbols}
    previous_execution: dict[str, SessionExecution] | None = None
    current_signal: date | None = None
    equity = initial_equity
    daily_rows: list[dict[str, Any]] = []
    rebalance_rows: list[dict[str, Any]] = []
    attribution = {
        symbol: {"pricePnl": 0.0, "fundingPnl": 0.0, "tradingCost": 0.0}
        for symbol in symbols
    }
    cost_rate = cost_bps_per_side / 10_000.0
    for session_index, session in enumerate(session_dates):
        execution = {symbol: sessions[symbol][session] for symbol in symbols}
        start_equity = equity
        active_pnl = 0.0
        core_pnl = 0.0
        active_funding = 0.0
        core_funding = 0.0
        active_cost = 0.0
        core_cost = 0.0
        if previous_execution is not None:
            for symbol in symbols:
                rule = rules[symbol]
                pnl = price_pnl(
                    positions[symbol],
                    rule.ct_val,
                    previous_execution[symbol].exit_price,
                    execution[symbol].entry_price,
                )
                funding_pnl = funding_cash_pnl(
                    funding[symbol],
                    previous_execution[symbol].exit_ts,
                    execution[symbol].entry_ts,
                    positions[symbol],
                    rule.ct_val,
                    previous_execution[symbol].exit_price,
                )
                if symbol == "QQQ":
                    core_pnl += pnl
                    core_funding += funding_pnl
                else:
                    active_pnl += pnl
                    active_funding += funding_pnl
                attribution[symbol]["pricePnl"] += pnl
                attribution[symbol]["fundingPnl"] += funding_pnl
            equity += active_pnl + core_pnl + active_funding + core_funding

        selected = weights_strictly_before(session, weight_history)
        if selected is None:
            previous_execution = execution
            continue
        signal_date, target_weights = selected
        if signal_date != current_signal:
            prices = {symbol: execution[symbol].entry_price for symbol in stock_symbols}
            if active_mode == "optimized":
                book = optimize_active_book(
                    target_weights,
                    prices,
                    equity,
                    rules,
                    risks[signal_date],
                    industries,
                )
                if not book.feasible:
                    raise RuntimeError(f"No feasible discrete active book at {signal_date}")
                new_positions = dict(book.contracts)
            elif active_mode == "all_minimum":
                book = all_minimum_active_book(
                    target_weights,
                    prices,
                    equity,
                    rules,
                    risks[signal_date],
                    industries,
                )
                if not book.feasible:
                    raise RuntimeError(f"No feasible all-minimum active book at {signal_date}")
                new_positions = dict(book.contracts)
            else:
                book = DiscreteBook(
                    feasible=True,
                    contracts={symbol: 0.0 for symbol in stock_symbols},
                    notionals={symbol: 0.0 for symbol in stock_symbols},
                    active_gross=0.0,
                    active_net=0.0,
                    beta_residual=0.0,
                    industry_residuals={name: 0.0 for name in sorted(set(industries.values()))},
                    ex_ante_tracking_error=0.0,
                    target_deviation_tracking_error=0.0,
                    selected_positions=0,
                )
                new_positions = {symbol: 0.0 for symbol in stock_symbols}
            new_positions["QQQ"] = core_contract_size(
                rules["QQQ"],
                execution["QQQ"].entry_price,
                equity,
                book.active_gross,
                gross_cap,
            )
            for symbol in symbols:
                turnover = (
                    abs(new_positions[symbol] - positions[symbol])
                    * rules[symbol].ct_val
                    * execution[symbol].entry_price
                )
                cost = turnover * cost_rate
                if symbol == "QQQ":
                    core_cost += cost
                else:
                    active_cost += cost
                attribution[symbol]["tradingCost"] += cost
            equity -= active_cost + core_cost
            positions = new_positions
            current_signal = signal_date
            gross = sum(
                abs(positions[symbol]) * rules[symbol].ct_val * execution[symbol].entry_price
                for symbol in symbols
            )
            net = sum(
                positions[symbol] * rules[symbol].ct_val * execution[symbol].entry_price
                for symbol in symbols
            )
            for symbol in symbols:
                if abs(positions[symbol]) <= 1e-15:
                    continue
                rebalance_rows.append(
                    {
                        "session": session,
                        "signalDate": signal_date.isoformat(),
                        "symbol": symbol,
                        "contracts": positions[symbol],
                        "price": execution[symbol].entry_price,
                        "notional": positions[symbol]
                        * rules[symbol].ct_val
                        * execution[symbol].entry_price,
                        "equityBeforeTrade": equity + active_cost + core_cost,
                        "grossAfterTrade": gross,
                        "netAfterTrade": net,
                        "activeGross": book.active_gross,
                        "activeNet": book.active_net,
                        "betaResidual": book.beta_residual,
                        "exAnteTrackingError": book.ex_ante_tracking_error,
                        "targetDeviationTrackingError": book.target_deviation_tracking_error,
                    }
                )

        # Fixed contract notionals can exceed the account-level gross cap after
        # a drawdown.  Between monthly signals, this guard only reduces QQQ at
        # the session entry; it never adds leverage merely because gross fell.
        active_gross_at_entry = sum(
            abs(positions[symbol])
            * rules[symbol].ct_val
            * execution[symbol].entry_price
            for symbol in stock_symbols
        )
        maximum_core = core_contract_size(
            rules["QQQ"],
            execution["QQQ"].entry_price,
            equity,
            active_gross_at_entry,
            gross_cap,
        )
        if positions["QQQ"] > maximum_core + 1e-15:
            reduction_notional = (
                (positions["QQQ"] - maximum_core)
                * rules["QQQ"].ct_val
                * execution["QQQ"].entry_price
            )
            guard_cost = reduction_notional * cost_rate
            core_cost += guard_cost
            attribution["QQQ"]["tradingCost"] += guard_cost
            equity -= guard_cost
            positions["QQQ"] = maximum_core

        intraday_active_pnl = 0.0
        intraday_core_pnl = 0.0
        intraday_active_funding = 0.0
        intraday_core_funding = 0.0
        for symbol in symbols:
            rule = rules[symbol]
            pnl = price_pnl(
                positions[symbol],
                rule.ct_val,
                execution[symbol].entry_price,
                execution[symbol].exit_price,
            )
            funding_pnl = funding_cash_pnl(
                funding[symbol],
                execution[symbol].entry_ts,
                execution[symbol].exit_ts,
                positions[symbol],
                rule.ct_val,
                execution[symbol].entry_price,
            )
            if symbol == "QQQ":
                intraday_core_pnl += pnl
                intraday_core_funding += funding_pnl
            else:
                intraday_active_pnl += pnl
                intraday_active_funding += funding_pnl
            attribution[symbol]["pricePnl"] += pnl
            attribution[symbol]["fundingPnl"] += funding_pnl
        active_pnl += intraday_active_pnl
        core_pnl += intraday_core_pnl
        active_funding += intraday_active_funding
        core_funding += intraday_core_funding
        equity += (
            intraday_active_pnl
            + intraday_core_pnl
            + intraday_active_funding
            + intraday_core_funding
        )

        marked_equity = equity
        gross_exposure = sum(
            abs(positions[symbol])
            * rules[symbol].ct_val
            * execution[symbol].exit_price
            for symbol in symbols
        ) / max(marked_equity, 1e-12)
        net_exposure = sum(
            positions[symbol]
            * rules[symbol].ct_val
            * execution[symbol].exit_price
            for symbol in symbols
        ) / max(marked_equity, 1e-12)

        if session_index == len(session_dates) - 1:
            closing_active_cost = 0.0
            closing_core_cost = 0.0
            for symbol in symbols:
                close_notional = (
                    abs(positions[symbol])
                    * rules[symbol].ct_val
                    * execution[symbol].exit_price
                )
                cost = close_notional * cost_rate
                if symbol == "QQQ":
                    closing_core_cost += cost
                else:
                    closing_active_cost += cost
                attribution[symbol]["tradingCost"] += cost
            active_cost += closing_active_cost
            core_cost += closing_core_cost
            equity -= closing_active_cost + closing_core_cost
            positions = {symbol: 0.0 for symbol in symbols}

        active_return = (active_pnl + active_funding - active_cost) / start_equity
        core_return = (core_pnl + core_funding - core_cost) / start_equity
        daily_rows.append(
            {
                "session": session,
                "signalDate": signal_date.isoformat(),
                "startEquity": start_equity,
                "endEquity": equity,
                "activePnl": active_pnl / start_equity,
                "corePnl": core_pnl / start_equity,
                "activeFunding": active_funding / start_equity,
                "coreFunding": core_funding / start_equity,
                "activeCost": active_cost / start_equity,
                "coreCost": core_cost / start_equity,
                "activeReturn": active_return,
                "coreReturn": core_return,
                "portfolioReturn": active_return + core_return,
                "grossExposure": gross_exposure,
                "netExposure": net_exposure,
            }
        )
        previous_execution = execution
    for values in attribution.values():
        values["netPnl"] = (
            values["pricePnl"] + values["fundingPnl"] - values["tradingCost"]
        )
    return pd.DataFrame(daily_rows).set_index("session"), rebalance_rows, attribution


def markdown_report(payload: dict[str, Any]) -> str:
    def pct(value: Any) -> str:
        return f"{float(value):.3f}%"

    lines = [
        "# 100 USDT QQQ 纯合约离散优化",
        "",
        "> 只读研究。使用冻结的点时月频信号、OKX公开合约规格/5m K线/realized funding；不访问账户、不下单、不修改实盘配置。离散约束在查看本次组合收益前固定。",
        "",
        "## 固定约束",
        "",
        f"- 初始权益：{payload['config']['initialEquityUsdt']:.2f} USDT；连续持有并在月频信号变化时调仓。",
        "- `enhanced`：方向不得与冻结权重相反；主动gross≤20%，并保留美元/beta/行业/TE约束。",
        "- `allMin`：用户指定的第二种方案；每个非零旧方向固定一份OKX最小合约，不再强制主动gross、单股、美元、beta、行业或TE约束。",
        "- 两种执行都不使用这43天的合约收益挑股票、方向或参数。",
        "- 分别把总gross限制在1.2倍和1.5倍；QQQ核心使用剩余gross，因此杠杆主要放大QQQ beta，而不是主动alpha。",
        "- 月内若开盘时gross超过上限，只减少QQQ核心并计入换手成本；月内不会因gross低于上限主动补杠杆。",
        "- 基础成本每边5 bps手续费+5 bps滑点；压力成本翻倍。资金费按公开历史realized rate和实际合约方向计入。",
        "",
        "## 当前100 USDT两种离散簿",
        "",
        f"- 规格快照：{payload['current']['capturedAt']}；信号日期：{payload['current']['signalDate']}。",
        f"- 主动gross {pct(payload['current']['activeGrossPct'])}，主动净敞口 {pct(payload['current']['activeNetPct'])}，beta残差 {pct(payload['current']['betaResidualPct'])}，事前TE {pct(payload['current']['trackingErrorPct'])}。",
        "",
        "| 标的 | 方向 | 合约数量 | 最新价 | 名义金额/权益 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in payload["current"]["activePositions"]:
        lines.append(
            f"| {row['symbol']} | {row['side']} | {abs(row['contracts']):.4f} | "
            f"{row['price']:.2f} | {row['weightPct']:.3f}% |"
        )
    for item in payload["current"]["leverageVariants"]:
        lines.append(
            f"- gross上限 {item['grossCap']:.1f}：QQQ {item['qqqContracts']:.4f} 份，"
            f"QQQ名义 {item['qqqNotional']:.2f} USDT，实际总gross {item['actualGrossPct']:.2f}%。"
        )
    all_min = payload["currentAllMin"]
    lines.extend(
        [
            "",
            f"- `allMin` 主动gross {pct(all_min['activeGrossPct'])}，主动净敞口 {pct(all_min['activeNetPct'])}，beta残差 {pct(all_min['betaResidualPct'])}，事前TE {pct(all_min['trackingErrorPct'])}。",
            "",
            "| allMin标的 | 方向 | 合约数量 | 最新价 | 名义金额/权益 |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in all_min["activePositions"]:
        lines.append(
            f"| {row['symbol']} | {row['side']} | {abs(row['contracts']):.4f} | "
            f"{row['price']:.2f} | {row['weightPct']:.3f}% |"
        )
    for item in all_min["leverageVariants"]:
        lines.append(
            f"- allMin gross上限 {item['grossCap']:.1f}：QQQ {item['qqqContracts']:.4f} 份，"
            f"QQQ名义 {item['qqqNotional']:.2f} USDT，实际总gross {item['actualGrossPct']:.2f}%。"
        )
    lines.extend(
        [
            "",
            "## 43天合约回测",
            "",
            f"- 区间：{payload['period']['start']} 至 {payload['period']['end']}，共 {payload['period']['sessions']} 个共同完整RTH交易日。",
            "- 这是看过旧连续权重结果后提出的新离散执行模型；虽然优化没有使用收益，仍只能视为回顾性可执行性检查，最后11天不是新的独立测试集。",
            "",
            "| 成本 | gross上限 | 组合 | 全期累计 | 主动累计 | 波动 | 最大回撤 | 资金费 | 交易成本 | 平均/最高gross |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for variant in ("base", "stress"):
        for gross_key in ("1.2", "1.5"):
            for book_name in ("enhanced", "allMin", "qqqOnly"):
                item = payload["results"][variant][gross_key][book_name]["full"]
                lines.append(
                    f"| {variant} | {gross_key} | {book_name} | {pct(item['cumulativePct'])} | "
                    f"{pct(item['activeCumulativePct'])} | {pct(item['volatilityPct'])} | "
                    f"{pct(item['maxDrawdownPct'])} | {pct(item['fundingPct'])} | "
                    f"{pct(item['tradingCostPct'])} | {pct(item['averageGrossPct'])}/{pct(item['maximumGrossPct'])} |"
                )
    attribution_summary = payload["allMinAttributionSummary"]
    lines.extend(
        [
            "",
            "## allMin主动收益归因（基础成本，1.2倍）",
            "",
            f"- 主动现金净P&L {attribution_summary['activeNetPnlUsdt']:.3f} USDT；最大贡献来自 {attribution_summary['largestContributor']}，为 {attribution_summary['largestContributorNetPnlUsdt']:.3f} USDT。",
            f"- 去掉最大贡献标的后，其余主动腿合计 {attribution_summary['activeNetPnlWithoutLargestUsdt']:.3f} USDT。",
            "",
            "| 标的 | 价格P&L | 资金费P&L | 交易成本 | 净P&L |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["allMinAttributionBase1p2"]:
        lines.append(
            f"| {row['symbol']} | {row['pricePnl']:.3f} | {row['fundingPnl']:.3f} | "
            f"{row['tradingCost']:.3f} | {row['netPnl']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 月频离散持仓",
            "",
            "| 组合 | gross上限 | 信号日 | 调仓日 | 主动腿 | 主动gross | 主动净额 | beta残差 | 事前TE |",
            "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["rebalanceSummary"]:
        lines.append(
            f"| {row['strategy']} | {row['grossCap']:.1f} | {row['signalDate']} | {row['session']} | {row['positions']} | "
            f"{pct(row['activeGrossPct'])} | {pct(row['activeNetPct'])} | "
            f"{pct(row['betaResidualPct'])} | {pct(row['trackingErrorPct'])} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            f"- 状态：`{decision['status']}`。{decision['reason']}",
            f"- 是否授权仿真或实盘：`{decision['eligibleForPaperOrLive']}`。",
            "",
            "## 边界",
            "",
            "- 43天窗口很短，且合约多数上市不久；无法估计跨年度资金费、基差和尾部流动性。",
            "- 使用当前OKX lot/minSz规则回放整个43天，缺少交易所历史规则快照。",
            "- 5m K线无法恢复盘口深度、排队和精确成交；真实滑点可能更高。",
            "- `enhanced`只保留少数股票腿；`allMin`虽保留所有方向但权重严重变形；两者都已是新执行模型。",
            "- 本报告只产生研究文件，不加载.env、不访问账户、不下单。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    locked = json.loads(Path(args.locked_model).read_text(encoding="utf-8"))
    if locked.get("paperOrLiveAuthorized") is not False:
        raise RuntimeError("Locked model must remain unauthorized for paper/live trading")
    stock_symbols = list(locked["basis"]["symbols"])
    symbols = ["QQQ", *stock_symbols]
    rules = fetch_contract_rules(symbols)
    industries = load_industries(Path(args.universe), stock_symbols)
    prices = load_price_series(Path(args.price_root), symbols)
    weight_history = load_weight_history(Path(args.weights), stock_symbols)

    sessions: dict[str, dict[str, SessionExecution]] = {}
    funding: dict[str, list[FundingPoint]] = {}
    for symbol in symbols:
        contract = f"{symbol}-USDT-SWAP"
        candles = load_contract_candles(
            contract,
            Path(args.contract_root),
            pages=args.pages,
            fetch_missing=False,
            refresh=False,
        )
        sessions[symbol] = executable_sessions(candles)
        funding[symbol] = load_funding_history(
            contract, Path(args.funding_root), refresh=False
        )
    common = shared_sessions(sessions)
    if len(common) < 20:
        raise RuntimeError(f"Only {len(common)} common complete sessions")
    valid_signals = {
        weights_strictly_before(session, weight_history)[0]
        for session in common
        if weights_strictly_before(session, weight_history) is not None
    }
    risks = {
        signal_date: risk_snapshot_asof(signal_date, stock_symbols, prices)
        for signal_date in sorted(valid_signals)
    }
    splits = chronological_splits(common)
    cost_variants = {
        "base": BASE_FEE_BPS_PER_SIDE + BASE_SLIPPAGE_BPS_PER_SIDE,
        "stress": (BASE_FEE_BPS_PER_SIDE + BASE_SLIPPAGE_BPS_PER_SIDE)
        * STRESS_MULTIPLIER,
    }
    result_frames: dict[tuple[str, float, str], pd.DataFrame] = {}
    rebalance_payloads: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    attribution_payloads: dict[
        tuple[str, float, str], dict[str, dict[str, float]]
    ] = {}
    results: dict[str, Any] = {}
    for variant, cost_bps in cost_variants.items():
        results[variant] = {}
        for gross_cap in GROSS_CAPS:
            gross_key = f"{gross_cap:.1f}"
            results[variant][gross_key] = {}
            for book_name, active_mode in (
                ("enhanced", "optimized"),
                ("allMin", "all_minimum"),
                ("qqqOnly", "none"),
            ):
                frame, rebalances, attribution = backtest_book(
                    common,
                    stock_symbols,
                    sessions,
                    funding,
                    weight_history,
                    risks,
                    industries,
                    rules,
                    initial_equity=args.initial_equity,
                    gross_cap=gross_cap,
                    cost_bps_per_side=cost_bps,
                    active_mode=active_mode,
                )
                result_frames[(variant, gross_cap, book_name)] = frame
                rebalance_payloads[(variant, gross_cap, book_name)] = rebalances
                attribution_payloads[(variant, gross_cap, book_name)] = attribution
                results[variant][gross_key][book_name] = segmented_metrics(frame, splits)

    latest_signal = max(weight_history)
    latest_target = weight_history[latest_signal]
    current_prices = {symbol: rules[symbol].last for symbol in stock_symbols}
    current_book = optimize_active_book(
        latest_target,
        current_prices,
        args.initial_equity,
        rules,
        risks[latest_signal],
        industries,
    )
    if not current_book.feasible:
        raise RuntimeError("No feasible current discrete book")
    current_all_min_book = all_minimum_active_book(
        latest_target,
        current_prices,
        args.initial_equity,
        rules,
        risks[latest_signal],
        industries,
    )
    if not current_all_min_book.feasible:
        raise RuntimeError("No feasible current all-minimum book")

    def current_positions(book: DiscreteBook) -> list[dict[str, Any]]:
        return [
            {
                "symbol": symbol,
                "side": "long" if book.contracts[symbol] > 0 else "short",
                "contracts": book.contracts[symbol],
                "price": rules[symbol].last,
                "notional": book.notionals[symbol],
                "weightPct": book.notionals[symbol] / args.initial_equity * 100.0,
            }
            for symbol in stock_symbols
            if abs(book.contracts[symbol]) > 1e-15
        ]

    def leverage_variants_for(book: DiscreteBook) -> list[dict[str, float]]:
        items: list[dict[str, float]] = []
        for gross_cap in GROSS_CAPS:
            qqq_size = core_contract_size(
                rules["QQQ"],
                rules["QQQ"].last,
                args.initial_equity,
                book.active_gross,
                gross_cap,
            )
            qqq_notional = qqq_size * rules["QQQ"].ct_val * rules["QQQ"].last
            items.append(
                {
                    "grossCap": gross_cap,
                    "qqqContracts": qqq_size,
                    "qqqNotional": qqq_notional,
                    "actualGrossPct": (qqq_notional + book.active_gross)
                    / args.initial_equity
                    * 100.0,
                }
            )
        return items

    active_positions = current_positions(current_book)
    leverage_variants = leverage_variants_for(current_book)
    all_min_positions = current_positions(current_all_min_book)
    all_min_leverage_variants = leverage_variants_for(current_all_min_book)

    rebalance_summary: list[dict[str, Any]] = []
    for gross_cap in GROSS_CAPS:
        for strategy in ("enhanced", "allMin"):
            rows = rebalance_payloads[("base", gross_cap, strategy)]
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for row in rows:
                grouped.setdefault((row["signalDate"], row["session"]), []).append(row)
            for (signal_date, session), group in grouped.items():
                active = [row for row in group if row["symbol"] != "QQQ"]
                if not active:
                    continue
                first = active[0]
                positions_label = ", ".join(
                    f"{row['symbol']} {'+' if row['contracts'] > 0 else '-'}{abs(row['contracts']):.2f}"
                    for row in active
                )
                equity_before = float(first["equityBeforeTrade"])
                rebalance_summary.append(
                    {
                        "strategy": strategy,
                        "grossCap": gross_cap,
                        "signalDate": signal_date,
                        "session": session,
                        "positions": positions_label,
                        "activeGrossPct": float(first["activeGross"])
                        / equity_before
                        * 100.0,
                        "activeNetPct": float(first["activeNet"])
                        / equity_before
                        * 100.0,
                        "betaResidualPct": float(first["betaResidual"])
                        / equity_before
                        * 100.0,
                        "trackingErrorPct": float(first["exAnteTrackingError"]) * 100.0,
                    }
                )

    base_full_12 = results["base"]["1.2"]["enhanced"]["full"]
    base_full_15 = results["base"]["1.5"]["enhanced"]["full"]
    qqq_full_12 = results["base"]["1.2"]["qqqOnly"]["full"]
    qqq_full_15 = results["base"]["1.5"]["qqqOnly"]["full"]
    all_min_full_12 = results["base"]["1.2"]["allMin"]["full"]
    all_min_full_15 = results["base"]["1.5"]["allMin"]["full"]
    enhanced_beats_both = (
        base_full_12["cumulativePct"] > qqq_full_12["cumulativePct"]
        and base_full_15["cumulativePct"] > qqq_full_15["cumulativePct"]
    )
    all_min_beats_both = (
        all_min_full_12["cumulativePct"] > qqq_full_12["cumulativePct"]
        and all_min_full_15["cumulativePct"] > qqq_full_15["cumulativePct"]
    )
    all_min_attribution = []
    for symbol, values in attribution_payloads[("base", 1.2, "allMin")].items():
        if symbol == "QQQ":
            continue
        all_min_attribution.append(
            {
                "symbol": symbol,
                **values,
                "netPnlPctInitial": values["netPnl"]
                / args.initial_equity
                * 100.0,
            }
        )
    all_min_attribution.sort(key=lambda row: row["netPnl"], reverse=True)
    active_net_cash = sum(row["netPnl"] for row in all_min_attribution)
    largest_contributor = all_min_attribution[0]
    active_without_largest = active_net_cash - largest_contributor["netPnl"]
    if all_min_beats_both:
        reason = (
            "全11腿最小合约在43天基础成本下优于同gross的QQQ合约对照，但权重、beta和行业暴露已严重偏离原模型，只能进入全新的只读前瞻观察。"
        )
    else:
        reason = (
            "全11腿最小合约没有同时优于1.2和1.5倍的同gross QQQ合约对照；保留全部方向仍未形成可用于实盘的独立alpha证据。"
        )
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_100_usdt_discrete_qqq_contract_research",
        "modelId": locked["modelId"],
        "config": {
            "initialEquityUsdt": args.initial_equity,
            "grossCaps": list(GROSS_CAPS),
            "activeGrossLimitPct": ACTIVE_GROSS_LIMIT * 100.0,
            "singleStockLimitPct": SINGLE_STOCK_LIMIT * 100.0,
            "dollarResidualLimitPct": DOLLAR_RESIDUAL_LIMIT * 100.0,
            "betaResidualLimitPct": BETA_RESIDUAL_LIMIT * 100.0,
            "industryResidualLimitPct": INDUSTRY_RESIDUAL_LIMIT * 100.0,
            "trackingErrorLimitPct": TRACKING_ERROR_LIMIT * 100.0,
            "baseCostBpsPerSide": cost_variants["base"],
            "stressCostBpsPerSide": cost_variants["stress"],
        },
        "period": {
            "sessions": len(common),
            "start": common[0],
            "end": common[-1],
            "splits": splits,
        },
        "contractRules": [asdict(rules[symbol]) for symbol in symbols],
        "current": {
            "capturedAt": max(rules[symbol].captured_at for symbol in symbols),
            "signalDate": latest_signal.isoformat(),
            "activeGrossPct": current_book.active_gross / args.initial_equity * 100.0,
            "activeNetPct": current_book.active_net / args.initial_equity * 100.0,
            "betaResidualPct": current_book.beta_residual / args.initial_equity * 100.0,
            "trackingErrorPct": current_book.ex_ante_tracking_error * 100.0,
            "targetDeviationTrackingErrorPct": current_book.target_deviation_tracking_error
            * 100.0,
            "activePositions": active_positions,
            "leverageVariants": leverage_variants,
        },
        "currentAllMin": {
            "capturedAt": max(rules[symbol].captured_at for symbol in symbols),
            "signalDate": latest_signal.isoformat(),
            "activeGrossPct": current_all_min_book.active_gross
            / args.initial_equity
            * 100.0,
            "activeNetPct": current_all_min_book.active_net
            / args.initial_equity
            * 100.0,
            "betaResidualPct": current_all_min_book.beta_residual
            / args.initial_equity
            * 100.0,
            "trackingErrorPct": current_all_min_book.ex_ante_tracking_error * 100.0,
            "targetDeviationTrackingErrorPct": current_all_min_book.target_deviation_tracking_error
            * 100.0,
            "activePositions": all_min_positions,
            "leverageVariants": all_min_leverage_variants,
        },
        "results": results,
        "allMinAttributionBase1p2": all_min_attribution,
        "allMinAttributionSummary": {
            "activeNetPnlUsdt": active_net_cash,
            "largestContributor": largest_contributor["symbol"],
            "largestContributorNetPnlUsdt": largest_contributor["netPnl"],
            "activeNetPnlWithoutLargestUsdt": active_without_largest,
        },
        "rebalanceSummary": rebalance_summary,
        "decision": {
            "status": "research_only",
            "enhancedBeatsSameGrossQqqAtBothCaps": enhanced_beats_both,
            "allMinBeatsSameGrossQqqAtBothCaps": all_min_beats_both,
            "eligibleForPaperOrLive": False,
            "reason": reason,
        },
    }

    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    pd.DataFrame(payload["contractRules"]).to_csv(
        output_dir / "contract_rules.csv", index=False
    )
    pd.DataFrame(active_positions).to_csv(
        output_dir / "current_active_positions.csv", index=False
    )
    pd.DataFrame(all_min_positions).to_csv(
        output_dir / "current_all_min_positions.csv", index=False
    )
    pd.DataFrame(rebalance_summary).to_csv(
        output_dir / "rebalance_summary.csv", index=False
    )
    pd.DataFrame(all_min_attribution).to_csv(
        output_dir / "all_min_attribution_base_1.2.csv", index=False
    )
    for (variant, gross_cap, book_name), frame in result_frames.items():
        frame.to_csv(
            output_dir / f"{variant}_{gross_cap:.1f}_{book_name}_daily.csv",
            index_label="session",
        )
    print(f"output_dir={output_dir}")
    print(
        "current_active="
        + json.dumps(active_positions, ensure_ascii=False, separators=(",", ":"))
    )
    print("decision=" + json.dumps(payload["decision"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
