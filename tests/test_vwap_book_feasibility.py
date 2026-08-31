from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from vwap_book_feasibility import (
    coverage_summary,
    interval_trade_range,
    method_viable,
    sha256_path,
)


class VwapBookFeasibilityTests(unittest.TestCase):
    def test_interval_uses_completed_bars_then_falls_back(self) -> None:
        candles = pd.DataFrame(
            {
                "time": pd.to_datetime(
                    ["2026-07-02T00:05:00Z", "2026-07-02T00:10:00Z", "2026-07-02T00:15:00Z"],
                    utc=True,
                ),
                "low": [99.0, 98.5, 97.0],
                "high": [101.0, 102.0, 100.0],
            }
        )
        low, high, bars = interval_trade_range(
            candles,
            pd.Timestamp("2026-07-02T00:05:00Z"),
            pd.Timestamp("2026-07-02T00:12:00Z"),
            100.0,
        )
        self.assertEqual(bars, 0)
        low, high, bars = interval_trade_range(
            candles,
            pd.Timestamp("2026-07-02T00:04:00Z"),
            pd.Timestamp("2026-07-02T00:12:00Z"),
            100.0,
        )
        self.assertEqual(bars, 1)
        self.assertEqual(low, 98.5)
        self.assertEqual(high, 102.0)
        low, high, bars = interval_trade_range(
            candles,
            pd.Timestamp("2026-07-02T01:00:00Z"),
            pd.Timestamp("2026-07-02T01:01:00Z"),
            100.5,
        )
        self.assertEqual(bars, 0)
        self.assertEqual(low, 100.5)

    def test_method_requires_two_liquid_books(self) -> None:
        self.assertFalse(method_viable([{"snapshots": 10, "completeBookRatio": 1.0}], []))
        coverages = [
            {"snapshots": 600, "completeBookRatio": 0.99},
            {"snapshots": 600, "completeBookRatio": 0.99},
        ]
        results = [{"snapshotsJoined": 600}, {"snapshotsJoined": 600}]
        self.assertTrue(method_viable(coverages, results))
        coverages[1]["completeBookRatio"] = 0.5
        self.assertFalse(method_viable(coverages, results))

    def test_registry_stays_trading_disabled(self) -> None:
        path = Path("config/vwap_book_feasibility_preregistration.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(payload["study"]["paperOrLiveAuthorized"])
        self.assertEqual(payload["study"]["universe"], ["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
        self.assertTrue(sha256_path(path))


if __name__ == "__main__":
    unittest.main()
