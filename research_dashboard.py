from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime as _DateTime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from aggressive_sector_plan import build_sector_plan, load_playbook


PROJECT_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = PROJECT_ROOT / "data_lake" / "manifest.json"
PREREGISTRY_PATH = PROJECT_ROOT / "config" / "research_preregistrations.json"
FORWARD_STOCK_REGISTRY_PATH = PROJECT_ROOT / "config" / "qqq_pure_stock_microstructure_forward_preregistration.json"
QQQ_SUMMARY_PATH = PROJECT_ROOT / "reports" / "qqq_active_enhancement" / "qqq-pit-20260808-v5" / "summary.json"
MEAN_REVERSION_SUMMARY_PATH = PROJECT_ROOT / "reports" / "us_equity_mean_reversion" / "mr-2016-2026-v1" / "summary.json"
MONTE_CARLO_SUMMARY_PATH = PROJECT_ROOT / "reports" / "qqq_pure_stock_monte_carlo" / "pure-stock-mc-20260811-v1" / "summary.json"
SNAPSHOT_ROOT = PROJECT_ROOT / "data_lake" / "snapshots"
WS_ROOT = PROJECT_ROOT / "data" / "microstructure_ws"
PRICE_ROOT = PROJECT_ROOT / "data" / "qqq_active_enhancement" / "prices"
SEC_ROOT = PROJECT_ROOT / "data" / "qqq_active_enhancement" / "sec"
TRADFI_ROOT = PROJECT_ROOT / "data" / "tradfi_intraday"
OPTIONS_ROOT = PROJECT_ROOT / "data" / "options"

_CACHE: dict[str, Any] = {"expires": 0.0, "payload": None}
_FORWARD_BASELINE: dict[tuple[str, str], int] = {}
_CACHE_LOCK = Lock()
_MANUAL_SECTOR_CACHE: dict[str, Any] = {"signature": None, "payload": None}
_MANUAL_SECTOR_LOCK = Lock()
CACHE_SECONDS = 30.0


class datetime(_DateTime):
    """Patchable datetime shim for deterministic dashboard tests."""

    pass


