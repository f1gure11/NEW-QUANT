from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from microstructure_ws_audit import audit_root


class MicrostructureWebSocketAuditTests(unittest.TestCase):
    def test_complete_fresh_sample_is_ready(self) -> None:
        now_ts = 1_800_010_800_000
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_sample(root, "BTC-USDT-SWAP", 1_799_999_900_000)
            self._write_sample(root, "BTC-USDT-SWAP", now_ts - 1_000)
            result = audit_root(
                root,
                ("BTC-USDT-SWAP",),
                ("books5", "trades", "tickers"),
                min_duration_hours=3.0,
                max_gap_seconds=12_000.0,
                now_ts=now_ts,
            )
        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "ready_for_forward_backtest")

    def test_short_sample_remains_collecting(self) -> None:
        now_ts = 1_800_000_001_000
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_sample(root, "BTC-USDT-SWAP", now_ts - 1_000)
            result = audit_root(
                root,
                ("BTC-USDT-SWAP",),
                ("books5", "trades", "tickers"),
                min_duration_hours=72.0,
                now_ts=now_ts,
            )
        self.assertFalse(result["ready"])
        self.assertTrue(any("duration" in reason for reason in result["instruments"][0]["reasons"]))

    def test_crossed_book_is_reported_as_invalid(self) -> None:
        now_ts = 1_800_000_001_000
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_event(
                root,
                "BTC-USDT-SWAP",
                "books5",
                now_ts - 1_000,
                {"ts": str(now_ts - 1_001), "bids": [["101", "1"]], "asks": [["100", "1"]]},
            )
            result = audit_root(
                root,
                ("BTC-USDT-SWAP",),
                ("books5",),
                min_duration_hours=0.0,
                max_invalid_pct=0.0,
                now_ts=now_ts,
            )
        channel = result["instruments"][0]["channels"]["books5"]
        self.assertEqual(channel["invalidPayloads"], 1)
        self.assertFalse(result["ready"])

    def test_missing_channels_produce_serializable_collecting_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = audit_root(
                Path(tmpdir),
                ("BTC-USDT-SWAP",),
                ("books5", "trades", "tickers"),
                now_ts=1_800_000_001_000,
            )
        self.assertFalse(result["ready"])
        self.assertIsNone(result["instruments"][0]["channels"]["books5"]["stalenessSeconds"])
        json.dumps(result, allow_nan=False)

    def test_long_capture_gap_blocks_readiness(self) -> None:
        now_ts = 1_800_010_800_000
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_sample(root, "BTC-USDT-SWAP", 1_799_999_900_000)
            self._write_sample(root, "BTC-USDT-SWAP", now_ts - 1_000)
            result = audit_root(
                root,
                ("BTC-USDT-SWAP",),
                ("books5", "trades", "tickers"),
                min_duration_hours=3.0,
                max_gap_seconds=60.0,
                now_ts=now_ts,
            )
        self.assertFalse(result["ready"])
        self.assertTrue(any("maximum gap" in reason for reason in result["instruments"][0]["reasons"]))

    def _write_sample(self, root: Path, inst_id: str, captured_ts: int) -> None:
        self._write_event(
            root,
            inst_id,
            "books5",
            captured_ts,
            {"ts": str(captured_ts - 1), "bids": [["99", "1"]], "asks": [["101", "1"]]},
        )
        self._write_event(
            root,
            inst_id,
            "trades",
            captured_ts,
            {"ts": str(captured_ts - 1), "side": "buy", "px": "100", "sz": "1", "tradeId": str(captured_ts)},
        )
        self._write_event(
            root,
            inst_id,
            "tickers",
            captured_ts,
            {"ts": str(captured_ts - 1), "bidPx": "99", "askPx": "101"},
        )

    @staticmethod
    def _write_event(root: Path, inst_id: str, channel: str, captured_ts: int, data: dict[str, object]) -> None:
        path = root / "btc_usdt_swap" / "20270115.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "capturedAt": "2027-01-15T00:00:00Z",
            "capturedTs": captured_ts,
            "source": "okx_public_websocket",
            "instId": inst_id,
            "channel": channel,
            "action": "snapshot",
            "data": data,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    unittest.main()
