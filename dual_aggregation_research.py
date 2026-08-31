from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, iso_time, read_candles_csv
from dual_aggregation import (
    DualAggregationConfig,
    DualAggregationSimulation,
    path_statistics,
    simulate_dual_aggregation,
)
from funding_research import funding_cache_path, read_funding_csv
from layered_aggregation import round_quantity_down


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "dual_aggregation"
DEFAULT_SOURCE = PROJECT_ROOT / "reports" / "layered_aggregation" / "semis-5m-20260806" / "summary.json"
LEVERAGES = (1.0, 2.0, 3.0, 5.0, 8.0, 10.0)


@dataclass(frozen=True, slots=True)
class Candidate:
    step_bps: float
    take_profit_bps: float
    tranches_per_side: int
    side_stop_bps: float


@dataclass(slots=True)
class CandidateScore:
    params: Candidate
    score: float
    median_return_pct: float
    median_drawdown_pct: float
    worst_return_pct: float
    positive: int
    instruments: int
    median_round_trips: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only shared-equity research for independent long/short aggregation books."
    )
    parser.add_argument("--source-summary", default=str(DEFAULT_SOURCE))
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--starting-equity", type=float, default=200.0)
    parser.add_argument("--account-stop-pct", type=float, default=6.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.source_summary)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {item["inst_id"]: item for item in source["instruments"] if item["selected"]}
    bar = str(source["config"]["bar"])
    suffix = "" if args.pages <= 1 else f"x{args.pages}"
    candles_by_inst: dict[str, list[Candle]] = {}
    funding_by_inst = {}
    for inst_id in metadata:
        candle_path = PROJECT_ROOT / "data" / "backtest" / f"{inst_id}_{bar}_{args.limit}{suffix}.csv"
        if not candle_path.exists():
            raise SystemExit(f"Missing candle cache: {candle_path}")
        candles_by_inst[inst_id] = read_candles_csv(candle_path)
        funding_path = funding_cache_path(inst_id, 100, 1)
        funding_by_inst[inst_id] = read_funding_csv(funding_path) if funding_path.exists() else []

    period = source["commonPeriod"]
    common_start = parse_iso_ms(period["start"])
    train_end = parse_iso_ms(period["trainEnd"])
    validation_end = parse_iso_ms(period["validationEnd"])
    common_end = parse_iso_ms(period["end"])
    common_candles = {
        inst_id: time_slice(candles, common_start, common_end)
        for inst_id, candles in candles_by_inst.items()
    }
    train_candles = {
        inst_id: time_slice(candles, common_start, train_end)
        for inst_id, candles in common_candles.items()
    }
    base = DualAggregationConfig(
        starting_equity=args.starting_equity,
        allocation_pct=float(source["config"]["allocation_pct"]),
        leverage=1.0,
        cooldown_bars=int(source["config"]["cooldown_bars"]),
        maker_fee_bps=float(source["config"]["maker_fee_bps"]),
        taker_fee_bps=float(source["config"]["taker_fee_bps"]),
        liquidation_slippage_bps=float(source["config"]["stop_slippage_bps"]),
        fill_buffer_bps=float(source["config"]["fill_buffer_bps"]),
    )
    candidate_scores = select_parameters(train_candles, funding_by_inst, metadata, base)
    if not candidate_scores:
        raise SystemExit("No tradeable candidate produced enough training activity")
    selected = candidate_scores[0].params

    rows: list[dict[str, Any]] = []
    for inst_id, candles in common_candles.items():
        segments = {
            "train": time_slice(candles, common_start, train_end),
            "validation": time_slice(candles, train_end + 1, validation_end),
            "test": time_slice(candles, validation_end + 1, common_end),
            "full": candles,
            "worst_downtrend": extreme_return_window(candles, 864, minimum=True),
            "worst_uptrend": extreme_return_window(candles, 864, minimum=False),
        }
        meta = metadata[inst_id]
        for leverage in LEVERAGES:
            config = instrument_config(base, selected, meta, leverage)
            for segment_name, segment_candles in segments.items():
                simulation = simulate_dual_aggregation(
                    segment_candles,
                    config,
                    funding_by_inst.get(inst_id, []),
                    record_details=False,
                )
                rows.append(result_row(inst_id, segment_name, "raw", leverage, simulation))

            stressed = replace(
                config,
                maker_fee_bps=max(5.0, config.maker_fee_bps * 2.5),
                taker_fee_bps=max(8.0, config.taker_fee_bps * 1.6),
                liquidation_slippage_bps=max(4.0, config.liquidation_slippage_bps * 2.0),
                fill_buffer_bps=max(4.0, config.fill_buffer_bps * 4.0),
            )
            stress_sim = simulate_dual_aggregation(
                segments["test"], stressed, funding_by_inst.get(inst_id, []), record_details=False
            )
            rows.append(result_row(inst_id, "test", "cost_stress", leverage, stress_sim))

            stopped = replace(config, account_stop_pct=args.account_stop_pct)
            stopped_sim = simulate_dual_aggregation(
                segments["test"], stopped, funding_by_inst.get(inst_id, []), record_details=False
            )
            rows.append(result_row(inst_id, "test", "account_stop", leverage, stopped_sim))

            if selected.side_stop_bps > 0:
                no_side_stop = replace(config, side_stop_bps=0.0)
                for segment_name in ("test", "full"):
                    simulation = simulate_dual_aggregation(
                        segments[segment_name],
                        no_side_stop,
                        funding_by_inst.get(inst_id, []),
                        record_details=False,
                    )
                    rows.append(result_row(inst_id, segment_name, "no_side_stop", leverage, simulation))

    aggregates = aggregate_rows(rows)
    rolling_rows = rolling_path_experiment(
        common_candles,
        funding_by_inst,
        metadata,
        base,
        selected,
        window_bars=864,
        stride_bars=288,
    )
    rolling_summary = rolling_regime_summary(rolling_rows)
    synthetic = synthetic_experiment(base, selected)
    decision = decision_payload(aggregates)
    minimum_equity = minimum_starting_equity(selected, metadata, common_candles, base.allocation_pct)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_dual_aggregation_volatility_research",
        "sourceSummary": str(source_path.resolve()),
        "strategyDefinition": {
            "books": "independent long-below-anchor and short-above-anchor aggregation ladders",
            "exit": "each filled layer exits at the nearer of its fixed TP or the previous ladder level",
            "reanchor": "each book reanchors independently only after that book is flat or its cooldown ends",
            "riskBudget": "one shared marked-to-market account; half of the total gross budget reserved per side",
            "intrabar": "maintenance/stop first; existing TP before entries; no same-bar entry/TP",
            "forecast": "no directional or trend forecast is used",
        },
        "literature": literature_payload(),
        "config": {
            "bar": bar,
            "startingEquity": base.starting_equity,
            "allocationPct": base.allocation_pct,
            "leverages": list(LEVERAGES),
            "makerFeeBps": base.maker_fee_bps,
            "takerFeeBps": base.taker_fee_bps,
            "accountStopPct": args.account_stop_pct,
            "maintenanceMarginPct": base.maintenance_margin_pct,
        },
        "commonPeriod": period,
        "instruments": list(metadata),
        "selectedParameters": asdict(selected),
        "minimumStartingEquity": minimum_equity,
        "candidateScores": [score_payload(item) for item in candidate_scores[:25]],
        "rows": rows,
        "aggregates": aggregates,
        "rollingRows": rolling_rows,
        "rollingRegimes": rolling_summary,
        "syntheticScenarios": synthetic,
        "decision": decision,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "rows.csv", rows)
    write_csv(output_dir / "aggregate.csv", aggregates)
    write_csv(output_dir / "rolling_windows.csv", rolling_rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"selected={asdict(selected)}")
    for leverage in LEVERAGES:
        item = aggregate_lookup(aggregates, "test", "raw", leverage)
        print(
            f"leverage={leverage:g}x median={item['median_return_pct']:.6f}% "
            f"positive={item['positive']}/{item['count']} liquidated={item['liquidations']}"
        )
    print(f"status={decision['status']} passing={decision['passingLeverages']}")
    return 0


