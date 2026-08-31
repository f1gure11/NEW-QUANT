from __future__ import annotations

import math
import unittest

from option_strangle_backtest import HOUR_MS, Bar, bs_price
from slow_factor_tail_hedge_research import (
    ENTRY_HOURS,
    FactorProfile,
    HedgeVariant,
    OptionWing,
    aggregate_rows,
    candidate_option_strikes,
    sample_for_expiry,
    simulate_window,
)


class SlowFactorTailHedgeResearchTests(unittest.TestCase):
    def test_chronological_sample_boundaries(self) -> None:
        self.assertEqual([sample_for_expiry(index, 16) for index in (0, 7, 8, 11, 12, 15)], ["train", "train", "validation", "validation", "test", "test"])

    def test_candidate_strikes_stay_on_the_otm_side(self) -> None:
        puts = candidate_option_strikes("BTC", 50_000.0, "P")
        calls = candidate_option_strikes("BTC", 50_000.0, "C")
        self.assertTrue(puts and all(0 < item < 50_000.0 for item in puts))
        self.assertTrue(calls and all(item > 50_000.0 for item in calls))

    def test_fixed_iv_mark_respects_intrinsic_direction(self) -> None:
        put = OptionWing("BTC-X-40000-P", "P", 40_000.0, 15.0, 20.0, 500.0, 0.6, 0.0)
        calm = bs_price(50_000.0, put.strike, 1 / 12, put.entry_iv, "P")
        crash = bs_price(30_000.0, put.strike, 1 / 12, put.entry_iv, "P")
        self.assertGreater(crash, calm)

    def test_deep_otm_wings_reduce_synthetic_crash_drawdown(self) -> None:
        expiry = 2_000_000_000_000
        entry = expiry - ENTRY_HOURS * HOUR_MS
        warmup = 180
        start = entry - warmup * HOUR_MS
        bars = []
        for index in range(warmup + ENTRY_HOURS):
            ts = start + index * HOUR_MS
            price = 100.0 * math.exp(index * 0.0001)
            if index == warmup + ENTRY_HOURS - 1:
                price *= 0.50
            bars.append(Bar(ts, price, 1.0))
        profile = FactorProfile("test", (12, 24, 48, 96))
        put = OptionWing("X-P", "P", 85.0, 15.0, 15.0, 0.25, 0.8, 0.0)
        call = OptionWing("X-C", "C", 115.0, 15.0, 15.0, 0.25, 0.8, 0.0)
        unhedged = simulate_window(
            base="BTC",
            expiry_ms=expiry,
            sample="test",
            bars=tuple(bars),
            profile=profile,
            hedge=HedgeVariant("unhedged", 0.0, 0.0),
            study="tail_hedge",
        )
        hedged = simulate_window(
            base="BTC",
            expiry_ms=expiry,
            sample="test",
            bars=tuple(bars),
            profile=profile,
            hedge=HedgeVariant("hedged", 1.0, 500.0),
            put=put,
            call=call,
            study="tail_hedge",
        )
        self.assertLess(hedged.max_drawdown_pct, unhedged.max_drawdown_pct)

    def test_aggregate_keeps_studies_separate(self) -> None:
        expiry = 2_000_000_000_000
        entry = expiry - ENTRY_HOURS * HOUR_MS
        bars = tuple(Bar(entry - 180 * HOUR_MS + index * HOUR_MS, 100.0 + index * 0.01, 1.0) for index in range(180 + ENTRY_HOURS))
        row = simulate_window(
            base="BTC",
            expiry_ms=expiry,
            sample="train",
            bars=bars,
            profile=FactorProfile("test", (12, 24, 48, 96)),
            hedge=HedgeVariant("unhedged", 0.0, 0.0),
            study="factor_period",
        )
        aggregate = aggregate_rows([row])[0]
        self.assertEqual((aggregate["study"], aggregate["count"]), ("factor_period", 1))


if __name__ == "__main__":
    unittest.main()
