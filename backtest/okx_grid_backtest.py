from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from pathlib import Path
from typing import Any

from okx_client import OkxApiError, OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "backtest"
REPORT_DIR = PROJECT_ROOT / "reports" / "backtests"
BAR_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1H": 3_600_000,
    "2H": 7_200_000,
    "4H": 14_400_000,
    "1D": 86_400_000,
}


@dataclass(slots=True)
class Candle:
    ts: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(slots=True)
class GridBacktestConfig:
    inst_id: str = "BEAT-USDT-SWAP"
    bar: str = "1m"
    limit: int = 300
    lower: Decimal = Decimal("2.10")
    upper: Decimal = Decimal("2.30")
    leverage: Decimal = Decimal("3")
    grid_bps: Decimal = Decimal("25")
    soft_bps: Decimal = Decimal("45")
    hard_bps: Decimal = Decimal("80")
    order_sz: Decimal = Decimal("0.1")
    max_position: Decimal = Decimal("0.6")
    max_open_orders_per_side: int = 2
    max_actions_per_bar: int = 4
    mode: str = "adaptive"
    adaptive_width_bps: Decimal = Decimal("520")
    adaptive_min_width_bps: Decimal = Decimal("320")
    adaptive_max_width_bps: Decimal = Decimal("1000")
    adaptive_vol_multiplier: Decimal = Decimal("12")
    range_drift_mode: str = "cooldown"
    range_drift_weight_bps: Decimal = Decimal("5000")
    range_drift_max_bps: Decimal = Decimal("500")
    one_way_open: bool = True
    maker_fee_bps: Decimal = Decimal("2")
    taker_fee_bps: Decimal = Decimal("5")
    slippage_bps: Decimal = Decimal("2")
    starting_equity: Decimal = Decimal("100")
    ct_val: Decimal = Decimal("1")
    tick_sz: Decimal = Decimal("0.0001")
    lot_sz: Decimal = Decimal("0.1")
    min_sz: Decimal = Decimal("0.1")
    min_tp_bps: Decimal = Decimal("160")
    total_loss_sl_pct: Decimal = Decimal("3")
    total_loss_sl_cap: Decimal = Decimal("0.5")
    position_loss_sl_bps: Decimal = Decimal("550")
    risk_cooldown_bars: int = 10
    regime_filter: str = "ma_cross"
    regime_bar: str = "15m"
    regime_short_ma: int = 5
    regime_long_ma: int = 20
    regime_diff_bps: Decimal = Decimal("50")
    regime_confirm_bars: int = 3
    trend_filter: str = "off"
    trend_lookback: int = 8
    trend_threshold_bps: Decimal = Decimal("90")


@dataclass(slots=True)
class Position:
    size: Decimal = Decimal("0")
    avg_px: Decimal = Decimal("0")


@dataclass(slots=True)
class SimOrder:
    side: str
    pos_side: str
    price: Decimal
    size: Decimal
    reduce_only: bool
    tag: str


@dataclass(slots=True)
class Fill:
    ts: int
    side: str
    pos_side: str
    price: Decimal
    size: Decimal
    fee: Decimal
    realized_pnl: Decimal
    tag: str
    equity: Decimal


@dataclass(slots=True)
class BacktestResult:
    config: dict[str, Any]
    bars: int
    start_time: str
    end_time: str
    starting_equity: Decimal
    final_equity: Decimal
    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    realized_pnl: Decimal
    fees: Decimal
    fills: int
    wins: int
    losses: int
    win_rate_pct: Decimal
    profit_factor: Decimal
    risk_events: int
    output_dir: str


