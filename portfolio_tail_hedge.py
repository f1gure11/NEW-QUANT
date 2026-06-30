from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

from market_selector import MarketCandidate
from okx_client import OkxApiError, OkxRestClient, load_env
from portfolio_allocator import CurrentExposure, TargetAllocation
from scoring import plain


LOG_PATH = Path("data") / "okx" / "portfolio_tail_hedge_actions.jsonl"
STATE_PATH = Path("data") / "okx" / "portfolio_tail_hedge_state.json"
HEDGE_ACTION_FIELDS = [
    "inst_id",
    "action",
    "side",
    "pos_side",
    "sz",
    "reduce_only",
    "estimated_px",
    "target_notional",
    "estimated_notional",
    "target_hedge_ratio",
    "hedge_level",
    "max_margin_pct",
    "leverage",
    "ord_type",
    "status",
    "reason",
    "note",
]

NON_CRYPTO_BASES = {
    "XAU",
    "XAG",
    "GOLD",
    "SILVER",
    "USOIL",
    "UKOIL",
    "BRENT",
    "WTI",
    "SPX",
    "SPY",
    "SP500",
    "US500",
    "NAS",
    "NDX",
    "US100",
    "DJI",
    "DOW",
    "US30",
    "AAPL",
    "AMD",
    "AMZN",
    "BABA",
    "COIN",
    "GOOG",
    "GOOGL",
    "META",
    "MSFT",
    "MSTR",
    "NFLX",
    "NIO",
    "NVDA",
    "TSLA",
}


@dataclass(slots=True)
class TailHedgeConfig:
    mode: str = "plan"
    hedge_inst_id: str = ""
    hedge_ratio: Decimal = Decimal("0.35")
    stress_hedge_ratio: Decimal = Decimal("0.70")
    full_hedge_ratio: Decimal = Decimal("1")
    trigger_net_exposure_pct: Decimal = Decimal("120")
    trigger_shock_bps: Decimal = Decimal("120")
    trigger_trend_bps: Decimal = Decimal("350")
    trigger_risk_events: int = 8
    stress_net_exposure_pct: Decimal = Decimal("180")
    stress_shock_bps: Decimal = Decimal("180")
    stress_trend_bps: Decimal = Decimal("550")
    stress_risk_events: int = 40
    full_hedge_net_exposure_pct: Decimal = Decimal("240")
    full_hedge_shock_bps: Decimal = Decimal("260")
    full_hedge_trend_bps: Decimal = Decimal("800")
    full_hedge_risk_events: int = 80
    min_hedge_notional: Decimal = Decimal("10")
    max_hedge_margin_pct: Decimal = Decimal("20")
    stress_hedge_max_margin_pct: Decimal = Decimal("40")
    full_hedge_max_margin_pct: Decimal = Decimal("100")
    hedge_leverage: Decimal = Decimal("3")
    ord_type: str = "market"


@dataclass(slots=True)
class TailHedgeAction:
    inst_id: str
    action: str
    side: str
    pos_side: str
    sz: Decimal
    reduce_only: bool
    estimated_px: Decimal
    target_notional: Decimal
    estimated_notional: Decimal
    target_hedge_ratio: Decimal
    hedge_level: str
    max_margin_pct: Decimal
    leverage: Decimal
    ord_type: str
    status: str
    reason: str
    note: str


@dataclass(slots=True)
class TailHedgePlan:
    generated_at: str
    mode: str
    status: str
    equity: Decimal
    gross_notional: Decimal
    net_notional: Decimal
    net_exposure_pct: Decimal
    long_notional: Decimal
    short_notional: Decimal
    max_shock_bps: Decimal
    max_abs_trend_bps: Decimal
    total_risk_events: int
    hedge_basis_notional: Decimal
    existing_hedge_notional: Decimal
    target_hedge_ratio: Decimal
    target_hedge_level: str
    target_hedge_notional: Decimal
    trigger_reasons: list[str]
    actions: list[TailHedgeAction]
    note: str
    config: TailHedgeConfig


