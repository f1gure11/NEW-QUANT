from __future__ import annotations

from datetime import datetime, timezone
import unittest

from macro_calendar import macro_calendar_snapshot


class MacroCalendarTest(unittest.TestCase):
    def test_returns_sorted_2026_calendar_with_next_event(self) -> None:
        payload = macro_calendar_snapshot(now=datetime(2026, 7, 21, 12, tzinfo=timezone.utc))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scheduleYear"], 2026)
        self.assertEqual(payload["nextEvent"]["id"], "ecb-2026-07-23")
        scheduled = [event["scheduledAt"] for event in payload["events"]]
        self.assertEqual(scheduled, sorted(scheduled))

    def test_keeps_monthly_and_quarterly_high_impact_events(self) -> None:
        payload = macro_calendar_snapshot(now=datetime(2026, 7, 21, 12, tzinfo=timezone.utc))
        by_id = {event["id"]: event for event in payload["events"]}

        self.assertEqual(by_id["cpi-2026-08-12"]["officialTime"], "08:30 ET")
        self.assertIn("employment", by_id["nfp-2026-08-07"]["categories"])
        self.assertIn("quarterly", by_id["fomc-2026-09-16"]["categories"])
        self.assertIn("quarterly", by_id["gdp-advance-2026-q3"]["categories"])
        self.assertEqual(by_id["fomc-2026-09-16"]["status"], "scheduled")

    def test_marks_elapsed_events_without_mutating_future_events(self) -> None:
        payload = macro_calendar_snapshot(now=datetime(2026, 8, 13, 0, tzinfo=timezone.utc))
        by_id = {event["id"]: event for event in payload["events"]}

        self.assertEqual(by_id["cpi-2026-08-12"]["status"], "released")
        self.assertEqual(by_id["nfp-2026-09-04"]["status"], "scheduled")
        self.assertEqual(payload["nextEvent"]["id"], "pce-2026-08-26")


if __name__ == "__main__":
    unittest.main()