def candidate_grid() -> list[Candidate]:
    return [
        Candidate(step, take_profit, tranches, side_stop)
        for step in (75.0, 100.0, 150.0, 200.0)
        for take_profit in (25.0, 40.0, 60.0)
        if take_profit <= step
        for tranches in (4, 6)
        for side_stop in (0.0, 600.0, 900.0)
    ]


def select_parameters(
    candles_by_inst: dict[str, list[Candle]],
    funding_by_inst: dict[str, list[Any]],
    metadata: dict[str, dict[str, Any]],
    base: DualAggregationConfig,
) -> list[CandidateScore]:
    scores = []
    for params in candidate_grid():
        if not candidate_is_tradeable(params, candles_by_inst, metadata, base):
            continue
        returns = []
        drawdowns = []
        trips = []
        for inst_id, candles in candles_by_inst.items():
            config = instrument_config(base, params, metadata[inst_id], 1.0)
            result = simulate_dual_aggregation(
                candles, config, funding_by_inst.get(inst_id, []), record_details=False
            ).result
            returns.append(result.return_pct)
            drawdowns.append(result.max_drawdown_pct)
            trips.append(result.round_trips)
        median_trips = statistics.median(trips)
        if median_trips < 4 or sum(value >= 4 for value in trips) < math.ceil(len(trips) / 2):
            continue
        median_return = statistics.median(returns)
        median_drawdown = statistics.median(drawdowns)
        positive = sum(value > 0 for value in returns)
        score = (
            median_return
            - 0.60 * median_drawdown
            + 0.006 * min(median_trips, 150)
            + 0.15 * (positive - len(returns) / 2.0)
            + 0.20 * min(returns)
        )
        scores.append(
            CandidateScore(
                params,
                score,
                median_return,
                median_drawdown,
                min(returns),
                positive,
                len(returns),
                median_trips,
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def candidate_is_tradeable(
    params: Candidate,
    candles_by_inst: dict[str, list[Candle]],
    metadata: dict[str, dict[str, Any]],
    base: DualAggregationConfig,
) -> bool:
    layer_notional = base.starting_equity * base.allocation_pct / 100.0 / (2.0 * params.tranches_per_side)
    for inst_id, candles in candles_by_inst.items():
        meta = metadata[inst_id]
        price = float(candles[0].close)
        raw_quantity = layer_notional / (price * float(meta["contract_value"]))
        if round_quantity_down(raw_quantity, float(meta["lot_size"]), float(meta["min_size"])) <= 0:
            return False
    return True


def instrument_config(
    base: DualAggregationConfig,
    params: Candidate,
    meta: dict[str, Any],
    leverage: float,
) -> DualAggregationConfig:
    return replace(
        base,
        leverage=leverage,
        step_bps=params.step_bps,
        take_profit_bps=params.take_profit_bps,
        tranches_per_side=params.tranches_per_side,
        side_stop_bps=params.side_stop_bps,
        lot_size=float(meta["lot_size"]),
        min_size=float(meta["min_size"]),
        contract_value=float(meta["contract_value"]),
        tick_size=float(meta["tick_size"]),
    )


def result_row(
    inst_id: str,
    segment: str,
    variant: str,
    leverage: float,
    simulation: DualAggregationSimulation,
) -> dict[str, Any]:
    result = simulation.result
    return {
        "inst_id": inst_id,
        "segment": segment,
        "variant": variant,
        "leverage": leverage,
        "start": iso_time(result.start_ts),
        "end": iso_time(result.end_ts),
        "bars": result.bars,
        "price_return_pct": result.price_return_pct,
        "path_variation_pct": result.path_variation_pct,
        "path_efficiency_ratio": result.path_efficiency_ratio,
        "return_pct": result.return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "realized_harvest": result.realized_harvest,
        "stop_pnl": result.stop_pnl,
        "terminal_unrealized": result.terminal_unrealized,
        "fees": result.fees,
        "funding_cost": result.funding_cost,
        "entries": result.entries,
        "round_trips": result.round_trips,
        "long_round_trips": result.long_round_trips,
        "short_round_trips": result.short_round_trips,
        "side_stop_events": result.side_stop_events,
        "terminal_long_layers": result.terminal_long_layers,
        "terminal_short_layers": result.terminal_short_layers,
        "max_gross_exposure_pct": result.max_gross_exposure_pct,
        "max_abs_net_exposure_pct": result.max_abs_net_exposure_pct,
        "liquidated": result.liquidated,
        "account_stopped": result.account_stopped,
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, float], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["segment"], row["variant"], float(row["leverage"])), []).append(row)
    result = []
    for (segment, variant, leverage), items in groups.items():
        returns = [float(item["return_pct"]) for item in items]
        drawdowns = [float(item["max_drawdown_pct"]) for item in items]
        result.append(
            {
                "segment": segment,
                "variant": variant,
                "leverage": leverage,
                "count": len(items),
                "positive": sum(value > 0 for value in returns),
                "median_return_pct": statistics.median(returns),
                "mean_return_pct": statistics.fmean(returns),
                "worst_return_pct": min(returns),
                "median_drawdown_pct": statistics.median(drawdowns),
                "worst_drawdown_pct": max(drawdowns),
                "liquidations": sum(bool(item["liquidated"]) for item in items),
                "account_stops": sum(bool(item["account_stopped"]) for item in items),
                "median_round_trips": statistics.median(float(item["round_trips"]) for item in items),
                "median_max_gross_exposure_pct": statistics.median(
                    float(item["max_gross_exposure_pct"]) for item in items
                ),
                "median_max_abs_net_exposure_pct": statistics.median(
                    float(item["max_abs_net_exposure_pct"]) for item in items
                ),
            }
        )
    result.sort(key=lambda item: (item["segment"], item["variant"], item["leverage"]))
    return result


