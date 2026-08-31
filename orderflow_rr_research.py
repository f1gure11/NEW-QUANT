from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_ROOT = PROJECT_ROOT / "data" / "microstructure"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "orderflow_rr"
DEFAULT_INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
FACTOR_FAMILIES = (
    "trade_flow_momentum",
    "trade_flow_reversal",
    "depth_imbalance_momentum",
    "depth_imbalance_reversal",
    "ofi_momentum",
    "ofi_reversal",
    "book_trade_consensus",
    "ofi_trade_consensus",
    "absorption_reversal",
)


@dataclass(frozen=True, slots=True)
class OrderFlowSnapshot:
    ts: int
    bid: float
    ask: float
    mid: float
    spread_bps: float
    book_imbalance: float
    trade_imbalance: float
    ofi: float
    open_interest: float = 0.0
    funding_rate: float = 0.0
    funding_premium: float = 0.0
    volume: float = 0.0
    bid_depth_5: float = 0.0
    ask_depth_5: float = 0.0
    bid_depth_10: float = 0.0
    ask_depth_10: float = 0.0


@dataclass(frozen=True, slots=True)
class StrategyCandidate:
    family: str
    threshold: float
    take_profit_bps: float
    stop_loss_bps: float
    max_hold_bars: int


@dataclass(slots=True)
class OrderFlowTrade:
    entry_ts: int
    exit_ts: int
    side: int
    signal_score: float
    entry_price: float
    exit_price: float
    exit_reason: str
    hold_bars: int
    net_pnl_bps: float
    mae_bps: float
    mfe_bps: float


@dataclass(slots=True)
class BacktestResult:
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    average_win_bps: float
    average_loss_bps: float
    payoff_ratio: float
    breakeven_win_rate_pct: float
    expectancy_bps: float
    profit_factor: float
    total_return_pct: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    tp_exits: int
    stop_exits: int
    time_exits: int
    gap_exits: int
    average_hold_bars: float
    average_mae_bps: float
    average_mfe_bps: float
    final_equity: float
    trade_rows: list[OrderFlowTrade]


