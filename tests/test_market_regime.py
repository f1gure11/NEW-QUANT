from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backtest.okx_grid_backtest import Candle, GridBacktestConfig, Position, allowed_open_sides
import backtest.okx_grid_backtest as grid_backtest
import auto_grid_bot
from market_regime import FEATURE_COLUMNS, RegimeSignal, add_features, candles_to_frame, rules_signal, training_matrix


def trend_candles(count: int = 80) -> list[Candle]:
    candles = []
    for index in range(count):
        close = Decimal("100") + Decimal(index) / Decimal("5")
        candles.append(
            Candle(
                ts=1_800_000_000_000 + index * 60_000,
                open=close - Decimal("0.05"),
                high=close + Decimal("0.3"),
                low=close - Decimal("0.1"),
                close=close,
                volume=Decimal("1000"),
            )
        )
    return candles


def range_candles(count: int = 80) -> list[Candle]:
    candles = []
    for index in range(count):
        close = Decimal("100") + Decimal(index % 6 - 3) / Decimal("20")
        candles.append(
            Candle(
                ts=1_800_000_000_000 + index * 60_000,
                open=close,
                high=close + Decimal("0.1"),
                low=close - Decimal("0.1"),
                close=close,
                volume=Decimal("1000"),
            )
        )
    return candles


