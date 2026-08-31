from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from backtest.okx_grid_backtest import Candle
from funding_research import FundingPoint
from layered_aggregation import round_price_down, round_price_up, round_quantity_down


@dataclass(frozen=True, slots=True)
class DualAggregationConfig:
    """Two independent aggregation books sharing one marked-to-market account.

    ``allocation_pct * leverage`` is the maximum *combined* gross notional as
    a fraction of current equity.  Half of that budget is reserved for each
    direction so that leverage is not silently doubled by hedge mode.
    """

    starting_equity: float = 200.0
    allocation_pct: float = 60.0
    leverage: float = 1.0
    tranches_per_side: int = 6
    step_bps: float = 200.0
    take_profit_bps: float = 60.0
    side_stop_bps: float = 900.0
    cooldown_bars: int = 12
    account_stop_pct: float = 0.0
    max_abs_net_exposure_pct: float = 0.0
    inventory_timeout_bars: int = 0
    basket_pair_start_bars: int = 0
    basket_pair_min_net_bps: float = 0.0
    staged_reduction_start_bars: int = 0
    staged_reduction_interval_bars: int = 0
    staged_reduction_fraction_pct: float = 0.0
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    liquidation_slippage_bps: float = 2.0
    fill_buffer_bps: float = 1.0
    maintenance_margin_pct: float = 1.5
    lot_size: float = 0.001
    min_size: float = 0.001
    contract_value: float = 1.0
    tick_size: float = 0.01


@dataclass(slots=True)
class DualLot:
    level: int
    entry_price: float
    quantity: float
    entry_ts: int
    reduction_stage: int = 0
    entry_fee: float = 0.0


@dataclass(slots=True)
class BookState:
    direction: str
    anchor: float
    prices: list[float]
    lots: dict[int, DualLot]
    cooldown: int = 0
    reanchors: int = 0
    pending_reanchor: bool = False


@dataclass(slots=True)
class DualFill:
    ts: int
    direction: str
    action: str
    level: int
    price: float
    quantity: float
    gross_pnl: float
    fee: float
    equity: float


@dataclass(slots=True)
class DualAggregationResult:
    config: dict[str, Any]
    bars: int
    start_ts: int
    end_ts: int
    starting_equity: float
    final_mark_equity: float
    final_liquidation_equity: float
    return_pct: float
    max_drawdown_pct: float
    min_equity: float
    realized_pnl: float
    realized_harvest: float
    stop_pnl: float
    terminal_unrealized: float
    fees: float
    funding_cost: float
    entries: int
    long_entries: int
    short_entries: int
    round_trips: int
    long_round_trips: int
    short_round_trips: int
    side_stop_events: int
    inventory_expiries: int
    basket_pair_events: int
    simultaneous_pair_events: int
    harvest_budget_exit_events: int
    basket_paired_quantity: float
    basket_pair_gross_pnl: float
    harvest_budget_exit_gross_pnl: float
    harvest_exit_credit_remaining: float
    staged_reduction_events: int
    staged_reduction_gross_pnl: float
    reanchors: int
    terminal_long_layers: int
    terminal_short_layers: int
    terminal_long_average: float
    terminal_short_average: float
    max_gross_exposure_pct: float
    max_abs_net_exposure_pct: float
    average_gross_exposure_pct: float
    turnover: float
    price_return_pct: float
    path_variation_pct: float
    path_efficiency_ratio: float
    liquidated: bool
    account_stopped: bool


@dataclass(slots=True)
class DualAggregationSimulation:
    result: DualAggregationResult
    fills: list[DualFill]
    equity_curve: list[dict[str, Any]]


