from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

from backtest.okx_grid_backtest import (
    BAR_MS,
    DATA_DIR,
    Candle,
    GridBacktestConfig,
    fetch_okx_candle_rows,
    parse_okx_candles,
    plain,
    read_candles_csv,
    round_to_tick,
    run_grid_backtest,
    write_candles_csv,
)
from doubao_quant import MlRegimeProfile, latest_ml_regime_profile, profile_to_dict, quant_metadata
from market_selector import (
    MarketCandidate,
    MarketSelectorConfig,
    candidate_to_dict,
    select_candidates,
    selector_config_to_dict,
)
from okx_client import OkxApiError, OkxRestClient
from portfolio_allocator import (
    AllocationConfig,
    action_to_dict,
    allocation_to_dict,
    build_rebalance_actions,
    build_target_allocations,
    exposure_to_dict,
    fetch_current_exposures,
)
from portfolio_execution import ExecutionConfig, intent_to_dict, write_execution_bundle
from portfolio_tail_hedge import TailHedgeConfig, build_tail_hedge_plan, write_tail_hedge_outputs
from scoring import ScoreWeights, score_backtest, score_to_dict, weights_to_dict


PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_DIR = PROJECT_ROOT / "reports" / "portfolio"
SCORE_FIELDS = [
    "rank",
    "status",
    "inst_id",
    "score",
    "quote_volume_24h",
    "spread_bps",
    "last",
    "bars",
    "total_return_pct",
    "max_drawdown_pct",
    "profit_factor",
    "fills",
    "win_rate_pct",
    "risk_events",
    "selected_trend_filter",
    "trend_filter_checked",
    "trend_score_delta",
    "baseline_score",
    "baseline_total_return_pct",
    "baseline_max_drawdown_pct",
    "baseline_profit_factor",
    "baseline_risk_events",
    "auto_trend_score",
    "auto_trend_total_return_pct",
    "auto_trend_max_drawdown_pct",
    "auto_trend_profit_factor",
    "auto_trend_risk_events",
    "market_regime_filter",
    "market_regime_signal",
    "market_regime_confidence",
    "market_regime_allowed_sides",
    "market_regime_model_path",
    "ml_score_delta_vs_baseline",
    "ml_return_delta_vs_baseline",
    "ml_drawdown_delta_vs_baseline",
    "ml_risk_event_delta_vs_baseline",
    "pool_window_hours",
    "pool_window_bars",
    "pool_avg_abs_bps",
    "pool_shock_bps",
    "pool_trend_bps",
    "final_equity",
    "error",
]
REBALANCE_FIELDS = [
    "inst_id",
    "action",
    "current_weight_pct",
    "target_weight_pct",
    "delta_weight_pct",
    "current_margin",
    "target_margin",
    "delta_margin",
    "note",
]


@dataclass(slots=True)
class PortfolioBacktestConfig:
    selector: MarketSelectorConfig
    score_weights: ScoreWeights
    allocation: AllocationConfig
    backtest_bar: str = "1m"
    backtest_limit: int = 300
    backtest_pages: int = 3
    pool_window_hours: Decimal = Decimal("5")
    refresh: bool = False
    starting_equity: Decimal = Decimal("100")
    leverage: Decimal = Decimal("7")
    outer_range_bps: Decimal = Decimal("1200")
    grid_bps: Decimal = Decimal("10")
    soft_bps: Decimal = Decimal("35")
    hard_bps: Decimal = Decimal("60")
    max_open_orders_per_side: int = 5
    max_actions_per_bar: int = 12
    adaptive_width_bps: Decimal = Decimal("420")
    adaptive_min_width_bps: Decimal = Decimal("260")
    adaptive_max_width_bps: Decimal = Decimal("1200")
    adaptive_vol_multiplier: Decimal = Decimal("12")
    range_drift_weight_bps: Decimal = Decimal("2500")
    range_drift_max_bps: Decimal = Decimal("250")
    order_margin_pct: Decimal = Decimal("25")
    max_margin_pct: Decimal = Decimal("75")
    maker_fee_bps: Decimal = Decimal("2")
    taker_fee_bps: Decimal = Decimal("5")
    slippage_bps: Decimal = Decimal("2")
    min_tp_bps: Decimal = Decimal("30")
    total_loss_sl_pct: Decimal = Decimal("4")
    total_loss_sl_cap: Decimal = Decimal("0.8")
    position_loss_sl_bps: Decimal = Decimal("700")
    risk_cooldown_bars: int = 1
    regime_filter: str = "off"
    regime_bar: str = "15m"
    regime_short_ma: int = 5
    regime_long_ma: int = 20
    regime_diff_bps: Decimal = Decimal("50")
    regime_confirm_bars: int = 3
    market_regime_filter: str = "auto"
    market_regime_model_path: str = ""
    market_regime_min_confidence: Decimal = Decimal("0.52")
    market_regime_mixed_policy: str = "price_anchor"
    ml_profile: MlRegimeProfile | None = None
    tail_hedge: TailHedgeConfig | None = None
    trend_filter: str = "off"
    trend_lookback: int = 8
    trend_threshold_bps: Decimal = Decimal("70")
    one_way_open: bool = False
    include_account: bool = False
    trading_mode: str = "backtest"


