from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from backtest.okx_grid_backtest import Candle
from funding_research import FundingPoint
from layered_aggregation import round_price_down, round_price_up, round_quantity_down


@dataclass(frozen=True, slots=True)
class FlipGridConfig:
    starting_equity: float = 100.0
    allocation_pct: float = 60.0
    leverage: float = 1.0
    chains: int = 6
    seed_step_bps: float = 200.0
    flip_take_profit_bps: float = 60.0
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    liquidation_slippage_bps: float = 2.0
    fill_buffer_bps: float = 1.0
    maintenance_margin_pct: float = 0.5
    account_stop_pct: float = 0.0
    lot_size: float = 0.001
    min_size: float = 0.001
    contract_value: float = 1.0
    tick_size: float = 0.01


@dataclass(slots=True)
class FlipLot:
    chain: int
    direction: int
    entry_price: float
    quantity: float
    entry_ts: int


@dataclass(slots=True)
class FlipFill:
    ts: int
    action: str
    chain: int
    direction: int
    price: float
    quantity: float
    gross_pnl: float
    fee: float
    equity: float


@dataclass(slots=True)
class FlipGridResult:
    config: dict[str, Any]
    bars: int
    start_ts: int
    end_ts: int
    starting_equity: float
    final_mark_equity: float
    final_liquidation_equity: float
    return_pct: float
    max_drawdown_pct: float
    realized_pnl: float
    terminal_unrealized: float
    gross_harvest: float
    fees: float
    funding_cost: float
    seed_entries: int
    flips: int
    long_completions: int
    short_completions: int
    terminal_lots: int
    max_gross_exposure_pct: float
    max_abs_net_exposure_pct: float
    price_return_pct: float
    liquidated: bool
    account_stopped: bool


@dataclass(slots=True)
class FlipGridSimulation:
    result: FlipGridResult
    fills: list[FlipFill]
    equity_curve: list[dict[str, Any]]


def validate_flip_config(config: FlipGridConfig) -> None:
    if config.starting_equity <= 0 or config.chains <= 0:
        raise ValueError("starting equity and chains must be positive")
    if not 0 < config.allocation_pct <= 100 or config.leverage <= 0:
        raise ValueError("allocation and leverage must be positive")
    if config.seed_step_bps <= 0 or config.flip_take_profit_bps <= 0:
        raise ValueError("grid spacing and take profit must be positive")
    if min(config.lot_size, config.min_size, config.contract_value, config.tick_size) <= 0:
        raise ValueError("contract metadata must be positive")


def seed_prices(anchor: float, config: FlipGridConfig) -> list[float]:
    step = 1.0 - config.seed_step_bps / 10_000.0
    return [round_price_down(anchor * step**chain, config.tick_size) for chain in range(config.chains)]


def flip_target(lot: FlipLot, config: FlipGridConfig) -> float:
    if lot.direction > 0:
        return round_price_up(
            lot.entry_price * (1.0 + config.flip_take_profit_bps / 10_000.0),
            config.tick_size,
        )
    return round_price_down(
        lot.entry_price * (1.0 - config.flip_take_profit_bps / 10_000.0),
        config.tick_size,
    )


def inventory_snapshot(lots: dict[int, FlipLot], mark: float, contract_value: float) -> tuple[float, float, float]:
    gross = sum(lot.quantity * mark * contract_value for lot in lots.values())
    net = sum(lot.direction * lot.quantity * mark * contract_value for lot in lots.values())
    unrealized = sum(
        lot.direction * (mark - lot.entry_price) * lot.quantity * contract_value
        for lot in lots.values()
    )
    return gross, net, unrealized


