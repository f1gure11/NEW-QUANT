from __future__ import annotations

import math
import unittest
from dataclasses import replace
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from flip_grid import FlipGridConfig, FlipLot, flip_target, seed_prices, simulate_flip_grid
from funding_research import FundingPoint


def candle(index: int, open_px: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        ts=1_800_000_000_000 + index * 300_000,
        open=Decimal(str(open_px)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


class FlipGridTest(unittest.TestCase):
    def config(self) -> FlipGridConfig:
        return FlipGridConfig(
            starting_equity=100.0,
            allocation_pct=60.0,
            leverage=1.0,
            chains=2,
            seed_step_bps=100.0,
            flip_take_profit_bps=100.0,
            maker_fee_bps=1.0,
            taker_fee_bps=5.0,
            liquidation_slippage_bps=1.0,
            fill_buffer_bps=0.0,
            lot_size=0.001,
            min_size=0.001,
            tick_size=0.01,
        )

    def test_long_tp_flips_to_short_at_same_price(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.1, 99.8, 100.0),
            candle(2, 100.0, 101.2, 100.0, 101.0),
        ]

        simulation = simulate_flip_grid(rows, self.config())
        actions = [fill.action for fill in simulation.fills]

        self.assertIn("flip_close", actions)
        self.assertIn("flip_open", actions)
        self.assertEqual(simulation.result.long_completions, 1)
        self.assertEqual(simulation.result.short_completions, 0)

    def test_new_reverse_leg_cannot_complete_on_same_bar(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.1, 99.8, 100.0),
            candle(2, 100.0, 102.0, 98.0, 100.0),
        ]

        simulation = simulate_flip_grid(rows, self.config())

        self.assertEqual(simulation.result.flips, 1)

    def test_round_trip_oscillation_harvests_both_directions(self) -> None:
        rows = [candle(0, 100.0, 100.0, 100.0, 100.0)]
        for index in range(1, 80):
            close = 100.0 + math.sin(index * math.pi / 2.0) * 1.2
            rows.append(candle(index, 100.0, max(100.0, close) + 0.1, min(100.0, close) - 0.1, close))

        simulation = simulate_flip_grid(rows, self.config())

        self.assertGreater(simulation.result.long_completions, 2)
        self.assertGreater(simulation.result.short_completions, 2)
        self.assertGreater(simulation.result.return_pct, 0.0)

    def test_monotonic_breakout_leaves_countertrend_loss(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.2, 99.8, 100.0),
        ]
        for index in range(2, 80):
            px = 100.0 + index * 0.4
            rows.append(candle(index, px, px + 0.05, px - 0.05, px))

        simulation = simulate_flip_grid(rows, self.config())

        self.assertGreater(simulation.result.long_completions, 0)
        self.assertLess(simulation.result.terminal_unrealized, 0.0)
        self.assertLess(simulation.result.return_pct, 0.0)

    def test_positive_funding_offsets_between_mixed_sides(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.1, 98.8, 99.0),
            candle(2, 99.0, 101.2, 98.8, 101.0),
            candle(3, 101.0, 101.1, 100.8, 101.0),
        ]
        event = FundingPoint(ts=rows[3].ts, rate=0.001, realized_rate=0.001)

        funded = simulate_flip_grid(rows, self.config(), [event])
        plain = simulate_flip_grid(rows, self.config())

        self.assertNotEqual(funded.result.funding_cost, 0.0)
        self.assertNotEqual(funded.result.final_mark_equity, plain.result.final_mark_equity)

    def test_high_leverage_breakout_can_liquidate(self) -> None:
        rows = [candle(0, 100.0, 100.0, 100.0, 100.0)]
        rows.append(candle(1, 100.0, 101.2, 99.8, 101.0))
        rows.append(candle(2, 101.0, 140.0, 101.0, 140.0))

        simulation = simulate_flip_grid(rows, replace(self.config(), leverage=10.0, allocation_pct=100.0))

        self.assertTrue(simulation.result.liquidated)
        self.assertGreaterEqual(simulation.result.return_pct, -100.0)

    def test_seed_and_flip_prices_respect_tick(self) -> None:
        config = replace(self.config(), tick_size=0.1, flip_take_profit_bps=33.0)
        prices = seed_prices(100.03, config)
        target = flip_target(FlipLot(0, 1, prices[0], 1.0, 0), config)

        self.assertAlmostEqual((prices[0] / 0.1) % 1.0, 0.0)
        self.assertAlmostEqual((target / 0.1) % 1.0, 0.0)


if __name__ == "__main__":
    unittest.main()