def main() -> int:
    args = parse_args()
    config = config_from_args(args)
    candles = load_or_fetch_candles(args, config)
    if len(candles) < max(30, config.regime_long_ma + 5):
        raise SystemExit(f"Not enough candles for backtest: {len(candles)}")

    result, fills, equity_curve = run_grid_backtest(candles, config)
    output_dir = write_outputs(result, fills, equity_curve, args.output_dir)
    print_summary(result, output_dir)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest the OKX adaptive grid bot on historical candles.")
    parser.add_argument("--inst-id", default="BEAT-USDT-SWAP")
    parser.add_argument("--bar", default="1m", choices=["1m", "3m", "5m", "15m", "30m", "1H", "2H", "4H", "1D"])
    parser.add_argument("--limit", type=int, default=300, help="Number of candles to fetch or read from cache.")
    parser.add_argument("--pages", type=int, default=1, help="Number of historical candle pages to fetch. Each page uses --limit.")
    parser.add_argument("--refresh", action="store_true", help="Fetch fresh public OKX candles instead of cache.")
    parser.add_argument("--input-csv", default="", help="Use a local candle CSV instead of OKX public candles.")
    parser.add_argument("--output-dir", default="", help="Optional output directory under reports/backtests.")
    parser.add_argument("--runtime-config", default="", help="Load strategy values from a dashboard runtime config JSON.")

    parser.add_argument("--lower", default="2.10")
    parser.add_argument("--upper", default="2.30")
    parser.add_argument("--leverage", default="3")
    parser.add_argument("--grid-bps", default="25")
    parser.add_argument("--soft-bps", default="45")
    parser.add_argument("--hard-bps", default="80")
    parser.add_argument("--order-sz", default="0.1")
    parser.add_argument("--max-position", default="0.6")
    parser.add_argument("--max-open-orders-per-side", type=int, default=2)
    parser.add_argument("--max-actions-per-bar", type=int, default=4)
    parser.add_argument("--mode", choices=["fixed", "adaptive"], default="adaptive")
    parser.add_argument("--adaptive-width-bps", default="520")
    parser.add_argument("--adaptive-min-width-bps", default="320")
    parser.add_argument("--adaptive-max-width-bps", default="1000")
    parser.add_argument("--adaptive-vol-multiplier", default="12")
    parser.add_argument("--range-drift-weight-bps", default="5000")
    parser.add_argument("--range-drift-max-bps", default="500")
    parser.add_argument("--allow-dual-open", dest="one_way_open", action="store_false")
    parser.set_defaults(one_way_open=True)

    parser.add_argument("--maker-fee-bps", default="2")
    parser.add_argument("--taker-fee-bps", default="5")
    parser.add_argument("--slippage-bps", default="2")
    parser.add_argument("--starting-equity", default="100")
    parser.add_argument("--ct-val", default="1")
    parser.add_argument("--tick-sz", default="0.0001")
    parser.add_argument("--lot-sz", default="0.1")
    parser.add_argument("--min-sz", default="0.1")
    parser.add_argument("--min-tp-bps", default="160")
    parser.add_argument("--total-loss-sl-pct", default="3")
    parser.add_argument("--total-loss-sl-cap", default="0.5")
    parser.add_argument("--position-loss-sl-bps", default="550")
    parser.add_argument("--risk-cooldown-bars", type=int, default=10)
    parser.add_argument("--regime-filter", choices=["off", "ma_cross"], default="ma_cross")
    parser.add_argument("--regime-bar", choices=["1m", "3m", "5m", "15m", "30m", "1H", "2H", "4H"], default="15m")
    parser.add_argument("--regime-short-ma", type=int, default=5)
    parser.add_argument("--regime-long-ma", type=int, default=20)
    parser.add_argument("--regime-diff-bps", default="50")
    parser.add_argument("--regime-confirm-bars", type=int, default=3)
    parser.add_argument("--trend-filter", choices=["off", "auto"], default="off")
    parser.add_argument("--trend-lookback", type=int, default=8)
    parser.add_argument("--trend-threshold-bps", default="90")
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> GridBacktestConfig:
    values = vars(args).copy()
    if args.runtime_config:
        payload = json.loads(Path(args.runtime_config).read_text(encoding="utf-8"))
        mapping = {
            "lower": "lower",
            "upper": "upper",
            "leverage": "leverage",
            "gridBps": "grid_bps",
            "softBps": "soft_bps",
            "hardBps": "hard_bps",
            "orderSz": "order_sz",
            "maxPosition": "max_position",
            "maxOpenOrdersPerSide": "max_open_orders_per_side",
            "maxActionsPerCycle": "max_actions_per_bar",
            "mode": "mode",
            "adaptiveWidthBps": "adaptive_width_bps",
            "adaptiveMinWidthBps": "adaptive_min_width_bps",
            "adaptiveMaxWidthBps": "adaptive_max_width_bps",
            "adaptiveVolMultiplier": "adaptive_vol_multiplier",
            "rangeDriftWeightBps": "range_drift_weight_bps",
            "rangeDriftMaxBps": "range_drift_max_bps",
            "rangeDriftMode": "range_drift_mode",
            "oneWayOpen": "one_way_open",
            "minTpBps": "min_tp_bps",
            "totalLossSlPct": "total_loss_sl_pct",
            "totalLossSlCap": "total_loss_sl_cap",
            "positionLossSlBps": "position_loss_sl_bps",
            "regimeFilter": "regime_filter",
            "regimeBar": "regime_bar",
            "regimeShortMa": "regime_short_ma",
            "regimeLongMa": "regime_long_ma",
            "regimeDiffBps": "regime_diff_bps",
            "regimeConfirmBars": "regime_confirm_bars",
            "trendFilter": "trend_filter",
            "trendLookback": "trend_lookback",
            "trendThresholdBps": "trend_threshold_bps",
        }
        for source_key, target_key in mapping.items():
            if source_key in payload:
                values[target_key] = payload[source_key]
        values["inst_id"] = payload.get("instId", values.get("inst_id"))
        if "riskCooldown" in payload:
            values["risk_cooldown_bars"] = cooldown_seconds_to_bars(dec(payload["riskCooldown"]), str(values["bar"]))

    return GridBacktestConfig(
        inst_id=str(values["inst_id"]),
        bar=str(values["bar"]),
        limit=int(values["limit"]),
        lower=dec(values["lower"]),
        upper=dec(values["upper"]),
        leverage=dec(values["leverage"]),
        grid_bps=dec(values["grid_bps"]),
        soft_bps=dec(values["soft_bps"]),
        hard_bps=dec(values["hard_bps"]),
        order_sz=dec(values["order_sz"]),
        max_position=dec(values["max_position"]),
        max_open_orders_per_side=int(values["max_open_orders_per_side"]),
        max_actions_per_bar=int(values["max_actions_per_bar"]),
        mode=str(values["mode"]),
        adaptive_width_bps=dec(values["adaptive_width_bps"]),
        adaptive_min_width_bps=dec(values["adaptive_min_width_bps"]),
        adaptive_max_width_bps=dec(values["adaptive_max_width_bps"]),
        adaptive_vol_multiplier=dec(values["adaptive_vol_multiplier"]),
        range_drift_mode=str(values["range_drift_mode"]),
        range_drift_weight_bps=dec(values["range_drift_weight_bps"]),
        range_drift_max_bps=dec(values["range_drift_max_bps"]),
        one_way_open=bool(values["one_way_open"]),
        maker_fee_bps=dec(values["maker_fee_bps"]),
        taker_fee_bps=dec(values["taker_fee_bps"]),
        slippage_bps=dec(values["slippage_bps"]),
        starting_equity=dec(values["starting_equity"]),
        ct_val=dec(values["ct_val"]),
        tick_sz=dec(values["tick_sz"]),
        lot_sz=dec(values["lot_sz"]),
        min_sz=dec(values["min_sz"]),
        min_tp_bps=dec(values["min_tp_bps"]),
        total_loss_sl_pct=dec(values["total_loss_sl_pct"]),
        total_loss_sl_cap=dec(values["total_loss_sl_cap"]),
        position_loss_sl_bps=dec(values["position_loss_sl_bps"]),
        risk_cooldown_bars=int(values["risk_cooldown_bars"]),
        regime_filter=str(values["regime_filter"]),
        regime_bar=str(values["regime_bar"]),
        regime_short_ma=int(values["regime_short_ma"]),
        regime_long_ma=int(values["regime_long_ma"]),
        regime_diff_bps=dec(values["regime_diff_bps"]),
        regime_confirm_bars=int(values["regime_confirm_bars"]),
        trend_filter=str(values["trend_filter"]),
        trend_lookback=int(values["trend_lookback"]),
        trend_threshold_bps=dec(values["trend_threshold_bps"]),
    )