STRATEGY_CATALOG = [
    {
        "key": "qqq_active_enhancement",
        "name": "QQQ 月频主动增强",
        "family": "美股多因子",
        "market": "QQQ + 12只主动腿",
        "cadence": "月频",
        "stage": "forward",
        "status": "forward_observation_only",
        "finding": "唯一较有希望的历史结果；验证期仍为负，尚未形成独立前向结论。",
    },
    {
        "key": "qqq_exit_overlay",
        "name": "QQQ 主动腿退出覆盖",
        "family": "退出与风险控制",
        "market": "QQQ 主动腿",
        "cadence": "5分钟 / 月频",
        "stage": "collecting",
        "status": "preregistered_collecting",
        "finding": "月持有、固定止盈、追踪止盈与20日趋势退出正在前向观察。",
    },
    {
        "key": "stock_microstructure_reduction",
        "name": "29股微观结构减仓",
        "family": "OI / premium / 订单流 / 深度",
        "market": "29只美股合约",
        "cadence": "30分钟",
        "stage": "data_only",
        "status": "collecting_no_rule",
        "finding": "数据层已冻结；减仓公式尚未登记，不能回灌旧蒙特卡洛。",
    },
    {
        "key": "pure_stock_monte_carlo",
        "name": "纯股票因子蒙特卡洛",
        "family": "风险压力测试",
        "market": "29只美股",
        "cadence": "月频路径",
        "stage": "development",
        "status": "development_only",
        "finding": "4,000条同步月度路径；输入历史已检查，不是新验证。",
    },
    {
        "key": "us_equity_mean_reversion",
        "name": "美股均值回归组合",
        "family": "横截面 / 残差 / 配对",
        "market": "26只美股",
        "cadence": "日频",
        "stage": "rejected",
        "status": "failed_validation_research_only",
        "finding": "三个固定组合均未通过训练门槛；高杠杆放大亏损。",
    },
    {
        "key": "alt_negative_funding",
        "name": "负资金费率反转 V1-V4",
        "family": "资金费率事件",
        "market": "主流币与微型山寨币",
        "cadence": "8小时决策 / 5分钟执行",
        "stage": "collecting",
        "status": "preregistered_collecting",
        "finding": "四个隔离版本只接受冻结边界后的新资金费率事件。",
    },
    {
        "key": "spcx_momentum",
        "name": "SPCX 多周期动量",
        "family": "趋势",
        "market": "SPCX-USDT-SWAP",
        "cadence": "1小时",
        "stage": "collecting",
        "status": "preregistered_collecting",
        "finding": "6/12/24/48小时投票模型，等待足够前向天数与信号切换。",
    },
    {
        "key": "qqq_event_gate",
        "name": "QQQ 宏观事件突破/反转",
        "family": "事件驱动",
        "market": "QQQ-USDT-SWAP",
        "cadence": "5分钟",
        "stage": "collecting",
        "status": "preregistered_collecting",
        "finding": "CPI、NFP、PCE、GDP、FOMC事件样本仍不足。",
    },
    {
        "key": "generic_walk_forward",
        "name": "通用趋势、突破与均值回归",
        "family": "TSM / EMA / MACD / Donchian / RSI",
        "market": "OKX 多合约",
        "cadence": "5分钟至1小时",
        "stage": "rejected",
        "status": "research_only",
        "finding": "旧窗口未产生跨主/确认报告稳定通过的候选。",
    },
    {
        "key": "grid_gex_aggregation",
        "name": "网格、聚合与 GEX",
        "family": "再平衡 / 库存风险",
        "market": "BTC、ETH、半导体合约",
        "cadence": "分钟至6小时",
        "stage": "rejected",
        "status": "research_only",
        "finding": "分层、翻转、双账本、GEX风控与库存退出均未通过。",
    },
    {
        "key": "orderflow_maker_factors",
        "name": "订单流、ML 与做市",
        "family": "微观结构",
        "market": "BTC / ETH",
        "cadence": "逐事件 / 快照",
        "stage": "rejected",
        "status": "research_only",
        "finding": "RR、概率模型、46因子和VWAP做市未通过成本与验证门禁。",
    },
    {
        "key": "options_hedging",
        "name": "期权与对冲策略",
        "family": "波动率 / GEX / Delta",
        "market": "BTC / ETH 期权",
        "cadence": "小时至到期",
        "stage": "rejected",
        "status": "research_only",
        "finding": "跨式、宽跨、IV/RV、尾翼与Delta对冲均不足以部署。",
    },
    {
        "key": "tradfi_intraday",
        "name": "美股日内因子与 QQQ 日内化",
        "family": "日内执行",
        "market": "半导体 / QQQ",
        "cadence": "5分钟 / 日频",
        "stage": "rejected",
        "status": "research_only",
        "finding": "基础和压力成本均未稳定通过，日内平仓版本已停止。",
    },
]


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected an object in {path}")
    return payload


