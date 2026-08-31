from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from backtest.okx_grid_backtest import (
    BAR_MS,
    Candle,
    fetch_okx_candle_rows,
    parse_okx_candles,
    read_candles_csv,
    write_candles_csv,
)
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "vwap_market_maker"
LEGACY_DATA_ROOT = PROJECT_ROOT / "data" / "backtest"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "vwap_market_maker"
DEFAULT_INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class VwapMakerParams:
    vwap_window: int
    anchor_weight: float
    min_half_spread_bps: float
    volatility_multiplier: float
    inventory_skew_bps: float
    trend_lookback: int = 12
    max_vwap_slope_bps: float = 40.0
    volatility_window: int = 24
    max_volatility_bps: float = 30.0
    quote_notional_pct: float = 2.0
    max_inventory_pct: float = 10.0
    max_inventory_bars: int = 72
    inventory_stop_bps: float = 150.0
    penetration_bps: float = 0.5

    def __post_init__(self) -> None:
        if self.vwap_window < 2 or self.trend_lookback < 1 or self.volatility_window < 2:
            raise ValueError("VWAP, trend, and volatility windows must be positive")
        if not 0.0 <= self.anchor_weight <= 1.0:
            raise ValueError("anchor_weight must be in [0, 1]")
        positive = (
            self.min_half_spread_bps,
            self.volatility_multiplier,
            self.inventory_skew_bps,
            self.max_vwap_slope_bps,
            self.max_volatility_bps,
            self.quote_notional_pct,
            self.max_inventory_pct,
            self.inventory_stop_bps,
        )
        if min(positive) <= 0 or self.max_inventory_bars < 1 or self.penetration_bps < 0:
            raise ValueError("strategy risk and quote parameters must be positive")
        if self.quote_notional_pct > self.max_inventory_pct:
            raise ValueError("quote notional cannot exceed maximum inventory")


@dataclass(frozen=True, slots=True)
class MakerExecutionConfig:
    starting_equity: float = 100_000.0
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    taker_slippage_bps: float = 1.0
    holding_cost_bps_per_day: float = 0.5
    latency_bars: int = 0
    conservative_single_fill: bool = True

    def __post_init__(self) -> None:
        if self.starting_equity <= 0:
            raise ValueError("starting equity must be positive")
        if min(
            self.maker_fee_bps,
            self.taker_fee_bps,
            self.taker_slippage_bps,
            self.holding_cost_bps_per_day,
            self.latency_bars,
        ) < 0:
            raise ValueError("execution costs and latency cannot be negative")


@dataclass(frozen=True, slots=True)
class MakerFeature:
    ts: int
    close: float
    vwap: float
    volatility_bps: float
    vwap_slope_bps: float
    half_spread_bps: float
    regime_active: bool


@dataclass(frozen=True, slots=True)
class MakerQuote:
    side: str
    price: float
    quantity: float
    reduce_only: bool


@dataclass(frozen=True, slots=True)
class MakerFill:
    ts: int
    side: str
    role: str
    price: float
    quantity: float
    fee: float
    realized_pnl: float
    inventory_after: float


@dataclass(frozen=True, slots=True)
class InventoryCycle:
    entry_ts: int
    exit_ts: int
    exit_reason: str
    net_pnl: float
    bars_held: int


@dataclass(frozen=True, slots=True)
class MakerBacktestResult:
    start: str
    end: str
    starting_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    quote_bars: int
    maker_fills: int
    taker_exits: int
    inventory_cycles: int
    profitable_cycles: int
    fill_rate_pct: float
    exposure_pct: float
    max_inventory_pct: float
    average_inventory_age_bars: float
    fees: float
    holding_cost: float
    stop_exits: int
    timeout_exits: int
    terminal_exits: int
    both_sides_touched: int


