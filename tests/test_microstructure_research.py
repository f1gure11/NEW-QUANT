from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from microstructure_research import evaluate_records, load_records, signal_side, write_outputs


def snapshot(ts: int, mid: float, book_imbalance: float, trade_imbalance: float) -> dict:
    return {
        "capturedTs": ts,
        "instId": "AAA-USDT-SWAP",
        "ok": True,
        "ticker": {"bidPx": str(mid - 0.5), "askPx": str(mid + 0.5)},
        "features": {
            "book": {"mid": mid, "imbalance_10": book_imbalance},
            "trades": {"imbalance": trade_imbalance},
        },
    }


class MicrostructureResearchTest(unittest.TestCase):
    def test_signal_side_requires_prior_snapshot_features(self) -> None:
        row = snapshot(1, 100.0, 0.3, -0.1)

        self.assertEqual(signal_side(row, "book.imbalance_10", 0.2), 1)
        self.assertEqual(signal_side(row, "trades.imbalance", 0.2), 0)
        self.assertEqual(signal_side(row, "combined", 0.2), 0)

    def test_evaluate_records_uses_current_snapshot_signal_for_next_mid_return(self) -> None:
        rows = [
            snapshot(1, 100.0, 0.5, 0.5),
            snapshot(2, 101.0, 0.0, 0.0),
            snapshot(3, 102.0, -0.5, -0.5),
            snapshot(4, 101.0, 0.0, 0.0),
        ]
        args = SimpleNamespace(min_samples=4, threshold=0.2, fee_bps=0.0, slippage_bps=0.0, cost_stress_multiplier=1.0)

        results = evaluate_records({"AAA-USDT-SWAP": rows}, args)
        by_strategy = {result.strategy: result for result in results}

        self.assertGreater(by_strategy["book_imbalance"].total_return_pct, 1.9)
        self.assertEqual(by_strategy["book_imbalance"].trades, 2)
        self.assertGreater(by_strategy["book_imbalance"].profit_factor, 1.0)

    def test_load_records_and_insufficient_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data" / "aaa_usdt_swap"
            data_dir.mkdir(parents=True)
            (data_dir / "20260702.jsonl").write_text(json.dumps(snapshot(1, 100.0, 0.1, 0.1)) + "\n", encoding="utf-8")
            output = root / "report"
            args = SimpleNamespace(min_samples=10, threshold=0.2, fee_bps=5.0, slippage_bps=2.0, cost_stress_multiplier=1.5)

            records = load_records(root / "data")
            results = evaluate_records(records, args)
            write_outputs(output, records, results, args)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))["summary"]

        self.assertEqual(summary["status"], "insufficient_data")
        self.assertEqual(summary["totalSnapshots"], 1)


if __name__ == "__main__":
    unittest.main()