def main() -> int:
    args = parse_args()
    config = config_from_args(args)
    client = public_client_from_env()
    output_dir = run_portfolio_backtest(client, config, args.output_dir)
    print(f"portfolio_report={output_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select hot OKX USDT perpetual swaps and batch-backtest the adaptive grid strategy. Public/read-only APIs only."
    )
    parser.add_argument("--min-quote-volume", "--min_quote_volume", dest="min_quote_volume", default="5000000")
    parser.add_argument("--max-spread-bps", "--max_spread_bps", dest="max_spread_bps", default="20")
    parser.add_argument("--top-n", "--top_n", dest="top_n", type=int, default=20)
    parser.add_argument("--backtest-bar", "--backtest_bar", dest="backtest_bar", default="1m", choices=list(BAR_MS))
    parser.add_argument("--backtest-pages", "--backtest_pages", dest="backtest_pages", type=int, default=3)
    parser.add_argument("--backtest-limit", "--backtest_limit", dest="backtest_limit", type=int, default=300)
    parser.add_argument("--pool-window-hours", default="5", help="Recent trading-pool window used to prewrite adaptive runtime parameters.")
    parser.add_argument("--refresh", action="store_true", help="Fetch fresh candles instead of using local public-data cache.")
    parser.add_argument("--output-dir", default="", help="Optional output dir. Relative paths are under reports/portfolio/.")
    parser.add_argument("--include-account", action="store_true", help="Read private positions for rebalance dry-run. Does not trade.")
    parser.add_argument("--trading-mode", choices=["backtest", "paper", "live"], default="backtest")

    parser.add_argument("--starting-equity", default="100")
    parser.add_argument("--leverage", default="7")
    parser.add_argument("--outer-range-bps", default="1200")
    parser.add_argument("--grid-bps", default="10")
    parser.add_argument("--max-open-orders-per-side", type=int, default=5)
    parser.add_argument("--max-actions-per-bar", type=int, default=12)
    parser.add_argument("--order-margin-pct", default="25")
    parser.add_argument("--max-margin-pct", default="75")
    parser.add_argument("--regime-filter", choices=["off", "ma_cross"], default="off")
    parser.add_argument("--market-regime-filter", choices=["auto", "off", "rules", "rf", "hmm"], default="auto")
    parser.add_argument("--market-regime-model-path", default="")
    parser.add_argument("--market-regime-min-confidence", default="0.52")
    parser.add_argument("--market-regime-mixed-policy", choices=["pause", "price_anchor", "range"], default="price_anchor")
    parser.add_argument("--tail-hedge-mode", choices=["off", "plan", "dynamic"], default="plan")
    parser.add_argument("--tail-hedge-inst-id", default="")
    parser.add_argument("--tail-hedge-ratio", default="0.35")
    parser.add_argument("--tail-hedge-stress-ratio", default="0.70")
    parser.add_argument("--tail-hedge-full-ratio", default="1")
    parser.add_argument("--tail-hedge-trigger-net-exposure-pct", default="120")
    parser.add_argument("--tail-hedge-trigger-shock-bps", default="120")
    parser.add_argument("--tail-hedge-trigger-trend-bps", default="350")
    parser.add_argument("--tail-hedge-trigger-risk-events", type=int, default=8)
    parser.add_argument("--tail-hedge-stress-net-exposure-pct", default="180")
    parser.add_argument("--tail-hedge-stress-shock-bps", default="180")
    parser.add_argument("--tail-hedge-stress-trend-bps", default="550")
    parser.add_argument("--tail-hedge-stress-risk-events", type=int, default=40)
    parser.add_argument("--tail-hedge-full-net-exposure-pct", default="240")
    parser.add_argument("--tail-hedge-full-shock-bps", default="260")
    parser.add_argument("--tail-hedge-full-trend-bps", default="800")
    parser.add_argument("--tail-hedge-full-risk-events", type=int, default=80)
    parser.add_argument("--tail-hedge-min-notional", default="10")
    parser.add_argument("--tail-hedge-max-margin-pct", default="20")
    parser.add_argument("--tail-hedge-stress-max-margin-pct", default="40")
    parser.add_argument("--tail-hedge-full-max-margin-pct", default="100")
    parser.add_argument("--tail-hedge-leverage", default="3")
    parser.add_argument("--tail-hedge-ord-type", choices=["market", "limit"], default="market")
    parser.add_argument("--trend-filter", choices=["off", "auto", "compare"], default="off")
    parser.add_argument("--allow-dual-open", dest="one_way_open", action="store_false")
    parser.add_argument("--one-way-open", dest="one_way_open", action="store_true")
    parser.set_defaults(one_way_open=False)
    parser.add_argument("--target-symbols", type=int, default=6)
    parser.add_argument("--allocation-min-score", default="-999999")
    parser.add_argument("--allocation-min-fills", type=int, default=1)
    parser.add_argument("--allocation-max-risk-events", type=int, default=5)
    parser.add_argument("--max-weight-pct", default="45")
    parser.add_argument("--min-weight-pct", default="5")
    parser.add_argument("--cash-reserve-pct", default="10")
    parser.add_argument("--min-deploy-pct", default="75")
    parser.add_argument("--core-symbols", type=int, default=2)
    parser.add_argument("--core-weight-share-pct", default="70")
    parser.add_argument("--satellite-max-weight-pct", default="12")
    parser.add_argument("--satellite-min-weight-pct", default="3")
    parser.add_argument("--rebalance-threshold-pct", default="1")
    parser.add_argument("--close-missing", dest="close_missing", action="store_true", default=True, help="Dry-run exit actions for current holdings not in target portfolio.")
    parser.add_argument("--no-close-missing", dest="close_missing", action="store_false", help="Ignore current holdings not in target portfolio.")
    return parser.parse_args()


