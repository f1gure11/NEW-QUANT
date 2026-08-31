"""Read-only research for passive fills around option GEX walls.

The older :mod:`gex_strategy` waits for candle confirmation and enters on the
next open.  This module tests a different mechanism: a resting buy below the
Put Wall and a resting sell above the Call Wall.  It deliberately has no OKX
client, account, order, leverage, or service integration.

Important execution assumptions are conservative but still bar-based.  A GEX
event must be known strictly before a quote candle, price must trade through a
limit, simultaneous two-sided touches are skipped, a new fill cannot take
profit on its fill candle, and ambiguous stop/target candles resolve to the
stop.  Real queue priority still requires event-level forward validation.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, iso_time, read_candles_csv
from gex_delta_neutral_research import GexEvent, load_crypto_gex_events


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GEX = PROJECT_ROOT / "data" / "okx" / "gex_snapshots.jsonl"
DEFAULT_CANDLE_ROOT = PROJECT_ROOT / "data" / "vwap_market_maker"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "gex_pin_catcher"
UNDERLYINGS = ("BTC", "ETH")
BAR_MS = 5 * 60 * 1000


@dataclass(frozen=True, slots=True)
class PinCandidate:
    wall_offset_bps: float
    take_profit_bps: float
    stop_loss_bps: float
    max_hold_bars: int
    max_gex_age_hours: float


@dataclass(frozen=True, slots=True)
class PinExecutionConfig:
    starting_equity: float = 100_000.0
    allocation_pct: float = 20.0
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    exit_slippage_bps: float = 1.0
    penetration_bps: float = 0.5
    max_wall_distance_bps: float = 200.0
    wall_move_exit_bps: float = 50.0
    event_latency_bars: int = 0


@dataclass(slots=True)
class PinPosition:
    side: int
    entry_price: float
    quantity: float
    entry_ts: int
    entry_index: int
    entry_event_ts: int
    anchor_wall: float
    stop_price: float
    target_price: float
    entry_fee: float
    entry_equity: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Point-in-time BTC/ETH passive pin-catching research around positive-GEX walls."
    )
    parser.add_argument("--gex-file", default=str(DEFAULT_GEX))
    parser.add_argument("--candle-root", default=str(DEFAULT_CANDLE_ROOT))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--minimum-training-trades", type=int, default=5)
    return parser.parse_args()


def candidate_grid() -> list[PinCandidate]:
    exits = ((25.0, 50.0, 12), (40.0, 80.0, 24), (60.0, 120.0, 48))
    return [
        PinCandidate(offset, take_profit, stop_loss, bars, age)
        for offset in (0.0, 10.0, 25.0, 50.0)
        for take_profit, stop_loss, bars in exits
        for age in (1.0, 3.0, 6.0)
    ]


def latest_event_strictly_before(
    events: list[GexEvent], timestamp: int
) -> GexEvent | None:
    """Return only information that existed before ``timestamp``."""

    if not events:
        return None
    timestamps = [event.event_ts for event in events]
    index = bisect.bisect_left(timestamps, timestamp) - 1
    return events[index] if index >= 0 else None


def quote_limits(event: GexEvent, candidate: PinCandidate) -> tuple[float, float]:
    offset = candidate.wall_offset_bps / 10_000.0
    return event.put_wall * (1.0 - offset), event.call_wall * (1.0 + offset)


def _finite_price(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) and parsed > 0 else 0.0


def _adverse_market_price(reference: float, side: int, slippage_bps: float) -> float:
    # Closing a long sells lower; closing a short buys higher.
    return reference * (1.0 - side * slippage_bps / 10_000.0)


def _profit_factor(values: list[float]) -> float:
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses > 0:
        return gains / losses
    return 999.0 if gains > 0 else 0.0


def _wall_moved(position: PinPosition, event: GexEvent, threshold_bps: float) -> bool:
    wall = event.put_wall if position.side > 0 else event.call_wall
    if wall <= 0 or position.anchor_wall <= 0:
        return True
    return abs(wall / position.anchor_wall - 1.0) * 10_000.0 > threshold_bps


def run_pin_backtest(
    candles: list[Candle],
    events: list[GexEvent],
    candidate: PinCandidate,
    execution: PinExecutionConfig | None = None,
    *,
    record_details: bool = False,
) -> dict[str, Any]:
    """Simulate one unlevered position around positive-GEX walls.

    Candle timestamps are treated as bar-open timestamps.  The selected GEX
    event is strictly earlier than the order's active bar.  When
    ``event_latency_bars`` is positive the observable event cutoff is shifted
    further back, while freshness is still measured at the actual bar time.
    """

    execution = execution or PinExecutionConfig()
    rows = sorted(candles, key=lambda item: item.ts)
    event_rows = sorted(events, key=lambda item: item.event_ts)
    if not rows:
        return _empty_result(execution.starting_equity)
    if candidate.max_hold_bars < 1 or candidate.max_gex_age_hours <= 0:
        raise ValueError("holding period and GEX age must be positive")

    cash = execution.starting_equity
    position: PinPosition | None = None
    trades: list[dict[str, Any]] = []
    equity_curve = [cash]
    quote_bars = 0
    fresh_gex_bars = 0
    positive_gamma_bars = 0
    eligible_quote_bars = 0
    single_pin_quote_bars = 0
    both_sides_touched = 0
    maker_entries = 0
    risk_exits = 0
    target_exits = 0
    stale_exit_count = 0
    regime_exit_count = 0
    wall_move_exit_count = 0
    max_age_ms = int(candidate.max_gex_age_hours * 60 * 60 * 1000)

    def close_position(
        current: PinPosition,
        candle: Candle,
        exit_reference: float,
        reason: str,
        *,
        maker: bool,
    ) -> None:
        nonlocal cash, position, risk_exits, target_exits
        nonlocal stale_exit_count, regime_exit_count, wall_move_exit_count
        exit_price = exit_reference if maker else _adverse_market_price(
            exit_reference, current.side, execution.exit_slippage_bps
        )
        fee_bps = execution.maker_fee_bps if maker else execution.taker_fee_bps
        exit_fee = current.quantity * exit_price * fee_bps / 10_000.0
        gross_pnl = current.side * current.quantity * (exit_price - current.entry_price)
        cash += gross_pnl - exit_fee
        net_pnl = gross_pnl - current.entry_fee - exit_fee
        trade = {
            "entryTs": iso_time(current.entry_ts),
            "exitTs": iso_time(candle.ts),
            "side": "long" if current.side > 0 else "short",
            "entry": round(current.entry_price, 10),
            "exit": round(exit_price, 10),
            "quantity": round(current.quantity, 12),
            "barsHeld": max(0, (candle.ts - current.entry_ts) // BAR_MS),
            "reason": reason,
            "netPnl": round(net_pnl, 8),
            "returnPct": round(net_pnl / current.entry_equity * 100.0, 8),
            "entryEventTs": iso_time(current.entry_event_ts),
        }
        trades.append(trade)
        if maker:
            target_exits += 1
        else:
            risk_exits += 1
        if reason == "gex_expired":
            stale_exit_count += 1
        elif reason == "gamma_regime_exit":
            regime_exit_count += 1
        elif reason in {"wall_moved", "wall_missing"}:
            wall_move_exit_count += 1
        position = None

    for index, candle in enumerate(rows):
        open_price = _finite_price(candle.open)
        high = _finite_price(candle.high)
        low = _finite_price(candle.low)
        close = _finite_price(candle.close)
        if min(open_price, high, low, close) <= 0:
            equity_curve.append(cash)
            continue
        cutoff = candle.ts - max(0, execution.event_latency_bars) * BAR_MS
        event = latest_event_strictly_before(event_rows, cutoff)
        event_age = candle.ts - event.event_ts if event is not None else max_age_ms + 1
        fresh = event is not None and 0 <= event_age <= max_age_ms
        if fresh:
            fresh_gex_bars += 1
            if event.net_gex > 0:
                positive_gamma_bars += 1

        exited_this_bar = False
        if position is not None:
            bars_held = index - position.entry_index
            exit_reason = ""
            exit_reference = open_price
            maker_exit = False
            if not fresh:
                exit_reason = "gex_expired"
            elif event is None or event.net_gex <= 0:
                exit_reason = "gamma_regime_exit"
            elif event.put_wall <= 0 or event.call_wall <= 0:
                exit_reason = "wall_missing"
            elif event.event_ts != position.entry_event_ts and _wall_moved(
                position, event, execution.wall_move_exit_bps
            ):
                exit_reason = "wall_moved"
            elif bars_held >= candidate.max_hold_bars:
                exit_reason = "time_stop"
            elif position.side > 0:
                if low <= position.stop_price:
                    exit_reason = "stop_loss"
                    exit_reference = min(open_price, position.stop_price)
                elif high >= position.target_price:
                    exit_reason = "take_profit"
                    exit_reference = position.target_price
                    maker_exit = True
            else:
                if high >= position.stop_price:
                    exit_reason = "stop_loss"
                    exit_reference = max(open_price, position.stop_price)
                elif low <= position.target_price:
                    exit_reason = "take_profit"
                    exit_reference = position.target_price
                    maker_exit = True
            if exit_reason:
                close_position(
                    position,
                    candle,
                    exit_reference,
                    exit_reason,
                    maker=maker_exit,
                )
                exited_this_bar = True

        if position is None and not exited_this_bar and index > 0 and fresh and event is not None:
            previous_close = _finite_price(rows[index - 1].close)
            walls_valid = event.put_wall > 0 and event.call_wall > 0
            if event.net_gex > 0 and walls_valid and previous_close > 0:
                buy_limit, sell_limit = quote_limits(event, candidate)
                buy_distance = abs(event.put_wall / previous_close - 1.0) * 10_000.0
                sell_distance = abs(event.call_wall / previous_close - 1.0) * 10_000.0
                buy_eligible = (
                    buy_limit < previous_close
                    and buy_distance <= execution.max_wall_distance_bps
                )
                sell_eligible = (
                    sell_limit > previous_close
                    and sell_distance <= execution.max_wall_distance_bps
                )
                if buy_eligible or sell_eligible:
                    quote_bars += 1
                    eligible_quote_bars += 1
                    if math.isclose(event.put_wall, event.call_wall, rel_tol=0.0, abs_tol=1e-12):
                        single_pin_quote_bars += 1
                    penetration = execution.penetration_bps / 10_000.0
                    buy_touched = buy_eligible and low <= buy_limit * (1.0 - penetration)
                    sell_touched = sell_eligible and high >= sell_limit * (1.0 + penetration)
                    if buy_touched and sell_touched:
                        both_sides_touched += 1
                    elif buy_touched or sell_touched:
                        side = 1 if buy_touched else -1
                        entry = buy_limit if side > 0 else sell_limit
                        entry_equity = max(0.0, cash)
                        notional = entry_equity * execution.allocation_pct / 100.0
                        quantity = notional / entry if entry > 0 else 0.0
                        if quantity > 0:
                            entry_fee = quantity * entry * execution.maker_fee_bps / 10_000.0
                            cash -= entry_fee
                            anchor_wall = event.put_wall if side > 0 else event.call_wall
                            position = PinPosition(
                                side=side,
                                entry_price=entry,
                                quantity=quantity,
                                entry_ts=candle.ts,
                                entry_index=index,
                                entry_event_ts=event.event_ts,
                                anchor_wall=anchor_wall,
                                stop_price=entry * (1.0 - side * candidate.stop_loss_bps / 10_000.0),
                                target_price=entry * (1.0 + side * candidate.take_profit_bps / 10_000.0),
                                entry_fee=entry_fee,
                                entry_equity=entry_equity,
                            )
                            maker_entries += 1
                            # The order may fill before the adverse extreme of
                            # the candle.  Allow the stop, never the target, on
                            # the entry candle to avoid favorable sequencing.
                            same_bar_stop = (
                                side > 0 and low <= position.stop_price
                            ) or (
                                side < 0 and high >= position.stop_price
                            )
                            if same_bar_stop:
                                stop_reference = (
                                    min(open_price, position.stop_price)
                                    if side > 0
                                    else max(open_price, position.stop_price)
                                )
                                close_position(
                                    position,
                                    candle,
                                    stop_reference,
                                    "same_bar_stop",
                                    maker=False,
                                )

        marked_equity = cash
        if position is not None:
            marked_equity += position.side * position.quantity * (close - position.entry_price)
        equity_curve.append(marked_equity)

    if position is not None:
        final_candle = rows[-1]
        final_close = _finite_price(final_candle.close)
        close_position(position, final_candle, final_close, "terminal_exit", maker=False)
        equity_curve.append(cash)

    trade_returns = [float(trade["returnPct"]) for trade in trades]
    peak = execution.starting_equity
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak * 100.0)
    result = {
        "startingEquity": execution.starting_equity,
        "finalEquity": round(cash, 8),
        "returnPct": round((cash / execution.starting_equity - 1.0) * 100.0, 8),
        "maxDrawdownPct": round(max_drawdown, 8),
        "tradeCount": len(trades),
        "longTrades": sum(1 for trade in trades if trade["side"] == "long"),
        "shortTrades": sum(1 for trade in trades if trade["side"] == "short"),
        "winRatePct": round(
            sum(value > 0 for value in trade_returns) / len(trade_returns) * 100.0,
            6,
        ) if trade_returns else 0.0,
        "profitFactor": round(_profit_factor(trade_returns), 8),
        "expectancyBps": round(statistics.fmean(trade_returns) * 100.0, 8)
        if trade_returns else 0.0,
        "makerEntries": maker_entries,
        "targetExits": target_exits,
        "riskExits": risk_exits,
        "staleExits": stale_exit_count,
        "regimeExits": regime_exit_count,
        "wallMoveExits": wall_move_exit_count,
        "freshGexBars": fresh_gex_bars,
        "positiveGammaBars": positive_gamma_bars,
        "quoteBars": quote_bars,
        "eligibleQuoteBars": eligible_quote_bars,
        "singlePinQuoteBars": single_pin_quote_bars,
        "bothSidesTouched": both_sides_touched,
        "candleCount": len(rows),
        "trades": trades if record_details else [],
    }
    return result


def _empty_result(starting_equity: float) -> dict[str, Any]:
    return {
        "startingEquity": starting_equity,
        "finalEquity": starting_equity,
        "returnPct": 0.0,
        "maxDrawdownPct": 0.0,
        "tradeCount": 0,
        "longTrades": 0,
        "shortTrades": 0,
        "winRatePct": 0.0,
        "profitFactor": 0.0,
        "expectancyBps": 0.0,
        "makerEntries": 0,
        "targetExits": 0,
        "riskExits": 0,
        "staleExits": 0,
        "regimeExits": 0,
        "wallMoveExits": 0,
        "freshGexBars": 0,
        "positiveGammaBars": 0,
        "quoteBars": 0,
        "eligibleQuoteBars": 0,
        "singlePinQuoteBars": 0,
        "bothSidesTouched": 0,
        "candleCount": 0,
        "trades": [],
    }


def select_candidate(
    train_candles: dict[str, list[Candle]],
    events: dict[str, list[GexEvent]],
    execution: PinExecutionConfig,
    *,
    minimum_trades: int,
) -> tuple[PinCandidate, list[dict[str, Any]]]:
    scores: list[dict[str, Any]] = []
    stressed_execution = replace(
        execution,
        maker_fee_bps=5.0,
        taker_fee_bps=8.0,
        exit_slippage_bps=2.0,
        penetration_bps=2.0,
    )
    for candidate in candidate_grid():
        primary = {
            base: run_pin_backtest(train_candles[base], events[base], candidate, execution)
            for base in UNDERLYINGS
        }
        stressed = {
            base: run_pin_backtest(
                train_candles[base], events[base], candidate, stressed_execution
            )
            for base in UNDERLYINGS
        }
        primary_returns = [primary[base]["returnPct"] for base in UNDERLYINGS]
        stressed_returns = [stressed[base]["returnPct"] for base in UNDERLYINGS]
        counts = [primary[base]["tradeCount"] for base in UNDERLYINGS]
        worst_drawdown = max(
            result["maxDrawdownPct"]
            for table in (primary, stressed)
            for result in table.values()
        )
        score = (
            statistics.median(primary_returns)
            + statistics.median(stressed_returns)
            - 0.25 * worst_drawdown
        )
        scores.append(
            {
                "params": asdict(candidate),
                "score": round(score, 8),
                "eligible": min(counts) >= minimum_trades,
                "minimumInstrumentTrades": min(counts),
                "primaryMedianReturnPct": round(statistics.median(primary_returns), 8),
                "stressedMedianReturnPct": round(statistics.median(stressed_returns), 8),
                "worstDrawdownPct": round(worst_drawdown, 8),
                "instrumentResults": {
                    base: {
                        "primaryReturnPct": primary[base]["returnPct"],
                        "primaryTrades": primary[base]["tradeCount"],
                        "stressedReturnPct": stressed[base]["returnPct"],
                        "stressedTrades": stressed[base]["tradeCount"],
                    }
                    for base in UNDERLYINGS
                },
            }
        )
    scores.sort(
        key=lambda item: (
            bool(item["eligible"]),
            float(item["score"]),
            int(item["minimumInstrumentTrades"]),
        ),
        reverse=True,
    )
    selected = PinCandidate(**scores[0]["params"])
    return selected, scores


def result_row(
    base: str,
    segment: str,
    variant: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "underlying": base,
        "instId": f"{base}-USDT-SWAP",
        "segment": segment,
        "variant": variant,
        **{key: value for key, value in result.items() if key != "trades"},
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["segment"], row["variant"]), []).append(row)
    result = []
    for (segment, variant), items in sorted(grouped.items()):
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "instruments": len(items),
                "medianReturnPct": round(
                    statistics.median(item["returnPct"] for item in items), 8
                ),
                "worstReturnPct": round(min(item["returnPct"] for item in items), 8),
                "worstDrawdownPct": round(
                    max(item["maxDrawdownPct"] for item in items), 8
                ),
                "totalTrades": sum(item["tradeCount"] for item in items),
                "minimumInstrumentTrades": min(item["tradeCount"] for item in items),
                "positiveInstruments": sum(item["returnPct"] > 0 for item in items),
                "minimumProfitFactor": round(min(item["profitFactor"] for item in items), 8),
            }
        )
    return result


def family_oos_audit(
    segments: dict[str, dict[str, list[Candle]]],
    events: dict[str, list[GexEvent]],
    scores: list[dict[str, Any]],
    execution: PinExecutionConfig,
) -> dict[str, Any]:
    """Describe family robustness without changing the train-selected winner."""

    rows = []
    for score in scores:
        candidate = PinCandidate(**score["params"])
        segment_results: dict[str, dict[str, Any]] = {}
        for segment in ("validation", "test"):
            results = {
                base: run_pin_backtest(
                    segments[base][segment], events[base], candidate, execution
                )
                for base in UNDERLYINGS
            }
            segment_results[segment] = {
                "medianReturnPct": round(
                    statistics.median(results[base]["returnPct"] for base in UNDERLYINGS),
                    8,
                ),
                "minimumInstrumentTrades": min(
                    results[base]["tradeCount"] for base in UNDERLYINGS
                ),
                "instrumentReturns": {
                    base: results[base]["returnPct"] for base in UNDERLYINGS
                },
                "instrumentTrades": {
                    base: results[base]["tradeCount"] for base in UNDERLYINGS
                },
            }
        rows.append(
            {
                "params": score["params"],
                "trainingEligible": score["eligible"],
                **segment_results,
            }
        )
    eligible = [row for row in rows if row["trainingEligible"]]
    active = [
        row
        for row in eligible
        if row["validation"]["minimumInstrumentTrades"] >= 1
        and row["test"]["minimumInstrumentTrades"] >= 1
    ]
    return {
        "warning": (
            "Validation/test family inspection is descriptive only. It is not used to replace "
            "the training-selected parameters."
        ),
        "candidateCount": len(rows),
        "trainingEligibleCandidateCount": len(eligible),
        "eligibleWithBothOosActivity": len(active),
        "eligibleValidationPositiveMedianCount": sum(
            row["validation"]["medianReturnPct"] > 0 for row in eligible
        ),
        "eligibleTestPositiveMedianCount": sum(
            row["test"]["medianReturnPct"] > 0 for row in eligible
        ),
        "eligiblePositiveInBothCount": sum(
            row["validation"]["medianReturnPct"] > 0
            and row["test"]["medianReturnPct"] > 0
            for row in eligible
        ),
        "allTestPositiveMedianCount": sum(
            row["test"]["medianReturnPct"] > 0 for row in rows
        ),
        "rows": rows,
    }


def decision_payload(
    selected_score: dict[str, Any],
    rows: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    *,
    minimum_training_trades: int,
) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "primary")]
    test = lookup[("test", "primary")]
    stress = lookup[("test", "cost_stress")]
    latency = lookup[("test", "one_bar_latency")]
    test_rows = [
        row for row in rows if row["segment"] == "test" and row["variant"] == "primary"
    ]
    gates = {
        "trainingTradeCountEligible": bool(selected_score["eligible"]),
        "validationMedianPositive": validation["medianReturnPct"] > 0,
        "testMedianPositive": test["medianReturnPct"] > 0,
        "bothTestInstrumentsPositive": test["positiveInstruments"] == len(UNDERLYINGS),
        "bothTestProfitFactorsAboveOne": all(row["profitFactor"] > 1 for row in test_rows),
        "testCostStressPositive": stress["medianReturnPct"] > 0,
        "testLatencyPositive": latency["medianReturnPct"] > 0,
        "minimumThreeTestTradesPerInstrument": test["minimumInstrumentTrades"] >= 3,
    }
    quantitative_pass = all(gates.values())
    return {
        "status": "forward_validation_required" if quantitative_pass else "research_only",
        "quantitativeGatePassed": quantitative_pass,
        "gates": gates,
        "minimumTrainingTradesPerInstrument": minimum_training_trades,
        "barFillLimitation": (
            "5m OHLC cannot establish queue priority, cancellation latency, or whether a trade-through "
            "occurred after the resting order became active"
        ),
        "deploymentAllowed": False,
    }


def chronological_boundaries(start_ts: int, end_ts: int) -> tuple[int, int]:
    span = max(0, end_ts - start_ts)
    return start_ts + span // 2, start_ts + span * 3 // 4


def time_slice(candles: list[Candle], start_ts: int, end_ts: int) -> list[Candle]:
    return [candle for candle in candles if start_ts <= candle.ts <= end_ts]


def resolve_output_dir(value: str) -> Path:
    if value:
        return Path(value)
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    score = payload["selectedTrainingScore"]
    decision = payload["decision"]
    family = payload["familyOosAudit"]
    full_rows = {
        row["underlying"]: row
        for row in payload["rows"]
        if row["segment"] == "full" and row["variant"] == "primary"
    }
    lines = [
        "# BTC/ETH 期权关键价接针研究",
        "",
        f"生成时间：`{payload['generatedAt']}`",
        "",
        "## 结论",
        "",
        f"- 状态：`{decision['status']}`；实盘许可：`false`。",
        f"- 训练样本门槛：每标的至少 {decision['minimumTrainingTradesPerInstrument']} 笔；"
        f"所选参数最低标的成交 {score['minimumInstrumentTrades']} 笔，"
        f"门槛{'通过' if score['eligible'] else '未通过'}。",
        "- 即使数量与收益门槛通过，5 分钟 K 线也无法证明 maker 排队优先级，仍必须使用全新逐事件数据前向验证。",
        "",
        "## 冻结策略",
        "",
        "- 仅在点时 GEX 为正且未过期时挂单；负 Gamma 不逆势接针。",
        "- Put Wall 下方挂被动买单，Call Wall 上方挂被动卖单；同一 pin strike 则两侧对称挂单。",
        "- GEX 必须严格早于订单生效 K 线；价格需穿透限价；同根双边触发直接跳过。",
        "- 新仓同根不得止盈，但可按保守顺序触发止损；止盈止损同根时止损优先。",
        "- 单标的单仓、20% 权益、无杠杆；GEX 过期/转负/墙位移动时下一根开盘风险退出。",
        "",
        "## 训练锁定参数",
        "",
        f"- 墙外偏移：{selected['wall_offset_bps']:.1f} bps",
        f"- 止盈/止损：{selected['take_profit_bps']:.1f}/{selected['stop_loss_bps']:.1f} bps",
        f"- 最长持有：{selected['max_hold_bars']} 根 5 分钟 K 线",
        f"- GEX 最长年龄：{selected['max_gex_age_hours']:.1f} 小时",
        f"- 训练主成本/压力中位收益：{score['primaryMedianReturnPct']:.6f}% / "
        f"{score['stressedMedianReturnPct']:.6f}%",
        "",
        "## 参数族稳健性（仅诊断，不换参）",
        "",
        f"- 36 个候选中有 {family['trainingEligibleCandidateCount']} 个满足训练成交门槛；"
        f"其中验证中位为正 {family['eligibleValidationPositiveMedianCount']} 个，"
        f"测试中位为正 {family['eligibleTestPositiveMedianCount']} 个，"
        f"验证和测试同时为正 {family['eligiblePositiveInBothCount']} 个。",
        f"- 全部候选中虽有 {family['allTestPositiveMedianCount']} 个测试中位为正，"
        "但它们均未通过训练成交门槛，不能事后替换训练锁定参数。",
        "",
        "## 分段结果",
        "",
        "| 分段 | 版本 | 中位收益 | 最差收益 | 最差回撤 | 总成交 | 最低单标的成交 | 正收益标的 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    order = {"train": 0, "validation": 1, "test": 2, "full": 3}
    for item in sorted(
        payload["aggregates"], key=lambda row: (order.get(row["segment"], 9), row["variant"])
    ):
        lines.append(
            f"| {item['segment']} | {item['variant']} | {item['medianReturnPct']:.6f}% | "
            f"{item['worstReturnPct']:.6f}% | {item['worstDrawdownPct']:.6f}% | "
            f"{item['totalTrades']} | {item['minimumInstrumentTrades']} | "
            f"{item['positiveInstruments']}/{item['instruments']} |"
        )
    lines.extend(
        [
            "",
            "## 数据与限制",
            "",
            f"- 区间：{payload['period']['start']} 至 {payload['period']['end']}；按 50%/25%/25% 切分。",
            f"- GEX 事件数：{payload['eventCounts']}。事件时间取采集时间与期权源时间的较晚者。",
        ]
    )
    for base in UNDERLYINGS:
        row = full_rows[base]
        denominator = max(1, row["candleCount"])
        lines.append(
            f"- {base}：GEX 新鲜覆盖 {row['freshGexBars'] / denominator * 100:.2f}%，"
            f"正 Gamma 覆盖 {row['positiveGammaBars'] / denominator * 100:.2f}%，"
            f"实际可挂墙位覆盖 {row['quoteBars'] / denominator * 100:.2f}%。"
        )
    lines.extend(
        [
            "- GEX dealer 持仓方向是估算约定，不是交易所公布事实；墙位也可能随到期和持仓变化跳动。",
            "- 回测未模拟盘口队列、撤改单延迟、资金费和真实 tick/lot 约束；成本压力不能替代逐事件成交验证。",
            "",
            "## 决策门槛",
            "",
        ]
    )
    for name, passed in decision["gates"].items():
        lines.append(f"- `{name}`: `{'pass' if passed else 'fail'}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    events_all = load_crypto_gex_events(Path(args.gex_file))
    missing = set(UNDERLYINGS) - set(events_all)
    if missing:
        raise SystemExit(f"Missing point-in-time GEX history for {sorted(missing)}")
    events = {base: events_all[base] for base in UNDERLYINGS}
    candle_root = Path(args.candle_root)
    candles = {
        base: read_candles_csv(candle_root / f"{base}-USDT-SWAP_5m_300x48.csv")
        for base in UNDERLYINGS
    }
    maximum_age_ms = 6 * 60 * 60 * 1000
    common_start = max(events[base][0].event_ts for base in UNDERLYINGS)
    common_end = min(
        min(candles[base][-1].ts, events[base][-1].event_ts + maximum_age_ms)
        for base in UNDERLYINGS
    )
    if common_end <= common_start:
        raise SystemExit("GEX events and candles do not overlap")
    train_end, validation_end = chronological_boundaries(common_start, common_end)
    segments = {
        base: {
            "train": time_slice(candles[base], common_start, train_end),
            "validation": time_slice(candles[base], train_end + 1, validation_end),
            "test": time_slice(candles[base], validation_end + 1, common_end),
            "full": time_slice(candles[base], common_start, common_end),
        }
        for base in UNDERLYINGS
    }
    execution = PinExecutionConfig()
    selected, scores = select_candidate(
        {base: segments[base]["train"] for base in UNDERLYINGS},
        events,
        execution,
        minimum_trades=max(1, args.minimum_training_trades),
    )
    selected_score = scores[0]
    family_audit = family_oos_audit(segments, events, scores, execution)
    stressed = replace(
        execution,
        maker_fee_bps=5.0,
        taker_fee_bps=8.0,
        exit_slippage_bps=2.0,
        penetration_bps=2.0,
    )
    latency = replace(execution, event_latency_bars=1)
    rows: list[dict[str, Any]] = []
    trade_details: dict[str, list[dict[str, Any]]] = {}
    for base in UNDERLYINGS:
        for segment, segment_candles in segments[base].items():
            primary = run_pin_backtest(
                segment_candles, events[base], selected, execution, record_details=True
            )
            trade_details[f"{base}:{segment}:primary"] = primary["trades"]
            rows.append(result_row(base, segment, "primary", primary))
            if segment == "test":
                rows.append(
                    result_row(
                        base,
                        segment,
                        "cost_stress",
                        run_pin_backtest(segment_candles, events[base], selected, stressed),
                    )
                )
                rows.append(
                    result_row(
                        base,
                        segment,
                        "one_bar_latency",
                        run_pin_backtest(segment_candles, events[base], selected, latency),
                    )
                )
    aggregates = aggregate_rows(rows)
    decision = decision_payload(
        selected_score,
        rows,
        aggregates,
        minimum_training_trades=max(1, args.minimum_training_trades),
    )
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_point_in_time_positive_gex_passive_pin_catcher",
        "gexFile": str(Path(args.gex_file).resolve()),
        "candleRoot": str(candle_root.resolve()),
        "period": {
            "start": iso_time(common_start),
            "trainEnd": iso_time(train_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "eventCounts": {base: len(events[base]) for base in UNDERLYINGS},
        "candidateCount": len(scores),
        "execution": asdict(execution),
        "costStress": asdict(stressed),
        "selectedParameters": asdict(selected),
        "selectedTrainingScore": selected_score,
        "candidateScores": scores,
        "familyOosAudit": family_audit,
        "rows": rows,
        "aggregates": aggregates,
        "tradeDetails": trade_details,
        "decision": decision,
    }
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "candidate_scores.csv", scores)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={asdict(selected)} eligible={selected_score['eligible']}")
    for item in aggregates:
        if item["variant"] == "primary" or item["segment"] == "test":
            print(
                f"segment={item['segment']} variant={item['variant']} "
                f"median={item['medianReturnPct']:.6f}% trades={item['totalTrades']} "
                f"positive={item['positiveInstruments']}/{item['instruments']}"
            )
    print(f"decision={decision['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