@dataclass(frozen=True, slots=True)
class CandidateScore:
    params: VwapMakerParams
    score: float
    median_return_pct: float
    worst_return_pct: float
    stressed_median_return_pct: float
    stressed_worst_return_pct: float
    median_drawdown_pct: float
    median_fills: float
    positive_instruments: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only rolling-VWAP market-maker research on public OKX candles."
    )
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--bar", default="5m", choices=list(BAR_MS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=48)
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--maker-fee-bps", type=float, default=2.0)
    parser.add_argument("--taker-fee-bps", type=float, default=5.0)
    parser.add_argument("--taker-slippage-bps", type=float, default=1.0)
    parser.add_argument("--holding-cost-bps-per-day", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    histories, sources = load_histories(args, instruments)
    histories = completed_common_histories(histories, args.bar)
    if any(len(histories.get(inst_id, [])) < 4_000 for inst_id in instruments):
        raise SystemExit("At least 4,000 completed common candles per instrument are required")

    segments, period = chronological_segments(histories, instruments)
    execution = MakerExecutionConfig(
        starting_equity=args.starting_equity,
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
        taker_slippage_bps=args.taker_slippage_bps,
        holding_cost_bps_per_day=args.holding_cost_bps_per_day,
    )
    scores = select_parameters(
        {inst_id: values["train"] for inst_id, values in segments.items()},
        execution,
        BAR_MS[args.bar],
    )
    if not scores:
        raise SystemExit("No candidate generated enough training maker fills")
    selected = scores[0].params

    rows: list[dict[str, Any]] = []
    test_fills: list[dict[str, Any]] = []
    test_cycles: list[dict[str, Any]] = []
    for inst_id in instruments:
        for segment, candles in segments[inst_id].items():
            result, fills, cycles, _ = run_market_maker_backtest(
                candles,
                selected,
                execution,
                bar_ms=BAR_MS[args.bar],
                record_details=segment == "test",
            )
            rows.append(result_row(inst_id, segment, "selected", selected, result))
            if segment == "test":
                test_fills.extend({"inst_id": inst_id, **asdict(item)} for item in fills)
                test_cycles.extend({"inst_id": inst_id, **asdict(item)} for item in cycles)
                rows.extend(test_variants(inst_id, candles, selected, execution, BAR_MS[args.bar]))

    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, aggregates)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_vwap_inventory_skew_market_maker_research",
        "instruments": list(instruments),
        "bar": args.bar,
        "dataSources": sources,
        "dataDefinition": {
            "source": "public OKX OHLCV candles",
            "split": "first 50% train, next 25% validation, last 25% reused-history test",
            "limitation": (
                "bar data cannot establish queue position or maker fill probability; a quote must be "
                "traded through, only the worse side fills when both sides touch, and quotes become active one bar later"
            ),
        },
        "strategyDefinition": {
            "fairValue": "completed-bar close pulled toward rolling typical-price VWAP",
            "reservationPrice": "fair value minus a normalized net-inventory skew",
            "quotes": "post-only proxy quotes around reservation price with volatility-scaled width",
            "risk": "VWAP-slope/volatility pause, 10% maximum inventory, timeout and loss exit",
            "positioning": "2% equity per quote, net inventory only, no leverage",
        },
        "executionConfig": asdict(execution),
        "period": period,
        "sampleCounts": {
            inst_id: {name: len(candles) for name, candles in values.items()}
            for inst_id, values in segments.items()
        },
        "selectedParameters": asdict(selected),
        "candidateScores": [candidate_payload(item) for item in scores[:100]],
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "test_fills.csv", test_fills)
    write_csv(output_dir / "test_inventory_cycles.csv", test_cycles)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")

    print(f"output_dir={output_dir}")
    print(f"selected={json.dumps(asdict(selected), sort_keys=True)}")
    print(f"decision={json.dumps(decision, sort_keys=True)}")
    lookup = {(row['segment'], row['variant']): row for row in aggregates}
    for segment in ("train", "validation", "test", "full"):
        item = lookup[(segment, "selected")]
        print(
            f"segment={segment} median_return={item['median_return_pct']:.6f}% "
            f"median_pf={item['median_profit_factor']:.4f} "
            f"median_fills={item['median_maker_fills']:.1f}"
        )
    return 0


def load_histories(
    args: argparse.Namespace, instruments: tuple[str, ...]
) -> tuple[dict[str, list[Candle]], dict[str, str]]:
    root = Path(args.data_root)
    root.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.pages <= 1 else f"x{args.pages}"
    histories: dict[str, list[Candle]] = {}
    sources: dict[str, str] = {}
    client = OkxRestClient()
    for inst_id in instruments:
        cache = root / f"{inst_id}_{args.bar}_{args.limit}{suffix}.csv"
        legacy = LEGACY_DATA_ROOT / cache.name
        if cache.exists() and not args.refresh:
            candles = read_candles_csv(cache)
            source = cache
        elif legacy.exists() and not args.refresh:
            candles = read_candles_csv(legacy)
            source = legacy
        else:
            rows = fetch_okx_candle_rows(client, inst_id, args.bar, args.limit, max(1, args.pages))
            candles = parse_completed_okx_candles(rows, args.bar)
            write_candles_csv(cache, candles)
            source = cache
            time.sleep(0.25)
        histories[inst_id] = candles
        sources[inst_id] = str(source)
    return histories, sources


def parse_completed_okx_candles(
    rows: list[list[str]], bar: str, *, now_ms: int | None = None
) -> list[Candle]:
    """Discard OKX's current partial candle before it can enter a reusable cache."""

    confirmed_rows = [row for row in rows if len(row) < 9 or str(row[8]) == "1"]
    candles = parse_okx_candles(confirmed_rows)
    cutoff = int(now_ms if now_ms is not None else time.time() * 1000)
    duration = BAR_MS[bar]
    return [candle for candle in candles if candle.ts + duration <= cutoff]