def build_tail_hedge_plan(
    *,
    targets: list[TargetAllocation],
    current_exposures: dict[str, CurrentExposure],
    candidates: list[MarketCandidate],
    score_rows: list[dict[str, Any]],
    equity: Decimal,
    config: TailHedgeConfig | None = None,
    generated_at: str = "",
) -> TailHedgePlan:
    config = config or TailHedgeConfig()
    generated_at = generated_at or now_iso()
    long_notional = sum((exposure.long_notional for exposure in current_exposures.values()), Decimal("0"))
    short_notional = sum((exposure.short_notional for exposure in current_exposures.values()), Decimal("0"))
    gross_notional = sum((exposure.gross_notional for exposure in current_exposures.values()), Decimal("0"))
    net_notional = sum((exposure.net_notional for exposure in current_exposures.values()), Decimal("0"))
    net_exposure_pct = abs(net_notional) / equity * Decimal("100") if equity > 0 else Decimal("0")
    max_shock_bps = max_tail_metric(targets, score_rows, "pool_shock_bps")
    max_abs_trend_bps = max_abs_tail_metric(targets, score_rows, "pool_trend_bps")
    total_risk_events = sum_tail_risk_events(targets, score_rows)
    trigger_reasons = tail_trigger_reasons(
        config=config,
        net_exposure_pct=net_exposure_pct,
        max_shock_bps=max_shock_bps,
        max_abs_trend_bps=max_abs_trend_bps,
        total_risk_events=total_risk_events,
    )
    dynamic_target = dynamic_hedge_target(
        config=config,
        net_exposure_pct=net_exposure_pct,
        max_shock_bps=max_shock_bps,
        max_abs_trend_bps=max_abs_trend_bps,
        total_risk_events=total_risk_events,
    )

    if config.mode == "off":
        return tail_plan(
            generated_at,
            config,
            "disabled",
            equity,
            gross_notional,
            net_notional,
            net_exposure_pct,
            long_notional,
            short_notional,
            max_shock_bps,
            max_abs_trend_bps,
            total_risk_events,
            abs(net_notional),
            Decimal("0"),
            dynamic_target["ratio"],
            str(dynamic_target["level"]),
            Decimal("0"),
            [],
            [],
            "tail hedge mode is off",
        )
    if not current_exposures:
        return tail_plan(
            generated_at,
            config,
            "no_account",
            equity,
            gross_notional,
            net_notional,
            net_exposure_pct,
            long_notional,
            short_notional,
            max_shock_bps,
            max_abs_trend_bps,
            total_risk_events,
            abs(net_notional),
            Decimal("0"),
            dynamic_target["ratio"],
            str(dynamic_target["level"]),
            Decimal("0"),
            trigger_reasons,
            [],
            "account exposures are unavailable; pass --include-account to size a hedge plan",
        )
    if abs(net_notional) <= 0:
        return tail_plan(
            generated_at,
            config,
            "watch",
            equity,
            gross_notional,
            net_notional,
            net_exposure_pct,
            long_notional,
            short_notional,
            max_shock_bps,
            max_abs_trend_bps,
            total_risk_events,
            abs(net_notional),
            Decimal("0"),
            dynamic_target["ratio"],
            str(dynamic_target["level"]),
            Decimal("0"),
            trigger_reasons,
            [],
            "no net directional exposure to hedge",
        )
    if not trigger_reasons:
        return tail_plan(
            generated_at,
            config,
            "watch",
            equity,
            gross_notional,
            net_notional,
            net_exposure_pct,
            long_notional,
            short_notional,
            max_shock_bps,
            max_abs_trend_bps,
            total_risk_events,
            abs(net_notional),
            Decimal("0"),
            dynamic_target["ratio"],
            str(dynamic_target["level"]),
            Decimal("0"),
            [],
            [],
            "tail hedge triggers were not reached",
        )

    target_ratio = dynamic_target["ratio"]
    target_level = str(dynamic_target["level"])
    max_margin_pct = dec(dynamic_target["max_margin_pct"], config.max_hedge_margin_pct)
    target_notional = target_hedge_notional(abs(net_notional), equity, target_ratio, max_margin_pct, config)
    if target_notional < config.min_hedge_notional:
        return tail_plan(
            generated_at,
            config,
            "watch",
            equity,
            gross_notional,
            net_notional,
            net_exposure_pct,
            long_notional,
            short_notional,
            max_shock_bps,
            max_abs_trend_bps,
            total_risk_events,
            abs(net_notional),
            Decimal("0"),
            target_ratio,
            target_level,
            target_notional,
            trigger_reasons,
            [],
            f"computed hedge notional {plain(target_notional)} is below minimum {plain(config.min_hedge_notional)}",
        )

    cap_notional = hedge_cap_notional(
        equity,
        TailHedgeConfig(
            max_hedge_margin_pct=max_margin_pct,
            hedge_leverage=config.hedge_leverage,
        ),
    )
    actions, action_note = build_hedge_actions(
        current_exposures=current_exposures,
        candidates=candidates,
        net_notional=net_notional,
        target_ratio=target_ratio,
        target_level=target_level,
        target_notional=target_notional,
        max_margin_pct=max_margin_pct,
        cap_notional=cap_notional,
        trigger_reasons=trigger_reasons,
        config=config,
    )
    if not actions:
        return tail_plan(
            generated_at,
            config,
            "blocked",
            equity,
            gross_notional,
            net_notional,
            net_exposure_pct,
            long_notional,
            short_notional,
            max_shock_bps,
            max_abs_trend_bps,
            total_risk_events,
            abs(net_notional),
            Decimal("0"),
            target_ratio,
            target_level,
            target_notional,
            trigger_reasons,
            [],
            action_note,
        )

    plan_status = "blocked" if any(action.status == "blocked" for action in actions) else "triggered"
    return tail_plan(
        generated_at,
        config,
        plan_status,
        equity,
        gross_notional,
        net_notional,
        net_exposure_pct,
        long_notional,
        short_notional,
        max_shock_bps,
        max_abs_trend_bps,
        total_risk_events,
        abs(net_notional),
        Decimal("0"),
        target_ratio,
        target_level,
        target_notional,
        trigger_reasons,
        actions,
        action_note or "tail hedge action can be auto-executed by the scheduled hedge guard",
    )


def tail_plan(
    generated_at: str,
    config: TailHedgeConfig,
    status: str,
    equity: Decimal,
    gross_notional: Decimal,
    net_notional: Decimal,
    net_exposure_pct: Decimal,
    long_notional: Decimal,
    short_notional: Decimal,
    max_shock_bps: Decimal,
    max_abs_trend_bps: Decimal,
    total_risk_events: int,
    hedge_basis_notional: Decimal,
    existing_hedge_notional: Decimal,
    target_hedge_ratio: Decimal,
    target_hedge_level: str,
    target_hedge_notional: Decimal,
    trigger_reasons: list[str],
    actions: list[TailHedgeAction],
    note: str,
) -> TailHedgePlan:
    return TailHedgePlan(
        generated_at=generated_at,
        mode=config.mode,
        status=status,
        equity=equity,
        gross_notional=gross_notional,
        net_notional=net_notional,
        net_exposure_pct=net_exposure_pct,
        long_notional=long_notional,
        short_notional=short_notional,
        max_shock_bps=max_shock_bps,
        max_abs_trend_bps=max_abs_trend_bps,
        total_risk_events=total_risk_events,
        hedge_basis_notional=hedge_basis_notional,
        existing_hedge_notional=existing_hedge_notional,
        target_hedge_ratio=target_hedge_ratio,
        target_hedge_level=target_hedge_level,
        target_hedge_notional=target_hedge_notional,
        trigger_reasons=trigger_reasons,
        actions=actions,
        note=note,
        config=config,
    )


def tail_trigger_reasons(
    *,
    config: TailHedgeConfig,
    net_exposure_pct: Decimal,
    max_shock_bps: Decimal,
    max_abs_trend_bps: Decimal,
    total_risk_events: int,
) -> list[str]:
    reasons: list[str] = []
    if net_exposure_pct >= config.trigger_net_exposure_pct:
        reasons.append(f"net exposure {plain(net_exposure_pct)}% >= {plain(config.trigger_net_exposure_pct)}%")
    if max_shock_bps >= config.trigger_shock_bps:
        reasons.append(f"shock {plain(max_shock_bps)}bps >= {plain(config.trigger_shock_bps)}bps")
    if max_abs_trend_bps >= config.trigger_trend_bps:
        reasons.append(f"trend {plain(max_abs_trend_bps)}bps >= {plain(config.trigger_trend_bps)}bps")
    if config.trigger_risk_events > 0 and total_risk_events >= config.trigger_risk_events:
        reasons.append(f"risk events {total_risk_events} >= {config.trigger_risk_events}")
    return reasons