def load_or_fetch_candles(args: argparse.Namespace, config: GridBacktestConfig) -> list[Candle]:
    if args.input_csv:
        return read_candles_csv(Path(args.input_csv))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    page_suffix = "" if args.pages <= 1 else f"x{args.pages}"
    cache_path = DATA_DIR / f"{config.inst_id}_{config.bar}_{config.limit}{page_suffix}.csv"
    if cache_path.exists() and not args.refresh:
        return read_candles_csv(cache_path)

    client = OkxRestClient()
    rows = fetch_okx_candle_rows(client, config.inst_id, config.bar, config.limit, max(1, args.pages))
    candles = parse_okx_candles(rows)
    write_candles_csv(cache_path, candles)
    return candles


def fetch_okx_candle_rows(client: OkxRestClient, inst_id: str, bar: str, limit: int, pages: int) -> list[list[str]]:
    rows: list[list[str]] = []
    seen_ts: set[str] = set()
    after = ""
    for _ in range(pages):
        params = {"instId": inst_id, "bar": bar, "limit": str(limit)}
        if after:
            params["after"] = after
        response = okx_public_request_with_retry(client, "/api/v5/market/history-candles", params)
        page_rows = response.get("data", [])
        if not page_rows and not rows:
            response = okx_public_request_with_retry(client, "/api/v5/market/candles", params)
            page_rows = response.get("data", [])
        if not page_rows:
            break
        for row in page_rows:
            if row and row[0] not in seen_ts:
                rows.append(row)
                seen_ts.add(row[0])
        oldest_ts = page_rows[-1][0] if page_rows[-1] else ""
        if not oldest_ts or oldest_ts == after:
            break
        after = oldest_ts
        time.sleep(0.25)
    return rows


def okx_public_request_with_retry(client: OkxRestClient, path: str, params: dict[str, str]) -> dict[str, Any]:
    last_exc: OkxApiError | None = None
    for attempt in range(5):
        try:
            return client.request("GET", path, params=params)
        except OkxApiError as exc:
            last_exc = exc
            if exc.status != 429 and exc.okx_code != "50011":
                raise
            time.sleep(1.0 + attempt)
    if last_exc:
        raise last_exc
    return {}


def parse_okx_candles(rows: list[list[str]]) -> list[Candle]:
    candles = []
    for row in rows:
        if len(row) < 6:
            continue
        candles.append(
            Candle(
                ts=int(row[0]),
                open=dec(row[1]),
                high=dec(row[2]),
                low=dec(row[3]),
                close=dec(row[4]),
                volume=dec(row[5]),
            )
        )
    candles.sort(key=lambda candle: candle.ts)
    return candles


