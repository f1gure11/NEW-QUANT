from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import BAR_MS, Candle, fetch_okx_candle_rows, read_candles_csv, write_candles_csv
from funding_research import FundingPoint, fetch_funding_history, read_funding_csv, write_funding_csv
from gex_strategy import load_snapshot_series
from macro_calendar import macro_calendar_snapshot
from okx_client import OkxRestClient
from strategy_search import multi_horizon_momentum_targets, simulator_volatility_scale
from vwap_market_maker_research import VwapMakerParams, parse_completed_okx_candles, rolling_vwap_features


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "data" / "combined_overlay"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "combined_overlay"
GEX_PATH = PROJECT_ROOT / "data" / "okx" / "gex_snapshots.jsonl"
DEFAULT_INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SPCX-USDT-SWAP")
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class CombinedConfig:
    starting_equity: float = 100_000.0
    allocation_pct: float = 50.0
    target_daily_vol_bps: float = 300.0
    momentum_lookbacks: tuple[int, ...] = (6, 12, 24, 48)
    momentum_vol_window: int = 48
    momentum_threshold_sigma: float = 0.1
    momentum_min_votes: int = 2
    quote_notional_pct: float = 10.0
    max_passive_bars: int = 6
    min_rebalance_pct: float = 0.5
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    taker_slippage_bps: float = 1.0
    holding_cost_bps_per_day: float = 0.5
    funding_cost_threshold_bps: float = 1.0
    funding_multiplier: float = 0.5
    funding_max_age_hours: float = 12.0
    gex_risk_multiplier: float = 0.5
    gex_max_age_hours: float = 6.0
    macro_multiplier: float = 0.25
    macro_window_minutes: float = 60.0

    def __post_init__(self) -> None:
        if self.starting_equity <= 0:
            raise ValueError("starting equity must be positive")
        if not 0 < self.allocation_pct <= 100 or not 0 < self.quote_notional_pct <= 100:
            raise ValueError("allocation and quote percentages must be in (0, 100]")
        if self.max_passive_bars < 1 or self.momentum_min_votes < 1:
            raise ValueError("holding and vote counts must be positive")
        if not self.momentum_lookbacks or min(self.momentum_lookbacks) < 1:
            raise ValueError("momentum lookbacks must be positive")
        for value in (self.funding_multiplier, self.gex_risk_multiplier, self.macro_multiplier):
            if not 0 <= value <= 1:
                raise ValueError("risk multipliers must be in [0, 1]")
        nonnegative = (
            self.target_daily_vol_bps,
            self.momentum_threshold_sigma,
            self.min_rebalance_pct,
            self.maker_fee_bps,
            self.taker_fee_bps,
            self.taker_slippage_bps,
            self.holding_cost_bps_per_day,
            self.funding_cost_threshold_bps,
            self.funding_max_age_hours,
            self.gex_max_age_hours,
            self.macro_window_minutes,
        )
        if min(nonnegative) < 0:
            raise ValueError("cost, threshold, and age settings cannot be negative")


@dataclass(frozen=True, slots=True)
class Variant:
    name: str
    execution: str
    funding_filter: bool = False
    gex_filter: bool = False
    macro_filter: bool = False
    latency_bars: int = 0
    cost_stress: bool = False


@dataclass(frozen=True, slots=True)
class PreparedMomentum:
    sides: list[int]
    volatility_scales: list[float]
    hourly_bars: int


@dataclass(frozen=True, slots=True)
class OverlayDecision:
    multiplier: float
    funding_reduced: bool
    gex_fresh: bool
    gex_reduced: bool
    macro_reduced: bool


@dataclass(frozen=True, slots=True)
class CombinedFill:
    ts: int
    side: str
    role: str
    price: float
    quantity: float
    fee: float
    realized_pnl: float
    position_after: float


@dataclass(frozen=True, slots=True)
class DirectionCycle:
    entry_ts: int
    exit_ts: int
    side: int
    exit_reason: str
    net_pnl: float
    bars_held: int