def rolling_path_experiment(
    candles_by_inst: dict[str, list[Candle]],
    funding_by_inst: dict[str, list[Any]],
    metadata: dict[str, dict[str, Any]],
    base: DualAggregationConfig,
    selected: Candidate,
    *,
    window_bars: int,
    stride_bars: int,
) -> list[dict[str, Any]]:
    rows = []
    for inst_id, candles in candles_by_inst.items():
        config = instrument_config(base, selected, metadata[inst_id], 1.0)
        for start in range(0, len(candles) - window_bars + 1, stride_bars):
            window = candles[start : start + window_bars]
            simulation = simulate_dual_aggregation(
                window, config, funding_by_inst.get(inst_id, []), record_details=False
            )
            result = simulation.result
            rows.append(
                {
                    "inst_id": inst_id,
                    "start": iso_time(result.start_ts),
                    "end": iso_time(result.end_ts),
                    "return_pct": result.return_pct,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "price_return_pct": result.price_return_pct,
                    "path_variation_pct": result.path_variation_pct,
                    "path_efficiency_ratio": result.path_efficiency_ratio,
                    "round_trips": result.round_trips,
                    "realized_harvest_pct": result.realized_harvest / result.starting_equity * 100.0,
                    "fees_pct": result.fees / result.starting_equity * 100.0,
                    "funding_cost_pct": result.funding_cost / result.starting_equity * 100.0,
                    "terminal_unrealized_pct": result.terminal_unrealized / result.starting_equity * 100.0,
                    "max_abs_net_exposure_pct": result.max_abs_net_exposure_pct,
                    "liquidated": result.liquidated,
                }
            )
    return rows