def read_candles_csv(path: Path) -> list[Candle]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        candles = [
            Candle(
                ts=int(row["ts"]),
                open=dec(row["open"]),
                high=dec(row["high"]),
                low=dec(row["low"]),
                close=dec(row["close"]),
                volume=dec(row.get("volume", "0")),
            )
            for row in reader
        ]
    candles.sort(key=lambda candle: candle.ts)
    return candles


def write_candles_csv(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["ts", "time", "open", "high", "low", "close", "volume"])
        for candle in candles:
            writer.writerow([candle.ts, iso_time(candle.ts), candle.open, candle.high, candle.low, candle.close, candle.volume])


def run_grid_backtest(
    candles: list[Candle],
    config: GridBacktestConfig,
) -> tuple[BacktestResult, list[Fill], list[dict[str, Any]]]:
    long_pos = Position()
    short_pos = Position()
    orders: list[SimOrder] = []
    fills: list[Fill] = []
    equity_curve: list[dict[str, Any]] = []
    realized_pnl = Decimal("0")
    total_fees = Decimal("0")
    equity = config.starting_equity
    peak_equity = equity
    max_drawdown = Decimal("0")
    cooldown_left = 0
    risk_events = 0

    for index, candle in enumerate(candles):
        context = candles[: index + 1]
        realized_delta, fees_delta, actions = execute_orders(candle, orders, long_pos, short_pos, config, equity)
        filled_order_ids = {id(order) for order, *_ in actions}
        orders = [order for order in orders if id(order) not in filled_order_ids]
        realized_pnl += realized_delta
        total_fees += fees_delta
        equity += realized_delta - fees_delta
        for order, fill_price, pnl, fee in actions:
            fills.append(
                Fill(
                    ts=candle.ts,
                    side=order.side,
                    pos_side=order.pos_side,
                    price=fill_price,
                    size=order.size,
                    fee=fee,
                    realized_pnl=pnl,
                    tag=order.tag,
                    equity=equity,
                )
            )

        mark_px = candle.close
        unrealized = unrealized_pnl(long_pos, short_pos, mark_px, config)
        account_equity = equity + unrealized
        risk_reason = risk_stop_reason(long_pos, short_pos, account_equity, unrealized, mark_px, config)
        if risk_reason:
            risk_events += 1
            close_pnl, close_fees, close_fills = close_all_positions(candle, risk_reason, long_pos, short_pos, config, equity)
            realized_pnl += close_pnl
            total_fees += close_fees
            equity += close_pnl - close_fees
            fills.extend(close_fills)
            orders = []
            cooldown_left = config.risk_cooldown_bars
            if config.range_drift_mode == "cooldown":
                recenter_outer_range(config, mark_px)

        if cooldown_left > 0:
            cooldown_left -= 1
        else:
            desired = desired_sim_orders(context, config, long_pos, short_pos, orders, mark_px)
            orders = reconcile_sim_orders(orders, desired, config.max_actions_per_bar)

        account_equity = equity + unrealized_pnl(long_pos, short_pos, mark_px, config)
        peak_equity = max(peak_equity, account_equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - account_equity) / peak_equity)
        equity_curve.append(
            {
                "ts": candle.ts,
                "time": iso_time(candle.ts),
                "close": str(candle.close),
                "equity": str(account_equity),
                "realizedEquity": str(equity),
                "unrealized": str(unrealized_pnl(long_pos, short_pos, mark_px, config)),
                "longSize": str(long_pos.size),
                "longAvg": str(long_pos.avg_px),
                "shortSize": str(short_pos.size),
                "shortAvg": str(short_pos.avg_px),
                "openOrders": len(orders),
            }
        )

    final_equity = dec(equity_curve[-1]["equity"])
    pnl_fills = [fill for fill in fills if fill.tag.startswith("tp") or fill.tag.startswith("risk")]
    wins = sum(1 for fill in pnl_fills if fill.realized_pnl > 0)
    losses = sum(1 for fill in pnl_fills if fill.realized_pnl < 0)
    gross_profit = sum((fill.realized_pnl for fill in pnl_fills if fill.realized_pnl > 0), Decimal("0"))
    gross_loss = abs(sum((fill.realized_pnl for fill in pnl_fills if fill.realized_pnl < 0), Decimal("0")))
    result = BacktestResult(
        config=serializable_config(config),
        bars=len(candles),
        start_time=iso_time(candles[0].ts),
        end_time=iso_time(candles[-1].ts),
        starting_equity=config.starting_equity,
        final_equity=final_equity,
        total_return_pct=pct(final_equity / config.starting_equity - Decimal("1")) if config.starting_equity > 0 else Decimal("0"),
        max_drawdown_pct=pct(max_drawdown),
        realized_pnl=realized_pnl,
        fees=total_fees,
        fills=len(fills),
        wins=wins,
        losses=losses,
        win_rate_pct=pct(Decimal(wins) / Decimal(wins + losses)) if wins + losses else Decimal("0"),
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else Decimal("0"),
        risk_events=risk_events,
        output_dir="",
    )
    return result, fills, equity_curve


