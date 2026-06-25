from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class ScoreWeights:
    return_weight: Decimal = Decimal("4")
    drawdown_weight: Decimal = Decimal("3")
    profit_factor_weight: Decimal = Decimal("2")
    fill_weight: Decimal = Decimal("5")
    risk_event_penalty: Decimal = Decimal("7")
    no_trade_penalty: Decimal = Decimal("20")
    fill_target: Decimal = Decimal("20")
    profit_factor_cap: Decimal = Decimal("5")


@dataclass(slots=True)
class ScoreBreakdown:
    score: Decimal
    return_component: Decimal
    drawdown_component: Decimal
    profit_factor_component: Decimal
    fill_component: Decimal
    risk_penalty: Decimal
    no_trade_penalty: Decimal


def score_backtest(result: Any, weights: ScoreWeights | None = None) -> ScoreBreakdown:
    weights = weights or ScoreWeights()
    total_return_pct = dec(getattr(result, "total_return_pct", Decimal("0")))
    max_drawdown_pct = max(Decimal("0"), dec(getattr(result, "max_drawdown_pct", Decimal("0"))))
    profit_factor = max(Decimal("0"), dec(getattr(result, "profit_factor", Decimal("0"))))
    fills = max(Decimal("0"), dec(getattr(result, "fills", Decimal("0"))))
    risk_events = max(Decimal("0"), dec(getattr(result, "risk_events", Decimal("0"))))

    capped_profit_factor = min(profit_factor, weights.profit_factor_cap)
    fill_ratio = Decimal("0")
    if weights.fill_target > 0:
        fill_ratio = min(Decimal("1"), fills / weights.fill_target)

    return_component = total_return_pct * weights.return_weight
    drawdown_component = max_drawdown_pct * weights.drawdown_weight
    profit_factor_component = capped_profit_factor * weights.profit_factor_weight
    fill_component = fill_ratio * weights.fill_weight
    risk_penalty = risk_events * weights.risk_event_penalty
    no_trade_penalty = weights.no_trade_penalty if fills <= 0 else Decimal("0")
    score = (
        return_component
        - drawdown_component
        + profit_factor_component
        + fill_component
        - risk_penalty
        - no_trade_penalty
    )
    return ScoreBreakdown(
        score=score,
        return_component=return_component,
        drawdown_component=drawdown_component,
        profit_factor_component=profit_factor_component,
        fill_component=fill_component,
        risk_penalty=risk_penalty,
        no_trade_penalty=no_trade_penalty,
    )


def score_to_dict(score: ScoreBreakdown) -> dict[str, Any]:
    return jsonable(asdict(score))


def weights_to_dict(weights: ScoreWeights) -> dict[str, Any]:
    return jsonable(asdict(weights))


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
