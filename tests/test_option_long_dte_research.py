from __future__ import annotations

import unittest

from option_long_dte_research import entry_volatility, passes_filter, realized_volatility, selected_by_training
from option_strangle_backtest import HOUR_MS, Bar, OptionPair, bs_price


class OptionLongDteResearchTests(unittest.TestCase):
    def test_realized_volatility_uses_only_pre_entry_bars(self) -> None:
        entry = 200 * HOUR_MS
        bars = tuple(
            Bar(entry - (30 - index) * HOUR_MS, 100.0 * (1.002 ** index), 1.0)
            for index in range(31)
        ) + (Bar(entry + HOUR_MS, 1_000.0, 1.0),)
        value = realized_volatility(bars, entry, lookback_hours=30)
        self.assertIsNotNone(value)
        self.assertLess(value or 0.0, 0.01)

    def test_entry_volatility_recovers_pair_iv_with_stale_trade(self) -> None:
        spot = 100.0
        entry = 100 * HOUR_MS
        years = 72 / (365.25 * 24.0)
        call_price = bs_price(spot, 102.0, years, 0.8, "C")
        put_price = bs_price(spot, 98.0, years, 0.8, "P")
        pair = OptionPair(
            call_name="TEST-C",
            put_name="TEST-P",
            call_strike=102.0,
            put_strike=98.0,
            target_otm_pct=2.0,
            actual_call_otm_pct=2.0,
            actual_put_otm_pct=2.0,
            call_bars=(Bar(entry - HOUR_MS, call_price / spot, 1.0),),
            put_bars=(Bar(entry - HOUR_MS, put_price / spot, 1.0),),
        )
        value = entry_volatility(pair, spot, entry, 72)
        self.assertIsNotNone(value)
        self.assertAlmostEqual(value or 0.0, 0.8, places=6)

    def test_volatility_filters_are_disjoint_at_expensive_boundary(self) -> None:
        self.assertTrue(passes_filter("all", 1.5))
        self.assertTrue(passes_filter("iv_rv_le_1.0", 1.0))
        self.assertTrue(passes_filter("iv_rv_le_1.2", 1.2))
        self.assertFalse(passes_filter("iv_rv_gt_1.2", 1.2))
        self.assertTrue(passes_filter("iv_rv_gt_1.2", 1.2001))

    def test_training_selection_rejects_sparse_overfit_and_negative_edge(self) -> None:
        def row(count: int, median: float, vol_filter: str, otm: float) -> dict[str, object]:
            return {
                "underlying": "BTC",
                "sample": "train",
                "option_slippage_bps": 100.0,
                "count": count,
                "vol_filter": vol_filter,
                "median_return_on_premium_pct": median,
                "mean_return_on_premium_pct": median,
                "entry_hours_before_expiry": 72,
                "target_otm_pct": otm,
                "hedge_variant": "baseline",
                "delta_threshold_pct": 5.0,
                "hedge_interval_hours": 6,
                "max_rehedges": 12,
            }

        selected = selected_by_training(
            [
                row(8, -5.0, "all", 0.0),
                row(6, -2.0, "iv_rv_le_1.2", 1.0),
                row(2, 200.0, "iv_rv_gt_1.2", 2.0),
            ]
        )["BTC"]
        self.assertEqual(selected["targetOtmPct"], 1.0)
        self.assertEqual(selected["minimumTrainingCount"], 6)
        self.assertEqual(selected["decision"], "reject_no_positive_training_edge")


if __name__ == "__main__":
    unittest.main()
