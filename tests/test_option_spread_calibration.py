from __future__ import annotations

import unittest

from option_spread_calibration import (
    dte_bucket,
    fitted_value,
    half_spread_bps,
    moneyness_bucket,
    option_otm_pct,
    percentile,
)


class OptionSpreadCalibrationTests(unittest.TestCase):
    def test_half_spread_matches_midpoint_execution_cost(self) -> None:
        self.assertAlmostEqual(half_spread_bps(0.009, 0.011) or 0.0, 1_000.0)
        self.assertIsNone(half_spread_bps(0.01, 0.01))
        self.assertIsNone(half_spread_bps(0.0, 0.01))

    def test_dte_and_moneyness_buckets_match_research_windows(self) -> None:
        self.assertEqual(dte_bucket(24.0), "24h")
        self.assertEqual(dte_bucket(72.0), "72h")
        self.assertEqual(dte_bucket(168.0), "168h")
        self.assertIsNone(dte_bucket(300.0))
        self.assertEqual(moneyness_bucket(0.5), "atm")
        self.assertEqual(moneyness_bucket(1.5), "light_otm")
        self.assertEqual(moneyness_bucket(4.0), "deep_otm")
        self.assertIsNone(moneyness_bucket(-2.0))

    def test_option_otm_sign_depends_on_option_type(self) -> None:
        self.assertAlmostEqual(option_otm_pct("call", 102.0, 100.0), 2.0)
        self.assertAlmostEqual(option_otm_pct("put", 98.0, 100.0), 2.0)
        self.assertLess(option_otm_pct("put", 102.0, 100.0), 0.0)

    def test_percentile_and_linear_repricing(self) -> None:
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0, 4.0], 0.75), 3.25)
        rows = [
            {"option_slippage_bps": "50", "total_pnl_usd": "90"},
            {"option_slippage_bps": "100", "total_pnl_usd": "80"},
            {"option_slippage_bps": "200", "total_pnl_usd": "60"},
        ]
        self.assertAlmostEqual(fitted_value(rows, "total_pnl_usd", 300.0), 40.0)


if __name__ == "__main__":
    unittest.main()