def rolling_regime_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    efficiencies = sorted(float(item["path_efficiency_ratio"]) for item in rows)
    variations = sorted(float(item["path_variation_pct"]) for item in rows)
    low_eff = quantile(efficiencies, 1.0 / 3.0)
    high_eff = quantile(efficiencies, 2.0 / 3.0)
    median_variation = quantile(variations, 0.5)
    groups = {
        "most_oscillatory_third": [item for item in rows if float(item["path_efficiency_ratio"]) <= low_eff],
        "most_directional_third": [item for item in rows if float(item["path_efficiency_ratio"]) >= high_eff],
        "high_variation_oscillatory": [
            item
            for item in rows
            if float(item["path_variation_pct"]) >= median_variation
            and float(item["path_efficiency_ratio"]) <= low_eff
        ],
        "high_variation_directional": [
            item
            for item in rows
            if float(item["path_variation_pct"]) >= median_variation
            and float(item["path_efficiency_ratio"]) >= high_eff
        ],
    }
    result = []
    for label, items in groups.items():
        returns = [float(item["return_pct"]) for item in items]
        result.append(
            {
                "regime": label,
                "count": len(items),
                "positive": sum(value > 0 for value in returns),
                "median_return_pct": statistics.median(returns) if returns else 0.0,
                "worst_return_pct": min(returns, default=0.0),
                "median_round_trips": statistics.median(
                    [float(item["round_trips"]) for item in items]
                )
                if items
                else 0.0,
                "median_efficiency_ratio": statistics.median(
                    [float(item["path_efficiency_ratio"]) for item in items]
                )
                if items
                else 0.0,
                "median_variation_pct": statistics.median(
                    [float(item["path_variation_pct"]) for item in items]
                )
                if items
                else 0.0,
                "median_realized_harvest_pct": statistics.median(
                    [float(item["realized_harvest_pct"]) for item in items]
                )
                if items
                else 0.0,
                "median_fees_pct": statistics.median([float(item["fees_pct"]) for item in items])
                if items
                else 0.0,
                "median_terminal_unrealized_pct": statistics.median(
                    [float(item["terminal_unrealized_pct"]) for item in items]
                )
                if items
                else 0.0,
            }
        )
    return result