@dataclass(frozen=True, slots=True)
class CombinedResult:
    start: str
    end: str
    starting_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    direction_cycles: int
    profitable_cycles: int
    maker_fills: int
    taker_fills: int
    passive_timeouts: int
    signal_changes: int
    exposure_pct: float
    average_abs_target_pct: float
    average_abs_position_pct: float
    tracking_error_pct: float
    fees: float
    funding_pnl: float
    holding_cost: float
    funding_reduced_bars: int
    gex_fresh_bars: int
    gex_reduced_bars: int
    macro_reduced_bars: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only multi-horizon momentum plus VWAP/risk-overlay research."
    )
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--bar", default="5m", choices=list(BAR_MS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=48)
    parser.add_argument("--funding-limit", type=int, default=100)
    parser.add_argument("--funding-pages", type=int, default=2)
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--gex-path", default=str(GEX_PATH))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--refresh-funding", action="store_true")
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instruments = tuple(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    config = CombinedConfig()
    histories, candle_sources = load_candles(args, instruments)
    histories = align_common_histories(histories)
    if any(len(histories.get(inst_id, [])) < 4_000 for inst_id in instruments):
        raise SystemExit("At least 4,000 common completed candles per instrument are required")
    funding, funding_sources = load_funding(args, instruments)
    gex_by_underlying = load_snapshot_series(Path(args.gex_path))
    macro_times = macro_event_times()
    segments, period = chronological_boundaries(histories, instruments)
    vwap_params = VwapMakerParams(
        vwap_window=288,
        anchor_weight=0.5,
        min_half_spread_bps=10.0,
        volatility_multiplier=1.0,
        inventory_skew_bps=10.0,
        max_vwap_slope_bps=50.0,
    )
    variants = research_variants()

    prepared = {
        inst_id: {
            "momentum": prepare_hourly_momentum(candles, config),
            "vwap": rolling_vwap_features(candles, vwap_params),
        }
        for inst_id, candles in histories.items()
    }
    rows: list[dict[str, Any]] = []
    test_fills: list[dict[str, Any]] = []
    test_cycles: list[dict[str, Any]] = []
    for inst_id in instruments:
        candles = histories[inst_id]
        underlying = inst_id.split("-", 1)[0]
        for segment, (start, end) in segments.items():
            for variant in variants:
                result, fills, cycles = simulate_combined(
                    candles,
                    start,
                    end,
                    prepared[inst_id]["momentum"],
                    prepared[inst_id]["vwap"],
                    funding.get(inst_id, []),
                    gex_by_underlying.get(underlying, []),
                    macro_times,
                    config,
                    vwap_params,
                    variant,
                    bar_ms=BAR_MS[args.bar],
                    record_details=segment == "test" and variant.name == "combined",
                )
                rows.append(result_row(inst_id, segment, variant.name, result))
                if segment == "test" and variant.name == "combined":
                    test_fills.extend({"inst_id": inst_id, **asdict(item)} for item in fills)
                    test_cycles.extend({"inst_id": inst_id, **asdict(item)} for item in cycles)

    aggregates = aggregate_rows(rows)
    decision = decision_payload(rows, aggregates)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_layered_momentum_vwap_risk_overlay_research",
        "instruments": list(instruments),
        "bar": args.bar,
        "period": period,
        "sampleCounts": {inst_id: len(rows_) for inst_id, rows_ in histories.items()},
        "candleSources": candle_sources,
        "fundingSources": funding_sources,
        "gexSource": str(args.gex_path),
        "config": {**asdict(config), "momentum_lookbacks": list(config.momentum_lookbacks)},
        "vwapExecutionParameters": asdict(vwap_params),
        "variants": [asdict(item) for item in variants],
        "dataBoundaries": {
            "reusedHistory": True,
            "gexCoverage": "BTC/ETH point-in-time snapshots begin 2026-07-24; unavailable/stale GEX is neutral",
            "funding": "public historical realized funding known no earlier than its timestamp",
            "macro": "reviewed schedule only; no surprise/consensus data",
            "maker": "5m trade-through proxy without queue priority",
        },
        "rows": rows,
        "aggregates": aggregates,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "test_combined_fills.csv", test_fills)
    write_csv(output_dir / "test_combined_cycles.csv", test_cycles)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"decision={json.dumps(decision, sort_keys=True)}")
    lookup = {(row['segment'], row['variant']): row for row in aggregates}
    for segment in ("train", "validation", "test", "full"):
        for variant in ("momentum_taker", "momentum_vwap", "combined"):
            item = lookup[(segment, variant)]
            print(
                f"segment={segment} variant={variant} "
                f"median_return={item['median_return_pct']:.6f}% "
                f"worst_return={item['worst_return_pct']:.6f}% "
                f"median_pf={item['median_profit_factor']:.4f}"
            )
    return 0


