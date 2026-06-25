from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(slots=True)
class RollingAdaptiveLimits:
    window: int = 30
    low_vol_bps: Decimal = Decimal("3")
    high_vol_bps: Decimal = Decimal("25")
    min_leverage: Decimal = Decimal("1")
    max_leverage: Decimal = Decimal("5")
    min_grid_bps: Decimal = Decimal("18")
    max_grid_bps: Decimal = Decimal("80")
    grid_vol_multiplier: Decimal = Decimal("2.4")
    min_width_bps: Decimal = Decimal("260")
    max_width_bps: Decimal = Decimal("1200")
    width_vol_multiplier: Decimal = Decimal("14")
    min_order_margin_pct: Decimal = Decimal("3")
    max_order_margin_pct: Decimal = Decimal("10")
    min_max_margin_pct: Decimal = Decimal("12")
    max_max_margin_pct: Decimal = Decimal("35")
    min_stop_bps: Decimal = Decimal("90")
    max_stop_bps: Decimal = Decimal("900")
    stop_vol_multiplier: Decimal = Decimal("8")
    min_tp_bps: Decimal = Decimal("45")
    max_tp_bps: Decimal = Decimal("180")
    tp_grid_multiplier: Decimal = Decimal("2.2")
    min_total_profit_tp_pct: Decimal = Decimal("0.6")
    max_total_profit_tp_pct: Decimal = Decimal("2.5")
    min_total_loss_sl_pct: Decimal = Decimal("0.8")
    max_total_loss_sl_pct: Decimal = Decimal("2.0")


@dataclass(slots=True)
class RollingAdaptiveResult:
    avg_abs_bps: Decimal
    shock_bps: Decimal
    rolling_vol_bps: Decimal
    trend_bps: Decimal
    risk_score: Decimal
    leverage: Decimal
    grid_bps: Decimal
    adaptive_width_bps: Decimal
    adaptive_min_width_bps: Decimal
    adaptive_max_width_bps: Decimal
    order_margin_pct: Decimal
    max_margin_pct: Decimal
    min_tp_bps: Decimal
    position_loss_sl_bps: Decimal
    exchange_stop_bps: Decimal
    total_profit_tp_pct: Decimal
    total_loss_sl_pct: Decimal
    min_contract_margin: Decimal
    min_contract_margin_pct: Decimal
    tradeable_min_contract: bool
    note: str


def calculate_rolling_adaptive(
    candles: list[list[str]],
    *,
    mark_px: Decimal,
    equity: Decimal,
    ct_val: Decimal,
    min_sz: Decimal,
    limits: RollingAdaptiveLimits | None = None,
) -> RollingAdaptiveResult:
    limits = limits or RollingAdaptiveLimits()
    returns = rolling_return_bps(candles, limits.window)
    abs_returns = [abs(value) for value in returns]
    avg_abs_bps = sum(abs_returns, Decimal("0")) / Decimal(len(abs_returns)) if abs_returns else Decimal("0")
    shock_bps = max(abs_returns) if abs_returns else Decimal("0")
    rolling_vol_bps = max(avg_abs_bps, shock_bps / Decimal("3"))
    trend_bps = rolling_trend_bps(candles, limits.window)

    vol_score = scale_score(rolling_vol_bps, limits.low_vol_bps, limits.high_vol_bps)
    trend_score = scale_score(abs(trend_bps), limits.low_vol_bps * Decimal("2"), limits.high_vol_bps * Decimal("3"))
    risk_score = max(vol_score, trend_score / Decimal("2"))

    leverage = rounded_int(lerp(limits.max_leverage, limits.min_leverage, risk_score))
    leverage = clamp(leverage, limits.min_leverage, limits.max_leverage)
    if leverage <= 0:
        leverage = Decimal("1")

    grid_bps = clamp(
        rolling_vol_bps * limits.grid_vol_multiplier,
        limits.min_grid_bps,
        limits.max_grid_bps,
    )
    adaptive_width_bps = clamp(
        rolling_vol_bps * limits.width_vol_multiplier,
        limits.min_width_bps,
        limits.max_width_bps,
    )
    adaptive_min_width_bps = clamp(adaptive_width_bps * Decimal("0.75"), limits.min_width_bps, limits.max_width_bps)
    adaptive_max_width_bps = clamp(adaptive_width_bps * Decimal("1.35"), limits.min_width_bps, limits.max_width_bps)
    if adaptive_max_width_bps < adaptive_min_width_bps:
        adaptive_max_width_bps = adaptive_min_width_bps

    order_margin_pct = clamp(
        lerp(limits.max_order_margin_pct, limits.min_order_margin_pct, risk_score),
        limits.min_order_margin_pct,
        limits.max_order_margin_pct,
    )
    max_margin_pct = clamp(
        lerp(limits.max_max_margin_pct, limits.min_max_margin_pct, risk_score),
        limits.min_max_margin_pct,
        limits.max_max_margin_pct,
    )

    exit_params = adaptive_exit_parameters(grid_bps, rolling_vol_bps, risk_score, limits)
    min_tp_bps = exit_params["min_tp_bps"]
    position_loss_sl_bps = exit_params["position_loss_sl_bps"]
    exchange_stop_bps = exit_params["exchange_stop_bps"]
    total_profit_tp_pct = exit_params["total_profit_tp_pct"]
    total_loss_sl_pct = exit_params["total_loss_sl_pct"]

    min_contract_margin = Decimal("0")
    min_contract_margin_pct = Decimal("0")
    if mark_px > 0 and ct_val > 0 and min_sz > 0 and leverage > 0:
        min_contract_margin = min_sz * ct_val * mark_px / leverage
        if equity > 0:
            min_contract_margin_pct = min_contract_margin / equity * Decimal("100")
    tradeable_min_contract = equity <= 0 or min_contract_margin_pct <= max_margin_pct

    note = (
        f"rolling window={limits.window} avg_abs={plain(avg_abs_bps)}bps "
        f"shock={plain(shock_bps)}bps trend={plain(trend_bps)}bps "
        f"risk={plain(risk_score)} min_contract_margin={plain(min_contract_margin)}"
    )
    return RollingAdaptiveResult(
        avg_abs_bps=avg_abs_bps,
        shock_bps=shock_bps,
        rolling_vol_bps=rolling_vol_bps,
        trend_bps=trend_bps,
        risk_score=risk_score,
        leverage=leverage,
        grid_bps=grid_bps,
        adaptive_width_bps=adaptive_width_bps,
        adaptive_min_width_bps=adaptive_min_width_bps,
        adaptive_max_width_bps=adaptive_max_width_bps,
        order_margin_pct=order_margin_pct,
        max_margin_pct=max_margin_pct,
        min_tp_bps=min_tp_bps,
        position_loss_sl_bps=position_loss_sl_bps,
        exchange_stop_bps=exchange_stop_bps,
        total_profit_tp_pct=total_profit_tp_pct,
        total_loss_sl_pct=total_loss_sl_pct,
        min_contract_margin=min_contract_margin,
        min_contract_margin_pct=min_contract_margin_pct,
        tradeable_min_contract=tradeable_min_contract,
        note=note,
    )


