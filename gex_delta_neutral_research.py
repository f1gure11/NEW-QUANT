from __future__ import annotations

import argparse
import bisect
import csv
import json
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import Candle, iso_time, read_candles_csv
from dual_aggregation import DualAggregationConfig, simulate_dual_aggregation
from funding_research import funding_cache_path, read_funding_csv
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GEX = PROJECT_ROOT / "data" / "okx" / "gex_snapshots.jsonl"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "gex_delta_neutral"
LEVERAGES = (1.0, 3.0, 10.0)


@dataclass(frozen=True, slots=True)
class GexEvent:
    underlying: str
    event_ts: int
    captured_at: str
    source_timestamp: str
    net_gex: float
    gross_gex: float
    oi_usd: float
    spot_price: float
    call_wall: float
    put_wall: float


@dataclass(frozen=True, slots=True)
class GridParams:
    step_bps: float
    take_profit_bps: float
    tranches_per_side: int


@dataclass(slots=True)
class GridScore:
    params: GridParams
    score: float
    median_return_pct: float
    median_drawdown_pct: float
    worst_return_pct: float
    positive: int
    windows: int
    median_round_trips: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Point-in-time GEX regime test for dual aggregation and delta-neutral feasibility."
    )
    parser.add_argument("--gex-file", default=str(DEFAULT_GEX))
    parser.add_argument("--window-bars", type=int, default=72, help="Forward 5m bars; 72 = six hours")
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    events = load_crypto_gex_events(Path(args.gex_file))
    underlyings = sorted(events)
    candles_by_base = {
        base: read_candles_csv(PROJECT_ROOT / "data" / "backtest" / f"{base}-USDT-SWAP_5m_300x30.csv")
        for base in underlyings
    }
    windows = non_overlapping_forward_windows(events, candles_by_base, args.window_bars)
    metadata = public_swap_metadata([f"{base}-USDT-SWAP" for base in underlyings])
    funding = {}
    for base in underlyings:
        inst_id = f"{base}-USDT-SWAP"
        path = funding_cache_path(inst_id, 100, 1)
        funding[base] = read_funding_csv(path) if path.exists() else []

    base_config = DualAggregationConfig(
        starting_equity=args.starting_equity,
        allocation_pct=60.0,
        leverage=1.0,
        side_stop_bps=0.0,
        cooldown_bars=12,
        maker_fee_bps=2.0,
        taker_fee_bps=5.0,
        liquidation_slippage_bps=2.0,
        fill_buffer_bps=1.0,
    )
    train_ids, test_ids = chronological_window_split(windows)
    candidate_scores = select_crypto_grid(
        [item for item in windows if (item[0], item[1].event_ts) in train_ids],
        metadata,
        funding,
        base_config,
    )
    if not candidate_scores:
        raise SystemExit("No crypto grid candidate produced enough training activity")
    selected = candidate_scores[0].params
    base_config = replace(
        base_config,
        step_bps=selected.step_bps,
        take_profit_bps=selected.take_profit_bps,
        tranches_per_side=selected.tranches_per_side,
    )
    rows = []
    for base, event, candles in windows:
        meta = metadata[f"{base}-USDT-SWAP"]
        for leverage in LEVERAGES:
            config = replace(
                base_config,
                leverage=leverage,
                lot_size=float(meta["lotSz"]),
                min_size=float(meta["minSz"]),
                contract_value=float(meta["ctVal"]),
                tick_size=float(meta["tickSz"]),
            )
            result = simulate_dual_aggregation(
                candles, config, funding.get(base, []), record_details=False
            ).result
            rows.append(
                {
                    "underlying": base,
                    "inst_id": f"{base}-USDT-SWAP",
                    "event_time": iso_time(event.event_ts),
                    "sample": "train" if (base, event.event_ts) in train_ids else "test",
                    "window_start": iso_time(candles[0].ts),
                    "window_end": iso_time(candles[-1].ts),
                    "gex_sign": "positive" if event.net_gex > 0 else "negative" if event.net_gex < 0 else "zero",
                    "net_gex": event.net_gex,
                    "gross_gex": event.gross_gex,
                    "oi_usd": event.oi_usd,
                    "normalized_net_gex": event.net_gex / event.oi_usd if event.oi_usd > 0 else 0.0,
                    "leverage": leverage,
                    "price_return_pct": result.price_return_pct,
                    "path_variation_pct": result.path_variation_pct,
                    "path_efficiency_ratio": result.path_efficiency_ratio,
                    "strategy_return_pct": result.return_pct,
                    "max_drawdown_pct": result.max_drawdown_pct,
                    "round_trips": result.round_trips,
                    "fees_pct": result.fees / result.starting_equity * 100.0,
                    "terminal_unrealized_pct": result.terminal_unrealized / result.starting_equity * 100.0,
                    "max_gross_exposure_pct": result.max_gross_exposure_pct,
                    "max_abs_net_exposure_pct": result.max_abs_net_exposure_pct,
                    "liquidated": result.liquidated,
                }
            )
    path_summary = summarize_paths(rows)
    strategy_summary = summarize_strategy(rows)
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_point_in_time_gex_delta_neutral_feasibility",
        "gexFile": str(Path(args.gex_file).resolve()),
        "methodology": {
            "eventTime": "max(snapshot capture time, exchange option source time)",
            "windows": f"non-overlapping forward windows of {args.window_bars} completed 5m bars",
            "lookahead": "the first price bar begins strictly after the GEX event timestamp",
            "gexSign": "calls positive and puts negative; dealer-position sign is assumed, not observed",
            "linearTest": "GEX conditions a shared-equity dual aggregation strategy; no options are traded",
            "optionTest": "not run because snapshots lack point-in-time option bid/ask, IV, theta and executable hedge fills",
        },
        "config": {
            "windowBars": args.window_bars,
            "startingEquity": args.starting_equity,
            "leverages": list(LEVERAGES),
            "selectedGridParameters": asdict(selected),
        },
        "underlyings": underlyings,
        "eventCounts": {base: len(events[base]) for base in underlyings},
        "selectedWindowCounts": {
            base: sum(1 for item in windows if item[0] == base) for base in underlyings
        },
        "sampleWindowCounts": {"train": len(train_ids), "test": len(test_ids)},
        "instrumentMetadata": metadata,
        "candidateScores": [score_payload(item) for item in candidate_scores],
        "pathSummary": path_summary,
        "strategySummary": strategy_summary,
        "rows": rows,
    }
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(output_dir / "event_windows.csv", rows)
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print(f"events={payload['eventCounts']} windows={payload['selectedWindowCounts']}")
    for item in path_summary:
        print(
            f"gex={item['gex_sign']} windows={item['count']} "
            f"efficiency={item['median_path_efficiency_ratio']:.6f} "
            f"variation={item['median_path_variation_pct']:.6f}%"
        )
    return 0


