#!/usr/bin/env python3
"""Frozen replay and forward observations for an altcoin funding short.

This module is research-only. It reads public inputs through data_pipeline
loaders and has no account, order, configuration, or executor integration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from data_pipeline import RESEARCH_DIR, load_candles, load_funding


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PREREGISTRATION = (
    PROJECT_ROOT / "config" / "altcoin_negative_funding_reversion_preregistration.json"
)
V2_PREREGISTRATION = (
    PROJECT_ROOT
    / "config"
    / "altcoin_negative_funding_reversion_v2_preregistration.json"
)
V3_PREREGISTRATION = (
    PROJECT_ROOT
    / "config"
    / "altcoin_negative_funding_reversion_v3_preregistration.json"
)
V4_PREREGISTRATION = (
    PROJECT_ROOT
    / "config"
    / "altcoin_negative_funding_reversion_v4_preregistration.json"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "altcoin_negative_funding_reversion"
    / "frozen-v1-development"
)


@dataclass(frozen=True, slots=True)
class Signal:
    decision_at: pd.Timestamp
    entry_at: pd.Timestamp
    inst_id: str
    rank: int
    price_return: float
    turnover_usdt: float
    earlier_funding: float
    latest_funding: float
    funding_improvement: float


@dataclass(frozen=True, slots=True)
class TradePlan:
    signal: Signal
    entry_at: pd.Timestamp
    entry_reference: float
    exit_at: pd.Timestamp
    exit_reference: float
    exit_reason: str
    bearish_hour_return: float | None
    bearish_close_location: float | None


def as_utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def iso_utc(value: Any) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_preregistration(config: dict[str, Any]) -> None:
    required = {
        "modelId",
        "frozenAt",
        "status",
        "paperOrLiveAuthorized",
        "universe",
        "signal",
        "execution",
        "costs",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"preregistration missing fields: {sorted(missing)}")
    if config["paperOrLiveAuthorized"] is not False:
        raise ValueError("research preregistration cannot authorize trading")
    instruments = list(config["universe"].get("instruments", []))
    contract_values = config["universe"].get("contractValue", {})
    if not instruments or set(instruments) != set(contract_values):
        raise ValueError("instrument and contract-value universes differ")
    execution = config["execution"]
    leverage = float(execution["leverage"])
    notional_fraction = float(execution["notionalFractionPerPosition"])
    maximum_positions = int(execution["maximumConcurrentPositions"])
    margin_fraction = float(
        execution.get("marginFractionPerPosition", notional_fraction / leverage)
    )
    maximum_margin = float(
        execution.get("maximumConcurrentMarginFraction", 0.10)
    )
    maximum_notional = float(
        execution.get("maximumGrossNotionalFraction", 0.20)
    )
    if leverage <= 0.0 or leverage > 2.0:
        raise ValueError("frozen leverage must be in (0, 2]")
    if maximum_positions <= 0:
        raise ValueError("maximum concurrent positions must be positive")
    if margin_fraction <= 0.0 or margin_fraction > 0.10 + 1e-12:
        raise ValueError("per-position margin must be in (0, 10%]")
    if notional_fraction > margin_fraction * leverage + 1e-12:
        raise ValueError("notional exposure exceeds frozen margin times leverage")
    if maximum_margin <= 0.0 or maximum_margin > 0.20 + 1e-12:
        raise ValueError("frozen concurrent margin cap must be in (0, 20%]")
    if maximum_notional <= 0.0 or maximum_notional > 0.40 + 1e-12:
        raise ValueError("frozen gross notional cap must be in (0, 40%]")
    if margin_fraction * maximum_positions > maximum_margin + 1e-12:
        raise ValueError("frozen concurrent margin exceeds its configured cap")
    if notional_fraction * maximum_positions > maximum_notional + 1e-12:
        raise ValueError("frozen gross notional exposure exceeds its configured cap")
    signal = config["signal"]
    top_n = int(signal["crossSectionTopN"])
    if top_n <= 0 or top_n > len(instruments):
        raise ValueError("cross-section capacity must be within the frozen universe")
    if signal.get("crossSectionRankBy", "price_return") not in {
        "price_return",
        "funding_improvement",
    }:
        raise ValueError("unsupported cross-section ranking metric")
    if execution.get("hardStopFraction") is None:
        if execution.get("marginMode") != "isolated":
            raise ValueError("a no-stop specification requires isolated margin")
        liquidation_move = float(
            execution.get("modeledLiquidationAdverseMoveFraction", 0.0)
        )
        if liquidation_move <= 0.0:
            raise ValueError("a no-stop specification requires modeled liquidation")


def load_inputs(
    config: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    candles: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for inst_id in config["universe"]["instruments"]:
        candle_frame = load_candles(inst_id, str(config["execution"]["bar"]))
        funding_frame = load_funding(inst_id)
        if candle_frame.empty or funding_frame.empty:
            raise ValueError(f"data lake coverage missing for {inst_id}")
        candle_frame = candle_frame.copy()
        funding_frame = funding_frame.copy()
        candle_frame["time"] = pd.to_datetime(candle_frame["time"], utc=True)
        funding_frame["funding_time"] = pd.to_datetime(
            funding_frame["funding_time"], utc=True
        )
        candles[inst_id] = (
            candle_frame.sort_values("time")
            .drop_duplicates("time", keep="last")
            .reset_index(drop=True)
        )
        funding[inst_id] = (
            funding_frame.sort_values("funding_time")
            .drop_duplicates("funding_time", keep="last")
            .reset_index(drop=True)
        )
    return candles, funding


def common_window(
    config: dict[str, Any],
    candles: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    *,
    require_completed_holding: bool,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    lookback = pd.Timedelta(hours=int(config["signal"]["priceLookbackHours"]))
    holding = pd.Timedelta(hours=int(config["execution"]["maximumHoldingHours"]))
    starts: list[pd.Timestamp] = []
    ends: list[pd.Timestamp] = []
    for inst_id in config["universe"]["instruments"]:
        starts.append(
            max(
                as_utc(candles[inst_id]["time"].iloc[0]) + lookback,
                as_utc(funding[inst_id]["funding_time"].iloc[1]),
            )
        )
        candle_end = as_utc(candles[inst_id]["time"].iloc[-1])
        if require_completed_holding:
            candle_end -= holding
        ends.append(
            min(candle_end, as_utc(funding[inst_id]["funding_time"].iloc[-1]))
        )
    start = max(starts)
    end = min(ends)
    if end < start:
        raise ValueError(f"no common data window: {start}..{end}")
    return start, end


def point_features(
    config: dict[str, Any],
    inst_id: str,
    decision_at: pd.Timestamp,
    candles: pd.DataFrame,
    funding: pd.DataFrame,
) -> dict[str, Any]:
    signal = config["signal"]
    funding_seen = funding[funding["funding_time"] <= decision_at]
    current_exact = (
        not funding_seen.empty
        and as_utc(funding_seen["funding_time"].iloc[-1]) == decision_at
    )
    row: dict[str, Any] = {
        "instId": inst_id,
        "decisionAt": iso_utc(decision_at),
        "hasCurrentFunding": bool(current_exact),
        "eligibleBeforeRank": False,
        "selected": False,
        "reasons": [],
    }
    if not current_exact or len(funding_seen) < int(signal["fundingObservations"]):
        row["reasons"].append("funding_observation_missing")
        return row

    earlier = float(funding_seen["realized_rate"].iloc[-2])
    latest = float(funding_seen["realized_rate"].iloc[-1])
    improvement = latest - earlier
    prior = candles[candles["time"] < decision_at]
    if prior.empty:
        row["reasons"].append("prior_candles_missing")
        return row

    price_cutoff = decision_at - pd.Timedelta(
        hours=int(signal["priceLookbackHours"])
    )
    reference = prior[prior["time"] <= price_cutoff]
    if (
        reference.empty
        or price_cutoff - as_utc(reference["time"].iloc[-1])
        > pd.Timedelta(minutes=10)
    ):
        row["reasons"].append("price_lookback_incomplete")
        return row
    price_return = float(
        prior["close"].iloc[-1] / reference["close"].iloc[-1] - 1.0
    )

    liquidity_start = decision_at - pd.Timedelta(
        hours=int(signal["liquidityLookbackHours"])
    )
    liquid = prior[prior["time"] >= liquidity_start]
    expected = int(signal["liquidityLookbackHours"]) * 12
    coverage = len(liquid) / expected if expected else 0.0
    contract_value = float(config["universe"]["contractValue"][inst_id])
    turnover = float(
        (liquid["volume"] * contract_value * liquid["close"]).sum()
    )
    next_bar = candles[candles["time"] > decision_at]
    entry_at = as_utc(next_bar["time"].iloc[0]) if not next_bar.empty else None
    row.update(
        {
            "earlierFunding": earlier,
            "latestFunding": latest,
            "fundingImprovement": improvement,
            "priceReturn": price_return,
            "turnoverUsdt": turnover,
            "liquidityCoverage": coverage,
            "entryAt": iso_utc(entry_at) if entry_at is not None else None,
        }
    )
    checks = {
        "earlier_funding_not_negative_enough": earlier
        <= float(signal["earlierFundingMaximum"]),
        "latest_funding_not_below_zero": latest
        < float(signal["latestFundingMaximum"]),
        "funding_improvement_too_small": improvement
        >= float(signal["minimumFundingImprovement"]),
        "price_return_too_small": price_return
        >= float(signal["minimumPriceReturn"]),
        "turnover_too_small": turnover
        >= float(signal["minimumApproxQuoteTurnoverUsdt"]),
        "liquidity_coverage_incomplete": coverage
        >= float(signal["minimumLiquidityBarCoverage"]),
        "entry_bar_missing": entry_at is not None,
    }
    row["reasons"].extend(reason for reason, passed in checks.items() if not passed)
    row["eligibleBeforeRank"] = not row["reasons"]
    return row


def build_signals(
    config: dict[str, Any],
    candles: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[list[Signal], list[dict[str, Any]]]:
    decision_times = sorted(
        {
            as_utc(value)
            for frame in funding.values()
            for value in frame["funding_time"]
            if start <= as_utc(value) <= end
        }
    )
    selected: list[Signal] = []
    audit: list[dict[str, Any]] = []
    top_n = int(config["signal"]["crossSectionTopN"])
    rank_by = str(config["signal"].get("crossSectionRankBy", "price_return"))
    for decision_at in decision_times:
        rows = [
            point_features(
                config, inst_id, decision_at, candles[inst_id], funding[inst_id]
            )
            for inst_id in config["universe"]["instruments"]
        ]
        eligible = [row for row in rows if row["eligibleBeforeRank"]]
        if rank_by == "funding_improvement":
            eligible.sort(
                key=lambda row: (
                    -float(row["fundingImprovement"]),
                    -float(row["priceReturn"]),
                    str(row["instId"]),
                )
            )
        else:
            eligible.sort(
                key=lambda row: (-float(row["priceReturn"]), str(row["instId"]))
            )
        for rank, row in enumerate(eligible, start=1):
            row["rank"] = rank
            if rank > top_n:
                row["reasons"].append("outside_cross_section_top_n")
                continue
            row["selected"] = True
            selected.append(
                Signal(
                    decision_at=decision_at,
                    entry_at=as_utc(row["entryAt"]),
                    inst_id=str(row["instId"]),
                    rank=rank,
                    price_return=float(row["priceReturn"]),
                    turnover_usdt=float(row["turnoverUsdt"]),
                    earlier_funding=float(row["earlierFunding"]),
                    latest_funding=float(row["latestFunding"]),
                    funding_improvement=float(row["fundingImprovement"]),
                )
            )
        audit.extend(rows)
    return selected, audit


def plan_trade(
    config: dict[str, Any], signal: Signal, candles: pd.DataFrame
) -> TradePlan:
    execution = config["execution"]
    entry_rows = candles.index[candles["time"] == signal.entry_at]
    if len(entry_rows) != 1:
        raise ValueError(f"entry candle missing for {signal.inst_id} {signal.entry_at}")
    entry_index = int(entry_rows[0])
    entry_reference = float(candles.loc[entry_index, "open"])
    hard_stop_fraction = execution.get("hardStopFraction")
    stop = (
        None
        if hard_stop_fraction is None
        else entry_reference * (1.0 + float(hard_stop_fraction))
    )
    liquidation_move = execution.get("modeledLiquidationAdverseMoveFraction")
    liquidation = (
        None
        if liquidation_move is None
        else entry_reference * (1.0 + float(liquidation_move))
    )
    liquidation_penalty = (
        float(execution.get("modeledLiquidationPenaltyBps", 0.0)) / 10_000.0
    )
    deadline = signal.entry_at + pd.Timedelta(
        hours=int(execution["maximumHoldingHours"])
    )
    bearish = execution["bigBearishCandle"]

    for index in range(entry_index, len(candles)):
        bar = candles.loc[index]
        at = as_utc(bar["time"])
        open_price = float(bar["open"])
        if stop is not None and open_price >= stop:
            return TradePlan(
                signal,
                signal.entry_at,
                entry_reference,
                at,
                open_price,
                "hard_stop",
                None,
                None,
            )
        if liquidation is not None and open_price >= liquidation:
            return TradePlan(
                signal,
                signal.entry_at,
                entry_reference,
                at,
                open_price * (1.0 + liquidation_penalty),
                "modeled_liquidation",
                None,
                None,
            )
        if at.minute == 0 and at.second == 0 and signal.entry_at <= at - pd.Timedelta(hours=1):
            hour = candles[
                (candles["time"] >= at - pd.Timedelta(hours=1))
                & (candles["time"] < at)
            ]
            if len(hour) == 12:
                hour_return = float(
                    hour["close"].iloc[-1] / hour["open"].iloc[0] - 1.0
                )
                hour_high = float(hour["high"].max())
                hour_low = float(hour["low"].min())
                close_location = (
                    (float(hour["close"].iloc[-1]) - hour_low)
                    / (hour_high - hour_low)
                    if hour_high > hour_low
                    else 1.0
                )
                if (
                    hour_return
                    <= float(bearish["maximumOpenToCloseReturn"])
                    and close_location
                    <= float(bearish["maximumCloseLocationInRange"])
                    and float(hour["close"].iloc[-1]) < entry_reference
                ):
                    return TradePlan(
                        signal,
                        signal.entry_at,
                        entry_reference,
                        at,
                        open_price,
                        "big_bearish_candle_take_profit",
                        hour_return,
                        close_location,
                    )
        if at >= deadline:
            return TradePlan(
                signal,
                signal.entry_at,
                entry_reference,
                at,
                open_price,
                "time_exit",
                None,
                None,
            )
        if stop is not None and float(bar["high"]) >= stop:
            return TradePlan(
                signal,
                signal.entry_at,
                entry_reference,
                at,
                stop,
                "hard_stop",
                None,
                None,
            )
        if liquidation is not None and float(bar["high"]) >= liquidation:
            return TradePlan(
                signal,
                signal.entry_at,
                entry_reference,
                at,
                liquidation * (1.0 + liquidation_penalty),
                "modeled_liquidation",
                None,
                None,
            )
    raise ValueError(f"trade path is incomplete for {signal.inst_id} {signal.entry_at}")


def enforce_portfolio_constraints(
    config: dict[str, Any],
    signals: list[Signal],
    candles: dict[str, pd.DataFrame],
) -> tuple[list[TradePlan], Counter[str]]:
    maximum = int(config["execution"]["maximumConcurrentPositions"])
    cooldown = pd.Timedelta(
        hours=int(config["execution"]["reentryCooldownHours"])
    )
    active: list[TradePlan] = []
    selected: list[TradePlan] = []
    last_exit: dict[str, pd.Timestamp] = {}
    skipped: Counter[str] = Counter()
    ordered = sorted(
        signals,
        key=lambda row: (row.entry_at, row.rank, -row.price_return, row.inst_id),
    )
    for signal in ordered:
        active = [plan for plan in active if plan.exit_at > signal.entry_at]
        if any(plan.signal.inst_id == signal.inst_id for plan in active):
            skipped["same_instrument_already_open"] += 1
            continue
        if (
            signal.inst_id in last_exit
            and signal.entry_at < last_exit[signal.inst_id] + cooldown
        ):
            skipped["reentry_cooldown"] += 1
            continue
        if len(active) >= maximum:
            skipped["maximum_concurrent_positions"] += 1
            continue
        plan = plan_trade(config, signal, candles[signal.inst_id])
        selected.append(plan)
        active.append(plan)
        last_exit[signal.inst_id] = plan.exit_at
    return selected, skipped


def price_at(candles: pd.DataFrame, at: pd.Timestamp, column: str) -> float:
    exact = candles[candles["time"] == at]
    if not exact.empty:
        return float(exact[column].iloc[0])
    prior = candles[candles["time"] < at]
    if prior.empty:
        raise ValueError(f"no price at or before {at}")
    return float(prior["close"].iloc[-1])


def worst_rolling_return(
    equity_rows: list[dict[str, Any]], days: int = 7
) -> float:
    if not equity_rows:
        return 0.0
    frame = (
        pd.DataFrame(equity_rows)
        .set_index("time")["equity"]
        .resample("1D")
        .last()
        .dropna()
    )
    returns = frame.pct_change().dropna()
    if returns.empty:
        return 0.0
    window = min(days, len(returns))
    rolled = (1.0 + returns).rolling(window).apply(
        lambda values: float(values.prod()), raw=False
    ) - 1.0
    valid = rolled.dropna()
    return float(valid.min() * 100.0) if not valid.empty else 0.0


def simulate_portfolio(
    config: dict[str, Any],
    plans: list[TradePlan],
    candles: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    *,
    cost_multiplier: float,
    include_funding: bool,
) -> dict[str, Any]:
    if not plans:
        return {
            "returnPct": 0.0,
            "maxDrawdownPct": 0.0,
            "profitFactor": 0.0,
            "trades": 0,
            "fundingPnl": 0.0,
            "fees": 0.0,
            "slippageCost": 0.0,
            "worst7DayReturnPct": 0.0,
            "tradeRows": [],
        }
    fee_rate = (
        float(config["costs"]["takerFeePerSideBps"])
        * cost_multiplier
        / 10_000.0
    )
    slip = (
        float(config["costs"]["adverseSlippagePerSideBps"])
        * cost_multiplier
        / 10_000.0
    )
    fraction = float(config["execution"]["notionalFractionPerPosition"])
    entries: dict[pd.Timestamp, list[TradePlan]] = defaultdict(list)
    exits: dict[pd.Timestamp, list[TradePlan]] = defaultdict(list)
    for plan in plans:
        entries[plan.entry_at].append(plan)
        exits[plan.exit_at].append(plan)
    start = min(plan.entry_at for plan in plans)
    end = max(plan.exit_at for plan in plans)
    timeline = pd.date_range(
        start.floor("5min"), end.ceil("5min"), freq="5min", tz="UTC"
    )
    funding_maps = {
        inst_id: {
            as_utc(row.funding_time): float(row.realized_rate)
            for row in frame.itertuples()
        }
        for inst_id, frame in funding.items()
    }
    cash = 100.0
    peak = cash
    max_drawdown = 0.0
    positions: dict[str, dict[str, Any]] = {}
    equity_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    def marked_equity(at: pd.Timestamp, column: str = "open") -> float:
        return cash + sum(
            (
                position["entryFill"]
                - price_at(candles[inst_id], at, column)
            )
            * position["quantity"]
            for inst_id, position in positions.items()
        )

    def close_position(plan: TradePlan) -> None:
        nonlocal cash
        position = positions.pop(plan.signal.inst_id)
        exit_fill = plan.exit_reference * (1.0 + slip)
        fill_pnl = (
            position["entryFill"] - exit_fill
        ) * position["quantity"]
        exit_fee = abs(exit_fill * position["quantity"]) * fee_rate
        cash += fill_pnl - exit_fee
        reference_quantity = position["notional"] / plan.entry_reference
        gross_pnl = (
            plan.entry_reference - plan.exit_reference
        ) * reference_quantity
        net_pnl = (
            fill_pnl
            - position["entryFee"]
            - exit_fee
            + position["fundingPnl"]
        )
        trade_rows.append(
            {
                "instId": plan.signal.inst_id,
                "decisionAt": iso_utc(plan.signal.decision_at),
                "entryAt": iso_utc(plan.entry_at),
                "exitAt": iso_utc(plan.exit_at),
                "exitReason": plan.exit_reason,
                "rank": plan.signal.rank,
                "priceReturn72hPct": plan.signal.price_return * 100.0,
                "turnover24hUsdt": plan.signal.turnover_usdt,
                "earlierFundingBps": plan.signal.earlier_funding * 10_000.0,
                "latestFundingBps": plan.signal.latest_funding * 10_000.0,
                "fundingImprovementBps": (
                    plan.signal.funding_improvement * 10_000.0
                ),
                "entryReference": plan.entry_reference,
                "exitReference": plan.exit_reference,
                "notional": position["notional"],
                "grossPricePnl": gross_pnl,
                "fundingPnl": position["fundingPnl"],
                "fees": position["entryFee"] + exit_fee,
                "slippageCost": gross_pnl - fill_pnl,
                "netPnl": net_pnl,
                "bearishHourReturnPct": (
                    None
                    if plan.bearish_hour_return is None
                    else plan.bearish_hour_return * 100.0
                ),
                "bearishCloseLocation": plan.bearish_close_location,
            }
        )

    for at in timeline:
        if include_funding:
            for inst_id, position in list(positions.items()):
                if (
                    at in funding_maps[inst_id]
                    and position["plan"].entry_at < at
                    <= position["plan"].exit_at
                ):
                    mark = price_at(candles[inst_id], at, "open")
                    payment = (
                        mark
                        * position["quantity"]
                        * funding_maps[inst_id][at]
                    )
                    cash += payment
                    position["fundingPnl"] += payment
        for plan in exits.get(at, []):
            if plan.entry_at < at and plan.signal.inst_id in positions:
                close_position(plan)
        for plan in entries.get(at, []):
            if plan.signal.inst_id in positions:
                raise RuntimeError(
                    f"overlapping position: {plan.signal.inst_id}"
                )
            notional = max(0.0, marked_equity(at, "open") * fraction)
            entry_fill = plan.entry_reference * (1.0 - slip)
            quantity = notional / entry_fill if entry_fill > 0 else 0.0
            entry_fee = notional * fee_rate
            cash -= entry_fee
            positions[plan.signal.inst_id] = {
                "plan": plan,
                "notional": notional,
                "entryFill": entry_fill,
                "quantity": quantity,
                "entryFee": entry_fee,
                "fundingPnl": 0.0,
            }
        for plan in exits.get(at, []):
            if plan.entry_at == at and plan.signal.inst_id in positions:
                close_position(plan)
        equity = marked_equity(at, "close")
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(
                max_drawdown, (peak - equity) / peak * 100.0
            )
        equity_rows.append({"time": at, "equity": equity})
    if positions:
        raise RuntimeError(f"positions not closed: {sorted(positions)}")
    gross_profit = sum(
        float(row["netPnl"])
        for row in trade_rows
        if float(row["netPnl"]) > 0
    )
    gross_loss = abs(
        sum(
            float(row["netPnl"])
            for row in trade_rows
            if float(row["netPnl"]) < 0
        )
    )
    return {
        "returnPct": (cash / 100.0 - 1.0) * 100.0,
        "maxDrawdownPct": max_drawdown,
        "profitFactor": (
            gross_profit / gross_loss
            if gross_loss > 0
            else (999.0 if gross_profit > 0 else 0.0)
        ),
        "trades": len(trade_rows),
        "fundingPnl": sum(float(row["fundingPnl"]) for row in trade_rows),
        "fees": sum(float(row["fees"]) for row in trade_rows),
        "slippageCost": sum(
            float(row["slippageCost"]) for row in trade_rows
        ),
        "worst7DayReturnPct": worst_rolling_return(equity_rows),
        "tradeRows": trade_rows,
    }


def compact_metrics(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "tradeRows"}


def split_boundaries(
    start: pd.Timestamp, end: pd.Timestamp
) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    span = end - start
    train_end = start + span * 0.50
    validation_end = start + span * 0.75
    return [
        ("train", start, train_end),
        ("validation", train_end, validation_end),
        ("test", validation_end, end + pd.Timedelta(nanoseconds=1)),
    ]


def run_replay(
    config: dict[str, Any], preregistration_path: Path
) -> dict[str, Any]:
    if config.get("evidencePolicy", {}).get("developmentReplayAllowed") is False:
        raise ValueError(
            "development replay is disabled; this specification is forward-only"
        )
    candles, funding = load_inputs(config)
    start, end = common_window(
        config, candles, funding, require_completed_holding=True
    )
    signals, audit = build_signals(config, candles, funding, start, end)
    plans, skipped = enforce_portfolio_constraints(config, signals, candles)
    gross = simulate_portfolio(
        config,
        plans,
        candles,
        funding,
        cost_multiplier=0.0,
        include_funding=False,
    )
    base = simulate_portfolio(
        config,
        plans,
        candles,
        funding,
        cost_multiplier=1.0,
        include_funding=True,
    )
    stressed = simulate_portfolio(
        config,
        plans,
        candles,
        funding,
        cost_multiplier=float(config["costs"]["stressMultiplier"]),
        include_funding=True,
    )
    splits: dict[str, Any] = {}
    for name, split_start, split_end in split_boundaries(start, end):
        split_plans = [
            plan for plan in plans if split_start <= plan.entry_at < split_end
        ]
        split_gross = simulate_portfolio(
            config,
            split_plans,
            candles,
            funding,
            cost_multiplier=0.0,
            include_funding=False,
        )
        split_base = simulate_portfolio(
            config,
            split_plans,
            candles,
            funding,
            cost_multiplier=1.0,
            include_funding=True,
        )
        split_stressed = simulate_portfolio(
            config,
            split_plans,
            candles,
            funding,
            cost_multiplier=float(config["costs"]["stressMultiplier"]),
            include_funding=True,
        )
        splits[name] = {
            "start": iso_utc(split_start),
            "end": iso_utc(split_end),
            "gross": compact_metrics(split_gross),
            "base": compact_metrics(split_base),
            "stressed": compact_metrics(split_stressed),
        }
    exits = Counter(plan.exit_reason for plan in plans)
    instruments = Counter(plan.signal.inst_id for plan in plans)
    failure_reasons = Counter(
        reason
        for row in audit
        for reason in row.get("reasons", [])
    )
    latencies = [
        (plan.entry_at - plan.signal.decision_at).total_seconds() / 60.0
        for plan in plans
    ]
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "mode": "frozen_development_replay_not_new_evidence",
        "modelId": config["modelId"],
        "preregistrationSha256": sha256_file(preregistration_path),
        "paperOrLiveAuthorized": False,
        "dataWindow": {"start": iso_utc(start), "end": iso_utc(end)},
        "decisionTimestamps": len({row["decisionAt"] for row in audit}),
        "auditedInstrumentDecisions": len(audit),
        "rawSignals": len(signals),
        "trades": len(plans),
        "portfolioConstraintSkips": dict(skipped),
        "exitReasonCounts": dict(sorted(exits.items())),
        "instrumentTradeCounts": dict(sorted(instruments.items())),
        "failureReasonCounts": dict(failure_reasons.most_common()),
        "meanDecisionToEntryMinutes": (
            sum(latencies) / len(latencies) if latencies else None
        ),
        "overall": {
            "gross": compact_metrics(gross),
            "base": compact_metrics(base),
            "stressed": compact_metrics(stressed),
        },
        "splits": splits,
        "tradeRows": base["tradeRows"],
        "signalAudit": audit,
        "limitations": [
            "All replay data predates or overlaps the preregistration boundary and is development-only.",
            "The fixed current-contract universe creates survivorship bias and excludes delisted contracts.",
            "Historical quote turnover is approximated from candle volume, contract value, and close; historical bid/ask and depth are unavailable.",
            "Realized funding is observable only at its timestamp; entry is delayed to the first later 5-minute open.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(payload: dict[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# 山寨币负资金费向零修复做空：冻结开发回放",
        "",
        f"- 模型：{payload['modelId']}",
        f"- 数据区间：{payload['dataWindow']['start']} 至 {payload['dataWindow']['end']}",
        "- 证据等级：仅开发回放，不是预注册后的新样本",
        "- 纸盘/实盘授权：否",
        "",
        "## 规则",
        "",
        "固定 6 个山寨永续；72 小时涨幅至少 20%，且为同一资金费时点候选中涨幅前 2；过去 24 小时近似成交额至少 1000 万 USDT；前次资金费不高于 -5 bps，最新仍低于 0，且至少向零修复 2 bps。资金费公布后的第一根 5 分钟开盘做空。每仓名义本金 5%，1 倍杠杆，最多两仓；8% 止损，24 小时时间退出；盈利状态下出现 1 小时跌幅不低于 4%、收盘位于小时振幅底部 25% 时，下一根 5 分钟开盘止盈。",
        "",
        "## 整体结果",
        "",
        "| 口径 | 收益 | PF | 最大回撤 | 交易数 | 资金费 | 手续费 | 滑点成本 | 最差7日 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, label in (("gross", "毛价格"), ("base", "基础成本"), ("stressed", "双倍成本")):
        row = overall[key]
        lines.append(
            f"| {label} | {row['returnPct']:.6f}% | {row['profitFactor']:.3f} | "
            f"{row['maxDrawdownPct']:.6f}% | {row['trades']} | {row['fundingPnl']:.6f} | "
            f"{row['fees']:.6f} | {row['slippageCost']:.6f} | {row['worst7DayReturnPct']:.6f}% |"
        )
    if payload["trades"] == 0:
        lines.extend([
            "",
            "结论：当前共同历史没有触发冻结条件，收益、胜率和 PF 均不可评估；表中的 0 不是策略通过或保本。",
        ])
    lines.extend([
        "",
        "## 时间顺序切分",
        "",
        "| 区间 | 时间 | 毛价格 | 基础成本 | 双倍成本 | 基础PF | 交易数 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for name in ("train", "validation", "test"):
        row = payload["splits"][name]
        lines.append(
            f"| {name} | {row['start']} - {row['end']} | "
            f"{row['gross']['returnPct']:.6f}% | {row['base']['returnPct']:.6f}% | "
            f"{row['stressed']['returnPct']:.6f}% | {row['base']['profitFactor']:.3f} | "
            f"{row['base']['trades']} |"
        )
    lines.extend([
        "",
        "## 样本与退出",
        "",
        f"- 原始信号：{payload['rawSignals']}",
        f"- 实际交易：{payload['trades']}",
        f"- 未通过原因计数：{json.dumps(payload['failureReasonCounts'], ensure_ascii=False)}",
        f"- 退出原因：{json.dumps(payload['exitReasonCounts'], ensure_ascii=False, sort_keys=True)}",
        f"- 合约分布：{json.dumps(payload['instrumentTradeCounts'], ensure_ascii=False, sort_keys=True)}",
        f"- 平均决策到入场延迟：{payload['meanDecisionToEntryMinutes']} 分钟",
        "",
        "## 结论边界",
        "",
    ])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.extend([
        "- 无论本次结果好坏，都不能据此授权纸盘或实盘，也不能回看后修改冻结阈值。",
        "",
    ])
    return "\n".join(lines)


def write_replay(payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_csv(output_dir / "trades.csv", payload["tradeRows"])
    audit_rows = [
        {**row, "reasons": "|".join(row.get("reasons", []))}
        for row in payload["signalAudit"]
    ]
    write_csv(output_dir / "signal_audit.csv", audit_rows)
    (output_dir / "report.md").write_text(
        markdown_report(payload), encoding="utf-8"
    )


def read_jsonl(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def serializable_signal(signal: Signal) -> dict[str, Any]:
    row = asdict(signal)
    row["decision_at"] = iso_utc(row["decision_at"])
    row["entry_at"] = iso_utc(row["entry_at"])
    return row


def collect_forward_observations(
    config: dict[str, Any], preregistration_path: Path
) -> dict[str, Any]:
    candles, funding = load_inputs(config)
    observable_start, observable_end = common_window(
        config, candles, funding, require_completed_holding=False
    )
    boundary = as_utc(config["evidencePolicy"]["forwardEvaluationStart"])
    start = max(observable_start, boundary)
    if observable_end < start:
        return {
            "status": "waiting_for_post_boundary_funding",
            "observationsAdded": 0,
            "latestCommonFundingAt": iso_utc(observable_end),
        }
    signals, audit = build_signals(
        config, candles, funding, start, observable_end
    )
    root = RESEARCH_DIR / str(config["modelId"])
    existing = {str(row.get("decisionAt")) for row in read_jsonl(root)}
    captured = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    by_time: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in audit:
        by_time[str(row["decisionAt"])].append(row)
    added = 0
    for decision_at, rows in sorted(by_time.items()):
        if decision_at in existing:
            continue
        selected = [
            serializable_signal(signal)
            for signal in signals
            if iso_utc(signal.decision_at) == decision_at
        ]
        payload = {
            "schemaVersion": 1,
            "modelId": config["modelId"],
            "observationType": "funding_decision",
            "capturedAt": captured,
            "decisionAt": decision_at,
            "preregistrationSha256": sha256_file(preregistration_path),
            "instrumentRows": rows,
            "selectedSignals": selected,
            "ordersOrAccountAccess": False,
            "paperOrLiveAuthorized": False,
        }
        at = as_utc(decision_at)
        append_jsonl(root / f"{at:%Y%m%d}.jsonl", payload)
        added += 1
    return {
        "status": "collected",
        "observationsAdded": added,
        "decisionTimesSeen": len(by_time),
        "latestCommonFundingAt": iso_utc(observable_end),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Frozen altcoin negative-funding reversion research"
    )
    parser.add_argument(
        "--preregistration", default=str(DEFAULT_PREREGISTRATION)
    )
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser(
        "backtest", help="run the frozen development replay"
    )
    replay.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    sub.add_parser(
        "observe", help="append post-boundary funding-decision observations"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preregistration_path = Path(args.preregistration)
    config = read_json(preregistration_path)
    validate_preregistration(config)
    if args.command == "backtest":
        payload = run_replay(config, preregistration_path)
        output_dir = Path(args.output_dir)
        write_replay(payload, output_dir)
        print(
            json.dumps(
                {
                    "report": str(output_dir / "report.md"),
                    "mode": payload["mode"],
                    "trades": payload["trades"],
                    "baseReturnPct": payload["overall"]["base"]["returnPct"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    result = collect_forward_observations(config, preregistration_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