def rolling_return_bps(candles: list[list[str]], window: int) -> list[Decimal]:
    closes = candle_closes(candles, window + 1)
    values: list[Decimal] = []
    for index in range(len(closes) - 1):
        prev = closes[index + 1]
        if prev > 0:
            values.append((closes[index] / prev - Decimal("1")) * Decimal("10000"))
    return values


def adaptive_exit_parameters(
    grid_bps: Decimal,
    rolling_vol_bps: Decimal,
    risk_score: Decimal,
    limits: RollingAdaptiveLimits,
) -> dict[str, Decimal]:
    min_tp_bps = clamp(grid_bps * limits.tp_grid_multiplier, limits.min_tp_bps, limits.max_tp_bps)
    loss_reward_ratio = lerp(Decimal("1.7"), Decimal("2.4"), risk_score)
    raw_stop_bps = max(min_tp_bps * loss_reward_ratio, rolling_vol_bps * limits.stop_vol_multiplier)
    position_loss_sl_bps = clamp(raw_stop_bps, limits.min_stop_bps, limits.max_stop_bps)
    exchange_stop_bps = clamp(position_loss_sl_bps * Decimal("1.08"), limits.min_stop_bps, limits.max_stop_bps)
    total_profit_tp_pct = clamp(
        lerp(limits.max_total_profit_tp_pct, limits.min_total_profit_tp_pct, risk_score),
        limits.min_total_profit_tp_pct,
        limits.max_total_profit_tp_pct,
    )
    total_loss_sl_pct = clamp(
        max(total_profit_tp_pct * Decimal("1.15"), lerp(limits.max_total_loss_sl_pct, limits.min_total_loss_sl_pct, risk_score)),
        limits.min_total_loss_sl_pct,
        limits.max_total_loss_sl_pct,
    )
    return {
        "min_tp_bps": min_tp_bps,
        "position_loss_sl_bps": position_loss_sl_bps,
        "exchange_stop_bps": exchange_stop_bps,
        "total_profit_tp_pct": total_profit_tp_pct,
        "total_loss_sl_pct": total_loss_sl_pct,
    }


def rolling_trend_bps(candles: list[list[str]], window: int) -> Decimal:
    closes = candle_closes(candles, window + 1)
    if len(closes) < 2 or closes[-1] <= 0:
        return Decimal("0")
    return (closes[0] / closes[-1] - Decimal("1")) * Decimal("10000")


def candle_closes(candles: list[list[str]], limit: int) -> list[Decimal]:
    closes: list[Decimal] = []
    for item in candles[: max(0, limit)]:
        if len(item) <= 4:
            continue
        close = dec(item[4])
        if close > 0:
            closes.append(close)
    return closes


def scale_score(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    if high <= low:
        return Decimal("0")
    return clamp((value - low) / (high - low), Decimal("0"), Decimal("1"))


def lerp(low_risk_value: Decimal, high_risk_value: Decimal, risk_score: Decimal) -> Decimal:
    score = clamp(risk_score, Decimal("0"), Decimal("1"))
    return low_risk_value + (high_risk_value - low_risk_value) * score


def clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    if upper < lower:
        lower, upper = upper, lower
    return max(lower, min(value, upper))


def rounded_int(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_HALF_UP)


def result_to_dict(result: RollingAdaptiveResult) -> dict[str, Any]:
    return jsonable(asdict(result))


def limits_to_dict(limits: RollingAdaptiveLimits) -> dict[str, Any]:
    return jsonable(asdict(limits))


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")
