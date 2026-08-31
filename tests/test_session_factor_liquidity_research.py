from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from orderflow_rr_research import OrderFlowSnapshot
from session_factor_liquidity_research import (
    AMERICAS_PROFILES,
    feature_lookback,
    same_americas_window,
    slow_maker_grid,
)


def snapshot(ts: int) -> OrderFlowSnapshot:
    return OrderFlowSnapshot(ts, 99.0, 101.0, 100.0, 2.0, 0.0, 0.0, 0.0)


class SessionFactorLiquidityResearchTests(unittest.TestCase):
    def test_feature_lookback_uses_longest_component_window(self) -> None:
        self.assertEqual(feature_lookback("return_5_bps"), 5)
        self.assertEqual(feature_lookback("acceleration_5_30"), 30)
        self.assertEqual(feature_lookback("vol_ratio_30_240"), 240)
        self.assertEqual(feature_lookback("spread_bps"), 1)

    def test_americas_window_must_remain_inside_one_session(self) -> None:
        start = datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc)
        rows = [snapshot(int((start + timedelta(minutes=index)).timestamp() * 1_000)) for index in range(90)]
        self.assertTrue(same_americas_window(rows, 30, 15, 10))

        crossed = datetime(2026, 7, 6, 13, 20, tzinfo=timezone.utc)
        crossed_rows = [
            snapshot(int((crossed + timedelta(minutes=index)).timestamp() * 1_000))
            for index in range(90)
        ]
        self.assertFalse(same_americas_window(crossed_rows, 15, 15, 10))

    def test_profiles_tie_shorter_factors_to_shorter_holding_periods(self) -> None:
        lookbacks = [item.max_lookback for item in AMERICAS_PROFILES]
        holds = [item.max_hold_bars for item in AMERICAS_PROFILES]
        self.assertEqual(lookbacks, sorted(lookbacks))
        self.assertEqual(holds, sorted(holds))
        self.assertLess(holds[0], holds[-1])

    def test_non_americas_maker_grid_is_slow_only(self) -> None:
        grid = slow_maker_grid()
        self.assertEqual(len(grid), 96)
        self.assertGreaterEqual(min(item.vwap_window for item in grid), 144)


if __name__ == "__main__":
    unittest.main()
