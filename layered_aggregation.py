from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from backtest.okx_grid_backtest import Candle
from funding_research import FundingPoint


@dataclass(frozen=True, slots=True)
class LayeredConfig:
    """Configuration for a long-only layered inventory strategy.

    ``allocation_pct`` is margin as a percentage of starting equity and
    ``leverage`` converts it to maximum notional.  Every layer receives the
    same quote-currency notional; its contract quantity is rounded down to the
    exchange lot size.
    """

    starting_equity: float = 100.0
    allocation_pct: float = 60.0
    leverage: float = 1.0
    tranches: int = 6
    step_bps: float = 100.0
    take_profit_bps: float = 30.0
    basket_stop_bps: float = 800.0
    cooldown_bars: int = 12
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    stop_slippage_bps: float = 2.0
    fill_buffer_bps: float = 1.0
    lot_size: float = 0.001
    min_size: float = 0.001
    contract_value: float = 1.0
    tick_size: float = 0.01
    direction: str = "long"


@dataclass(slots=True)
class LayerLot:
    level: int
    entry_price: float
    quantity: float
    entry_ts: int


@dataclass(slots=True)
class LayerFill:
    ts: int
    action: str
    level: int
    price: float
    quantity: float
    gross_pnl: float
    fee: float
    funding: float
    equity: float


@dataclass(slots=True)
class LayeredResult:
    config: dict[str, Any]
    bars: int
    start_ts: int
    end_ts: int
    starting_equity: float
    final_mark_equity: float
    final_liquidation_equity: float
    return_pct: float
    mark_return_pct: float
    max_drawdown_pct: float
    min_equity: float
    realized_pnl: float
    realized_harvest: float
    stop_pnl: float
    terminal_unrealized: float
    fees: float
    funding_cost: float
    entries: int
    round_trips: int
    stop_events: int
    reanchors: int
    max_active_layers: int
    terminal_active_layers: int
    average_exposure_pct: float
    max_exposure_pct: float
    turnover: float
    price_return_pct: float
    buy_hold_return_pct: float
    insolvent: bool


@dataclass(slots=True)
class LayeredSimulation:
    result: LayeredResult
    fills: list[LayerFill]
    equity_curve: list[dict[str, Any]]


def validate_config(config: LayeredConfig) -> None:
    if config.starting_equity <= 0:
        raise ValueError("starting_equity must be positive")
    if config.tranches <= 0:
        raise ValueError("tranches must be positive")
    if not 0 < config.allocation_pct <= 100:
        raise ValueError("allocation_pct must be in (0, 100]")
    if config.leverage <= 0:
        raise ValueError("leverage must be positive")
    if not 0 < config.step_bps < 10_000:
        raise ValueError("step_bps must be in (0, 10000)")
    if config.take_profit_bps <= 0:
        raise ValueError("take_profit_bps must be positive")
    if config.lot_size <= 0 or config.min_size <= 0 or config.contract_value <= 0 or config.tick_size <= 0:
        raise ValueError("contract metadata must be positive")
    if config.direction not in {"long", "short"}:
        raise ValueError("direction must be long or short")


def layer_prices(anchor: float, config: LayeredConfig) -> list[float]:
    if config.direction == "long":
        step = 1.0 - config.step_bps / 10_000.0
        return [round_price_down(anchor * step**level, config.tick_size) for level in range(config.tranches)]
    step = 1.0 + config.step_bps / 10_000.0
    return [round_price_up(anchor * step**level, config.tick_size) for level in range(config.tranches)]


def layer_exit_price(lot: LayerLot, prices: list[float], config: LayeredConfig) -> float:
    if config.direction == "long":
        fixed_target = round_price_up(
            lot.entry_price * (1.0 + config.take_profit_bps / 10_000.0),
            config.tick_size,
        )
        if lot.level <= 0:
            return fixed_target
        return min(fixed_target, prices[lot.level - 1])
    fixed_target = round_price_down(
        lot.entry_price * (1.0 - config.take_profit_bps / 10_000.0),
        config.tick_size,
    )
    if lot.level <= 0:
        return fixed_target
    return max(fixed_target, prices[lot.level - 1])


def round_price_down(price: float, tick_size: float) -> float:
    return math.floor((price + 1e-12) / tick_size) * tick_size


def round_price_up(price: float, tick_size: float) -> float:
    return math.ceil((price - 1e-12) / tick_size) * tick_size


