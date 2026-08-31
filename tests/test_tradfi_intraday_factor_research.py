from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from backtest.okx_grid_backtest import Candle
from tradfi_intraday_factor_research import (
    MIN_FULL_SESSION_BARS,
    chronological_splits,
    matched_regular_sessions,
    quote_turnover_24h,
    regular_session_date,
    slow_daily_sides,
    session_targets,
    simulate_sessions,
)


def candle(timestamp: int, price: float) -> Candle:
    value = Decimal(str(price))
    return Candle(timestamp, value, value, value, value, Decimal("100"))


def rth_day(day: int, *, final_jump: float = 0.0) -> list[Candle]:
    start = int(datetime(2026, 7, day, 13, 30, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [candle(start + index * 300_000, 100.0 + index * 0.03) for index in range(78)]
    if final_jump:
        final = rows[-1]
        rows[-1] = candle(final.ts, float(final.close) + final_jump)
    return rows


class TradfiIntradayFactorResearchTests(unittest.TestCase):
    def test_regular_session_excludes_weekends_holidays_and_after_hours(self) -> None:
        self.assertEqual(regular_session_date(int(datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc).timestamp() * 1000)), "2026-07-06")
        self.assertIsNone(regular_session_date(int(datetime(2026, 7, 4, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)))
        self.assertIsNone(regular_session_date(int(datetime(2026, 7, 3, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)))
        self.assertIsNone(regular_session_date(int(datetime(2026, 7, 6, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)))

    def test_alignment_requires_exact_timestamps_and_complete_sessions(self) -> None:
        source = rth_day(6)
        contract = rth_day(6)[7:]
        sessions, diagnostics = matched_regular_sessions(source, contract)
        self.assertEqual(sessions, {})
        self.assertEqual(diagnostics["exactTimestampMatches"], MIN_FULL_SESSION_BARS - 1)

    def test_targets_do_not_use_future_underlying_close(self) -> None:
        base = [(row, row) for row in rth_day(6)]
        changed = [(row, row) for row in rth_day(6, final_jump=50.0)]
        self.assertEqual(session_targets(base)[:-1], session_targets(changed)[:-1])

    def test_simulation_flattens_every_session(self) -> None:
        first = [(row, row) for row in rth_day(6)]
        second = [(row, row) for row in rth_day(7)]
        result, trades = simulate_sessions(
            symbol="TEST",
            contract="TEST-USDT-SWAP",
            sessions=[first, second],
            starting_equity=1000.0,
            allocation_pct=20.0,
            leverage=1.0,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
        )
        self.assertEqual(result.sessions, 2)
        self.assertGreaterEqual(len(trades), 2)
        self.assertTrue(all(item.exit_reason == "session_flatten" for item in trades))

    def test_split_is_chronological_and_disjoint(self) -> None:
        dates = [f"2026-07-{value:02d}" for value in range(1, 21)]
        splits = chronological_splits(dates)
        self.assertEqual(splits["train"], dates[:10])
        self.assertEqual(splits["validation"], dates[10:15])
        self.assertEqual(splits["test"], dates[15:])
        self.assertEqual(len(set(splits["train"]) & set(splits["test"])), 0)

    def test_quote_turnover_uses_direct_quote_field_then_base_volume(self) -> None:
        self.assertEqual(quote_turnover_24h({"volCcyQuote24h": "123"}, last=10.0, contract_value=1.0), 123.0)
        self.assertEqual(quote_turnover_24h({"volCcy24h": "12"}, last=10.0, contract_value=1.0), 120.0)

    def test_slow_daily_signal_uses_only_completed_prior_daily_close(self) -> None:
        rows = [
            candle(int(datetime(2025, 1, 1, 13, 30, tzinfo=timezone.utc).timestamp() * 1000) + index * 86_400_000, 100.0 + index)
            for index in range(153)
        ]
        changed = list(rows)
        changed[-1] = candle(changed[-1].ts, 1.0)
        sessions = ["2025-06-02"]
        self.assertEqual(slow_daily_sides(rows, sessions), slow_daily_sides(changed, sessions))


if __name__ == "__main__":
    unittest.main()
