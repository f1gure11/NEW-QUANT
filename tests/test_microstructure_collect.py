from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from microstructure_collect import (
    DEFAULT_FORWARD_REGISTRY,
    append_snapshot,
    book_stats,
    depth_features,
    fetch_microstructure_snapshot,
    forward_instruments,
    forward_snapshot_metadata,
    load_forward_registry,
    trade_stats,
    validate_forward_instrument_metadata,
    validate_forward_registry,
)


class FakePublicClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], bool]] = []

    def request(self, method, path, *, params=None, body=None, private=False):
        self.calls.append((method, path, params or {}, private))
        if path == "/api/v5/market/ticker":
            return {"data": [{"instId": "AAA-USDT-SWAP", "bidPx": "99", "askPx": "101", "last": "100", "ts": "1"}]}
        if path == "/api/v5/market/books":
            return {
                "data": [
                    {
                        "ts": "2",
                        "bids": [["99", "2"], ["98", "1"]],
                        "asks": [["101", "1"], ["102", "1"]],
                    }
                ]
            }
        if path == "/api/v5/market/trades":
            return {
                "data": [
                    {"ts": "3", "side": "buy", "px": "100", "sz": "2", "tradeId": "a"},
                    {"ts": "4", "side": "sell", "px": "101", "sz": "1", "tradeId": "b"},
                ]
            }
        if path == "/api/v5/public/open-interest":
            return {"data": [{"instId": "AAA-USDT-SWAP", "oi": "10", "oiCcy": "1", "oiUsd": "100", "ts": "5", "ctVal": "0.1"}]}
        if path == "/api/v5/public/funding-rate":
            return {"data": [{"instId": "AAA-USDT-SWAP", "fundingRate": "0.0001", "premium": "-0.0002", "fundingTime": "6", "ts": "5"}]}
        raise AssertionError(path)


class MicrostructureCollectTest(unittest.TestCase):
    def test_book_stats_computes_depth_and_imbalance(self) -> None:
        stats = book_stats(
            {"bids": [["99", "2"], ["98", "1"]], "asks": [["101", "1"], ["102", "1"]]},
            {"bidPx": "99", "askPx": "101"},
        )

        self.assertAlmostEqual(stats.mid, 100.0)
        self.assertAlmostEqual(stats.spread_bps, 200.0)
        self.assertAlmostEqual(stats.bid_depth_5, 296.0)
        self.assertAlmostEqual(stats.ask_depth_5, 203.0)
        self.assertGreater(stats.imbalance_5, 0)

    def test_trade_stats_computes_signed_flow_imbalance(self) -> None:
        stats = trade_stats(
            [
                {"ts": "1", "side": "buy", "px": "100", "sz": "2"},
                {"ts": "2", "side": "sell", "px": "100", "sz": "1"},
            ],
            contract_value=__import__("decimal").Decimal("0.1"),
        )

        self.assertEqual(stats.buy_count, 1)
        self.assertEqual(stats.sell_count, 1)
        self.assertAlmostEqual(stats.buy_notional, 20.0)
        self.assertAlmostEqual(stats.sell_notional, 10.0)
        self.assertAlmostEqual(stats.imbalance, 1 / 3)
        self.assertEqual(stats.last_trade_ts, 2)

    def test_snapshot_uses_public_endpoints_only(self) -> None:
        client = FakePublicClient()
        research = {
            "modelId": "model-1",
            "observationOnly": True,
            "paperOrLiveAuthorized": False,
        }

        snapshot = fetch_microstructure_snapshot(
            client,
            "AAA-USDT-SWAP",
            books_size=50,
            trades_limit=100,
            captured_at="now",
            instrument={"instId": "AAA-USDT-SWAP", "ctVal": "0.1", "instCategory": "3"},
            research=research,
        )

        self.assertTrue(snapshot["ok"])
        self.assertTrue(snapshot["dataComplete"])
        self.assertEqual(snapshot["schemaVersion"], 2)
        self.assertEqual(snapshot["instId"], "AAA-USDT-SWAP")
        self.assertEqual(snapshot["research"], research)
        self.assertEqual(snapshot["features"]["open_interest"]["usd"], 100.0)
        self.assertEqual(snapshot["features"]["premium"]["premium_rate"], -0.0002)
        self.assertEqual(snapshot["features"]["order_flow"]["sample_type"], "latest_public_trades_at_capture")
        self.assertEqual(snapshot["features"]["depth"]["contract_value"], 0.1)
        self.assertEqual(snapshot["features"]["trades"]["buyCount"] if "buyCount" in snapshot["features"]["trades"] else snapshot["features"]["trades"]["buy_count"], 1)
        self.assertTrue(all(not private for _, _, _, private in client.calls))
        self.assertEqual(
            [path for _, path, _, _ in client.calls],
            [
                "/api/v5/market/ticker",
                "/api/v5/market/books",
                "/api/v5/market/trades",
                "/api/v5/public/open-interest",
                "/api/v5/public/funding-rate",
            ],
        )

    def test_append_snapshot_partitions_by_safe_instrument_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = append_snapshot(Path(tmpdir), {"instId": "AAA-USDT-SWAP", "ok": True})
            payload = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(path.parent.name, "aaa_usdt_swap")
        self.assertEqual(payload["instId"], "AAA-USDT-SWAP")

    def test_depth_features_freezes_5_10_25_50_level_contract_and_notional_views(self) -> None:
        bids = [[str(100 - index), "2"] for index in range(50)]
        asks = [[str(101 + index), "1"] for index in range(50)]

        features = depth_features(
            {"ts": "123", "bids": bids, "asks": asks},
            contract_value=__import__("decimal").Decimal("0.1"),
            requested_levels=50,
        )

        self.assertEqual(features["returned_bid_levels"], 50)
        self.assertEqual(features["returned_ask_levels"], 50)
        self.assertEqual(features["bid_contracts_50"], 100.0)
        self.assertEqual(features["ask_contracts_50"], 50.0)
        self.assertAlmostEqual(features["bid_notional_5"], 98.0)
        self.assertAlmostEqual(features["ask_notional_5"], 51.5)
        self.assertGreater(features["imbalance_50"], -1.0)
        self.assertLess(features["imbalance_50"], 1.0)


