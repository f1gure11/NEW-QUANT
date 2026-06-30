from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

from market_selector import MarketCandidate
from okx_client import OkxRestClient
from scoring import plain


@dataclass(slots=True)
class AllocationConfig:
    max_symbols: int = 6
    min_score: Decimal = Decimal("-999999")
    min_fills: int = 1
    max_risk_events: int = 5
    max_weight_pct: Decimal = Decimal("45")
    min_weight_pct: Decimal = Decimal("5")
    cash_reserve_pct: Decimal = Decimal("10")
    min_deploy_pct: Decimal = Decimal("75")
    core_symbols: int = 2
    core_weight_share_pct: Decimal = Decimal("70")
    satellite_max_weight_pct: Decimal = Decimal("12")
    satellite_min_weight_pct: Decimal = Decimal("3")
    default_equity: Decimal = Decimal("100")
    rebalance_threshold_pct: Decimal = Decimal("1")
    close_missing: bool = True


@dataclass(slots=True)
class TargetAllocation:
    inst_id: str
    rank: int
    role: str
    score: Decimal
    weight_pct: Decimal
    target_margin: Decimal
    target_notional: Decimal
    last: Decimal
    order_sz: Decimal
    max_position: Decimal
    pool_window_hours: Decimal
    pool_window_bars: int
    pool_avg_abs_bps: Decimal
    pool_shock_bps: Decimal
    pool_trend_bps: Decimal
    reason: str
    selected_trend_filter: str = "off"
    trend_filter_checked: bool = False
    trend_score_delta: Decimal = Decimal("0")
    market_regime_filter: str = "off"
    market_regime_signal: str = ""
    market_regime_confidence: Decimal = Decimal("0")
    market_regime_allowed_sides: str = ""
    market_regime_model_path: str = ""
    ml_score_delta_vs_baseline: Decimal = Decimal("0")
    ml_return_delta_vs_baseline: Decimal = Decimal("0")
    ml_drawdown_delta_vs_baseline: Decimal = Decimal("0")
    ml_risk_event_delta_vs_baseline: int = 0
    total_return_pct: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
    fills: int = 0
    risk_events: int = 0
    win_rate_pct: Decimal = Decimal("0")


@dataclass(slots=True)
class CurrentExposure:
    inst_id: str
    long_sz: Decimal = Decimal("0")
    short_sz: Decimal = Decimal("0")
    long_notional: Decimal = Decimal("0")
    short_notional: Decimal = Decimal("0")
    net_notional: Decimal = Decimal("0")
    gross_notional: Decimal = Decimal("0")
    margin_estimate: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")


@dataclass(slots=True)
class RebalanceAction:
    inst_id: str
    action: str
    current_weight_pct: Decimal
    target_weight_pct: Decimal
    delta_weight_pct: Decimal
    current_margin: Decimal
    target_margin: Decimal
    delta_margin: Decimal
    note: str


