from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd

from backtest.okx_grid_backtest import Candle
from qqq_intraday_flat_research import (
    FundingPoint,
    SessionExecution,
    apply_costs,
    build_raw_session_frame,
    chronological_splits,
    executable_sessions,
    funding_pnl,
    weights_strictly_before,
)


def candle(timestamp: int, price: float) -> Candle:
    value = Decimal(str(price))
    return Candle(timestamp, value, value, value, value, Decimal("1"))


def rth_session(day: int) -> list[Candle]:
    start = int(datetime(2026, 7, day, 13, 30, tzinfo=timezone.utc).timestamp() * 1000)
    return [candle(start + index * 300_000, 100.0 + index * 0.01) for index in range(78)]


def execution(session: str, entry: float, exit_price: float) -> SessionExecution:
    day = date.fromisoformat(session).day
    entry_ts = int(datetime(2026, 7, day, 13, 45, tzinfo=timezone.utc).timestamp() * 1000)
    exit_ts = int(datetime(2026, 7, day, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)
    return SessionExecution(session, entry_ts, exit_ts, entry, exit_price)


class QqqIntradayFlatResearchTests(unittest.TestCase):
    def test_session_uses_0945_open_and_1555_close(self) -> None:
        rows = executable_sessions(rth_session(6))
        item = rows["2026-07-06"]
        self.assertAlmostEqual(item.entry_price, 100.03)
        self.assertAlmostEqual(item.exit_price, 100.77)
        self.assertEqual(
            datetime.fromtimestamp(item.exit_ts / 1000, timezone.utc).strftime("%H:%M"),
            "20:00",
        )

    def test_weight_lookup_is_strictly_before_session(self) -> None:
        history = {
            date(2026, 6, 30): {"A": 0.1},
            date(2026, 7, 31): {"A": -0.1},
        }
        self.assertEqual(weights_strictly_before("2026-07-31", history)[0], date(2026, 6, 30))
        self.assertEqual(weights_strictly_before("2026-08-03", history)[0], date(2026, 7, 31))

    def test_positive_funding_is_paid_by_long_and_received_by_short(self) -> None:
        points = [FundingPoint(100, 0.001), FundingPoint(200, -0.0002)]
        self.assertAlmostEqual(funding_pnl(points, 0, 150, 0.5), -0.0005)
        self.assertAlmostEqual(funding_pnl(points, 0, 150, -0.5), 0.0005)

    def test_daily_flat_active_return_and_cost_use_round_trip_gross(self) -> None:
        dates = ["2026-07-06", "2026-07-07"]
        sessions = {
            "QQQ": {dates[0]: execution(dates[0], 100, 101), dates[1]: execution(dates[1], 102, 103)},
            "A": {dates[0]: execution(dates[0], 100, 102), dates[1]: execution(dates[1], 103, 104)},
            "B": {dates[0]: execution(dates[0], 100, 99), dates[1]: execution(dates[1], 98, 97)},
        }
        funding = {symbol: [] for symbol in sessions}
        weights = {date(2026, 6, 30): {"A": 0.1, "B": -0.1}}
        raw = build_raw_session_frame(dates, ["A", "B"], sessions, funding, weights)
        self.assertAlmostEqual(raw.iloc[0]["flatActiveGrossReturn"], 0.003)
        self.assertAlmostEqual(raw.iloc[0]["flatActiveTurnover"], 0.4)
        costed = apply_costs(raw, cost_bps_per_side=10.0)
        self.assertAlmostEqual(costed.iloc[0]["flatActiveCost"], 0.0004)
        self.assertAlmostEqual(costed.iloc[0]["flatCoreCost"], 0.002)

    def test_continuous_mode_includes_overnight_move(self) -> None:
        dates = ["2026-07-06", "2026-07-07"]
        sessions = {
            "QQQ": {dates[0]: execution(dates[0], 100, 100), dates[1]: execution(dates[1], 110, 110)},
            "A": {dates[0]: execution(dates[0], 100, 100), dates[1]: execution(dates[1], 120, 120)},
            "B": {dates[0]: execution(dates[0], 100, 100), dates[1]: execution(dates[1], 90, 90)},
        }
        funding = {symbol: [] for symbol in sessions}
        weights = {date(2026, 6, 30): {"A": 0.1, "B": -0.1}}
        raw = build_raw_session_frame(dates, ["A", "B"], sessions, funding, weights)
        self.assertAlmostEqual(raw.iloc[1]["flatActiveGrossReturn"], 0.0)
        self.assertAlmostEqual(raw.iloc[1]["continuousActiveGrossReturn"], 0.03)
        self.assertAlmostEqual(raw.iloc[1]["continuousCoreGrossReturn"], 0.10)

    def test_split_is_chronological(self) -> None:
        values = [f"2026-07-{value:02d}" for value in range(1, 21)]
        splits = chronological_splits(values)
        self.assertEqual(splits["train"], values[:10])
        self.assertEqual(splits["validation"], values[10:15])
        self.assertEqual(splits["test"], values[15:])


if __name__ == "__main__":
    unittest.main()
