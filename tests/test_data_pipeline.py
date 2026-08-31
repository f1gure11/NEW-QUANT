"""Tests for the data_lake pipeline (data_pipeline.py).

Uses temporary fixture data only; never touches real data/ or the network.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

# Ensure the module is importable regardless of CWD
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data_pipeline as dp  # noqa: E402


def make_candle_csv(path: Path, inst: str, tf: str, times: list[str],
                    close_base: float = 100.0) -> None:
    rows = []
    for i, t in enumerate(times):
        px = close_base + i
        rows.append(f"{int(pd.Timestamp(t).timestamp()*1000)},{t},{px},{px+1},{px-1},{px},{1000+i}")
    path.write_text("ts,time,open,high,low,close,volume\n" + "\n".join(rows) + "\n", encoding="utf-8")


def make_funding_csv(path: Path, inst: str, times_ms: list[int]) -> None:
    rows = []
    for i, t in enumerate(times_ms):
        rows.append(f"{t},{0.0001*i},{0.0001*i}")
    path.write_text("funding_time,funding_rate,realized_rate\n" + "\n".join(rows) + "\n", encoding="utf-8")


import argparse


def build_args() -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.command = "build"
    return ns


class PipelineIsolatedTestCase(unittest.TestCase):
    """Run pipeline functions against a temp data/ + temp lake."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="datalake_test_")
        self._data = Path(self._tmp) / "data"
        self._lake = Path(self._tmp) / "data_lake"
        (self._data / "backtest").mkdir(parents=True)
        (self._data / "funding").mkdir(parents=True)
        (self._data / "microstructure").mkdir(parents=True)

        # stash real roots
        self._orig = {
            "DATA_ROOT": dp.DATA_ROOT,
            "LAKE_ROOT": dp.LAKE_ROOT,
            "CANDLE_SOURCE_DIR": dp.CANDLE_SOURCE_DIR,
            "FUNDING_SOURCE_DIR": dp.FUNDING_SOURCE_DIR,
            "SNAPSHOT_SOURCE_DIR": dp.SNAPSHOT_SOURCE_DIR,
            "MANIFEST_PATH": dp.MANIFEST_PATH,
            "CANDLE_DIR": dp.CANDLE_DIR,
            "FUNDING_DIR": dp.FUNDING_DIR,
            "SNAPSHOT_DIR": dp.SNAPSHOT_DIR,
            "EVENT_DIR": dp.EVENT_DIR,
            "RESEARCH_DIR": dp.RESEARCH_DIR,
        }
        dp.DATA_ROOT = self._data
        dp.LAKE_ROOT = self._lake
        dp.CANDLE_DIR = self._lake / "candles"
        dp.FUNDING_DIR = self._lake / "funding"
        dp.SNAPSHOT_DIR = self._lake / "snapshots"
        dp.EVENT_DIR = self._lake / "events"
        dp.RESEARCH_DIR = self._lake / "research"
        dp.CANDLE_SOURCE_DIR = self._data / "backtest"
        dp.FUNDING_SOURCE_DIR = self._data / "funding"
        dp.SNAPSHOT_SOURCE_DIR = self._data / "microstructure"
        dp.MANIFEST_PATH = self._lake / "manifest.json"

    def tearDown(self) -> None:
        for k, v in self._orig.items():
            setattr(dp, k, v)
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestCandleParse(PipelineIsolatedTestCase):
    def test_parse_candle_csv_name(self):
        self.assertEqual(dp.parse_candle_csv_name("BTC-USDT-SWAP_5m_300x24.csv"),
                         ("BTC-USDT-SWAP", "5m"))
        self.assertEqual(dp.parse_candle_csv_name("QQQ-USDT-SWAP_5m_300x60.csv"),
                         ("QQQ-USDT-SWAP", "5m"))
        self.assertIsNone(dp.parse_candle_csv_name("notes.txt"))

    def test_normalize_timeframe(self):
        self.assertEqual(dp.normalize_timeframe("1H"), "1h")
        self.assertEqual(dp.normalize_timeframe("5m"), "5m")
        self.assertEqual(dp.to_okx_bar("1h"), "1H")
        self.assertEqual(dp.to_okx_bar("1H"), "1H")
        self.assertEqual(dp.to_okx_bar("5m"), "5m")
        self.assertEqual(dp.tf_to_minutes("1h"), 60)
        self.assertEqual(dp.tf_to_minutes("5m"), 5)