def simulate_flip_grid(
    candles: list[Candle],
    config: FlipGridConfig,
    funding: Iterable[FundingPoint] = (),
    *,
    record_details: bool = True,
) -> FlipGridSimulation:
    """Simulate staggered take-profit-and-reverse inventory chains.

    Every chain starts as a resting long layer.  A profitable long closes and
    opens a same-quantity short at its TP; a profitable short closes and opens
    a long.  A newly opened reverse leg cannot complete again on the same bar.
    Existing inventory is checked for maintenance-margin liquidation before
    any favorable intrabar flip.
    """

    validate_flip_config(config)
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    anchor = float(candles[0].close)
    seeds = seed_prices(anchor, config)
    per_chain_notional = (
        config.starting_equity
        * config.allocation_pct
        / 100.0
        * config.leverage
        / config.chains
    )
    lots: dict[int, FlipLot] = {}
    fills: list[FlipFill] = []
    curve: list[dict[str, Any]] = []
    cash = config.starting_equity
    realized_pnl = 0.0
    gross_harvest = 0.0
    fees = 0.0
    funding_cost = 0.0
    seed_entries = 0
    flips = 0
    long_completions = 0
    short_completions = 0
    peak = config.starting_equity
    max_drawdown = 0.0
    max_gross_pct = 0.0
    max_abs_net_pct = 0.0
    liquidated = False
    account_stopped = False
    halted = False
    maker_rate = config.maker_fee_bps / 10_000.0
    taker_rate = config.taker_fee_bps / 10_000.0
    liquidation_slip = config.liquidation_slippage_bps / 10_000.0
    fill_buffer = config.fill_buffer_bps / 10_000.0
    maintenance_rate = config.maintenance_margin_pct / 100.0
    funding_points = sorted(funding, key=lambda item: item.ts)
    funding_index = 0
    while funding_index < len(funding_points) and funding_points[funding_index].ts <= candles[0].ts:
        funding_index += 1

    def equity_at(mark: float) -> float:
        return cash + inventory_snapshot(lots, mark, config.contract_value)[2]

    def add_fill(
        ts: int,
        action: str,
        chain: int,
        direction: int,
        price: float,
        quantity: float,
        gross_pnl: float,
        fee: float,
    ) -> None:
        if record_details:
            fills.append(
                FlipFill(ts, action, chain, direction, price, quantity, gross_pnl, fee, equity_at(price))
            )

    def close_all(candle: Candle, mark: float, action: str) -> None:
        nonlocal cash, realized_pnl, fees, halted
        for chain in sorted(list(lots)):
            lot = lots.pop(chain)
            if lot.direction > 0:
                fill = mark * (1.0 - liquidation_slip)
            else:
                fill = mark * (1.0 + liquidation_slip)
            gross = lot.direction * (fill - lot.entry_price) * lot.quantity * config.contract_value
            fee = fill * lot.quantity * config.contract_value * taker_rate
            cash += gross - fee
            realized_pnl += gross
            fees += fee
            add_fill(candle.ts, action, chain, lot.direction, fill, lot.quantity, gross, fee)
        halted = True

    for index in range(1, len(candles)):
        candle = candles[index]
        prior_ts = candles[index - 1].ts
        while funding_index < len(funding_points) and funding_points[funding_index].ts <= candle.ts:
            point = funding_points[funding_index]
            if point.ts > prior_ts and lots:
                rate = point.realized_rate or point.rate
                payment = sum(
                    lot.direction * lot.quantity * float(candle.open) * config.contract_value * rate
                    for lot in lots.values()
                )
                cash -= payment
                funding_cost += payment
            funding_index += 1

        if lots and not halted:
            low = float(candle.low)
            high = float(candle.high)
            low_equity = equity_at(low)
            high_equity = equity_at(high)
            adverse_mark, adverse_equity = (low, low_equity) if low_equity <= high_equity else (high, high_equity)
            gross, _, _ = inventory_snapshot(lots, adverse_mark, config.contract_value)
            if adverse_equity <= gross * maintenance_rate:
                close_all(candle, adverse_mark, "liquidation")
                cash = max(0.0, cash)
                liquidated = True

        if not halted:
            existing = sorted(lots)
            for chain in existing:
                lot = lots.get(chain)
                if lot is None:
                    continue
                target = flip_target(lot, config)
                if lot.direction > 0:
                    touched = float(candle.high) >= target * (1.0 + fill_buffer)
                else:
                    touched = float(candle.low) <= target * (1.0 - fill_buffer)
                if not touched:
                    continue
                gross = lot.direction * (target - lot.entry_price) * lot.quantity * config.contract_value
                close_fee = target * lot.quantity * config.contract_value * maker_rate
                open_fee = close_fee
                cash += gross - close_fee - open_fee
                realized_pnl += gross
                gross_harvest += gross
                fees += close_fee + open_fee
                completed_direction = lot.direction
                lots[chain] = FlipLot(chain, -lot.direction, target, lot.quantity, candle.ts)
                flips += 1
                if completed_direction > 0:
                    long_completions += 1
                else:
                    short_completions += 1
                add_fill(candle.ts, "flip_close", chain, completed_direction, target, lot.quantity, gross, close_fee)
                add_fill(candle.ts, "flip_open", chain, -completed_direction, target, lot.quantity, 0.0, open_fee)

            for chain, price in enumerate(seeds):
                if chain in lots:
                    continue
                if float(candle.low) > price * (1.0 - fill_buffer):
                    continue
                gross_now, _, _ = inventory_snapshot(lots, price, config.contract_value)
                current_equity = max(0.0, equity_at(price))
                max_gross = current_equity * config.allocation_pct / 100.0 * config.leverage
                available = max(0.0, max_gross - gross_now)
                notional = min(per_chain_notional, available)
                quantity = round_quantity_down(
                    notional / (price * config.contract_value),
                    config.lot_size,
                    config.min_size,
                )
                if quantity <= 0:
                    continue
                fee = price * quantity * config.contract_value * maker_rate
                cash -= fee
                fees += fee
                lots[chain] = FlipLot(chain, 1, price, quantity, candle.ts)
                seed_entries += 1
                add_fill(candle.ts, "seed_long", chain, 1, price, quantity, 0.0, fee)

        mark = float(candle.close)
        gross, net, unrealized = inventory_snapshot(lots, mark, config.contract_value)
        equity = cash + unrealized
        if lots and not halted and equity <= gross * maintenance_rate:
            close_all(candle, mark, "liquidation")
            cash = max(0.0, cash)
            liquidated = True
            gross, net, unrealized = inventory_snapshot(lots, mark, config.contract_value)
            equity = cash
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)
        max_gross_pct = max(max_gross_pct, gross / config.starting_equity * 100.0)
        max_abs_net_pct = max(max_abs_net_pct, abs(net) / config.starting_equity * 100.0)
        if not halted and config.account_stop_pct > 0:
            stop_equity = config.starting_equity * (1.0 - config.account_stop_pct / 100.0)
            if equity <= stop_equity:
                close_all(candle, mark, "account_stop")
                account_stopped = True
                gross, net, unrealized = inventory_snapshot(lots, mark, config.contract_value)
                equity = cash
        if record_details:
            curve.append(
                {
                    "ts": candle.ts,
                    "close": mark,
                    "equity": equity,
                    "cash_equity": cash,
                    "unrealized": unrealized,
                    "lots": len(lots),
                    "gross_exposure": gross,
                    "net_exposure": net,
                }
            )

    final_mark = float(candles[-1].close)
    final_gross, _, terminal_unrealized = inventory_snapshot(lots, final_mark, config.contract_value)
    final_mark_equity = cash + terminal_unrealized
    final_exit_cost = final_gross * (taker_rate + liquidation_slip)
    final_liquidation_equity = max(0.0, final_mark_equity - final_exit_cost) if liquidated else final_mark_equity - final_exit_cost
    result = FlipGridResult(
        config=asdict(config),
        bars=len(candles),
        start_ts=candles[0].ts,
        end_ts=candles[-1].ts,
        starting_equity=config.starting_equity,
        final_mark_equity=final_mark_equity,
        final_liquidation_equity=final_liquidation_equity,
        return_pct=(final_liquidation_equity / config.starting_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown,
        realized_pnl=realized_pnl,
        terminal_unrealized=terminal_unrealized,
        gross_harvest=gross_harvest,
        fees=fees,
        funding_cost=funding_cost,
        seed_entries=seed_entries,
        flips=flips,
        long_completions=long_completions,
        short_completions=short_completions,
        terminal_lots=len(lots),
        max_gross_exposure_pct=max_gross_pct,
        max_abs_net_exposure_pct=max_abs_net_pct,
        price_return_pct=(final_mark / float(candles[0].close) - 1.0) * 100.0,
        liquidated=liquidated,
        account_stopped=account_stopped,
    )
    return FlipGridSimulation(result, fills, curve)