def desired_sim_orders(
    candles: list[Candle],
    config: GridBacktestConfig,
    long_pos: Position,
    short_pos: Position,
    existing_orders: list[SimOrder],
    mark_px: Decimal,
) -> list[SimOrder]:
    effective_lower, effective_upper = effective_range(config, candles, mark_px)
    step = grid_step(config, effective_lower, effective_upper)
    midpoint = (effective_lower + effective_upper) / Decimal("2")
    open_sides = allowed_open_sides(config, candles, long_pos, short_pos, mark_px, midpoint)
    desired: list[SimOrder] = []

    if long_pos.size > 0:
        desired.append(
            SimOrder(
                side="sell",
                pos_side="long",
                price=tp_price(config, "long", long_pos.avg_px, step),
                size=min(config.order_sz, long_pos.size),
                reduce_only=True,
                tag="tp_long",
            )
        )
    if short_pos.size > 0:
        desired.append(
            SimOrder(
                side="buy",
                pos_side="short",
                price=tp_price(config, "short", short_pos.avg_px, step),
                size=min(config.order_sz, short_pos.size),
                reduce_only=True,
                tag="tp_short",
            )
        )

    open_pending_long = sum(order.size for order in existing_orders if not order.reduce_only and order.pos_side == "long")
    open_pending_short = sum(order.size for order in existing_orders if not order.reduce_only and order.pos_side == "short")
    if "long" in open_sides and long_pos.size + open_pending_long < config.max_position:
        remaining = config.max_position - long_pos.size - open_pending_long
        prices = nearest_prices(effective_lower, min(mark_px - step, midpoint - step), step, config.tick_sz, reverse=True)
        for price in prices[: config.max_open_orders_per_side]:
            size = min(config.order_sz, remaining)
            if size <= 0:
                break
            desired.append(SimOrder("buy", "long", price, size, False, "open_long"))
            remaining -= size

    if "short" in open_sides and short_pos.size + open_pending_short < config.max_position:
        remaining = config.max_position - short_pos.size - open_pending_short
        prices = nearest_prices(max(mark_px + step, midpoint + step), effective_upper, step, config.tick_sz, reverse=False)
        for price in prices[: config.max_open_orders_per_side]:
            size = min(config.order_sz, remaining)
            if size <= 0:
                break
            desired.append(SimOrder("sell", "short", price, size, False, "open_short"))
            remaining -= size
    return desired


def execute_orders(
    candle: Candle,
    orders: list[SimOrder],
    long_pos: Position,
    short_pos: Position,
    config: GridBacktestConfig,
    equity: Decimal,
) -> tuple[Decimal, Decimal, list[tuple[SimOrder, Decimal, Decimal, Decimal]]]:
    realized = Decimal("0")
    fees = Decimal("0")
    fills: list[tuple[SimOrder, Decimal, Decimal, Decimal]] = []
    for order in list(orders):
        if not order_filled(candle, order):
            continue
        fill_px = apply_slippage(order.price, order.side, config.slippage_bps)
        pnl = apply_fill(order, fill_px, long_pos, short_pos, config)
        fee = abs(fill_px * order.size * config.ct_val) * config.maker_fee_bps / Decimal("10000")
        realized += pnl
        fees += fee
        fills.append((order, fill_px, pnl, fee))
        if len(fills) >= config.max_actions_per_bar:
            break
    return realized, fees, fills


def apply_fill(order: SimOrder, fill_px: Decimal, long_pos: Position, short_pos: Position, config: GridBacktestConfig) -> Decimal:
    if order.pos_side == "long":
        if order.reduce_only:
            close_size = min(order.size, long_pos.size)
            pnl = (fill_px - long_pos.avg_px) * close_size * config.ct_val
            long_pos.size -= close_size
            if long_pos.size <= 0:
                long_pos.size = Decimal("0")
                long_pos.avg_px = Decimal("0")
            return pnl
        long_pos.avg_px = weighted_avg(long_pos.avg_px, long_pos.size, fill_px, order.size)
        long_pos.size += order.size
        return Decimal("0")

    if order.reduce_only:
        close_size = min(order.size, short_pos.size)
        pnl = (short_pos.avg_px - fill_px) * close_size * config.ct_val
        short_pos.size -= close_size
        if short_pos.size <= 0:
            short_pos.size = Decimal("0")
            short_pos.avg_px = Decimal("0")
        return pnl
    short_pos.avg_px = weighted_avg(short_pos.avg_px, short_pos.size, fill_px, order.size)
    short_pos.size += order.size
    return Decimal("0")