def validate_config(config: DualAggregationConfig) -> None:
    if config.starting_equity <= 0:
        raise ValueError("starting_equity must be positive")
    if not 0 < config.allocation_pct <= 100:
        raise ValueError("allocation_pct must be in (0, 100]")
    if config.leverage <= 0:
        raise ValueError("leverage must be positive")
    if config.tranches_per_side <= 0:
        raise ValueError("tranches_per_side must be positive")
    if not 0 < config.step_bps < 10_000:
        raise ValueError("step_bps must be in (0, 10000)")
    if config.take_profit_bps <= 0:
        raise ValueError("take_profit_bps must be positive")
    if config.maintenance_margin_pct < 0:
        raise ValueError("maintenance_margin_pct cannot be negative")
    if config.max_abs_net_exposure_pct < 0:
        raise ValueError("max_abs_net_exposure_pct cannot be negative")
    if config.inventory_timeout_bars < 0:
        raise ValueError("inventory_timeout_bars cannot be negative")
    if config.basket_pair_start_bars < 0:
        raise ValueError("basket_pair_start_bars cannot be negative")
    if config.basket_pair_min_net_bps < 0:
        raise ValueError("basket_pair_min_net_bps cannot be negative")
    if config.staged_reduction_start_bars < 0:
        raise ValueError("staged_reduction_start_bars cannot be negative")
    if config.staged_reduction_interval_bars < 0:
        raise ValueError("staged_reduction_interval_bars cannot be negative")
    if not 0 <= config.staged_reduction_fraction_pct < 100:
        raise ValueError("staged_reduction_fraction_pct must be in [0, 100)")
    staged_enabled = config.staged_reduction_start_bars > 0
    if staged_enabled and (
        config.staged_reduction_interval_bars <= 0
        or config.staged_reduction_fraction_pct <= 0
    ):
        raise ValueError("enabled staged reduction requires a positive interval and fraction")
    if staged_enabled and (
        config.inventory_timeout_bars <= config.staged_reduction_start_bars
    ):
        raise ValueError("staged reduction must begin before inventory expiry")
    if min(config.lot_size, config.min_size, config.contract_value, config.tick_size) <= 0:
        raise ValueError("contract metadata must be positive")


def book_prices(anchor: float, direction: str, config: DualAggregationConfig) -> list[float]:
    if direction == "long":
        step = 1.0 - config.step_bps / 10_000.0
        return [round_price_down(anchor * step**level, config.tick_size) for level in range(config.tranches_per_side)]
    if direction == "short":
        step = 1.0 + config.step_bps / 10_000.0
        return [round_price_up(anchor * step**level, config.tick_size) for level in range(config.tranches_per_side)]
    raise ValueError("direction must be long or short")


def exit_price(lot: DualLot, book: BookState, config: DualAggregationConfig) -> float:
    if book.direction == "long":
        fixed = round_price_up(lot.entry_price * (1.0 + config.take_profit_bps / 10_000.0), config.tick_size)
        return fixed if lot.level == 0 else min(fixed, book.prices[lot.level - 1])
    fixed = round_price_down(lot.entry_price * (1.0 - config.take_profit_bps / 10_000.0), config.tick_size)
    return fixed if lot.level == 0 else max(fixed, book.prices[lot.level - 1])


def book_snapshot(
    lots: dict[int, DualLot], mark: float, contract_value: float, direction: str
) -> tuple[float, float, float]:
    sign = 1.0 if direction == "long" else -1.0
    quantity = sum(lot.quantity for lot in lots.values())
    notional = quantity * mark * contract_value
    unrealized = sum(sign * (mark - lot.entry_price) * lot.quantity * contract_value for lot in lots.values())
    return quantity, notional, unrealized


def portfolio_snapshot(
    long_lots: dict[int, DualLot],
    short_lots: dict[int, DualLot],
    mark: float,
    contract_value: float,
) -> tuple[float, float, float, float, float]:
    long_quantity, long_notional, long_unrealized = book_snapshot(long_lots, mark, contract_value, "long")
    short_quantity, short_notional, short_unrealized = book_snapshot(short_lots, mark, contract_value, "short")
    return (
        long_quantity,
        short_quantity,
        long_notional + short_notional,
        (long_quantity - short_quantity) * mark * contract_value,
        long_unrealized + short_unrealized,
    )


def weighted_entry(lots: dict[int, DualLot]) -> float:
    quantity = sum(lot.quantity for lot in lots.values())
    if quantity <= 0:
        return 0.0
    return sum(lot.entry_price * lot.quantity for lot in lots.values()) / quantity


def path_statistics(candles: list[Candle]) -> tuple[float, float]:
    log_returns = [
        math.log(float(current.close) / float(previous.close))
        for previous, current in zip(candles, candles[1:])
        if float(previous.close) > 0 and float(current.close) > 0
    ]
    variation = sum(abs(value) for value in log_returns)
    displacement = abs(sum(log_returns))
    efficiency = displacement / variation if variation > 0 else 0.0
    return variation * 100.0, efficiency


