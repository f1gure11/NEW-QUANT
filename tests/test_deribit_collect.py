from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

import data_pipeline as dp
import deribit_collect as dc


def _ms(stamp: str) -> int:
    return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)


class DeribitCollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="deribit_lake_")
        self._orig_lake = dp.LAKE_ROOT
        dp.LAKE_ROOT = Path(self._tmp) / "data_lake"

    def tearDown(self) -> None:
        dp.LAKE_ROOT = self._orig_lake

    def test_parse_chart_and_funding_and_dvol(self) -> None:
        chart = dc.parse_chart(
            {
                "result": {
                    "status": "ok",
                    "ticks": [_ms("2026-01-01T00:00:00Z"), _ms("2026-01-01T01:00:00Z")],
                    "open": [90.0, 100.0],
                    "high": [95.0, 110.0],
                    "low": [88.0, 99.0],
                    "close": [100.0, 105.0],
                    "volume": [1.0, 2.0],
                }
            }
        )
        self.assertEqual(len(chart), 2)
        self.assertEqual(chart["close"].iloc[-1], 105.0)
        funding = dc.parse_funding(
            {
                "result": [
                    {"timestamp": _ms("2026-01-01T08:00:00Z"), "interest_8h": 0.0001},
                    {"timestamp": 0, "interest_8h": 0.5},
                ]
            }
        )
        self.assertEqual(len(funding), 1)
        self.assertAlmostEqual(funding["funding_rate"].iloc[0], 0.0001)
        dvol = dc.parse_dvol({"result": {"data": [[_ms("2026-01-01T00:00:00Z"), 50, 55, 49, 52]]}})
        self.assertEqual(len(dvol), 1)
        self.assertEqual(dvol["close"].iloc[0], 52)

    def test_collect_writes_to_isolated_lake(self) -> None:
        start = _ms("2026-06-01T00:00:00Z")
        end = _ms("2026-06-01T02:00:00Z")

        def http_get(url: str) -> dict:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            path = parsed.path
            if path.endswith("get_tradingview_chart_data"):
                return {
                    "result": {
                        "status": "ok",
                        "ticks": [start, end],
                        "open": [1.0, 2.0],
                        "high": [1.1, 2.1],
                        "low": [0.9, 1.9],
                        "close": [1.05, 2.05],
                        "volume": [10.0, 11.0],
                    }
                }
            if path.endswith("get_funding_rate_history"):
                return {"result": [{"timestamp": start, "interest_8h": 0.0002}]}
            if path.endswith("get_volatility_index_data"):
                return {"result": {"data": [[start, 40, 41, 39, 40.5]]}}
            raise AssertionError(url)

        counts = dc.collect_deribit(lookback_days=5, http_get=http_get)
        self.assertGreater(counts["candles"]["BTC-PERPETUAL"], 0)
        candles = dc.load_deribit_candles("BTC-PERPETUAL", "1h")
        funding = dc.load_deribit_funding("ETH-PERPETUAL")
        dvol = dc.load_deribit_dvol("BTC")
        self.assertEqual(list(candles["timeframe"].unique()), ["1h"])
        self.assertFalse(funding.empty)
        self.assertAlmostEqual(dvol["close"].iloc[0], 40.5)
        coverage = dc.scan_deribit_coverage()
        self.assertGreaterEqual(coverage["candleFiles"], 1)
        self.assertGreaterEqual(coverage["fundingFiles"], 1)
        self.assertGreaterEqual(coverage["dvolFiles"], 1)

    def test_deribit_has_no_gold_default(self) -> None:
        self.assertNotIn("XAU-PERPETUAL", dc.DEFAULT_PERPS)


if __name__ == "__main__":
    unittest.main()