@dataclass(slots=True)
class CandidateScore:
    params: StrategyCandidate
    score: float
    median_expectancy_bps: float
    worst_expectancy_bps: float
    median_profit_factor: float
    median_return_pct: float
    median_drawdown_pct: float
    median_trades: float
    positive_instruments: int
    instruments: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only order-flow strategy research with executable quotes and realized reward/risk."
    )
    parser.add_argument("--input-root", default=str(INPUT_ROOT))
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--allocation-pct", type=float, default=20.0)
    parser.add_argument("--fee-bps-per-side", type=float, default=5.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=1.0)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    parser.add_argument("--max-gap-seconds", type=float, default=180.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    snapshots = load_snapshot_history(Path(args.input_root), instruments)
    missing = [inst_id for inst_id in instruments if len(snapshots.get(inst_id, [])) < 100]
    if missing:
        raise SystemExit(f"Insufficient order-flow snapshots for {missing}")
    common_start = max(snapshots[inst_id][0].ts for inst_id in instruments)
    common_end = min(snapshots[inst_id][-1].ts for inst_id in instruments)
    train_end, validation_end = chronological_boundaries(common_start, common_end)
    segments = {
        inst_id: {
            "train": time_slice(rows, common_start, train_end),
            "validation": time_slice(rows, train_end + 1, validation_end),
            "test": time_slice(rows, validation_end + 1, common_end),
            "full": time_slice(rows, common_start, common_end),
        }
        for inst_id, rows in snapshots.items()
        if inst_id in instruments
    }
    simulation_kwargs = {
        "starting_equity": args.starting_equity,
        "allocation_pct": args.allocation_pct,
        "fee_bps_per_side": args.fee_bps_per_side,
        "slippage_bps_per_side": args.slippage_bps_per_side,
        "max_spread_bps": args.max_spread_bps,
        "max_gap_ms": int(args.max_gap_seconds * 1000),
    }
    candidate_scores = select_parameters(
        {inst_id: segments[inst_id]["train"] for inst_id in instruments},
        simulation_kwargs,
    )
    if not candidate_scores:
        raise SystemExit("No order-flow candidate generated enough training trades")
    selected = candidate_scores[0].params

    rows: list[dict[str, Any]] = []
    selected_test_trades: list[dict[str, Any]] = []
    for inst_id in instruments:
        for segment, segment_rows in segments[inst_id].items():
            simulation = simulate_strategy(
                segment_rows,
                selected,
                **simulation_kwargs,
                record_trades=segment == "test",
            )
            rows.append(result_row(inst_id, segment, "selected", selected, simulation))
            if segment == "test":
                selected_test_trades.extend(
                    trade_payload(inst_id, trade) for trade in simulation.trade_rows
                )

                stressed = simulate_strategy(
                    segment_rows,
                    selected,
                    **{
                        **simulation_kwargs,
                        "fee_bps_per_side": 8.0,
                        "slippage_bps_per_side": 2.0,
                    },
                )
                rows.append(result_row(inst_id, segment, "cost_stress", selected, stressed))

                latency = simulate_strategy(
                    segment_rows,
                    selected,
                    **simulation_kwargs,
                    latency_bars=1,
                )
                rows.append(result_row(inst_id, segment, "one_snapshot_latency", selected, latency))

                no_cost = simulate_strategy(
                    segment_rows,
                    selected,
                    **{
                        **simulation_kwargs,
                        "fee_bps_per_side": 0.0,
                        "slippage_bps_per_side": 0.0,
                    },
                )
                rows.append(result_row(inst_id, segment, "zero_cost_upper_bound", selected, no_cost))

                for side_filter, variant in ((1, "long_only"), (-1, "short_only")):
                    side_result = simulate_strategy(
                        segment_rows,
                        selected,
                        **simulation_kwargs,
                        side_filter=side_filter,
                    )
                    rows.append(result_row(inst_id, segment, variant, selected, side_result))

                for family, variant in (
                    ("depth_imbalance_momentum", "depth_only"),
                    ("trade_flow_momentum", "trade_only"),
                    ("ofi_momentum", "ofi_only"),
                ):
                    ablation = StrategyCandidate(
                        family,
                        selected.threshold,
                        selected.take_profit_bps,
                        selected.stop_loss_bps,
                        selected.max_hold_bars,
                    )
                    factor_result = simulate_strategy(
                        segment_rows,
                        ablation,
                        **simulation_kwargs,
                    )
                    rows.append(result_row(inst_id, segment, variant, ablation, factor_result))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, aggregates)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_orderflow_reward_risk_research",
        "instruments": list(instruments),
        "dataDefinition": {
            "source": "locally collected OKX public REST snapshots",
            "sampling": "approximately 65 seconds; each snapshot contains a book and the latest 100 trades",
            "limitation": "not a lossless websocket event stream; latency stress is mandatory",
        },
        "strategyDefinition": {
            "factors": "5/10-level depth imbalance, latest-trade imbalance, and normalized top-of-book OFI",
            "execution": "marketable bid/ask, per-side taker fee and adverse slippage",
            "positioning": "one position per instrument, fixed fraction of current equity, no leverage",
            "exit": "executable-quote take profit, stop loss, or maximum holding snapshots",
            "timing": "signals use only the current or earlier completed snapshot",
        },
        "config": {
            "startingEquity": args.starting_equity,
            "allocationPct": args.allocation_pct,
            "feeBpsPerSide": args.fee_bps_per_side,
            "slippageBpsPerSide": args.slippage_bps_per_side,
            "maxSpreadBps": args.max_spread_bps,
            "maxGapSeconds": args.max_gap_seconds,
        },
        "period": {
            "start": iso_time(common_start),
            "trainEnd": iso_time(train_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "sampleCounts": {
            inst_id: {segment: len(values) for segment, values in inst_segments.items()}
            for inst_id, inst_segments in segments.items()
        },
        "selectedParameters": asdict(selected),
        "candidateScores": [score_payload(item) for item in candidate_scores[:100]],
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "trades.csv", selected_test_trades)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={asdict(selected)}")
    print(f"decision={decision}")
    lookup = {(item['segment'], item['variant']): item for item in aggregates}
    for segment in ("train", "validation", "test", "full"):
        item = lookup[(segment, "selected")]
        print(
            f"segment={segment} median_return={item['median_return_pct']:.6f}% "
            f"median_expectancy={item['median_expectancy_bps']:.4f}bps "
            f"median_pf={item['median_profit_factor']:.4f}"
        )
    return 0


def load_snapshot_history(
    input_root: Path,
    instruments: Iterable[str],
) -> dict[str, list[OrderFlowSnapshot]]:
    result: dict[str, list[OrderFlowSnapshot]] = {}
    for inst_id in instruments:
        directory = input_root / safe_name(inst_id)
        snapshots: list[OrderFlowSnapshot] = []
        previous_book: tuple[float, float, float, float] | None = None
        previous_ts = -1
        for path in sorted(directory.glob("*.jsonl")):
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not row.get("ok") or str(row.get("instId") or "") != inst_id:
                        continue
                    parsed = parse_snapshot(row, previous_book)
                    if parsed is None or parsed.ts <= previous_ts:
                        continue
                    snapshots.append(parsed)
                    previous_ts = parsed.ts
                    previous_book = top_of_book(row)
        result[inst_id] = snapshots
    return result


def parse_snapshot(
    row: dict[str, Any],
    previous_book: tuple[float, float, float, float] | None,
) -> OrderFlowSnapshot | None:
    ts = integer_value(row.get("capturedTs"))
    bid, bid_size, ask, ask_size = top_of_book(row)
    if ts <= 0 or min(bid, ask, bid_size, ask_size) <= 0 or ask < bid:
        return None
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    book = features.get("book") if isinstance(features.get("book"), dict) else {}
    trades = features.get("trades") if isinstance(features.get("trades"), dict) else {}
    open_interest = row.get("openInterest") if isinstance(row.get("openInterest"), dict) else {}
    funding = row.get("funding") if isinstance(row.get("funding"), dict) else {}
    imbalance_5 = float_value(book.get("imbalance_5"))
    imbalance_10 = float_value(book.get("imbalance_10"))
    book_imbalance = clip((imbalance_5 + imbalance_10) / 2.0, -1.0, 1.0)
    trade_imbalance = clip(float_value(trades.get("imbalance")), -1.0, 1.0)
    mid = (bid + ask) / 2.0
    spread_bps = (ask - bid) / mid * 10_000.0 if mid > 0 else 0.0
    return OrderFlowSnapshot(
        ts=ts,
        bid=bid,
        ask=ask,
        mid=mid,
        spread_bps=spread_bps,
        book_imbalance=book_imbalance,
        trade_imbalance=trade_imbalance,
        ofi=normalized_ofi(previous_book, (bid, bid_size, ask, ask_size)),
        open_interest=float_value(open_interest.get("oi")),
        funding_rate=float_value(funding.get("fundingRate")),
        funding_premium=float_value(funding.get("premium")),
        volume=max(
            0.0,
            float_value(trades.get("buy_notional"))
            + float_value(trades.get("sell_notional")),
        ),
        bid_depth_5=max(0.0, float_value(book.get("bid_depth_5"))),
        ask_depth_5=max(0.0, float_value(book.get("ask_depth_5"))),
        bid_depth_10=max(0.0, float_value(book.get("bid_depth_10"))),
        ask_depth_10=max(0.0, float_value(book.get("ask_depth_10"))),
    )


def top_of_book(row: dict[str, Any]) -> tuple[float, float, float, float]:
    ticker = row.get("ticker") if isinstance(row.get("ticker"), dict) else {}
    book = row.get("book") if isinstance(row.get("book"), dict) else {}
    bids = book.get("bids") if isinstance(book.get("bids"), list) else []
    asks = book.get("asks") if isinstance(book.get("asks"), list) else []
    bid = float_value(ticker.get("bidPx")) or book_value(bids, 0, 0)
    ask = float_value(ticker.get("askPx")) or book_value(asks, 0, 0)
    bid_size = book_value(bids, 0, 1) or float_value(ticker.get("bidSz"))
    ask_size = book_value(asks, 0, 1) or float_value(ticker.get("askSz"))
    return bid, bid_size, ask, ask_size


def normalized_ofi(
    previous: tuple[float, float, float, float] | None,
    current: tuple[float, float, float, float],
) -> float:
    if previous is None:
        return 0.0
    previous_bid, previous_bid_size, previous_ask, previous_ask_size = previous
    bid, bid_size, ask, ask_size = current
    if bid > previous_bid:
        bid_event = bid_size
    elif bid == previous_bid:
        bid_event = bid_size - previous_bid_size
    else:
        bid_event = -previous_bid_size
    if ask < previous_ask:
        ask_event = ask_size
    elif ask == previous_ask:
        ask_event = ask_size - previous_ask_size
    else:
        ask_event = -previous_ask_size
    average_depth = (
        previous_bid_size + previous_ask_size + bid_size + ask_size
    ) / 2.0
    if average_depth <= 0:
        return 0.0
    return clip((bid_event - ask_event) / average_depth, -1.0, 1.0)


def factor_score(snapshot: OrderFlowSnapshot, family: str) -> float:
    book = snapshot.book_imbalance
    trade = snapshot.trade_imbalance
    ofi = snapshot.ofi
    if family == "trade_flow_momentum":
        return trade
    if family == "trade_flow_reversal":
        return -trade
    if family == "depth_imbalance_momentum":
        return book
    if family == "depth_imbalance_reversal":
        return -book
    if family == "ofi_momentum":
        return ofi
    if family == "ofi_reversal":
        return -ofi
    if family == "book_trade_consensus":
        return signed_consensus(book, trade)
    if family == "ofi_trade_consensus":
        return signed_consensus(ofi, trade)
    if family == "absorption_reversal":
        if book * trade < 0:
            return math.copysign(min(abs(book), abs(trade)), book)
        return 0.0
    raise ValueError(f"unknown factor family: {family}")


def signed_consensus(left: float, right: float) -> float:
    if left * right <= 0:
        return 0.0
    return math.copysign(min(abs(left), abs(right)), left)


def candidate_grid() -> list[StrategyCandidate]:
    exits = ((40.0, 15.0), (60.0, 20.0), (80.0, 25.0), (100.0, 30.0))
    return [
        StrategyCandidate(family, threshold, take_profit, stop_loss, hold)
        for family in FACTOR_FAMILIES
        for threshold in (0.20, 0.35, 0.50)
        for take_profit, stop_loss in exits
        for hold in (10, 20, 40, 60)
    ]


def select_parameters(
    training_rows: dict[str, list[OrderFlowSnapshot]],
    simulation_kwargs: dict[str, Any],
) -> list[CandidateScore]:
    scores = []
    for candidate in candidate_grid():
        results = [
            simulate_strategy(rows, candidate, **simulation_kwargs)
            for rows in training_rows.values()
        ]
        if not results or min(item.trades for item in results) < 40:
            continue
        expectancies = [item.expectancy_bps for item in results]
        returns = [item.total_return_pct for item in results]
        drawdowns = [item.max_drawdown_pct for item in results]
        profit_factors = [item.profit_factor for item in results]
        positive = sum(value > 0 for value in expectancies)
        median_expectancy = statistics.median(expectancies)
        worst_expectancy = min(expectancies)
        score = (
            median_expectancy
            + 0.75 * worst_expectancy
            - 0.25 * statistics.median(drawdowns)
            + 1.0 * (positive - len(results) / 2.0)
        )
        scores.append(
            CandidateScore(
                candidate,
                score,
                median_expectancy,
                worst_expectancy,
                statistics.median(profit_factors),
                statistics.median(returns),
                statistics.median(drawdowns),
                statistics.median(item.trades for item in results),
                positive,
                len(results),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def simulate_strategy(
    snapshots: list[OrderFlowSnapshot],
    candidate: StrategyCandidate,
    *,
    starting_equity: float = 100_000.0,
    allocation_pct: float = 20.0,
    fee_bps_per_side: float = 5.0,
    slippage_bps_per_side: float = 1.0,
    max_spread_bps: float = 1.0,
    max_gap_ms: int = 180_000,
    latency_bars: int = 0,
    side_filter: int = 0,
    record_trades: bool = False,
    active_predicate: Callable[[OrderFlowSnapshot], bool] | None = None,
) -> BacktestResult:
    if len(snapshots) < 2:
        return empty_result(starting_equity)
    if not 0 < allocation_pct <= 100:
        raise ValueError("allocation_pct must be in (0, 100]")
    if min(fee_bps_per_side, slippage_bps_per_side, max_spread_bps) < 0:
        raise ValueError("costs and spread cap cannot be negative")
    if latency_bars < 0:
        raise ValueError("latency_bars cannot be negative")
    fee_rate = fee_bps_per_side / 10_000.0
    slip_rate = slippage_bps_per_side / 10_000.0
    cash_equity = starting_equity
    peak_equity = starting_equity
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    trades: list[OrderFlowTrade] = []
    cooldown_until = -1

    def mark_equity(snapshot: OrderFlowSnapshot) -> float:
        if position is None:
            return cash_equity
        raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
        exit_price = raw_exit * (1.0 - slip_rate * position["side"])
        gross = position["side"] * (exit_price - position["entry_price"]) * position["units"]
        exit_fee = exit_price * position["units"] * fee_rate
        return cash_equity + gross - exit_fee

    def update_drawdown(snapshot: OrderFlowSnapshot) -> None:
        nonlocal peak_equity, max_drawdown
        equity = mark_equity(snapshot)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100.0)

    def close_position(index: int, reason: str) -> None:
        nonlocal position, cash_equity, cooldown_until
        if position is None:
            return
        snapshot = snapshots[index]
        raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
        exit_price = raw_exit * (1.0 - slip_rate * position["side"])
        gross = position["side"] * (exit_price - position["entry_price"]) * position["units"]
        exit_fee = exit_price * position["units"] * fee_rate
        cash_equity += gross - exit_fee
        net_pnl = gross - exit_fee - position["entry_fee"]
        net_bps = net_pnl / position["notional"] * 10_000.0
        trades.append(
            OrderFlowTrade(
                entry_ts=position["entry_ts"],
                exit_ts=snapshot.ts,
                side=position["side"],
                signal_score=position["signal_score"],
                entry_price=position["entry_price"],
                exit_price=exit_price,
                exit_reason=reason,
                hold_bars=index - position["entry_index"],
                net_pnl_bps=net_bps,
                mae_bps=position["mae_bps"],
                mfe_bps=position["mfe_bps"],
            )
        )
        position = None
        cooldown_until = index + 1

    for index, snapshot in enumerate(snapshots):
        previous_gap = snapshot.ts - snapshots[index - 1].ts if index > 0 else 0
        is_active = active_predicate(snapshot) if active_predicate is not None else True
        if position is not None:
            raw_exit = snapshot.bid if position["side"] > 0 else snapshot.ask
            gross_move_bps = (
                position["side"]
                * (raw_exit / position["entry_price"] - 1.0)
                * 10_000.0
            )
            position["mae_bps"] = min(position["mae_bps"], gross_move_bps)
            position["mfe_bps"] = max(position["mfe_bps"], gross_move_bps)
            reason = ""
            if not is_active:
                reason = "time_exit"
            elif index > position["entry_index"] and previous_gap > max_gap_ms:
                reason = "gap"
            elif gross_move_bps >= candidate.take_profit_bps:
                reason = "take_profit"
            elif gross_move_bps <= -candidate.stop_loss_bps:
                reason = "stop_loss"
            elif index - position["entry_index"] >= candidate.max_hold_bars:
                reason = "time_exit"
            if reason:
                close_position(index, reason)

        update_drawdown(snapshot)
        if (
            not is_active
            or position is not None
            or index >= len(snapshots) - 1
            or index < cooldown_until
        ):
            continue
        signal_index = index - latency_bars
        if signal_index < 0:
            continue
        signal_snapshot = snapshots[signal_index]
        if snapshot.ts - signal_snapshot.ts > max_gap_ms:
            continue
        if index > 0 and previous_gap > max_gap_ms:
            continue
        if snapshot.spread_bps > max_spread_bps:
            continue
        score = factor_score(signal_snapshot, candidate.family)
        side = 1 if score >= candidate.threshold else -1 if score <= -candidate.threshold else 0
        if side == 0 or (side_filter and side != side_filter):
            continue
        entry_price = snapshot.ask * (1.0 + slip_rate) if side > 0 else snapshot.bid * (1.0 - slip_rate)
        pre_entry_equity = cash_equity
        notional = pre_entry_equity * allocation_pct / 100.0
        if entry_price <= 0 or notional <= 0:
            continue
        entry_fee = notional * fee_rate
        cash_equity -= entry_fee
        position = {
            "side": side,
            "entry_index": index,
            "entry_ts": snapshot.ts,
            "entry_price": entry_price,
            "notional": notional,
            "units": notional / entry_price,
            "entry_fee": entry_fee,
            "signal_score": score,
            "mae_bps": 0.0,
            "mfe_bps": 0.0,
        }
        update_drawdown(snapshot)

    if position is not None:
        close_position(len(snapshots) - 1, "time_exit")
        update_drawdown(snapshots[-1])

    return summarize_trades(
        trades,
        starting_equity,
        cash_equity,
        max_drawdown,
        record_trades=record_trades,
    )


def summarize_trades(
    trades: list[OrderFlowTrade],
    starting_equity: float,
    final_equity: float,
    max_drawdown_pct: float,
    *,
    record_trades: bool,
) -> BacktestResult:
    wins = [trade.net_pnl_bps for trade in trades if trade.net_pnl_bps > 0]
    losses = [trade.net_pnl_bps for trade in trades if trade.net_pnl_bps <= 0]
    average_win = statistics.fmean(wins) if wins else 0.0
    average_loss = abs(statistics.fmean(losses)) if losses else 0.0
    payoff = average_win / average_loss if average_loss > 0 else (999.0 if average_win > 0 else 0.0)
    breakeven = 100.0 / (1.0 + payoff) if payoff > 0 else 100.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    consecutive = 0
    max_consecutive = 0
    for trade in trades:
        consecutive = 0 if trade.net_pnl_bps > 0 else consecutive + 1
        max_consecutive = max(max_consecutive, consecutive)
    return BacktestResult(
        trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=len(wins) / len(trades) * 100.0 if trades else 0.0,
        average_win_bps=average_win,
        average_loss_bps=average_loss,
        payoff_ratio=payoff,
        breakeven_win_rate_pct=breakeven,
        expectancy_bps=statistics.fmean(trade.net_pnl_bps for trade in trades) if trades else 0.0,
        profit_factor=profit_factor,
        total_return_pct=(final_equity / starting_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown_pct,
        max_consecutive_losses=max_consecutive,
        tp_exits=sum(trade.exit_reason == "take_profit" for trade in trades),
        stop_exits=sum(trade.exit_reason == "stop_loss" for trade in trades),
        time_exits=sum(trade.exit_reason == "time_exit" for trade in trades),
        gap_exits=sum(trade.exit_reason == "gap" for trade in trades),
        average_hold_bars=statistics.fmean(trade.hold_bars for trade in trades) if trades else 0.0,
        average_mae_bps=statistics.fmean(trade.mae_bps for trade in trades) if trades else 0.0,
        average_mfe_bps=statistics.fmean(trade.mfe_bps for trade in trades) if trades else 0.0,
        final_equity=final_equity,
        trade_rows=trades if record_trades else [],
    )


def empty_result(starting_equity: float) -> BacktestResult:
    return BacktestResult(
        0, 0, 0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, 0,
        0.0, 0.0, 0.0, starting_equity, [],
    )


def result_row(
    inst_id: str,
    segment: str,
    variant: str,
    candidate: StrategyCandidate,
    result: BacktestResult,
) -> dict[str, Any]:
    return {
        "inst_id": inst_id,
        "segment": segment,
        "variant": variant,
        "family": candidate.family,
        "threshold": candidate.threshold,
        "take_profit_bps": candidate.take_profit_bps,
        "stop_loss_bps": candidate.stop_loss_bps,
        "max_hold_bars": candidate.max_hold_bars,
        "trades": result.trades,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate_pct": result.win_rate_pct,
        "average_win_bps": result.average_win_bps,
        "average_loss_bps": result.average_loss_bps,
        "payoff_ratio": result.payoff_ratio,
        "breakeven_win_rate_pct": result.breakeven_win_rate_pct,
        "win_rate_edge_pct": result.win_rate_pct - result.breakeven_win_rate_pct,
        "expectancy_bps": result.expectancy_bps,
        "profit_factor": result.profit_factor,
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "max_consecutive_losses": result.max_consecutive_losses,
        "tp_exits": result.tp_exits,
        "stop_exits": result.stop_exits,
        "time_exits": result.time_exits,
        "gap_exits": result.gap_exits,
        "average_hold_bars": result.average_hold_bars,
        "average_mae_bps": result.average_mae_bps,
        "average_mfe_bps": result.average_mfe_bps,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["segment"], row["variant"]), []).append(row)
    result = []
    for (segment, variant), items in grouped.items():
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "count": len(items),
                "positive": sum(float(item["total_return_pct"]) > 0 for item in items),
                "median_return_pct": statistics.median(float(item["total_return_pct"]) for item in items),
                "worst_return_pct": min(float(item["total_return_pct"]) for item in items),
                "median_expectancy_bps": statistics.median(float(item["expectancy_bps"]) for item in items),
                "worst_expectancy_bps": min(float(item["expectancy_bps"]) for item in items),
                "median_win_rate_pct": statistics.median(float(item["win_rate_pct"]) for item in items),
                "median_payoff_ratio": statistics.median(float(item["payoff_ratio"]) for item in items),
                "median_profit_factor": statistics.median(float(item["profit_factor"]) for item in items),
                "worst_drawdown_pct": max(float(item["max_drawdown_pct"]) for item in items),
                "total_trades": sum(int(item["trades"]) for item in items),
            }
        )
    result.sort(key=lambda item: (item["segment"], item["variant"]))
    return result