def simulate_dual_aggregation(
    candles: list[Candle],
    config: DualAggregationConfig,
    funding: Iterable[FundingPoint] = (),
    *,
    record_details: bool = True,
    entry_enabled_by_ts: Mapping[int, bool] | None = None,
) -> DualAggregationSimulation:
    """Run symmetric long/short aggregation with a shared equity ledger.

    Stops and maintenance margin are checked at adverse candle extremes before
    profitable exits.  Existing take-profits are handled before resting entry
    orders, and a newly opened lot cannot take profit in that same candle.
    """

    validate_config(config)
    if len(candles) < 2:
        raise ValueError("at least two candles are required")

    initial_anchor = float(candles[0].close)
    books = {
        direction: BookState(direction, initial_anchor, book_prices(initial_anchor, direction, config), {})
        for direction in ("long", "short")
    }
    funding_points = sorted(funding, key=lambda item: item.ts)
    funding_index = 0
    while funding_index < len(funding_points) and funding_points[funding_index].ts <= candles[0].ts:
        funding_index += 1

    cash_equity = config.starting_equity
    realized_pnl = 0.0
    realized_harvest = 0.0
    stop_pnl = 0.0
    fees = 0.0
    funding_cost = 0.0
    entries = 0
    entries_by_side = {"long": 0, "short": 0}
    trips_by_side = {"long": 0, "short": 0}
    side_stop_events = 0
    inventory_expiries = 0
    basket_pair_events = 0
    simultaneous_pair_events = 0
    harvest_budget_exit_events = 0
    basket_paired_quantity = 0.0
    basket_pair_gross_pnl = 0.0
    harvest_budget_exit_gross_pnl = 0.0
    harvest_exit_credit = 0.0
    staged_reduction_events = 0
    staged_reduction_gross_pnl = 0.0
    turnover = 0.0
    fills: list[DualFill] = []
    curve: list[dict[str, Any]] = []
    peak_equity = config.starting_equity
    min_equity = config.starting_equity
    max_drawdown_pct = 0.0
    max_gross_exposure_pct = 0.0
    max_abs_net_exposure_pct = 0.0
    gross_exposure_sum = 0.0
    liquidated = False
    account_stopped = False
    maker_rate = config.maker_fee_bps / 10_000.0
    taker_rate = config.taker_fee_bps / 10_000.0
    liquidation_slip = config.liquidation_slippage_bps / 10_000.0
    fill_buffer = config.fill_buffer_bps / 10_000.0
    layer_notional = (
        config.starting_equity
        * config.allocation_pct
        / 100.0
        * config.leverage
        / (2.0 * config.tranches_per_side)
    )
    positive_intervals = [
        current.ts - previous.ts
        for previous, current in zip(candles, candles[1:])
        if current.ts > previous.ts
    ]
    bar_ms = min(positive_intervals) if positive_intervals else 0
    inventory_timeout_ms = config.inventory_timeout_bars * bar_ms
    basket_pair_start_ms = config.basket_pair_start_bars * bar_ms
    staged_reduction_start_ms = config.staged_reduction_start_bars * bar_ms
    staged_reduction_interval_ms = config.staged_reduction_interval_bars * bar_ms

    def snapshot(mark: float) -> tuple[float, float, float, float, float]:
        return portfolio_snapshot(
            books["long"].lots,
            books["short"].lots,
            mark,
            config.contract_value,
        )

    def account_equity(mark: float) -> float:
        return cash_equity + snapshot(mark)[4]

    def append_fill(
        ts: int,
        direction: str,
        action: str,
        level: int,
        price: float,
        quantity: float,
        gross_pnl: float,
        fee: float,
    ) -> None:
        if record_details:
            fills.append(
                DualFill(ts, direction, action, level, price, quantity, gross_pnl, fee, account_equity(price))
            )

    def close_book(book: BookState, candle: Candle, mark: float, action: str) -> None:
        nonlocal cash_equity, realized_pnl, realized_harvest, stop_pnl, fees, turnover
        sign = 1.0 if book.direction == "long" else -1.0
        fill_price = mark * (1.0 - liquidation_slip) if book.direction == "long" else mark * (1.0 + liquidation_slip)
        for level in sorted(list(book.lots)):
            lot = book.lots.pop(level)
            gross = sign * (fill_price - lot.entry_price) * lot.quantity * config.contract_value
            notional = fill_price * lot.quantity * config.contract_value
            fee = notional * taker_rate
            cash_equity += gross - fee
            realized_pnl += gross
            if action == "take_profit":
                realized_harvest += gross
            else:
                stop_pnl += gross
            fees += fee
            turnover += notional
            append_fill(candle.ts, book.direction, action, level, fill_price, lot.quantity, gross, fee)

    def projected_risk_close(
        book: BookState,
        lot: DualLot,
        mark: float,
        quantity: float,
    ) -> tuple[float, float, float, float]:
        sign = 1.0 if book.direction == "long" else -1.0
        fill_price = (
            mark * (1.0 - liquidation_slip)
            if book.direction == "long"
            else mark * (1.0 + liquidation_slip)
        )
        gross = sign * (fill_price - lot.entry_price) * quantity * config.contract_value
        fee = fill_price * quantity * config.contract_value * taker_rate
        entry_fee_share = lot.entry_fee * quantity / lot.quantity if lot.quantity > 0 else 0.0
        return fill_price, gross, fee, entry_fee_share

    def close_lot_quantity(
        book: BookState,
        candle: Candle,
        level: int,
        mark: float,
        action: str,
        quantity: float,
    ) -> tuple[float, float, float, float]:
        nonlocal cash_equity, realized_pnl, stop_pnl, fees, turnover
        lot = book.lots[level]
        closed_quantity = min(lot.quantity, max(0.0, quantity))
        if closed_quantity <= 0:
            return 0.0, 0.0, 0.0, 0.0
        fill_price, gross, fee, entry_fee_share = projected_risk_close(
            book, lot, mark, closed_quantity
        )
        notional = fill_price * closed_quantity * config.contract_value
        if closed_quantity >= lot.quantity - 1e-12:
            book.lots.pop(level)
        else:
            lot.quantity -= closed_quantity
            lot.entry_fee = max(0.0, lot.entry_fee - entry_fee_share)
        cash_equity += gross - fee
        realized_pnl += gross
        stop_pnl += gross
        fees += fee
        turnover += notional
        append_fill(candle.ts, book.direction, action, level, fill_price, closed_quantity, gross, fee)
        return closed_quantity, gross, fee, entry_fee_share

    def close_lot(book: BookState, candle: Candle, level: int, mark: float, action: str) -> None:
        close_lot_quantity(book, candle, level, mark, action, book.lots[level].quantity)

    def adverse_margin_mark(candle: Candle) -> tuple[float, float, float]:
        candidates = []
        for mark in (float(candle.low), float(candle.high)):
            _, _, gross, _, unrealized = snapshot(mark)
            equity = cash_equity + unrealized
            maintenance = gross * config.maintenance_margin_pct / 100.0
            candidates.append((equity - maintenance, mark, equity))
        _, mark, equity = min(candidates, key=lambda item: item[0])
        gross = snapshot(mark)[2]
        return mark, equity, gross

    def close_account(candle: Candle, mark: float, action: str) -> None:
        close_book(books["long"], candle, mark, action)
        close_book(books["short"], candle, mark, action)

    def account_risk_triggered(candle: Candle) -> bool:
        nonlocal liquidated, account_stopped
        if not books["long"].lots and not books["short"].lots:
            return False
        mark, equity, gross = adverse_margin_mark(candle)
        if equity <= gross * config.maintenance_margin_pct / 100.0:
            close_account(candle, mark, "liquidation")
            liquidated = True
            return True
        stop_equity = config.starting_equity * (1.0 - config.account_stop_pct / 100.0)
        if config.account_stop_pct > 0 and equity <= stop_equity:
            close_account(candle, mark, "account_stop")
            account_stopped = True
            return True
        return False

    for index in range(1, len(candles)):
        candle = candles[index]
        prior_ts = candles[index - 1].ts

        while funding_index < len(funding_points) and funding_points[funding_index].ts <= candle.ts:
            point = funding_points[funding_index]
            if point.ts > prior_ts:
                rate = point.realized_rate or point.rate
                long_notional = book_snapshot(
                    books["long"].lots, float(candle.open), config.contract_value, "long"
                )[1]
                short_notional = book_snapshot(
                    books["short"].lots, float(candle.open), config.contract_value, "short"
                )[1]
                payment = (long_notional - short_notional) * rate
                funding_cost += payment
                cash_equity -= payment
            funding_index += 1

        if not liquidated and not account_stopped:
            account_risk_triggered(candle)

        stopped_sides: set[str] = set()
        if not liquidated and not account_stopped:
            for direction in ("long", "short"):
                book = books[direction]
                if not book.lots or config.side_stop_bps <= 0:
                    continue
                average = weighted_entry(book.lots)
                if direction == "long":
                    trigger = average * (1.0 - config.side_stop_bps / 10_000.0)
                    touched = float(candle.low) <= trigger
                else:
                    trigger = average * (1.0 + config.side_stop_bps / 10_000.0)
                    touched = float(candle.high) >= trigger
                if touched:
                    close_book(book, candle, trigger, "side_stop")
                    book.cooldown = max(0, config.cooldown_bars)
                    book.pending_reanchor = True
                    side_stop_events += 1
                    stopped_sides.add(direction)

        risk_exit_sides: set[str] = set()
        if not liquidated and not account_stopped and basket_pair_start_ms > 0:
            while books["long"].lots and books["short"].lots:
                pair_candidates: list[tuple[int, float, int, int, float]] = []
                open_mark = float(candle.open)
                for long_level, long_lot in books["long"].lots.items():
                    for short_level, short_lot in books["short"].lots.items():
                        oldest_age = max(
                            candle.ts - long_lot.entry_ts,
                            candle.ts - short_lot.entry_ts,
                        )
                        if oldest_age < basket_pair_start_ms:
                            continue
                        quantity = min(long_lot.quantity, short_lot.quantity)
                        if quantity <= 0:
                            continue
                        _, long_gross, long_fee, long_entry_fee = projected_risk_close(
                            books["long"], long_lot, open_mark, quantity
                        )
                        _, short_gross, short_fee, short_entry_fee = projected_risk_close(
                            books["short"], short_lot, open_mark, quantity
                        )
                        exit_notional = 2.0 * open_mark * quantity * config.contract_value
                        required_net = exit_notional * config.basket_pair_min_net_bps / 10_000.0
                        net_pnl = (
                            long_gross
                            + short_gross
                            - long_fee
                            - short_fee
                            - long_entry_fee
                            - short_entry_fee
                        )
                        if net_pnl + 1e-12 >= required_net:
                            pair_candidates.append(
                                (oldest_age, net_pnl, long_level, short_level, quantity)
                            )
                if not pair_candidates:
                    break
                _, _, long_level, short_level, quantity = max(
                    pair_candidates,
                    key=lambda item: (item[0], item[1]),
                )
                long_closed, long_gross, long_fee, long_entry_fee = close_lot_quantity(
                    books["long"],
                    candle,
                    long_level,
                    open_mark,
                    "basket_pair",
                    quantity,
                )
                short_closed, short_gross, short_fee, short_entry_fee = close_lot_quantity(
                    books["short"],
                    candle,
                    short_level,
                    open_mark,
                    "basket_pair",
                    quantity,
                )
                paired_quantity = min(long_closed, short_closed)
                if paired_quantity <= 0:
                    break
                basket_pair_events += 1
                simultaneous_pair_events += 1
                basket_paired_quantity += paired_quantity
                basket_pair_gross_pnl += long_gross + short_gross
                harvest_exit_credit += max(
                    0.0,
                    long_gross
                    + short_gross
                    - long_fee
                    - short_fee
                    - long_entry_fee
                    - short_entry_fee,
                )
                risk_exit_sides.update(("long", "short"))
                for direction in ("long", "short"):
                    if not books[direction].lots:
                        books[direction].pending_reanchor = True

            while harvest_exit_credit > 0:
                open_mark = float(candle.open)
                _, _, _, current_net, _ = snapshot(open_mark)
                if abs(current_net) <= 1e-12:
                    break
                risk_direction = "long" if current_net > 0 else "short"
                book = books[risk_direction]
                credit_candidates: list[tuple[int, float, int, float]] = []
                for level, lot in book.lots.items():
                    age = candle.ts - lot.entry_ts
                    if age < basket_pair_start_ms:
                        continue
                    _, gross, fee, entry_fee_share = projected_risk_close(
                        book,
                        lot,
                        open_mark,
                        lot.quantity,
                    )
                    exit_net_pnl = gross - fee - entry_fee_share
                    close_notional = open_mark * lot.quantity * config.contract_value
                    direction_sign = 1.0 if risk_direction == "long" else -1.0
                    post_exit_net = current_net - direction_sign * close_notional
                    if abs(post_exit_net) > abs(current_net) + 1e-12:
                        continue
                    required_credit = (
                        close_notional * config.basket_pair_min_net_bps / 10_000.0
                    )
                    if harvest_exit_credit + exit_net_pnl + 1e-12 < required_credit:
                        continue
                    credit_candidates.append((age, exit_net_pnl, level, lot.quantity))
                if not credit_candidates:
                    break
                _, exit_net_pnl, level, quantity = max(
                    credit_candidates,
                    key=lambda item: (item[0], item[1]),
                )
                closed, gross, fee, entry_fee_share = close_lot_quantity(
                    book,
                    candle,
                    level,
                    open_mark,
                    "harvest_budget_exit",
                    quantity,
                )
                if closed <= 0:
                    break
                harvest_exit_credit = max(
                    0.0,
                    harvest_exit_credit + gross - fee - entry_fee_share,
                )
                basket_pair_events += 1
                harvest_budget_exit_events += 1
                basket_paired_quantity += closed
                basket_pair_gross_pnl += gross
                harvest_budget_exit_gross_pnl += gross
                risk_exit_sides.add(risk_direction)
                if not book.lots:
                    book.pending_reanchor = True

        if (
            not liquidated
            and not account_stopped
            and staged_reduction_start_ms > 0
            and staged_reduction_interval_ms > 0
        ):
            for direction in ("long", "short"):
                book = books[direction]
                for level in sorted(list(book.lots)):
                    lot = book.lots.get(level)
                    if lot is None:
                        continue
                    age = candle.ts - lot.entry_ts
                    if age < staged_reduction_start_ms:
                        continue
                    if inventory_timeout_ms > 0 and age >= inventory_timeout_ms:
                        continue
                    due_stage = 1 + (age - staged_reduction_start_ms) // staged_reduction_interval_ms
                    if lot.reduction_stage >= due_stage:
                        continue
                    lot.reduction_stage = int(due_stage)
                    reduction_quantity = round_quantity_down(
                        lot.quantity * config.staged_reduction_fraction_pct / 100.0,
                        config.lot_size,
                        config.min_size,
                    )
                    if reduction_quantity <= 0 or reduction_quantity >= lot.quantity - 1e-12:
                        continue
                    closed, gross, _, _ = close_lot_quantity(
                        book,
                        candle,
                        level,
                        float(candle.open),
                        "staged_reduction",
                        reduction_quantity,
                    )
                    if closed > 0:
                        staged_reduction_events += 1
                        staged_reduction_gross_pnl += gross
                        risk_exit_sides.add(direction)
                if not book.lots and direction in risk_exit_sides:
                    book.pending_reanchor = True

        if not liquidated and not account_stopped and inventory_timeout_ms > 0:
            for direction in ("long", "short"):
                book = books[direction]
                expired = [
                    level
                    for level, lot in book.lots.items()
                    if candle.ts - lot.entry_ts >= inventory_timeout_ms
                ]
                for level in sorted(expired):
                    close_lot(book, candle, level, float(candle.open), "inventory_expiry")
                    inventory_expiries += 1
                if expired:
                    risk_exit_sides.add(direction)
                    if not book.lots:
                        book.pending_reanchor = True

        exited_levels: dict[str, set[int]] = {"long": set(), "short": set()}
        if not liquidated and not account_stopped:
            for direction in ("long", "short"):
                book = books[direction]
                if direction in stopped_sides:
                    continue
                sign = 1.0 if direction == "long" else -1.0
                for level in sorted(list(book.lots)):
                    lot = book.lots.get(level)
                    if lot is None:
                        continue
                    target = exit_price(lot, book, config)
                    touched = (
                        float(candle.high) >= target * (1.0 + fill_buffer)
                        if direction == "long"
                        else float(candle.low) <= target * (1.0 - fill_buffer)
                    )
                    if not touched:
                        continue
                    gross = sign * (target - lot.entry_price) * lot.quantity * config.contract_value
                    notional = target * lot.quantity * config.contract_value
                    fee = notional * maker_rate
                    book.lots.pop(level)
                    cash_equity += gross - fee
                    realized_pnl += gross
                    realized_harvest += gross
                    harvest_exit_credit += max(0.0, gross - fee - lot.entry_fee)
                    fees += fee
                    turnover += notional
                    trips_by_side[direction] += 1
                    exited_levels[direction].add(level)
                    append_fill(candle.ts, direction, "take_profit", level, target, lot.quantity, gross, fee)

            for direction in ("long", "short"):
                book = books[direction]
                if direction in stopped_sides:
                    continue
                entries_enabled = (
                    entry_enabled_by_ts is None
                    or bool(entry_enabled_by_ts.get(candle.ts, False))
                )
                if not entries_enabled or direction in risk_exit_sides:
                    continue
                if book.cooldown > 0:
                    continue
                for level, entry_price in enumerate(book.prices):
                    if level in book.lots or level in exited_levels[direction]:
                        continue
                    touched = (
                        float(candle.low) <= entry_price * (1.0 - fill_buffer)
                        if direction == "long"
                        else float(candle.high) >= entry_price * (1.0 + fill_buffer)
                    )
                    if not touched:
                        continue
                    current_equity = max(0.0, account_equity(entry_price))
                    _, side_notional, _ = book_snapshot(
                        book.lots, entry_price, config.contract_value, direction
                    )
                    _, _, gross_notional, net_notional, _ = snapshot(entry_price)
                    max_gross = current_equity * config.allocation_pct / 100.0 * config.leverage
                    available_limits = [max_gross / 2.0 - side_notional, max_gross - gross_notional]
                    if config.max_abs_net_exposure_pct > 0:
                        direction_sign = 1.0 if direction == "long" else -1.0
                        max_abs_net = current_equity * config.max_abs_net_exposure_pct / 100.0
                        available_limits.append(max_abs_net - direction_sign * net_notional)
                    available = min(available_limits)
                    entry_notional = min(layer_notional, max(0.0, available))
                    quantity = round_quantity_down(
                        entry_notional / (entry_price * config.contract_value),
                        config.lot_size,
                        config.min_size,
                    )
                    if quantity <= 0:
                        continue
                    fee = entry_price * quantity * config.contract_value * maker_rate
                    book.lots[level] = DualLot(
                        level,
                        entry_price,
                        quantity,
                        candle.ts,
                        entry_fee=fee,
                    )
                    cash_equity -= fee
                    fees += fee
                    turnover += entry_price * quantity * config.contract_value
                    entries += 1
                    entries_by_side[direction] += 1
                    append_fill(candle.ts, direction, "entry", level, entry_price, quantity, 0.0, fee)

            if not account_risk_triggered(candle):
                for direction in ("long", "short"):
                    book = books[direction]
                    if not book.lots or config.side_stop_bps <= 0 or direction in stopped_sides:
                        continue
                    average = weighted_entry(book.lots)
                    if direction == "long":
                        trigger = average * (1.0 - config.side_stop_bps / 10_000.0)
                        touched = float(candle.low) <= trigger
                    else:
                        trigger = average * (1.0 + config.side_stop_bps / 10_000.0)
                        touched = float(candle.high) >= trigger
                    if touched:
                        close_book(book, candle, trigger, "side_stop")
                        book.cooldown = max(0, config.cooldown_bars)
                        book.pending_reanchor = True
                        side_stop_events += 1
                        stopped_sides.add(direction)

        for direction in ("long", "short"):
            book = books[direction]
            if book.lots:
                continue
            if book.cooldown > 0:
                book.cooldown -= 1
                if book.cooldown > 0:
                    continue
            should_reanchor = bool(exited_levels[direction]) or book.pending_reanchor
            if should_reanchor and not liquidated and not account_stopped:
                book.anchor = float(candle.close)
                book.prices = book_prices(book.anchor, direction, config)
                book.reanchors += 1
                book.pending_reanchor = False

        mark = float(candle.close)
        _, _, gross, net, unrealized = snapshot(mark)
        equity = cash_equity + unrealized
        peak_equity = max(peak_equity, equity)
        min_equity = min(min_equity, equity)
        if peak_equity > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak_equity - equity) / peak_equity * 100.0)
        gross_pct = gross / config.starting_equity * 100.0
        net_pct = abs(net) / config.starting_equity * 100.0
        gross_exposure_sum += gross_pct
        max_gross_exposure_pct = max(max_gross_exposure_pct, gross_pct)
        max_abs_net_exposure_pct = max(max_abs_net_exposure_pct, net_pct)
        if record_details:
            curve.append(
                {
                    "ts": candle.ts,
                    "close": mark,
                    "equity": equity,
                    "cash_equity": cash_equity,
                    "unrealized": unrealized,
                    "long_layers": len(books["long"].lots),
                    "short_layers": len(books["short"].lots),
                    "long_average": weighted_entry(books["long"].lots),
                    "short_average": weighted_entry(books["short"].lots),
                    "gross_exposure_pct": gross_pct,
                    "net_exposure_pct": net / config.starting_equity * 100.0,
                }
            )

    final_mark = float(candles[-1].close)
    _, _, final_gross, _, terminal_unrealized = snapshot(final_mark)
    final_mark_equity = cash_equity + terminal_unrealized
    terminal_cost = final_gross * (taker_rate + liquidation_slip)
    final_liquidation_equity = final_mark_equity - terminal_cost
    price_return_pct = (final_mark / float(candles[0].close) - 1.0) * 100.0
    variation_pct, efficiency_ratio = path_statistics(candles)
    result = DualAggregationResult(
        config=asdict(config),
        bars=len(candles),
        start_ts=candles[0].ts,
        end_ts=candles[-1].ts,
        starting_equity=config.starting_equity,
        final_mark_equity=final_mark_equity,
        final_liquidation_equity=final_liquidation_equity,
        return_pct=(final_liquidation_equity / config.starting_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown_pct,
        min_equity=min_equity,
        realized_pnl=realized_pnl,
        realized_harvest=realized_harvest,
        stop_pnl=stop_pnl,
        terminal_unrealized=terminal_unrealized,
        fees=fees,
        funding_cost=funding_cost,
        entries=entries,
        long_entries=entries_by_side["long"],
        short_entries=entries_by_side["short"],
        round_trips=trips_by_side["long"] + trips_by_side["short"],
        long_round_trips=trips_by_side["long"],
        short_round_trips=trips_by_side["short"],
        side_stop_events=side_stop_events,
        inventory_expiries=inventory_expiries,
        basket_pair_events=basket_pair_events,
        simultaneous_pair_events=simultaneous_pair_events,
        harvest_budget_exit_events=harvest_budget_exit_events,
        basket_paired_quantity=basket_paired_quantity,
        basket_pair_gross_pnl=basket_pair_gross_pnl,
        harvest_budget_exit_gross_pnl=harvest_budget_exit_gross_pnl,
        harvest_exit_credit_remaining=harvest_exit_credit,
        staged_reduction_events=staged_reduction_events,
        staged_reduction_gross_pnl=staged_reduction_gross_pnl,
        reanchors=books["long"].reanchors + books["short"].reanchors,
        terminal_long_layers=len(books["long"].lots),
        terminal_short_layers=len(books["short"].lots),
        terminal_long_average=weighted_entry(books["long"].lots),
        terminal_short_average=weighted_entry(books["short"].lots),
        max_gross_exposure_pct=max_gross_exposure_pct,
        max_abs_net_exposure_pct=max_abs_net_exposure_pct,
        average_gross_exposure_pct=gross_exposure_sum / max(1, len(candles) - 1),
        turnover=turnover,
        price_return_pct=price_return_pct,
        path_variation_pct=variation_pct,
        path_efficiency_ratio=efficiency_ratio,
        liquidated=liquidated,
        account_stopped=account_stopped,
    )
    return DualAggregationSimulation(result, fills, curve)