def build_target_allocations(
    score_rows: list[dict[str, Any]],
    candidates: list[MarketCandidate],
    config: AllocationConfig,
    *,
    equity: Decimal | None = None,
    leverage: Decimal = Decimal("3"),
) -> list[TargetAllocation]:
    equity = equity if equity is not None and equity > 0 else config.default_equity
    candidate_by_id = {candidate.inst_id: candidate for candidate in candidates}
    eligible = eligible_score_rows(score_rows, config)
    if not eligible:
        return []
    selected = eligible[: max(0, config.max_symbols)]
    weighted_rows = role_weighted_rows(selected, config)
    targets: list[TargetAllocation] = []
    for row, weight_pct, role in weighted_rows:
        inst_id = str(row.get("inst_id", ""))
        candidate = candidate_by_id.get(inst_id)
        if not candidate:
            continue
        target_margin = equity * weight_pct / Decimal("100")
        target_notional = target_margin * leverage
        targets.append(
            TargetAllocation(
                inst_id=inst_id,
                rank=int(dec(row.get("rank"), Decimal("0"))),
                role=role,
                score=dec(row.get("score")),
                weight_pct=weight_pct,
                target_margin=target_margin,
                target_notional=target_notional,
                last=candidate.last,
                order_sz=contract_size_from_notional(
                    target_notional / Decimal("4"),
                    candidate.last,
                    candidate.ct_val,
                    candidate.lot_sz,
                    candidate.min_sz,
                ),
                max_position=contract_size_from_notional(
                    target_notional,
                    candidate.last,
                    candidate.ct_val,
                    candidate.lot_sz,
                    candidate.min_sz,
                ),
                pool_window_hours=dec(row.get("pool_window_hours")),
                pool_window_bars=int(dec(row.get("pool_window_bars"))),
                pool_avg_abs_bps=dec(row.get("pool_avg_abs_bps")),
                pool_shock_bps=dec(row.get("pool_shock_bps")),
                pool_trend_bps=dec(row.get("pool_trend_bps")),
                reason=f"{role} rank={row.get('rank')} score={plain(dec(row.get('score')))}",
                selected_trend_filter=str(row.get("selected_trend_filter") or row.get("trend_filter") or "off"),
                trend_filter_checked=str(row.get("trend_filter_checked", "")).lower() in {"1", "true", "yes", "on"},
                trend_score_delta=dec(row.get("trend_score_delta")),
                market_regime_filter=str(row.get("market_regime_filter") or "off"),
                market_regime_signal=str(row.get("market_regime_signal") or ""),
                market_regime_confidence=dec(row.get("market_regime_confidence")),
                market_regime_allowed_sides=str(row.get("market_regime_allowed_sides") or ""),
                market_regime_model_path=str(row.get("market_regime_model_path") or ""),
                ml_score_delta_vs_baseline=dec(row.get("ml_score_delta_vs_baseline")),
                ml_return_delta_vs_baseline=dec(row.get("ml_return_delta_vs_baseline")),
                ml_drawdown_delta_vs_baseline=dec(row.get("ml_drawdown_delta_vs_baseline")),
                ml_risk_event_delta_vs_baseline=int(dec(row.get("ml_risk_event_delta_vs_baseline"))),
                total_return_pct=dec(row.get("total_return_pct")),
                max_drawdown_pct=dec(row.get("max_drawdown_pct")),
                profit_factor=dec(row.get("profit_factor")),
                fills=int(dec(row.get("fills"))),
                risk_events=int(dec(row.get("risk_events"))),
                win_rate_pct=dec(row.get("win_rate_pct")),
            )
        )
    return targets


def role_weighted_rows(rows: list[dict[str, Any]], config: AllocationConfig) -> list[tuple[dict[str, Any], Decimal, str]]:
    if not rows:
        return []
    deploy_pct = target_deploy_pct(config)
    core_count = max(0, min(config.core_symbols, len(rows)))
    if core_count <= 0:
        core_count = min(1, len(rows))
    core_rows = rows[:core_count]
    satellite_rows = rows[core_count:]

    if satellite_rows:
        initial_core_budget = deploy_pct * clamp_pct(config.core_weight_share_pct) / Decimal("100")
        satellite_budget = deploy_pct - initial_core_budget
        satellite_weights = score_weights(
            satellite_rows,
            allocatable_pct=satellite_budget,
            max_weight_pct=config.satellite_max_weight_pct,
            min_weight_pct=config.satellite_min_weight_pct,
        )
        core_budget = deploy_pct - sum(satellite_weights, Decimal("0"))
    else:
        satellite_weights = []
        core_budget = deploy_pct

    weighted: list[tuple[dict[str, Any], Decimal, str]] = []
    for row, weight in zip(
        core_rows,
        score_weights(
            core_rows,
            allocatable_pct=core_budget,
            max_weight_pct=config.max_weight_pct,
            min_weight_pct=config.min_weight_pct,
        ),
    ):
        weighted.append((row, weight, "core"))
    for row, weight in zip(satellite_rows, satellite_weights):
        weighted.append((row, weight, "satellite"))
    return weighted


def target_deploy_pct(config: AllocationConfig) -> Decimal:
    reserve_based = Decimal("100") - clamp_pct(config.cash_reserve_pct)
    return clamp_pct(max(config.min_deploy_pct, reserve_based))