def decision_payload(
    rows: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
) -> dict[str, Any]:
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    validation = lookup[("validation", "selected")]
    test = lookup[("test", "selected")]
    stress = lookup[("test", "cost_stress")]
    latency = lookup[("test", "one_snapshot_latency")]
    test_rows = [row for row in rows if row["segment"] == "test" and row["variant"] == "selected"]
    passing = (
        validation["median_return_pct"] > 0
        and validation["median_expectancy_bps"] > 0
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["profit_factor"]) >= 1.10 for row in test_rows)
        and all(float(row["win_rate_edge_pct"]) >= 2.0 for row in test_rows)
        and all(int(row["trades"]) >= 30 for row in test_rows)
        and test["worst_drawdown_pct"] <= 3.0
    )
    return {
        "status": "paper_candidate" if passing else "research_only",
        "rule": (
            "验证期望必须为正；BTC/ETH 在测试、成本压力和延迟一张快照时都必须盈利；测试 PF 不低于 1.10，"
            "实际胜率至少高于盈亏平衡胜率 2 个百分点，每个标的不少于30笔交易，最差回撤不超过3%。"
        ),
        "liveAuthorized": False,
    }


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    period = payload["period"]
    aggregates = payload["aggregates"]
    lookup = {(item["segment"], item["variant"]): item for item in aggregates}
    lines = [
        "# BTC/ETH 订单流胜率—盈亏比策略回测",
        "",
        "> 只读研究；聚合策略已放弃。本报告不读取账户、不启动服务、不发送订单。",
        "",
        "## 因子与执行",
        "",
        "- 因子：五档/十档深度失衡、最新100笔主动成交失衡，以及 Cont–Kukanov–Stoikov 风格的标准化顶层 OFI。",
        "- 信号只使用当时已经完成的快照；同一标的一次最多一个仓位，不叠加信号、不使用杠杆。",
        "- 多头按卖一、空头按买一开仓，退出使用可成交的买一/卖一；双边各计 Taker 费和不利滑点。",
        "- 约65秒一张 REST 快照并非无损 WebSocket 事件流，因此一分钟延迟测试是强制准入条件。",
        "",
        "## 文献依据",
        "",
        "- Cont, Kukanov and Stoikov (2014), `10.1093/jjfinec/nbt003`: order-flow imbalance 与短期价格冲击。",
        "- Gould and Bonart (2016), `10.1142/S2382626616500064`: queue imbalance 的短期价格预测信息。",
        "- Cartea, Donnelly and Jaimungal (2018), `10.1080/1350486X.2018.1434009`: 将订单簿信号纳入交易与执行控制。",
        "",
        "## 数据与训练选择",
        "",
        f"- 公共快照区间：`{period['start']}` 至 `{period['end']}`；前50%训练、随后25%验证、最后25%最终测试。",
        f"- 训练选择：`{selected['family']}`，阈值 {selected['threshold']:.2f}，止盈 {selected['take_profit_bps']:.0f} bps，止损 {selected['stop_loss_bps']:.0f} bps，最长持有 {selected['max_hold_bars']} 张快照。",
        "- 训练最优候选本身仍为负期望；它只是全部候选中损失最小的一组，不是合格策略。",
        f"- 基础成本：每边 {payload['config']['feeBpsPerSide']:.1f} bps Taker + {payload['config']['slippageBpsPerSide']:.1f} bps 滑点；每笔使用当前权益 {payload['config']['allocationPct']:.0f}%。",
        "",
        "## 主策略跨时间结果",
        "",
        "| 区间 | 正收益 | 中位收益 | 中位每笔期望 | 中位胜率 | 中位实际盈亏比 | 中位PF | 最差回撤 | 总交易 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for segment, label in (("train", "训练"), ("validation", "验证"), ("test", "测试"), ("full", "完整")):
        item = lookup[(segment, "selected")]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_win_rate_pct']:.2f}% | "
            f"{item['median_payoff_ratio']:.3f} | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['total_trades']} |"
        )
    lines.extend(
        [
            "",
            "## 最终测试压力与消融",
            "",
            "| 版本 | 正收益 | 中位收益 | 中位期望 | 中位胜率 | 中位盈亏比 | 中位PF | 最差回撤 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    variants = (
        ("selected", "主策略"),
        ("cost_stress", "成本压力"),
        ("one_snapshot_latency", "延迟一张快照"),
        ("zero_cost_upper_bound", "零成本理论上限"),
        ("long_only", "仅多头"),
        ("short_only", "仅空头"),
        ("depth_only", "深度失衡动量"),
        ("trade_only", "主动成交动量"),
        ("ofi_only", "OFI动量"),
    )
    for variant, label in variants:
        item = lookup[("test", variant)]
        lines.append(
            f"| {label} | {item['positive']}/{item['count']} | {item['median_return_pct']:.4f}% | "
            f"{item['median_expectancy_bps']:.3f} bps | {item['median_win_rate_pct']:.2f}% | "
            f"{item['median_payoff_ratio']:.3f} | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% |"
        )
    test_rows = [row for row in payload["rows"] if row["segment"] == "test" and row["variant"] == "selected"]
    lines.extend(
        [
            "",
            "## 最终测试逐标的胜率与盈亏比",
            "",
            "| 标的 | 交易 | 收益 | 胜率 | 平均盈利 | 平均亏损 | 实际盈亏比 | 盈亏平衡胜率 | 胜率优势 | 每笔期望 | PF | 最大连亏 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in test_rows:
        lines.append(
            f"| {row['inst_id']} | {row['trades']} | {row['total_return_pct']:.4f}% | "
            f"{row['win_rate_pct']:.2f}% | {row['average_win_bps']:.2f} bps | "
            f"{row['average_loss_bps']:.2f} bps | {row['payoff_ratio']:.3f} | "
            f"{row['breakeven_win_rate_pct']:.2f}% | {row['win_rate_edge_pct']:.2f} pct | "
            f"{row['expectancy_bps']:.3f} bps | {row['profit_factor']:.3f} | "
            f"{row['max_consecutive_losses']} |"
        )
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            f"- **{'可进入仿真候选' if decision['status'] == 'paper_candidate' else '仅研究'}**。",
            f"- 准入规则：{decision['rule']}",
            "- 即使通过也不授权实盘；必须先用 WebSocket 逐事件数据复现并完成仿真。",
        ]
    )
    return "\n".join(lines) + "\n"


def chronological_boundaries(start_ts: int, end_ts: int) -> tuple[int, int]:
    span = end_ts - start_ts
    return start_ts + int(span * 0.50), start_ts + int(span * 0.75)


def time_slice(
    rows: list[OrderFlowSnapshot],
    start_ts: int,
    end_ts: int,
) -> list[OrderFlowSnapshot]:
    return [row for row in rows if start_ts <= row.ts <= end_ts]


def score_payload(item: CandidateScore) -> dict[str, Any]:
    return {
        "params": asdict(item.params),
        **{key: value for key, value in asdict(item).items() if key != "params"},
    }


def trade_payload(inst_id: str, trade: OrderFlowTrade) -> dict[str, Any]:
    return {
        "inst_id": inst_id,
        "entry": iso_time(trade.entry_ts),
        "exit": iso_time(trade.exit_ts),
        "side": "long" if trade.side > 0 else "short",
        "signal_score": trade.signal_score,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "exit_reason": trade.exit_reason,
        "hold_bars": trade.hold_bars,
        "net_pnl_bps": trade.net_pnl_bps,
        "mae_bps": trade.mae_bps,
        "mfe_bps": trade.mfe_bps,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_name(value: str) -> str:
    return "_".join(part for part in value.lower().replace("-", "_").split("_") if part)


def book_value(rows: list[Any], row_index: int, column_index: int) -> float:
    try:
        return float(rows[row_index][column_index])
    except (IndexError, TypeError, ValueError):
        return 0.0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def integer_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def clip(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def iso_time(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
