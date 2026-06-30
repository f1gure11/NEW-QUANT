from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from market_selector import MarketCandidate
from portfolio_allocator import RebalanceAction, TargetAllocation
from portfolio_execution import (
    ExecutionConfig,
    backtest_risk_reward_values,
    build_execution_intents,
    executable_grid_floor_bps,
    pool_adaptive_runtime_values,
    runtime_config_for_target,
    write_execution_bundle,
)


def candidate(inst_id: str = "AAA-USDT-SWAP") -> MarketCandidate:
    return MarketCandidate(
        inst_id=inst_id,
        inst_family=inst_id.removesuffix("-SWAP"),
        base_ccy=inst_id.split("-")[0],
        quote_ccy="USDT",
        settle_ccy="USDT",
        ct_val=Decimal("1"),
        tick_sz=Decimal("0.01"),
        lot_sz=Decimal("1"),
        min_sz=Decimal("1"),
        state="live",
        last=Decimal("100"),
        bid_px=Decimal("99.99"),
        ask_px=Decimal("100.01"),
        spread_bps=Decimal("2"),
        quote_volume_24h=Decimal("10000000"),
        volume_24h=Decimal("100000"),
    )


def target(inst_id: str = "AAA-USDT-SWAP") -> TargetAllocation:
    return TargetAllocation(
        inst_id=inst_id,
        rank=1,
        role="core",
        score=Decimal("12"),
        weight_pct=Decimal("40"),
        target_margin=Decimal("40"),
        target_notional=Decimal("120"),
        last=Decimal("100"),
        order_sz=Decimal("1"),
        max_position=Decimal("3"),
        pool_window_hours=Decimal("5"),
        pool_window_bars=300,
        pool_avg_abs_bps=Decimal("8"),
        pool_shock_bps=Decimal("40"),
        pool_trend_bps=Decimal("120"),
        reason="test",
    )


def volatile_target(inst_id: str = "AAA-USDT-SWAP") -> TargetAllocation:
    item = target(inst_id)
    item.pool_avg_abs_bps = Decimal("60")
    item.pool_shock_bps = Decimal("240")
    item.pool_trend_bps = Decimal("-500")
    return item


def action(inst_id: str = "AAA-USDT-SWAP", action_name: str = "enter") -> RebalanceAction:
    return RebalanceAction(
        inst_id=inst_id,
        action=action_name,
        current_weight_pct=Decimal("0"),
        target_weight_pct=Decimal("40"),
        delta_weight_pct=Decimal("40"),
        current_margin=Decimal("0"),
        target_margin=Decimal("40"),
        delta_margin=Decimal("40"),
        note="test",
    )


