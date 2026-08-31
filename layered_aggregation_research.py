from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import BAR_MS, Candle, iso_time
from funding_research import (
    FundingPoint,
    fetch_funding_history,
    funding_cache_path,
    read_funding_csv,
    write_funding_csv,
)
from layered_aggregation import (
    LayeredConfig,
    LayeredSimulation,
    break_even_take_profit_bps,
    round_quantity_down,
    simulate_layered_strategy,
)
from okx_client import OkxRestClient
from strategy_search import load_candles_for_instruments


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "layered_aggregation"
DEFAULT_INSTRUMENTS = [
    "SOXL-USDT-SWAP",
    "SMH-USDT-SWAP",
    "NVDA-USDT-SWAP",
    "AMD-USDT-SWAP",
    "MU-USDT-SWAP",
    "SNDK-USDT-SWAP",
    "TSM-USDT-SWAP",
    "SKHYNIX-USDT-SWAP",
    "SKHY-USDT-SWAP",
]


@dataclass(frozen=True, slots=True)
class InstrumentSnapshot:
    inst_id: str
    state: str
    list_time: int
    contract_value: float
    lot_size: float
    min_size: float
    tick_size: float
    last: float
    bid: float
    ask: float
    spread_bps: float
    turnover_24h_usdt: float
    selected: bool
    selection_note: str


@dataclass(frozen=True, slots=True)
class CandidateParams:
    step_bps: float
    take_profit_bps: float
    tranches: int
    basket_stop_bps: float


