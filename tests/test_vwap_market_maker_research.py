from __future__ import annotations

import math
import unittest
from dataclasses import replace
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from vwap_market_maker_research import (
    MakerExecutionConfig,
    MakerFeature,
    VwapMakerParams,
    apply_inventory_fill,
    parse_completed_okx_candles,
    quote_levels,
    rolling_vwap_features,
    run_market_maker_backtest,
)


def candles(count: int = 120, *, drift: float = 0.02) -> list[Candle]:
    result = []
    close = 100.0
    for index in range(count):
        open_price = close
        close = open_price + drift + (0.12 if index % 9 == 0 else -0.03 if index % 7 == 0 else 0.0)
        result.append(
            Candle(
                ts=index * 300_000,
                open=Decimal(str(open_price)),
                high=Decimal(str(max(open_price, close) + 0.20)),
                low=Decimal(str(min(open_price, close) - 0.20)),
                close=Decimal(str(close)),
                volume=Decimal(str(100 + index % 11)),
            )
        )
    return result


def params(**values: float | int) -> VwapMakerParams:
    base = VwapMakerParams(
        vwap_window=12,
        anchor_weight=0.5,
        min_half_spread_bps=5.0,
        volatility_multiplier=0.5,
        inventory_skew_bps=20.0,
        trend_lookback=3,
        max_vwap_slope_bps=1_000.0,
        volatility_window=6,
        max_volatility_bps=1_000.0,
        max_inventory_bars=20,
        inventory_stop_bps=1_000.0,
    )
    return replace(base, **values)