def completed_common_histories(
    histories: dict[str, list[Candle]], bar: str, *, now_ms: int | None = None
) -> dict[str, list[Candle]]:
    if not histories or any(not rows for rows in histories.values()):
        return histories
    cutoff = int(now_ms if now_ms is not None else time.time() * 1000)
    duration = BAR_MS[bar]
    completed = {
        inst_id: [candle for candle in candles if candle.ts + duration <= cutoff]
        for inst_id, candles in histories.items()
    }
    if any(not rows for rows in completed.values()):
        return completed
    common_start = max(rows[0].ts for rows in completed.values())
    common_end = min(rows[-1].ts for rows in completed.values())
    return {
        inst_id: [candle for candle in rows if common_start <= candle.ts <= common_end]
        for inst_id, rows in completed.items()
    }


def chronological_segments(
    histories: dict[str, list[Candle]], instruments: tuple[str, ...]
) -> tuple[dict[str, dict[str, list[Candle]]], dict[str, str]]:
    count = min(len(histories[inst_id]) for inst_id in instruments)
    train_end = count // 2
    validation_end = train_end + count // 4
    result: dict[str, dict[str, list[Candle]]] = {}
    for inst_id in instruments:
        rows = histories[inst_id][-count:]
        result[inst_id] = {
            "train": rows[:train_end],
            "validation": rows[train_end:validation_end],
            "test": rows[validation_end:],
            "full": rows,
        }
    reference = result[instruments[0]]
    return result, {
        "start": iso_time(reference["full"][0].ts),
        "trainEnd": iso_time(reference["train"][-1].ts),
        "validationEnd": iso_time(reference["validation"][-1].ts),
        "end": iso_time(reference["full"][-1].ts),
    }


def rolling_vwap_features(
    candles: list[Candle], params: VwapMakerParams
) -> list[MakerFeature | None]:
    count = len(candles)
    if not count:
        return []
    closes = [float(candle.close) for candle in candles]
    typical = [
        (float(candle.high) + float(candle.low) + float(candle.close)) / 3.0
        for candle in candles
    ]
    volumes = [max(0.0, float(candle.volume)) for candle in candles]
    cumulative_pv = [0.0]
    cumulative_volume = [0.0]
    for price, volume in zip(typical, volumes):
        cumulative_pv.append(cumulative_pv[-1] + price * volume)
        cumulative_volume.append(cumulative_volume[-1] + volume)

    vwaps: list[float] = [math.nan] * count
    for index in range(count):
        start = max(0, index - params.vwap_window + 1)
        volume = cumulative_volume[index + 1] - cumulative_volume[start]
        if index - start + 1 >= params.vwap_window and volume > EPSILON:
            vwaps[index] = (cumulative_pv[index + 1] - cumulative_pv[start]) / volume

    log_returns = [0.0]
    for index in range(1, count):
        previous = max(closes[index - 1], EPSILON)
        current = max(closes[index], EPSILON)
        log_returns.append(math.log(current / previous))
    cumulative_return = [0.0]
    cumulative_return_sq = [0.0]
    for value in log_returns:
        cumulative_return.append(cumulative_return[-1] + value)
        cumulative_return_sq.append(cumulative_return_sq[-1] + value * value)

    features: list[MakerFeature | None] = [None] * count
    warmup = max(params.vwap_window, params.volatility_window, params.trend_lookback + 1)
    for index in range(warmup - 1, count):
        vwap = vwaps[index]
        prior_vwap = vwaps[index - params.trend_lookback]
        if not math.isfinite(vwap) or not math.isfinite(prior_vwap) or prior_vwap <= 0:
            continue
        start = index - params.volatility_window + 1
        n = params.volatility_window
        total = cumulative_return[index + 1] - cumulative_return[start]
        total_sq = cumulative_return_sq[index + 1] - cumulative_return_sq[start]
        variance = max(0.0, total_sq / n - (total / n) ** 2)
        volatility_bps = math.sqrt(variance) * 10_000.0
        slope_bps = (vwap / prior_vwap - 1.0) * 10_000.0
        half_spread = max(
            params.min_half_spread_bps,
            volatility_bps * params.volatility_multiplier,
        )
        features[index] = MakerFeature(
            ts=candles[index].ts,
            close=closes[index],
            vwap=vwap,
            volatility_bps=volatility_bps,
            vwap_slope_bps=slope_bps,
            half_spread_bps=half_spread,
            regime_active=(
                abs(slope_bps) <= params.max_vwap_slope_bps
                and volatility_bps <= params.max_volatility_bps
            ),
        )
    return features