def dynamic_hedge_target(
    *,
    config: TailHedgeConfig,
    net_exposure_pct: Decimal,
    max_shock_bps: Decimal,
    max_abs_trend_bps: Decimal,
    total_risk_events: int,
) -> dict[str, Any]:
    base_ratio = clamp(config.hedge_ratio, Decimal("0"), Decimal("1"))
    if config.mode != "dynamic":
        return {
            "level": "fixed",
            "ratio": base_ratio,
            "max_margin_pct": config.max_hedge_margin_pct,
            "reasons": [],
        }

    full_reasons = hedge_level_reasons(
        level="full",
        net_exposure_pct=net_exposure_pct,
        net_threshold=config.full_hedge_net_exposure_pct,
        max_shock_bps=max_shock_bps,
        shock_threshold=config.full_hedge_shock_bps,
        max_abs_trend_bps=max_abs_trend_bps,
        trend_threshold=config.full_hedge_trend_bps,
        total_risk_events=total_risk_events,
        risk_threshold=config.full_hedge_risk_events,
    )
    if full_reasons:
        return {
            "level": "full",
            "ratio": clamp(config.full_hedge_ratio, base_ratio, Decimal("1")),
            "max_margin_pct": max(config.max_hedge_margin_pct, config.full_hedge_max_margin_pct),
            "reasons": full_reasons,
        }

    stress_reasons = hedge_level_reasons(
        level="stress",
        net_exposure_pct=net_exposure_pct,
        net_threshold=config.stress_net_exposure_pct,
        max_shock_bps=max_shock_bps,
        shock_threshold=config.stress_shock_bps,
        max_abs_trend_bps=max_abs_trend_bps,
        trend_threshold=config.stress_trend_bps,
        total_risk_events=total_risk_events,
        risk_threshold=config.stress_risk_events,
    )
    if stress_reasons:
        return {
            "level": "stress",
            "ratio": clamp(config.stress_hedge_ratio, base_ratio, Decimal("1")),
            "max_margin_pct": max(config.max_hedge_margin_pct, config.stress_hedge_max_margin_pct),
            "reasons": stress_reasons,
        }

    return {
        "level": "base",
        "ratio": base_ratio,
        "max_margin_pct": config.max_hedge_margin_pct,
        "reasons": [],
    }


def hedge_level_reasons(
    *,
    level: str,
    net_exposure_pct: Decimal,
    net_threshold: Decimal,
    max_shock_bps: Decimal,
    shock_threshold: Decimal,
    max_abs_trend_bps: Decimal,
    trend_threshold: Decimal,
    total_risk_events: int,
    risk_threshold: int,
) -> list[str]:
    reasons: list[str] = []
    if net_threshold > 0 and net_exposure_pct >= net_threshold:
        reasons.append(f"{level} net exposure {plain(net_exposure_pct)}% >= {plain(net_threshold)}%")
    if shock_threshold > 0 and max_shock_bps >= shock_threshold:
        reasons.append(f"{level} shock {plain(max_shock_bps)}bps >= {plain(shock_threshold)}bps")
    if trend_threshold > 0 and max_abs_trend_bps >= trend_threshold:
        reasons.append(f"{level} trend {plain(max_abs_trend_bps)}bps >= {plain(trend_threshold)}bps")
    if risk_threshold > 0 and total_risk_events >= risk_threshold:
        reasons.append(f"{level} risk events {total_risk_events} >= {risk_threshold}")
    return reasons


def target_hedge_notional(
    basis_notional: Decimal,
    equity: Decimal,
    target_ratio: Decimal,
    max_margin_pct: Decimal,
    config: TailHedgeConfig,
) -> Decimal:
    uncapped = basis_notional * clamp(target_ratio, Decimal("0"), Decimal("1"))
    cap_notional = hedge_cap_notional(
        equity,
        TailHedgeConfig(
            max_hedge_margin_pct=max_margin_pct,
            hedge_leverage=config.hedge_leverage,
        ),
    )
    return min(uncapped, cap_notional) if cap_notional > 0 else uncapped


def build_hedge_actions(
    *,
    current_exposures: dict[str, CurrentExposure],
    candidates: list[MarketCandidate],
    net_notional: Decimal,
    target_ratio: Decimal,
    target_level: str,
    target_notional: Decimal,
    max_margin_pct: Decimal,
    cap_notional: Decimal,
    trigger_reasons: list[str],
    config: TailHedgeConfig,
) -> tuple[list[TailHedgeAction], str]:
    candidate_by_id = {candidate.inst_id: candidate for candidate in candidates}
    buckets = exposure_buckets(current_exposures)
    actions: list[TailHedgeAction] = []
    notes: list[str] = []
    for bucket in buckets:
        bucket_target_notional = allocate_bucket_target(bucket, abs(net_notional), target_notional)
        if bucket_target_notional < config.min_hedge_notional:
            notes.append(f"{bucket['kind']} target {plain(bucket_target_notional)} below minimum")
            continue
        if bucket["kind"] == "crypto":
            candidate = choose_crypto_hedge_candidate(candidates, config.hedge_inst_id)
            if candidate is None:
                notes.append("no crypto hedge instrument metadata was available")
                continue
            actions.append(
                hedge_action_from_candidate(
                    candidate=candidate,
                    net_notional=dec(bucket["net_notional"]),
                    target_notional=bucket_target_notional,
                    cap_notional=cap_notional,
                    target_ratio=target_ratio,
                    target_level=target_level,
                    max_margin_pct=max_margin_pct,
                    trigger_reasons=trigger_reasons,
                    config=config,
                    note_prefix="crypto basket hedge",
                )
            )
            continue

        for exposure in bucket["exposures"]:
            inst_target_notional = abs(exposure.net_notional) * bucket_target_notional / dec(bucket["abs_net_notional"])
            if inst_target_notional < config.min_hedge_notional:
                notes.append(f"{exposure.inst_id} target {plain(inst_target_notional)} below minimum")
                continue
            candidate = candidate_by_id.get(exposure.inst_id)
            if candidate is None:
                action = reduce_only_action_from_exposure(
                    exposure=exposure,
                    target_notional=inst_target_notional,
                    target_ratio=target_ratio,
                    target_level=target_level,
                    max_margin_pct=max_margin_pct,
                    trigger_reasons=trigger_reasons,
                    config=config,
                    note="non-crypto exposure has no same-instrument metadata; reduce only instead of cross-asset hedge",
                )
                actions.append(action)
                continue
            actions.append(
                hedge_action_from_candidate(
                    candidate=candidate,
                    net_notional=exposure.net_notional,
                    target_notional=inst_target_notional,
                    cap_notional=cap_notional,
                    target_ratio=target_ratio,
                    target_level=target_level,
                    max_margin_pct=max_margin_pct,
                    trigger_reasons=trigger_reasons,
                    config=config,
                    note_prefix="same-instrument non-crypto hedge",
                )
            )
    ready_count = sum(1 for action in actions if action.status == "ready")
    if ready_count:
        notes.append(f"{ready_count} hedge action(s) ready")
    return actions, "; ".join(notes)


def exposure_buckets(current_exposures: dict[str, CurrentExposure]) -> list[dict[str, Any]]:
    crypto_exposures: list[CurrentExposure] = []
    non_crypto_exposures: list[CurrentExposure] = []
    for exposure in current_exposures.values():
        if exposure.net_notional == 0:
            continue
        if is_crypto_inst(exposure.inst_id):
            crypto_exposures.append(exposure)
        else:
            non_crypto_exposures.append(exposure)

    buckets: list[dict[str, Any]] = []
    crypto_net = sum((item.net_notional for item in crypto_exposures), Decimal("0"))
    if crypto_net != 0:
        buckets.append(
            {
                "kind": "crypto",
                "net_notional": crypto_net,
                "abs_net_notional": abs(crypto_net),
                "exposures": crypto_exposures,
            }
        )
    for exposure in non_crypto_exposures:
        buckets.append(
            {
                "kind": "same_instrument",
                "net_notional": exposure.net_notional,
                "abs_net_notional": abs(exposure.net_notional),
                "exposures": [exposure],
            }
        )
    return buckets