def score_weights(
    rows: list[dict[str, Any]],
    *,
    allocatable_pct: Decimal,
    max_weight_pct: Decimal,
    min_weight_pct: Decimal,
) -> list[Decimal]:
    if not rows:
        return []
    score_floor = min((dec(row.get("score")) for row in rows), default=Decimal("0"))
    raw_scores = [max(Decimal("0"), dec(row.get("score")) - score_floor + Decimal("1")) for row in rows]
    if sum(raw_scores, Decimal("0")) <= 0:
        raw_scores = [Decimal("1") for _ in rows]
    return capped_weights(
        raw_scores,
        allocatable_pct=allocatable_pct,
        max_weight_pct=max_weight_pct,
        min_weight_pct=min_weight_pct,
    )


def eligible_score_rows(rows: list[dict[str, Any]], config: AllocationConfig) -> list[dict[str, Any]]:
    eligible = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        if dec(row.get("score")) < config.min_score:
            continue
        if int(dec(row.get("fills"))) < config.min_fills:
            continue
        if int(dec(row.get("risk_events"))) > config.max_risk_events:
            continue
        eligible.append(row)
    eligible.sort(key=lambda row: (dec(row.get("score")), dec(row.get("quote_volume_24h"))), reverse=True)
    return eligible


def capped_weights(
    raw_scores: list[Decimal],
    *,
    allocatable_pct: Decimal,
    max_weight_pct: Decimal,
    min_weight_pct: Decimal,
) -> list[Decimal]:
    if not raw_scores or allocatable_pct <= 0:
        return []
    scores = [max(Decimal("0"), score) for score in raw_scores]
    if sum(scores, Decimal("0")) <= 0:
        scores = [Decimal("1") for _ in raw_scores]

    count = len(scores)
    max_cap = max_weight_pct if max_weight_pct > 0 else Decimal("0")
    min_floor = max(Decimal("0"), min_weight_pct)
    if max_cap > 0:
        min_floor = min(min_floor, max_cap)
    if min_floor * Decimal(count) > allocatable_pct:
        min_floor = Decimal("0")

    weights = [min_floor for _ in scores]
    remaining = allocatable_pct - sum(weights, Decimal("0"))
    active = set(range(count))
    while remaining > Decimal("0.00000001") and active:
        total_score = sum((scores[index] for index in active), Decimal("0"))
        if total_score <= 0:
            total_score = Decimal(len(active))
        capped: set[int] = set()
        additions: dict[int, Decimal] = {}
        for index in active:
            score = scores[index] if sum((scores[item] for item in active), Decimal("0")) > 0 else Decimal("1")
            add = remaining * score / total_score
            proposed = weights[index] + add
            if max_cap > 0 and proposed >= max_cap:
                additions[index] = max(Decimal("0"), max_cap - weights[index])
                capped.add(index)
            else:
                additions[index] = add
        used = sum(additions.values(), Decimal("0"))
        for index, add in additions.items():
            weights[index] += add
        remaining -= used
        if not capped:
            break
        active -= capped
        if used <= 0:
            break
    return weights


def contract_size_from_notional(
    notional: Decimal,
    mark_px: Decimal,
    ct_val: Decimal,
    lot_sz: Decimal,
    min_sz: Decimal,
) -> Decimal:
    if notional <= 0 or mark_px <= 0 or ct_val <= 0:
        return min_sz
    raw_size = notional / (mark_px * ct_val)
    size = round_size_down(raw_size, lot_sz)
    if size < min_sz:
        size = min_sz
    return size