def quote_levels(
    feature: MakerFeature,
    params: VwapMakerParams,
    *,
    inventory: float,
    max_inventory: float,
) -> tuple[float, float, float]:
    if max_inventory <= 0:
        raise ValueError("maximum inventory must be positive")
    fair_value = feature.close + params.anchor_weight * (feature.vwap - feature.close)
    inventory_ratio = max(-1.0, min(1.0, inventory / max_inventory))
    reservation = fair_value * (
        1.0 - params.inventory_skew_bps * inventory_ratio / 10_000.0
    )
    half = feature.half_spread_bps / 10_000.0
    post_only_guard = 0.01 / 10_000.0
    bid = min(reservation * (1.0 - half), feature.close * (1.0 - post_only_guard))
    ask = max(reservation * (1.0 + half), feature.close * (1.0 + post_only_guard))
    return reservation, bid, ask


def desired_quotes(
    feature: MakerFeature,
    params: VwapMakerParams,
    *,
    inventory: float,
    equity: float,
) -> list[MakerQuote]:
    if equity <= 0 or feature.close <= 0:
        return []
    base_quantity = equity * params.quote_notional_pct / 100.0 / feature.close
    max_inventory = equity * params.max_inventory_pct / 100.0 / feature.close
    _, bid, ask = quote_levels(
        feature,
        params,
        inventory=inventory,
        max_inventory=max_inventory,
    )
    quotes: list[MakerQuote] = []

    if inventory < -EPSILON:
        buy_quantity = min(base_quantity, abs(inventory))
        if buy_quantity > EPSILON:
            quotes.append(MakerQuote("buy", bid, buy_quantity, True))
    elif feature.regime_active and inventory + base_quantity <= max_inventory + EPSILON:
        quotes.append(MakerQuote("buy", bid, base_quantity, False))

    if inventory > EPSILON:
        sell_quantity = min(base_quantity, inventory)
        if sell_quantity > EPSILON:
            quotes.append(MakerQuote("sell", ask, sell_quantity, True))
    elif feature.regime_active and inventory - base_quantity >= -max_inventory - EPSILON:
        quotes.append(MakerQuote("sell", ask, base_quantity, False))
    return quotes


