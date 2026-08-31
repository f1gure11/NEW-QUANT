from __future__ import annotations

import unittest

import numpy as np

from orderflow_ml_probability_research import (
    ActionPrediction,
    BarrierPolicy,
    ProbabilityBundle,
    barrier_outcome,
    predict_bundle,
    prepare_segment,
    simulate_dynamic_strategy,
)
from orderflow_rr_research import OrderFlowSnapshot


def rows(count: int, *, final_jump: float = 0.0) -> list[OrderFlowSnapshot]:
    result = []
    for index in range(count):
        mid = 100.0 + index * 0.01
        if index == count - 1:
            mid += final_jump
        result.append(
            OrderFlowSnapshot(
                ts=1_800_000_000_000 + index * 60_000,
                bid=mid - 0.005,
                ask=mid + 0.005,
                mid=mid,
                spread_bps=1.0,
                book_imbalance=0.1 * ((index % 3) - 1),
                trade_imbalance=0.05 * ((index % 5) - 2),
                ofi=0.08 * ((index % 4) - 1),
            )
        )
    return result


class FixedClassifier:
    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        return np.column_stack((np.full(len(features), 0.4), np.full(len(features), 0.6)))


class OrderFlowMLProbabilityTests(unittest.TestCase):
    def test_features_at_index_do_not_use_future_snapshots(self) -> None:
        original = prepare_segment(rows(16), instrument_code=1.0)
        changed = prepare_segment(rows(16, final_jump=20.0), instrument_code=1.0)
        position = original.positions[10]
        self.assertTrue(np.allclose(original.features[position], changed.features[position]))

    def test_barrier_label_uses_executable_quotes_and_both_fees(self) -> None:
        snapshots = rows(30)
        snapshots[11] = OrderFlowSnapshot(
            snapshots[11].ts,
            100.60,
            100.61,
            100.605,
            1.0,
            0.0,
            0.0,
            0.0,
        )
        outcome = barrier_outcome(
            snapshots,
            10,
            1,
            BarrierPolicy("test", 40.0, 15.0, 10),
            fee_bps_per_side=5.0,
            slippage_bps_per_side=0.0,
        )
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome.exit_reason, "take_profit")
        self.assertGreater(outcome.net_pnl_bps, 38.0)
        self.assertLess(outcome.net_pnl_bps, 41.0)

    def test_barrier_label_exits_at_data_gap(self) -> None:
        snapshots = rows(30)
        gap_row = snapshots[12]
        snapshots[12] = OrderFlowSnapshot(
            snapshots[11].ts + 300_000,
            gap_row.bid,
            gap_row.ask,
            gap_row.mid,
            gap_row.spread_bps,
            gap_row.book_imbalance,
            gap_row.trade_imbalance,
            gap_row.ofi,
        )
        outcome = barrier_outcome(
            snapshots,
            10,
            1,
            BarrierPolicy("test", 100.0, 50.0, 10),
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_gap_ms=180_000,
        )
        self.assertIsNotNone(outcome)
        assert outcome is not None
        self.assertEqual(outcome.exit_reason, "gap")
        self.assertEqual(outcome.exit_index, 12)

    def test_probability_bundle_computes_dynamic_payoff_and_expectancy(self) -> None:
        bundle = ProbabilityBundle(
            "test",
            FixedClassifier(),
            None,
            None,
            None,
            30.0,
            20.0,
        )
        prediction = predict_bundle(bundle, np.zeros((3, 2)))
        self.assertTrue(np.allclose(prediction.probability, 0.6))
        self.assertTrue(np.allclose(prediction.payoff_ratio, 1.5))
        self.assertTrue(np.allclose(prediction.expectancy_bps, 10.0))

    def test_dynamic_expectancy_threshold_can_abstain(self) -> None:
        segment = prepare_segment(rows(18), instrument_code=1.0)
        count = len(segment.indices)
        prediction = ActionPrediction(
            probability=np.full(count, 0.6),
            win_bps=np.full(count, 30.0),
            loss_bps=np.full(count, 20.0),
            payoff_ratio=np.full(count, 1.5),
            expectancy_bps=np.full(count, 4.0),
        )
        predictions = {(1, "tp40_sl15_h20"): prediction}
        abstained = simulate_dynamic_strategy(
            segment,
            predictions,
            min_expectancy_bps=5.0,
            starting_equity=100_000.0,
            allocation_pct=20.0,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=2.0,
            max_gap_ms=180_000,
        )
        traded = simulate_dynamic_strategy(
            segment,
            predictions,
            min_expectancy_bps=3.0,
            starting_equity=100_000.0,
            allocation_pct=20.0,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=2.0,
            max_gap_ms=180_000,
        )
        self.assertEqual(abstained.base.trades, 0)
        self.assertGreater(traded.base.trades, 0)


if __name__ == "__main__":
    unittest.main()