def synthetic_experiment(base: DualAggregationConfig, selected: Candidate) -> list[dict[str, Any]]:
    rows = []
    for leverage in (1.0, 3.0, 10.0):
        config = replace(
            base,
            leverage=leverage,
            step_bps=selected.step_bps,
            take_profit_bps=selected.take_profit_bps,
            tranches_per_side=selected.tranches_per_side,
            side_stop_bps=selected.side_stop_bps,
            lot_size=0.001,
            min_size=0.001,
            contract_value=1.0,
            tick_size=0.01,
        )
        for scenario in (
            "range",
            "oscillating_uptrend",
            "oscillating_downtrend",
            "monotonic_uptrend",
            "monotonic_downtrend",
        ):
            simulation = simulate_dual_aggregation(
                synthetic_candles(scenario), config, (), record_details=False
            )
            rows.append({"scenario": scenario, "leverage": leverage, **result_row("SYNTHETIC", scenario, "raw", leverage, simulation)})
    return rows


def synthetic_candles(kind: str, count: int = 1200) -> list[Candle]:
    rows = []
    prior = 100.0
    for index in range(count):
        wave = 2.0 * math.sin(index * 2.0 * math.pi / 48.0)
        if kind == "range":
            close = 100.0 + wave
        elif kind == "oscillating_uptrend":
            close = 100.0 + 0.010 * index + wave
        elif kind == "oscillating_downtrend":
            close = 100.0 - 0.010 * index + wave
        elif kind == "monotonic_uptrend":
            close = 100.0 + 0.020 * index
        elif kind == "monotonic_downtrend":
            close = 100.0 - 0.020 * index
        else:
            raise ValueError(kind)
        close = max(5.0, close)
        wick = 0.18 if kind.startswith("monotonic") else 0.35
        rows.append(
            Candle(
                ts=1_800_000_000_000 + index * 300_000,
                open=Decimal(str(prior)),
                high=Decimal(str(max(prior, close) + wick)),
                low=Decimal(str(min(prior, close) - wick)),
                close=Decimal(str(close)),
                volume=Decimal("1000"),
            )
        )
        prior = close
    return rows