def build_research_overview(*, force: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    if not force and _CACHE["payload"] is not None and now < float(_CACHE["expires"]):
        return _CACHE["payload"]

    with _CACHE_LOCK:
        # Several browser tabs or proxy retries can arrive during the first
        # build. Recheck after waiting so only one request reads the lake.
        now = time.monotonic()
        if not force and _CACHE["payload"] is not None and now < float(_CACHE["expires"]):
            return _CACHE["payload"]

        manifest = read_json(MANIFEST_PATH)
        preregistry = read_json(PREREGISTRY_PATH)
        forward_registry = read_json(FORWARD_STOCK_REGISTRY_PATH)
        qqq = read_json(QQQ_SUMMARY_PATH)
        mean_reversion = read_json(MEAN_REVERSION_SUMMARY_PATH)
        monte_carlo = read_json(MONTE_CARLO_SUMMARY_PATH)
        forward = forward_stock_status(manifest, forward_registry)

        payload = {
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "classification": "read_only_research_inventory",
            "data": data_inventory(manifest, forward),
            "strategies": strategy_inventory(preregistry),
            "samples": sample_inventory(qqq, mean_reversion, monte_carlo, forward),
            "backtests": backtest_inventory(qqq, mean_reversion),
            "monteCarlo": monte_carlo_inventory(qqq, monte_carlo),
            "manualSectorPlan": cached_manual_sector_inventory(force=force),
            "forward": forward,
            "rules": {
                "selection": "training_only",
                "defaultSplit": "chronological_50_25_25",
                "costs": "gross_base_and_stress",
                "promotion": "historical_research_to_forward_observation_to_separate_explicit_live_approval",
                "historyWarning": "2026-06-18_and_later_has_been_repeatedly_inspected",
            },
        }
        _CACHE["payload"] = payload
        _CACHE["expires"] = time.monotonic() + CACHE_SECONDS
        return payload


def cached_manual_sector_inventory(*, force: bool = False) -> dict[str, Any]:
    signature = tuple(
        (path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
        for path in (MANIFEST_PATH, PROJECT_ROOT / "config" / "aggressive_sector_playbook.json")
    )
    if not force and _MANUAL_SECTOR_CACHE["payload"] is not None and signature == _MANUAL_SECTOR_CACHE["signature"]:
        return _MANUAL_SECTOR_CACHE["payload"]

    with _MANUAL_SECTOR_LOCK:
        if not force and _MANUAL_SECTOR_CACHE["payload"] is not None and signature == _MANUAL_SECTOR_CACHE["signature"]:
            return _MANUAL_SECTOR_CACHE["payload"]
        payload = manual_sector_inventory()
        _MANUAL_SECTOR_CACHE["signature"] = signature
        _MANUAL_SECTOR_CACHE["payload"] = payload
        return payload


def manual_sector_inventory() -> dict[str, Any]:
    """Expose the frozen subjective playbook and lake-derived references only."""

    playbook = load_playbook()
    data = playbook["data"]
    risk = playbook["risk"]
    execution = playbook["execution"]
    sectors: list[dict[str, Any]] = []
    for key, config in playbook["sectors"].items():
        plan = build_sector_plan(
            sector=key,
            direction="long",
            equity=1,
            leverage=risk["defaultLeverage"],
            playbook=playbook,
        )
        references = {
            item["instId"]: {
                "status": item.get("status"),
                "reason": item.get("reason"),
                "atr": item.get("atr"),
                "atr14Pct": item.get("atr14Pct"),
                "atrAsOf": item.get("atrAsOf"),
                "referencePrice": item.get("referencePrice"),
                "stopDistancePct": item.get("stopDistancePct"),
            }
            for item in plan.get("items", [])
        }
        sectors.append(
            {
                "key": key,
                "label": config.get("label", key),
                "thesis": config.get("thesis", ""),
                "atrMultiplier": config.get("atrMultiplier"),
                "stopFloorPct": config.get("stopFloorPct"),
                "stopCapPct": config.get("stopCapPct"),
                "legs": [
                    {
                        "instId": str(leg.get("instId", "")),
                        "riskWeight": leg.get("riskWeight"),
                        "reference": references.get(str(leg.get("instId", "")), {}),
                    }
                    for leg in config.get("legs", [])
                ],
            }
        )
    return {
        "playbookId": plan.get("playbookId", ""),
        "mode": playbook.get("mode"),
        "status": playbook.get("status"),
        "purpose": playbook.get("purpose"),
        "data": {
            "timeframe": data.get("timeframe"),
            "sessionTimezone": data.get("sessionTimezone"),
            "sessionOpen": data.get("sessionOpen"),
            "sessionClose": data.get("sessionClose"),
            "minSessionBars": data.get("minSessionBars"),
            "atrWindow": data.get("atrWindow"),
        },
        "risk": {
            "defaultRiskPct": risk.get("defaultRiskPct"),
            "costBufferPct": risk.get("costBufferPct"),
            "defaultLeverage": risk.get("defaultLeverage"),
            "minLeverage": risk.get("minLeverage"),
            "maxLeverage": risk.get("maxLeverage"),
            "maxMarginPct": risk.get("maxMarginPct"),
            "maxLegs": risk.get("maxLegs"),
            "takeProfit1R": risk.get("takeProfit1R"),
            "takeProfit2R": risk.get("takeProfit2R"),
            "takeProfit1ClosePct": risk.get("takeProfit1ClosePct"),
        },
        "execution": {
            "minMinutesAfterOpen": execution.get("minMinutesAfterOpen"),
            "minMinutesBeforeClose": execution.get("minMinutesBeforeClose"),
            "openingRangeMinutes": execution.get("openingRangeMinutes"),
            "maxEntryDeviationBps": execution.get("maxEntryDeviationBps"),
            "requireVwapConfirmation": execution.get("requireVwapConfirmation"),
            "requireOpeningRangeConfirmation": execution.get("requireOpeningRangeConfirmation"),
            "flatBeforeUsClose": execution.get("flatBeforeUsClose"),
            "allowAveragingDown": execution.get("allowAveragingDown"),
            "allowStopReentry": execution.get("allowStopReentry"),
            "allowOvernight": execution.get("allowOvernight"),
        },
        "sectors": sectors,
        "directions": ["long", "short"],
        "paperOrLiveAuthorized": False,
    }


def data_inventory(manifest: dict[str, Any], forward: dict[str, Any]) -> dict[str, Any]:
    candle_coverage = manifest.get("coverage", {}).get("candles", {})
    funding_coverage = manifest.get("coverage", {}).get("funding", {})
    candle_shards = [item for shards in candle_coverage.values() for item in shards]
    funding_shards = [item for shards in funding_coverage.values() for item in shards]
    cadence: dict[str, dict[str, Any]] = {}
    for key, shards in candle_coverage.items():
        inst_id, timeframe = key.rsplit("/", 1)
        item = cadence.setdefault(timeframe, {"timeframe": timeframe, "instruments": set(), "series": 0, "rows": 0})
        item["instruments"].add(inst_id)
        item["series"] += 1
        item["rows"] += sum(int(shard.get("rows", 0)) for shard in shards)
    cadence_rows = [
        {**item, "instruments": len(item["instruments"])}
        for _, item in sorted(cadence.items(), key=lambda pair: timeframe_seconds(pair[0]))
    ]
    sources = manifest.get("sources", {})
    snapshot_rows = sum(int(item.get("rows", 0)) for item in sources.get("snapshots", []))
    ws_rows = sum(int(item.get("rows", 0)) for item in sources.get("microstructure_ws", []))
    pools = [
        pool("candles", "OKX K线", sum(int(x.get("rows", 0)) for x in candle_shards), "根", len(candle_coverage), "合约/周期序列", last_of(candle_shards)),
        pool("funding", "资金费率", sum(int(x.get("rows", 0)) for x in funding_shards), "条", len(funding_coverage), "合约", last_of(funding_shards)),
        pool("snapshots", "30分钟微观结构", snapshot_rows, "条", int(manifest.get("stats", {}).get("snapshotInstruments", 0)), "合约", forward.get("lastCapturedAt")),
        pool("websocket", "WebSocket逐事件", ws_rows, "行", len(sources.get("microstructure_ws", [])), "合约", websocket_last_capture()),
        pool("equity", "美股价格", file_count(PRICE_ROOT, "*.csv") + file_count(TRADFI_ROOT, "*.csv"), "文件", file_count(PRICE_ROOT, "*.csv"), "长期日线", file_mtime_latest([PRICE_ROOT, TRADFI_ROOT])),
        pool("sec", "SEC点时财务", file_count(SEC_ROOT, "*.json"), "文件", file_count(SEC_ROOT, "*companyfacts.json"), "Company Facts", file_mtime_latest([SEC_ROOT])),
        pool("options", "期权历史与盘口", file_count(OPTIONS_ROOT, "*.json"), "文件", directory_size(OPTIONS_ROOT), "字节", file_mtime_latest([OPTIONS_ROOT])),
        pool("events", "宏观事件", int(manifest.get("stats", {}).get("eventRows", 0)), "条", int(manifest.get("stats", {}).get("eventFiles", 0)), "文件", manifest.get("generatedAt")),
    ]
    return {
        "manifestGeneratedAt": manifest.get("generatedAt"),
        "candleInstruments": len({key.rsplit("/", 1)[0] for key in candle_coverage}),
        "candleSeries": len(candle_coverage),
        "candleRows": sum(int(x.get("rows", 0)) for x in candle_shards),
        "fundingRows": sum(int(x.get("rows", 0)) for x in funding_shards),
        "snapshotRowsAsOfManifest": snapshot_rows,
        "websocketRows": ws_rows,
        "cadence": cadence_rows,
        "pools": pools,
    }


def pool(key: str, name: str, count: int, unit: str, secondary: int, secondary_unit: str, latest: Any) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "count": count,
        "unit": unit,
        "secondary": secondary,
        "secondaryUnit": secondary_unit,
        "latest": latest,
    }


def strategy_inventory(preregistry: dict[str, Any]) -> dict[str, Any]:
    models = preregistry.get("models", [])
    stage_counts = Counter(item["stage"] for item in STRATEGY_CATALOG)
    return {
        "catalog": STRATEGY_CATALOG,
        "counts": dict(stage_counts),
        "total": len(STRATEGY_CATALOG),
        "registeredForwardModels": len(models) + 6,
        "paperOrLiveAuthorizedByResearch": sum(bool(item.get("paperOrLiveAuthorized")) for item in models),
    }


def sample_inventory(
    qqq: dict[str, Any], mean_reversion: dict[str, Any], monte_carlo: dict[str, Any], forward: dict[str, Any]
) -> list[dict[str, Any]]:
    qqq_segments = qqq["results"]["monthly"]["base"]["segments"]
    mr_split = mean_reversion["study"]["split"]
    mc_split = monte_carlo["sourceSplitDiagnostics"]
    return [
        {
            "key": "qqq_active",
            "name": "QQQ 月频主动增强",
            "method": "时间顺序切分；训练选择、验证诊断、测试只读",
            "classification": "历史代理，已锁模前向观察",
            "segments": [segment_from_metric(key, qqq_segments[key], "days") for key in ("train", "validation", "test")],
        },
        {
            "key": "mean_reversion",
            "name": "美股均值回归",
            "method": "252日预热后固定50/25/25；每段从1000美元空仓开始",
            "classification": "训练门禁失败",
            "segments": [segment_from_metric(key, mr_split[key], "rows") for key in ("train", "validation", "test")],
        },
        {
            "key": "monte_carlo_source",
            "name": "纯股票蒙特卡洛源样本",
            "method": "24个月度片段的12/6/6稳定性诊断；不用于选参",
            "classification": "已检查历史，开发压力测试",
            "segments": [
                {
                    "key": key,
                    "label": split_label(key),
                    "start": mc_split[key]["signalStart"],
                    "end": mc_split[key]["signalEnd"],
                    "rows": mc_split[key]["episodes"],
                    "unit": "月度片段",
                }
                for key in ("train", "validation", "test")
            ],
        },
        {
            "key": "stock_forward",
            "name": "29股微观结构前向样本",
            "method": "冻结边界后只追加；成熟后一次50/25/25切分",
            "classification": "未成熟，禁止提前评估",
            "segments": [
                {"key": "collected", "label": "已采集", "start": forward.get("boundary"), "end": forward.get("lastCapturedAt"), "rows": forward.get("eligibleSnapshots", 0), "unit": "快照"},
                {"key": "months", "label": "完整月", "start": None, "end": None, "rows": forward.get("completeCalendarMonths", 0), "unit": "/ 12月"},
                {"key": "events", "label": "减仓事件", "start": None, "end": None, "rows": forward.get("reductionEvents", 0), "unit": "/ 100次"},
            ],
        },
    ]


def segment_from_metric(key: str, metric: dict[str, Any], row_key: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": split_label(key),
        "start": metric.get("start"),
        "end": metric.get("end"),
        "rows": metric.get(row_key),
        "unit": "交易日",
    }


def backtest_inventory(qqq: dict[str, Any], mean_reversion: dict[str, Any]) -> dict[str, Any]:
    qqq_rows = []
    for cost in ("base", "stress"):
        for split in ("train", "validation", "test"):
            row = qqq["results"]["monthly"][cost]["segments"][split]
            qqq_rows.append(
                {
                    "split": split,
                    "costProfile": cost,
                    "annualizedActiveReturnPct": row.get("annualizedActiveReturnPct"),
                    "informationRatio": row.get("informationRatio"),
                    "portfolioAnnualReturnPct": row.get("portfolioAnnualReturnPct"),
                    "benchmarkAnnualReturnPct": row.get("benchmarkAnnualReturnPct"),
                    "maxDrawdownPct": row.get("portfolioMaxDrawdownPct"),
                    "averageGrossPct": row.get("averageGrossPct"),
                }
            )
    mr_rows = []
    keep = {
        "strategy",
        "split",
        "leverage",
        "cost_profile",
        "terminal_equity",
        "total_return_pct",
        "annualized_return_pct",
        "sharpe",
        "profit_factor",
        "max_drawdown_pct",
        "turnover_usd",
        "trade_orders",
        "liquidated",
        "ruined",
    }
    for item in mean_reversion.get("results", []):
        mr_rows.append({key: value for key, value in item.items() if key in keep})
    return {
        "qqq": {
            "name": "QQQ 月频主动增强",
            "status": qqq.get("decision", {}).get("status"),
            "rows": qqq_rows,
        },
        "meanReversion": {
            "name": "美股均值回归",
            "status": mean_reversion.get("selection", {}).get("status"),
            "rows": mr_rows,
        },
    }


def monte_carlo_inventory(qqq: dict[str, Any], monte_carlo: dict[str, Any]) -> dict[str, Any]:
    study = monte_carlo["study"]
    scenarios = []
    for item in monte_carlo.get("scenarios", []):
        mc = item["monteCarlo"]
        scenarios.append(
            {
                "exitVariant": item["exitVariant"],
                "leverage": item["leverage"],
                "costProfile": item["costProfile"],
                "perSideBps": item["perSideBps"],
                "actualGross": mc.get("meanRebalanceGrossMultiple"),
                "netReturnPct": mc.get("netReturnPct"),
                "maxDrawdownPct": mc.get("maxDrawdownPct"),
                "ruinProbabilityPct": mc.get("ruinProbabilityPct"),
                "liquidationProbabilityPct": mc.get("liquidationProbabilityPct"),
                "drawdown50ProbabilityPct": mc.get("drawdownAtLeast50ProbabilityPct"),
                "drawdown90ProbabilityPct": mc.get("drawdownAtLeast90ProbabilityPct"),
                "meanTurnoverUsdt": mc.get("meanTurnoverUsdt"),
                "meanFundingPnlUsdt": mc.get("meanFundingPnlUsdt"),
            }
        )
    return {
        "classification": monte_carlo.get("decision", {}).get("classification"),
        "newValidation": monte_carlo.get("decision", {}).get("newValidation"),
        "paperOrLiveAuthorized": monte_carlo.get("decision", {}).get("paperOrLiveAuthorized"),
        "method": study["monteCarlo"].get("method"),
        "paths": study["monteCarlo"].get("paths"),
        "horizonMonths": study["monteCarlo"].get("horizonMonths"),
        "seed": study["monteCarlo"].get("seed"),
        "source": monte_carlo.get("data"),
        "sourceSplits": monte_carlo.get("sourceSplitDiagnostics"),
        "scenarios": scenarios,
        "qqqBootstrap": qqq["results"]["monthly"]["base"].get("testActiveBootstrap"),
    }


def forward_stock_status(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    study = registry["study"]
    boundary = parse_time(study["forwardBoundary"])
    instruments = study["universe"]["instruments"]
    model_id = study["modelId"]
    boundary_day = boundary.strftime("%Y%m%d")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    manifest_time = parse_time(manifest["generatedAt"])
    source_by_inst = {item["inst"]: item for item in manifest.get("sources", {}).get("snapshots", [])}
    eligible_as_of_manifest = 0
    live_rows: list[dict[str, Any]] = []
    for inst_id in instruments:
        safe_id = inst_id.lower().replace("-", "_")
        directory = SNAPSHOT_ROOT / safe_id
        if not directory.exists():
            continue
        source = source_by_inst.get(safe_id, {})
        files = list(source.get("files") or [])
        if not files:
            files = [path.name for path in sorted(directory.glob("*.jsonl"))]
        baseline_key = (model_id, safe_id)
        if baseline_key not in _FORWARD_BASELINE:
            excluded = 0
            for filename in files:
                path = directory / filename
                if not path.exists():
                    continue
                if path.stem < boundary_day:
                    excluded += line_count(path)
                    continue
                if path.stem == boundary_day:
                    excluded += sum(
                        1
                        for row in jsonl_rows(path)
                        if parse_time(row.get("capturedAt")) <= manifest_time
                        and (
                            parse_time(row.get("capturedAt")) <= boundary
                            or (row.get("research") or {}).get("modelId") != model_id
                        )
                    )
            _FORWARD_BASELINE[baseline_key] = excluded
        eligible_as_of_manifest += sum(
            1
            for filename in files
            for row in jsonl_rows(directory / filename)
            if parse_time(row.get("capturedAt")) > boundary
            and parse_time(row.get("capturedAt")) <= manifest_time
            and (row.get("research") or {}).get("modelId") == model_id
        )

        current_path = directory / f"{today}.jsonl"
        if current_path.exists():
            for row in jsonl_rows(current_path):
                captured = parse_time(row.get("capturedAt"))
                if captured <= boundary or (row.get("research") or {}).get("modelId") != model_id:
                    continue
                if captured > manifest_time:
                    live_rows.append(row)
    today_rows = []
    for inst_id in instruments:
        path = SNAPSHOT_ROOT / inst_id.lower().replace("-", "_") / f"{today}.jsonl"
        if not path.exists():
            continue
        for row in jsonl_rows(path):
            if parse_time(row.get("capturedAt")) > boundary and (row.get("research") or {}).get("modelId") == model_id:
                today_rows.append(row)
    latest_rows: dict[str, dict[str, Any]] = {}
    for row in today_rows:
        latest_rows[row.get("instId", "")] = row
    last_capture = max((row.get("capturedAt") for row in today_rows), default=None)
    complete_today = sum(bool(row.get("ok") and row.get("dataComplete")) for row in today_rows)
    complete_latest = sum(bool(row.get("ok") and row.get("dataComplete")) for row in latest_rows.values())
    eligible_total = eligible_as_of_manifest + len(live_rows)
    maturity = study["maturity"]
    return {
        "modelId": model_id,
        "status": study.get("status"),
        "boundary": study["forwardBoundary"],
        "instruments": len(instruments),
        "eligibleSnapshots": eligible_total,
        "todaySnapshots": len(today_rows),
        "todayCompleteSnapshots": complete_today,
        "latestCompleteInstruments": complete_latest,
        "lastCapturedAt": last_capture,
        "completeCalendarMonths": 0,
        "minimumCompleteCalendarMonths": maturity["minimumCompleteCalendarMonths"],
        "reductionEvents": 0,
        "minimumReductionEvents": maturity["minimumIndependentReductionEvents"],
        "candidateRuleStatus": study["candidateReductionMapping"]["status"],
        "paperOrLiveAuthorized": study.get("paperOrLiveAuthorized", False),
    }


def count_snapshot_rows(directory: Path, *, predicate: Any, end: datetime) -> int:
    count = 0
    if not directory.exists():
        return count
    for path in sorted(directory.glob("*.jsonl")):
        for row in jsonl_rows(path):
            captured = parse_time(row.get("capturedAt"))
            if captured <= end and predicate(row):
                count += 1
    return count


def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("rb") as handle:
        return sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(1024 * 1024), b""))


