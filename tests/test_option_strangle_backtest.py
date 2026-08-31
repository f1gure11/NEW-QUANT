from __future__ import annotations

import unittest

from option_strangle_backtest import (
    HOUR_MS,
    BacktestConfig,
    Bar,
    OptionPair,
    bs_price,
    candidate_strikes,
    greeks_from_price,
    implied_volatility,
    nearest_pair,
    run_trade,
)


class OptionStrangleBacktestTests(unittest.TestCase):
    def test_implied_volatility_recovers_black_scholes_input(self) -> None:
        price = bs_price(100.0, 100.0, 7 / 365.25, 0.75, "C")
        inferred = implied_volatility(price, 100.0, 100.0, 7 / 365.25, "C")
        self.assertIsNotNone(inferred)
        self.assertAlmostEqual(inferred or 0.0, 0.75, places=6)
        delta, gamma, theta = greeks_from_price(price, 100.0, 100.0, 7 / 365.25, "C")
        self.assertGreater(delta, 0.5)
        self.assertGreater(gamma, 0.0)
        self.assertLess(theta, 0.0)

    def test_candidate_strikes_cover_symmetric_otm_targets(self) -> None:
        strikes = candidate_strikes("BTC", 20_000.0)
        self.assertIn(20_000.0, strikes)
        self.assertLessEqual(min(strikes), 18_400.0)
        self.assertGreaterEqual(max(strikes), 21_600.0)

    def test_nearest_pair_selects_otm_call_and_put(self) -> None:
        expiry = 1_000_000_000
        entry = expiry - 24 * HOUR_MS
        exit_ts = expiry - HOUR_MS
        charts = {}
        for strike in candidate_strikes("BTC", 20_000.0):
            for option_type in ("C", "P"):
                name = f"BTC-12JAN70-{strike:g}-{option_type}"
                charts[name] = (
                    Bar(entry, 0.01, 1.0),
                    Bar(exit_ts, 0.008, 1.0),
                )
        pair = nearest_pair("BTC", expiry, 20_000.0, 2.0, charts, entry, exit_ts, 6)
        self.assertIsNotNone(pair)
        assert pair is not None
        self.assertGreaterEqual(pair.call_strike, 20_000.0)
        self.assertLessEqual(pair.put_strike, 20_000.0)
        self.assertNotEqual(pair.call_strike, pair.put_strike)

    def test_trade_respects_rehedge_cap(self) -> None:
        expiry = 100 * HOUR_MS
        entry = expiry - 24 * HOUR_MS
        exit_ts = expiry - HOUR_MS
        underlying = tuple(
            Bar(entry + index * HOUR_MS, 100.0 + (8.0 if index % 2 else -8.0), 1.0)
            for index in range(24)
        )
        call_bars = tuple(Bar(item.ts, 0.04 + index * 0.001, 1.0) for index, item in enumerate(underlying))
        put_bars = tuple(Bar(item.ts, 0.04 + (23 - index) * 0.001, 1.0) for index, item in enumerate(underlying))
        pair = OptionPair(
            call_name="TEST-C",
            put_name="TEST-P",
            call_strike=102.0,
            put_strike=98.0,
            target_otm_pct=2.0,
            actual_call_otm_pct=2.0,
            actual_put_otm_pct=2.0,
            call_bars=call_bars,
            put_bars=put_bars,
        )
        row = run_trade(
            "BTC",
            expiry,
            underlying,
            pair,
            BacktestConfig(max_rehedges=2, hedge_interval_hours=1),
            "test",
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertLessEqual(row.rehedges, 2)
        self.assertTrue(row.return_on_premium_pct == row.return_on_premium_pct)


if __name__ == "__main__":
    unittest.main()
