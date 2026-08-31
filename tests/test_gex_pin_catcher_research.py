from __future__ import annotations

import unittest
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from gex_delta_neutral_research import GexEvent
from gex_pin_catcher_research import (
    PinCandidate,
    PinExecutionConfig,
    latest_event_strictly_before,
    quote_limits,
    run_pin_backtest,
)


def event(
    timestamp: int,
    *,
    net_gex: float = 1.0,
    put_wall: float = 99.0,
    call_wall: float = 101.0,
) -> GexEvent:
    return GexEvent(
        underlying="BTC",
        event_ts=timestamp,
        captured_at="",
        source_timestamp="",
        net_gex=net_gex,
        gross_gex=10.0,
        oi_usd=1_000.0,
        spot_price=100.0,
        call_wall=call_wall,
        put_wall=put_wall,
    )


def candle(timestamp: int, *, open_: float = 100.0, high: float = 100.2, low: float = 99.8, close: float = 100.0) -> Candle:
    return Candle(
        ts=timestamp,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


def candidate(**overrides: float | int) -> PinCandidate:
    values: dict[str, float | int] = {
        "wall_offset_bps": 0.0,
        "take_profit_bps": 25.0,
        "stop_loss_bps": 50.0,
        "max_hold_bars": 12,
        "max_gex_age_hours": 1.0,
    }
    values.update(overrides)
    return PinCandidate(**values)  # type: ignore[arg-type]


class GexPinCatcherResearchTests(unittest.TestCase):
    def test_event_must_be_strictly_earlier_than_quote_bar(self) -> None:
        rows = [event(100), event(200)]
        self.assertIsNone(latest_event_strictly_before(rows, 100))
        self.assertEqual(latest_event_strictly_before(rows, 200).event_ts, 100)  # type: ignore[union-attr]
        self.assertEqual(latest_event_strictly_before(rows, 201).event_ts, 200)  # type: ignore[union-attr]

    def test_positive_gamma_put_wall_trade_can_take_profit_next_bar(self) -> None:
        rows = [
            candle(0),
            candle(300_000, low=98.9, close=99.1),
            candle(600_000, high=99.5, low=99.0, close=99.4),
        ]
        result = run_pin_backtest(
            rows,
            [event(-1)],
            candidate(),
            PinExecutionConfig(penetration_bps=0.0),
            record_details=True,
        )
        self.assertEqual(result["tradeCount"], 1)
        self.assertEqual(result["targetExits"], 1)
        self.assertEqual(result["trades"][0]["reason"], "take_profit")

    def test_negative_gamma_never_posts_contrarian_quote(self) -> None:
        rows = [candle(0), candle(300_000, high=102.0, low=98.0)]
        result = run_pin_backtest(
            rows,
            [event(-1, net_gex=-1.0)],
            candidate(),
            PinExecutionConfig(penetration_bps=0.0),
        )
        self.assertEqual(result["quoteBars"], 0)
        self.assertEqual(result["tradeCount"], 0)

    def test_two_sided_touch_is_skipped(self) -> None:
        rows = [candle(0), candle(300_000, high=102.0, low=98.0)]
        result = run_pin_backtest(
            rows,
            [event(-1)],
            candidate(),
            PinExecutionConfig(penetration_bps=0.0),
        )
        self.assertEqual(result["bothSidesTouched"], 1)
        self.assertEqual(result["makerEntries"], 0)

    def test_single_pin_strike_quotes_both_sides_symmetrically(self) -> None:
        pin_event = event(-1, put_wall=100.0, call_wall=100.0)
        buy, sell = quote_limits(pin_event, candidate(wall_offset_bps=10.0))
        self.assertAlmostEqual(buy, 99.9)
        self.assertAlmostEqual(sell, 100.1)
        rows = [candle(0), candle(300_000, high=100.05, low=99.8, close=99.95)]
        result = run_pin_backtest(
            rows,
            [pin_event],
            candidate(wall_offset_bps=10.0),
            PinExecutionConfig(penetration_bps=0.0),
        )
        self.assertEqual(result["singlePinQuoteBars"], 1)
        self.assertEqual(result["makerEntries"], 1)

    def test_new_fill_cannot_take_profit_on_entry_bar(self) -> None:
        rows = [candle(0), candle(300_000, high=99.5, low=98.9, close=99.2)]
        result = run_pin_backtest(
            rows,
            [event(-1)],
            candidate(),
            PinExecutionConfig(penetration_bps=0.0),
            record_details=True,
        )
        self.assertEqual(result["targetExits"], 0)
        self.assertEqual(result["trades"][0]["reason"], "terminal_exit")

    def test_new_fill_can_stop_on_entry_bar_conservatively(self) -> None:
        rows = [candle(0), candle(300_000, high=100.0, low=98.0, close=98.5)]
        result = run_pin_backtest(
            rows,
            [event(-1)],
            candidate(),
            PinExecutionConfig(penetration_bps=0.0),
            record_details=True,
        )
        self.assertEqual(result["tradeCount"], 1)
        self.assertEqual(result["trades"][0]["reason"], "same_bar_stop")
        self.assertLess(result["returnPct"], 0)

    def test_open_position_exits_when_gex_expires(self) -> None:
        rows = [
            candle(0),
            candle(300_000, low=98.9, close=99.1),
            candle(3_900_000, open_=99.2, high=99.3, low=99.1, close=99.2),
        ]
        result = run_pin_backtest(
            rows,
            [event(-1)],
            candidate(max_hold_bars=100, max_gex_age_hours=1.0),
            PinExecutionConfig(penetration_bps=0.0),
            record_details=True,
        )
        self.assertEqual(result["staleExits"], 1)
        self.assertEqual(result["trades"][0]["reason"], "gex_expired")


if __name__ == "__main__":
    unittest.main()
