"""Read-only slow-factor and deep-OTM tail-hedge research for BTC/ETH.

The experiment deliberately keeps the grid small.  It compares three fixed
momentum horizons, then overlays symmetric 30-DTE option wings on the moderate
horizon.  Historical Deribit trades determine entry cost; fixed entry IV is
used for causal hourly marking because historical bid/ask and continuous
option marks are unavailable from the public chart endpoint.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from option_long_dte_research import QUARTERLY_EXPIRIES
from option_strangle_backtest import (
    DEFAULT_CACHE,
    HOUR_MS,
    YEAR_MS,
    Bar,
    DeribitHistory,
    bs_price,
    expiry_code,
    implied_volatility,
    iso_ms,
    option_fee,
    parse_iso_ms,
    strike_step,
    traded_observation,
    BacktestConfig,
)
from strategy_search import multi_horizon_momentum_targets


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "slow_factor_tail_hedge"
BASES = ("BTC", "ETH")
ENTRY_HOURS = 30 * 24
EXIT_HOURS = 1
TARGET_OTM_PCT = 15.0
STARTING_EQUITY = 100_000.0
LEVERAGE = 2.0
PERP_FEE_BPS = 5.0
PERP_SLIPPAGE_BPS = 1.0
HOLDING_COST_BPS_PER_DAY = 0.5
OPTION_ENTRY_STALENESS_HOURS = 24
OPTION_FEE_CONFIG = BacktestConfig()
EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class FactorProfile:
    name: str
    lookbacks: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class HedgeVariant:
    name: str
    coverage_ratio: float
    option_slippage_bps: float


@dataclass(frozen=True, slots=True)
class OptionWing:
    name: str
    option_type: str
    strike: float
    target_otm_pct: float
    actual_otm_pct: float
    entry_price_usd: float
    entry_iv: float
    entry_staleness_hours: float


@dataclass(frozen=True, slots=True)
class WindowResult:
    base: str
    expiry: str
    sample: str
    study: str
    variant: str
    lookbacks: str
    leverage: float
    hedge_coverage_pct: float
    option_slippage_bps: float
    actual_put_otm_pct: float
    actual_call_otm_pct: float
    option_entry_staleness_hours: float
    total_return_pct: float
    max_drawdown_pct: float
    trades: int
    signal_changes: int
    exposure_pct: float
    perp_cost_usd: float
    option_premium_pct_equity: float
    option_pnl_pct_equity: float


FACTOR_PROFILES = (
    FactorProfile("original_6_12_24_48", (6, 12, 24, 48)),
    FactorProfile("moderate_12_24_48_96", (12, 24, 48, 96)),
    FactorProfile("slow_24_48_96_168", (24, 48, 96, 168)),
)
PRIMARY_PROFILE = FACTOR_PROFILES[1]
HEDGE_VARIANTS = (
    HedgeVariant("unhedged_common", 0.0, 0.0),
    HedgeVariant("wings_25pct", 0.25, 500.0),
    HedgeVariant("wings_50pct", 0.50, 500.0),
    HedgeVariant("wings_100pct", 1.00, 500.0),
    HedgeVariant("wings_50pct_cost_stress", 0.50, 1000.0),
)


def sample_for_expiry(index: int, count: int) -> str:
    train_end = count // 2
    validation_end = train_end + count // 4
    if index < train_end:
        return "train"
    if index < validation_end:
        return "validation"
    return "test"


def candidate_option_strikes(base: str, spot: float, option_type: str) -> list[float]:
    if option_type not in {"P", "C"}:
        raise ValueError("option type must be P or C")
    target = spot * (1.0 - TARGET_OTM_PCT / 100.0 if option_type == "P" else 1.0 + TARGET_OTM_PCT / 100.0)
    step = strike_step(base, spot)
    center = round(target / step) * step
    values = [center + offset * step for offset in range(-6, 7)]
    if option_type == "P":
        values = [value for value in values if 0 < value < spot]
    else:
        values = [value for value in values if value > spot]
    return sorted(set(values))


def select_option_wing(
    *,
    base: str,
    expiry_ms: int,
    entry_ts: int,
    entry_spot: float,
    option_type: str,
    charts: dict[str, tuple[Bar, ...]],
) -> OptionWing | None:
    candidates: list[OptionWing] = []
    years = max((expiry_ms - entry_ts) / YEAR_MS, 1e-9)
    for strike in candidate_option_strikes(base, entry_spot, option_type):
        name = f"{base}-{expiry_code(expiry_ms)}-{strike:g}-{option_type}"
        observation = traded_observation(charts.get(name, ()), entry_ts, OPTION_ENTRY_STALENESS_HOURS)
        if observation is None:
            continue
        price_usd = observation[0].close * entry_spot
        iv = implied_volatility(price_usd, entry_spot, strike, years, option_type)
        if iv is None or iv <= 0:
            continue
        actual_otm = (1.0 - strike / entry_spot) * 100.0 if option_type == "P" else (strike / entry_spot - 1.0) * 100.0
        candidates.append(
            OptionWing(
                name=name,
                option_type=option_type,
                strike=strike,
                target_otm_pct=TARGET_OTM_PCT,
                actual_otm_pct=actual_otm,
                entry_price_usd=price_usd,
                entry_iv=iv,
                entry_staleness_hours=observation[1],
            )
        )
    return min(candidates, key=lambda item: abs(item.actual_otm_pct - TARGET_OTM_PCT)) if candidates else None


def option_mid_value(wing: OptionWing, spot: float, timestamp: int, expiry_ms: int) -> float:
    years = max((expiry_ms - timestamp) / YEAR_MS, 1e-9)
    return bs_price(spot, wing.strike, years, wing.entry_iv, wing.option_type)


def simulate_window(
    *,
    base: str,
    expiry_ms: int,
    sample: str,
    bars: tuple[Bar, ...],
    profile: FactorProfile,
    hedge: HedgeVariant,
    put: OptionWing | None = None,
    call: OptionWing | None = None,
    study: str,
) -> WindowResult:
    entry_ts = expiry_ms - ENTRY_HOURS * HOUR_MS
    exit_ts = expiry_ms - EXIT_HOURS * HOUR_MS
    path = tuple(item for item in sorted(bars, key=lambda row: row.ts) if item.ts <= exit_ts)
    entry_index = next((index for index, item in enumerate(path) if item.ts >= entry_ts), -1)
    if entry_index < 0 or path[entry_index].ts != entry_ts or path[-1].ts != exit_ts:
        raise ValueError("underlying path must contain exact entry and exit hours")
    if hedge.coverage_ratio > 0 and (put is None or call is None):
        raise ValueError("both option wings are required for a hedged simulation")

    closes = [item.close for item in path]
    targets = multi_horizon_momentum_targets(
        closes,
        list(profile.lookbacks),
        max(profile.lookbacks),
        0.1,
        2,
    )
    entry_spot = path[entry_index].close
    option_units = hedge.coverage_ratio * LEVERAGE * STARTING_EQUITY / entry_spot
    option_slip = hedge.option_slippage_bps / 10_000.0
    wings = tuple(item for item in (put, call) if item is not None) if hedge.coverage_ratio > 0 else ()
    raw_entry_premium = sum(item.entry_price_usd * option_units for item in wings)
    option_entry_fees = sum(option_fee(item.entry_price_usd, entry_spot, OPTION_FEE_CONFIG) * option_units for item in wings)
    option_entry_cost = raw_entry_premium * (1.0 + option_slip) + option_entry_fees

    cash = STARTING_EQUITY - option_entry_cost
    position = 0.0
    entry_fill = 0.0
    peak_equity = STARTING_EQUITY
    max_drawdown = 0.0
    perp_cost = 0.0
    trades = 0
    signal_changes = 0
    exposure_hours = 0
    last_side = 0
    fee_rate = PERP_FEE_BPS / 10_000.0
    perp_slip = PERP_SLIPPAGE_BPS / 10_000.0

    def marked_perp(spot: float) -> float:
        return position * (spot - entry_fill) if abs(position) > EPSILON else 0.0

    def marked_options(spot: float, timestamp: int) -> float:
        return sum(option_mid_value(item, spot, timestamp, expiry_ms) * option_units for item in wings)

    for index in range(entry_index, len(path)):
        bar = path[index]
        desired = targets[index]
        if desired != last_side:
            signal_changes += int(index > entry_index)
            last_side = desired
        if desired != (1 if position > EPSILON else -1 if position < -EPSILON else 0):
            if abs(position) > EPSILON:
                close_fill = bar.close * (1.0 - perp_slip if position > 0 else 1.0 + perp_slip)
                realized = position * (close_fill - entry_fill)
                fee = abs(position * close_fill) * fee_rate
                cash += realized - fee
                perp_cost += fee + abs(position) * abs(close_fill - bar.close)
                trades += 1
                position = 0.0
                entry_fill = 0.0
            if desired:
                signed_notional = desired * LEVERAGE * STARTING_EQUITY
                entry_fill = bar.close * (1.0 + perp_slip if desired > 0 else 1.0 - perp_slip)
                position = signed_notional / entry_fill
                fee = abs(signed_notional) * fee_rate
                cash -= fee
                perp_cost += fee + abs(position) * abs(entry_fill - bar.close)
        if abs(position) > EPSILON:
            exposure_hours += 1
            holding_cost = abs(position * bar.close) * HOLDING_COST_BPS_PER_DAY / 10_000.0 / 24.0
            cash -= holding_cost
            perp_cost += holding_cost
        equity = cash + marked_perp(bar.close) + marked_options(bar.close, bar.ts)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100.0)

    final_bar = path[-1]
    if abs(position) > EPSILON:
        close_fill = final_bar.close * (1.0 - perp_slip if position > 0 else 1.0 + perp_slip)
        realized = position * (close_fill - entry_fill)
        fee = abs(position * close_fill) * fee_rate
        cash += realized - fee
        perp_cost += fee + abs(position) * abs(close_fill - final_bar.close)
        trades += 1
    raw_exit_value = sum(option_mid_value(item, final_bar.close, final_bar.ts, expiry_ms) * option_units for item in wings)
    option_exit_fees = sum(
        option_fee(option_mid_value(item, final_bar.close, final_bar.ts, expiry_ms), final_bar.close, OPTION_FEE_CONFIG) * option_units
        for item in wings
    )
    option_exit_proceeds = max(0.0, raw_exit_value * (1.0 - option_slip) - option_exit_fees)
    cash += option_exit_proceeds
    peak_equity = max(peak_equity, cash)
    if peak_equity > 0:
        max_drawdown = max(max_drawdown, (peak_equity - cash) / peak_equity * 100.0)

    return WindowResult(
        base=base,
        expiry=iso_ms(expiry_ms),
        sample=sample,
        study=study,
        variant=hedge.name if study == "tail_hedge" else profile.name,
        lookbacks="/".join(str(item) for item in profile.lookbacks),
        leverage=LEVERAGE,
        hedge_coverage_pct=hedge.coverage_ratio * 100.0,
        option_slippage_bps=hedge.option_slippage_bps,
        actual_put_otm_pct=put.actual_otm_pct if put is not None else 0.0,
        actual_call_otm_pct=call.actual_otm_pct if call is not None else 0.0,
        option_entry_staleness_hours=max((item.entry_staleness_hours for item in wings), default=0.0),
        total_return_pct=(cash / STARTING_EQUITY - 1.0) * 100.0,
        max_drawdown_pct=max_drawdown,
        trades=trades,
        signal_changes=signal_changes,
        exposure_pct=exposure_hours / max(1, len(path) - entry_index) * 100.0,
        perp_cost_usd=perp_cost,
        option_premium_pct_equity=option_entry_cost / STARTING_EQUITY * 100.0,
        option_pnl_pct_equity=(option_exit_proceeds - option_entry_cost) / STARTING_EQUITY * 100.0,
    )


def aggregate_rows(rows: Iterable[WindowResult]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[WindowResult]] = {}
    for row in rows:
        grouped.setdefault((row.sample, row.study, row.variant), []).append(row)
    result: list[dict[str, Any]] = []
    for (sample, study, variant), items in sorted(grouped.items()):
        result.append(
            {
                "sample": sample,
                "study": study,
                "variant": variant,
                "count": len(items),
                "positive": sum(item.total_return_pct > 0 for item in items),
                "median_return_pct": statistics.median(item.total_return_pct for item in items),
                "mean_return_pct": statistics.fmean(item.total_return_pct for item in items),
                "median_max_drawdown_pct": statistics.median(item.max_drawdown_pct for item in items),
                "worst_max_drawdown_pct": max(item.max_drawdown_pct for item in items),
                "median_signal_changes": statistics.median(item.signal_changes for item in items),
                "median_trades": statistics.median(item.trades for item in items),
                "median_option_premium_pct_equity": statistics.median(item.option_premium_pct_equity for item in items),
                "median_option_pnl_pct_equity": statistics.median(item.option_pnl_pct_equity for item in items),
            }
        )
    return result


def decision_payload(aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    lookup = {(item["sample"], item["study"], item["variant"]): item for item in aggregates}
    original = lookup[("test", "factor_period", FACTOR_PROFILES[0].name)]
    moderate = lookup[("test", "factor_period", PRIMARY_PROFILE.name)]
    unhedged = lookup[("test", "tail_hedge", HEDGE_VARIANTS[0].name)]
    hedged = [lookup[("test", "tail_hedge", item.name)] for item in HEDGE_VARIANTS[1:]]
    best_median_dd = min(hedged, key=lambda item: item["median_max_drawdown_pct"])
    best_worst_dd = min(hedged, key=lambda item: item["worst_max_drawdown_pct"])
    period_reduces_median_drawdown = moderate["median_max_drawdown_pct"] < original["median_max_drawdown_pct"]
    period_passes = moderate["median_return_pct"] > 0 and moderate["worst_max_drawdown_pct"] <= original["worst_max_drawdown_pct"]
    return {
        "status": "research_only",
        "periodNoiseHypothesisPartiallySupported": period_reduces_median_drawdown,
        "periodGatePassed": period_passes,
        "moderateVsOriginal": {
            "medianReturnChangePctPoints": moderate["median_return_pct"] - original["median_return_pct"],
            "medianDrawdownChangePctPoints": moderate["median_max_drawdown_pct"] - original["median_max_drawdown_pct"],
            "worstDrawdownChangePctPoints": moderate["worst_max_drawdown_pct"] - original["worst_max_drawdown_pct"],
            "medianSignalChangesChange": moderate["median_signal_changes"] - original["median_signal_changes"],
        },
        "staticTailHedgeReducedMedianDrawdown": best_median_dd["median_max_drawdown_pct"] < unhedged["median_max_drawdown_pct"],
        "staticTailHedgeReducedWorstDrawdown": best_worst_dd["worst_max_drawdown_pct"] < unhedged["worst_max_drawdown_pct"],
        "bestHedgedMedianDrawdownVariant": best_median_dd["variant"],
        "bestHedgedWorstDrawdownVariant": best_worst_dd["variant"],
        "recommendation": "do_not_deploy; keep moderate horizons as a future preregistered baseline and reject static 30-DTE symmetric wings",
    }


def report_markdown(payload: dict[str, Any]) -> str:
    aggregates = payload["aggregates"]
    decision = payload["decision"]
    lines = [
        "# BTC/ETH 慢因子与深度虚值期权尾部保险研究",
        "",
        "> 只读历史研究；不读取账户、不发送订单、不改变实盘配置。",
        "",
        "## 设计",
        "",
        f"- 使用 {len(payload['expiries'])} 个季度到期窗口，每个窗口从到期前 30 天至到期前 1 小时；前 50% 训练、随后 25% 验证、最后 25% 复用测试。",
        "- 固定比较 6/12/24/48h、12/24/48/96h、24/48/96/168h 三组多周期动量；2 倍名义暴露，2 票确认，0.1 sigma 门槛。",
        "- 尾部层只叠加在 12/24/48/96h 主方案：同时买入约 15% OTM Put 和 Call，30 DTE，覆盖 25%/50%/100% 的 2 倍名义敞口。",
        "- 永续每端 5 bps 手续费加 1 bps 滑点，并计 0.5 bps/日持有成本；期权基础情景每端 5% 滑点，压力情景每端 10%。",
        "- 期权入场价来自 24 小时内真实 Deribit 成交；逐小时估值用入场成交价反推的固定 IV，避免用未来 IV，但不会捕捉危机时 IV 上升，因此回撤改善估计偏保守。",
        "",
        "## 因子周期对照",
        "",
        "| 区间 | 周期 | 窗口 | 正收益 | 中位收益 | 中位回撤 | 最差回撤 | 中位信号切换 | 中位平仓数 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sample in ("train", "validation", "test"):
        for profile in FACTOR_PROFILES:
            item = next((row for row in aggregates if row["sample"] == sample and row["study"] == "factor_period" and row["variant"] == profile.name), None)
            if item:
                lines.append(
                    f"| {sample} | {'/'.join(map(str, profile.lookbacks))}h | {item['count']} | {item['positive']}/{item['count']} | "
                    f"{item['median_return_pct']:.3f}% | {item['median_max_drawdown_pct']:.3f}% | {item['worst_max_drawdown_pct']:.3f}% | "
                    f"{item['median_signal_changes']:.1f} | {item['median_trades']:.1f} |"
                )
    lines.extend(
        [
            "",
            "## 尾部保险对照（共同可交易窗口）",
            "",
            "| 区间 | 方案 | 窗口 | 正收益 | 中位收益 | 中位回撤 | 最差回撤 | 中位权利金/权益 | 中位期权损益/权益 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for sample in ("train", "validation", "test"):
        for hedge in HEDGE_VARIANTS:
            item = next((row for row in aggregates if row["sample"] == sample and row["study"] == "tail_hedge" and row["variant"] == hedge.name), None)
            if item:
                lines.append(
                    f"| {sample} | {hedge.name} | {item['count']} | {item['positive']}/{item['count']} | "
                    f"{item['median_return_pct']:.3f}% | {item['median_max_drawdown_pct']:.3f}% | {item['worst_max_drawdown_pct']:.3f}% | "
                    f"{item['median_option_premium_pct_equity']:.3f}% | {item['median_option_pnl_pct_equity']:.3f}% |"
                )
    lines.extend(
        [
            "",
            "## 结果判断",
            "",
            f"- 适度放宽周期后，测试中位收益变化 {decision['moderateVsOriginal']['medianReturnChangePctPoints']:+.3f} 个百分点，中位回撤变化 {decision['moderateVsOriginal']['medianDrawdownChangePctPoints']:+.3f} 个百分点，中位信号切换变化 {decision['moderateVsOriginal']['medianSignalChangesChange']:+.1f} 次。",
            f"- 但测试最差回撤变化 {decision['moderateVsOriginal']['worstDrawdownChangePctPoints']:+.3f} 个百分点，适度放宽方案仍为负收益，因此只能说噪声假设得到部分支持，不能说模型已经有效。",
            f"- 静态期权层降低测试中位回撤：`{str(decision['staticTailHedgeReducedMedianDrawdown']).lower()}`；降低测试最差回撤：`{str(decision['staticTailHedgeReducedWorstDrawdown']).lower()}`。权利金无法对冲趋势模型的反复翻向损失。",
            "- 结论：保留 12/24/48/96h 作为未来预注册基线的候选，但本历史上不部署；拒绝固定持有 30 DTE 双边深度 OTM wings 作为这套模型的常态回撤控制。",
            "",
            "## 判定边界",
            "",
            f"- 期权共同覆盖 {payload['optionCoverage']['eligibleWindows']}/{payload['optionCoverage']['totalWindows']} 个标的-到期窗口；缺失窗口不参与尾部方案对照。",
            "- 同一到期窗口按 100,000 USDT 独立重置，结果衡量结构在不同市场窗口的分布，不是连续复利账户曲线。",
            "- 公共历史没有 bid/ask，5%/10% 期权滑点只是显式压力假设；深度虚值合约若无法在 24 小时内找到成交则剔除。",
            "- 测试段已属于反复查看过的历史，结果只能用于研究判断，不能授权仿真、实盘或自动买入期权。",
            "",
        ]
    )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[WindowResult]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only slow-factor and deep-OTM tail-hedge research")
    parser.add_argument("--cache-file", default=str(DEFAULT_CACHE))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--expiry", action="append", dest="expiries", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expiries = sorted(parse_iso_ms(item) for item in (args.expiries or list(QUARTERLY_EXPIRIES)))
    history = DeribitHistory(Path(args.cache_file), workers=args.workers)
    rows: list[WindowResult] = []
    coverage_rows: list[dict[str, Any]] = []
    maximum_lookback = max(max(profile.lookbacks) for profile in FACTOR_PROFILES)

    for expiry_index, expiry_ms in enumerate(expiries):
        sample = sample_for_expiry(expiry_index, len(expiries))
        entry_ts = expiry_ms - ENTRY_HOURS * HOUR_MS
        exit_ts = expiry_ms - EXIT_HOURS * HOUR_MS
        history_start = entry_ts - (maximum_lookback + 2) * HOUR_MS
        option_start = entry_ts - OPTION_ENTRY_STALENESS_HOURS * HOUR_MS
        for base in BASES:
            perpetual_name = f"{base}-PERPETUAL"
            bars = history.fetch_many([perpetual_name], history_start, exit_ts).get(perpetual_name, ())
            if not bars:
                continue
            entry_bar = next((item for item in bars if item.ts == entry_ts), None)
            exit_bar = next((item for item in bars if item.ts == exit_ts), None)
            if entry_bar is None or exit_bar is None:
                continue
            for profile in FACTOR_PROFILES:
                rows.append(
                    simulate_window(
                        base=base,
                        expiry_ms=expiry_ms,
                        sample=sample,
                        bars=bars,
                        profile=profile,
                        hedge=HEDGE_VARIANTS[0],
                        study="factor_period",
                    )
                )

            names = [
                f"{base}-{expiry_code(expiry_ms)}-{strike:g}-{option_type}"
                for option_type in ("P", "C")
                for strike in candidate_option_strikes(base, entry_bar.close, option_type)
            ]
            charts = history.fetch_many(names, option_start, entry_ts)
            put = select_option_wing(
                base=base,
                expiry_ms=expiry_ms,
                entry_ts=entry_ts,
                entry_spot=entry_bar.close,
                option_type="P",
                charts=charts,
            )
            call = select_option_wing(
                base=base,
                expiry_ms=expiry_ms,
                entry_ts=entry_ts,
                entry_spot=entry_bar.close,
                option_type="C",
                charts=charts,
            )
            coverage_rows.append(
                {
                    "base": base,
                    "expiry": iso_ms(expiry_ms),
                    "sample": sample,
                    "eligible": put is not None and call is not None,
                    "put": asdict(put) if put else None,
                    "call": asdict(call) if call else None,
                }
            )
            if put is None or call is None:
                continue
            for hedge in HEDGE_VARIANTS:
                rows.append(
                    simulate_window(
                        base=base,
                        expiry_ms=expiry_ms,
                        sample=sample,
                        bars=bars,
                        profile=PRIMARY_PROFILE,
                        hedge=hedge,
                        put=put,
                        call=call,
                        study="tail_hedge",
                    )
                )

    if not rows:
        raise SystemExit("No eligible slow-factor research windows")
    aggregates = aggregate_rows(rows)
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_ROOT / datetime.now(timezone.utc).strftime("btc-eth-%Y%m%d")
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_slow_factor_deep_otm_tail_hedge_research",
        "expiries": [iso_ms(item) for item in expiries],
        "factorProfiles": [asdict(item) for item in FACTOR_PROFILES],
        "primaryProfile": asdict(PRIMARY_PROFILE),
        "hedgeVariants": [asdict(item) for item in HEDGE_VARIANTS],
        "config": {
            "entryHours": ENTRY_HOURS,
            "exitHours": EXIT_HOURS,
            "targetOtmPct": TARGET_OTM_PCT,
            "startingEquity": STARTING_EQUITY,
            "leverage": LEVERAGE,
            "perpFeeBps": PERP_FEE_BPS,
            "perpSlippageBps": PERP_SLIPPAGE_BPS,
            "holdingCostBpsPerDay": HOLDING_COST_BPS_PER_DAY,
            "optionEntryStalenessHours": OPTION_ENTRY_STALENESS_HOURS,
        },
        "optionCoverage": {
            "totalWindows": len(coverage_rows),
            "eligibleWindows": sum(bool(item["eligible"]) for item in coverage_rows),
            "rows": coverage_rows,
        },
        "aggregates": aggregates,
        "decision": decision_payload(aggregates),
        "rows": [asdict(row) for row in rows],
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "rows.csv", rows)
    (output_dir / "report.md").write_text(report_markdown(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"rows={len(rows)} option_coverage={payload['optionCoverage']['eligibleWindows']}/{payload['optionCoverage']['totalWindows']}")
    for item in aggregates:
        if item["sample"] in {"validation", "test"}:
            print(
                f"sample={item['sample']} study={item['study']} variant={item['variant']} "
                f"median_return={item['median_return_pct']:.4f}% median_dd={item['median_max_drawdown_pct']:.4f}% "
                f"worst_dd={item['worst_max_drawdown_pct']:.4f}% count={item['count']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