def config_from_args(args: argparse.Namespace) -> PortfolioBacktestConfig:
    market_regime_min_confidence = dec(args.market_regime_min_confidence, Decimal("0.52"))
    ml_profile = latest_ml_regime_profile(
        requested_mode=args.market_regime_filter,
        model_path=args.market_regime_model_path,
        min_confidence=market_regime_min_confidence,
    )
    return PortfolioBacktestConfig(
        selector=MarketSelectorConfig(
            min_quote_volume=dec(args.min_quote_volume),
            max_spread_bps=dec(args.max_spread_bps),
            top_n=args.top_n,
        ),
        score_weights=ScoreWeights(),
        allocation=AllocationConfig(
            max_symbols=args.target_symbols,
            min_score=dec(args.allocation_min_score),
            min_fills=args.allocation_min_fills,
            max_risk_events=args.allocation_max_risk_events,
            max_weight_pct=dec(args.max_weight_pct),
            min_weight_pct=dec(args.min_weight_pct),
            cash_reserve_pct=dec(args.cash_reserve_pct),
            min_deploy_pct=dec(args.min_deploy_pct),
            core_symbols=args.core_symbols,
            core_weight_share_pct=dec(args.core_weight_share_pct),
            satellite_max_weight_pct=dec(args.satellite_max_weight_pct),
            satellite_min_weight_pct=dec(args.satellite_min_weight_pct),
            default_equity=dec(args.starting_equity),
            rebalance_threshold_pct=dec(args.rebalance_threshold_pct),
            close_missing=args.close_missing,
        ),
        backtest_bar=args.backtest_bar,
        backtest_limit=args.backtest_limit,
        backtest_pages=args.backtest_pages,
        pool_window_hours=dec(args.pool_window_hours),
        refresh=args.refresh,
        starting_equity=dec(args.starting_equity),
        leverage=dec(args.leverage),
        outer_range_bps=dec(args.outer_range_bps),
        grid_bps=dec(args.grid_bps),
        max_open_orders_per_side=args.max_open_orders_per_side,
        max_actions_per_bar=args.max_actions_per_bar,
        order_margin_pct=dec(args.order_margin_pct),
        max_margin_pct=dec(args.max_margin_pct),
        regime_filter=args.regime_filter,
        market_regime_filter=args.market_regime_filter,
        market_regime_model_path=args.market_regime_model_path,
        market_regime_min_confidence=market_regime_min_confidence,
        market_regime_mixed_policy=args.market_regime_mixed_policy,
        ml_profile=ml_profile,
        tail_hedge=TailHedgeConfig(
            mode=args.tail_hedge_mode,
            hedge_inst_id=args.tail_hedge_inst_id,
            hedge_ratio=dec(args.tail_hedge_ratio),
            stress_hedge_ratio=dec(args.tail_hedge_stress_ratio),
            full_hedge_ratio=dec(args.tail_hedge_full_ratio),
            trigger_net_exposure_pct=dec(args.tail_hedge_trigger_net_exposure_pct),
            trigger_shock_bps=dec(args.tail_hedge_trigger_shock_bps),
            trigger_trend_bps=dec(args.tail_hedge_trigger_trend_bps),
            trigger_risk_events=args.tail_hedge_trigger_risk_events,
            stress_net_exposure_pct=dec(args.tail_hedge_stress_net_exposure_pct),
            stress_shock_bps=dec(args.tail_hedge_stress_shock_bps),
            stress_trend_bps=dec(args.tail_hedge_stress_trend_bps),
            stress_risk_events=args.tail_hedge_stress_risk_events,
            full_hedge_net_exposure_pct=dec(args.tail_hedge_full_net_exposure_pct),
            full_hedge_shock_bps=dec(args.tail_hedge_full_shock_bps),
            full_hedge_trend_bps=dec(args.tail_hedge_full_trend_bps),
            full_hedge_risk_events=args.tail_hedge_full_risk_events,
            min_hedge_notional=dec(args.tail_hedge_min_notional),
            max_hedge_margin_pct=dec(args.tail_hedge_max_margin_pct),
            stress_hedge_max_margin_pct=dec(args.tail_hedge_stress_max_margin_pct),
            full_hedge_max_margin_pct=dec(args.tail_hedge_full_max_margin_pct),
            hedge_leverage=dec(args.tail_hedge_leverage),
            ord_type=args.tail_hedge_ord_type,
        ),
        trend_filter=args.trend_filter,
        one_way_open=args.one_way_open,
        include_account=args.include_account,
        trading_mode=args.trading_mode,
    )


def public_client_from_env() -> OkxRestClient:
    return OkxRestClient(
        base_url=os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/"),
        proxy_url=os.getenv("OKX_PROXY", ""),
        user_agent=os.getenv("OKX_USER_AGENT", "curl/8.10.1"),
    )


def private_client_from_env() -> OkxRestClient:
    from okx_client import load_env

    load_env()
    return OkxRestClient.from_env()


def run_portfolio_backtest(
    client: OkxRestClient,
    config: PortfolioBacktestConfig,
    output_dir_arg: str = "",
) -> Path:
    candidates = select_candidates(client, config.selector)
    rows = [backtest_candidate(client, candidate, config) for candidate in candidates]
    rows = rank_rows(rows)
    current_exposures = {}
    if config.include_account:
        current_exposures = fetch_current_exposures(private_client_from_env(), default_leverage=config.leverage)
    targets = build_target_allocations(
        rows,
        candidates,
        config.allocation,
        equity=config.starting_equity,
        leverage=config.leverage,
    )
    actions = build_rebalance_actions(targets, current_exposures, config.allocation)
    return write_portfolio_outputs(candidates, rows, targets, current_exposures, actions, config, output_dir_arg)