def research_variants() -> tuple[Variant, ...]:
    return (
        Variant("momentum_taker", "taker"),
        Variant("momentum_vwap", "vwap"),
        Variant("combined_no_gex", "vwap", funding_filter=True, macro_filter=True),
        Variant("combined", "vwap", funding_filter=True, gex_filter=True, macro_filter=True),
        Variant(
            "combined_cost_stress",
            "vwap",
            funding_filter=True,
            gex_filter=True,
            macro_filter=True,
            cost_stress=True,
        ),
        Variant(
            "combined_one_bar_latency",
            "vwap",
            funding_filter=True,
            gex_filter=True,
            macro_filter=True,
            latency_bars=1,
        ),
    )


def load_candles(
    args: argparse.Namespace, instruments: tuple[str, ...]
) -> tuple[dict[str, list[Candle]], dict[str, str]]:
    root = Path(args.data_root) / "candles"
    root.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.pages <= 1 else f"x{args.pages}"
    client = OkxRestClient()
    histories: dict[str, list[Candle]] = {}
    sources: dict[str, str] = {}
    for inst_id in instruments:
        path = root / f"{inst_id}_{args.bar}_{args.limit}{suffix}.csv"
        if path.exists() and not args.refresh:
            candles = read_candles_csv(path)
        else:
            raw = fetch_okx_candle_rows(client, inst_id, args.bar, args.limit, max(1, args.pages))
            candles = parse_completed_okx_candles(raw, args.bar)
            write_candles_csv(path, candles)
            time.sleep(0.25)
        histories[inst_id] = candles
        sources[inst_id] = str(path)
    return histories, sources


def load_funding(
    args: argparse.Namespace, instruments: tuple[str, ...]
) -> tuple[dict[str, list[FundingPoint]], dict[str, str]]:
    root = Path(args.data_root) / "funding"
    root.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.funding_pages <= 1 else f"x{args.funding_pages}"
    client = OkxRestClient()
    result: dict[str, list[FundingPoint]] = {}
    sources: dict[str, str] = {}
    for inst_id in instruments:
        path = root / f"{inst_id}_funding_{args.funding_limit}{suffix}.csv"
        if path.exists() and not args.refresh_funding:
            points = read_funding_csv(path)
        else:
            points = fetch_funding_history(
                client,
                inst_id,
                limit=args.funding_limit,
                pages=max(1, args.funding_pages),
                sleep=0.25,
            )
            write_funding_csv(path, points)
        result[inst_id] = points
        sources[inst_id] = str(path)
    return result, sources


def align_common_histories(histories: dict[str, list[Candle]]) -> dict[str, list[Candle]]:
    if not histories or any(not rows for rows in histories.values()):
        return histories
    common = set.intersection(*(set(candle.ts for candle in rows) for rows in histories.values()))
    return {
        inst_id: [candle for candle in rows if candle.ts in common]
        for inst_id, rows in histories.items()
    }


def chronological_boundaries(
    histories: dict[str, list[Candle]], instruments: tuple[str, ...]
) -> tuple[dict[str, tuple[int, int]], dict[str, str]]:
    count = min(len(histories[inst_id]) for inst_id in instruments)
    train_end = count // 2
    validation_end = train_end + count // 4
    reference = histories[instruments[0]]
    return (
        {
            "train": (0, train_end),
            "validation": (train_end, validation_end),
            "test": (validation_end, count),
            "full": (0, count),
        },
        {
            "start": iso_time(reference[0].ts),
            "trainEnd": iso_time(reference[train_end - 1].ts),
            "validationEnd": iso_time(reference[validation_end - 1].ts),
            "end": iso_time(reference[count - 1].ts),
        },
    )


def aggregate_complete_hours(candles: list[Candle]) -> tuple[list[Candle], dict[int, int]]:
    buckets: dict[int, list[Candle]] = {}
    for candle in candles:
        bucket = candle.ts // BAR_MS["1H"] * BAR_MS["1H"]
        buckets.setdefault(bucket, []).append(candle)
    hourly: list[Candle] = []
    bucket_to_index: dict[int, int] = {}
    for bucket, rows in sorted(buckets.items()):
        rows.sort(key=lambda item: item.ts)
        if len(rows) != 12 or rows[0].ts != bucket or rows[-1].ts != bucket + 55 * 60_000:
            continue
        if any(rows[index].ts - rows[index - 1].ts != BAR_MS["5m"] for index in range(1, 12)):
            continue
        hourly.append(
            Candle(
                ts=bucket,
                open=rows[0].open,
                high=max(row.high for row in rows),
                low=min(row.low for row in rows),
                close=rows[-1].close,
                volume=sum((row.volume for row in rows), rows[0].volume * 0),
            )
        )
        bucket_to_index[bucket] = len(hourly) - 1
    return hourly, bucket_to_index