def close_all_positions(
    candle: Candle,
    reason: str,
    long_pos: Position,
    short_pos: Position,
    config: GridBacktestConfig,
    equity: Decimal,
) -> tuple[Decimal, Decimal, list[Fill]]:
    pnl = Decimal("0")
    fees = Decimal("0")
    fills: list[Fill] = []
    if long_pos.size > 0:
        price = apply_slippage(candle.close, "sell", config.slippage_bps)
        size = long_pos.size
        realized = (price - long_pos.avg_px) * size * config.ct_val
        fee = abs(price * size * config.ct_val) * config.taker_fee_bps / Decimal("10000")
        pnl += realized
        fees += fee
        long_pos.size = Decimal("0")
        long_pos.avg_px = Decimal("0")
        fills.append(Fill(candle.ts, "sell", "long", price, size, fee, realized, f"risk_{reason}", equity + pnl - fees))
    if short_pos.size > 0:
        price = apply_slippage(candle.close, "buy", config.slippage_bps)
        size = short_pos.size
        realized = (short_pos.avg_px - price) * size * config.ct_val
        fee = abs(price * size * config.ct_val) * config.taker_fee_bps / Decimal("10000")
        pnl += realized
        fees += fee
        short_pos.size = Decimal("0")
        short_pos.avg_px = Decimal("0")
        fills.append(Fill(candle.ts, "buy", "short", price, size, fee, realized, f"risk_{reason}", equity + pnl - fees))
    return pnl, fees, fills


def risk_stop_reason(
    long_pos: Position,
    short_pos: Position,
    account_equity: Decimal,
    unrealized: Decimal,
    mark_px: Decimal,
    config: GridBacktestConfig,
) -> str:
    threshold = account_equity * config.total_loss_sl_pct / Decimal("100") if account_equity > 0 else Decimal("0")
    if config.total_loss_sl_cap > 0 and threshold > config.total_loss_sl_cap:
        threshold = config.total_loss_sl_cap
    if threshold > 0 and unrealized <= -threshold:
        return "total_loss_sl"

    if long_pos.size > 0 and long_pos.avg_px > 0:
        adverse = max(Decimal("0"), (long_pos.avg_px - mark_px) / long_pos.avg_px * Decimal("10000") * config.leverage)
        if adverse >= config.position_loss_sl_bps:
            return "position_loss_sl_long"
    if short_pos.size > 0 and short_pos.avg_px > 0:
        adverse = max(Decimal("0"), (mark_px - short_pos.avg_px) / short_pos.avg_px * Decimal("10000") * config.leverage)
        if adverse >= config.position_loss_sl_bps:
            return "position_loss_sl_short"
    return ""


def allowed_open_sides(
    config: GridBacktestConfig,
    candles: list[Candle],
    long_pos: Position,
    short_pos: Position,
    mark_px: Decimal,
    midpoint: Decimal,
) -> set[str]:
    regime = regime_state(config, candles)
    trend = trend_state(config, candles)
    if config.regime_filter == "ma_cross" and regime in {"up", "down"}:
        sides = {"long"} if regime == "up" else {"short"}
    elif mark_px < midpoint:
        sides = {"long"}
    else:
        sides = {"short"}

    if config.trend_filter == "auto" and trend in {"up", "down"}:
        trend_sides = {"long"} if trend == "up" else {"short"}
        if config.regime_filter == "ma_cross" and regime in {"up", "down"} and not sides & trend_sides:
            return set()
        sides = trend_sides

    if config.one_way_open:
        if short_pos.size > 0 and "long" in sides:
            return set()
        if long_pos.size > 0 and "short" in sides:
            return set()
    return sides


def regime_state(config: GridBacktestConfig, candles: list[Candle]) -> str:
    if config.regime_filter != "ma_cross":
        return "off"
    regime_candles = aggregate_candles(candles, config.regime_bar, config.bar)
    if len(regime_candles) < config.regime_long_ma:
        return "range"
    states = [
        ma_regime_state(config, regime_candles[: len(regime_candles) - offset])
        for offset in range(max(1, config.regime_confirm_bars))
    ]
    if states and all(state == states[0] for state in states):
        return states[0]
    return "range"


def ma_regime_state(config: GridBacktestConfig, candles: list[Candle]) -> str:
    if len(candles) < config.regime_long_ma:
        return "range"
    closes = [candle.close for candle in candles]
    short_ma = sum(closes[-config.regime_short_ma :]) / Decimal(config.regime_short_ma)
    long_ma = sum(closes[-config.regime_long_ma :]) / Decimal(config.regime_long_ma)
    diff_bps = (short_ma / long_ma - Decimal("1")) * Decimal("10000") if long_ma > 0 else Decimal("0")
    if diff_bps >= config.regime_diff_bps:
        return "up"
    if diff_bps <= -config.regime_diff_bps:
        return "down"
    return "range"


def aggregate_candles(candles: list[Candle], target_bar: str, source_bar: str) -> list[Candle]:
    target_ms = BAR_MS.get(target_bar, BAR_MS["15m"])
    source_ms = BAR_MS.get(source_bar, BAR_MS["1m"])
    if target_ms <= source_ms:
        return candles
    if not candles:
        return []
    latest_close_ms = candles[-1].ts + source_ms
    buckets: dict[int, list[Candle]] = {}
    for candle in candles:
        bucket = candle.ts - (candle.ts % target_ms)
        if bucket + target_ms > latest_close_ms:
            continue
        buckets.setdefault(bucket, []).append(candle)
    aggregated = []
    for bucket in sorted(buckets):
        items = buckets[bucket]
        aggregated.append(
            Candle(
                ts=bucket,
                open=items[0].open,
                high=max(item.high for item in items),
                low=min(item.low for item in items),
                close=items[-1].close,
                volume=sum((item.volume for item in items), Decimal("0")),
            )
        )
    return aggregated