@dataclass(slots=True)
class CandidateScore:
    params: CandidateParams
    score: float
    median_return_pct: float
    median_drawdown_pct: float
    median_round_trips: float
    positive_instruments: int
    instrument_count: int
    worst_return_pct: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only research for a layered long aggregation / partial-reduction strategy."
    )
    parser.add_argument("--inst-id", action="append", default=[])
    parser.add_argument("--bar", default="5m", choices=list(BAR_MS))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--funding-limit", type=int, default=100)
    parser.add_argument("--funding-pages", type=int, default=1)
    parser.add_argument("--refresh-funding", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--min-turnover-usdt", type=float, default=1_000_000.0)
    parser.add_argument("--max-spread-bps", type=float, default=5.0)
    parser.add_argument("--starting-equity", type=float, default=100.0)
    parser.add_argument("--allocation-pct", type=float, default=60.0)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--maker-fee-bps", type=float, default=2.0)
    parser.add_argument("--taker-fee-bps", type=float, default=5.0)
    parser.add_argument("--stop-slippage-bps", type=float, default=2.0)
    parser.add_argument("--fill-buffer-bps", type=float, default=1.0)
    parser.add_argument("--cooldown-bars", type=int, default=12)
    parser.add_argument("--min-common-bars", type=int, default=2400)
    parser.add_argument("--downtrend-days", type=float, default=3.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    client = OkxRestClient()
    requested = list(dict.fromkeys(args.inst_id or DEFAULT_INSTRUMENTS))
    snapshots = instrument_snapshots(client, requested, args)
    selected = [item.inst_id for item in snapshots if item.selected]
    if len(selected) < 3:
        raise SystemExit(f"Need at least 3 liquid semiconductor contracts, found {len(selected)}")

    candles_by_inst = load_candles_for_instruments(args, selected)
    candles_by_inst, common_start, common_end = common_candle_interval(candles_by_inst)
    too_short = {inst: len(rows) for inst, rows in candles_by_inst.items() if len(rows) < args.min_common_bars}
    if too_short:
        raise SystemExit(f"Insufficient common history: {too_short}")
    funding_by_inst = load_public_funding(client, selected, args)

    base = LayeredConfig(
        starting_equity=args.starting_equity,
        allocation_pct=args.allocation_pct,
        leverage=args.leverage,
        cooldown_bars=args.cooldown_bars,
        maker_fee_bps=args.maker_fee_bps,
        taker_fee_bps=args.taker_fee_bps,
        stop_slippage_bps=args.stop_slippage_bps,
        fill_buffer_bps=args.fill_buffer_bps,
    )
    metadata = {item.inst_id: item for item in snapshots if item.selected}
    train_end, validation_end = chronological_boundaries(common_start, common_end)
    train_candles = {inst: time_slice(rows, common_start, train_end) for inst, rows in candles_by_inst.items()}
    candidate_scores = select_global_parameters(train_candles, funding_by_inst, metadata, base)
    if not candidate_scores:
        raise SystemExit("No parameter candidate produced enough training activity")
    selected_params = candidate_scores[0].params
    best_risk_capped_score = next((item for item in candidate_scores if item.params.basket_stop_bps > 0), None)
    best_risk_capped_params = best_risk_capped_score.params if best_risk_capped_score else None
    minimum_starting_equity = minimum_starting_equity_for_params(
        selected_params,
        metadata,
        candles_by_inst,
        args.allocation_pct,
        args.leverage,
    )

    segment_rows: list[dict[str, Any]] = []
    all_fills: list[dict[str, Any]] = []
    all_curve: list[dict[str, Any]] = []
    for inst_id, candles in candles_by_inst.items():
        segments = {
            "train": time_slice(candles, common_start, train_end),
            "validation": time_slice(candles, train_end + 1, validation_end),
            "test": time_slice(candles, validation_end + 1, common_end),
            "full": candles,
            "worst_downtrend": worst_return_window(candles, args.bar, args.downtrend_days),
        }
        config = config_for_instrument(base, selected_params, metadata[inst_id])
        for segment_name, segment_candles in segments.items():
            simulation = simulate_layered_strategy(
                segment_candles,
                config,
                funding_by_inst.get(inst_id, []),
                record_details=segment_name == "test",
            )
            segment_rows.append(simulation_row(inst_id, segment_name, "selected", simulation))
            if segment_name == "test":
                all_fills.extend(fill_rows(inst_id, segment_name, simulation))
                all_curve.extend(curve_rows(inst_id, segment_name, simulation))

            if best_risk_capped_params is not None and segment_name in {"validation", "test", "full", "worst_downtrend"}:
                if best_risk_capped_params != selected_params:
                    capped_config = config_for_instrument(base, best_risk_capped_params, metadata[inst_id])
                    capped_sim = simulate_layered_strategy(
                        segment_candles,
                        capped_config,
                        funding_by_inst.get(inst_id, []),
                        record_details=False,
                    )
                    segment_rows.append(simulation_row(inst_id, segment_name, "risk_capped", capped_sim))

            if config.basket_stop_bps > 0 and segment_name in {"validation", "test", "full", "worst_downtrend"}:
                no_stop_config = replace(config, basket_stop_bps=0.0)
                no_stop_sim = simulate_layered_strategy(
                    segment_candles,
                    no_stop_config,
                    funding_by_inst.get(inst_id, []),
                    record_details=False,
                )
                segment_rows.append(simulation_row(inst_id, segment_name, "no_stop", no_stop_sim))

        test_candles = segments["test"]
        stress = replace(
            config,
            maker_fee_bps=max(5.0, config.maker_fee_bps * 2.5),
            taker_fee_bps=max(8.0, config.taker_fee_bps * 1.6),
            stop_slippage_bps=max(4.0, config.stop_slippage_bps * 2.0),
            fill_buffer_bps=max(4.0, config.fill_buffer_bps * 4.0),
        )
        stress_sim = simulate_layered_strategy(test_candles, stress, funding_by_inst.get(inst_id, []), record_details=False)
        segment_rows.append(simulation_row(inst_id, "test", "cost_stress", stress_sim))

        no_funding = simulate_layered_strategy(test_candles, config, (), record_details=False)
        segment_rows.append(simulation_row(inst_id, "test", "no_funding", no_funding))

        naive = replace(config, step_bps=100.0, take_profit_bps=30.0, tranches=6, basket_stop_bps=0.0)
        naive_sim = simulate_layered_strategy(test_candles, naive, funding_by_inst.get(inst_id, []), record_details=False)
        segment_rows.append(simulation_row(inst_id, "test", "naive_100_30_6", naive_sim))

    synthetic = run_synthetic_scenarios(base, selected_params)
    feasibility = feasibility_decision(segment_rows)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_layered_aggregation_research",
        "strategyDefinition": {
            "direction": "long_only",
            "sizing": "equal_quote_notional_per_layer",
            "entry": "static percentage ladder below a completed-close anchor",
            "exit": "min(fixed take-profit, previous higher layer price)",
            "reanchor": "only after inventory is flat or risk cooldown ends",
            "intrabar": "adverse stop-first; new entries cannot take profit on the same candle",
            "marking": "terminal inventory is marked to market and charged estimated taker/slippage liquidation cost",
        },
        "config": vars(args),
        "commonPeriod": {
            "start": iso_time(common_start),
            "trainEnd": iso_time(train_end),
            "validationEnd": iso_time(validation_end),
            "end": iso_time(common_end),
        },
        "instruments": [asdict(item) for item in snapshots],
        "selectedParameters": asdict(selected_params),
        "bestRiskCappedParameters": asdict(best_risk_capped_params) if best_risk_capped_params else None,
        "minimumStartingEquityForSelected": minimum_starting_equity,
        "roundTripBreakEvenTpBps": break_even_take_profit_bps(args.maker_fee_bps),
        "candidateScores": [candidate_score_payload(item) for item in candidate_scores[:25]],
        "segmentResults": segment_rows,
        "syntheticScenarios": synthetic,
        "feasibility": feasibility,
    }
    write_outputs(output_dir, payload, segment_rows, all_fills, all_curve)
    print_summary(output_dir, payload)
    return 0


def instrument_snapshots(client: OkxRestClient, requested: list[str], args: argparse.Namespace) -> list[InstrumentSnapshot]:
    instruments = client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"}).get("data", [])
    tickers = client.request("GET", "/api/v5/market/tickers", params={"instType": "SWAP"}).get("data", [])
    instrument_map = {str(item.get("instId")): item for item in instruments}
    ticker_map = {str(item.get("instId")): item for item in tickers}
    result: list[InstrumentSnapshot] = []
    for inst_id in requested:
        meta = instrument_map.get(inst_id, {})
        ticker = ticker_map.get(inst_id, {})
        state = str(meta.get("state") or "missing")
        last = number(ticker.get("last"))
        bid = number(ticker.get("bidPx"))
        ask = number(ticker.get("askPx"))
        midpoint = (bid + ask) / 2.0 if bid > 0 and ask > 0 else 0.0
        spread_bps = (ask - bid) / midpoint * 10_000.0 if midpoint > 0 else math.inf
        contract_value = number(meta.get("ctVal"), 1.0)
        base_volume = number(ticker.get("volCcy24h") or ticker.get("vol24h"))
        turnover = base_volume * last * contract_value
        reasons = []
        if state != "live":
            reasons.append(f"state={state}")
        if spread_bps > args.max_spread_bps:
            reasons.append(f"spread>{args.max_spread_bps:g}bps")
        if turnover < args.min_turnover_usdt:
            reasons.append(f"turnover<{args.min_turnover_usdt:g}")
        selected = not reasons
        result.append(
            InstrumentSnapshot(
                inst_id=inst_id,
                state=state,
                list_time=integer(meta.get("listTime")),
                contract_value=contract_value,
                lot_size=number(meta.get("lotSz"), 0.001),
                min_size=number(meta.get("minSz"), 0.001),
                tick_size=number(meta.get("tickSz"), 0.01),
                last=last,
                bid=bid,
                ask=ask,
                spread_bps=spread_bps,
                turnover_24h_usdt=turnover,
                selected=selected,
                selection_note="selected" if selected else "; ".join(reasons),
            )
        )
    return result


def load_public_funding(client: OkxRestClient, inst_ids: list[str], args: argparse.Namespace) -> dict[str, list[FundingPoint]]:
    result: dict[str, list[FundingPoint]] = {}
    for inst_id in inst_ids:
        path = funding_cache_path(inst_id, args.funding_limit, args.funding_pages)
        if path.exists() and not args.refresh_funding:
            points = read_funding_csv(path)
        else:
            points = fetch_funding_history(
                client,
                inst_id,
                limit=args.funding_limit,
                pages=args.funding_pages,
                sleep=args.sleep,
            )
            write_funding_csv(path, points)
        result[inst_id] = points
    return result


def common_candle_interval(candles_by_inst: dict[str, list[Candle]]) -> tuple[dict[str, list[Candle]], int, int]:
    usable = {inst: sorted(rows, key=lambda item: item.ts) for inst, rows in candles_by_inst.items() if rows}
    if not usable:
        raise ValueError("no candle history")
    common_start = max(rows[0].ts for rows in usable.values())
    common_end = min(rows[-1].ts for rows in usable.values())
    if common_end <= common_start:
        raise ValueError("instruments have no overlapping candle interval")
    trimmed = {inst: time_slice(rows, common_start, common_end) for inst, rows in usable.items()}
    return trimmed, common_start, common_end


def chronological_boundaries(start_ts: int, end_ts: int) -> tuple[int, int]:
    span = end_ts - start_ts
    return start_ts + int(span * 0.50), start_ts + int(span * 0.75)


def time_slice(candles: list[Candle], start_ts: int, end_ts: int) -> list[Candle]:
    rows = [item for item in candles if start_ts <= item.ts <= end_ts]
    if len(rows) < 2:
        raise ValueError(f"candle segment too short: {len(rows)}")
    return rows


def candidate_grid() -> list[CandidateParams]:
    return [
        CandidateParams(step, take_profit, tranches, stop)
        for step in (50.0, 75.0, 100.0, 150.0, 200.0)
        for take_profit in (15.0, 25.0, 40.0, 60.0)
        for tranches in (4, 6, 8)
        for stop in (0.0, 600.0, 900.0)
    ]


def select_global_parameters(
    candles_by_inst: dict[str, list[Candle]],
    funding_by_inst: dict[str, list[FundingPoint]],
    metadata: dict[str, InstrumentSnapshot],
    base: LayeredConfig,
) -> list[CandidateScore]:
    scores: list[CandidateScore] = []
    for params in candidate_grid():
        tradeable = True
        for inst_id, candles in candles_by_inst.items():
            config = config_for_instrument(base, params, metadata[inst_id])
            first_price = float(candles[0].close)
            layer_notional = base.starting_equity * base.allocation_pct / 100.0 * base.leverage / params.tranches
            raw_quantity = layer_notional / (first_price * config.contract_value)
            if round_quantity_down(raw_quantity, config.lot_size, config.min_size) <= 0:
                tradeable = False
                break
        if not tradeable:
            continue
        returns: list[float] = []
        drawdowns: list[float] = []
        round_trips: list[int] = []
        for inst_id, candles in candles_by_inst.items():
            config = config_for_instrument(base, params, metadata[inst_id])
            result = simulate_layered_strategy(
                candles,
                config,
                funding_by_inst.get(inst_id, []),
                record_details=False,
            ).result
            returns.append(result.return_pct)
            drawdowns.append(result.max_drawdown_pct)
            round_trips.append(result.round_trips)
        median_trips = statistics.median(round_trips)
        active_instruments = sum(1 for value in round_trips if value >= 3)
        if median_trips < 3 or active_instruments < max(2, math.ceil(len(round_trips) * 0.5)):
            continue
        median_return = statistics.median(returns)
        median_drawdown = statistics.median(drawdowns)
        positive = sum(1 for value in returns if value > 0)
        score = (
            median_return
            - 0.60 * median_drawdown
            + 0.0125 * min(median_trips, 80)
            + 0.15 * (positive - len(returns) / 2.0)
            + 0.20 * min(returns)
        )
        scores.append(
            CandidateScore(
                params=params,
                score=score,
                median_return_pct=median_return,
                median_drawdown_pct=median_drawdown,
                median_round_trips=median_trips,
                positive_instruments=positive,
                instrument_count=len(returns),
                worst_return_pct=min(returns),
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def minimum_starting_equity_for_params(
    params: CandidateParams,
    metadata: dict[str, InstrumentSnapshot],
    candles_by_inst: dict[str, list[Candle]],
    allocation_pct: float,
    leverage: float,
) -> float:
    if allocation_pct <= 0 or leverage <= 0:
        return math.inf
    required = 0.0
    for inst_id, candles in candles_by_inst.items():
        meta = metadata[inst_id]
        minimum_layer_notional = meta.min_size * float(candles[0].close) * meta.contract_value
        equity = minimum_layer_notional * params.tranches / (allocation_pct / 100.0 * leverage)
        required = max(required, equity)
    return required


def config_for_instrument(base: LayeredConfig, params: CandidateParams, meta: InstrumentSnapshot) -> LayeredConfig:
    return replace(
        base,
        step_bps=params.step_bps,
        take_profit_bps=params.take_profit_bps,
        tranches=params.tranches,
        basket_stop_bps=params.basket_stop_bps,
        lot_size=meta.lot_size,
        min_size=meta.min_size,
        contract_value=meta.contract_value,
        tick_size=meta.tick_size,
    )


def worst_return_window(candles: list[Candle], bar: str, days: float) -> list[Candle]:
    desired = max(48, int(days * 86_400_000 / BAR_MS[bar]))
    if len(candles) <= desired:
        return candles
    worst_start = 0
    worst_return = math.inf
    for start in range(0, len(candles) - desired + 1):
        first = float(candles[start].close)
        last = float(candles[start + desired - 1].close)
        value = last / first - 1.0 if first > 0 else 0.0
        if value < worst_return:
            worst_return = value
            worst_start = start
    return candles[worst_start : worst_start + desired]


def simulation_row(inst_id: str, segment: str, variant: str, simulation: LayeredSimulation) -> dict[str, Any]:
    result = simulation.result
    return {
        "inst_id": inst_id,
        "segment": segment,
        "variant": variant,
        "start": iso_time(result.start_ts),
        "end": iso_time(result.end_ts),
        "bars": result.bars,
        "return_pct": result.return_pct,
        "mark_return_pct": result.mark_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "price_return_pct": result.price_return_pct,
        "buy_hold_return_pct": result.buy_hold_return_pct,
        "realized_harvest": result.realized_harvest,
        "stop_pnl": result.stop_pnl,
        "terminal_unrealized": result.terminal_unrealized,
        "fees": result.fees,
        "funding_cost": result.funding_cost,
        "entries": result.entries,
        "round_trips": result.round_trips,
        "stop_events": result.stop_events,
        "terminal_active_layers": result.terminal_active_layers,
        "average_exposure_pct": result.average_exposure_pct,
        "max_exposure_pct": result.max_exposure_pct,
    }


def fill_rows(inst_id: str, segment: str, simulation: LayeredSimulation) -> list[dict[str, Any]]:
    return [
        {
            "inst_id": inst_id,
            "segment": segment,
            "time": iso_time(fill.ts),
            **asdict(fill),
        }
        for fill in simulation.fills
    ]


def curve_rows(inst_id: str, segment: str, simulation: LayeredSimulation) -> list[dict[str, Any]]:
    return [
        {"inst_id": inst_id, "segment": segment, "time": iso_time(int(row["ts"])), **row}
        for row in simulation.equity_curve
    ]


def synthetic_candles(kind: str, count: int = 1200) -> list[Candle]:
    rows: list[Candle] = []
    prior = 100.0
    for index in range(count):
        if kind == "range":
            close = 100.0 + 2.0 * math.sin(index * 2.0 * math.pi / 48.0)
        elif kind == "oscillating_downtrend":
            close = 100.0 - 0.010 * index + 1.8 * math.sin(index * 2.0 * math.pi / 42.0)
        elif kind == "monotonic_downtrend":
            close = 100.0 - 0.020 * index
        else:
            raise ValueError(f"unknown synthetic kind: {kind}")
        close = max(5.0, close)
        open_px = prior
        wick = 0.18 if kind == "monotonic_downtrend" else 0.35
        high = max(open_px, close) + wick
        low = min(open_px, close) - wick
        rows.append(
            Candle(
                ts=1_800_000_000_000 + index * 300_000,
                open=Decimal(str(open_px)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=Decimal("1000"),
            )
        )
        prior = close
    return rows


def run_synthetic_scenarios(base: LayeredConfig, params: CandidateParams) -> list[dict[str, Any]]:
    config = replace(
        base,
        step_bps=params.step_bps,
        take_profit_bps=params.take_profit_bps,
        tranches=params.tranches,
        basket_stop_bps=params.basket_stop_bps,
        lot_size=0.001,
        min_size=0.001,
        contract_value=1.0,
        tick_size=0.01,
    )
    rows = []
    for scenario in ("range", "oscillating_downtrend", "monotonic_downtrend"):
        simulation = simulate_layered_strategy(synthetic_candles(scenario), config, (), record_details=False)
        rows.append({"scenario": scenario, **simulation_row("SYNTHETIC", scenario, "selected", simulation)})
    return rows


def feasibility_decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def subset(segment: str, variant: str) -> list[dict[str, Any]]:
        return [row for row in rows if row["segment"] == segment and row["variant"] == variant]

    validation = subset("validation", "selected")
    test = subset("test", "selected")
    stress = subset("test", "cost_stress")
    downtrend = subset("worst_downtrend", "selected")
    full_period = subset("full", "selected")
    risk_capped_test = subset("test", "risk_capped")
    no_stop_test = subset("test", "no_stop")
    no_stop_full = subset("full", "no_stop")
    no_stop_downtrend = subset("worst_downtrend", "no_stop")

    def metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
        returns = [float(row["return_pct"]) for row in items]
        drawdowns = [float(row["max_drawdown_pct"]) for row in items]
        return {
            "count": len(items),
            "positive": sum(1 for value in returns if value > 0),
            "positiveRatePct": sum(1 for value in returns if value > 0) / len(returns) * 100.0 if returns else 0.0,
            "medianReturnPct": statistics.median(returns) if returns else 0.0,
            "worstReturnPct": min(returns, default=0.0),
            "medianDrawdownPct": statistics.median(drawdowns) if drawdowns else 0.0,
            "worstDrawdownPct": max(drawdowns, default=0.0),
        }

    validation_metrics = metrics(validation)
    test_metrics = metrics(test)
    stress_metrics = metrics(stress)
    downtrend_metrics = metrics(downtrend)
    paper_candidate = (
        validation_metrics["positiveRatePct"] >= 60.0
        and validation_metrics["medianReturnPct"] > 0
        and test_metrics["positiveRatePct"] >= 60.0
        and test_metrics["medianReturnPct"] > 0
        and stress_metrics["medianReturnPct"] > 0
        and test_metrics["worstDrawdownPct"] <= 10.0
    )
    downtrend_claim_supported = downtrend_metrics["positiveRatePct"] >= 60.0 and downtrend_metrics["medianReturnPct"] > 0
    return {
        "status": "paper_candidate" if paper_candidate else "research_only",
        "downtrendProfitClaimSupported": downtrend_claim_supported,
        "validation": validation_metrics,
        "test": test_metrics,
        "costStressTest": stress_metrics,
        "fullPeriod": metrics(full_period),
        "worstDowntrendWindows": downtrend_metrics,
        "riskCappedTest": metrics(risk_capped_test),
        "noStopTest": metrics(no_stop_test),
        "noStopFullPeriod": metrics(no_stop_full),
        "noStopWorstDowntrend": metrics(no_stop_downtrend),
        "rule": "Paper candidate requires positive validation/test median, >=60% positive instruments, positive stressed median, and <=10% worst test drawdown.",
    }


def candidate_score_payload(item: CandidateScore) -> dict[str, Any]:
    return {**asdict(item.params), **{key: value for key, value in asdict(item).items() if key != "params"}}


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
    segment_rows: list[dict[str, Any]],
    fill_rows_payload: list[dict[str, Any]],
    curve_rows_payload: list[dict[str, Any]],
) -> None:
    (output_dir / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(output_dir / "segments.csv", segment_rows)
    write_csv(output_dir / "fills.csv", fill_rows_payload)
    write_csv(output_dir / "equity_curve.csv", curve_rows_payload)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    risk_capped = payload.get("bestRiskCappedParameters")
    top_candidate = payload["candidateScores"][0]
    period = payload["commonPeriod"]
    feasibility = payload["feasibility"]
    selected_instruments = [item for item in payload["instruments"] if item["selected"]]
    excluded = [item for item in payload["instruments"] if not item["selected"]]
    lines = [
        "# 半导体合约分层聚合减仓策略研究",
        "",
        "> 只读研究，不构成投资建议；没有读取私有账户，也没有启动服务或发送订单。",
        "",
        "## 策略还原",
        "",
        "- 只做多；从上一根已完成 K 线的锚点向下按固定百分比铺等额 USDT 分仓。",
        "- 每层独立记账；反弹至固定止盈价或上一层入场价（取更近者）就减掉该层。",
        "- 新开层禁止同一根 K 线内止盈；止损与成交采用偏保守的 K 线内顺序。",
        "- 收益按期末盯市并预扣模拟平仓成本，未实现亏损不能被已实现小盈利掩盖。",
        "",
        "## 数据与筛选",
        "",
        f"- 公共 {payload['config']['bar']} 共同区间：`{period['start']}` 至 `{period['end']}`。",
        f"- 入选合约：{', '.join(item['inst_id'] for item in selected_instruments)}。",
        f"- 训练/验证边界：`{period['trainEnd']}`；验证/测试边界：`{period['validationEnd']}`。",
    ]
    if excluded:
        lines.append("- 排除：" + ", ".join(f"{item['inst_id']} ({item['selection_note']})" for item in excluded) + "。")
    lines.extend(
        [
            "",
            "## 训练段统一选出的参数",
            "",
            "| 参数 | 数值 |",
            "| --- | ---: |",
            f"| 网格间距 | {selected['step_bps']:.1f} bps |",
            f"| 固定止盈 | {selected['take_profit_bps']:.1f} bps |",
            f"| 分仓数 | {selected['tranches']} |",
            f"| 篮子止损 | {selected['basket_stop_bps']:.1f} bps |",
            f"| 仅手续费的止盈盈亏平衡点 | {payload['roundTripBreakEvenTpBps']:.4f} bps |",
            f"| 覆盖全部样本的最低起始资金 | {payload['minimumStartingEquityForSelected']:.2f} USDT |",
            "",
            "同一组参数由所有入选合约的前 50% 数据共同选择，验证段和最终测试段没有参与参数选择。",
            f"但训练段最优组合的跨合约中位收益也只有 {top_candidate['median_return_pct']:.4f}%，"
            f"仅 {top_candidate['positive_instruments']}/{top_candidate['instrument_count']} 个合约为正，"
            "因此它是负样本中的相对排名第一，不代表训练阶段已经合格。",
            "",
            "## 样本外汇总",
            "",
            "| 区间 | 正收益合约 | 正收益占比 | 中位收益 | 最差收益 | 最差回撤 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    labels = [
        ("验证段", feasibility["validation"]),
        ("最终测试段", feasibility["test"]),
        ("最终测试成本压力", feasibility["costStressTest"]),
        ("连续完整区间", feasibility["fullPeriod"]),
        ("各合约最差三日窗口", feasibility["worstDowntrendWindows"]),
    ]
    for label, metrics in labels:
        lines.append(
            f"| {label} | {metrics['positive']}/{metrics['count']} | {metrics['positiveRatePct']:.1f}% | "
            f"{metrics['medianReturnPct']:.4f}% | {metrics['worstReturnPct']:.4f}% | {metrics['worstDrawdownPct']:.4f}% |"
        )
    if risk_capped and risk_capped != selected:
        capped_metrics = feasibility["riskCappedTest"]
        lines.extend(
            [
                "",
                "## 强制风险上限版本",
                "",
                f"训练段内表现最好的带止损参数为：层距 {risk_capped['step_bps']:.1f} bps、止盈 "
                f"{risk_capped['take_profit_bps']:.1f} bps、{risk_capped['tranches']} 层、篮子止损 "
                f"{risk_capped['basket_stop_bps']:.1f} bps。",
                f"最终测试为 {capped_metrics['positive']}/{capped_metrics['count']} 个合约正收益，中位 "
                f"{capped_metrics['medianReturnPct']:.4f}%，最差 {capped_metrics['worstReturnPct']:.4f}%，"
                f"最差回撤 {capped_metrics['worstDrawdownPct']:.4f}%。",
            ]
        )
    elif selected["basket_stop_bps"] > 0:
        no_stop_test = feasibility["noStopTest"]
        no_stop_full = feasibility["noStopFullPeriod"]
        no_stop_downtrend = feasibility["noStopWorstDowntrend"]
        lines.extend(
            [
                "",
                "## 去掉止损的尾部风险对照",
                "",
                f"使用相同层距/止盈/分仓但取消篮子止损后，最终测试中位收益为 "
                f"{no_stop_test['medianReturnPct']:.4f}%（{no_stop_test['positive']}/{no_stop_test['count']} 正收益）；"
                f"连续完整区间中位收益为 {no_stop_full['medianReturnPct']:.4f}%，最差三日窗口中位收益为 "
                f"{no_stop_downtrend['medianReturnPct']:.4f}%。",
                "短测试段的改善来自把亏损继续留在库存中，并没有消除单边下跌风险。",
            ]
        )
    test_rows = [
        row
        for row in payload["segmentResults"]
        if row["segment"] == "test" and row["variant"] == "selected"
    ]
    lines.extend(
        [
            "",
            "## 最终测试逐合约",
            "",
            "| 合约 | 标的涨跌 | 策略收益 | 最大回撤 | 已收割毛利 | 期末浮盈亏 | 费用+资金费 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in test_rows:
        lines.append(
            f"| {row['inst_id']} | {row['price_return_pct']:.4f}% | {row['return_pct']:.4f}% | "
            f"{row['max_drawdown_pct']:.4f}% | {row['realized_harvest']:.4f} | "
            f"{row['terminal_unrealized']:.4f} | {row['fees'] + row['funding_cost']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 合成行情压力测试",
            "",
            "| 场景 | 标的涨跌 | 策略收益 | 最大回撤 | 完成减仓 | 期末持仓层 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    scenario_names = {
        "range": "横盘震荡",
        "oscillating_downtrend": "震荡下跌",
        "monotonic_downtrend": "单边下跌",
    }
    for row in payload["syntheticScenarios"]:
        lines.append(
            f"| {scenario_names.get(row['scenario'], row['scenario'])} | {row['price_return_pct']:.4f}% | "
            f"{row['return_pct']:.4f}% | {row['max_drawdown_pct']:.4f}% | {row['round_trips']} | "
            f"{row['terminal_active_layers']} |"
        )
    status_text = "可进入仿真盘候选" if feasibility["status"] == "paper_candidate" else "仅保留研究，不进入仿真/实盘"
    downtrend_text = "支持" if feasibility["downtrendProfitClaimSupported"] else "不支持"
    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"- 判定：**{status_text}**。",
            f"- “下降趋势也能盈利”的样本支持：**{downtrend_text}**。该说法只可能在有足够反弹频率的震荡下跌中成立，单边下跌不会凭空产生收益。",
            "- 经济本质是用不断增加的库存/尾部风险换取高频小额均值回归收益；必须同时看盯市净值、期末库存、资金费率和止损损失。",
            "- `segments.csv` 可查看每个合约、每个时间段与压力版本；`fills.csv` 和 `equity_curve.csv` 保存最终测试段的逐笔与净值证据。",
            "",
            "## 局限",
            "",
            "- 5m OHLC 无法还原真实逐笔先后和挂单排队；穿透缓冲只能近似成交概率。",
            "- 当前盘口筛选是报告生成时快照，不代表整个历史区间流动性。",
            "- 股票/ETF 永续存在休市、跳空和高资金费率风险；回测不能等同于可成交实盘。",
        ]
    )
    return "\n".join(lines) + "\n"


def print_summary(output_dir: Path, payload: dict[str, Any]) -> None:
    selected = payload["selectedParameters"]
    feasibility = payload["feasibility"]
    print(f"output_dir={output_dir}")
    print(
        f"selected step={selected['step_bps']}bps tp={selected['take_profit_bps']}bps "
        f"tranches={selected['tranches']} stop={selected['basket_stop_bps']}bps"
    )
    print(
        f"status={feasibility['status']} test_median={feasibility['test']['medianReturnPct']:.6f}% "
        f"stress_median={feasibility['costStressTest']['medianReturnPct']:.6f}% "
        f"downtrend_supported={feasibility['downtrendProfitClaimSupported']}"
    )


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return OUTPUT_ROOT / timestamp


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())