class TestBuildAndMerge(PipelineIsolatedTestCase):
    def _make_two_overlapping_candle_csvs(self):
        times1 = ["2026-01-01T00:00:00+00:00", "2026-01-01T00:05:00+00:00", "2026-01-01T00:10:00+00:00"]
        times2 = ["2026-01-01T00:10:00+00:00", "2026-01-01T00:15:00+00:00", "2026-01-01T00:20:00+00:00"]
        make_candle_csv(dp.CANDLE_SOURCE_DIR / "BTC-USDT-SWAP_5m_300x2.csv", "BTC-USDT-SWAP", "5m", times1)
        make_candle_csv(dp.CANDLE_SOURCE_DIR / "BTC-USDT-SWAP_5m_300x3.csv", "BTC-USDT-SWAP", "5m", times2)

    def test_build_merges_overlapping_csvs(self):
        self._make_two_overlapping_candle_csvs()
        make_funding_csv(dp.FUNDING_SOURCE_DIR / "BTC-USDT-SWAP_funding_100.csv",
                         "BTC-USDT-SWAP", [1780732800000, 1780761600000])
        dp.cmd_build(build_args()) if False else None
        # invoke build through the subparser to mirror CLI
        args = build_args()
        rc = dp.cmd_build(args)
        self.assertEqual(rc, 0)

        df = dp.load_candles("BTC-USDT-SWAP", "5m")
        # 5 unique times (overlap 00:10 merged)
        self.assertEqual(len(df), 5)
        self.assertEqual(df["time"].iloc[0], pd.Timestamp("2026-01-01T00:00:00+00:00"))
        self.assertEqual(df["time"].iloc[-1], pd.Timestamp("2026-01-01T00:20:00+00:00"))
        self.assertTrue(df["time"].is_monotonic_increasing)

    def test_manifest_generated_with_stats(self):
        self._make_two_overlapping_candle_csvs()
        make_funding_csv(dp.FUNDING_SOURCE_DIR / "BTC-USDT-SWAP_funding_100.csv",
                         "BTC-USDT-SWAP", [1780732800000])
        dp.cmd_build(build_args())
        self.assertTrue(dp.MANIFEST_PATH.exists())
        manifest = json.loads(dp.MANIFEST_PATH.read_text())
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["stats"]["candleFiles"], 1)
        self.assertEqual(manifest["stats"]["fundingInstruments"], 1)
        # coverage key exists
        self.assertIn("BTC-USDT-SWAP/5m", manifest["coverage"]["candles"])

    def test_funding_conversion(self):
        make_funding_csv(dp.FUNDING_SOURCE_DIR / "ETH-USDT-SWAP_funding_100.csv",
                         "ETH-USDT-SWAP", [1780732800000, 1780761600000])
        dp.cmd_build(build_args())
        df = dp.load_funding("ETH-USDT-SWAP")
        self.assertEqual(len(df), 2)
        self.assertEqual(df["inst_id"].iloc[0], "ETH-USDT-SWAP")
        self.assertEqual(df["funding_time"].iloc[0], pd.Timestamp("2026-06-06T08:00:00+00:00"))

    def test_incremental_candles_page_backward_from_newest_without_looping(self):
        existing_times = ["2026-08-08T00:00:00+00:00", "2026-08-08T00:05:00+00:00"]
        make_candle_csv(
            dp.CANDLE_SOURCE_DIR / "SPCX-USDT-SWAP_5m_300x2.csv",
            "SPCX-USDT-SWAP",
            "5m",
            existing_times,
        )
        dp.cmd_build(build_args())
        all_times = [pd.Timestamp(f"2026-08-08T00:{minute:02d}:00+00:00") for minute in range(0, 25, 5)]

        def raw_row(value: pd.Timestamp) -> list[str]:
            ts = str(int(value.timestamp() * 1000))
            return [ts, "100", "101", "99", "100", "1", "1", "100", "1"]

        class FakeClient:
            def __init__(self) -> None:
                self.params: list[dict] = []

            def request(self, method, path, *, params=None):
                self.params.append(dict(params or {}))
                rows = all_times[2:] if "after" not in (params or {}) else all_times[:2]
                return {"data": [raw_row(value) for value in reversed(rows)]}

        client = FakeClient()
        counts = dp.collect_candles(client, ["SPCX-USDT-SWAP"], "5m", lookback_days=180, limit=3)
        frame = dp.load_candles("SPCX-USDT-SWAP", "5m")

        self.assertEqual(counts["SPCX-USDT-SWAP"], 3)
        self.assertEqual(len(frame), 5)
        self.assertNotIn("before", client.params[0])
        self.assertIn("after", client.params[1])
        manifest = dp.build_manifest()
        coverage = manifest["coverage"]["candles"]["SPCX-USDT-SWAP/5m"]
        self.assertEqual(sum(row["rows"] for row in coverage), 5)

    def test_backfill_walks_older_than_existing_earliest(self):
        existing_times = ["2026-08-08T00:10:00+00:00", "2026-08-08T00:15:00+00:00"]
        make_candle_csv(
            dp.CANDLE_SOURCE_DIR / "SPCX-USDT-SWAP_5m_300x2.csv",
            "SPCX-USDT-SWAP",
            "5m",
            existing_times,
        )
        dp.cmd_build(build_args())
        older = [pd.Timestamp("2026-08-08T00:00:00+00:00"), pd.Timestamp("2026-08-08T00:05:00+00:00")]
        newer = [pd.Timestamp(value) for value in existing_times]

        def raw_row(value: pd.Timestamp) -> list[str]:
            ts = str(int(value.timestamp() * 1000))
            return [ts, "100", "101", "99", "100", "1", "1", "100", "1"]

        class FakeClient:
            def request(self, method, path, *, params=None):
                if "after" in (params or {}):
                    return {"data": [raw_row(value) for value in reversed(older)]}
                return {"data": [raw_row(value) for value in reversed(newer)]}

        counts = dp.collect_candles(
            FakeClient(),
            ["SPCX-USDT-SWAP"],
            "5m",
            lookback_days=3650,
            limit=3,
            backfill=True,
        )
        frame = dp.load_candles("SPCX-USDT-SWAP", "5m")
        self.assertEqual(counts["SPCX-USDT-SWAP"], 2)
        self.assertEqual(len(frame), 4)
        self.assertEqual(frame["time"].iloc[0], pd.Timestamp("2026-08-08T00:00:00+00:00"))

    def test_manifest_indexes_lake_only_funding_without_raw_csv(self):
        frame = pd.DataFrame(
            {
                "funding_time": pd.to_datetime(["2026-08-08T00:00:00Z", "2026-08-08T08:00:00Z"]),
                "funding_rate": [0.0001, 0.0002],
                "realized_rate": [0.0001, 0.0002],
                "inst_id": ["SPY-USDT-SWAP", "SPY-USDT-SWAP"],
            }
        )
        dp.write_funding_parquet(frame, "SPY-USDT-SWAP")

        manifest = dp.build_manifest()

        coverage = manifest["coverage"]["funding"]["SPY-USDT-SWAP"]
        self.assertEqual(sum(row["rows"] for row in coverage), 2)
        self.assertEqual(manifest["stats"]["fundingInstruments"], 1)

    def test_locked_equity_refresh_keeps_qqq_and_universe_order(self) -> None:
        universe = Path(self._tmp) / "universe.csv"
        universe.write_text(
            "symbol,cik\nAMD,2488\nQQQ,000000\nGOOGL,1652044\n",
            encoding="utf-8",
        )
        targets = dp.locked_equity_refresh_targets(universe)
        self.assertEqual([item["symbol"] for item in targets], ["QQQ", "AMD", "GOOGL"])
        self.assertIsNone(targets[0]["cik"])
        self.assertEqual(targets[1]["cik"], 2488)

    def test_collect_equity_caches_uses_injected_public_loaders(self) -> None:
        universe = Path(self._tmp) / "universe.csv"
        universe.write_text("symbol,cik\nAMD,2488\n", encoding="utf-8")
        calls: list[tuple[str, object]] = []

        def price_loader(symbol, data_root, *, history_range, refresh):
            calls.append(("price", symbol, history_range, refresh, data_root))

        def sec_loader(cik, data_root, *, refresh):
            calls.append(("sec", cik, refresh, data_root))

        counts = dp.collect_equity_caches(
            data_root=Path(self._tmp) / "qqq",
            universe_path=universe,
            price_loader=price_loader,
            sec_loader=sec_loader,
        )
        self.assertEqual(counts["prices"], 2)
        self.assertEqual(counts["sec"], 1)
        self.assertEqual(counts["errors"], [])
        self.assertEqual(calls[0][0], "price")
        self.assertEqual(calls[0][1], "QQQ")
        self.assertEqual(calls[-1][0], "sec")
        self.assertEqual(calls[-1][1], 2488)