def prepare_hourly_momentum(candles: list[Candle], config: CombinedConfig) -> PreparedMomentum:
    hourly, mapping = aggregate_complete_hours(candles)
    targets = multi_horizon_momentum_targets(
        [float(candle.close) for candle in hourly],
        list(config.momentum_lookbacks),
        config.momentum_vol_window,
        config.momentum_threshold_sigma,
        config.momentum_min_votes,
    )
    scales = [
        simulator_volatility_scale(
            hourly,
            index,
            {
                "target_daily_vol_bps": config.target_daily_vol_bps,
                "vol_window_bars": config.momentum_vol_window,
            },
        )
        for index in range(len(hourly))
    ]
    sides_by_bar = [0] * len(candles)
    scales_by_bar = [0.0] * len(candles)
    for index, candle in enumerate(candles):
        bucket = candle.ts // BAR_MS["1H"] * BAR_MS["1H"]
        hour_index = mapping.get(bucket)
        if hour_index is None:
            continue
        sides_by_bar[index] = targets[hour_index]
        scales_by_bar[index] = scales[hour_index] if targets[hour_index] else 0.0
    return PreparedMomentum(sides_by_bar, scales_by_bar, len(hourly))


def macro_event_times() -> list[int]:
    snapshot = macro_calendar_snapshot(now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    result = []
    for event in snapshot.get("events", []):
        try:
            result.append(
                int(
                    datetime.fromisoformat(str(event["scheduledAt"]).replace("Z", "+00:00")).timestamp()
                    * 1000
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result)


def point_before(points: list[Any], timestamp: int, *, timestamp_key: Any) -> Any | None:
    if not points:
        return None
    timestamps = [int(timestamp_key(item)) for item in points]
    index = bisect.bisect_right(timestamps, timestamp) - 1
    return points[index] if index >= 0 else None


def overlay_decision(
    *,
    side: int,
    price: float,
    timestamp: int,
    funding: list[FundingPoint],
    gex: list[tuple[int, dict[str, Any]]],
    macro_times: list[int],
    config: CombinedConfig,
    use_funding: bool,
    use_gex: bool,
    use_macro: bool,
) -> OverlayDecision:
    if not side:
        return OverlayDecision(0.0, False, False, False, False)
    multiplier = 1.0
    funding_reduced = False
    gex_fresh = False
    gex_reduced = False
    macro_reduced = False

    if use_funding:
        point = point_before(funding, timestamp, timestamp_key=lambda item: item.ts)
        if point is not None and timestamp - point.ts <= config.funding_max_age_hours * 3_600_000:
            costly_bps = side * float(point.realized_rate) * 10_000.0
            if costly_bps > config.funding_cost_threshold_bps:
                multiplier *= config.funding_multiplier
                funding_reduced = True

    if use_gex:
        point = point_before(gex, timestamp, timestamp_key=lambda item: item[0])
        if point is not None and timestamp - int(point[0]) <= config.gex_max_age_hours * 3_600_000:
            gex_fresh = True
            row = point[1]
            net_gex = finite_number(row.get("netGex"))
            call_wall = wall_strike(row, "callWall")
            put_wall = wall_strike(row, "putWall")
            outside_walls = call_wall > 0 and put_wall > 0 and not (put_wall <= price <= call_wall)
            if net_gex < 0 or outside_walls:
                multiplier *= config.gex_risk_multiplier
                gex_reduced = True

    if use_macro and macro_times:
        window = config.macro_window_minutes * 60_000
        insertion = bisect.bisect_left(macro_times, timestamp)
        neighbors = macro_times[max(0, insertion - 1) : min(len(macro_times), insertion + 1)]
        if any(abs(timestamp - event_ts) <= window for event_ts in neighbors):
            multiplier *= config.macro_multiplier
            macro_reduced = True

    return OverlayDecision(multiplier, funding_reduced, gex_fresh, gex_reduced, macro_reduced)


def simulate_combined(
    candles: list[Candle],
    start: int,
    end: int,
    momentum: PreparedMomentum,
    vwap_features: list[Any],
    funding: list[FundingPoint],
    gex: list[tuple[int, dict[str, Any]]],
    macro_times: list[int],
    config: CombinedConfig,
    vwap_params: VwapMakerParams,
    variant: Variant,
    *,
    bar_ms: int,
    record_details: bool = False,
) -> tuple[CombinedResult, list[CombinedFill], list[DirectionCycle]]:
    if not 0 <= start < end <= len(candles):
        raise ValueError("invalid simulation segment")
    if len(momentum.sides) != len(candles) or len(vwap_features) != len(candles):
        raise ValueError("prepared signal lengths must match candles")

    maker_fee = max(5.0, config.maker_fee_bps * 2.5) if variant.cost_stress else config.maker_fee_bps
    taker_fee = max(8.0, config.taker_fee_bps * 1.6) if variant.cost_stress else config.taker_fee_bps
    taker_slippage = max(2.0, config.taker_slippage_bps * 2.0) if variant.cost_stress else config.taker_slippage_bps
    penetration = max(2.0, vwap_params.penetration_bps) if variant.cost_stress else vwap_params.penetration_bps
    holding_rate = (
        max(1.0, config.holding_cost_bps_per_day * 2.0)
        if variant.cost_stress
        else config.holding_cost_bps_per_day
    )
    funding_by_ts = {point.ts: point.realized_rate for point in funding}

    cash = config.starting_equity
    position = 0.0
    average_price = 0.0
    target_position = 0.0
    last_target_fraction: float | None = None
    pending_since: int | None = None
    pending_direction = 0
    peak_equity = cash
    max_drawdown = 0.0
    total_fees = 0.0
    funding_pnl = 0.0
    holding_cost = 0.0
    maker_fills = 0
    taker_fills = 0
    passive_timeouts = 0
    signal_changes = 0
    exposure_bars = 0
    target_pct_sum = 0.0
    position_pct_sum = 0.0
    tracking_pct_sum = 0.0
    funding_reduced_bars = 0
    gex_fresh_bars = 0
    gex_reduced_bars = 0
    macro_reduced_bars = 0
    fills: list[CombinedFill] = []
    cycles: list[DirectionCycle] = []
    cycle_side = 0
    cycle_entry_ts = 0
    cycle_entry_index = 0
    cycle_net = 0.0

    def marked_equity(price: float) -> float:
        return cash + (price - average_price) * position if abs(position) > EPSILON else cash

    def begin_cycle(index: int, side: int) -> None:
        nonlocal cycle_side, cycle_entry_ts, cycle_entry_index, cycle_net
        cycle_side = side
        cycle_entry_ts = candles[index].ts
        cycle_entry_index = index
        cycle_net = 0.0

    def finish_cycle(index: int, reason: str) -> None:
        nonlocal cycle_side, cycle_entry_ts, cycle_entry_index, cycle_net
        if not cycle_side:
            return
        cycles.append(
            DirectionCycle(
                entry_ts=cycle_entry_ts,
                exit_ts=candles[index].ts,
                side=cycle_side,
                exit_reason=reason,
                net_pnl=cycle_net,
                bars_held=max(0, index - cycle_entry_index),
            )
        )
        cycle_side = 0
        cycle_entry_ts = 0
        cycle_entry_index = 0
        cycle_net = 0.0

    def execute_leg(index: int, signed_quantity: float, price: float, role: str, fee_bps: float) -> None:
        nonlocal cash, position, average_price, cycle_net, total_fees, maker_fills, taker_fills
        if abs(signed_quantity) <= EPSILON:
            return
        side = 1 if signed_quantity > 0 else -1
        quantity = abs(signed_quantity)
        if abs(position) <= EPSILON:
            begin_cycle(index, side)
            fee = quantity * price * fee_bps / 10_000.0
            cash -= fee
            cycle_net -= fee
            total_fees += fee
            position = signed_quantity
            average_price = price
            realized = 0.0
        elif position * signed_quantity > 0:
            fee = quantity * price * fee_bps / 10_000.0
            cash -= fee
            cycle_net -= fee
            total_fees += fee
            average_price = (
                abs(position) * average_price + quantity * price
            ) / (abs(position) + quantity)
            position += signed_quantity
            realized = 0.0
        else:
            close_quantity = min(abs(position), quantity)
            close_signed = -math.copysign(close_quantity, position)
            close_fee = close_quantity * price * fee_bps / 10_000.0
            realized = (price - average_price) * close_quantity * (1.0 if position > 0 else -1.0)
            cash += realized - close_fee
            cycle_net += realized - close_fee
            total_fees += close_fee
            position += close_signed
            remaining = quantity - close_quantity
            if abs(position) <= EPSILON:
                position = 0.0
                average_price = 0.0
                finish_cycle(index, role)
            if remaining > EPSILON:
                begin_cycle(index, side)
                open_fee = remaining * price * fee_bps / 10_000.0
                cash -= open_fee
                cycle_net -= open_fee
                total_fees += open_fee
                position = side * remaining
                average_price = price
                close_fee += open_fee
            fee = close_fee
        if role == "maker":
            maker_fills += 1
        else:
            taker_fills += 1
        if record_details:
            fills.append(
                CombinedFill(
                    ts=candles[index].ts,
                    side="buy" if signed_quantity > 0 else "sell",
                    role=role,
                    price=price,
                    quantity=quantity,
                    fee=fee,
                    realized_pnl=realized,
                    position_after=position,
                )
            )

    def execute_order(index: int, signed_quantity: float, price: float, role: str, fee_bps: float) -> None:
        execute_leg(index, signed_quantity, price, role, fee_bps)

    for index in range(start, end):
        candle = candles[index]
        open_price = float(candle.open)
        close = float(candle.close)
        if abs(position) > EPSILON and candle.ts in funding_by_ts:
            pnl = -position * open_price * funding_by_ts[candle.ts]
            cash += pnl
            cycle_net += pnl
            funding_pnl += pnl

        signal_index = max(0, index - variant.latency_bars)
        side = momentum.sides[signal_index]
        vol_scale = momentum.volatility_scales[signal_index]
        overlay = overlay_decision(
            side=side,
            price=open_price,
            timestamp=candle.ts,
            funding=funding,
            gex=gex,
            macro_times=macro_times,
            config=config,
            use_funding=variant.funding_filter,
            use_gex=variant.gex_filter,
            use_macro=variant.macro_filter,
        )
        funding_reduced_bars += int(overlay.funding_reduced)
        gex_fresh_bars += int(overlay.gex_fresh)
        gex_reduced_bars += int(overlay.gex_reduced)
        macro_reduced_bars += int(overlay.macro_reduced)
        target_fraction = side * config.allocation_pct / 100.0 * vol_scale * overlay.multiplier
        equity_at_open = max(EPSILON, marked_equity(open_price))
        if last_target_fraction is None or not math.isclose(target_fraction, last_target_fraction, abs_tol=1e-12):
            target_position = target_fraction * equity_at_open / open_price
            if last_target_fraction is not None and math.copysign(1.0, target_fraction or 1.0) != math.copysign(1.0, last_target_fraction or 1.0):
                signal_changes += 1
            last_target_fraction = target_fraction

        difference = target_position - position
        minimum_quantity = config.min_rebalance_pct / 100.0 * equity_at_open / open_price
        if abs(difference) <= minimum_quantity:
            pending_since = None
            pending_direction = 0
        elif variant.execution == "taker":
            slip = taker_slippage / 10_000.0
            fill_price = open_price * (1.0 + slip if difference > 0 else 1.0 - slip)
            execute_order(index, difference, fill_price, "taker_rebalance", taker_fee)
            pending_since = None
            pending_direction = 0
        else:
            direction = 1 if difference > 0 else -1
            if pending_since is None or direction != pending_direction:
                pending_since = index
                pending_direction = direction
            if pending_since is not None and index - pending_since >= config.max_passive_bars:
                slip = taker_slippage / 10_000.0
                fill_price = open_price * (1.0 + slip if difference > 0 else 1.0 - slip)
                execute_order(index, difference, fill_price, "passive_timeout", taker_fee)
                passive_timeouts += 1
                pending_since = None
                pending_direction = 0
            else:
                feature_index = index - 1 - variant.latency_bars
                feature = vwap_features[feature_index] if feature_index >= 0 else None
                if feature is not None:
                    fair = open_price + vwap_params.anchor_weight * (feature.vwap - open_price)
                    half = feature.half_spread_bps / 10_000.0
                    guard = 0.01 / 10_000.0
                    max_quantity = config.quote_notional_pct / 100.0 * equity_at_open / open_price
                    quantity = min(abs(difference), max_quantity)
                    if difference > 0:
                        price = min(fair * (1.0 - half), open_price * (1.0 - guard))
                        touched = float(candle.low) <= price * (1.0 - penetration / 10_000.0)
                        signed_quantity = quantity
                    else:
                        price = max(fair * (1.0 + half), open_price * (1.0 + guard))
                        touched = float(candle.high) >= price * (1.0 + penetration / 10_000.0)
                        signed_quantity = -quantity
                    if touched and quantity > EPSILON:
                        execute_order(index, signed_quantity, price, "maker", maker_fee)
                        remaining = target_position - position
                        if abs(remaining) <= minimum_quantity:
                            pending_since = None
                            pending_direction = 0

        if abs(position) > EPSILON:
            exposure_bars += 1
            cost = (
                abs(position)
                * close
                * holding_rate
                / 10_000.0
                * bar_ms
                / 86_400_000.0
            )
            cash -= cost
            cycle_net -= cost
            holding_cost += cost

        equity = marked_equity(close)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100.0)
        target_pct_sum += abs(target_position) * close / max(equity, EPSILON) * 100.0
        position_pct_sum += abs(position) * close / max(equity, EPSILON) * 100.0
        tracking_pct_sum += abs(target_position - position) * close / max(equity, EPSILON) * 100.0

    if abs(position) > EPSILON:
        index = end - 1
        close = float(candles[index].close)
        slip = taker_slippage / 10_000.0
        signed_quantity = -position
        fill_price = close * (1.0 + slip if signed_quantity > 0 else 1.0 - slip)
        execute_order(index, signed_quantity, fill_price, "terminal_exit", taker_fee)

    final_equity = cash
    peak_equity = max(peak_equity, final_equity)
    if peak_equity > 0:
        max_drawdown = max(max_drawdown, (peak_equity - final_equity) / peak_equity * 100.0)
    gross_profit = sum(max(0.0, cycle.net_pnl) for cycle in cycles)
    gross_loss = abs(sum(min(0.0, cycle.net_pnl) for cycle in cycles))
    bars = end - start
    result = CombinedResult(
        start=iso_time(candles[start].ts),
        end=iso_time(candles[end - 1].ts),
        starting_equity=config.starting_equity,
        final_equity=final_equity,
        total_return_pct=(final_equity / config.starting_equity - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown,
        profit_factor=gross_profit / gross_loss if gross_loss > EPSILON else (999.0 if gross_profit > 0 else 0.0),
        direction_cycles=len(cycles),
        profitable_cycles=sum(cycle.net_pnl > 0 for cycle in cycles),
        maker_fills=maker_fills,
        taker_fills=taker_fills,
        passive_timeouts=passive_timeouts,
        signal_changes=signal_changes,
        exposure_pct=exposure_bars / max(1, bars) * 100.0,
        average_abs_target_pct=target_pct_sum / max(1, bars),
        average_abs_position_pct=position_pct_sum / max(1, bars),
        tracking_error_pct=tracking_pct_sum / max(1, bars),
        fees=total_fees,
        funding_pnl=funding_pnl,
        holding_cost=holding_cost,
        funding_reduced_bars=funding_reduced_bars,
        gex_fresh_bars=gex_fresh_bars,
        gex_reduced_bars=gex_reduced_bars,
        macro_reduced_bars=macro_reduced_bars,
    )
    return result, fills, cycles


def finite_number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def wall_strike(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    return finite_number(value.get("strike")) if isinstance(value, dict) else 0.0


def result_row(inst_id: str, segment: str, variant: str, result: CombinedResult) -> dict[str, Any]:
    return {"inst_id": inst_id, "segment": segment, "variant": variant, **asdict(result)}


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["segment"]), str(row["variant"])), []).append(row)
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
                "median_profit_factor": statistics.median(float(item["profit_factor"]) for item in items),
                "worst_drawdown_pct": max(float(item["max_drawdown_pct"]) for item in items),
                "median_cycles": statistics.median(float(item["direction_cycles"]) for item in items),
                "median_fees": statistics.median(float(item["fees"]) for item in items),
                "median_tracking_error_pct": statistics.median(float(item["tracking_error_pct"]) for item in items),
            }
        )
    order = {"train": 0, "validation": 1, "test": 2, "full": 3}
    result.sort(key=lambda item: (order.get(str(item["segment"]), 9), str(item["variant"])))
    return result