def run_market_maker_backtest(
    candles: list[Candle],
    params: VwapMakerParams,
    execution: MakerExecutionConfig,
    *,
    bar_ms: int,
    features: list[MakerFeature | None] | None = None,
    record_details: bool = False,
    active_predicate: Callable[[Candle], bool] | None = None,
) -> tuple[
    MakerBacktestResult,
    list[MakerFill],
    list[InventoryCycle],
    list[dict[str, Any]],
]:
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    features = features if features is not None else rolling_vwap_features(candles, params)
    if len(features) != len(candles):
        raise ValueError("feature and candle lengths must match")

    cash = execution.starting_equity
    inventory = 0.0
    average_price = 0.0
    peak_equity = cash
    max_drawdown_pct = 0.0
    max_inventory_pct = 0.0
    total_fees = 0.0
    holding_cost_total = 0.0
    quote_bars = 0
    maker_fills = 0
    taker_exits = 0
    stop_exits = 0
    timeout_exits = 0
    terminal_exits = 0
    both_sides_touched = 0
    exposure_bars = 0
    inventory_entry_index: int | None = None
    cycle_entry_ts = 0
    cycle_net = 0.0
    cycle_age_samples: list[int] = []
    fills: list[MakerFill] = []
    cycles: list[InventoryCycle] = []
    equity_curve: list[dict[str, Any]] = []

    def mark_equity(price: float) -> float:
        if abs(inventory) <= EPSILON:
            return cash
        return cash + (price - average_price) * inventory

    def begin_cycle(index: int) -> None:
        nonlocal inventory_entry_index, cycle_entry_ts, cycle_net
        inventory_entry_index = index
        cycle_entry_ts = candles[index].ts
        cycle_net = 0.0

    def finish_cycle(index: int, reason: str) -> None:
        nonlocal inventory_entry_index, cycle_entry_ts, cycle_net
        if inventory_entry_index is None:
            return
        age = max(0, index - inventory_entry_index)
        cycles.append(
            InventoryCycle(
                entry_ts=cycle_entry_ts,
                exit_ts=candles[index].ts,
                exit_reason=reason,
                net_pnl=cycle_net,
                bars_held=age,
            )
        )
        cycle_age_samples.append(age)
        inventory_entry_index = None
        cycle_entry_ts = 0
        cycle_net = 0.0

    def execute_fill(index: int, side: str, price: float, quantity: float, role: str) -> None:
        nonlocal cash, inventory, average_price, total_fees, cycle_net
        nonlocal maker_fills, taker_exits
        if quantity <= EPSILON or price <= 0:
            return
        previous_inventory = inventory
        if abs(previous_inventory) <= EPSILON:
            begin_cycle(index)
        signed_quantity = quantity if side == "buy" else -quantity
        realized, inventory_after, average_after = apply_inventory_fill(
            inventory,
            average_price,
            signed_quantity,
            price,
        )
        fee_rate = execution.maker_fee_bps if role == "maker" else execution.taker_fee_bps
        fee = price * quantity * fee_rate / 10_000.0
        cash += realized - fee
        cycle_net += realized - fee
        total_fees += fee
        inventory = inventory_after
        average_price = average_after
        if role == "maker":
            maker_fills += 1
        else:
            taker_exits += 1
        if record_details:
            fills.append(
                MakerFill(
                    ts=candles[index].ts,
                    side=side,
                    role=role,
                    price=price,
                    quantity=quantity,
                    fee=fee,
                    realized_pnl=realized,
                    inventory_after=inventory,
                )
            )
        if abs(inventory) <= EPSILON:
            inventory = 0.0
            average_price = 0.0
            finish_cycle(index, "maker_flat" if role == "maker" else role)

    for index, candle in enumerate(candles):
        close = float(candle.close)
        low = float(candle.low)
        high = float(candle.high)
        is_active = active_predicate(candle) if active_predicate is not None else True
        if not is_active and abs(inventory) > EPSILON:
            side = "sell" if inventory > 0 else "buy"
            slip = execution.taker_slippage_bps / 10_000.0
            boundary_price = float(candle.open) * (
                1.0 - slip if side == "sell" else 1.0 + slip
            )
            execute_fill(index, side, boundary_price, abs(inventory), "session_exit")
        signal_index = index - 1 - execution.latency_bars
        feature = features[signal_index] if signal_index >= 0 else None
        equity_before = max(EPSILON, mark_equity(float(candle.open)))
        quotes = (
            desired_quotes(feature, params, inventory=inventory, equity=equity_before)
            if is_active and feature is not None
            else []
        )
        if quotes:
            quote_bars += 1
            touched = []
            penetration = params.penetration_bps / 10_000.0
            for quote in quotes:
                if quote.side == "buy" and low <= quote.price * (1.0 - penetration):
                    touched.append(quote)
                elif quote.side == "sell" and high >= quote.price * (1.0 + penetration):
                    touched.append(quote)
            if len(touched) > 1:
                both_sides_touched += 1
                if execution.conservative_single_fill:
                    touched = [
                        min(
                            touched,
                            key=lambda quote: (
                                (close - quote.price) * quote.quantity
                                if quote.side == "buy"
                                else (quote.price - close) * quote.quantity
                            )
                            - quote.price
                            * quote.quantity
                            * execution.maker_fee_bps
                            / 10_000.0,
                        )
                    ]
            for quote in touched:
                execute_fill(index, quote.side, quote.price, quote.quantity, "maker")

        if abs(inventory) > EPSILON:
            exposure_bars += 1
            holding_cost = (
                abs(inventory)
                * close
                * execution.holding_cost_bps_per_day
                / 10_000.0
                * bar_ms
                / 86_400_000.0
            )
            cash -= holding_cost
            cycle_net -= holding_cost
            holding_cost_total += holding_cost
            inventory_notional_pct = abs(inventory) * close / max(mark_equity(close), EPSILON) * 100.0
            max_inventory_pct = max(max_inventory_pct, inventory_notional_pct)
            age = index - inventory_entry_index if inventory_entry_index is not None else 0
            inventory_pnl_bps = (
                (close / average_price - 1.0) * 10_000.0 * (1.0 if inventory > 0 else -1.0)
                if average_price > 0
                else 0.0
            )
            risk_reason = ""
            if inventory_pnl_bps <= -params.inventory_stop_bps:
                risk_reason = "inventory_stop"
                stop_exits += 1
            elif age >= params.max_inventory_bars:
                risk_reason = "inventory_timeout"
                timeout_exits += 1
            if risk_reason:
                side = "sell" if inventory > 0 else "buy"
                slip = execution.taker_slippage_bps / 10_000.0
                price = close * (1.0 - slip if side == "sell" else 1.0 + slip)
                execute_fill(index, side, price, abs(inventory), risk_reason)

        equity = mark_equity(close)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak_equity - equity) / peak_equity * 100.0)
        if record_details:
            equity_curve.append(
                {
                    "ts": candle.ts,
                    "time": iso_time(candle.ts),
                    "close": close,
                    "equity": equity,
                    "inventory": inventory,
                    "average_price": average_price,
                    "regime_active": bool(feature.regime_active) if feature else False,
                }
            )

    if abs(inventory) > EPSILON:
        index = len(candles) - 1
        close = float(candles[index].close)
        side = "sell" if inventory > 0 else "buy"
        slip = execution.taker_slippage_bps / 10_000.0
        price = close * (1.0 - slip if side == "sell" else 1.0 + slip)
        terminal_exits += 1
        execute_fill(index, side, price, abs(inventory), "terminal_exit")

    final_equity = cash
    peak_equity = max(peak_equity, final_equity)
    if peak_equity > 0:
        max_drawdown_pct = max(
            max_drawdown_pct,
            (peak_equity - final_equity) / peak_equity * 100.0,
        )
    profitable_cycles = sum(cycle.net_pnl > 0 for cycle in cycles)
    gross_profit = sum(max(0.0, cycle.net_pnl) for cycle in cycles)
    gross_loss = abs(sum(min(0.0, cycle.net_pnl) for cycle in cycles))
    result = MakerBacktestResult(
        start=iso_time(candles[0].ts),
        end=iso_time(candles[-1].ts),
        starting_equity=execution.starting_equity,
        final_equity=final_equity,
        total_return_pct=(final_equity / execution.starting_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown_pct,
        profit_factor=(gross_profit / gross_loss if gross_loss > EPSILON else (999.0 if gross_profit > 0 else 0.0)),
        quote_bars=quote_bars,
        maker_fills=maker_fills,
        taker_exits=taker_exits,
        inventory_cycles=len(cycles),
        profitable_cycles=profitable_cycles,
        fill_rate_pct=maker_fills / max(quote_bars, 1) * 100.0,
        exposure_pct=exposure_bars / max(len(candles), 1) * 100.0,
        max_inventory_pct=max_inventory_pct,
        average_inventory_age_bars=(statistics.fmean(cycle_age_samples) if cycle_age_samples else 0.0),
        fees=total_fees,
        holding_cost=holding_cost_total,
        stop_exits=stop_exits,
        timeout_exits=timeout_exits,
        terminal_exits=terminal_exits,
        both_sides_touched=both_sides_touched,
    )
    return result, fills, cycles, equity_curve


def apply_inventory_fill(
    inventory: float,
    average_price: float,
    signed_quantity: float,
    price: float,
) -> tuple[float, float, float]:
    if abs(signed_quantity) <= EPSILON:
        return 0.0, inventory, average_price
    if abs(inventory) <= EPSILON or inventory * signed_quantity > 0:
        new_inventory = inventory + signed_quantity
        new_average = (
            (abs(inventory) * average_price + abs(signed_quantity) * price)
            / abs(new_inventory)
        )
        return 0.0, new_inventory, new_average

    closing_quantity = min(abs(inventory), abs(signed_quantity))
    realized = (price - average_price) * closing_quantity * (1.0 if inventory > 0 else -1.0)
    new_inventory = inventory + signed_quantity
    if abs(new_inventory) <= EPSILON:
        return realized, 0.0, 0.0
    if inventory * new_inventory > 0:
        return realized, new_inventory, average_price
    return realized, new_inventory, price


def candidate_grid() -> Iterable[VwapMakerParams]:
    for vwap_window in (48, 144, 288):
        for anchor_weight in (0.25, 0.50):
            for half_spread in (5.0, 10.0):
                for volatility_multiplier in (0.5, 1.0):
                    for inventory_skew in (10.0, 25.0):
                        for max_slope in (20.0, 50.0):
                            yield VwapMakerParams(
                                vwap_window=vwap_window,
                                anchor_weight=anchor_weight,
                                min_half_spread_bps=half_spread,
                                volatility_multiplier=volatility_multiplier,
                                inventory_skew_bps=inventory_skew,
                                max_vwap_slope_bps=max_slope,
                            )


def select_parameters(
    training: dict[str, list[Candle]],
    execution: MakerExecutionConfig,
    bar_ms: int,
) -> list[CandidateScore]:
    stressed_execution = replace(
        execution,
        maker_fee_bps=max(5.0, execution.maker_fee_bps * 2.5),
        taker_fee_bps=max(8.0, execution.taker_fee_bps * 1.6),
        taker_slippage_bps=max(2.0, execution.taker_slippage_bps * 2.0),
        holding_cost_bps_per_day=max(1.0, execution.holding_cost_bps_per_day * 2.0),
    )
    scores: list[CandidateScore] = []
    for params in candidate_grid():
        primary_results = []
        stressed_results = []
        stressed_params = replace(params, penetration_bps=max(2.0, params.penetration_bps))
        for candles in training.values():
            features = rolling_vwap_features(candles, params)
            primary_results.append(
                run_market_maker_backtest(
                    candles,
                    params,
                    execution,
                    bar_ms=bar_ms,
                    features=features,
                )[0]
            )
            stressed_features = rolling_vwap_features(candles, stressed_params)
            stressed_results.append(
                run_market_maker_backtest(
                    candles,
                    stressed_params,
                    stressed_execution,
                    bar_ms=bar_ms,
                    features=stressed_features,
                )[0]
            )
        if not primary_results or min(result.maker_fills for result in primary_results) < 30:
            continue
        returns = [result.total_return_pct for result in primary_results]
        stressed_returns = [result.total_return_pct for result in stressed_results]
        drawdowns = [result.max_drawdown_pct for result in primary_results]
        median_return = statistics.median(returns)
        worst_return = min(returns)
        stressed_median = statistics.median(stressed_returns)
        stressed_worst = min(stressed_returns)
        score = (
            median_return
            + 0.75 * worst_return
            + 0.50 * stressed_median
            + 0.25 * stressed_worst
            - 0.20 * statistics.median(drawdowns)
        )
        scores.append(
            CandidateScore(
                params=params,
                score=score,
                median_return_pct=median_return,
                worst_return_pct=worst_return,
                stressed_median_return_pct=stressed_median,
                stressed_worst_return_pct=stressed_worst,
                median_drawdown_pct=statistics.median(drawdowns),
                median_fills=statistics.median(result.maker_fills for result in primary_results),
                positive_instruments=sum(value > 0 for value in returns),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def test_variants(
    inst_id: str,
    candles: list[Candle],
    selected: VwapMakerParams,
    execution: MakerExecutionConfig,
    bar_ms: int,
) -> list[dict[str, Any]]:
    variants = (
        (
            "cost_stress",
            replace(selected, penetration_bps=max(2.0, selected.penetration_bps)),
            replace(
                execution,
                maker_fee_bps=max(5.0, execution.maker_fee_bps * 2.5),
                taker_fee_bps=max(8.0, execution.taker_fee_bps * 1.6),
                taker_slippage_bps=max(2.0, execution.taker_slippage_bps * 2.0),
                holding_cost_bps_per_day=max(1.0, execution.holding_cost_bps_per_day * 2.0),
            ),
        ),
        ("one_bar_latency", selected, replace(execution, latency_bars=1)),
        ("no_vwap_anchor", replace(selected, anchor_weight=0.0), execution),
        ("no_inventory_skew", replace(selected, inventory_skew_bps=EPSILON), execution),
        ("no_regime_filter", replace(selected, max_vwap_slope_bps=1e12, max_volatility_bps=1e12), execution),
    )
    rows = []
    for name, params, variant_execution in variants:
        result = run_market_maker_backtest(
            candles,
            params,
            variant_execution,
            bar_ms=bar_ms,
        )[0]
        rows.append(result_row(inst_id, "test", name, params, result))
    return rows


def result_row(
    inst_id: str,
    segment: str,
    variant: str,
    params: VwapMakerParams,
    result: MakerBacktestResult,
) -> dict[str, Any]:
    return {
        "inst_id": inst_id,
        "segment": segment,
        "variant": variant,
        **asdict(result),
        "vwap_window": params.vwap_window,
        "anchor_weight": params.anchor_weight,
        "min_half_spread_bps": params.min_half_spread_bps,
        "volatility_multiplier": params.volatility_multiplier,
        "inventory_skew_bps": params.inventory_skew_bps,
        "max_vwap_slope_bps": params.max_vwap_slope_bps,
        "penetration_bps": params.penetration_bps,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["segment"]), str(row["variant"])), []).append(row)
    result = []
    for (segment, variant), items in groups.items():
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "count": len(items),
                "positive": sum(float(item["total_return_pct"]) > 0 for item in items),
                "median_return_pct": statistics.median(float(item["total_return_pct"]) for item in items),
                "worst_return_pct": min(float(item["total_return_pct"]) for item in items),
                "median_profit_factor": statistics.median(float(item["profit_factor"]) for item in items),
                "worst_drawdown_pct": max(float(item["max_drawdown_pct"]) for item in items),
                "median_maker_fills": statistics.median(float(item["maker_fills"]) for item in items),
                "median_inventory_cycles": statistics.median(float(item["inventory_cycles"]) for item in items),
                "median_max_inventory_pct": statistics.median(float(item["max_inventory_pct"]) for item in items),
            }
        )
    order = {"train": 0, "validation": 1, "test": 2, "full": 3}
    result.sort(key=lambda item: (order.get(str(item["segment"]), 9), str(item["variant"])))
    return result


