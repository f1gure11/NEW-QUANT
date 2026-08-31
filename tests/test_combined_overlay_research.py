from __future__ import annotations

import unittest
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from funding_research import FundingPoint
from combined_overlay_research import (
    CombinedConfig,
    OverlayDecision,
    PreparedMomentum,
    Variant,
    aggregate_complete_hours,
    macro_event_times,
    overlay_decision,
    prepare_hourly_momentum,
    simulate_combined,
)
from vwap_market_maker_research import VwapMakerParams, rolling_vwap_features


def candles(count: int = 900, *, drift: float = 0.03) -> list[Candle]:
    result = []
    close = 100.0
    for index in range(count):
        open_price = close
        close = open_price + drift + (0.12 if index % 29 == 0 else -0.05 if index % 17 == 0 else 0.0)
        result.append(
            Candle(
                ts=index * 300_000,
                open=Decimal(str(open_price)),
                high=Decimal(str(max(open_price, close) + 0.25)),
                low=Decimal(str(min(open_price, close) - 0.25)),
                close=Decimal(str(close)),
                volume=Decimal(str(100 + index % 13)),
            )
        )
    return result


def config() -> CombinedConfig:
    return CombinedConfig(
        starting_equity=100_000.0,
        allocation_pct=20.0,
        target_daily_vol_bps=300.0,
        quote_notional_pct=10.0,
        max_passive_bars=3,
        min_rebalance_pct=0.1,
        maker_fee_bps=2.0,
        taker_fee_bps=5.0,
        taker_slippage_bps=1.0,
    )


def vwap_params() -> VwapMakerParams:
    return VwapMakerParams(
        vwap_window=24,
        anchor_weight=0.5,
        min_half_spread_bps=5.0,
        volatility_multiplier=0.5,
        inventory_skew_bps=10.0,
        trend_lookback=3,
        max_vwap_slope_bps=1_000.0,
        volatility_window=6,
        max_volatility_bps=1_000.0,
        penetration_bps=0.0,
    )