def jsonl_rows(path: Path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def parse_time(value: Any) -> datetime:
    if isinstance(value, _DateTime):
        return value.astimezone(timezone.utc)
    text = str(value or "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timeframe_seconds(value: str) -> int:
    number = int("".join(character for character in value if character.isdigit()) or 0)
    if value.lower().endswith("m"):
        return number * 60
    if value.lower().endswith("h"):
        return number * 3600
    return number


def last_of(shards: list[dict[str, Any]]) -> str | None:
    values = [item.get("last") for item in shards if item.get("last")]
    return max(values) if values else None


def file_count(root: Path, pattern: str) -> int:
    return sum(1 for path in root.glob(pattern) if path.is_file()) if root.exists() else 0


def directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.glob("*") if path.is_file()) if root.exists() else 0


def file_mtime_latest(roots: list[Path]) -> str | None:
    mtimes = [path.stat().st_mtime for root in roots if root.exists() for path in root.glob("*") if path.is_file()]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def websocket_last_capture() -> str | None:
    latest: str | None = None
    for directory in WS_ROOT.glob("*") if WS_ROOT.exists() else []:
        files = sorted(directory.glob("*.jsonl"))
        if not files:
            continue
        try:
            with files[-1].open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - 65_536))
                lines = handle.read().splitlines()
                line = lines[-1].decode("utf-8")
            captured = json.loads(line).get("capturedAt")
        except (OSError, json.JSONDecodeError):
            continue
        if captured and (latest is None or captured > latest):
            latest = captured
    return latest


def split_label(key: str) -> str:
    return {"train": "训练", "validation": "验证", "test": "测试"}.get(key, key)
