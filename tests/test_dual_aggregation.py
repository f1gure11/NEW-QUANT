from __future__ import annotations

import math
import unittest
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from dual_aggregation import (
    DualAggregationConfig,
    DualLot,
    book_prices,
    path_statistics,
    portfolio_snapshot,
    simulate_dual_aggregation,
)
from gex_delta_neutral_research import GexEvent, non_overlapping_forward_windows
from gex_risk_controlled_aggregation import gex_entry_gate


def candles_from_closes(closes: list[float], wick: float = 0.05) -> list[Candle]:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_price = previous if index else close
        rows.append(
            Candle(
                ts=1_800_000_000_000 + index * 300_000,
                open=Decimal(str(open_price)),
                high=Decimal(str(max(open_price, close) + wick)),
                low=Decimal(str(min(open_price, close) - wick)),
                close=Decimal(str(close)),
                volume=Decimal("1000"),
            )
        )
        previous = close
    return rows


class DualAggregationTests(unittest.TestCase):
    def base_config(self, **overrides: float | int) -> DualAggregationConfig:
        values = {
            "starting_equity": 200.0,
            "allocation_pct": 60.0,
            "leverage": 1.0,
            "tranches_per_side": 3,
            "step_bps": 100.0,
            "take_profit_bps": 50.0,
            "side_stop_bps": 0.0,
            "cooldown_bars": 0,
            "maker_fee_bps": 2.0,
            "taker_fee_bps": 5.0,
            "liquidation_slippage_bps": 2.0,
            "fill_buffer_bps": 0.0,
            "lot_size": 0.001,
            "min_size": 0.001,
            "contract_value": 1.0,
            "tick_size": 0.01,
        }
        values.update(overrides)
        return DualAggregationConfig(**values)

    def test_equal_long_short_quantity_locks_average_spread(self) -> None:
        longs = {0: DualLot(0, 98.0, 2.0, 1)}
        shorts = {0: DualLot(0, 102.0, 2.0, 1)}
        at_90 = portfolio_snapshot(longs, shorts, 90.0, 1.0)
        at_110 = portfolio_snapshot(longs, shorts, 110.0, 1.0)
        self.assertAlmostEqual(at_90[4], 8.0)
        self.assertAlmostEqual(at_110[4], 8.0)
        self.assertAlmostEqual(at_90[3], 0.0)

    def test_ladders_move_long_average_down_and_short_average_up(self) -> None:
        config = self.base_config(step_bps=200.0)
        self.assertEqual(book_prices(100.0, "long", config), [100.0, 98.0, 96.04])
        self.assertEqual(book_prices(100.0, "short", config), [100.0, 102.0, 104.04])

    def test_new_entries_cannot_take_profit_on_same_candle(self) -> None:
        candles = [
            Candle(1, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("1")),
            Candle(2, Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("1")),
        ]
        simulation = simulate_dual_aggregation(
            candles,
            self.base_config(tranches_per_side=1, take_profit_bps=50.0),
        )
        self.assertEqual(simulation.result.entries, 2)
        self.assertEqual(simulation.result.round_trips, 0)

    def test_oscillating_path_harvests_both_sides(self) -> None:
        closes = [100.0 + 2.2 * math.sin(index * 2.0 * math.pi / 24.0) for index in range(500)]
        result = simulate_dual_aggregation(candles_from_closes(closes, 0.12), self.base_config()).result
        self.assertGreater(result.return_pct, 0.0)
        self.assertGreater(result.long_round_trips, 5)
        self.assertGreater(result.short_round_trips, 5)
        self.assertFalse(result.liquidated)

    def test_monotonic_rise_accumulates_losing_short_inventory(self) -> None:
        closes = [100.0 + index * 0.08 for index in range(500)]
        result = simulate_dual_aggregation(candles_from_closes(closes), self.base_config()).result
        self.assertLess(result.return_pct, 0.0)
        self.assertGreater(result.terminal_short_layers, 0)
        self.assertGreater(result.max_abs_net_exposure_pct, 0.0)

    def test_high_leverage_one_sided_move_can_liquidate(self) -> None:
        closes = [100.0 + index * 0.25 for index in range(200)]
        config = self.base_config(
            allocation_pct=100.0,
            leverage=10.0,
            tranches_per_side=1,
            maintenance_margin_pct=1.5,
        )
        result = simulate_dual_aggregation(candles_from_closes(closes), config).result
        self.assertTrue(result.liquidated)

    def test_path_efficiency_separates_range_from_monotonic_move(self) -> None:
        ranged = candles_from_closes([100.0 + math.sin(index / 3.0) for index in range(120)])
        monotonic = candles_from_closes([100.0 + index * 0.1 for index in range(120)])
        range_variation, range_efficiency = path_statistics(ranged)
        trend_variation, trend_efficiency = path_statistics(monotonic)
        self.assertGreater(range_variation, 0.0)
        self.assertGreater(trend_variation, 0.0)
        self.assertLess(range_efficiency, trend_efficiency)
        self.assertAlmostEqual(trend_efficiency, 1.0)

    def test_gex_forward_windows_start_after_event_and_do_not_overlap(self) -> None:
        candles = [
            Candle(
                ts=index * 300_000,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
            )
            for index in range(1, 12)
        ]

        def event(ts: int) -> GexEvent:
            return GexEvent("BTC", ts, "", "", 1.0, 1.0, 1.0, 100.0, 105.0, 95.0)

        events = {"BTC": [event(450_000), event(800_000), event(1_600_000)]}
        windows = non_overlapping_forward_windows(events, {"BTC": candles}, 3)
        self.assertEqual(len(windows), 2)
        self.assertGreater(windows[0][2][0].ts, windows[0][1].event_ts)
        self.assertLess(windows[0][2][-1].ts, windows[1][2][0].ts)

    def test_entry_gate_can_hold_strategy_in_reduce_only_mode(self) -> None:
        candles = candles_from_closes([100.0 + math.sin(index / 3.0) for index in range(80)])
        gate = {candle.ts: False for candle in candles}
        result = simulate_dual_aggregation(
            candles,
            self.base_config(),
            entry_enabled_by_ts=gate,
        ).result
        self.assertEqual(result.entries, 0)
        self.assertEqual(result.return_pct, 0.0)

    def test_net_exposure_cap_constrains_one_sided_inventory(self) -> None:
        candles = candles_from_closes([100.0 + index * 0.1 for index in range(60)], wick=0.0)
        config = self.base_config(
            allocation_pct=60.0,
            tranches_per_side=1,
            fill_buffer_bps=1.0,
            max_abs_net_exposure_pct=5.0,
        )
        result = simulate_dual_aggregation(candles, config).result
        self.assertGreater(result.entries, 0)
        self.assertLess(result.max_abs_net_exposure_pct, 5.5)

    def test_inventory_timeout_closes_old_lots(self) -> None:
        candles = candles_from_closes([100.0 + index * 0.03 for index in range(80)], wick=0.0)
        config = self.base_config(
            tranches_per_side=1,
            fill_buffer_bps=1.0,
            take_profit_bps=500.0,
            inventory_timeout_bars=3,
        )
        result = simulate_dual_aggregation(candles, config).result
        self.assertGreater(result.inventory_expiries, 0)

    def test_aged_profitable_long_short_basket_exits_at_open(self) -> None:
        candles = [
            Candle(1, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("1")),
            Candle(2, Decimal("100"), Decimal("105"), Decimal("95"), Decimal("100"), Decimal("1")),
            Candle(3, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"), Decimal("1")),
        ]
        simulation = simulate_dual_aggregation(
            candles,
            self.base_config(
                take_profit_bps=500.0,
                basket_pair_start_bars=1,
                basket_pair_min_net_bps=0.0,
            ),
        )
        self.assertGreater(simulation.result.basket_pair_events, 0)
        self.assertGreater(simulation.result.basket_pair_gross_pnl, 0.0)
        self.assertTrue(any(fill.action == "basket_pair" for fill in simulation.fills))

    def test_unprofitable_equal_entry_basket_is_not_paired(self) -> None:
        candles = candles_from_closes([100.0, 100.0, 100.0], wick=0.0)
        simulation = simulate_dual_aggregation(
            candles,
            self.base_config(
                tranches_per_side=1,
                take_profit_bps=500.0,
                basket_pair_start_bars=1,
                basket_pair_min_net_bps=0.0,
            ),
        )
        self.assertEqual(simulation.result.basket_pair_events, 0)
        self.assertFalse(any(fill.action == "basket_pair" for fill in simulation.fills))

    def test_realized_harvest_credit_can_reduce_aged_dominant_inventory(self) -> None:
        closes = [100.0 + index * 0.08 + 0.8 * math.sin(index / 2.0) for index in range(80)]
        simulation = simulate_dual_aggregation(
            candles_from_closes(closes, wick=0.1),
            self.base_config(
                inventory_timeout_bars=30,
                basket_pair_start_bars=3,
                basket_pair_min_net_bps=0.0,
            ),
        )
        profit_fills = [fill for fill in simulation.fills if fill.action == "take_profit"]
        budget_fills = [fill for fill in simulation.fills if fill.action == "harvest_budget_exit"]
        self.assertTrue(profit_fills)
        self.assertTrue(budget_fills)
        self.assertGreaterEqual(budget_fills[0].ts, profit_fills[0].ts)
        self.assertGreater(simulation.result.harvest_budget_exit_events, 0)
        self.assertGreaterEqual(simulation.result.harvest_exit_credit_remaining, 0.0)

    def test_staged_reduction_partially_closes_inventory_before_expiry(self) -> None:
        candles = candles_from_closes([100.0] * 8, wick=0.0)
        simulation = simulate_dual_aggregation(
            candles,
            self.base_config(
                tranches_per_side=1,
                take_profit_bps=500.0,
                inventory_timeout_bars=4,
                staged_reduction_start_bars=1,
                staged_reduction_interval_bars=1,
                staged_reduction_fraction_pct=50.0,
            ),
        )
        staged_fills = [fill for fill in simulation.fills if fill.action == "staged_reduction"]
        self.assertGreater(simulation.result.staged_reduction_events, 0)
        self.assertTrue(staged_fills)
        self.assertTrue(all(fill.quantity > 0 for fill in staged_fills))
        self.assertGreater(simulation.result.inventory_expiries, 0)

    def test_gex_gate_uses_only_prior_fresh_positive_event_inside_walls(self) -> None:
        candles = [
            Candle(
                ts=index * 300_000,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1"),
            )
            for index in range(1, 5)
        ]
        positive = GexEvent("BTC", 450_000, "", "", 1.0, 1.0, 1.0, 100.0, 105.0, 95.0)
        future_negative = GexEvent("BTC", 900_000, "", "", -1.0, 1.0, 1.0, 100.0, 105.0, 95.0)
        gate = gex_entry_gate(
            candles,
            [positive, future_negative],
            max_age_ms=1_000_000,
            require_inside_walls=True,
        )
        self.assertTrue(gate[600_000])
        self.assertTrue(gate[900_000])
        self.assertFalse(gate[1_200_000])


if __name__ == "__main__":
    unittest.main()