def decision_payload(rows: list[dict[str, Any]], aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = {(row["segment"], row["variant"]): row for row in aggregates}
    validation = lookup[("validation", "combined")]
    test = lookup[("test", "combined")]
    stress = lookup[("test", "combined_cost_stress")]
    latency = lookup[("test", "combined_one_bar_latency")]
    baseline = lookup[("test", "momentum_taker")]
    instrument_rows = [
        row for row in rows if row["segment"] == "test" and row["variant"] == "combined"
    ]
    quantitative_pass = (
        validation["positive"] == validation["count"]
        and test["positive"] == test["count"]
        and stress["positive"] == stress["count"]
        and latency["positive"] == latency["count"]
        and all(float(row["profit_factor"]) >= 1.10 for row in instrument_rows)
        and all(int(row["direction_cycles"]) >= 10 for row in instrument_rows)
        and test["worst_drawdown_pct"] <= 3.0
        and test["median_return_pct"] >= baseline["median_return_pct"]
    )
    return {
        "status": "research_only",
        "quantitativePassOnReusedHistory": quantitative_pass,
        "paperAuthorized": False,
        "liveAuthorized": False,
        "requiresFreshWalkForward": True,
        "rule": (
            "combined validation/test/cost/latency must be positive on every instrument, "
            "test PF>=1.10 and >=10 direction cycles per instrument, max drawdown<=3%, "
            "and combined median return must not trail direct momentum"
        ),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    aggregates = payload["aggregates"]
    rows = payload["rows"]
    period = payload["period"]
    decision = payload["decision"]
    lines = [
        "# 动量 + VWAP 执行 + 风险覆盖组合回测",
        "",
        "> 只读探索性研究；复用历史，不授权仿真或实盘。",
        "",
        "## 固定结构",
        "",
        "- 主 Alpha：1H 多周期动量 `6/12/24/48`，至少两票，阈值 0.1 sigma。",
        "- 仓位：目标日波动 300 bps，单标的最大 50% 权益，无杠杆。",
        "- 执行：5m、24h rolling VWAP、50% 锚定、10 bps 最小半价差；只向目标仓位方向挂单。",
        "- 每根最多执行 10% 权益；30 分钟未完成则 taker 补齐。",
        "- Funding、GEX 和宏观事件只会减仓，不会反向或加杠杆。",
        f"- 数据：`{period['start']}` 至 `{period['end']}`。",
        "",
        "## 分段与消融",
        "",
        "| 区间 | 变体 | 中位收益 | 最差收益 | 中位 PF | 最差回撤 | 中位周期 | 中位费用 | 跟踪误差 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in aggregates:
        lines.append(
            f"| {item['segment']} | {item['variant']} | {item['median_return_pct']:.4f}% | "
            f"{item['worst_return_pct']:.4f}% | {item['median_profit_factor']:.3f} | "
            f"{item['worst_drawdown_pct']:.3f}% | {item['median_cycles']:.1f} | "
            f"{item['median_fees']:.2f} | {item['median_tracking_error_pct']:.3f}% |"
        )
    lines.extend(
        [
            "",
            "## 测试期完整组合逐标的",
            "",
            "| 标的 | 收益 | PF | 回撤 | 周期 | Maker/Taker | GEX覆盖/减仓 | Funding减仓 | 宏观减仓 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        if row["segment"] == "test" and row["variant"] == "combined":
            lines.append(
                f"| {row['inst_id']} | {row['total_return_pct']:.4f}% | {row['profit_factor']:.3f} | "
                f"{row['max_drawdown_pct']:.3f}% | {row['direction_cycles']} | "
                f"{row['maker_fills']}/{row['taker_fills']} | "
                f"{row['gex_fresh_bars']}/{row['gex_reduced_bars']} | "
                f"{row['funding_reduced_bars']} | {row['macro_reduced_bars']} |"
            )
    lines.extend(
        [
            "",
            "## 决策",
            "",
            f"- 状态：`{decision['status']}`。",
            f"- 复用历史数量门禁：`{decision['quantitativePassOnReusedHistory']}`。",
            "- GEX 从 2026-07-24 才有 BTC/ETH 点时历史；SPCX 无可用 GEX 时保持中性。",
            "- K 线 maker 成交仍不能描述队列位置；任何通过结果都必须重新做全新 walk-forward 与事件级成交测试。",
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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def iso_time(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000.0, timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