class CombinedOverlayResearchTests(unittest.TestCase):
    def test_only_complete_hours_are_aggregated(self) -> None:
        rows = candles(25)
        hourly, mapping = aggregate_complete_hours(rows)
        self.assertEqual(len(hourly), 2)
        self.assertEqual(sorted(mapping), [0, 3_600_000])

    def test_hourly_momentum_does_not_use_current_hour_close(self) -> None:
        rows = candles(900)
        changed = list(rows)
        last = changed[-1]
        changed[-1] = Candle(
            ts=last.ts,
            open=last.open,
            high=Decimal("1000"),
            low=Decimal("1"),
            close=Decimal("900"),
            volume=last.volume,
        )
        base = prepare_hourly_momentum(rows, config())
        moved = prepare_hourly_momentum(changed, config())
        self.assertEqual(base.sides[-1], moved.sides[-1])
        self.assertEqual(base.volatility_scales[-1], moved.volatility_scales[-1])

    def test_risk_overlays_only_reduce_target_multiplier(self) -> None:
        ts = 20_000_000
        funding = [FundingPoint(ts=ts - 1_000, rate=0.0002, realized_rate=0.0002)]
        gex = [(ts - 1_000, {"netGex": -1.0, "callWall": {"strike": 110}, "putWall": {"strike": 90}})]
        decision = overlay_decision(
            side=1,
            price=100.0,
            timestamp=ts,
            funding=funding,
            gex=gex,
            macro_times=[ts],
            config=config(),
            use_funding=True,
            use_gex=True,
            use_macro=True,
        )
        self.assertTrue(decision.funding_reduced)
        self.assertTrue(decision.gex_reduced)
        self.assertTrue(decision.macro_reduced)
        self.assertGreaterEqual(decision.multiplier, 0.0)
        self.assertLessEqual(decision.multiplier, 1.0)

    def test_favorable_funding_does_not_flip_or_raise_multiplier(self) -> None:
        ts = 20_000_000
        funding = [FundingPoint(ts=ts - 1_000, rate=-0.0002, realized_rate=-0.0002)]
        decision = overlay_decision(
            side=1,
            price=100.0,
            timestamp=ts,
            funding=funding,
            gex=[],
            macro_times=[],
            config=config(),
            use_funding=True,
            use_gex=False,
            use_macro=False,
        )
        self.assertEqual(decision.multiplier, 1.0)
        self.assertFalse(decision.funding_reduced)

    def test_macro_schedule_is_available_for_risk_window(self) -> None:
        events = macro_event_times()
        self.assertGreater(len(events), 10)
        self.assertEqual(events, sorted(events))

    def test_vwap_execution_records_maker_or_timeout_and_terminal_close(self) -> None:
        rows = candles(900)
        cfg = config()
        momentum = prepare_hourly_momentum(rows, cfg)
        params = vwap_params()
        features = rolling_vwap_features(rows, params)
        result, _, cycles = simulate_combined(
            rows,
            0,
            len(rows),
            momentum,
            features,
            [],
            [],
            [],
            cfg,
            params,
            Variant("vwap", "vwap"),
            bar_ms=300_000,
        )
        self.assertGreater(result.maker_fills + result.taker_fills, 0)
        self.assertGreater(result.fees, 0.0)
        self.assertEqual(result.direction_cycles, len(cycles))
        self.assertGreaterEqual(result.tracking_error_pct, 0.0)

    def test_positive_funding_charges_long_position(self) -> None:
        rows = candles(900)
        cfg = config()
        momentum = prepare_hourly_momentum(rows, cfg)
        params = vwap_params()
        features = rolling_vwap_features(rows, params)
        funding_ts = rows[800].ts
        funding = [FundingPoint(funding_ts, 0.001, 0.001)]
        result, _, _ = simulate_combined(
            rows,
            0,
            len(rows),
            momentum,
            features,
            funding,
            [],
            [],
            cfg,
            params,
            Variant("taker", "taker"),
            bar_ms=300_000,
        )
        self.assertLessEqual(result.funding_pnl, 0.0)

    def test_direct_taker_accounting_matches_round_trip_costs(self) -> None:
        rows = [
            Candle(
                ts=index * 300_000,
                open=Decimal("100"),
                high=Decimal("100"),
                low=Decimal("100"),
                close=Decimal("100"),
                volume=Decimal("100"),
            )
            for index in range(2)
        ]
        cfg = CombinedConfig(
            starting_equity=100_000.0,
            allocation_pct=20.0,
            target_daily_vol_bps=300.0,
            quote_notional_pct=10.0,
            max_passive_bars=3,
            min_rebalance_pct=0.1,
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            taker_slippage_bps=1.0,
            holding_cost_bps_per_day=0.0,
        )
        momentum = PreparedMomentum(sides=[1, 1], volatility_scales=[1.0, 1.0], hourly_bars=0)
        result, fills, cycles = simulate_combined(
            rows,
            0,
            len(rows),
            momentum,
            [None, None],
            [],
            [],
            [],
            cfg,
            vwap_params(),
            Variant("taker", "taker"),
            bar_ms=300_000,
            record_details=True,
        )
        # 200 units enter at 100.01 and exit at 99.99. Slippage loses 4,
        # while the 5 bps entry/exit fees sum to exactly 20.
        self.assertAlmostEqual(result.final_equity, 99_976.0, places=6)
        self.assertAlmostEqual(result.total_return_pct, -0.024, places=9)
        self.assertAlmostEqual(result.fees, 20.0, places=6)
        self.assertEqual(result.maker_fills, 0)
        self.assertEqual(result.taker_fills, 2)
        self.assertEqual(len(fills), 2)
        self.assertEqual(len(cycles), 1)


if __name__ == "__main__":
    unittest.main()