def trend_state(config: GridBacktestConfig, candles: list[Candle]) -> str:
    if len(candles) <= config.trend_lookback:
        return "flat"
    current = candles[-1].close
    past = candles[-1 - config.trend_lookback].close
    if past <= 0:
        return "flat"
    change_bps = (current / past - Decimal("1")) * Decimal("10000")
    if change_bps >= config.trend_threshold_bps:
        return "up"
    if change_bps <= -config.trend_threshold_bps:
        return "down"
    return "flat"


def effective_range(config: GridBacktestConfig, candles: list[Candle], mark_px: Decimal) -> tuple[Decimal, Decimal]:
    if config.mode != "adaptive" or mark_px <= 0:
        return config.lower, config.upper
    avg_abs_bps = avg_abs_return_bps(candles[-60:])
    width_bps = max(config.adaptive_width_bps, avg_abs_bps * config.adaptive_vol_multiplier, config.adaptive_min_width_bps)
    width_bps = min(width_bps, config.adaptive_max_width_bps)
    half = width_bps / Decimal("20000")
    lower = max(config.lower, round_to_tick(mark_px * (Decimal("1") - half), config.tick_sz))
    upper = min(config.upper, round_to_tick(mark_px * (Decimal("1") + half), config.tick_sz))
    if upper <= lower:
        return config.lower, config.upper
    return lower, upper


def recenter_outer_range(config: GridBacktestConfig, mark_px: Decimal) -> None:
    width = config.upper - config.lower
    if width <= 0 or mark_px <= 0:
        return
    midpoint = (config.lower + config.upper) / Decimal("2")
    shift = (mark_px - midpoint) * min(max(config.range_drift_weight_bps, Decimal("0")), Decimal("10000")) / Decimal("10000")
    max_shift = midpoint * max(config.range_drift_max_bps, Decimal("0")) / Decimal("10000")
    if max_shift > 0:
        shift = max(-max_shift, min(shift, max_shift))
    config.lower = round_to_tick(config.lower + shift, config.tick_sz)
    config.upper = round_to_tick(config.lower + width, config.tick_sz)


def reconcile_sim_orders(existing: list[SimOrder], desired: list[SimOrder], max_actions: int) -> list[SimOrder]:
    keep: list[SimOrder] = []
    desired_keys = {order_signature(order) for order in desired}
    for order in existing:
        if order_signature(order) in desired_keys:
            keep.append(order)
    missing = [order for order in desired if order_signature(order) not in {order_signature(item) for item in keep}]
    keep.extend(missing[:max_actions])
    return keep


