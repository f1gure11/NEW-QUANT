from __future__ import annotations

import math
import unittest
from dataclasses import replace
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from funding_research import FundingPoint
from layered_aggregation import (
    LayerLot,
    LayeredConfig,
    break_even_take_profit_bps,
    layer_exit_price,
    layer_prices,
    simulate_layered_strategy,
)
from layered_aggregation_research import (
    CandidateParams,
    InstrumentSnapshot,
    minimum_starting_equity_for_params,
)


def candle(index: int, open_px: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        ts=1_800_000_000_000 + index * 300_000,
        open=Decimal(str(open_px)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


def oscillating_candles(count: int = 180, drift_per_bar: float = 0.0) -> list[Candle]:
    rows: list[Candle] = []
    for index in range(count):
        center = 100.0 + drift_per_bar * index + 1.2 * math.sin(index * math.pi / 6.0)
        rows.append(candle(index, center, center + 0.45, center - 0.45, center))
    return rows


class LayeredAggregationTest(unittest.TestCase):
    def base_config(self) -> LayeredConfig:
        return LayeredConfig(
            starting_equity=100.0,
            allocation_pct=60.0,
            leverage=1.0,
            tranches=4,
            step_bps=50.0,
            take_profit_bps=20.0,
            basket_stop_bps=0.0,
            maker_fee_bps=1.0,
            taker_fee_bps=5.0,
            stop_slippage_bps=0.0,
            fill_buffer_bps=0.0,
            lot_size=0.001,
            min_size=0.001,
        )

    def test_previous_layer_caps_take_profit(self) -> None:
        config = replace(self.base_config(), step_bps=100.0, take_profit_bps=200.0)
        prices = layer_prices(100.0, config)
        lot = LayerLot(level=2, entry_price=prices[2], quantity=1.0, entry_ts=0)

        self.assertAlmostEqual(layer_exit_price(lot, prices, config), prices[1])

    def test_short_ladder_is_above_anchor_and_reduces_toward_prior_layer(self) -> None:
        config = replace(
            self.base_config(),
            direction="short",
            step_bps=100.0,
            take_profit_bps=200.0,
        )
        prices = layer_prices(100.0, config)
        lot = LayerLot(level=2, entry_price=prices[2], quantity=1.0, entry_ts=0)

        self.assertGreater(prices[2], prices[1])
        self.assertAlmostEqual(layer_exit_price(lot, prices, config), prices[1])

    def test_new_entry_cannot_take_profit_on_same_candle(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 101.0, 98.0, 100.0),
        ]

        result = simulate_layered_strategy(rows, self.base_config())

        self.assertGreater(result.result.entries, 0)
        self.assertEqual(result.result.round_trips, 0)
        self.assertGreater(result.result.terminal_active_layers, 0)

    def test_oscillation_harvests_positive_net_profit(self) -> None:
        result = simulate_layered_strategy(oscillating_candles(), self.base_config())

        self.assertGreater(result.result.round_trips, 5)
        self.assertGreater(result.result.realized_harvest, result.result.fees)
        self.assertGreater(result.result.return_pct, 0.0)

    def test_monotonic_decline_does_not_create_fake_profit(self) -> None:
        rows = []
        for index in range(100):
            px = 100.0 - index * 0.25
            rows.append(candle(index, px, px + 0.02, px - 0.02, px))

        result = simulate_layered_strategy(rows, replace(self.base_config(), step_bps=100.0))

        self.assertEqual(result.result.round_trips, 0)
        self.assertLess(result.result.return_pct, 0.0)
        self.assertLess(result.result.terminal_unrealized, 0.0)

    def test_positive_funding_rate_charges_long_inventory(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.1, 99.8, 100.0),
            candle(2, 100.0, 100.1, 99.9, 100.0),
        ]
        event = FundingPoint(ts=rows[2].ts, rate=0.001, realized_rate=0.001)

        charged = simulate_layered_strategy(rows, self.base_config(), [event])
        uncharged = simulate_layered_strategy(rows, self.base_config())

        self.assertGreater(charged.result.funding_cost, 0.0)
        self.assertLess(charged.result.final_mark_equity, uncharged.result.final_mark_equity)

    def test_positive_funding_rate_credits_short_inventory(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.2, 99.9, 100.0),
            candle(2, 100.0, 100.1, 99.9, 100.0),
        ]
        event = FundingPoint(ts=rows[2].ts, rate=0.001, realized_rate=0.001)
        config = replace(self.base_config(), direction="short")

        credited = simulate_layered_strategy(rows, config, [event])
        uncredited = simulate_layered_strategy(rows, config)

        self.assertLess(credited.result.funding_cost, 0.0)
        self.assertGreater(credited.result.final_mark_equity, uncredited.result.final_mark_equity)

    def test_short_ladder_loses_in_monotonic_rise(self) -> None:
        rows = []
        for index in range(100):
            px = 100.0 + index * 0.25
            rows.append(candle(index, px, px + 0.02, px - 0.02, px))

        result = simulate_layered_strategy(
            rows,
            replace(self.base_config(), direction="short", step_bps=100.0),
        )

        self.assertEqual(result.result.round_trips, 0)
        self.assertLess(result.result.return_pct, 0.0)
        self.assertLess(result.result.terminal_unrealized, 0.0)

    def test_basket_stop_closes_inventory_and_records_loss(self) -> None:
        rows = [
            candle(0, 100.0, 100.0, 100.0, 100.0),
            candle(1, 100.0, 100.0, 97.0, 97.5),
        ]
        config = replace(self.base_config(), basket_stop_bps=100.0, step_bps=50.0)

        result = simulate_layered_strategy(rows, config)

        self.assertEqual(result.result.stop_events, 1)
        self.assertEqual(result.result.terminal_active_layers, 0)
        self.assertLess(result.result.stop_pnl, 0.0)

    def test_repeated_stops_cannot_reuse_lost_starting_equity_forever(self) -> None:
        rows = [candle(0, 100.0, 100.0, 100.0, 100.0)]
        for index in range(1, 800):
            center = 100.0 if index % 3 == 0 else 88.0
            rows.append(candle(index, center, center + 0.2, center - 0.2, center))
        config = replace(
            self.base_config(),
            basket_stop_bps=500.0,
            cooldown_bars=0,
            allocation_pct=80.0,
            taker_fee_bps=10.0,
        )

        result = simulate_layered_strategy(rows, config)

        self.assertGreaterEqual(result.result.return_pct, -100.0)
        self.assertLessEqual(result.result.max_exposure_pct, 80.1)

    def test_risk_cooldown_uses_full_number_of_bars(self) -> None:
        rows = [candle(0, 100.0, 100.0, 100.0, 100.0)]
        rows.append(candle(1, 100.0, 100.0, 80.0, 85.0))
        for index in range(2, 7):
            rows.append(candle(index, 85.0, 85.2, 84.8, 85.0))
        config = replace(
            self.base_config(),
            basket_stop_bps=500.0,
            cooldown_bars=3,
            step_bps=100.0,
        )

        result = simulate_layered_strategy(rows, config)
        entry_times = [fill.ts for fill in result.fills if fill.action == "entry"]

        self.assertIn(rows[1].ts, entry_times)
        self.assertNotIn(rows[2].ts, entry_times)
        self.assertNotIn(rows[3].ts, entry_times)
        self.assertNotIn(rows[4].ts, entry_times)
        self.assertIn(rows[5].ts, entry_times)

    def test_prefix_result_is_unchanged_by_future_candles(self) -> None:
        prefix = oscillating_candles(80)
        future = prefix + oscillating_candles(30, drift_per_bar=-0.02)

        short = simulate_layered_strategy(prefix, self.base_config())
        long = simulate_layered_strategy(future, self.base_config())

        self.assertEqual(short.equity_curve, long.equity_curve[: len(short.equity_curve)])

    def test_break_even_take_profit_includes_both_maker_fees(self) -> None:
        threshold = break_even_take_profit_bps(2.0)

        self.assertGreater(threshold, 4.0)
        self.assertLess(threshold, 4.01)

    def test_minimum_equity_respects_contract_minimum_and_tranche_count(self) -> None:
        meta = InstrumentSnapshot(
            inst_id="MU-USDT-SWAP",
            state="live",
            list_time=0,
            contract_value=1.0,
            lot_size=0.01,
            min_size=0.01,
            tick_size=0.01,
            last=900.0,
            bid=899.0,
            ask=901.0,
            spread_bps=1.0,
            turnover_24h_usdt=10_000_000.0,
            selected=True,
            selection_note="selected",
        )
        rows = [candle(0, 900.0, 900.0, 900.0, 900.0), candle(1, 900.0, 900.0, 900.0, 900.0)]

        required = minimum_starting_equity_for_params(
            CandidateParams(100.0, 30.0, 8, 0.0),
            {meta.inst_id: meta},
            {meta.inst_id: rows},
            allocation_pct=60.0,
            leverage=1.0,
        )

        self.assertAlmostEqual(required, 120.0)


if __name__ == "__main__":
    unittest.main()