class MarketRegimeTest(unittest.TestCase):
    def test_features_and_labels_are_built_from_candles(self) -> None:
        frame = candles_to_frame(trend_candles())
        features = add_features(frame)
        x, y = training_matrix([frame])

        self.assertTrue(set(FEATURE_COLUMNS).issubset(features.columns))
        self.assertFalse(x.empty)
        self.assertTrue(set(y.unique()) <= {"trend_up", "trend_down", "range"})

    def test_rules_signal_allows_trend_direction_only(self) -> None:
        signal = rules_signal(trend_candles())

        self.assertIn(signal.state, {"trend_up", "mixed", "range"})
        if signal.state == "trend_up":
            self.assertEqual(signal.allowed_open_sides, ["long"])

    def test_backtest_market_regime_filter_can_block_new_opens(self) -> None:
        config = GridBacktestConfig(market_regime_filter="rules", one_way_open=False)
        sides = allowed_open_sides(
            config,
            trend_candles(),
            Position(),
            Position(),
            Decimal("116"),
            Decimal("100"),
        )

        self.assertNotIn("short", sides)

    def test_rf_model_signal_can_be_loaded_by_backtest_gate(self) -> None:
        frame = candles_to_frame(trend_candles(120) + range_candles(120))
        x, y = training_matrix([frame])
        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("rf", RandomForestClassifier(n_estimators=20, max_depth=4, random_state=7)),
            ]
        )
        model.fit(x, y)
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model.joblib"
            joblib.dump({"kind": "rf", "feature_columns": FEATURE_COLUMNS, "model": model}, model_path)
            config = GridBacktestConfig(
                market_regime_filter="rf",
                market_regime_model_path=str(model_path),
                market_regime_min_confidence=Decimal("0"),
                one_way_open=False,
            )
            sides = allowed_open_sides(config, trend_candles(), Position(), Position(), Decimal("116"), Decimal("100"))

        self.assertTrue(sides <= {"long", "short"})

    def test_backtest_market_regime_signal_is_cached_per_bar(self) -> None:
        class FakeSignal:
            allowed_open_sides = ["long"]

        config = GridBacktestConfig(market_regime_filter="rules", one_way_open=False)
        candles = trend_candles()
        grid_backtest.MARKET_REGIME_SIGNAL_CACHE.clear()
        with patch("market_regime.signal_from_candles", return_value=FakeSignal()) as mocked:
            first = allowed_open_sides(config, candles, Position(), Position(), Decimal("116"), Decimal("100"))
            second = allowed_open_sides(config, candles, Position(), Position(), Decimal("116"), Decimal("100"))

        self.assertEqual(first, {"long"})
        self.assertEqual(second, {"long"})
        self.assertEqual(mocked.call_count, 1)

    def test_backtest_market_regime_mixed_uses_price_anchor_policy(self) -> None:
        signal = RegimeSignal("mixed", "flat", 0.43, "rf", [], "rf mixed", {})
        config = GridBacktestConfig(
            market_regime_filter="rf",
            market_regime_mixed_policy="price_anchor",
            one_way_open=False,
        )
        grid_backtest.MARKET_REGIME_SIGNAL_CACHE.clear()
        with patch("market_regime.signal_from_candles", return_value=signal):
            sides = allowed_open_sides(config, trend_candles(), Position(), Position(), Decimal("99"), Decimal("100"))

        self.assertEqual(sides, {"long"})

    def test_live_market_regime_signal_logs_slots_dataclass(self) -> None:
        config = auto_grid_bot.BotConfig(
            inst_id="TEST-USDT-SWAP",
            lower=Decimal("90"),
            upper=Decimal("110"),
            leverage=Decimal("5"),
            grid_bps=Decimal("10"),
            min_net_bps=Decimal("1"),
            soft_bps=Decimal("35"),
            hard_bps=Decimal("60"),
            order_sz=Decimal("1"),
            max_position=Decimal("3"),
            max_open_orders_per_side=2,
            max_actions_per_cycle=4,
            interval=8,
            live=True,
            once=False,
            set_leverage=True,
            cancel_on_stop=True,
            ord_type="post_only",
            mode="adaptive",
            adaptive_width_bps=Decimal("420"),
            adaptive_min_width_bps=Decimal("260"),
            adaptive_max_width_bps=Decimal("1200"),
            adaptive_vol_multiplier=Decimal("12"),
            range_drift_mode="cooldown",
            range_drift_weight_bps=Decimal("2500"),
            range_drift_max_bps=Decimal("250"),
            sizing_mode="margin_pct",
            order_margin_pct=Decimal("20"),
            max_margin_pct=Decimal("70"),
            cash_reserve_pct=Decimal("10"),
            total_profit_tp=Decimal("0"),
            total_profit_tp_pct=Decimal("1.5"),
            total_profit_tp_cap=Decimal("0.4"),
            total_profit_action="checkpoint",
            min_tp_profit=Decimal("0"),
            total_loss_sl=Decimal("0"),
            total_loss_sl_pct=Decimal("4"),
            total_loss_sl_cap=Decimal("0.8"),
            position_loss_sl_bps=Decimal("700"),
            exchange_stop_enabled=True,
            exchange_stop_bps=Decimal("800"),
            exchange_stop_trigger_px_type="mark",
            exchange_stop_reprice_bps=Decimal("5"),
            min_tp_bps=Decimal("30"),
            missed_tp_ord_type="limit",
            missed_tp_slippage_bps=Decimal("20"),
            hard_stop_ord_type="market",
            hard_stop_slippage_bps=Decimal("50"),
            risk_cooldown=60,
            recenter_on_cooldown=True,
            trend_filter="off",
            trend_lookback=8,
            trend_threshold_bps=Decimal("70"),
            market_regime_filter="rf",
            market_regime_model_path="/tmp/model.joblib",
            market_regime_min_confidence=Decimal("0.52"),
            market_regime_mixed_policy="price_anchor",
            regime_filter="off",
            regime_bar="15m",
            regime_short_ma=5,
            regime_long_ma=20,
            regime_diff_bps=Decimal("50"),
            regime_confirm_bars=3,
            one_way_open=False,
            bot_started_ms=1,
            rolling_adaptive_enabled=False,
            rolling_adaptive_window=20,
            rolling_adaptive_low_vol_bps=Decimal("3"),
            rolling_adaptive_high_vol_bps=Decimal("25"),
            rolling_adaptive_min_leverage=Decimal("3"),
            rolling_adaptive_max_leverage=Decimal("7"),
            rolling_adaptive_min_grid_bps=Decimal("8"),
            rolling_adaptive_max_grid_bps=Decimal("36"),
            rolling_adaptive_grid_vol_multiplier=Decimal("1"),
            rolling_adaptive_min_width_bps=Decimal("260"),
            rolling_adaptive_max_width_bps=Decimal("1200"),
            rolling_adaptive_width_vol_multiplier=Decimal("14"),
            rolling_adaptive_min_order_margin_pct=Decimal("12"),
            rolling_adaptive_max_order_margin_pct=Decimal("22"),
            rolling_adaptive_min_max_margin_pct=Decimal("55"),
            rolling_adaptive_max_max_margin_pct=Decimal("95"),
            rolling_adaptive_stop_vol_multiplier=Decimal("26"),
            rolling_adaptive_min_stop_bps=Decimal("700"),
            rolling_adaptive_max_stop_bps=Decimal("1300"),
            rolling_adaptive_min_tp_bps=Decimal("30"),
            rolling_adaptive_max_tp_bps=Decimal("120"),
            rolling_adaptive_tp_grid_multiplier=Decimal("1.6"),
            rolling_adaptive_min_total_profit_tp_pct=Decimal("0.8"),
            rolling_adaptive_max_total_profit_tp_pct=Decimal("3"),
            rolling_adaptive_min_total_loss_sl_pct=Decimal("3"),
            rolling_adaptive_max_total_loss_sl_pct=Decimal("8"),
        )
        config.private_cache["marketRegimeCandles"] = trend_candles()
        signal = RegimeSignal("trend_up", "up", 0.81, "rf", ["long"], "rf trend_up", {"ret_20_bps": 120.0})

        with patch("market_regime.signal_from_candles", return_value=signal), patch.object(auto_grid_bot, "log_event") as mocked_log:
            sides, note = auto_grid_bot.market_regime_open_sides(
                config,
                {"long": Decimal("0"), "short": Decimal("0")},
                Decimal("101"),
                Decimal("100"),
            )

        self.assertEqual(sides, {"long"})
        self.assertIn("market-regime rf state=trend_up", note)
        mocked_log.assert_called_once()
        self.assertEqual(mocked_log.call_args.args[1]["state"], "trend_up")
        self.assertEqual(mocked_log.call_args.args[1]["allowed_open_sides"], ["long"])

    def test_live_market_regime_mixed_uses_price_anchor_policy(self) -> None:
        config = auto_grid_bot.BotConfig(
            inst_id="TEST-USDT-SWAP",
            lower=Decimal("90"),
            upper=Decimal("110"),
            leverage=Decimal("5"),
            grid_bps=Decimal("10"),
            min_net_bps=Decimal("1"),
            soft_bps=Decimal("35"),
            hard_bps=Decimal("60"),
            order_sz=Decimal("1"),
            max_position=Decimal("3"),
            max_open_orders_per_side=2,
            max_actions_per_cycle=2,
            interval=1,
            live=False,
            once=True,
            set_leverage=False,
            cancel_on_stop=True,
            ord_type="post_only",
            mode="adaptive",
            adaptive_width_bps=Decimal("420"),
            adaptive_min_width_bps=Decimal("260"),
            adaptive_max_width_bps=Decimal("1200"),
            adaptive_vol_multiplier=Decimal("12"),
            range_drift_mode="cooldown",
            range_drift_weight_bps=Decimal("2500"),
            range_drift_max_bps=Decimal("250"),
            sizing_mode="fixed",
            order_margin_pct=Decimal("25"),
            max_margin_pct=Decimal("75"),
            cash_reserve_pct=Decimal("10"),
            total_profit_tp=Decimal("0"),
            total_profit_tp_pct=Decimal("0"),
            total_profit_tp_cap=Decimal("0"),
            total_profit_action="checkpoint",
            min_tp_profit=Decimal("0"),
            total_loss_sl=Decimal("0"),
            total_loss_sl_pct=Decimal("0"),
            total_loss_sl_cap=Decimal("0"),
            position_loss_sl_bps=Decimal("700"),
            exchange_stop_enabled=False,
            exchange_stop_bps=Decimal("800"),
            exchange_stop_trigger_px_type="mark",
            exchange_stop_reprice_bps=Decimal("5"),
            min_tp_bps=Decimal("30"),
            missed_tp_ord_type="limit",
            missed_tp_slippage_bps=Decimal("20"),
            hard_stop_ord_type="market",
            hard_stop_slippage_bps=Decimal("50"),
            risk_cooldown=60,
            recenter_on_cooldown=True,
            trend_filter="off",
            trend_lookback=8,
            trend_threshold_bps=Decimal("70"),
            market_regime_filter="rf",
            market_regime_model_path="/tmp/model.joblib",
            market_regime_min_confidence=Decimal("0.52"),
            market_regime_mixed_policy="price_anchor",
            regime_filter="off",
            regime_bar="15m",
            regime_short_ma=5,
            regime_long_ma=20,
            regime_diff_bps=Decimal("50"),
            regime_confirm_bars=3,
            one_way_open=False,
            bot_started_ms=1,
            rolling_adaptive_enabled=False,
            rolling_adaptive_window=20,
            rolling_adaptive_low_vol_bps=Decimal("3"),
            rolling_adaptive_high_vol_bps=Decimal("25"),
            rolling_adaptive_min_leverage=Decimal("3"),
            rolling_adaptive_max_leverage=Decimal("7"),
            rolling_adaptive_min_grid_bps=Decimal("8"),
            rolling_adaptive_max_grid_bps=Decimal("36"),
            rolling_adaptive_grid_vol_multiplier=Decimal("1"),
            rolling_adaptive_min_width_bps=Decimal("260"),
            rolling_adaptive_max_width_bps=Decimal("1200"),
            rolling_adaptive_width_vol_multiplier=Decimal("14"),
            rolling_adaptive_min_order_margin_pct=Decimal("12"),
            rolling_adaptive_max_order_margin_pct=Decimal("22"),
            rolling_adaptive_min_max_margin_pct=Decimal("55"),
            rolling_adaptive_max_max_margin_pct=Decimal("95"),
            rolling_adaptive_stop_vol_multiplier=Decimal("26"),
            rolling_adaptive_min_stop_bps=Decimal("700"),
            rolling_adaptive_max_stop_bps=Decimal("1300"),
            rolling_adaptive_min_tp_bps=Decimal("30"),
            rolling_adaptive_max_tp_bps=Decimal("120"),
            rolling_adaptive_tp_grid_multiplier=Decimal("1.6"),
            rolling_adaptive_min_total_profit_tp_pct=Decimal("0.8"),
            rolling_adaptive_max_total_profit_tp_pct=Decimal("3"),
            rolling_adaptive_min_total_loss_sl_pct=Decimal("3"),
            rolling_adaptive_max_total_loss_sl_pct=Decimal("8"),
        )
        signal = RegimeSignal("mixed", "flat", 0.41, "rf", [], "rf mixed", {})

        with patch("market_regime.signal_from_candles", return_value=signal):
            sides, note = auto_grid_bot.market_regime_open_sides(
                config,
                {"long": Decimal("0"), "short": Decimal("0")},
                Decimal("101"),
                Decimal("100"),
            )

        self.assertEqual(sides, {"short"})
        self.assertIn("mixed price-anchor short", note)


if __name__ == "__main__":
    unittest.main()
