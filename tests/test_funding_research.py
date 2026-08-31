from __future__ import annotations

import unittest
from types import SimpleNamespace

from backtest.okx_grid_backtest import Candle
from funding_research import FundingPoint, funding_point_from_payload, funding_targets, simulate_funding_segment


def candle(index: int, close: float = 100.0) -> Candle:
    return Candle(ts=index * 60_000, open=close, high=close, low=close, close=close, volume=0.0)


class FundingResearchTest(unittest.TestCase):
    def test_funding_payload_parses_realized_rate_fallback(self) -> None:
        point = funding_point_from_payload({"fundingTime": "60000", "fundingRate": "0.0001", "realizedRate": ""})

        self.assertIsNotNone(point)
        assert point is not None
        self.assertEqual(point.ts, 60_000)
        self.assertEqual(point.rate, 0.0001)
        self.assertEqual(point.realized_rate, 0.0001)

    def test_funding_targets_use_prior_funding_event_only(self) -> None:
        candles = [candle(index) for index in range(4)]
        funding = [FundingPoint(ts=120_000, rate=0.001, realized_rate=0.001)]

        targets = funding_targets(candles, funding, {"threshold_bps": 1.0, "mode": "carry"})

        self.assertEqual(targets[2], 0)
        self.assertEqual(targets[3], -1)

    def test_positive_funding_pays_shorts_and_charges_longs(self) -> None:
        candles = [candle(index) for index in range(4)]
        funding = [FundingPoint(ts=120_000, rate=0.01, realized_rate=0.01)]
        args = SimpleNamespace(
            starting_equity=100.0,
            leverage=1.0,
            margin_pct=100.0,
            fee_bps=0.0,
            slippage_bps=0.0,
            cost_stress_multiplier=1.0,
        )

        short = simulate_funding_segment(candles, funding, [0, -1, -1, 0], 1, 4, args)
        long = simulate_funding_segment(candles, funding, [0, 1, 1, 0], 1, 4, args)

        self.assertGreater(short.funding_pnl, 0)
        self.assertLess(long.funding_pnl, 0)
        self.assertGreater(short.return_pct, long.return_pct)


if __name__ == "__main__":
    unittest.main()