def allocate_bucket_target(bucket: dict[str, Any], total_abs_net: Decimal, target_notional: Decimal) -> Decimal:
    if total_abs_net <= 0:
        return Decimal("0")
    return target_notional * dec(bucket.get("abs_net_notional")) / total_abs_net


def hedge_action_from_candidate(
    *,
    candidate: MarketCandidate,
    net_notional: Decimal,
    target_notional: Decimal,
    cap_notional: Decimal,
    target_ratio: Decimal,
    target_level: str,
    max_margin_pct: Decimal,
    trigger_reasons: list[str],
    config: TailHedgeConfig,
    note_prefix: str,
) -> TailHedgeAction:
    size_result = hedge_size_from_notional(target_notional, candidate, cap_notional)
    status = str(size_result.get("status", "blocked"))
    note = str(size_result.get("note", ""))
    if status == "ready":
        note = (
            f"{note_prefix}; hedge_level={target_level} target_hedge_ratio={plain(target_ratio)} "
            f"against net_notional={plain(net_notional)}"
        )
    return TailHedgeAction(
        inst_id=candidate.inst_id,
        action="increase",
        side="sell" if net_notional > 0 else "buy",
        pos_side="short" if net_notional > 0 else "long",
        sz=dec(size_result.get("size")),
        reduce_only=False,
        estimated_px=candidate.last,
        target_notional=target_notional,
        estimated_notional=dec(size_result.get("estimated_notional")),
        target_hedge_ratio=target_ratio,
        hedge_level=target_level,
        max_margin_pct=max_margin_pct,
        leverage=config.hedge_leverage,
        ord_type=config.ord_type,
        status="ready" if status == "ready" else "blocked",
        reason="; ".join(trigger_reasons),
        note=note,
    )


def reduce_only_action_from_exposure(
    *,
    exposure: CurrentExposure,
    target_notional: Decimal,
    target_ratio: Decimal,
    target_level: str,
    max_margin_pct: Decimal,
    trigger_reasons: list[str],
    config: TailHedgeConfig,
    note: str,
) -> TailHedgeAction:
    if exposure.net_notional > 0:
        pos_side = "long"
        side = "sell"
        available_size = exposure.long_sz
        basis_notional = exposure.long_notional
    else:
        pos_side = "short"
        side = "buy"
        available_size = exposure.short_sz
        basis_notional = exposure.short_notional
    size = proportional_reduce_size(available_size, target_notional, basis_notional)
    status = "ready" if size > 0 else "blocked"
    return TailHedgeAction(
        inst_id=exposure.inst_id,
        action="reduce",
        side=side,
        pos_side=pos_side,
        sz=size,
        reduce_only=True,
        estimated_px=Decimal("0"),
        target_notional=target_notional,
        estimated_notional=target_notional if status == "ready" else Decimal("0"),
        target_hedge_ratio=target_ratio,
        hedge_level=target_level,
        max_margin_pct=max_margin_pct,
        leverage=config.hedge_leverage,
        ord_type="market",
        status=status,
        reason="; ".join(trigger_reasons),
        note=note if status == "ready" else f"{note}; unavailable position size for reduce-only action",
    )


def proportional_reduce_size(size: Decimal, target_notional: Decimal, basis_notional: Decimal) -> Decimal:
    if size <= 0 or target_notional <= 0:
        return Decimal("0")
    if basis_notional <= 0:
        return size
    ratio = clamp(target_notional / basis_notional, Decimal("0"), Decimal("1"))
    return size * ratio


def is_crypto_inst(inst_id: str) -> bool:
    base = inst_base_ccy(inst_id)
    return bool(base) and base not in NON_CRYPTO_BASES


def inst_base_ccy(inst_id: str) -> str:
    return str(inst_id).split("-")[0].upper()


def choose_hedge_candidate(candidates: list[MarketCandidate], preferred: str = "") -> MarketCandidate | None:
    return choose_crypto_hedge_candidate(candidates, preferred)


def choose_crypto_hedge_candidate(candidates: list[MarketCandidate], preferred: str = "") -> MarketCandidate | None:
    by_id = {candidate.inst_id: candidate for candidate in candidates}
    if preferred and preferred in by_id and is_crypto_inst(preferred):
        return by_id[preferred]
    for inst_id in ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"):
        if inst_id in by_id:
            return by_id[inst_id]
    live = [candidate for candidate in candidates if candidate.state == "live" and is_crypto_inst(candidate.inst_id)]
    if not live:
        return None
    return max(live, key=lambda item: item.quote_volume_24h)


def hedge_cap_notional(equity: Decimal, config: TailHedgeConfig) -> Decimal:
    if equity <= 0 or config.max_hedge_margin_pct <= 0 or config.hedge_leverage <= 0:
        return Decimal("0")
    return equity * config.max_hedge_margin_pct / Decimal("100") * config.hedge_leverage


def hedge_size_from_notional(
    target_notional: Decimal,
    candidate: MarketCandidate,
    cap_notional: Decimal,
) -> dict[str, Any]:
    if target_notional <= 0 or candidate.last <= 0 or candidate.ct_val <= 0:
        return {"status": "blocked", "note": "invalid hedge notional or instrument metadata"}
    raw_size = target_notional / (candidate.last * candidate.ct_val)
    size = round_size_down(raw_size, candidate.lot_sz)
    if size < candidate.min_sz:
        min_notional = candidate.min_sz * candidate.last * candidate.ct_val
        if cap_notional > 0 and min_notional > cap_notional:
            return {
                "status": "blocked",
                "note": (
                    f"minimum hedge contract notional {plain(min_notional)} exceeds cap "
                    f"{plain(cap_notional)} for {candidate.inst_id}"
                ),
            }
        size = candidate.min_sz
    estimated_notional = size * candidate.last * candidate.ct_val
    return {"status": "ready", "size": size, "estimated_notional": estimated_notional}


def max_tail_metric(targets: list[TargetAllocation], score_rows: list[dict[str, Any]], key: str) -> Decimal:
    values = [dec(getattr(target, key, Decimal("0"))) for target in targets]
    if not values:
        values = [dec(row.get(key)) for row in score_rows if row.get("status") == "ok"]
    return max(values, default=Decimal("0"))


def max_abs_tail_metric(targets: list[TargetAllocation], score_rows: list[dict[str, Any]], key: str) -> Decimal:
    values = [abs(dec(getattr(target, key, Decimal("0")))) for target in targets]
    if not values:
        values = [abs(dec(row.get(key))) for row in score_rows if row.get("status") == "ok"]
    return max(values, default=Decimal("0"))


def sum_tail_risk_events(targets: list[TargetAllocation], score_rows: list[dict[str, Any]]) -> int:
    if targets:
        return sum(max(0, int(dec(getattr(target, "risk_events", 0)))) for target in targets)
    return sum(max(0, int(dec(row.get("risk_events")))) for row in score_rows if row.get("status") == "ok")