class TestAccessApi(PipelineIsolatedTestCase):
    def setUp(self):
        super().setUp()
        times = ["2026-01-01T00:00:00+00:00", "2026-01-01T00:05:00+00:00", "2026-01-01T00:10:00+00:00",
                 "2026-02-01T00:00:00+00:00", "2026-02-01T00:05:00+00:00"]
        make_candle_csv(dp.CANDLE_SOURCE_DIR / "QQQ-USDT-SWAP_5m_300x60.csv", "QQQ-USDT-SWAP", "5m", times)
        dp.cmd_build(build_args())

    def test_time_filter(self):
        df = dp.load_candles("QQQ-USDT-SWAP", "5m",
                             start="2026-02-01T00:00:00+00:00", end="2026-02-01T00:05:00+00:00")
        self.assertEqual(len(df), 2)
        self.assertEqual(df["time"].min(), pd.Timestamp("2026-02-01T00:00:00+00:00"))

    def test_missing_instrument_empty(self):
        df = dp.load_candles("NOPE-USDT-SWAP", "5m")
        self.assertTrue(df.empty)

    def test_available_instruments(self):
        self.assertIn("qqq_usdt_swap", dp.available_instruments("candles"))
        self.assertIn("5m", dp.available_timeframes("QQQ-USDT-SWAP"))

    def test_snapshot_load(self):
        # write a small snapshot jsonl
        inst_dir = dp.SNAPSHOT_SOURCE_DIR / "btc_usdt_swap"
        inst_dir.mkdir(exist_ok=True)
        (inst_dir / "20260101.jsonl").write_text(
            '{"capturedAt":"2026-01-01T00:00:00+00:00","instId":"BTC-USDT-SWAP","ok":true}\n'
            '{"capturedAt":"2026-01-01T00:30:00+00:00","instId":"BTC-USDT-SWAP","ok":true}\n',
            encoding="utf-8")
        dp.cmd_build(build_args())
        df = dp.load_snapshots("btc_usdt_swap")
        self.assertEqual(len(df), 2)
        self.assertEqual(list(df.columns)[0], "capturedAt")

    def test_build_skips_snapshot_copy_when_source_and_lake_are_the_same(self) -> None:
        inst_dir = dp.SNAPSHOT_SOURCE_DIR / "btc_usdt_swap"
        inst_dir.mkdir(exist_ok=True)
        payload = '{"capturedAt":"2026-01-01T00:00:00+00:00","instId":"BTC-USDT-SWAP","ok":true}\n'
        (inst_dir / "20260101.jsonl").write_text(payload, encoding="utf-8")
        dp.SNAPSHOT_DIR = dp.SNAPSHOT_SOURCE_DIR
        dp.cmd_build(build_args())
        self.assertEqual((inst_dir / "20260101.jsonl").read_text(encoding="utf-8"), payload)

    def test_event_and_research_observation_loaders(self):
        dp.EVENT_DIR.mkdir(parents=True)
        (dp.EVENT_DIR / "20260101.jsonl").write_text(
            '{"capturedAt":"2026-01-01T00:00:00Z","eventId":"cpi-2026-01-01","dataComplete":false}\n'
            '{"capturedAt":"2026-01-01T01:00:00Z","eventId":"cpi-2026-01-01","dataComplete":true}\n',
            encoding="utf-8",
        )
        model_dir = dp.RESEARCH_DIR / "model-1"
        model_dir.mkdir(parents=True)
        (model_dir / "20260101.jsonl").write_text(
            '{"capturedAt":"2026-01-01T00:30:00Z","modelId":"model-1","signal":{"side":1}}\n',
            encoding="utf-8",
        )

        events = dp.load_events("cpi-2026-01-01", start="2026-01-01T00:30:00Z")
        observations = dp.load_research_observations("model-1")

        self.assertEqual(len(events), 1)
        self.assertTrue(bool(events.iloc[0]["dataComplete"]))
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations.iloc[0]["signal.side"], 1)

    def test_manifest_counts_forward_datasets(self):
        dp.EVENT_DIR.mkdir(parents=True)
        (dp.EVENT_DIR / "20260101.jsonl").write_text(
            '{"capturedAt":"2026-01-01T00:00:00Z","eventId":"event-1"}\n', encoding="utf-8"
        )
        model_dir = dp.RESEARCH_DIR / "model-1"
        model_dir.mkdir(parents=True)
        (model_dir / "20260101.jsonl").write_text(
            '{"capturedAt":"2026-01-01T00:00:00Z","modelId":"model-1"}\n', encoding="utf-8"
        )

        manifest = dp.build_manifest()

        self.assertEqual(manifest["stats"]["eventRows"], 1)
        self.assertEqual(manifest["stats"]["researchModels"], 1)
        self.assertEqual(manifest["stats"]["researchRows"], 1)


