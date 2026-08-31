from __future__ import annotations

import math
import unittest
from dataclasses import replace

import numpy as np

from multifactor_dynamic_rr_research import (
    MAX_LOOKBACK,
    DynamicCandidate,
    FeatureSeries,
    dynamic_levels,
    feature_names,
    prepare_series,
    simulate_dynamic_rr,
)
from orderflow_rr_research import OrderFlowSnapshot, parse_snapshot


def snapshots(count: int) -> list[OrderFlowSnapshot]:
    rows = []
    for index in range(count):
        mid = 100.0 + index * 0.01 + math.sin(index / 15.0)
        rows.append(
            OrderFlowSnapshot(
                ts=1_800_000_000_000 + index * 60_000,
                bid=mid - 0.005,
                ask=mid + 0.005,
                mid=mid,
                spread_bps=1.0,
                book_imbalance=0.1,
                trade_imbalance=0.2,
                ofi=0.1,
                volume=1_000.0 + index,
                bid_depth_5=100.0 + index,
                ask_depth_5=100.0,
                bid_depth_10=200.0,
                ask_depth_10=200.0,
            )
        )
    return rows


class MultiFactorDynamicRewardRiskTests(unittest.TestCase):
    def test_feature_families_are_explicit(self) -> None:
        names = feature_names()
        for prefix in ("momentum_", "liquidity_", "correlation_", "technical_", "alpha"):
            self.assertTrue(any(name.startswith(prefix) for name in names), prefix)
        self.assertIn("alpha101", names)

    def test_features_do_not_use_a_later_snapshot(self) -> None:
        original_rows = snapshots(400)
        changed_rows = list(original_rows)
        changed_rows[350] = replace(changed_rows[350], mid=200.0, bid=199.99, ask=200.01)
        original = prepare_series("BTC-USDT-SWAP", original_rows, original_rows)
        changed = prepare_series("BTC-USDT-SWAP", changed_rows, changed_rows)
        feature_position = 349 - MAX_LOOKBACK
        self.assertTrue(np.allclose(original.features[feature_position], changed.features[feature_position]))

    def test_parser_keeps_liquidity_inputs(self) -> None:
        parsed = parse_snapshot(
            {
                "capturedTs": 1_800_000_000_000,
                "ticker": {"bidPx": "99.9", "askPx": "100.1", "bidSz": "2", "askSz": "3"},
                "book": {"bids": [["99.9", "2"]], "asks": [["100.1", "3"]]},
                "features": {
                    "book": {"bid_depth_5": "120", "ask_depth_5": "80"},
                    "trades": {"buy_notional": "700", "sell_notional": "300"},
                },
            },
            None,
        )
        assert parsed is not None
        self.assertEqual(parsed.volume, 1_000.0)
        self.assertEqual(parsed.bid_depth_5 + parsed.ask_depth_5, 200.0)

    def test_entry_uses_training_prior_and_dynamic_breakeven_gate(self) -> None:
        rows = snapshots(MAX_LOOKBACK + 8)
        for index in range(MAX_LOOKBACK, len(rows)):
            mid = 100.0 + (index - MAX_LOOKBACK) * 0.5
            rows[index] = replace(rows[index], mid=mid, bid=mid - 0.005, ask=mid + 0.005)
        count = len(rows) - MAX_LOOKBACK
        prepared = FeatureSeries(
            "BTC-USDT-SWAP",
            rows,
            np.asarray([row.ts for row in rows], dtype=np.int64),
            np.zeros((count, len(feature_names()))),
            feature_names(),
            np.full(count, 10.0),
            np.zeros(count),
            np.zeros(count),
            predictions=np.ones(count),
            scores=np.full(count, 0.8),
        )
        candidate = DynamicCandidate(0.2, 1.0, 0.6, 45.0, 0.0, 5)
        start, end = rows[MAX_LOOKBACK].ts, rows[-1].ts
        no_prior = simulate_dynamic_rr(
            prepared, candidate, start, end, max_spread_bps=2.0, record_trades=True
        )
        with_prior = simulate_dynamic_rr(
            prepared,
            candidate,
            start,
            end,
            max_spread_bps=2.0,
            prior_posterior={(1, 1): [20, 0]},
            record_trades=True,
        )
        self.assertGreater(with_prior.trades, 0)
        self.assertGreater(
            with_prior.trade_rows[0].estimated_win_rate_pct,
            no_prior.trade_rows[0].estimated_win_rate_pct,
        )
        self.assertGreater(
            with_prior.trade_rows[0].estimated_win_rate_pct,
            with_prior.trade_rows[0].breakeven_win_rate_pct,
        )

    def test_dynamic_levels_respond_to_confidence_and_win_rate(self) -> None:
        candidate = DynamicCandidate(0.2, 1.5, 0.9, 45.0, 0.0, 60)
        low_target, low_stop = dynamic_levels(2.0, 0.2, 45.0, candidate)
        high_target, high_stop = dynamic_levels(2.0, 0.9, 70.0, candidate)
        self.assertGreater(high_target, low_target)
        self.assertLessEqual(high_stop, low_stop)


if __name__ == "__main__":
    unittest.main()