def write_tail_hedge_outputs(output_dir: Path, plan: TailHedgePlan) -> None:
    payload = plan_to_dict(plan)
    (output_dir / "hedge_plan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (output_dir / "hedge_plan.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEDGE_ACTION_FIELDS)
        writer.writeheader()
        for action in plan.actions:
            row = action_to_dict(action)
            writer.writerow({field: row.get(field, "") for field in HEDGE_ACTION_FIELDS})
    write_tail_hedge_markdown(output_dir / "hedge_plan.md", plan)


def write_tail_hedge_markdown(path: Path, plan: TailHedgePlan) -> None:
    lines = [
        "# Portfolio Tail Hedge Plan",
        "",
        f"- Generated: `{plan.generated_at}`",
        f"- Mode: `{plan.mode}`",
        f"- Status: `{plan.status}`",
        f"- Equity basis: `{plain(plan.equity)}`",
        f"- Net notional: `{plain(plan.net_notional)}` (`{plain(plan.net_exposure_pct)}`%)",
        f"- Gross notional: `{plain(plan.gross_notional)}`",
        f"- Hedge level / ratio: `{plan.target_hedge_level}` / `{plain(plan.target_hedge_ratio)}`",
        f"- Target hedge notional: `{plain(plan.target_hedge_notional)}`",
        f"- Max shock / trend: `{plain(plan.max_shock_bps)}` bps / `{plain(plan.max_abs_trend_bps)}` bps",
        f"- Total risk events: `{plan.total_risk_events}`",
        f"- Note: {plan.note}",
        "",
    ]
    if plan.trigger_reasons:
        lines.extend(["## Trigger Reasons", ""])
        for reason in plan.trigger_reasons:
            lines.append(f"- {reason}")
        lines.append("")
    lines.extend(["## Actions", ""])
    if not plan.actions:
        lines.extend(["No hedge action is ready.", ""])
    else:
        lines.extend(
            [
                "| Instrument | Action | Side | Pos Side | Size | Reduce Only | Est Px | Target Notional | Estimated Notional | Hedge Ratio | Level | Status | Reason |",
                "| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
            ]
        )
        for action in plan.actions:
            lines.append(
                f"| {action.inst_id} | {action.action} | {action.side} | {action.pos_side} | {plain(action.sz)} | "
                f"{str(action.reduce_only).lower()} | "
                f"{plain(action.estimated_px)} | {plain(action.target_notional)} | {plain(action.estimated_notional)} | "
                f"{plain(action.target_hedge_ratio)} | {action.hedge_level} | {action.status} | {action.reason} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Execution",
            "",
            "Scheduled auto hedge may execute ready actions when live guards are enabled. Manual review can still dry-run or live-run `portfolio_tail_hedge.py` directly.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    global LOG_PATH, STATE_PATH
    args = parse_args()
    LOG_PATH = Path(args.log_path)
    STATE_PATH = Path(args.state_path)
    if args.live:
        require_live_permission(args.confirm_live)
        load_env()
    client = OkxRestClient.from_env() if args.live else None
    run_once(client, args)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually execute a reviewed portfolio tail hedge plan.")
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--log-path", default=str(LOG_PATH))
    parser.add_argument("--ord-type", choices=("market", "limit"), default="")
    parser.add_argument("--slippage-bps", default="20")
    parser.add_argument("--state-path", default=str(STATE_PATH))
    parser.add_argument("--auto", action="store_true", help="Run with live duplicate and exposure checks for scheduled automation.")
    parser.add_argument("--force", action="store_true", help="Ignore same-report tail hedge state.")
    parser.add_argument("--max-plan-age-min", default="120")
    parser.add_argument("--existing-hedge-threshold-pct", default="95")
    parser.add_argument("--min-remaining-notional", default="10")
    parser.add_argument("--release-hedge-margin", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pause-hedge-inst-opens", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--margin-safety-multiplier", default="0.9")
    parser.add_argument("--no-set-leverage", dest="set_leverage", action="store_false")
    parser.set_defaults(set_leverage=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live", default="")
    return parser.parse_args()


def run_once(client: OkxRestClient | None, args: argparse.Namespace) -> list[dict[str, Any]]:
    report_dir = Path(args.report_dir)
    plan = load_plan(report_dir)
    auto_mode = bool(getattr(args, "auto", False))
    if getattr(args, "live", False) and auto_mode:
        validate_plan_age(plan, dec(getattr(args, "max_plan_age_min", "0")))
    state = load_state(STATE_PATH) if getattr(args, "live", False) and auto_mode else {}
    actions = [
        action for action in plan.get("actions", [])
        if str(action.get("status", "")) == "ready"
    ]
    if not actions:
        print(f"No ready tail hedge actions. status={plan.get('status')} note={plan.get('note')}")
        log_event("no_ready_actions", {"reportDir": args.report_dir, "status": plan.get("status"), "note": plan.get("note")})
        return []
    placed = []
    for action in actions:
        original_action = dict(action)
        action_key = hedge_action_key(report_dir, plan, original_action)
        if getattr(args, "live", False) and auto_mode and not getattr(args, "force", False) and state_has_action(state, action_key):
            note = f"tail hedge action already recorded for this report: {action_key}"
            print(f"SKIP tail hedge {action.get('inst_id')} {action.get('side')} {action.get('pos_side')}: {note}")
            log_event("skip_duplicate_action", {"reportDir": args.report_dir, "action": original_action, "actionKey": action_key, "note": note})
            continue
        if getattr(args, "live", False) and auto_mode and client:
            prepared = prepare_live_action(client, plan, original_action, args)
            if prepared["status"] != "ready":
                note = str(prepared.get("note", "live hedge action skipped"))
                print(f"SKIP tail hedge {action.get('inst_id')} {action.get('side')} {action.get('pos_side')}: {note}")
                log_event("skip_live_action", {"reportDir": args.report_dir, "action": original_action, **prepared})
                continue
            action = prepared["action"]
            reduce_only_action = bool_value(action.get("reduce_only"))
            if getattr(args, "set_leverage", False) and not reduce_only_action:
                sync_action_leverage(client, action, strict=not auto_mode)
            if getattr(args, "release_hedge_margin", False):
                if getattr(args, "pause_hedge_inst_opens", False) and not reduce_only_action:
                    pause_runtime_new_opens(str(action.get("inst_id", "")))
                cancel_non_reduce_pending_orders(client, str(action.get("inst_id", "")))
            if not reduce_only_action:
                action = fit_action_to_available_margin(client, action, args)
                if action is None:
                    note = "available margin is below minimum tradable hedge size"
                    print(f"SKIP tail hedge {original_action.get('inst_id')} {original_action.get('side')} {original_action.get('pos_side')}: {note}")
                    log_event("skip_live_action", {"reportDir": args.report_dir, "action": original_action, "status": "skipped", "note": note})
                    continue
        payload = hedge_order_payload(action, args)
        try:
            response = client.place_order(**payload) if args.live and client else {"dryRun": True, "data": [payload]}
        except OkxApiError as exc:
            log_event(
                "place_order_error",
                {
                    "live": args.live,
                    "reportDir": args.report_dir,
                    "action": action,
                    "payload": payload,
                    "error": str(exc),
                    "okxCode": exc.okx_code,
                    "response": exc.response,
                },
            )
            raise
        print(
            f"{'LIVE' if args.live else 'DRY'} tail hedge {payload['inst_id']} "
            f"{payload['side']} {payload.get('pos_side')} {payload['sz']} "
            f"ord_type={payload['ord_type']}"
        )
        event = {"live": args.live, "reportDir": args.report_dir, "action": action, "payload": payload, "response": response}
        log_event("tail_hedge_order", event)
        if getattr(args, "live", False) and auto_mode:
            state = record_state_action(state, action_key, event)
        placed.append(event)
    return placed


def prepare_live_action(
    client: OkxRestClient,
    plan: dict[str, Any],
    action: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    positions = client.get_positions("SWAP").get("data", [])
    current_net = net_notional_from_positions(positions)
    planned_net = dec(plan.get("net_notional"))
    meta = live_market_meta(client, str(action.get("inst_id", "")))
    if bool_value(action.get("reduce_only")):
        return prepare_live_reduce_action(client, action, positions, meta, args)

    if planned_net > 0 and current_net <= 0:
        return {
            "status": "skipped",
            "note": f"current net exposure is no longer long: {plain(current_net)}",
            "currentNetNotional": current_net,
        }
    if planned_net < 0 and current_net >= 0:
        return {
            "status": "skipped",
            "note": f"current net exposure is no longer short: {plain(current_net)}",
            "currentNetNotional": current_net,
        }

    target_notional = live_target_notional(plan, action, current_net)
    min_remaining = max(
        dec(plan.get("config", {}).get("min_hedge_notional")),
        dec(getattr(args, "min_remaining_notional", "0")),
    )
    if target_notional < min_remaining:
        return {
            "status": "skipped",
            "note": f"live target notional {plain(target_notional)} is below minimum {plain(min_remaining)}",
            "currentNetNotional": current_net,
            "targetNotional": target_notional,
        }

    existing = existing_same_direction_notional(client, action, positions, meta)
    threshold_pct = dec(getattr(args, "existing_hedge_threshold_pct", "95"), Decimal("95"))
    threshold_notional = target_notional * threshold_pct / Decimal("100")
    if existing["total_notional"] >= threshold_notional:
        return {
            "status": "skipped",
            "note": (
                f"existing same-direction hedge {plain(existing['total_notional'])} "
                f">= {plain(threshold_pct)}% of target {plain(target_notional)}"
            ),
            "currentNetNotional": current_net,
            "targetNotional": target_notional,
            "existing": existing,
        }

    remaining_notional = target_notional - existing["total_notional"]
    if remaining_notional < min_remaining:
        return {
            "status": "skipped",
            "note": f"remaining hedge notional {plain(remaining_notional)} is below minimum {plain(min_remaining)}",
            "currentNetNotional": current_net,
            "targetNotional": target_notional,
            "existing": existing,
        }

    adjusted = resize_action_to_notional(action, remaining_notional, meta)
    if adjusted is None:
        return {
            "status": "skipped",
            "note": f"remaining hedge notional {plain(remaining_notional)} is below tradable size",
            "currentNetNotional": current_net,
            "targetNotional": target_notional,
            "existing": existing,
        }
    return {
        "status": "ready",
        "action": adjusted,
        "currentNetNotional": current_net,
        "targetNotional": target_notional,
        "remainingNotional": remaining_notional,
        "existing": existing,
    }


def prepare_live_reduce_action(
    client: OkxRestClient,
    action: dict[str, Any],
    positions: list[dict[str, Any]],
    meta: dict[str, Decimal],
    args: argparse.Namespace,
) -> dict[str, Any]:
    inst_id = str(action.get("inst_id", ""))
    pos_side = str(action.get("pos_side", ""))
    available_size = Decimal("0")
    available_notional = Decimal("0")
    for position in positions:
        if str(position.get("instId", "")) != inst_id or not position_matches_pos_side(position, pos_side):
            continue
        size = abs(dec(position.get("pos")))
        available_size += size
        available_notional += position_notional_abs(position)
    if available_size <= 0 or available_notional <= 0:
        return {
            "status": "skipped",
            "note": f"no {inst_id} {pos_side} position is available for reduce-only hedge fallback",
            "availableSize": available_size,
            "availableNotional": available_notional,
        }

    target_notional = min(dec(action.get("target_notional"), dec(action.get("estimated_notional"))), available_notional)
    min_remaining = max(
        dec(action.get("config", {}).get("min_hedge_notional")),
        dec(getattr(args, "min_remaining_notional", "0")),
    )
    if target_notional < min_remaining:
        return {
            "status": "skipped",
            "note": f"reduce-only target notional {plain(target_notional)} is below minimum {plain(min_remaining)}",
            "targetNotional": target_notional,
        }

    adjusted = resize_reduce_action_to_notional(action, target_notional, available_size, available_notional, meta)
    if adjusted is None:
        return {
            "status": "skipped",
            "note": f"reduce-only target notional {plain(target_notional)} is below tradable size",
            "targetNotional": target_notional,
        }
    return {
        "status": "ready",
        "action": adjusted,
        "targetNotional": target_notional,
        "availableSize": available_size,
        "availableNotional": available_notional,
    }


def live_target_notional(plan: dict[str, Any], action: dict[str, Any], current_net: Decimal) -> Decimal:
    config = plan.get("config", {}) if isinstance(plan.get("config"), dict) else {}
    hedge_ratio = clamp(
        dec(action.get("target_hedge_ratio"), dec(plan.get("target_hedge_ratio"), dec(config.get("hedge_ratio"), Decimal("1")))),
        Decimal("0"),
        Decimal("1"),
    )
    planned_target = dec(action.get("target_notional"), dec(action.get("estimated_notional")))
    current_target = abs(current_net) * hedge_ratio
    cap_notional = hedge_cap_notional(
        dec(plan.get("equity")),
        TailHedgeConfig(
            max_hedge_margin_pct=dec(action.get("max_margin_pct"), dec(config.get("max_hedge_margin_pct"))),
            hedge_leverage=dec(config.get("hedge_leverage")),
        ),
    )
    if cap_notional > 0:
        current_target = min(current_target, cap_notional)
    return min(planned_target, current_target) if planned_target > 0 else current_target


def live_market_meta(client: OkxRestClient, inst_id: str) -> dict[str, Decimal]:
    instrument = first_data(
        client.request(
            "GET",
            "/api/v5/public/instruments",
            params={"instType": "SWAP", "instId": inst_id},
        )
    )
    ticker = first_data(client.get_ticker(inst_id))
    last = dec(ticker.get("last"), dec(instrument.get("last")))
    return {
        "last": last,
        "ct_val": dec(instrument.get("ctVal"), Decimal("1")),
        "lot_sz": dec(instrument.get("lotSz"), Decimal("1")),
        "min_sz": dec(instrument.get("minSz"), Decimal("1")),
    }


def existing_same_direction_notional(
    client: OkxRestClient,
    action: dict[str, Any],
    positions: list[dict[str, Any]],
    meta: dict[str, Decimal],
) -> dict[str, Decimal]:
    inst_id = str(action.get("inst_id", ""))
    pos_side = str(action.get("pos_side", ""))
    side = str(action.get("side", ""))
    position_notional = Decimal("0")
    for position in positions:
        if str(position.get("instId", "")) != inst_id or not position_matches_pos_side(position, pos_side):
            continue
        position_notional += position_notional_abs(position)

    pending_notional = Decimal("0")
    for order in client.get_pending_orders(inst_id).get("data", []):
        if is_reduce_only(order):
            continue
        if str(order.get("side", "")) != side or str(order.get("posSide", "")) != pos_side:
            continue
        px = dec(order.get("px"), meta["last"])
        sz = dec(order.get("sz"))
        if px > 0 and sz > 0 and meta["ct_val"] > 0:
            pending_notional += px * sz * meta["ct_val"]
    return {
        "position_notional": position_notional,
        "pending_notional": pending_notional,
        "total_notional": position_notional + pending_notional,
    }


def resize_action_to_notional(action: dict[str, Any], notional: Decimal, meta: dict[str, Decimal]) -> dict[str, Any] | None:
    last = meta["last"]
    ct_val = meta["ct_val"]
    lot_sz = meta["lot_sz"]
    min_sz = meta["min_sz"]
    if notional <= 0 or last <= 0 or ct_val <= 0:
        return None
    size = round_size_down(notional / (last * ct_val), lot_sz)
    original_size = dec(action.get("sz"))
    if original_size > 0 and size > original_size:
        size = original_size
    if size < min_sz:
        return None
    estimated_notional = size * last * ct_val
    if estimated_notional <= 0:
        return None
    adjusted = dict(action)
    adjusted["sz"] = plain(size)
    adjusted["estimated_px"] = plain(last)
    adjusted["estimated_notional"] = plain(estimated_notional)
    return adjusted


def resize_reduce_action_to_notional(
    action: dict[str, Any],
    notional: Decimal,
    available_size: Decimal,
    available_notional: Decimal,
    meta: dict[str, Decimal],
) -> dict[str, Any] | None:
    if notional <= 0 or available_size <= 0 or available_notional <= 0:
        return None
    size = available_size * clamp(notional / available_notional, Decimal("0"), Decimal("1"))
    lot_sz = meta["lot_sz"]
    min_sz = meta["min_sz"]
    size = round_size_down(size, lot_sz)
    original_size = dec(action.get("sz"))
    if original_size > 0 and size > original_size:
        size = original_size
    if size < min_sz:
        return None
    adjusted = dict(action)
    adjusted["sz"] = plain(size)
    adjusted["estimated_px"] = plain(meta["last"])
    adjusted["estimated_notional"] = plain(notional)
    adjusted["target_notional"] = plain(notional)
    adjusted["reduce_only"] = True
    return adjusted


def sync_action_leverage(client: OkxRestClient, action: dict[str, Any], *, strict: bool = True) -> None:
    leverage = dec(action.get("leverage"))
    if leverage <= 0:
        return
    payload = {
        "inst_id": str(action.get("inst_id")),
        "lever": plain(leverage),
        "mgn_mode": "cross",
        "pos_side": str(action.get("pos_side")),
    }
    try:
        response = client.set_leverage(**payload)
    except OkxApiError as exc:
        log_event("set_leverage_error", {"live": True, "payload": payload, "error": str(exc), "okxCode": exc.okx_code})
        if strict:
            raise
        print(f"WARN set hedge leverage failed; continuing with exchange leverage: {exc}")
        return
    print(f"LIVE set hedge leverage {payload['inst_id']} {payload['pos_side']} {payload['lever']}x -> {response.get('data')}")
    log_event("set_leverage", {"live": True, "payload": payload, "response": response})


def fit_action_to_available_margin(
    client: OkxRestClient,
    action: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    meta = live_market_meta(client, str(action.get("inst_id", "")))
    leverage = dec(action.get("leverage"))
    if leverage <= 0:
        leverage = Decimal("1")
    available = account_available_usdt(client)
    safety = max(Decimal("0"), min(dec(getattr(args, "margin_safety_multiplier", "0.9"), Decimal("0.9")), Decimal("1")))
    max_notional = available * leverage * safety
    requested = dec(action.get("estimated_notional"), dec(action.get("target_notional")))
    if max_notional <= 0 or requested <= 0 or requested <= max_notional:
        return action
    adjusted = resize_action_to_notional(action, max_notional, meta)
    if adjusted is None:
        return None
    log_event(
        "shrink_for_available_margin",
        {
            "live": True,
            "instId": action.get("inst_id"),
            "available": available,
            "leverage": leverage,
            "safety": safety,
            "requestedNotional": requested,
            "maxNotional": max_notional,
            "adjusted": adjusted,
        },
    )
    print(
        f"LIVE shrink tail hedge for margin {action.get('inst_id')} "
        f"requested_notional={plain(requested)} max_notional={plain(max_notional)} sz={adjusted.get('sz')}"
    )
    return adjusted


def account_available_usdt(client: OkxRestClient) -> Decimal:
    payload = client.get_balance()
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        for detail in item.get("details", []):
            if isinstance(detail, dict) and detail.get("ccy") == "USDT":
                return dec(detail.get("availBal"), dec(detail.get("availEq")))
        value = dec(item.get("availEq"))
        if value > 0:
            return value
    return Decimal("0")


def pause_runtime_new_opens(inst_id: str) -> None:
    runtime_path = active_runtime_path(inst_id)
    if runtime_path is None:
        return
    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log_event("pause_runtime_error", {"instId": inst_id, "path": str(runtime_path), "error": str(exc)})
        return
    if payload.get("pauseNewOpens") is True:
        return
    backup = runtime_path.with_suffix(runtime_path.suffix + f".pre_pause_new_opens_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak")
    backup.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["pauseNewOpens"] = True
    payload["pauseNewOpensReason"] = "tail hedge margin release"
    payload["updatedAt"] = now_iso()
    runtime_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"LIVE pause new opens for {inst_id} runtime={runtime_path}")
    log_event("pause_runtime_new_opens", {"live": True, "instId": inst_id, "path": str(runtime_path), "backup": str(backup)})


def active_runtime_path(inst_id: str) -> Path | None:
    needle = f"--inst-id {inst_id}"
    try:
        import subprocess

        result = subprocess.run(
            ["ps", "-eo", "cmd"],
            check=False,
            text=True,
            capture_output=True,
        )
    except Exception:
        return None
    for line in result.stdout.splitlines():
        if "auto_grid_bot.py" not in line or needle not in line or "--runtime-config" not in line:
            continue
        parts = line.split()
        try:
            index = parts.index("--runtime-config")
            return Path(parts[index + 1])
        except (ValueError, IndexError):
            continue
    return None


def cancel_non_reduce_pending_orders(client: OkxRestClient, inst_id: str) -> None:
    if not inst_id:
        return
    pending = client.get_pending_orders(inst_id).get("data", [])
    cancelable = [
        {"instId": inst_id, "ordId": str(order.get("ordId", "")), "clOrdId": str(order.get("clOrdId", ""))}
        for order in pending
        if not is_reduce_only(order)
    ]
    if not cancelable:
        return
    response = client.cancel_orders(cancelable)
    print(f"LIVE cancel hedge-margin orders {inst_id} count={len(cancelable)} -> {response.get('data')}")
    log_event("cancel_hedge_margin_orders", {"live": True, "instId": inst_id, "orders": cancelable, "response": response})


def net_notional_from_positions(positions: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for position in positions:
        raw_pos = dec(position.get("pos"))
        if raw_pos == 0:
            continue
        notional = position_notional_abs(position)
        if position_is_short(position):
            total -= notional
        else:
            total += notional
    return total


def position_notional_abs(position: dict[str, Any]) -> Decimal:
    notional = abs(dec(position.get("notionalUsd")))
    if notional > 0:
        return notional
    pos = abs(dec(position.get("pos")))
    px = dec(position.get("markPx"), dec(position.get("last"), dec(position.get("avgPx"))))
    ct_val = dec(position.get("ctVal"), Decimal("1"))
    return pos * px * ct_val if pos > 0 and px > 0 and ct_val > 0 else Decimal("0")


def position_is_short(position: dict[str, Any]) -> bool:
    pos_side = str(position.get("posSide", "net"))
    return pos_side == "short" or (pos_side == "net" and dec(position.get("pos")) < 0)


def position_matches_pos_side(position: dict[str, Any], pos_side: str) -> bool:
    if pos_side == "short":
        return position_is_short(position)
    if pos_side == "long":
        return not position_is_short(position)
    return False


def is_reduce_only(order: dict[str, Any]) -> bool:
    return str(order.get("reduceOnly", "")).lower() in {"true", "1"}


def hedge_order_payload(action: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ord_type = args.ord_type or str(action.get("ord_type") or "market")
    payload: dict[str, Any] = {
        "inst_id": str(action.get("inst_id")),
        "td_mode": "cross",
        "side": str(action.get("side")),
        "ord_type": ord_type,
        "sz": str(action.get("sz")),
        "pos_side": str(action.get("pos_side")),
        "reduce_only": bool_value(action.get("reduce_only")),
        "cl_ord_id": hedge_client_order_id(action),
    }
    if ord_type == "limit":
        px = limit_px_from_action(action, dec(args.slippage_bps))
        if px > 0:
            payload["px"] = plain(px)
    return payload


def limit_px_from_action(action: dict[str, Any], slippage_bps: Decimal) -> Decimal:
    raw_px = dec(action.get("estimated_px"))
    if raw_px <= 0:
        notional = dec(action.get("estimated_notional"))
        size = dec(action.get("sz"))
        if notional <= 0 or size <= 0:
            return Decimal("0")
        raw_px = notional / size
    if raw_px <= 0:
        return Decimal("0")
    bump = slippage_bps / Decimal("10000")
    return raw_px * (Decimal("1") + bump) if action.get("side") == "buy" else raw_px * (Decimal("1") - bump)


def hedge_client_order_id(action: dict[str, Any]) -> str:
    side = "b" if action.get("side") == "buy" else "s"
    pos = "l" if action.get("pos_side") == "long" else "s"
    action_kind = "r" if bool_value(action.get("reduce_only")) else "i"
    stamp = str(int(time.time() * 1000))[-8:]
    return f"pth{action_kind}{side}{pos}{stamp}"[:32]


def require_live_permission(confirm_live: str) -> None:
    load_env()
    if os.getenv("OKX_ENABLE_LIVE_TRADING", "0") != "1":
        raise PermissionError("Live trading is locked. Set OKX_ENABLE_LIVE_TRADING=1 before executing a tail hedge.")
    if confirm_live != "I_UNDERSTAND":
        raise PermissionError("Tail hedge live execution requires --confirm-live I_UNDERSTAND.")


def load_plan(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "hedge_plan.json"
    if not path.exists():
        raise FileNotFoundError(f"tail hedge plan missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def validate_plan_age(plan: dict[str, Any], max_age_min: Decimal) -> None:
    if max_age_min <= 0:
        return
    generated_at = str(plan.get("generated_at") or plan.get("generatedAt") or "")
    if not generated_at:
        raise RuntimeError("Tail hedge plan has no generated_at timestamp.")
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"Tail hedge plan timestamp is invalid: {generated_at}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    if age_seconds > float(max_age_min * Decimal("60")):
        raise RuntimeError(f"Tail hedge plan is stale: age={age_seconds:.0f}s max={plain(max_age_min)}m")


def first_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data", []) if isinstance(payload, dict) else []
    return data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}


def hedge_action_key(report_dir: Path, plan: dict[str, Any], action: dict[str, Any]) -> str:
    return "|".join(
        [
            str(report_dir.resolve()),
            str(plan.get("generated_at") or plan.get("generatedAt") or ""),
            str(action.get("inst_id") or ""),
            str(action.get("side") or ""),
            str(action.get("pos_side") or ""),
            str(action.get("target_notional") or ""),
        ]
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def state_has_action(state: dict[str, Any], action_key: str) -> bool:
    actions = state.get("actions", {})
    return isinstance(actions, dict) and action_key in actions


def record_state_action(state: dict[str, Any], action_key: str, event: dict[str, Any]) -> dict[str, Any]:
    actions = state.get("actions", {})
    if not isinstance(actions, dict):
        actions = {}
    actions[action_key] = {"updatedAt": now_iso(), "event": jsonable(event)}
    state = {"updatedAt": now_iso(), "actions": actions}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def plan_to_dict(plan: TailHedgePlan) -> dict[str, Any]:
    return jsonable(asdict(plan))


def action_to_dict(action: TailHedgeAction) -> dict[str, Any]:
    return jsonable(asdict(action))


def log_event(kind: str, payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now_iso(), "kind": kind, "payload": jsonable(payload)}
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def round_size_down(value: Decimal, lot_sz: Decimal) -> Decimal:
    if lot_sz <= 0:
        return value
    return (value / lot_sz).to_integral_value(rounding=ROUND_DOWN) * lot_sz


def clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    if upper < lower:
        lower, upper = upper, lower
    return max(lower, min(value, upper))


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


if __name__ == "__main__":
    raise SystemExit(main())