def backtest_candidate(
    client: OkxRestClient,
    candidate: MarketCandidate,
    config: PortfolioBacktestConfig,
) -> dict[str, Any]:
    base_row = candidate_row(candidate)
    try:
        candles = load_or_fetch_candidate_candles(client, candidate.inst_id, config)
        min_candles = minimum_backtest_candles(config)
        if len(candles) < min_candles:
            return {
                **base_row,
                "status": "skipped",
                "error": f"not enough candles: {len(candles)} < {min_candles}",
            }
        selected, baseline, auto_trend = select_trend_backtest(candidate, candles, config)
        market_signal = market_regime_signal_for_candidate(candles, config)
        result = selected["result"]
        score = selected["score"]
        pool_metrics = pool_window_metrics(candles, config)
        return {
            **base_row,
            "status": "ok",
            "score": score.score,
            "score_breakdown": score_to_dict(score),
            "bars": result.bars,
            "total_return_pct": result.total_return_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "profit_factor": result.profit_factor,
            "fills": result.fills,
            "win_rate_pct": result.win_rate_pct,
            "risk_events": result.risk_events,
            "selected_trend_filter": selected["trend_filter"],
            "trend_filter_checked": True,
            "trend_score_delta": auto_trend["score"].score - baseline["score"].score,
            "baseline_score": baseline["score"].score,
            "baseline_total_return_pct": baseline["result"].total_return_pct,
            "baseline_max_drawdown_pct": baseline["result"].max_drawdown_pct,
            "baseline_profit_factor": baseline["result"].profit_factor,
            "baseline_risk_events": baseline["result"].risk_events,
            "auto_trend_score": auto_trend["score"].score,
            "auto_trend_total_return_pct": auto_trend["result"].total_return_pct,
            "auto_trend_max_drawdown_pct": auto_trend["result"].max_drawdown_pct,
            "auto_trend_profit_factor": auto_trend["result"].profit_factor,
            "auto_trend_risk_events": auto_trend["result"].risk_events,
            "market_regime_filter": effective_market_regime_filter(config),
            "market_regime_signal": market_signal.get("state", ""),
            "market_regime_confidence": market_signal.get("confidence", ""),
            "market_regime_allowed_sides": ",".join(market_signal.get("allowed_open_sides", [])),
            "market_regime_model_path": effective_market_regime_model_path(config),
            "ml_score_delta_vs_baseline": ml_delta(config, "score"),
            "ml_return_delta_vs_baseline": ml_delta(config, "return"),
            "ml_drawdown_delta_vs_baseline": ml_delta(config, "drawdown"),
            "ml_risk_event_delta_vs_baseline": ml_delta(config, "risk_events"),
            **pool_metrics,
            "final_equity": result.final_equity,
            "error": "",
        }
    except (OkxApiError, RuntimeError, ValueError, OSError) as exc:
        return {**base_row, "status": "error", "error": str(exc)}