def write_outputs(
    result: BacktestResult,
    fills: list[Fill],
    equity_curve: list[dict[str, Any]],
    output_dir_arg: str = "",
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = resolve_output_dir(output_dir_arg, timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.output_dir = str(output_dir)
    result.config["outputDir"] = str(output_dir)

    (output_dir / "summary.json").write_text(json.dumps(to_jsonable(asdict(result)), indent=2), encoding="utf-8")
    with (output_dir / "fills.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["ts", "time", "side", "pos_side", "price", "size", "fee", "realized_pnl", "tag", "equity"])
        for fill in fills:
            writer.writerow([fill.ts, iso_time(fill.ts), fill.side, fill.pos_side, fill.price, fill.size, fill.fee, fill.realized_pnl, fill.tag, fill.equity])
    with (output_dir / "equity_curve.csv").open("w", encoding="utf-8", newline="") as file:
        fieldnames = list(equity_curve[0].keys()) if equity_curve else []
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(equity_curve)

    write_markdown_report(output_dir / "report.md", result)
    return output_dir


def resolve_output_dir(output_dir_arg: str, timestamp: str) -> Path:
    if not output_dir_arg:
        return REPORT_DIR / timestamp
    path = Path(output_dir_arg)
    if path.is_absolute():
        return path
    return REPORT_DIR / path


def write_markdown_report(path: Path, result: BacktestResult) -> None:
    lines = [
        "# OKX Grid Backtest Report",
        "",
        "This report is for research and validation only. It is not investment advice, and historical results do not imply future performance.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Instrument | {result.config['instId']} |",
        f"| Bars | {result.bars} |",
        f"| Period | {result.start_time} to {result.end_time} |",
        f"| Starting equity | {plain(result.starting_equity)} USDT |",
        f"| Final equity | {plain(result.final_equity)} USDT |",
        f"| Total return | {plain(result.total_return_pct)}% |",
        f"| Max drawdown | {plain(result.max_drawdown_pct)}% |",
        f"| Realized PnL | {plain(result.realized_pnl)} USDT |",
        f"| Fees | {plain(result.fees)} USDT |",
        f"| Fills | {result.fills} |",
        f"| Win rate | {plain(result.win_rate_pct)}% |",
        f"| Profit factor | {plain(result.profit_factor)} |",
        f"| Risk events | {result.risk_events} |",
        "",
        "## Outputs",
        "",
        "- `summary.json`: machine-readable metrics and parameters.",
        "- `fills.csv`: simulated fills.",
        "- `equity_curve.csv`: bar-by-bar equity and position state.",
        "",
        "## Method Notes",
        "",
        "- Limit orders are filled if the candle high/low crosses the order price.",
        "- Intrabar sequence is approximated; this is not a tick-level execution simulator.",
        "- Fees, slippage, contract value, tick size, and lot size are configurable.",
        "- The simulation uses public candles only and does not call private OKX APIs.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_summary(result: BacktestResult, output_dir: Path) -> None:
    print(f"instrument={result.config['instId']} bars={result.bars}")
    print(f"period={result.start_time} -> {result.end_time}")
    print(f"final_equity={plain(result.final_equity)} total_return={plain(result.total_return_pct)}% max_dd={plain(result.max_drawdown_pct)}%")
    print(f"fills={result.fills} fees={plain(result.fees)} risk_events={result.risk_events}")
    print(f"output_dir={output_dir}")


def order_filled(candle: Candle, order: SimOrder) -> bool:
    if order.side == "buy":
        return candle.low <= order.price
    return candle.high >= order.price


def apply_slippage(price: Decimal, side: str, slippage_bps: Decimal) -> Decimal:
    bump = slippage_bps / Decimal("10000")
    if side == "buy":
        return price * (Decimal("1") + bump)
    return price * (Decimal("1") - bump)


def unrealized_pnl(long_pos: Position, short_pos: Position, mark_px: Decimal, config: GridBacktestConfig) -> Decimal:
    pnl = Decimal("0")
    if long_pos.size > 0 and long_pos.avg_px > 0:
        pnl += (mark_px - long_pos.avg_px) * long_pos.size * config.ct_val
    if short_pos.size > 0 and short_pos.avg_px > 0:
        pnl += (short_pos.avg_px - mark_px) * short_pos.size * config.ct_val
    return pnl


def weighted_avg(old_avg: Decimal, old_size: Decimal, new_px: Decimal, new_size: Decimal) -> Decimal:
    total = old_size + new_size
    if total <= 0:
        return Decimal("0")
    return (old_avg * old_size + new_px * new_size) / total


def tp_price(config: GridBacktestConfig, pos_side: str, avg_px: Decimal, step: Decimal) -> Decimal:
    if pos_side == "long":
        target = max(avg_px + step, avg_px * (Decimal("1") + config.min_tp_bps / Decimal("10000")))
    else:
        target = min(avg_px - step, avg_px * (Decimal("1") - config.min_tp_bps / Decimal("10000")))
    return round_to_tick(target, config.tick_sz)


def grid_step(config: GridBacktestConfig, lower: Decimal, upper: Decimal) -> Decimal:
    midpoint = (lower + upper) / Decimal("2")
    if midpoint <= 0 or upper <= lower:
        return config.tick_sz
    target_step = midpoint * config.grid_bps / Decimal("10000")
    grid_count = max(1, int(((upper - lower) / target_step).to_integral_value(rounding=ROUND_HALF_UP)))
    return max(config.tick_sz, round_to_tick((upper - lower) / Decimal(grid_count), config.tick_sz))


def nearest_prices(start: Decimal, end: Decimal, step: Decimal, tick: Decimal, *, reverse: bool) -> list[Decimal]:
    if start > end or step <= 0:
        return []
    prices = []
    price = round_to_tick(start, tick)
    while price <= end + tick / Decimal("2"):
        prices.append(price)
        price += step
    return list(reversed(prices)) if reverse else prices


def avg_abs_return_bps(candles: list[Candle]) -> Decimal:
    if len(candles) < 2:
        return Decimal("0")
    values: list[Decimal] = []
    for prev, current in zip(candles, candles[1:]):
        if prev.close > 0:
            values.append(abs((current.close / prev.close - Decimal("1")) * Decimal("10000")))
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def order_signature(order: SimOrder) -> tuple[str, str, str, str, bool]:
    return (order.side, order.pos_side, plain(order.price), plain(order.size), order.reduce_only)


def serializable_config(config: GridBacktestConfig) -> dict[str, Any]:
    result = to_jsonable(asdict(config))
    result["instId"] = result.pop("inst_id")
    result["gridBps"] = result.pop("grid_bps")
    result["outputDir"] = ""
    return result


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value


def round_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        return value
    return (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def pct(value: Decimal) -> Decimal:
    return value * Decimal("100")


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def cooldown_seconds_to_bars(seconds: Decimal, bar: str) -> int:
    if seconds <= 0:
        return 0
    bar_seconds = Decimal(BAR_MS.get(bar, BAR_MS["1m"])) / Decimal("1000")
    return max(1, int((seconds / bar_seconds).to_integral_value(rounding=ROUND_UP)))


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def iso_time(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