class ForwardRegistryTest(unittest.TestCase):
    def test_registry_matches_exact_frozen_29_contract_universe(self) -> None:
        registry = load_forward_registry(DEFAULT_FORWARD_REGISTRY)

        self.assertEqual(len(forward_instruments(registry)), 29)
        self.assertNotIn("DASH-USDT-SWAP", forward_instruments(registry))
        self.assertFalse(registry["study"]["paperOrLiveAuthorized"])
        self.assertEqual(registry["study"]["maturity"]["minimumCompleteCalendarMonths"], 12)
        self.assertEqual(registry["study"]["maturity"]["minimumIndependentReductionEvents"], 100)
        metadata = forward_snapshot_metadata(registry)
        self.assertTrue(metadata["observationOnly"])
        self.assertFalse(metadata["historyReplayUsed"])
        self.assertFalse(metadata["paperOrLiveAuthorized"])

    def test_registry_rejects_tampering(self) -> None:
        registry = load_forward_registry(DEFAULT_FORWARD_REGISTRY)
        changed = copy.deepcopy(registry)
        changed["study"]["basis"]["orderFlow"]["requestedLatestTrades"] = 500

        with self.assertRaisesRegex(ValueError, "registryId"):
            validate_forward_registry(changed)

    def test_forward_metadata_must_be_live_tradfi_with_contract_value(self) -> None:
        valid = {
            "AAA-USDT-SWAP": {
                "instId": "AAA-USDT-SWAP",
                "state": "live",
                "instCategory": "3",
                "ctVal": "0.1",
            }
        }

        validate_forward_instrument_metadata(valid, ["AAA-USDT-SWAP"])
        with self.assertRaisesRegex(ValueError, "missing public metadata"):
            validate_forward_instrument_metadata({}, ["AAA-USDT-SWAP"])
        changed = copy.deepcopy(valid)
        changed["AAA-USDT-SWAP"]["instCategory"] = "1"
        with self.assertRaisesRegex(ValueError, "not live category-3"):
            validate_forward_instrument_metadata(changed, ["AAA-USDT-SWAP"])


if __name__ == "__main__":
    unittest.main()
