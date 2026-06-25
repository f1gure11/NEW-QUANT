from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backtest.okx_grid_backtest import Candle, GridBacktestConfig, Position, allowed_open_sides
from market_regime import FEATURE_COLUMNS, add_features, candles_to_frame, rules_signal, training_matrix


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


if __name__ == "__main__":
    unittest.main()