def decision_payload(
    rows: list[dict[str, Any]], aggregates: list[dict[str, Any]]
) -> dict[str, Any]:
    lookup = {(row["segment"], row["variant"]): row for row in aggregates}
    validation = lookup[("validation", "selected")]
    test = lookup[("test", "selected")]
    stress = lookup[("test", "cost_stress")]
    latency = lookup[("test", "one_bar_latency")]
    instrument_test = [
        row for row in rows if row["segment"] == "test" and row["variant"] == "selected"
    ]
    quantitative_pass = (
        validation["positive"] == validation["count"]
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["profit_factor"]) >= 1.10 for row in instrument_test)
        and all(int(row["inventory_cycles"]) >= 30 for row in instrument_test)
        and test["worst_drawdown_pct"] <= 3.0
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedBarHistory": quantitative_pass,
        "requiresLosslessWebSocketForwardTest": True,
        "paperAuthorized": False,
        "liveAuthorized": False,
        "rule": (
            "BTC/ETH validation, test, cost stress and latency stress must all be positive; "
            "test PF>=1.10, at least 30 inventory cycles per instrument, max drawdown<=3%; "
            "bar results never authorize maker execution without a fresh event-level queue/fill test."
        ),
    }


def candidate_payload(score: CandidateScore) -> dict[str, Any]:
    return {**asdict(score), "params": asdict(score.params)}


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    aggregates = payload["aggregates"]
    rows = payload["rows"]
    period = payload["period"]
    decision = payload["decision"]
    lines = [
        "# BTC/ETH VWAP 库存偏斜做市研究",
        "",
        "> 只读探索性 K 线回测；不授权仿真或实盘。",
        "",
        "## 方法与数据",
        "",
        f"- 数据：`{period['start']}` 至 `{period['end']}`，使用 `{payload['bar']}` 完成 K 线。",
        "- 前 50% 只用于参数选择，随后 25% 验证，最后 25% 为已复用历史上的探索性测试。",
        "- 完成 K 线计算滚动 typical-price VWAP；报价从下一根 K 线开始生效，避免同根前视。",
        "- 价格必须穿过限价才计 maker 成交；同根双边均穿过时只保留盯市结果更差的一边。",
        "- 单次报价 2% 权益、最大净库存 10%、无杠杆；库存超时或亏损触发 taker 退出。",
        "- K 线无法恢复队列位置、撤单顺序和真实成交率，因此即使盈利也需要全新 WebSocket 前向验证。",
        "",
        "## 训练选择参数",
        "",
        f"- VWAP 窗口：`{selected['vwap_window']}` 根；锚定权重：`{selected['anchor_weight']:.2f}`。",
        f"- 最小半价差：`{selected['min_half_spread_bps']:.1f}` bps；波动率倍数：`{selected['volatility_multiplier']:.2f}`。",
        f"- 满库存偏斜：`{selected['inventory_skew_bps']:.1f}` bps；VWAP 斜率门槛：`{selected['max_vwap_slope_bps']:.1f}` bps。",
        f"- 成交穿透：`{selected['penetration_bps']:.1f}` bps；库存期限：`{selected['max_inventory_bars']}` 根；库存止损：`{selected['inventory_stop_bps']:.1f}` bps。",
        "",
        "## 分段结果",
        "",
        "| 区间 | 变体 | 中位收益 | 最差收益 | 中位 PF | 最差回撤 | 中位 maker 成交 | 中位库存周期 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in aggregates:
        if item["variant"] == "selected" or item["segment"] == "test":
            lines.append(
                f"| {item['segment']} | {item['variant']} | {item['median_return_pct']:.4f}% | "
                f"{item['worst_return_pct']:.4f}% | {item['median_profit_factor']:.3f} | "
                f"{item['worst_drawdown_pct']:.3f}% | {item['median_maker_fills']:.1f} | "
                f"{item['median_inventory_cycles']:.1f} |"
            )
    lines.extend(
        [
            "",
            "## 测试期逐标的",
            "",
            "| 标的 | 收益 | PF | 回撤 | maker 成交 | 库存周期 | 最大库存 | 止损/超时退出 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        if row["segment"] == "test" and row["variant"] == "selected":
            lines.append(
                f"| {row['inst_id']} | {row['total_return_pct']:.4f}% | {row['profit_factor']:.3f} | "
                f"{row['max_drawdown_pct']:.3f}% | {row['maker_fills']} | {row['inventory_cycles']} | "
                f"{row['max_inventory_pct']:.2f}% | {row['stop_exits']}/{row['timeout_exits']} |"
            )
    lines.extend(
        [
            "",
            "## 决策",
            "",
            f"- 状态：`{decision['status']}`。",
            f"- 复用 K 线历史数量门禁：`{decision['quantitativePassOnReusedBarHistory']}`。",
            "- 无论本次门禁结果如何，都不能据此启动仿真或实盘；下一阶段必须使用足够长的、此前未查看的逐事件 WebSocket 数据验证 maker 排队和成交。",
            "",
            "输出：`summary.json`、`rows.csv`、`test_fills.csv`、`test_inventory_cycles.csv`。",
        ]
    )
    return "\n".join(lines) + "\n"


def resolve_output_dir(value: str) -> Path:
    if not value:
        return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    normalized = []
    for row in rows:
        normalized.append(
            {
                key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(normalized[0]))
        writer.writeheader()
        writer.writerows(normalized)


def iso_time(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000.0, timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