def build_rebalance_actions(
    targets: list[TargetAllocation],
    current: dict[str, CurrentExposure],
    config: AllocationConfig,
) -> list[RebalanceAction]:
    target_by_id = {target.inst_id: target for target in targets}
    inst_ids = set(target_by_id) | set(current)
    actions: list[RebalanceAction] = []
    for inst_id in sorted(inst_ids):
        target = target_by_id.get(inst_id)
        exposure = current.get(inst_id, CurrentExposure(inst_id=inst_id))
        target_margin = target.target_margin if target else Decimal("0")
        target_weight = target.weight_pct if target else Decimal("0")
        current_margin = exposure.margin_estimate
        current_weight = current_margin / config.default_equity * Decimal("100") if config.default_equity > 0 else Decimal("0")
        delta_margin = target_margin - current_margin
        delta_weight = target_weight - current_weight
        action = classify_action(target, exposure, delta_weight, config)
        if action == "hold":
            note = "within threshold"
        elif action == "enter":
            note = "new target allocation"
        elif action == "increase":
            note = "below target allocation"
        elif action == "decrease":
            note = "above target allocation"
        elif action == "exit":
            note = "not selected by target portfolio"
        else:
            note = "no action"
        actions.append(
            RebalanceAction(
                inst_id=inst_id,
                action=action,
                current_weight_pct=current_weight,
                target_weight_pct=target_weight,
                delta_weight_pct=delta_weight,
                current_margin=current_margin,
                target_margin=target_margin,
                delta_margin=delta_margin,
                note=note,
            )
        )
    actions.sort(key=lambda item: action_sort_key(item))
    return actions


def classify_action(
    target: TargetAllocation | None,
    exposure: CurrentExposure,
    delta_weight: Decimal,
    config: AllocationConfig,
) -> str:
    has_exposure = exposure.gross_notional > 0 or exposure.margin_estimate > 0
    if target is None:
        return "exit" if has_exposure and config.close_missing else "ignore"
    if not has_exposure:
        return "enter"
    threshold = max(Decimal("0"), config.rebalance_threshold_pct)
    if threshold > 0 and abs(delta_weight) < threshold:
        return "hold"
    return "increase" if delta_weight > 0 else "decrease"


def action_sort_key(action: RebalanceAction) -> tuple[int, Decimal]:
    priority = {
        "exit": 0,
        "decrease": 1,
        "enter": 2,
        "increase": 3,
        "hold": 4,
        "ignore": 5,
    }.get(action.action, 9)
    return priority, -abs(action.delta_margin)


def fetch_current_exposures(
    client: OkxRestClient,
    *,
    inst_type: str = "SWAP",
    default_leverage: Decimal = Decimal("3"),
) -> dict[str, CurrentExposure]:
    positions = client.get_positions(inst_type).get("data", [])
    exposures: dict[str, CurrentExposure] = {}
    for position in positions:
        inst_id = str(position.get("instId", ""))
        pos = abs(dec(position.get("pos")))
        if not inst_id or pos <= 0:
            continue
        mark_px = dec(position.get("markPx"), dec(position.get("last"), dec(position.get("avgPx"))))
        ct_val = dec(position.get("ctVal"), Decimal("1"))
        leverage = dec(position.get("lever"), default_leverage)
        notional = abs(dec(position.get("notionalUsd")))
        if notional <= 0 and mark_px > 0:
            notional = pos * mark_px * ct_val
        margin = notional / leverage if leverage > 0 else Decimal("0")
        exposure = exposures.setdefault(inst_id, CurrentExposure(inst_id=inst_id))
        pos_side = str(position.get("posSide", "net"))
        if pos_side == "short":
            exposure.short_sz += pos
            exposure.short_notional += notional
        else:
            exposure.long_sz += pos
            exposure.long_notional += notional
        exposure.gross_notional += notional
        exposure.margin_estimate += margin
        exposure.unrealized_pnl += dec(position.get("upl"))
    for exposure in exposures.values():
        exposure.net_notional = exposure.long_notional - exposure.short_notional
    return exposures


def allocation_to_dict(allocation: TargetAllocation) -> dict[str, Any]:
    return jsonable(asdict(allocation))


def exposure_to_dict(exposure: CurrentExposure) -> dict[str, Any]:
    return jsonable(asdict(exposure))


def action_to_dict(action: RebalanceAction) -> dict[str, Any]:
    return jsonable(asdict(action))


def round_size_down(value: Decimal, lot_sz: Decimal) -> Decimal:
    if lot_sz <= 0:
        return value
    return (value / lot_sz).to_integral_value(rounding=ROUND_DOWN) * lot_sz


def clamp_pct(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("100"), value))


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
