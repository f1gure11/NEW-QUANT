from __future__ import annotations

import unittest

import numpy as np

from expanded_factor_research import (
    ExpandedCandidate,
    feature_names,
    fit_bundle,
    prepare_segment,
    scored_snapshots,
)
from orderflow_rr_research import OrderFlowSnapshot, parse_snapshot


def snapshots(count: int, *, final_jump: float = 0.0) -> list[OrderFlowSnapshot]:
    rows = []
    for index in range(count):
        mid = 100.0 + index * 0.01 + 0.02 * ((index % 7) - 3)
        if index == count - 1:
            mid += final_jump
        rows.append(
            OrderFlowSnapshot(
                ts=1_800_000_000_000 + index * 60_000,
                bid=mid - 0.005,
                ask=mid + 0.005,
                mid=mid,
                spread_bps=1.0,
                book_imbalance=0.2,
                trade_imbalance=0.1,
                ofi=-0.1,
                open_interest=1_000_000.0 + index * 100.0,
                funding_rate=0.0001,
                funding_premium=-0.00005,
            )
        )
    return rows


class ExpandedFactorResearchTests(unittest.TestCase):
    def test_public_snapshot_parser_keeps_market_state(self) -> None:
        parsed = parse_snapshot(
            {
                "capturedTs": 1_800_000_000_000,
                "ticker": {"bidPx": "99.9", "askPx": "100.1", "bidSz": "2", "askSz": "3"},
                "book": {"bids": [["99.9", "2"]], "asks": [["100.1", "3"]]},
                "features": {"book": {"imbalance_5": "0.1", "imbalance_10": "0.2"}, "trades": {"imbalance": "0.3"}},
                "openInterest": {"oi": "12345.6"},
                "funding": {"fundingRate": "0.0001", "premium": "-0.0002"},
            },
            None,
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.open_interest, 12345.6)
        self.assertEqual(parsed.funding_rate, 0.0001)
        self.assertEqual(parsed.funding_premium, -0.0002)

    def test_expanded_feature_set_has_market_state_and_no_orderflow(self) -> None:
        names = feature_names()
        self.assertGreaterEqual(len(names), 35)
        self.assertIn("open_interest_change_120_bps", names)
        self.assertIn("funding_rate_bps", names)
        self.assertNotIn("trade_imbalance", names)
        self.assertNotIn("ofi", names)

    def test_features_do_not_use_future_snapshot(self) -> None:
        original = prepare_segment(snapshots(260), instrument_code=1.0)
        changed = prepare_segment(snapshots(260, final_jump=20.0), instrument_code=1.0)
        position = original.positions[258]
        self.assertTrue(np.allclose(original.features[position], changed.features[position]))

    def test_orderflow_overlay_cannot_become_core(self) -> None:
        with self.assertRaises(ValueError):
            ExpandedCandidate(30, 10.0, 0.20, 0.3, 100.0, 60.0, 90)

    def test_model_weights_are_normalized(self) -> None:
        segment = prepare_segment(snapshots(1_400), instrument_code=1.0)
        bundle = fit_bundle({"BTC": segment}, 30, 10.0)
        self.assertEqual(bundle.forecast_horizon, 30)
        self.assertEqual(set(bundle.feature_names), set(feature_names()))
        self.assertAlmostEqual(
            sum(abs(value) for value in bundle.normalized_coefficients.values()), 1.0
        )

    def test_scored_snapshots_preserve_warmup_and_quotes(self) -> None:
        segment = prepare_segment(snapshots(1_400), instrument_code=1.0)
        bundle = fit_bundle({"BTC": segment}, 30, 10.0)
        scored = scored_snapshots(segment, bundle, 0.10)
        self.assertEqual(scored[10].trade_imbalance, 0.0)
        self.assertEqual(scored[500].bid, segment.snapshots[500].bid)
        self.assertLessEqual(abs(scored[500].trade_imbalance), 1.0)


if __name__ == "__main__":
    unittest.main()