class PortfolioExecutionTest(unittest.TestCase):
    def test_runtime_config_for_target_matches_bot_keys(self) -> None:
        runtime = runtime_config_for_target(
            target(),
            candidate(),
            SimpleNamespace(
                outer_range_bps=Decimal("1000"),
                leverage=Decimal("3"),
                grid_bps=Decimal("18"),
                regime_filter="off",
                trend_filter="auto",
            ),
        )

        self.assertEqual(runtime["instId"], "AAA-USDT-SWAP")
        self.assertEqual(runtime["lower"], "95")
        self.assertEqual(runtime["upper"], "105")
        self.assertEqual(runtime["orderSz"], "1")
        self.assertEqual(runtime["maxPosition"], "3")
        self.assertEqual(runtime["sizingMode"], "margin_pct")
        self.assertEqual(runtime["cashReservePct"], "10")
        self.assertEqual(runtime["strategyProfile"], "portfolio_rolling_adaptive_v1")
        self.assertTrue(runtime["rollingAdaptiveEnabled"])
        self.assertEqual(runtime["rollingAdaptiveWindow"], "20")
        self.assertEqual(runtime["rollingAdaptiveMinLeverage"], "3")
        self.assertEqual(runtime["rollingAdaptiveMaxLeverage"], "7")
        self.assertEqual(runtime["leverage"], "7")
        self.assertEqual(runtime["gridBps"], "10")
        self.assertEqual(runtime["orderMarginPct"], "25")
        self.assertEqual(runtime["maxMarginPct"], "75")
        self.assertEqual(runtime["minTpBps"], "30")
        self.assertEqual(runtime["positionLossSlBps"], "700")
        self.assertEqual(runtime["exchangeStopBps"], "800")
        self.assertEqual(runtime["totalProfitTpPct"], "1.5")
        self.assertEqual(runtime["totalLossSlPct"], "4")
        self.assertEqual(runtime["maxOpenOrdersPerSide"], "5")
        self.assertEqual(runtime["maxActionsPerCycle"], "4")
        self.assertEqual(runtime["interval"], "8")
        self.assertEqual(runtime["trendFilter"], "off")
        self.assertEqual(runtime["totalLossSlCap"], "0.8")
        self.assertFalse(runtime["oneWayOpen"])
        self.assertEqual(runtime["poolAdaptiveWindowHours"], "5")
        self.assertEqual(runtime["poolAdaptiveAvgAbsBps"], "8")
        self.assertEqual(runtime["poolAdaptiveShockBps"], "40")
        self.assertIn("pool 5h", runtime["poolAdaptiveNote"])
        self.assertTrue(runtime["setLeverage"])
        self.assertTrue(runtime["exchangeStopEnabled"])
        self.assertTrue(runtime["portfolioGenerated"])

    def test_runtime_config_keeps_high_frequency_seed_and_records_pool_risk(self) -> None:
        quiet = runtime_config_for_target(
            target(),
            candidate(),
            SimpleNamespace(outer_range_bps=Decimal("1000")),
        )
        volatile = runtime_config_for_target(
            volatile_target(),
            candidate(),
            SimpleNamespace(outer_range_bps=Decimal("1000")),
        )

        self.assertEqual(quiet["strategyProfile"], "portfolio_rolling_adaptive_v1")
        self.assertEqual(volatile["strategyProfile"], "portfolio_rolling_adaptive_v1")
        self.assertEqual(quiet["leverage"], volatile["leverage"])
        self.assertEqual(quiet["gridBps"], volatile["gridBps"])
        self.assertEqual(quiet["minTpBps"], volatile["minTpBps"])
        self.assertLess(Decimal(quiet["poolAdaptiveRiskScore"]), Decimal(volatile["poolAdaptiveRiskScore"]))

    def test_runtime_config_raises_grid_floor_for_low_price_tick_after_fees(self) -> None:
        item = target("DOGE-USDT-SWAP")
        item.last = Decimal("0.07559")
        low_price_candidate = candidate("DOGE-USDT-SWAP")
        low_price_candidate.last = Decimal("0.07559")
        low_price_candidate.tick_sz = Decimal("0.00001")
        low_price_candidate.ct_val = Decimal("1000")
        low_price_candidate.lot_sz = Decimal("0.01")
        low_price_candidate.min_sz = Decimal("0.01")

        runtime = runtime_config_for_target(
            item,
            low_price_candidate,
            SimpleNamespace(outer_range_bps=Decimal("1200")),
            ExecutionConfig(
                min_net_bps=Decimal("1"),
                maker_fee_bps=Decimal("2"),
                taker_fee_bps=Decimal("5"),
                rolling_adaptive_min_grid_bps=Decimal("8"),
                rolling_adaptive_max_grid_bps=Decimal("36"),
            ),
        )

        self.assertGreater(Decimal(runtime["rollingAdaptiveMinGridBps"]), Decimal("8"))
        self.assertGreaterEqual(Decimal(runtime["gridBps"]), Decimal(runtime["rollingAdaptiveMinGridBps"]))
        self.assertIn("tick/fees", runtime["gridExecutableNote"])

    def test_executable_grid_floor_matches_doge_tick_rounding(self) -> None:
        floor = executable_grid_floor_bps(
            midpoint=Decimal("0.0755"),
            tick=Decimal("0.00001"),
            lower=Decimal("0.07452"),
            upper=Decimal("0.07648"),
            min_net_bps=Decimal("1"),
            maker_fee_bps=Decimal("2"),
            taker_fee_bps=Decimal("5"),
            ord_type="post_only",
        )

        self.assertEqual(floor["required_step"], Decimal("0.00007"))
        self.assertGreaterEqual(floor["required_grid_bps"], Decimal("9.2715"))

    def test_pool_adaptive_runtime_values_match_rolling_limits(self) -> None:
        values = pool_adaptive_runtime_values(volatile_target(), ExecutionConfig())

        self.assertEqual(values["leverage"], Decimal("3"))
        self.assertEqual(values["grid_bps"], Decimal("36"))
        self.assertEqual(values["position_loss_sl_bps"], Decimal("1300"))
        self.assertEqual(values["exchange_stop_bps"], Decimal("1300"))

    def test_backtest_risk_reward_controls_runtime_tp_sl(self) -> None:
        item = target()
        item.total_return_pct = Decimal("6")
        item.max_drawdown_pct = Decimal("3")
        item.profit_factor = Decimal("2.4")
        item.fills = 16
        adaptive = pool_adaptive_runtime_values(item, ExecutionConfig())

        values = backtest_risk_reward_values(item, adaptive, ExecutionConfig())

        self.assertGreaterEqual(values["total_profit_tp_pct"], Decimal("2.7"))
        self.assertGreaterEqual(values["total_loss_sl_pct"], values["total_profit_tp_pct"] * Decimal("2.2"))
        self.assertLessEqual(values["total_loss_sl_pct"], Decimal("8"))
        self.assertGreater(values["position_loss_sl_bps"], values["min_tp_bps"])
        self.assertLessEqual(values["position_loss_sl_bps"], Decimal("1300"))

    def test_backtest_risk_events_tighten_runtime_sl(self) -> None:
        clean = target()
        clean.max_drawdown_pct = Decimal("3")
        clean.profit_factor = Decimal("2")
        clean.fills = 16
        clean.risk_events = 0
        risky = target()
        risky.max_drawdown_pct = Decimal("8")
        risky.profit_factor = Decimal("1.1")
        risky.fills = 16
        risky.risk_events = 3

        clean_values = backtest_risk_reward_values(clean, pool_adaptive_runtime_values(clean, ExecutionConfig()), ExecutionConfig())
        risky_values = backtest_risk_reward_values(risky, pool_adaptive_runtime_values(risky, ExecutionConfig()), ExecutionConfig())

        self.assertLessEqual(risky_values["total_loss_sl_pct"], Decimal("8"))
        self.assertGreaterEqual(risky_values["total_loss_sl_pct"], risky_values["total_profit_tp_pct"] * Decimal("2.2"))

    def test_build_execution_intents_generates_dry_run_command_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            intents = build_execution_intents(
                targets=[target()],
                actions=[action()],
                candidates=[candidate()],
                strategy_config=SimpleNamespace(),
                output_dir=Path(tmpdir),
            )

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].status, "runtime_config_ready")
        self.assertIn("--once", intents[0].dry_run_command)
        self.assertIn("--lower 94", intents[0].dry_run_command)
        self.assertIn("--exchange-stop-enabled", intents[0].dry_run_command)
        self.assertIn("--total-profit-tp-pct 1.5", intents[0].dry_run_command)
        self.assertIn("--total-loss-sl-pct 4", intents[0].dry_run_command)
        self.assertIn("--missed-tp-ord-type limit", intents[0].dry_run_command)
        self.assertIn("--hard-stop-ord-type market", intents[0].dry_run_command)
        self.assertIn("--order-margin-pct 25", intents[0].dry_run_command)
        self.assertIn("--grid-bps 10", intents[0].dry_run_command)
        self.assertIn("--position-loss-sl-bps 700", intents[0].dry_run_command)
        self.assertIn("--market-regime-filter off", intents[0].dry_run_command)
        self.assertIn("--market-regime-mixed-policy price_anchor", intents[0].dry_run_command)
        self.assertIn("--cash-reserve-pct 10", intents[0].dry_run_command)
        self.assertIn("--rolling-adaptive", intents[0].dry_run_command)
        self.assertIn("--rolling-adaptive-window 20", intents[0].dry_run_command)
        self.assertIn("--max-open-orders-per-side 5", intents[0].dry_run_command)
        self.assertIn("--max-actions-per-cycle 4", intents[0].dry_run_command)
        self.assertIn("--interval 8", intents[0].dry_run_command)
        self.assertIn("--allow-dual-open", intents[0].dry_run_command)
        self.assertIn("--set-leverage", intents[0].dry_run_command)
        self.assertNotIn("--live", intents[0].dry_run_command)

    def test_runtime_config_uses_selected_trend_filter(self) -> None:
        item = target()
        item.selected_trend_filter = "auto"
        item.trend_filter_checked = True
        item.trend_score_delta = Decimal("1.5")

        runtime = runtime_config_for_target(item, candidate(), SimpleNamespace(outer_range_bps=Decimal("1000")))

        self.assertEqual(runtime["trendFilter"], "auto")
        self.assertTrue(runtime["trendFilterChecked"])
        self.assertEqual(runtime["trendScoreDelta"], "1.5")

    def test_runtime_config_carries_ml_regime_gate(self) -> None:
        item = target()
        item.market_regime_signal = "range"
        item.market_regime_confidence = Decimal("0.91")
        item.market_regime_allowed_sides = "long,short"
        item.ml_return_delta_vs_baseline = Decimal("9")
        runtime = runtime_config_for_target(
            item,
            candidate(),
            SimpleNamespace(outer_range_bps=Decimal("1000")),
            ExecutionConfig(market_regime_filter="rf", market_regime_model_path="/models/rf.joblib"),
        )

        self.assertEqual(runtime["marketRegimeFilter"], "rf")
        self.assertEqual(runtime["marketRegimeModelPath"], "/models/rf.joblib")
        self.assertEqual(runtime["marketRegimeMixedPolicy"], "price_anchor")
        self.assertEqual(runtime["marketRegimeSignal"], "range")
        self.assertEqual(runtime["marketRegimeConfidence"], "0.91")
        self.assertEqual(runtime["marketRegimeAllowedSides"], "long,short")
        self.assertEqual(runtime["mlReturnDeltaVsBaseline"], "9")
        self.assertIn("ml_regime=rf/range", runtime["poolAdaptiveNote"])

    def test_reduce_action_generates_rebalancer_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with redirect_stdout(StringIO()):
                intents = build_execution_intents(
                    targets=[],
                    actions=[action("OLD-USDT-SWAP", "exit")],
                    candidates=[],
                    strategy_config=SimpleNamespace(),
                    output_dir=Path(tmpdir),
                )

        self.assertEqual(intents[0].status, "rebalance_reduce_ready")
        self.assertIn("portfolio_rebalancer.py", intents[0].dry_run_command)
        self.assertIn("--inst-id OLD-USDT-SWAP", intents[0].dry_run_command)
        self.assertIn("--once", intents[0].dry_run_command)
        self.assertNotIn("--live", intents[0].dry_run_command)

    def test_decrease_action_generates_runtime_and_reduce_intents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with redirect_stdout(StringIO()):
                intents = build_execution_intents(
                    targets=[target()],
                    actions=[action("AAA-USDT-SWAP", "decrease")],
                    candidates=[candidate()],
                    strategy_config=SimpleNamespace(),
                    output_dir=Path(tmpdir),
                )

        self.assertEqual([intent.status for intent in intents], ["runtime_config_ready", "rebalance_reduce_ready"])
        self.assertEqual([intent.action for intent in intents], ["decrease", "decrease"])
        self.assertIn("auto_grid_bot.py", intents[0].dry_run_command)
        self.assertIn("portfolio_rebalancer.py", intents[1].dry_run_command)

    def test_write_execution_bundle_writes_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            intents = write_execution_bundle(
                targets=[target()],
                actions=[action()],
                candidates=[candidate()],
                strategy_config=SimpleNamespace(),
                output_dir=output_dir,
            )

            runtime_path = Path(intents[0].runtime_config_path)
            self.assertTrue(runtime_path.exists())
            self.assertTrue((output_dir / "execution_intents.json").exists())
            self.assertTrue((output_dir / "execution_intents.csv").exists())


if __name__ == "__main__":
    unittest.main()