def select_trend_backtest(
    candidate: MarketCandidate,
    candles: list[Candle],
    config: PortfolioBacktestConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    baseline = run_candidate_variant(candidate, candles, config, trend_filter="off")
    auto_trend = run_candidate_variant(candidate, candles, config, trend_filter="auto")
    if config.trend_filter == "off":
        selected = baseline
    elif config.trend_filter == "auto":
        selected = auto_trend
    else:
        selected = auto_trend if auto_trend["score"].score > baseline["score"].score else baseline
    return selected, baseline, auto_trend


def run_candidate_variant(
    candidate: MarketCandidate,
    candles: list[Candle],
    config: PortfolioBacktestConfig,
    *,
    trend_filter: str,
) -> dict[str, Any]:
    backtest_config = grid_config_for_candidate(candidate, candles, config, trend_filter=trend_filter)
    result, _, _ = run_grid_backtest(candles, backtest_config)
    score = score_backtest(result, config.score_weights)
    return {"trend_filter": trend_filter, "config": backtest_config, "result": result, "score": score}


def load_or_fetch_candidate_candles(
    client: OkxRestClient,
    inst_id: str,
    config: PortfolioBacktestConfig,
) -> list[Candle]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    page_suffix = "" if config.backtest_pages <= 1 else f"x{config.backtest_pages}"
    cache_path = DATA_DIR / f"{inst_id}_{config.backtest_bar}_{config.backtest_limit}{page_suffix}.csv"
    if cache_path.exists() and not config.refresh:
        return read_candles_csv(cache_path)

    rows = fetch_okx_candle_rows(
        client,
        inst_id,
        config.backtest_bar,
        config.backtest_limit,
        max(1, config.backtest_pages),
    )
    candles = parse_okx_candles(rows)
    write_candles_csv(cache_path, candles)
    return candles


def grid_config_for_candidate(
    candidate: MarketCandidate,
    candles: list[Candle],
    config: PortfolioBacktestConfig,
    *,
    trend_filter: str | None = None,
) -> GridBacktestConfig:
    mark_px = candles[-1].close if candles else candidate.last
    tick = candidate.tick_sz
    half_width = config.outer_range_bps / Decimal("20000")
    lower = round_to_tick(mark_px * (Decimal("1") - half_width), tick)
    upper = round_to_tick(mark_px * (Decimal("1") + half_width), tick)
    if lower <= 0:
        lower = tick
    if upper <= lower:
        upper = lower + tick

    order_sz = contract_size_for_margin(
        equity=config.starting_equity,
        margin_pct=config.order_margin_pct,
        leverage=config.leverage,
        mark_px=mark_px,
        ct_val=candidate.ct_val,
        lot_sz=candidate.lot_sz,
        min_sz=candidate.min_sz,
    )
    max_position = contract_size_for_margin(
        equity=config.starting_equity,
        margin_pct=config.max_margin_pct,
        leverage=config.leverage,
        mark_px=mark_px,
        ct_val=candidate.ct_val,
        lot_sz=candidate.lot_sz,
        min_sz=candidate.min_sz,
    )
    if max_position < order_sz:
        max_position = order_sz

    return GridBacktestConfig(
        inst_id=candidate.inst_id,
        bar=config.backtest_bar,
        limit=config.backtest_limit,
        lower=lower,
        upper=upper,
        leverage=config.leverage,
        grid_bps=config.grid_bps,
        soft_bps=config.soft_bps,
        hard_bps=config.hard_bps,
        order_sz=order_sz,
        max_position=max_position,
        max_open_orders_per_side=config.max_open_orders_per_side,
        max_actions_per_bar=config.max_actions_per_bar,
        mode="adaptive",
        adaptive_width_bps=config.adaptive_width_bps,
        adaptive_min_width_bps=config.adaptive_min_width_bps,
        adaptive_max_width_bps=config.adaptive_max_width_bps,
        adaptive_vol_multiplier=config.adaptive_vol_multiplier,
        range_drift_weight_bps=config.range_drift_weight_bps,
        range_drift_max_bps=config.range_drift_max_bps,
        maker_fee_bps=config.maker_fee_bps,
        taker_fee_bps=config.taker_fee_bps,
        slippage_bps=config.slippage_bps,
        starting_equity=config.starting_equity,
        ct_val=candidate.ct_val,
        tick_sz=tick,
        lot_sz=candidate.lot_sz,
        min_sz=candidate.min_sz,
        min_tp_bps=config.min_tp_bps,
        total_loss_sl_pct=config.total_loss_sl_pct,
        total_loss_sl_cap=config.total_loss_sl_cap,
        position_loss_sl_bps=config.position_loss_sl_bps,
        risk_cooldown_bars=config.risk_cooldown_bars,
        one_way_open=config.one_way_open,
        regime_filter=config.regime_filter,
        regime_bar=config.regime_bar,
        regime_short_ma=config.regime_short_ma,
        regime_long_ma=config.regime_long_ma,
        regime_diff_bps=config.regime_diff_bps,
        regime_confirm_bars=config.regime_confirm_bars,
        trend_filter=trend_filter or ("off" if config.trend_filter == "compare" else config.trend_filter),
        trend_lookback=config.trend_lookback,
        trend_threshold_bps=config.trend_threshold_bps,
        market_regime_filter=effective_market_regime_filter(config),
        market_regime_model_path=effective_market_regime_model_path(config),
        market_regime_min_confidence=config.market_regime_min_confidence,
        market_regime_mixed_policy=config.market_regime_mixed_policy,
    )


def effective_market_regime_filter(config: PortfolioBacktestConfig) -> str:
    if config.market_regime_filter == "auto":
        return config.ml_profile.mode if config.ml_profile and config.ml_profile.enabled else "off"
    return config.market_regime_filter


def effective_market_regime_model_path(config: PortfolioBacktestConfig) -> str:
    if config.market_regime_model_path:
        return config.market_regime_model_path
    if config.ml_profile and config.ml_profile.enabled:
        return config.ml_profile.model_path
    return ""


def market_regime_signal_for_candidate(candles: list[Candle], config: PortfolioBacktestConfig) -> dict[str, Any]:
    mode = effective_market_regime_filter(config)
    if mode == "off":
        return {"state": "off", "confidence": Decimal("1"), "allowed_open_sides": []}
    try:
        from market_regime import signal_from_candles, signal_to_dict

        return signal_to_dict(
            signal_from_candles(
                candles,
                mode=mode,
                model_path=effective_market_regime_model_path(config),
                min_confidence=float(config.market_regime_min_confidence),
            )
        )
    except Exception as exc:
        return {"state": "unknown", "confidence": Decimal("0"), "allowed_open_sides": [], "note": str(exc)}


def ml_delta(config: PortfolioBacktestConfig, key: str) -> Any:
    profile = config.ml_profile
    if not profile:
        return ""
    if key == "score":
        return profile.score_delta_vs_baseline
    if key == "return":
        return profile.return_delta_vs_baseline
    if key == "drawdown":
        return profile.drawdown_delta_vs_baseline
    if key == "risk_events":
        return profile.risk_event_delta_vs_baseline
    return ""


def contract_size_for_margin(
    *,
    equity: Decimal,
    margin_pct: Decimal,
    leverage: Decimal,
    mark_px: Decimal,
    ct_val: Decimal,
    lot_sz: Decimal,
    min_sz: Decimal,
) -> Decimal:
    if equity <= 0 or margin_pct <= 0 or leverage <= 0 or mark_px <= 0 or ct_val <= 0:
        return min_sz
    notional = equity * margin_pct / Decimal("100") * leverage
    raw_size = notional / (mark_px * ct_val)
    size = round_size_down(raw_size, lot_sz)
    if size < min_sz:
        size = min_sz
    return size


def round_size_down(value: Decimal, lot_sz: Decimal) -> Decimal:
    if lot_sz <= 0:
        return value
    return (value / lot_sz).to_integral_value(rounding=ROUND_DOWN) * lot_sz


def minimum_backtest_candles(config: PortfolioBacktestConfig) -> int:
    return max(30, config.regime_long_ma + config.regime_confirm_bars + 5)


def pool_window_metrics(candles: list[Candle], config: PortfolioBacktestConfig) -> dict[str, Any]:
    window_bars = pool_window_bars(config)
    window = candles[-window_bars:] if window_bars > 0 else candles
    if len(window) < 2:
        return {
            "pool_window_hours": config.pool_window_hours,
            "pool_window_bars": len(window),
            "pool_avg_abs_bps": Decimal("0"),
            "pool_shock_bps": Decimal("0"),
            "pool_trend_bps": Decimal("0"),
        }
    returns: list[Decimal] = []
    for previous, current in zip(window, window[1:]):
        if previous.close > 0:
            returns.append((current.close / previous.close - Decimal("1")) * Decimal("10000"))
    abs_returns = [abs(value) for value in returns]
    avg_abs_bps = sum(abs_returns, Decimal("0")) / Decimal(len(abs_returns)) if abs_returns else Decimal("0")
    shock_bps = max(abs_returns) if abs_returns else Decimal("0")
    trend_bps = Decimal("0")
    if window[0].close > 0:
        trend_bps = (window[-1].close / window[0].close - Decimal("1")) * Decimal("10000")
    return {
        "pool_window_hours": config.pool_window_hours,
        "pool_window_bars": len(window),
        "pool_avg_abs_bps": avg_abs_bps,
        "pool_shock_bps": shock_bps,
        "pool_trend_bps": trend_bps,
    }


def pool_window_bars(config: PortfolioBacktestConfig) -> int:
    bar_ms = BAR_MS.get(config.backtest_bar, 60_000)
    if bar_ms <= 0 or config.pool_window_hours <= 0:
        return 0
    window_ms = config.pool_window_hours * Decimal("3600000")
    bars = int((window_ms / Decimal(bar_ms)).to_integral_value(rounding=ROUND_DOWN))
    return max(2, bars)


def rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=row_sort_key, reverse=True)
    rank = 1
    for row in ranked:
        if row.get("status") == "ok":
            row["rank"] = rank
            rank += 1
        else:
            row["rank"] = ""
    return ranked


