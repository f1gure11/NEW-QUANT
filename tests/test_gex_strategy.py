from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from backtest.okx_grid_backtest import Candle
from gex_strategy import StrategyConfig, backtest, generate_signal, load_snapshot_series, snapshot_before


def make_candles(prices: list[float], volumes: list[float] | None = None) -> list[Candle]:
    volumes = volumes or [1.0] * len(prices)
    candles: list[Candle] = []
    for index, close in enumerate(prices):
        previous = prices[index - 1] if index else close
        open_price = close - 0.1 if index == len(prices) - 1 else previous
        high = max(open_price, close) + 0.1
        low = min(open_price, close) - 0.1
        candles.append(
            Candle(
                ts=1_700_000_000_000 + index * 300_000,
                open=Decimal(str(open_price)),
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(close)),
                volume=Decimal(str(volumes[index])),
            )
        )
    return candles


def gex_row(*, net_gex: float, call_wall: float = 110.0, put_wall: float = 100.0) -> dict[str, object]:
    return {
        "netGex": net_gex,
        "callWall": {"strike": call_wall},
        "putWall": {"strike": put_wall},
    }


class GexStrategyTest(unittest.TestCase):
    def test_positive_gamma_put_wall_rejection_is_long(self) -> None:
        candles = make_candles([90 + index * (10 / 39) for index in range(40)])
        signal = generate_signal(candles, gex_row(net_gex=100.0))
        self.assertEqual(signal["direction"], 1)
        self.assertEqual(signal["reason"], "positive_gamma_put_wall_rejection")
        self.assertEqual(signal["holdingWindow"], "30m-6h on 5m bars")

    def test_positive_gamma_call_wall_rejection_is_short(self) -> None:
        candles = make_candles([110 - index * (10 / 39) for index in range(40)])
        signal = generate_signal(candles, gex_row(net_gex=100.0, call_wall=100.0, put_wall=90.0))
        self.assertEqual(signal["direction"], -1)
        self.assertEqual(signal["reason"], "positive_gamma_call_wall_rejection")

    def test_negative_gamma_requires_volume_confirmed_breakout(self) -> None:
        prices = [90 + index * (21 / 39) for index in range(40)]
        candles = make_candles(prices, [1.0] * 39 + [2.0])
        signal = generate_signal(candles, gex_row(net_gex=-100.0, call_wall=100.0, put_wall=80.0))
        self.assertEqual(signal["direction"], 1)
        self.assertEqual(signal["reason"], "negative_gamma_call_wall_breakout")
        self.assertGreaterEqual(signal["volumeRatio"], 1.1)

    def test_snapshot_series_is_point_in_time_sorted_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            payload = {"updatedAt": "2026-07-16T00:05:00+00:00", "underlyings": [{"underlying": "BTC", "netGex": 2}]}
            records = [
                {"capturedAt": "2026-07-16T00:05:00+00:00", "data": payload},
                {"capturedAt": "2026-07-16T00:00:00+00:00", "data": {"underlyings": [{"underlying": "BTC", "netGex": 1}]}},
                {"capturedAt": "2026-07-16T00:05:00+00:00", "data": payload},
            ]
            path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            series = load_snapshot_series(path)["BTC"]

        self.assertEqual(len(series), 2)
        self.assertLess(series[0][0], series[1][0])
        self.assertEqual(series[1][1]["netGex"], 2)
        self.assertEqual(snapshot_before(series, series[1][0])["netGex"], 2)

    def test_backtest_refuses_snapshot_history_that_does_not_overlap_candles(self) -> None:
        candles = make_candles([100 + index * 0.1 for index in range(80)])
        snapshots = [
            (candles[-1].ts + (index + 1) * 300_000, gex_row(net_gex=1.0))
            for index in range(12)
        ]
        result = backtest(candles, snapshots, StrategyConfig())
        self.assertEqual(result["status"], "insufficient_history")
        self.assertEqual(result["reason"], "point_in_time_gex_snapshots_do_not_overlap_candles")

    def test_backtest_closes_open_paper_position_at_end_of_data(self) -> None:
        prices = [90 + index * (10 / 39) for index in range(40)] + [100.0] * 30
        candles = make_candles(prices)
        snapshots = [
            (candles[0].ts + index * 300_000, gex_row(net_gex=100.0))
            for index in range(12)
        ]
        result = backtest(candles, snapshots, StrategyConfig())
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["tradeCount"], 1)
        self.assertIn(result["trades"][-1]["reason"], {"take_profit", "end_of_data", "stop"})

    def test_backtest_does_not_open_from_expired_gex_snapshot(self) -> None:
        prices = [90 + index * (10 / 39) for index in range(40)] + [100.0] * 30
        candles = make_candles(prices)
        snapshots = [
            (
                candles[0].ts - 10 * 60 * 60 * 1000 + index * 300_000,
                gex_row(net_gex=100.0),
            )
            for index in range(12)
        ]
        result = backtest(candles, snapshots, StrategyConfig(max_gex_age_hours=6.0))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tradeCount"], 0)
        self.assertGreater(result["staleSnapshotBars"], 0)


if __name__ == "__main__":
    unittest.main()