def load_crypto_gex_events(path: Path) -> dict[str, list[GexEvent]]:
    by_base: dict[str, dict[int, GexEvent]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
                payload = record.get("data", record)
                captured = str(record.get("capturedAt") or payload.get("updatedAt") or "")
                captured_ts = parse_iso_ms(captured)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            for row in payload.get("underlyings", []):
                try:
                    base = str(row.get("underlying") or "").upper()
                    source = str(row.get("sourceTimestamp") or captured)
                    source_ts = parse_iso_ms(source)
                    event_ts = max(captured_ts, source_ts)
                    net_gex = float(row.get("netGex") or 0.0)
                    event = GexEvent(
                        underlying=base,
                        event_ts=event_ts,
                        captured_at=captured,
                        source_timestamp=source,
                        net_gex=net_gex,
                        gross_gex=float(row.get("grossGex") or 0.0),
                        oi_usd=float(row.get("oiUsd") or 0.0),
                        spot_price=float(row.get("spotPrice") or 0.0),
                        call_wall=wall_strike(row.get("callWall")),
                        put_wall=wall_strike(row.get("putWall")),
                    )
                except (TypeError, ValueError, OverflowError):
                    continue
                if base and event.oi_usd > 0 and event.spot_price > 0:
                    by_base.setdefault(base, {})[event_ts] = event
    return {base: sorted(items.values(), key=lambda item: item.event_ts) for base, items in by_base.items()}


def non_overlapping_forward_windows(
    events_by_base: dict[str, list[GexEvent]],
    candles_by_base: dict[str, list[Candle]],
    bars: int,
) -> list[tuple[str, GexEvent, list[Candle]]]:
    if bars < 2:
        raise ValueError("window must contain at least two bars")
    result = []
    for base, events in events_by_base.items():
        candles = sorted(candles_by_base.get(base, []), key=lambda item: item.ts)
        timestamps = [item.ts for item in candles]
        next_available_ts = 0
        for event in events:
            if event.event_ts < next_available_ts:
                continue
            start = bisect.bisect_right(timestamps, event.event_ts)
            window = candles[start : start + bars]
            if len(window) < bars:
                continue
            result.append((base, event, window))
            next_available_ts = window[-1].ts + 1
    result.sort(key=lambda item: (item[1].event_ts, item[0]))
    return result


def public_swap_metadata(inst_ids: list[str]) -> dict[str, dict[str, Any]]:
    response = OkxRestClient().request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"})
    wanted = set(inst_ids)
    result = {}
    for row in response.get("data", []):
        inst_id = str(row.get("instId") or "")
        if inst_id not in wanted:
            continue
        result[inst_id] = {
            "instId": inst_id,
            "ctVal": float(row.get("ctVal") or 1.0),
            "lotSz": float(row.get("lotSz") or 0.001),
            "minSz": float(row.get("minSz") or 0.001),
            "tickSz": float(row.get("tickSz") or 0.01),
        }
    missing = wanted - set(result)
    if missing:
        raise ValueError(f"missing public instrument metadata: {sorted(missing)}")
    return result


def chronological_window_split(
    windows: list[tuple[str, GexEvent, list[Candle]]]
) -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    by_base: dict[str, list[tuple[str, GexEvent, list[Candle]]]] = {}
    for item in windows:
        by_base.setdefault(item[0], []).append(item)
    train: set[tuple[str, int]] = set()
    test: set[tuple[str, int]] = set()
    for base, items in by_base.items():
        ordered = sorted(items, key=lambda item: item[1].event_ts)
        boundary = max(1, len(ordered) // 2)
        train.update((base, item[1].event_ts) for item in ordered[:boundary])
        test.update((base, item[1].event_ts) for item in ordered[boundary:])
    return train, test


def crypto_grid_candidates() -> list[GridParams]:
    return [
        GridParams(step, take_profit, tranches)
        for step in (25.0, 50.0, 75.0, 100.0)
        for take_profit in (15.0, 25.0, 40.0)
        if take_profit <= step
        for tranches in (4, 6)
    ]


def select_crypto_grid(
    windows: list[tuple[str, GexEvent, list[Candle]]],
    metadata: dict[str, dict[str, Any]],
    funding: dict[str, list[Any]],
    base: DualAggregationConfig,
) -> list[GridScore]:
    scores = []
    for params in crypto_grid_candidates():
        returns = []
        drawdowns = []
        trips = []
        for underlying, _, candles in windows:
            meta = metadata[f"{underlying}-USDT-SWAP"]
            config = replace(
                base,
                leverage=1.0,
                step_bps=params.step_bps,
                take_profit_bps=params.take_profit_bps,
                tranches_per_side=params.tranches_per_side,
                lot_size=float(meta["lotSz"]),
                min_size=float(meta["minSz"]),
                contract_value=float(meta["ctVal"]),
                tick_size=float(meta["tickSz"]),
            )
            result = simulate_dual_aggregation(
                candles, config, funding.get(underlying, []), record_details=False
            ).result
            returns.append(result.return_pct)
            drawdowns.append(result.max_drawdown_pct)
            trips.append(result.round_trips)
        median_trips = statistics.median(trips) if trips else 0.0
        if not returns or median_trips < 2:
            continue
        median_return = statistics.median(returns)
        median_drawdown = statistics.median(drawdowns)
        positive = sum(value > 0 for value in returns)
        score = (
            median_return
            - 0.55 * median_drawdown
            + 0.006 * min(median_trips, 100)
            + 0.02 * (positive - len(returns) / 2.0)
            + 0.15 * min(returns)
        )
        scores.append(
            GridScore(
                params=params,
                score=score,
                median_return_pct=median_return,
                median_drawdown_pct=median_drawdown,
                worst_return_pct=min(returns),
                positive=positive,
                windows=len(returns),
                median_round_trips=median_trips,
            )
        )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores


def summarize_paths(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    one_x = [
        row for row in rows if float(row["leverage"]) == 1.0 and row["sample"] == "test"
    ]
    result = []
    for sign in ("positive", "negative", "zero"):
        items = [row for row in one_x if row["gex_sign"] == sign]
        if not items:
            continue
        result.append(
            {
                "gex_sign": sign,
                "count": len(items),
                "underlyings": sorted({str(item["underlying"]) for item in items}),
                "median_abs_price_return_pct": statistics.median(abs(float(item["price_return_pct"])) for item in items),
                "median_path_variation_pct": statistics.median(float(item["path_variation_pct"]) for item in items),
                "median_path_efficiency_ratio": statistics.median(float(item["path_efficiency_ratio"]) for item in items),
            }
        )
    return result


def summarize_strategy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for sample in ("train", "test"):
        for leverage in LEVERAGES:
            for sign in ("all", "positive", "negative", "zero"):
                items = [
                    row
                    for row in rows
                    if row["sample"] == sample
                    and float(row["leverage"]) == leverage
                    and (sign == "all" or row["gex_sign"] == sign)
                ]
                if not items:
                    continue
                returns = [float(item["strategy_return_pct"]) for item in items]
                result.append(
                    {
                        "sample": sample,
                        "leverage": leverage,
                        "gex_sign": sign,
                        "count": len(items),
                        "positive": sum(value > 0 for value in returns),
                        "median_return_pct": statistics.median(returns),
                        "worst_return_pct": min(returns),
                        "median_drawdown_pct": statistics.median(float(item["max_drawdown_pct"]) for item in items),
                        "median_round_trips": statistics.median(float(item["round_trips"]) for item in items),
                        "median_max_abs_net_exposure_pct": statistics.median(
                            float(item["max_abs_net_exposure_pct"]) for item in items
                        ),
                        "liquidations": sum(bool(item["liquidated"]) for item in items),
                    }
                )
    return result


def score_payload(item: GridScore) -> dict[str, Any]:
    return {
        "params": asdict(item.params),
        **{key: value for key, value in asdict(item).items() if key != "params"},
    }


def markdown_report(payload: dict[str, Any]) -> str:
    config = payload["config"]
    selected = config["selectedGridParameters"]
    top = payload["candidateScores"][0]
    lines = [
        "# GEX、Delta 中性与杠杆：点时先行实验",
        "",
        "> 只读公共数据研究；没有读取账户、启动服务或发送订单。",
        "",
        "## 先区分两种策略",
        "",
        "1. 同时持有现货/永续多空，只能消掉一阶 Delta；线性合约的 Gamma 仍为零。这是库存/网格策略，不是真正的多 Gamma。",
        "2. 买入期权取得正 Gamma，再用现货或永续动态把 Delta 拉回零，才是经典 Delta 中性做多波动；其收益要覆盖 Theta、期权价差和反复对冲成本。",
        "",
        "本实验只检验第一种：GEX 符号能否解释未来六小时路径，并能否改善双账本聚合。当前快照没有逐期权点时买卖价、IV、Theta 和可执行对冲成交，不能诚实回测第二种。",
        "",
        "## 相关文献",
        "",
        "- [Black and Scholes (1973), The Pricing of Options and Corporate Liabilities](https://doi.org/10.1086/260062)：期权定价和动态复制的基础。",
        "- [Leland (1985), Option Pricing and Replication with Transactions Costs](https://doi.org/10.1111/j.1540-6261.1985.tb02383.x)：说明连续 Delta 对冲在交易成本下不能照搬无摩擦结论。",
        "- [Option Gamma and Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4256259)：市场 Gamma 与标的收益关系的实证参考，不是可直接执行的实时策略。",
        "- 再平衡收益和做市库存风险文献列于双账本聚合报告；它们解释了线性多空网格与期权多 Gamma 的差别。",
        "",
        "## 点时规则",
        "",
        f"- BTC、ETH、SOL 原始 GEX 事件数：{', '.join(f'{key} {value}' for key, value in payload['eventCounts'].items())}。",
        f"- 为避免重叠，选取的六小时窗口：{', '.join(f'{key} {value}' for key, value in payload['selectedWindowCounts'].items())}。",
        f"- 每个标的按时间前后切分：训练 {payload['sampleWindowCounts']['train']} 个窗口，样本外测试 {payload['sampleWindowCounts']['test']} 个窗口。",
        "- 每个窗口第一根 5m K 线严格晚于 GEX 源时间；同一标的不使用重叠窗口。",
        "- GEX 的 Call 正/Put 负符号是假设的做市商仓位方向，不是交易所公布的真实 dealer inventory。",
        "",
        "## 样本外 GEX 符号后的六小时路径",
        "",
        "| GEX | 窗口 | 中位绝对位移 | 中位累计变动 | 中位路径效率 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["pathSummary"]:
        lines.append(
            f"| {item['gex_sign']} | {item['count']} | {item['median_abs_price_return_pct']:.4f}% | "
            f"{item['median_path_variation_pct']:.4f}% | {item['median_path_efficiency_ratio']:.4f} |"
        )
    lines.extend(
        [
            "",
            "路径效率越低代表累计波动更多地来回抵消；越高代表更接近单边位移。",
            "",
            "## GEX 条件下的双账本聚合",
            "",
            f"只用前半段窗口选择出的参数：层距 {selected['step_bps']:.1f} bps、止盈 "
            f"{selected['take_profit_bps']:.1f} bps、每边 {selected['tranches_per_side']} 层。"
            f"训练中位收益 {top['median_return_pct']:.4f}%，{top['positive']}/{top['windows']} 个窗口为正。",
            "下表只展示后半段样本外窗口。",
            "",
            "| 杠杆 | GEX | 窗口 | 正收益 | 中位收益 | 最差收益 | 中位回撤 | 中位最大净敞口 | 清算 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in payload["strategySummary"]:
        if item["sample"] != "test":
            continue
        lines.append(
            f"| {item['leverage']:g}x | {item['gex_sign']} | {item['count']} | {item['positive']}/{item['count']} | "
            f"{item['median_return_pct']:.4f}% | {item['worst_return_pct']:.4f}% | "
            f"{item['median_drawdown_pct']:.4f}% | {item['median_max_abs_net_exposure_pct']:.2f}% | "
            f"{item['liquidations']} |"
        )
    lines.extend(
        [
            "",
            "## 实际 Delta 中性期权组合的准入条件",
            "",
            "- 组合 Delta 必须按期权乘数、现货/永续数量和币种统一计算，不能用名义金额相等代替。",
            "- 近似损益为 `0.5 × Gamma × (价格变动)^2 + Vega × IV变动 - Theta × 时间 - 交易/对冲成本`。Delta 为零只消掉很小价格变动的一阶项。",
            "- 杠杆应由 Gamma/跳空压力测试决定：同时冲击标的价格、隐含波动率、基差、盘口滑点和保证金，不应从“10x”倒推仓位。",
            "- 美股 GEX 是外部股票期权链对 OKX 股票永续的代理，还叠加交易时段和基差风险；不能把代理 GEX 当成永续自身的 Gamma。",
            "- 在获得足够长的逐期权点时 bid/ask、IV、Greeks、OI 和永续成交数据之前，只能进入研究或仿真，不能据此启用杠杆实盘。",
        ]
    )
    return "\n".join(lines) + "\n"


def wall_strike(value: Any) -> float:
    return float(value.get("strike") or 0.0) if isinstance(value, dict) else 0.0


def parse_iso_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


if __name__ == "__main__":
    raise SystemExit(main())