def row_sort_key(row: dict[str, Any]) -> tuple[int, Decimal, Decimal]:
    status_score = 1 if row.get("status") == "ok" else 0
    score = dec(row.get("score"), Decimal("-999999999"))
    volume = dec(row.get("quote_volume_24h"))
    return status_score, score, volume


def write_portfolio_outputs(
    candidates: list[MarketCandidate],
    rows: list[dict[str, Any]],
    targets: list[Any],
    current_exposures: dict[str, Any],
    actions: list[Any],
    config: PortfolioBacktestConfig,
    output_dir_arg: str = "",
) -> Path:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = resolve_output_dir(output_dir_arg, timestamp)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates_payload = {
        "generatedAt": generated_at,
        "product": quant_metadata(config.ml_profile),
        "selector": selector_config_to_dict(config.selector),
        "backtest": portfolio_config_to_dict(config),
        "candidateCount": len(candidates),
        "candidates": [candidate_to_dict(candidate) for candidate in candidates],
    }
    (output_dir / "candidates.json").write_text(json.dumps(candidates_payload, indent=2), encoding="utf-8")

    with (output_dir / "scores.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SCORE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field, "")) for field in SCORE_FIELDS})

    rebalance_payload = {
        "generatedAt": generated_at,
        "product": quant_metadata(config.ml_profile),
        "mode": "dry_run" if config.trading_mode in {"backtest", "paper"} else "live_candidate",
        "tradingMode": config.trading_mode,
        "includeAccount": config.include_account,
        "allocation": allocation_config_to_dict(config.allocation),
        "targets": [allocation_to_dict(target) for target in targets],
        "currentExposures": [exposure_to_dict(exposure) for exposure in current_exposures.values()],
        "actions": [action_to_dict(action) for action in actions],
    }
    (output_dir / "rebalance_plan.json").write_text(json.dumps(rebalance_payload, indent=2), encoding="utf-8")
    with (output_dir / "rebalance_plan.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REBALANCE_FIELDS)
        writer.writeheader()
        for action in actions:
            row = action_to_dict(action)
            writer.writerow({field: csv_value(row.get(field, "")) for field in REBALANCE_FIELDS})

    intents = write_execution_bundle(
        targets=targets,
        actions=actions,
        candidates=candidates,
        strategy_config=config,
        output_dir=output_dir,
        execution_config=ExecutionConfig(
            trading_mode=config.trading_mode,
            cash_reserve_pct=config.allocation.cash_reserve_pct,
            maker_fee_bps=config.maker_fee_bps,
            taker_fee_bps=config.taker_fee_bps,
            market_regime_filter=effective_market_regime_filter(config),
            market_regime_model_path=effective_market_regime_model_path(config),
            market_regime_min_confidence=config.market_regime_min_confidence,
        ),
    )

    hedge_plan = build_tail_hedge_plan(
        targets=targets,
        current_exposures=current_exposures,
        candidates=candidates,
        score_rows=rows,
        equity=config.starting_equity,
        config=config.tail_hedge or TailHedgeConfig(),
        generated_at=generated_at,
    )
    write_tail_hedge_outputs(output_dir, hedge_plan)

    write_summary(output_dir / "summary.md", generated_at, candidates, rows, targets, actions, intents, hedge_plan, config)
    return output_dir


def resolve_output_dir(output_dir_arg: str, timestamp: str) -> Path:
    if not output_dir_arg:
        return REPORT_DIR / timestamp
    path = Path(output_dir_arg)
    if path.is_absolute():
        return path
    return REPORT_DIR / path


def write_summary(
    path: Path,
    generated_at: str,
    candidates: list[MarketCandidate],
    rows: list[dict[str, Any]],
    targets: list[Any],
    actions: list[Any],
    intents: list[Any],
    hedge_plan: Any,
    config: PortfolioBacktestConfig,
) -> None:
    lines = [
        "# OKX Portfolio Candidate Backtest",
        "",
        f"Product layer: `{quant_metadata(config.ml_profile)['productCn']}` / `{quant_metadata(config.ml_profile)['product']}`.",
        "",
        "This report uses public OKX data only. It is research output, not investment advice.",
        "",
        f"- Generated: `{generated_at}`",
        f"- Candidates: `{len(candidates)}`",
        f"- Backtest: `{config.backtest_bar}` x `{config.backtest_limit}` x `{config.backtest_pages}` pages",
        f"- Selector: min quote volume `{plain(config.selector.min_quote_volume)}`, max spread `{plain(config.selector.max_spread_bps)}` bps, top `{config.selector.top_n}`",
        f"- Rebalance: dry-run, target symbols `{config.allocation.max_symbols}`, cash reserve `{plain(config.allocation.cash_reserve_pct)}`%, min deploy `{plain(config.allocation.min_deploy_pct)}`%",
        f"- Trading mode: `{config.trading_mode}`",
        f"- ML regime gate: `{effective_market_regime_filter(config)}` model `{effective_market_regime_model_path(config) or 'none'}` min confidence `{plain(config.market_regime_min_confidence)}` mixed policy `{config.market_regime_mixed_policy}`",
        f"- Portfolio shape: core `{config.allocation.core_symbols}` symbols / `{plain(config.allocation.core_weight_share_pct)}`% of deployed capital, satellites max `{plain(config.allocation.satellite_max_weight_pct)}`%",
        f"- Tail hedge: mode `{hedge_plan.mode}` status `{hedge_plan.status}` level `{hedge_plan.target_hedge_level}` ratio `{plain(hedge_plan.target_hedge_ratio)}` net `{plain(hedge_plan.net_notional)}` / `{plain(hedge_plan.net_exposure_pct)}`%",
        "",
        "## Run Parameters",
        "",
        "| Group | Setting | Value |",
        "| --- | --- | ---: |",
        f"| Universe | Candidate limit | {config.selector.top_n} |",
        f"| Universe | Min quote volume | {plain(config.selector.min_quote_volume)} |",
        f"| Universe | Max spread bps | {plain(config.selector.max_spread_bps)} |",
        f"| Backtest | Bar / pages / limit | {config.backtest_bar} / {config.backtest_pages} / {config.backtest_limit} |",
        f"| Allocation | Target symbols | {config.allocation.max_symbols} |",
        f"| Allocation | Min fills | {config.allocation.min_fills} |",
        f"| Allocation | Max risk events | {config.allocation.max_risk_events} |",
        f"| Allocation | Cash reserve % | {plain(config.allocation.cash_reserve_pct)} |",
        f"| Allocation | Min deploy % | {plain(config.allocation.min_deploy_pct)} |",
        f"| Sizing | Starting equity / leverage | {plain(config.starting_equity)} / {plain(config.leverage)}x |",
        f"| Filters | Trend / market regime | {config.trend_filter} / {effective_market_regime_filter(config)} |",
        "",
        "## Scores",
        "",
    ]
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    if not ok_rows:
        lines.extend(["No candidates completed a backtest.", ""])
    else:
        lines.extend(
            [
                "| Rank | Instrument | Score | Return % | Max DD % | Profit Factor | Fills | Risk Events |",
                "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in ok_rows[:20]:
            lines.append(
                "| {rank} | {inst} | {score} | {ret} | {dd} | {pf} | {fills} | {risk} |".format(
                    rank=row.get("rank", ""),
                    inst=row.get("inst_id", ""),
                    score=csv_value(row.get("score", "")),
                    ret=csv_value(row.get("total_return_pct", "")),
                    dd=csv_value(row.get("max_drawdown_pct", "")),
                    pf=csv_value(row.get("profit_factor", "")),
                    fills=csv_value(row.get("fills", "")),
                    risk=csv_value(row.get("risk_events", "")),
                )
            )
        lines.append("")

    lines.extend(["## Eligibility Diagnostics", ""])
    diagnostics = eligibility_diagnostics(rows, config)
    if not diagnostics:
        lines.extend(["No successful candidates were available for allocation.", ""])
    else:
        lines.extend(
            [
                "| Rank | Instrument | Allocation Status | Reason |",
                "| ---: | --- | --- | --- |",
            ]
        )
        for item in diagnostics[:20]:
            lines.append(
                f"| {item['rank']} | {item['inst_id']} | {item['status']} | {item['reason']} |"
            )
        if not targets:
            blocked = [item for item in diagnostics if item["status"] == "filtered"]
            if blocked:
                lines.extend(
                    [
                        "",
                        (
                            "No target allocations were generated because every successful candidate was filtered out. "
                            "The most common cause is `risk_events` above the allocation cap; raise the sandbox "
                            "`Max risk events` only for sensitivity testing, not as an automatic live setting."
                        ),
                    ]
                )
        lines.append("")

    lines.extend(["## Target Portfolio", ""])
    if not targets:
        lines.extend(["No target allocations were generated.", ""])
    else:
        lines.extend(
            [
                "| Rank | Role | Instrument | Weight % | Target Margin | Target Notional | Order Size | Max Position |",
                "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for target in targets:
            lines.append(
                "| {rank} | {role} | {inst} | {weight} | {margin} | {notional} | {order_sz} | {max_pos} |".format(
                    rank=target.rank,
                    role=getattr(target, "role", ""),
                    inst=target.inst_id,
                    weight=plain(target.weight_pct),
                    margin=plain(target.target_margin),
                    notional=plain(target.target_notional),
                    order_sz=plain(target.order_sz),
                    max_pos=plain(target.max_position),
                )
            )
        lines.append("")

    lines.extend(["## Rebalance Dry Run", ""])
    if not actions:
        lines.extend(["No rebalance actions were generated.", ""])
    else:
        lines.extend(
            [
                "| Instrument | Action | Current % | Target % | Delta % | Delta Margin | Note |",
                "| --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for action in actions:
            lines.append(
                "| {inst} | {action} | {current} | {target} | {delta} | {delta_margin} | {note} |".format(
                    inst=action.inst_id,
                    action=action.action,
                    current=plain(action.current_weight_pct),
                    target=plain(action.target_weight_pct),
                    delta=plain(action.delta_weight_pct),
                    delta_margin=plain(action.delta_margin),
                    note=action.note,
                )
            )
        lines.append("")

    lines.extend(["## Execution Bundle", ""])
    if not intents:
        lines.extend(["No execution intents were generated.", ""])
    else:
        lines.extend(
            [
                "| Instrument | Action | Status | Runtime Config | Note |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for intent in intents:
            path_label = Path(intent.runtime_config_path).name if intent.runtime_config_path else ""
            lines.append(
                f"| {intent.inst_id} | {intent.action} | {intent.status} | {path_label} | {intent.note} |"
            )
        lines.append("")

    lines.extend(["## Tail Hedge Plan", ""])
    lines.extend(
        [
            "| Status | Level | Hedge Ratio | Target Hedge | Net Notional | Net % | Shock bps | Trend bps | Risk Events | Note |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            (
                f"| {hedge_plan.status} | {hedge_plan.target_hedge_level} | "
                f"{plain(hedge_plan.target_hedge_ratio)} | {plain(hedge_plan.target_hedge_notional)} | "
                f"{plain(hedge_plan.net_notional)} | "
                f"{plain(hedge_plan.net_exposure_pct)} | {plain(hedge_plan.max_shock_bps)} | "
                f"{plain(hedge_plan.max_abs_trend_bps)} | {hedge_plan.total_risk_events} | {hedge_plan.note} |"
            ),
            "",
        ]
    )
    if hedge_plan.trigger_reasons:
        for reason in hedge_plan.trigger_reasons:
            lines.append(f"- {reason}")
        lines.append("")
    if hedge_plan.actions:
        lines.extend(
            [
                "| Instrument | Action | Side | Pos Side | Size | Target Notional | Hedge Ratio | Level | Status |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for action in hedge_plan.actions:
            lines.append(
                f"| {action.inst_id} | {action.action} | {action.side} | {action.pos_side} | {plain(action.sz)} | "
                f"{plain(action.target_notional)} | {plain(action.target_hedge_ratio)} | {action.hedge_level} | {action.status} |"
            )
        lines.append("")

    failed_rows = [row for row in rows if row.get("status") != "ok"]
    if failed_rows:
        lines.extend(["## Skipped Or Failed", ""])
        for row in failed_rows[:20]:
            lines.append(f"- `{row.get('inst_id', '')}`: {row.get('status')} - {row.get('error', '')}")
        lines.append("")
    lines.extend(
        [
            "## Files",
            "",
            "- `candidates.json`: selected market metadata and run configuration.",
            "- `scores.csv`: sortable score table and headline backtest metrics.",
            "- `rebalance_plan.json`: dry-run target allocations and action plan.",
            "- `rebalance_plan.csv`: sortable dry-run action table.",
            "- `execution_intents.json`: dry-run execution bundle and generated one-cycle bot commands.",
            "- `execution_intents.csv`: sortable dry-run execution intent table.",
            "- `hedge_plan.json`: portfolio tail hedge diagnostics and scheduled/manual hedge action draft.",
            "- `hedge_plan.csv`: sortable tail hedge action draft.",
            "- `hedge_plan.md`: human-readable tail hedge plan.",
            "- `runtime_configs/`: generated runtime config drafts for enter/increase/hold targets.",
            "- `summary.md`: this human-readable summary.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def eligibility_diagnostics(rows: list[dict[str, Any]], config: PortfolioBacktestConfig) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        reasons = []
        score = dec(row.get("score"))
        fills = int(dec(row.get("fills")))
        risk_events = int(dec(row.get("risk_events")))
        if score < config.allocation.min_score:
            reasons.append(f"score {plain(score)} < min {plain(config.allocation.min_score)}")
        if fills < config.allocation.min_fills:
            reasons.append(f"fills {fills} < min {config.allocation.min_fills}")
        if risk_events > config.allocation.max_risk_events:
            reasons.append(f"risk events {risk_events} > max {config.allocation.max_risk_events}")
        diagnostics.append(
            {
                "rank": str(row.get("rank", "")),
                "inst_id": str(row.get("inst_id", "")),
                "status": "filtered" if reasons else "eligible",
                "reason": "; ".join(reasons) if reasons else "passed allocation filters",
            }
        )
    return diagnostics


def candidate_row(candidate: MarketCandidate) -> dict[str, Any]:
    return {
        "rank": "",
        "status": "pending",
        "inst_id": candidate.inst_id,
        "score": "",
        "quote_volume_24h": candidate.quote_volume_24h,
        "spread_bps": candidate.spread_bps,
        "last": candidate.last,
        "bars": "",
        "total_return_pct": "",
        "max_drawdown_pct": "",
        "profit_factor": "",
        "fills": "",
        "win_rate_pct": "",
        "risk_events": "",
        "selected_trend_filter": "",
        "trend_filter_checked": "",
        "trend_score_delta": "",
        "baseline_score": "",
        "baseline_total_return_pct": "",
        "baseline_max_drawdown_pct": "",
        "baseline_profit_factor": "",
        "baseline_risk_events": "",
        "auto_trend_score": "",
            "auto_trend_total_return_pct": "",
            "auto_trend_max_drawdown_pct": "",
            "auto_trend_profit_factor": "",
            "auto_trend_risk_events": "",
            "market_regime_filter": "",
            "market_regime_signal": "",
            "market_regime_confidence": "",
            "market_regime_allowed_sides": "",
            "market_regime_model_path": "",
            "ml_score_delta_vs_baseline": "",
            "ml_return_delta_vs_baseline": "",
            "ml_drawdown_delta_vs_baseline": "",
            "ml_risk_event_delta_vs_baseline": "",
            "pool_window_hours": "",
        "pool_window_bars": "",
        "pool_avg_abs_bps": "",
        "pool_shock_bps": "",
        "pool_trend_bps": "",
        "final_equity": "",
        "error": "",
    }


def portfolio_config_to_dict(config: PortfolioBacktestConfig) -> dict[str, Any]:
    payload = jsonable(asdict(config))
    payload["score_weights"] = weights_to_dict(config.score_weights)
    if config.ml_profile:
        payload["ml_profile"] = profile_to_dict(config.ml_profile)
    return payload


def allocation_config_to_dict(config: AllocationConfig) -> dict[str, Any]:
    return jsonable(asdict(config))


def csv_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    return value


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


if __name__ == "__main__":
    raise SystemExit(main())
