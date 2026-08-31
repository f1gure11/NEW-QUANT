from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from option_strangle_backtest import HOUR_MS, Bar, bs_price
from deribit_factor_research import (
    FactorConfig,
    FactorObservation,
    directional_signal,
    evaluate_directional,
    infer_leg,
    monthly_expiries,
    sample_labels,
)


def observation(**overrides: object) -> FactorObservation:
    values: dict[str, object] = {
        "underlying": "BTC",
        "expiry_ts": 1000,
        "expiry": "1970-01-01T00:00:01Z",
        "sample": "train",
        "entry_ts": 0,
        "entry_time": "1970-01-01T00:00:00Z",
        "entry_spot": 100.0,
        "exit_spot": 102.0,
        "latency_entry_spot": 101.0,
        "latency_exit_spot": 102.0,
        "realized_vol_7d": 0.5,
        "atm_iv": 0.6,
        "iv_rv_ratio": 1.2,
        "variance_risk_premium": 0.11,
        "atm_call_put_iv_spread": 0.02,
        "risk_reversal_25d": -0.01,
        "butterfly_25d": 0.01,
        "call_put_volume_log_ratio": 0.5,
        "momentum_24h": 0.01,
        "momentum_7d": 0.02,
        "max_surface_stale_hours": 1.0,
        "atm_strike": 100.0,
        "call_25d_strike": 105.0,
        "put_25d_strike": 95.0,
        "future_return_24h": 0.02,
        "future_realized_vol_24h": 0.7,
        "long_straddle_return_on_premium_pct": 10.0,
        "long_straddle_stress_return_on_premium_pct": 5.0,
    }
    values.update(overrides)
    return FactorObservation(**values)  # type: ignore[arg-type]


class DeribitFactorResearchTests(unittest.TestCase):
    def test_monthly_expiries_are_last_friday_at_0800_utc(self) -> None:
        values = monthly_expiries("2023-01", "2023-03")
        parsed = [datetime.fromtimestamp(value / 1000, timezone.utc) for value in values]
        self.assertEqual([(row.month, row.day, row.hour) for row in parsed], [(1, 27, 8), (2, 24, 8), (3, 31, 8)])
        self.assertTrue(all(row.weekday() == 4 for row in parsed))

    def test_sample_labels_are_chronological(self) -> None:
        values = list(range(8))
        labels = sample_labels(values)
        self.assertEqual([labels[value] for value in values], ["train"] * 4 + ["validation"] * 2 + ["test"] * 2)

    def test_infer_leg_never_uses_post_signal_trade(self) -> None:
        timestamp = 100 * HOUR_MS
        spot = 100.0
        years = 72 / (365.25 * 24.0)
        price = bs_price(spot, 100.0, years, 0.8, "C") / spot
        bars = (
            Bar(timestamp - HOUR_MS, price, 2.0),
            Bar(timestamp + HOUR_MS, price * 5.0, 100.0),
        )
        leg = infer_leg(
            "BTC-TEST-100-C",
            "C",
            100.0,
            bars,
            timestamp=timestamp,
            spot=spot,
            years=years,
            max_stale_hours=6,
        )
        self.assertIsNotNone(leg)
        self.assertAlmostEqual(leg.iv if leg else 0.0, 0.8, places=6)
        self.assertEqual(leg.trailing_volume if leg else 0.0, 2.0)

    def test_paper_factor_orientations_are_fixed(self) -> None:
        row = observation()
        thresholds = {"vrp_median": 0.2}
        cfg = FactorConfig()
        self.assertEqual(directional_signal(row, "atm_iv_spread", thresholds, cfg), 1)
        self.assertEqual(directional_signal(row, "risk_reversal_25d", thresholds, cfg), -1)
        self.assertEqual(directional_signal(row, "option_volume", thresholds, cfg), 1)
        self.assertEqual(directional_signal(row, "iv_volume_consensus", thresholds, cfg), 1)
        self.assertEqual(directional_signal(row, "rr_volume_consensus", thresholds, cfg), 0)
        self.assertEqual(directional_signal(row, "variance_risk_premium", thresholds, cfg), -1)

    def test_directional_accounting_applies_allocation_and_round_trip_cost(self) -> None:
        cfg = FactorConfig(directional_allocation_per_asset=0.10, perpetual_round_trip_bps=12.0)
        row = observation(future_return_24h=0.02)
        result = evaluate_directional(
            [row],
            "train",
            "atm_iv_spread",
            "normal",
            {"vrp_median": 0.0},
            cfg,
        )
        self.assertAlmostEqual(result.total_return_pct, 0.188, places=9)
        self.assertAlmostEqual(result.median_trade_net_bps, 188.0, places=9)
        self.assertEqual(result.trades, 1)

    def test_strict_surface_staleness_abstains(self) -> None:
        row = observation(max_surface_stale_hours=2.01)
        side = directional_signal(
            row,
            "strict_paper_majority",
            {"vrp_median": 0.0},
            FactorConfig(strict_staleness_hours=2.0),
        )
        self.assertEqual(side, 0)


if __name__ == "__main__":
    unittest.main()
