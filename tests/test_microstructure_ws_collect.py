from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from microstructure_ws_collect import append_event, event_rows, subscription_args


class MicrostructureWebSocketCollectionTests(unittest.TestCase):
    def test_subscriptions_cover_each_public_channel_and_instrument(self) -> None:
        args = subscription_args(("BTC-USDT-SWAP", "ETH-USDT-SWAP"), ("books5", "trades"))
        self.assertEqual(
            args,
            [
                {"channel": "books5", "instId": "BTC-USDT-SWAP"},
                {"channel": "trades", "instId": "BTC-USDT-SWAP"},
                {"channel": "books5", "instId": "ETH-USDT-SWAP"},
                {"channel": "trades", "instId": "ETH-USDT-SWAP"},
            ],
        )

    def test_event_rows_keep_raw_channel_payload_and_capture_time(self) -> None:
        rows = event_rows(
            {
                "arg": {"channel": "books5", "instId": "BTC-USDT-SWAP"},
                "action": "snapshot",
                "data": [{"asks": [["101", "1"]], "bids": [["99", "2"]], "ts": "1"}],
            },
            captured_at="2026-08-07T00:00:00Z",
            captured_ts=1_800_000_000_000,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["channel"], "books5")
        self.assertEqual(rows[0]["instId"], "BTC-USDT-SWAP")
        self.assertEqual(rows[0]["data"]["bids"][0][0], "99")

    def test_non_market_messages_do_not_create_data_rows(self) -> None:
        self.assertEqual(event_rows({"event": "subscribe", "arg": {}}, captured_at="now", captured_ts=1), [])

    def test_append_event_partitions_by_instrument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = append_event(
                Path(tmpdir),
                {"instId": "BTC-USDT-SWAP", "channel": "trades", "data": {"tradeId": "1"}},
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path.parent.name, "btc_usdt_swap")
        self.assertEqual(payload["data"]["tradeId"], "1")


if __name__ == "__main__":
    unittest.main()