class VwapMarketMakerResearchTests(unittest.TestCase):
    def test_partial_okx_candle_is_not_cached(self) -> None:
        rows = [
            ["0", "100", "101", "99", "100", "10", "0", "0", "1"],
            ["300000", "100", "101", "99", "100", "10", "0", "0", "1"],
            ["600000", "100", "101", "99", "100", "10", "0", "0", "0"],
        ]
        parsed = parse_completed_okx_candles(rows, "5m", now_ms=900_000)
        self.assertEqual([candle.ts for candle in parsed], [0, 300_000])

    def test_features_are_causal(self) -> None:
        original = candles()
        changed = list(original)
        last = changed[-1]
        changed[-1] = Candle(
            ts=last.ts,
            open=Decimal("1000"),
            high=Decimal("1200"),
            low=Decimal("900"),
            close=Decimal("1100"),
            volume=Decimal("999999"),
        )
        left = rolling_vwap_features(original, params())
        right = rolling_vwap_features(changed, params())
        self.assertEqual(left[:-1], right[:-1])

    def test_vwap_uses_candle_volume(self) -> None:
        rows = candles(30, drift=0.0)
        changed = list(rows)
        source = changed[15]
        changed[15] = Candle(
            ts=source.ts,
            open=source.open,
            high=source.high,
            low=source.low,
            close=source.close,
            volume=Decimal("100000"),
        )
        left = rolling_vwap_features(rows, params(vwap_window=12))
        right = rolling_vwap_features(changed, params(vwap_window=12))
        self.assertNotEqual(left[15].vwap, right[15].vwap)  # type: ignore[union-attr]

    def test_inventory_skew_lowers_reservation_for_long_inventory(self) -> None:
        feature = MakerFeature(1, 100.0, 99.0, 5.0, 0.0, 5.0, True)
        flat = quote_levels(feature, params(), inventory=0.0, max_inventory=10.0)
        long = quote_levels(feature, params(), inventory=10.0, max_inventory=10.0)
        self.assertLess(long[0], flat[0])
        self.assertLessEqual(long[1], flat[1])
        self.assertLessEqual(long[2], flat[2])
        self.assertLess(flat[1], feature.close)
        self.assertGreater(flat[2], feature.close)

    def test_inventory_fill_realizes_linear_long_pnl(self) -> None:
        realized, inventory, average = apply_inventory_fill(2.0, 100.0, -1.0, 102.0)
        self.assertAlmostEqual(realized, 2.0)
        self.assertAlmostEqual(inventory, 1.0)
        self.assertAlmostEqual(average, 100.0)
        realized, inventory, average = apply_inventory_fill(inventory, average, -1.0, 101.0)
        self.assertAlmostEqual(realized, 1.0)
        self.assertEqual(inventory, 0.0)
        self.assertEqual(average, 0.0)

    def test_quotes_use_prior_completed_bar_and_charge_fees(self) -> None:
        rows = candles(80, drift=0.0)
        wide_rows = []
        for row in rows:
            wide_rows.append(
                Candle(
                    ts=row.ts,
                    open=row.open,
                    high=row.open * Decimal("1.005"),
                    low=row.open * Decimal("0.995"),
                    close=row.close,
                    volume=row.volume,
                )
            )
        result, _, cycles, _ = run_market_maker_backtest(
            wide_rows,
            params(penetration_bps=0.0),
            MakerExecutionConfig(),
            bar_ms=300_000,
        )
        self.assertGreater(result.maker_fills, 0)
        self.assertGreater(result.fees, 0.0)
        self.assertEqual(result.inventory_cycles, len(cycles))
        self.assertLessEqual(result.maker_fills, result.quote_bars)

    def test_both_side_touch_is_counted_but_only_one_maker_fill_per_bar(self) -> None:
        rows = candles(80, drift=0.0)
        wide_rows = [
            Candle(
                ts=row.ts,
                open=row.open,
                high=row.open * Decimal("1.01"),
                low=row.open * Decimal("0.99"),
                close=row.close,
                volume=row.volume,
            )
            for row in rows
        ]
        result, _, _, _ = run_market_maker_backtest(
            wide_rows,
            params(penetration_bps=0.0),
            MakerExecutionConfig(conservative_single_fill=True),
            bar_ms=300_000,
        )
        self.assertGreater(result.both_sides_touched, 0)
        self.assertLessEqual(result.maker_fills, result.quote_bars)
        self.assertTrue(math.isfinite(result.final_equity))

    def test_terminal_inventory_is_liquidated_with_taker_cost(self) -> None:
        rows = [
            Candle(
                ts=0,
                open=Decimal("100"),
                high=Decimal("100"),
                low=Decimal("100"),
                close=Decimal("100"),
                volume=Decimal("100"),
            ),
            Candle(
                ts=300_000,
                open=Decimal("100"),
                high=Decimal("100"),
                low=Decimal("99"),
                close=Decimal("99"),
                volume=Decimal("100"),
            ),
        ]
        feature = MakerFeature(0, 100.0, 100.0, 1.0, 0.0, 5.0, True)
        result, _, cycles, _ = run_market_maker_backtest(
            rows,
            params(penetration_bps=0.0),
            MakerExecutionConfig(),
            bar_ms=300_000,
            features=[feature, feature],
        )
        self.assertEqual(result.maker_fills, 1)
        self.assertEqual(result.terminal_exits, 1)
        self.assertEqual(result.taker_exits, 1)
        self.assertEqual(cycles[-1].exit_reason, "terminal_exit")
        self.assertLess(result.final_equity, result.starting_equity)
        self.assertGreater(result.max_drawdown_pct, 0.0)

    def test_session_filter_flattens_inventory_and_blocks_new_quotes(self) -> None:
        rows = candles(8, drift=0.0)
        wide_rows = [
            Candle(
                ts=row.ts,
                open=row.open,
                high=row.open * Decimal("1.01"),
                low=row.open * Decimal("0.99"),
                close=row.close,
                volume=row.volume,
            )
            for row in rows
        ]
        feature = MakerFeature(0, 100.0, 100.0, 1.0, 0.0, 5.0, True)
        result, fills, cycles, _ = run_market_maker_backtest(
            wide_rows,
            params(penetration_bps=0.0),
            MakerExecutionConfig(),
            bar_ms=300_000,
            features=[feature] * len(wide_rows),
            active_predicate=lambda row: row.ts < wide_rows[2].ts,
            record_details=True,
        )
        self.assertEqual(result.maker_fills, 1)
        self.assertEqual(result.taker_exits, 1)
        self.assertEqual(fills[-1].role, "session_exit")
        self.assertEqual(cycles[-1].exit_reason, "session_exit")


if __name__ == "__main__":
    unittest.main()
