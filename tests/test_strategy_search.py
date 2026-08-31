from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backtest.okx_grid_backtest import Candle
from strategy_search import (
    combined_search_score,
    cross_targets,
    ema_cross_atr_band_targets,
    multi_horizon_momentum_targets,
    simulator_volatility_scale,
    simulate_segment,
    time_series_momentum_targets,
)
from strategy_walk_forward import (
    build_regime_memberships,
    build_windows,
    cross_sectional_momentum_targets,
    filter_targets_by_regime,
    funding_daily_bps,
    instrument_cost_args,
    regime_variants,
    run_walk_forward,
)


class StrategySearchTest(unittest.TestCase):
    def test_time_series_momentum_is_active_and_uses_only_prior_bar(self) -> None:
        closes = [100.0 + index * 0.5 for index in range(80)]
        base = time_series_momentum_targets(closes, lookback=12, vol_window=24, threshold_sigma=0.0)
        moved = time_series_momentum_targets(closes[:-1] + [20.0], lookback=12, vol_window=24, threshold_sigma=0.0)

        self.assertEqual(base[-1], 1)
        self.assertEqual(base[-1], moved[-1])
        self.assertGreater(sum(1 for target in base if target != 0) / len(base), 0.5)

    def test_multi_horizon_momentum_votes_without_lookahead(self) -> None:
        closes = [100.0 + index * 0.25 for index in range(140)]
        base = multi_horizon_momentum_targets(closes, [6, 12, 24, 48], 48, 0.0, 2)
        moved = multi_horizon_momentum_targets(closes[:-1] + [10.0], [6, 12, 24, 48], 48, 0.0, 2)

        self.assertEqual(base[-1], 1)
        self.assertEqual(base[-1], moved[-1])

    def test_simulator_volatility_target_reduces_high_volatility_size(self) -> None:
        candles = [
            Candle(
                ts=index * 300_000,
                open=100.0 + (8.0 if index % 2 else -8.0),
                high=110.0,
                low=90.0,
                close=100.0 + (8.0 if index % 2 else -8.0),
                volume=1.0,
            )
            for index in range(70)
        ]

        scale = simulator_volatility_scale(candles, 69, {"target_daily_vol_bps": 300, "vol_window_bars": 48})

        self.assertGreater(scale, 0.0)
        self.assertLess(scale, 1.0)

    def test_cross_signal_is_delayed_to_next_bar_target(self) -> None:
        targets = cross_targets([1.0, 2.0, 2.0], [1.0, 1.0, 1.0], 0.0)

        self.assertEqual(targets, [0, 0, 1])

    def test_ema_cross_atr_band_uses_only_prior_bar_data(self) -> None:
        closes = [100.0] * 30 + [100.0, 130.0, 130.0, 130.0]
        highs = [value + 1.0 for value in closes]
        lows = [value - 1.0 for value in closes]

        base = ema_cross_atr_band_targets(closes, highs, lows, 2, 5, 3, 0.25, 1)
        # Mutating the final bar must not change the final bar's own target.
        moved = ema_cross_atr_band_targets(closes[:-1] + [50.0], highs[:-1] + [51.0], lows[:-1] + [49.0], 2, 5, 3, 0.25, 1)

        self.assertEqual(base[-1], moved[-1])

    def test_ema_cross_atr_band_persistence_delays_flip(self) -> None:
        closes = [100.0] * 30 + [140.0, 140.0, 140.0, 140.0]
        highs = [value + 1.0 for value in closes]
        lows = [value - 1.0 for value in closes]

        fast_flip = ema_cross_atr_band_targets(closes, highs, lows, 2, 5, 3, 0.1, 1)
        slow_flip = ema_cross_atr_band_targets(closes, highs, lows, 2, 5, 3, 0.1, 2)

        first_long_fast = fast_flip.index(1)
        first_long_slow = slow_flip.index(1)
        self.assertGreater(first_long_slow, first_long_fast)

    def test_segment_executes_target_on_current_open_not_prior_close(self) -> None:
        candles = [
            Candle(ts=0, open=100.0, high=100.0, low=100.0, close=100.0, volume=0.0),
            Candle(ts=60_000, open=100.0, high=110.0, low=100.0, close=110.0, volume=0.0),
            Candle(ts=120_000, open=200.0, high=200.0, low=200.0, close=200.0, volume=0.0),
        ]
        args = SimpleNamespace(
            starting_equity=100.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            margin_pct=100.0,
            leverage=1.0,
        )

        result = simulate_segment(candles, [0, 0, 1], 1, 3, args)

        self.assertEqual(result.trades, 1)
        self.assertEqual(result.return_pct, 0.0)
        self.assertEqual(result.exposure_pct, 50.0)

    def test_cost_stress_multiplier_makes_same_trade_less_profitable(self) -> None:
        candles = [
            Candle(ts=0, open=100.0, high=100.0, low=100.0, close=100.0, volume=0.0),
            Candle(ts=60_000, open=100.0, high=100.0, low=100.0, close=100.0, volume=0.0),
            Candle(ts=120_000, open=100.0, high=110.0, low=100.0, close=110.0, volume=0.0),
        ]
        base_args = SimpleNamespace(
            starting_equity=100.0,
            fee_bps=1.0,
            slippage_bps=1.0,
            cost_stress_multiplier=1.0,
            holding_cost_bps_per_day=0.0,
            margin_pct=100.0,
            leverage=1.0,
        )
        stressed_args = SimpleNamespace(**{**vars(base_args), "cost_stress_multiplier": 3.0})

        base = simulate_segment(candles, [0, 1, 1], 1, 3, base_args)
        stressed = simulate_segment(candles, [0, 1, 1], 1, 3, stressed_args)

        self.assertLess(stressed.return_pct, base.return_pct)
        self.assertGreater(stressed.fees, base.fees)

    def test_combined_search_score_uses_holdout_not_only_train(self) -> None:
        train_heavy = combined_search_score(10.0, 1.0)
        holdout_heavy = combined_search_score(1.0, 10.0)

        self.assertGreater(holdout_heavy, train_heavy)

    def test_risk_exit_uses_prior_completed_bar(self) -> None:
        candles = [
            Candle(ts=0, open=100.0, high=100.0, low=100.0, close=100.0, volume=0.0),
            Candle(ts=60_000, open=100.0, high=100.0, low=98.0, close=100.0, volume=0.0),
            Candle(ts=120_000, open=99.0, high=110.0, low=99.0, close=110.0, volume=0.0),
        ]
        args = SimpleNamespace(
            starting_equity=100.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            cost_stress_multiplier=1.0,
            holding_cost_bps_per_day=0.0,
            margin_pct=100.0,
            leverage=1.0,
        )

        stopped = simulate_segment(candles, [0, 1, 1], 1, 3, args, {"stop_loss_bps": 100})
        unstopped = simulate_segment(candles, [0, 1, 1], 1, 3, args)

        self.assertEqual(stopped.trades, 1)
        self.assertLess(stopped.return_pct, unstopped.return_pct)

    def test_walk_forward_windows_are_chronological(self) -> None:
        windows = build_windows(total_bars=12, train_bars=4, test_bars=2, step_bars=2)

        self.assertEqual(
            [(item.train_start, item.train_end, item.test_start, item.test_end) for item in windows],
            [(1, 5, 5, 7), (3, 7, 7, 9), (5, 9, 9, 11)],
        )

    def test_walk_forward_selects_by_train_segment_before_test(self) -> None:
        candles = [
            Candle(ts=index * 60_000, open=100.0 + index, high=101.0 + index, low=99.0 + index, close=100.0 + index, volume=0.0)
            for index in range(12)
        ]
        args = SimpleNamespace(
            min_bars=6,
            train_bars=4,
            test_bars=2,
            step_bars=2,
            select_top=1,
            min_train_trades=1,
            min_train_profit_factor=1.0,
            min_test_profit_factor=1.0,
            min_test_trades=1,
            max_test_drawdown_pct=100.0,
            regime_filter="off",
            regime_lookback=2,
            regime_vol_window=2,
            regime_trend_bps=20.0,
            regime_range_bps=5.0,
            regime_high_vol_bps=10.0,
            starting_equity=100.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            margin_pct=100.0,
            leverage=1.0,
        )
        specs = [
            SimpleNamespace(name="winner_in_train", family="test", params={"id": "a"}),
            SimpleNamespace(name="winner_in_test", family="test", params={"id": "b"}),
        ]

        def fake_targets(_candles, spec):
            if spec.name == "winner_in_train":
                return [0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 0]
            return [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1]

        with patch("strategy_walk_forward.strategy_grid", return_value=specs), patch(
            "strategy_walk_forward.strategy_targets",
            side_effect=fake_targets,
        ):
            rows = run_walk_forward({"AAA-USDT-SWAP": candles}, args)

        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.strategy == "winner_in_train" for row in rows))
        self.assertEqual([row.window.index for row in rows], [1, 2, 3])

    def test_default_regime_variant_preserves_unfiltered_targets(self) -> None:
        args = SimpleNamespace(regime_filter="off")

        self.assertEqual(regime_variants(args)[0].name, "all")
        self.assertEqual(filter_targets_by_regime([0, 1, -1], [{"all"}, {"range"}, {"trend"}], ("all",)), [0, 1, -1])

    def test_regime_membership_uses_prior_bars_only(self) -> None:
        candles = [
            Candle(ts=index, open=float(close), high=float(close), low=float(close), close=float(close), volume=0.0)
            for index, close in enumerate([100, 100, 100, 100, 150])
        ]
        args = SimpleNamespace(
            regime_lookback=2,
            regime_vol_window=2,
            regime_trend_bps=1000.0,
            regime_range_bps=10.0,
            regime_high_vol_bps=500.0,
        )

        memberships = build_regime_memberships(candles, args)

        self.assertIn("range", memberships[4])
        self.assertNotIn("trend_up", memberships[4])

    def test_cross_sectional_momentum_uses_prior_bar_returns_only(self) -> None:
        a = [
            Candle(ts=index, open=float(close), high=float(close), low=float(close), close=float(close), volume=0.0)
            for index, close in enumerate([100, 100, 120, 120])
        ]
        b = [
            Candle(ts=index, open=100.0, high=100.0, low=100.0, close=100.0, volume=0.0)
            for index in range(4)
        ]

        targets = cross_sectional_momentum_targets(
            {"AAA-USDT-SWAP": a, "BBB-USDT-SWAP": b},
            {"lookback": 1, "top_k": 1, "threshold_bps": 1},
            4,
        )

        self.assertEqual(targets["AAA-USDT-SWAP"][2], 0)
        self.assertEqual(targets["AAA-USDT-SWAP"][3], 1)
        self.assertEqual(targets["BBB-USDT-SWAP"][3], 0)

    def test_funding_daily_bps_from_settlement_history(self) -> None:
        points = [
            SimpleNamespace(ts=index * 14_400_000, rate=0.0001, realized_rate=0.0001)
            for index in range(12)
        ]

        daily_bps = funding_daily_bps(points)

        # 1 bp per 4h settlement -> 6 settlements/day -> 6 bps/day.
        self.assertAlmostEqual(daily_bps, 6.0, places=6)

    def test_funding_daily_bps_requires_minimum_history(self) -> None:
        points = [SimpleNamespace(ts=index * 14_400_000, rate=0.0001, realized_rate=0.0001) for index in range(3)]

        self.assertIsNone(funding_daily_bps(points))

    def test_instrument_cost_args_applies_funding_and_slippage_floors(self) -> None:
        args = SimpleNamespace(
            holding_cost_bps_per_day=1.0,
            slippage_bps=2.0,
            funding_daily_bps_map={"AAA-USDT-SWAP": 4.5},
            slippage_bps_map={"AAA-USDT-SWAP": 6.25},
        )

        inst_args = instrument_cost_args(args, "AAA-USDT-SWAP")
        untouched = instrument_cost_args(args, "BBB-USDT-SWAP")

        self.assertEqual(inst_args.holding_cost_bps_per_day, 4.5)
        self.assertEqual(inst_args.slippage_bps, 6.25)
        self.assertIs(untouched, args)


if __name__ == "__main__":
    unittest.main()