def decision_payload(aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    passing = []
    for leverage in LEVERAGES:
        validation = aggregate_lookup(aggregates, "validation", "raw", leverage)
        test = aggregate_lookup(aggregates, "test", "raw", leverage)
        stress = aggregate_lookup(aggregates, "test", "cost_stress", leverage)
        full = aggregate_lookup(aggregates, "full", "raw", leverage)
        if (
            validation["median_return_pct"] > 0
            and test["median_return_pct"] > 0
            and stress["median_return_pct"] > 0
            and full["median_return_pct"] > 0
            and validation["liquidations"] == 0
            and test["liquidations"] == 0
            and full["liquidations"] == 0
        ):
            passing.append(leverage)
    return {
        "status": "paper_candidate" if passing else "research_only",
        "passingLeverages": passing,
        "recommendedLeverage": min(passing) if passing else None,
        "rule": "Positive validation, test, stressed-test and full medians with zero liquidations.",
    }


def literature_payload() -> list[dict[str, str]]:
    return [
        {
            "citation": "Willenbrock (2011), Diversification Return, Portfolio Rebalancing, and the Commodity Return Puzzle",
            "url": "https://doi.org/10.2469/faj.v67.n4.1",
            "relevance": "rebalancing is the source of diversification return; buy-and-hold is not equivalent",
        },
        {
            "citation": "Witte (2015), Volatility Harvesting: Extracting Return from Randomness",
            "url": "https://arxiv.org/abs/1508.05241",
            "relevance": "discrete random return models can turn excess volatility into growth while retaining implicit risks",
        },
        {
            "citation": "Avellaneda and Stoikov (2008), High-frequency trading in a limit order book",
            "url": "https://doi.org/10.1080/14697680701381228",
            "relevance": "liquidity-provision quotes must account for inventory and price risk",
        },
        {
            "citation": "Guéant, Lehalle and Fernandez-Tapia (2013), Dealing with the inventory risk",
            "url": "https://doi.org/10.1007/s11579-012-0087-0",
            "relevance": "market-making optimization is explicitly solved under inventory constraints",
        },
        {
            "citation": "Chen, Chen and Jang (2025), Dynamic Grid Trading Strategy",
            "url": "https://arxiv.org/abs/2506.11921",
            "relevance": "preprint derives near-zero expectation for a traditional static grid under simple assumptions and tests dynamic resetting",
        },
    ]


def markdown_report(payload: dict[str, Any]) -> str:
    selected = payload["selectedParameters"]
    aggregates = payload["aggregates"]
    top = payload["candidateScores"][0]
    period = payload["commonPeriod"]
    lines = [
        "# 双账本聚合策略：波动收割研究",
        "",
        "> 只读公共数据研究；没有读取账户、启动服务或发送订单。",
        "",
        "## 文献定位",
        "",
        "这不是方向预测系统，而是离散再平衡/流动性提供策略。文献支持“波动可通过再平衡转化为增长”的条件性结论，"
        "同时一致强调库存风险。传统静态网格并不自动拥有正期望。",
        "",
    ]
    for item in payload["literature"]:
        lines.append(f"- [{item['citation']}]({item['url']})：{item['relevance']}。")
    lines.extend(
        [
            "",
            "## 策略与恒等式",
            "",
            "- 多头账本只在锚点及下方聚合，空头账本只在锚点及上方聚合；两边独立止盈和重新锚定。",
            "- 两边共享一个盯市权益账户，总毛敞口上限为 `allocation × leverage`，每边最多使用一半，避免把对冲模式误算成双倍杠杆。",
            "- 若多空数量都为 Q、均价分别为 C_L 与 C_S，则组合浮盈亏为 `Q(C_S-C_L)`；只有数量匹配时当前价格项才消失。",
            "- 本实验没有趋势判断。路径效率 `|期末位移|/累计绝对变动` 只用于事后分组：越低越往返，越高越单边。",
            "",
            "## 数据与训练选择",
            "",
            f"- 公共 {payload['config']['bar']} 数据：`{period['start']}` 至 `{period['end']}`；训练、验证、测试按 50%/25%/25% 顺序切分。",
            f"- 合约：{', '.join(payload['instruments'])}。",
            f"- 起始权益 {payload['config']['startingEquity']:.2f} USDT；满足全部合约双边最小下单量的估计下限为 {payload['minimumStartingEquity']:.2f} USDT。",
            f"- 训练选择：层距 {selected['step_bps']:.1f} bps、止盈 {selected['take_profit_bps']:.1f} bps、每边 {selected['tranches_per_side']} 层、单边止损 {selected['side_stop_bps']:.1f} bps。",
            f"- 训练最优候选中位收益 {top['median_return_pct']:.4f}%，{top['positive']}/{top['instruments']} 合约为正，中位回撤 {top['median_drawdown_pct']:.4f}%。",
            "",
            "## 杠杆与跨时间稳定性",
            "",
            "| 杠杆 | 验证中位 | 测试中位 | 成本压力中位 | 完整区间中位 | 最差下跌中位 | 最差上涨中位 | 完整区间清算 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for leverage in LEVERAGES:
        validation = aggregate_lookup(aggregates, "validation", "raw", leverage)
        test = aggregate_lookup(aggregates, "test", "raw", leverage)
        stress = aggregate_lookup(aggregates, "test", "cost_stress", leverage)
        full = aggregate_lookup(aggregates, "full", "raw", leverage)
        down = aggregate_lookup(aggregates, "worst_downtrend", "raw", leverage)
        up = aggregate_lookup(aggregates, "worst_uptrend", "raw", leverage)
        lines.append(
            f"| {leverage:g}x | {validation['median_return_pct']:.4f}% | {test['median_return_pct']:.4f}% | "
            f"{stress['median_return_pct']:.4f}% | {full['median_return_pct']:.4f}% | "
            f"{down['median_return_pct']:.4f}% | {up['median_return_pct']:.4f}% | {full['liquidations']} |"
        )
    lines.extend(
        [
            "",
            "## 最终测试段风险",
            "",
            "| 杠杆 | 正收益 | 中位回撤 | 最差回撤 | 中位最大毛敞口 | 中位最大净敞口 | 6%账户止损触发 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for leverage in LEVERAGES:
        raw = aggregate_lookup(aggregates, "test", "raw", leverage)
        stopped = aggregate_lookup(aggregates, "test", "account_stop", leverage)
        lines.append(
            f"| {leverage:g}x | {raw['positive']}/{raw['count']} | {raw['median_drawdown_pct']:.4f}% | "
            f"{raw['worst_drawdown_pct']:.4f}% | {raw['median_max_gross_exposure_pct']:.1f}% | "
            f"{raw['median_max_abs_net_exposure_pct']:.1f}% | {stopped['account_stops']}/{stopped['count']} |"
        )
    lines.extend(
        [
            "",
            "## 三日滚动路径实验（1x）",
            "",
            "路径分组不参与交易，只检验收益究竟来自哪种波动。",
            "",
            "| 路径组 | 窗口数 | 正收益 | 中位收益 | 毛收割 | 费用 | 期末库存 | 中位往返 | 路径效率 | 累计变动 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    labels = {
        "most_oscillatory_third": "往返性最高三分之一",
        "most_directional_third": "单边性最高三分之一",
        "high_variation_oscillatory": "高变动且往返",
        "high_variation_directional": "高变动且单边",
    }
    for item in payload["rollingRegimes"]:
        lines.append(
            f"| {labels[item['regime']]} | {item['count']} | {item['positive']}/{item['count']} | "
            f"{item['median_return_pct']:.4f}% | {item['median_realized_harvest_pct']:.4f}% | "
            f"{item['median_fees_pct']:.4f}% | {item['median_terminal_unrealized_pct']:.4f}% | "
            f"{item['median_round_trips']:.1f} | {item['median_efficiency_ratio']:.4f} | "
            f"{item['median_variation_pct']:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## 合成路径",
            "",
            "| 杠杆 | 区间震荡 | 震荡上涨 | 震荡下跌 | 单调上涨 | 单调下跌 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    synthetic = payload["syntheticScenarios"]
    scenario_keys = (
        "range",
        "oscillating_uptrend",
        "oscillating_downtrend",
        "monotonic_uptrend",
        "monotonic_downtrend",
    )
    for leverage in (1.0, 3.0, 10.0):
        values = {
            item["scenario"]: item
            for item in synthetic
            if float(item["leverage"]) == leverage
        }
        cells = [
            ("清算" if values[key]["liquidated"] else f"{values[key]['return_pct']:.4f}%")
            for key in scenario_keys
        ]
        lines.append(f"| {leverage:g}x | " + " | ".join(cells) + " |")
    decision = payload["decision"]
    lines.extend(
        [
            "",
            "## 判定",
            "",
            f"- 结果：**{'可进入仿真盘候选' if decision['status'] == 'paper_candidate' else '仅研究'}**；通过杠杆：{decision['passingLeverages'] or '无'}。",
            "- 该策略可以不预测方向，但并非纯粹‘做多波动’：它偏好高累计变动、低净位移的往返路径，并厌恶高净位移的单边路径。",
            "- 聚合改善的是成交均价；在另一边尚未匹配前，增加仓位同时增加净库存和清算风险。",
            "- `rolling_windows.csv` 保存不重叠起点的三日路径实验；它用于解释收益来源，不是未来可知的筛选器。",
        ]
    )
    return "\n".join(lines) + "\n"


def minimum_starting_equity(
    params: Candidate,
    metadata: dict[str, dict[str, Any]],
    candles_by_inst: dict[str, list[Candle]],
    allocation_pct: float,
) -> float:
    required = 0.0
    for inst_id, candles in candles_by_inst.items():
        meta = metadata[inst_id]
        minimum_notional = float(meta["min_size"]) * float(meta["contract_value"]) * float(candles[0].close)
        equity = minimum_notional * 2.0 * params.tranches_per_side / (allocation_pct / 100.0)
        required = max(required, equity)
    return required


def score_payload(item: CandidateScore) -> dict[str, Any]:
    return {"params": asdict(item.params), **{key: value for key, value in asdict(item).items() if key != "params"}}


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * min(1.0, max(0.0, fraction))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def aggregate_lookup(
    aggregates: list[dict[str, Any]], segment: str, variant: str, leverage: float
) -> dict[str, Any]:
    for item in aggregates:
        if item["segment"] == segment and item["variant"] == variant and float(item["leverage"]) == leverage:
            return item
    raise KeyError((segment, variant, leverage))


def time_slice(candles: list[Candle], start_ts: int, end_ts: int) -> list[Candle]:
    rows = [item for item in candles if start_ts <= item.ts <= end_ts]
    if len(rows) < 2:
        raise ValueError("candle slice too short")
    return rows


def extreme_return_window(candles: list[Candle], bars: int, *, minimum: bool) -> list[Candle]:
    if len(candles) <= bars:
        return candles
    best_start = 0
    best_value = math.inf if minimum else -math.inf
    for start in range(len(candles) - bars + 1):
        first = float(candles[start].close)
        last = float(candles[start + bars - 1].close)
        value = last / first - 1.0 if first > 0 else 0.0
        if (minimum and value < best_value) or (not minimum and value > best_value):
            best_value = value
            best_start = start
    return candles[best_start : best_start + bars]


def parse_iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
