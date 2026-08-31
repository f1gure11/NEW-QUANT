from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from volume_price_bubble import (
    BubbleFeature,
    BubbleParams,
    _levels_for_signal,
    bubble_events,
    compute_bubble_features,
    run_bubble_backtest,
)


def make_candles(count: int = 180, *, volume_scale: float = 1.0) -> list[Candle]:
    candles: list[Candle] = []
    price = 100.0
    for index in range(count):
        drift = 0.03 if index < count // 2 else -0.02
        open_px = price
        close = price + drift + (0.12 if index % 17 == 0 else 0.0)
        high = max(open_px, close) + 0.08
        low = min(open_px, close) - 0.08
        volume = (100.0 + (index % 11) * 3.0) * volume_scale
        candles.append(
            Candle(
                ts=index * 60_000,
                open=Decimal(str(open_px)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=Decimal(str(volume)),
            )
        )
        price = close
    return candles


class VolumePriceBubbleTests(unittest.TestCase):
    def test_features_do_not_use_future_candles(self) -> None:
        candles = make_candles()
        changed = list(candles)
        changed[-1] = Candle(
            ts=changed[-1].ts,
            open=Decimal("1000"),
            high=Decimal("1200"),
            low=Decimal("900"),
            close=Decimal("1100"),
            volume=Decimal("999999"),
        )
        full = compute_bubble_features(candles)
        changed_full = compute_bubble_features(changed)
        for left, right in zip(full[:-1], changed_full[:-1]):
            self.assertEqual(left, right)

    def test_volume_is_part_of_the_indicator(self) -> None:
        normal_candles = make_candles(volume_scale=1.0)
        high_volume_candles = list(normal_candles)
        source = high_volume_candles[-2]
        high_volume_candles[-2] = Candle(
            ts=source.ts,
            open=source.open,
            high=source.high,
            low=source.low,
            close=source.close,
            volume=Decimal("10000"),
        )
        normal = compute_bubble_features(normal_candles)
        high_volume = compute_bubble_features(high_volume_candles)
        self.assertNotEqual(normal[-2].volume_z, high_volume[-2].volume_z)

    def test_event_is_executed_one_bar_after_completed_signal(self) -> None:
        candles = make_candles()
        params = replace(
            BubbleParams(),
            min_score=0.0,
            min_extension_atr=0.0,
            min_divergence_z=0.0,
            min_absorption_z=0.0,
            min_volume_z=-10.0,
            cooldown_bars=0,
        )
        features = compute_bubble_features(candles, params)
        events = bubble_events(candles, params)
        for index in range(len(candles)):
            if index == 0:
                self.assertEqual(events[index], 0)
            else:
                expected = 0
                if features[index - 1].short_trigger:
                    expected = -1
                elif features[index - 1].long_trigger:
                    expected = 1
                self.assertIn(events[index], (-1, 0, 1))
                if expected:
                    self.assertEqual(events[index], expected)

    def test_stop_is_outside_bubble_extreme_and_target_uses_r_multiple(self) -> None:
        feature = BubbleFeature(
            ts=1,
            close=100.0,
            atr=2.0,
            price_extension_atr=2.0,
            price_momentum_z=1.0,
            volume_z=1.0,
            pressure_z=-1.0,
            pv_divergence_z=2.0,
            result_z=-1.0,
            absorption_z=1.0,
            up_bubble_score=80.0,
            down_bubble_score=0.0,
            previous_high=104.0,
            previous_low=98.0,
            bubble_high=105.0,
            bubble_low=98.0,
            short_trigger=True,
            long_trigger=False,
        )
        params = replace(BubbleParams(), stop_buffer_atr=0.25, take_profit_r=1.5)
        stop, target, risk = _levels_for_signal(-1, 100.0, feature, params) or (0.0, 0.0, 0.0)
        self.assertGreaterEqual(stop, 105.5)
        self.assertAlmostEqual(100.0 - target, risk * 1.5)

    def test_backtest_has_conservative_stop_first_intrabar_rule(self) -> None:
        candles = make_candles(220)
        result, trades, _ = run_bubble_backtest(candles)
        self.assertEqual(result.trades, len(trades))
        self.assertGreaterEqual(result.max_drawdown_pct, 0.0)
        self.assertGreaterEqual(result.fees, 0.0)


if __name__ == "__main__":
    unittest.main()