class TestTrackingUniverseConfig(unittest.TestCase):
    def test_repository_snapshot_adds_all_index_contracts_to_defaults(self):
        payload = json.loads(dp.TRADFI_TRACKING_PATH.read_text(encoding="utf-8"))
        tracked = payload["trackedInstruments"]
        expected = sorted(set(payload["indexProxyInstruments"])
                          | set(payload["nasdaq100Instruments"])
                          | set(payload["sp500Instruments"]))

        self.assertEqual(tracked, expected)
        self.assertEqual(len(tracked), 62)
        self.assertEqual(len(payload["nasdaq100Instruments"]), 38)
        self.assertEqual(len(payload["sp500Instruments"]), 51)
        defaults = dp.configured_collection_instruments()
        self.assertEqual(len(defaults), 67)
        self.assertTrue(set(dp.BASE_COLLECTION_INSTRUMENTS).issubset(defaults))
        self.assertTrue(set(tracked).issubset(defaults))
        self.assertIn("XAU-USDT-SWAP", defaults)
        self.assertEqual(
            dp.CORE_DAILY_INSTRUMENTS,
            ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "XAU-USDT-SWAP"),
        )

    def test_rejects_tracking_list_that_is_not_the_index_union(self):
        payload = {
            "schemaVersion": 1,
            "indexProxyInstruments": ["QQQ-USDT-SWAP", "SPY-USDT-SWAP"],
            "nasdaq100Instruments": ["AAPL-USDT-SWAP"],
            "sp500Instruments": ["AAPL-USDT-SWAP"],
            "trackedInstruments": ["AAPL-USDT-SWAP", "QQQ-USDT-SWAP"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tracking.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must equal the union"):
                dp.configured_collection_instruments(path)

    def test_rejects_unsorted_or_invalid_instruments(self):
        payload = {
            "schemaVersion": 1,
            "indexProxyInstruments": ["SPY-USDT-SWAP", "QQQ-USDT-SWAP"],
            "nasdaq100Instruments": ["not-a-contract"],
            "sp500Instruments": ["AAPL-USDT-SWAP"],
            "trackedInstruments": ["AAPL-USDT-SWAP"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tracking.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sorted and unique"):
                dp.configured_collection_instruments(path)


class TestCsvParserRobustness(PipelineIsolatedTestCase):
    def test_csv_with_duplicate_rows_dedupes(self):
        times = ["2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", "2026-01-01T00:05:00+00:00"]
        make_candle_csv(dp.CANDLE_SOURCE_DIR / "ETH-USDT-SWAP_5m_300x2.csv", "ETH-USDT-SWAP", "5m", times)
        dp.cmd_build(build_args())
        df = dp.load_candles("ETH-USDT-SWAP", "5m")
        self.assertEqual(len(df), 2)


if __name__ == "__main__":
    unittest.main()
