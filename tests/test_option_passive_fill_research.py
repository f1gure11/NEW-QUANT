from __future__ import annotations

import unittest

from option_passive_fill_research import cohort_rows, passive_limit, simulate_cohorts, summarize


def structure() -> dict:
    return {
        "name": "BTC_atm",
        "base": "BTC",
        "kind": "atm",
        "hoursToExpiry": 24.0,
        "call": {"instId": "CALL", "tickSize": 1.0},
        "put": {"instId": "PUT", "tickSize": 1.0},
    }


def bbo(inst_id: str, ts: int, bid: float, ask: float) -> dict:
    return {
        "capturedTs": ts,
        "instId": inst_id,
        "channel": "bbo-tbt",
        "data": {"bids": [[str(bid), "10"]], "asks": [[str(ask), "10"]]},
    }


def trade(inst_id: str, ts: int, price: float) -> dict:
    return {
        "capturedTs": ts,
        "instId": inst_id,
        "channel": "trades",
        "data": {"px": str(price), "side": "sell"},
    }


class OptionPassiveFillResearchTests(unittest.TestCase):
    def test_passive_policies_stay_post_only_and_tick_aligned(self) -> None:
        self.assertEqual(passive_limit(90.0, 110.0, 5.0, "join_bid"), 90.0)
        self.assertEqual(passive_limit(90.0, 110.0, 5.0, "improve25"), 95.0)
        self.assertEqual(passive_limit(90.0, 110.0, 5.0, "midpoint"), 100.0)
        self.assertEqual(passive_limit(100.0, 101.0, 1.0, "midpoint"), 100.0)

    def test_trade_touch_is_optimistic_while_ask_touch_is_conservative(self) -> None:
        events = [
            bbo("CALL", 1_000, 90, 110),
            bbo("PUT", 1_001, 90, 110),
            trade("CALL", 2_000, 100),
            trade("PUT", 2_001, 100),
            bbo("CALL", 4_000, 89, 99),
            bbo("PUT", 4_001, 89, 99),
            bbo("CALL", 20_000, 90, 110),
        ]
        cohorts = simulate_cohorts(
            events,
            [structure()],
            cohort_interval_seconds=10,
            ttl_seconds=5,
            max_quote_age_seconds=10,
        )
        rows = cohort_rows(cohorts)
        midpoint = next(row for row in rows if row["policy"] == "midpoint")
        self.assertTrue(midpoint["optimistic_touch_both"])
        self.assertTrue(midpoint["ask_touch_both"])
        report = summarize(rows)
        midpoint_summary = next(row for row in report if row["policy"] == "midpoint")
        self.assertEqual(midpoint_summary["cohorts"], 1)
        self.assertEqual(midpoint_summary["optimisticTouchBothPct"], 100.0)


if __name__ == "__main__":
    unittest.main()