def round_quantity_down(quantity: float, lot_size: float, min_size: float) -> float:
    if quantity <= 0 or lot_size <= 0:
        return 0.0
    units = math.floor((quantity + 1e-12) / lot_size)
    rounded = units * lot_size
    return rounded if rounded + 1e-12 >= min_size else 0.0


def position_snapshot(
    lots: dict[int, LayerLot],
    mark: float,
    contract_value: float,
    direction: str = "long",
) -> tuple[float, float, float]:
    sign = 1.0 if direction == "long" else -1.0
    quantity = sum(lot.quantity for lot in lots.values())
    notional = sum(lot.quantity * mark * contract_value for lot in lots.values())
    unrealized = sum(sign * (mark - lot.entry_price) * lot.quantity * contract_value for lot in lots.values())
    return quantity, notional, unrealized


def weighted_entry(lots: dict[int, LayerLot]) -> float:
    quantity = sum(lot.quantity for lot in lots.values())
    if quantity <= 0:
        return 0.0
    return sum(lot.entry_price * lot.quantity for lot in lots.values()) / quantity


def simulate_layered_strategy(
    candles: list[Candle],
    config: LayeredConfig,
    funding: Iterable[FundingPoint] = (),
    *,
    record_details: bool = True,
) -> LayeredSimulation:
    """Simulate the strategy without same-bar entry/TP round trips.

    Orders for the initial ladder are formed from the first completed close.
    Existing stop orders are resolved first (the adverse intrabar assumption),
    then existing take-profit orders, then resting entries.  A newly filled
    entry can hit its basket stop on the same bar but cannot take profit until
    a later bar.  This intentionally avoids the common OHLC-grid optimism.
    """

    validate_config(config)
    if len(candles) < 2:
        raise ValueError("at least two candles are required")

    funding_points = sorted(funding, key=lambda item: item.ts)
    funding_index = 0
    while funding_index < len(funding_points) and funding_points[funding_index].ts <= candles[0].ts:
        funding_index += 1

    anchor = float(candles[0].close)
    prices = layer_prices(anchor, config)
    lots: dict[int, LayerLot] = {}
    fills: list[LayerFill] = []
    curve: list[dict[str, Any]] = []
    cash_equity = config.starting_equity
    realized_pnl = 0.0
    realized_harvest = 0.0
    stop_pnl = 0.0
    fees = 0.0
    funding_cost = 0.0
    entries = 0
    round_trips = 0
    stop_events = 0
    reanchors = 0
    max_active_layers = 0
    max_exposure_pct = 0.0
    exposure_sum = 0.0
    turnover = 0.0
    cooldown = 0
    insolvent = False
    peak_equity = config.starting_equity
    min_equity = config.starting_equity
    max_drawdown_pct = 0.0
    maker_rate = config.maker_fee_bps / 10_000.0
    taker_rate = config.taker_fee_bps / 10_000.0
    stop_slip = config.stop_slippage_bps / 10_000.0
    fill_buffer = config.fill_buffer_bps / 10_000.0
    layer_notional = (
        config.starting_equity
        * config.allocation_pct
        / 100.0
        * config.leverage
        / config.tranches
    )
    direction_sign = 1.0 if config.direction == "long" else -1.0

    def account_equity(mark: float) -> float:
        return cash_equity + position_snapshot(lots, mark, config.contract_value, config.direction)[2]

    def append_fill(
        ts: int,
        action: str,
        level: int,
        price: float,
        quantity: float,
        gross_pnl: float,
        fee: float,
        funding_payment: float = 0.0,
    ) -> None:
        if not record_details:
            return
        fills.append(
            LayerFill(
                ts=ts,
                action=action,
                level=level,
                price=price,
                quantity=quantity,
                gross_pnl=gross_pnl,
                fee=fee,
                funding=funding_payment,
                equity=account_equity(price),
            )
        )

    def stop_all(candle: Candle, trigger_price: float) -> None:
        nonlocal cash_equity, fees, realized_pnl, stop_pnl, turnover, stop_events, cooldown
        if not lots:
            return
        open_price = float(candle.open)
        if config.direction == "long":
            fill_price = min(trigger_price, open_price) * (1.0 - stop_slip)
        else:
            fill_price = max(trigger_price, open_price) * (1.0 + stop_slip)
        for level in sorted(list(lots)):
            lot = lots.pop(level)
            gross = direction_sign * (fill_price - lot.entry_price) * lot.quantity * config.contract_value
            notional = fill_price * lot.quantity * config.contract_value
            fee = notional * taker_rate
            realized_pnl += gross
            stop_pnl += gross
            fees += fee
            cash_equity += gross - fee
            turnover += notional
            append_fill(candle.ts, "basket_stop", level, fill_price, lot.quantity, gross, fee)
        stop_events += 1
        cooldown = max(0, config.cooldown_bars)

    for index in range(1, len(candles)):
        candle = candles[index]
        prior_ts = candles[index - 1].ts
        was_cooling = cooldown > 0

        while funding_index < len(funding_points) and funding_points[funding_index].ts <= candle.ts:
            point = funding_points[funding_index]
            if point.ts > prior_ts and lots:
                rate = point.realized_rate or point.rate
                _, event_notional, _ = position_snapshot(lots, float(candle.open), config.contract_value, config.direction)
                payment = direction_sign * event_notional * rate
                funding_cost += payment
                cash_equity -= payment
                append_fill(candle.ts, "funding", -1, float(candle.open), 0.0, 0.0, 0.0, payment)
            funding_index += 1

        stopped = False
        if lots and config.basket_stop_bps > 0:
            if config.direction == "long":
                trigger = weighted_entry(lots) * (1.0 - config.basket_stop_bps / 10_000.0)
                stop_touched = float(candle.low) <= trigger
            else:
                trigger = weighted_entry(lots) * (1.0 + config.basket_stop_bps / 10_000.0)
                stop_touched = float(candle.high) >= trigger
            if stop_touched:
                stop_all(candle, trigger)
                stopped = True

        exited_levels: set[int] = set()
        if not stopped:
            existing_levels = sorted(lots)
            for level in existing_levels:
                lot = lots.get(level)
                if lot is None:
                    continue
                target = layer_exit_price(lot, prices, config)
                if config.direction == "long":
                    target_touched = float(candle.high) >= target * (1.0 + fill_buffer)
                else:
                    target_touched = float(candle.low) <= target * (1.0 - fill_buffer)
                if not target_touched:
                    continue
                gross = direction_sign * (target - lot.entry_price) * lot.quantity * config.contract_value
                notional = target * lot.quantity * config.contract_value
                fee = notional * maker_rate
                realized_pnl += gross
                realized_harvest += gross
                fees += fee
                cash_equity += gross - fee
                turnover += notional
                round_trips += 1
                exited_levels.add(level)
                lots.pop(level)
                append_fill(candle.ts, "take_profit", level, target, lot.quantity, gross, fee)

            if cooldown > 0:
                cooldown -= 1
            elif not insolvent:
                for level, entry_price in enumerate(prices):
                    if level in lots or level in exited_levels:
                        continue
                    if config.direction == "long":
                        entry_touched = float(candle.low) <= entry_price * (1.0 - fill_buffer)
                    else:
                        entry_touched = float(candle.high) >= entry_price * (1.0 + fill_buffer)
                    if not entry_touched:
                        continue
                    current_equity = max(0.0, account_equity(entry_price))
                    _, current_notional, _ = position_snapshot(lots, entry_price, config.contract_value, config.direction)
                    max_notional = current_equity * config.allocation_pct / 100.0 * config.leverage
                    available_notional = max(0.0, max_notional - current_notional)
                    entry_notional = min(layer_notional, available_notional)
                    raw_quantity = entry_notional / (entry_price * config.contract_value)
                    quantity = round_quantity_down(raw_quantity, config.lot_size, config.min_size)
                    if quantity <= 0:
                        continue
                    fee = entry_price * quantity * config.contract_value * maker_rate
                    lots[level] = LayerLot(level, entry_price, quantity, candle.ts)
                    fees += fee
                    cash_equity -= fee
                    entries += 1
                    turnover += entry_price * quantity * config.contract_value
                    append_fill(candle.ts, "entry", level, entry_price, quantity, 0.0, fee)

                if lots and config.basket_stop_bps > 0:
                    if config.direction == "long":
                        trigger = weighted_entry(lots) * (1.0 - config.basket_stop_bps / 10_000.0)
                        stop_touched = float(candle.low) <= trigger
                    else:
                        trigger = weighted_entry(lots) * (1.0 + config.basket_stop_bps / 10_000.0)
                        stop_touched = float(candle.high) >= trigger
                    if stop_touched:
                        stop_all(candle, trigger)
                        stopped = True

        if exited_levels and not lots and not stopped:
            anchor = float(candle.close)
            prices = layer_prices(anchor, config)
            reanchors += 1
        elif stopped and cooldown == 0:
            anchor = float(candle.close)
            prices = layer_prices(anchor, config)
            reanchors += 1
        elif was_cooling and not lots and cooldown == 0:
            anchor = float(candle.close)
            prices = layer_prices(anchor, config)
            reanchors += 1

        mark = float(candle.close)
        _, exposure, unrealized = position_snapshot(lots, mark, config.contract_value, config.direction)
        equity = cash_equity + unrealized
        if equity <= 0:
            insolvent = True
        peak_equity = max(peak_equity, equity)
        min_equity = min(min_equity, equity)
        if peak_equity > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak_equity - equity) / peak_equity * 100.0)
        exposure_pct = exposure / config.starting_equity * 100.0
        exposure_sum += exposure_pct
        max_exposure_pct = max(max_exposure_pct, exposure_pct)
        max_active_layers = max(max_active_layers, len(lots))
        if record_details:
            curve.append(
                {
                    "ts": candle.ts,
                    "close": mark,
                    "equity": equity,
                    "cash_equity": cash_equity,
                    "unrealized": unrealized,
                    "active_layers": len(lots),
                    "exposure": exposure,
                    "exposure_pct": exposure_pct,
                    "anchor": anchor,
                    "cooldown": cooldown,
                }
            )

    final_mark = float(candles[-1].close)
    _, final_notional, terminal_unrealized = position_snapshot(lots, final_mark, config.contract_value, config.direction)
    final_mark_equity = cash_equity + terminal_unrealized
    liquidation_cost = final_notional * (taker_rate + stop_slip)
    final_liquidation_equity = final_mark_equity - liquidation_cost
    price_return_pct = (final_mark / float(candles[0].close) - 1.0) * 100.0
    buy_hold_notional = config.starting_equity * config.allocation_pct / 100.0 * config.leverage
    buy_hold_pnl = direction_sign * buy_hold_notional * price_return_pct / 100.0
    buy_hold_cost = buy_hold_notional * maker_rate + max(0.0, buy_hold_notional * (1.0 + price_return_pct / 100.0)) * (taker_rate + stop_slip)
    buy_hold_return_pct = (buy_hold_pnl - buy_hold_cost) / config.starting_equity * 100.0

    result = LayeredResult(
        config=asdict(config),
        bars=len(candles),
        start_ts=candles[0].ts,
        end_ts=candles[-1].ts,
        starting_equity=config.starting_equity,
        final_mark_equity=final_mark_equity,
        final_liquidation_equity=final_liquidation_equity,
        return_pct=(final_liquidation_equity / config.starting_equity - 1.0) * 100.0,
        mark_return_pct=(final_mark_equity / config.starting_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown_pct,
        min_equity=min_equity,
        realized_pnl=realized_pnl,
        realized_harvest=realized_harvest,
        stop_pnl=stop_pnl,
        terminal_unrealized=terminal_unrealized,
        fees=fees,
        funding_cost=funding_cost,
        entries=entries,
        round_trips=round_trips,
        stop_events=stop_events,
        reanchors=reanchors,
        max_active_layers=max_active_layers,
        terminal_active_layers=len(lots),
        average_exposure_pct=exposure_sum / max(1, len(candles) - 1),
        max_exposure_pct=max_exposure_pct,
        turnover=turnover,
        price_return_pct=price_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        insolvent=insolvent,
    )
    return LayeredSimulation(result=result, fills=fills, equity_curve=curve)


def break_even_take_profit_bps(maker_fee_bps: float, extra_round_trip_bps: float = 0.0) -> float:
    """Exact TP threshold for a fixed-notional maker round trip.

    Gross lot profit is ``N*t`` while entry and exit fees are
    ``N*f + N*(1+t)*f``.  ``extra_round_trip_bps`` can represent expected
    queue loss, spread leakage, or other round-trip costs.
    """

    fee = max(0.0, maker_fee_bps) / 10_000.0
    extra = max(0.0, extra_round_trip_bps) / 10_000.0
    if fee >= 1.0:
        return math.inf
    threshold = (2.0 * fee + extra) / (1.0 - fee)
    return threshold * 10_000.0
