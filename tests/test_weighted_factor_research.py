from __future__ import annotations

import unittest

from orderflow_rr_research import OrderFlowSnapshot, simulate_strategy
from weighted_factor_research import (
    FactorWeights,
    WEIGHT_PROFILES,
    WeightedCandidate,
    factor_components,
    renormalize_price_weights,
    weighted_snapshots,
)


def snapshots(count: int, *, last_jump: float = 0.0) -> list[OrderFlowSnapshot]:
    rows = []
    for index in range(count):
        mid = 100.0 + index * 0.02
        if index == count - 1:
            mid += last_jump
        rows.append(
            OrderFlowSnapshot(
                ts=1_800_000_000_000 + index * 60_000,
                bid=mid - 0.005,
                ask=mid + 0.005,
                mid=mid,
                spread_bps=1.0,
                book_imbalance=0.6,
                trade_imbalance=-0.2,
                ofi=0.1,
            )
        )
    return rows


class WeightedFactorResearchTests(unittest.TestCase):
    def test_all_profiles_keep_orderflow_below_fifteen_percent(self) -> None:
        for weights in WEIGHT_PROFILES.values():
            self.assertGreaterEqual(weights.price_weight, 0.85)
            self.assertLessEqual(weights.orderflow, 0.15)

    def test_invalid_orderflow_core_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            FactorWeights(0.2, 0.2, 0.2, 0.4)

    def test_factor_at_index_does_not_use_future_price(self) -> None:
        original = factor_components(snapshots(20), 3, 10)
        changed = factor_components(snapshots(20, last_jump=20.0), 3, 10)
        self.assertEqual(original[18], changed[18])

    def test_price_only_ablation_renormalizes_to_one(self) -> None:
        result = renormalize_price_weights(FactorWeights(0.5, 0.0, 0.4, 0.1))
        self.assertAlmostEqual(result.price_weight, 1.0)
        self.assertEqual(result.orderflow, 0.0)

    def test_weighted_signal_uses_existing_executable_simulator(self) -> None:
        candidate = WeightedCandidate(
            "price_trend",
            WEIGHT_PROFILES["price_trend"],
            3,
            10,
            0.1,
            10.0,
            100.0,
            5,
        )
        scored = weighted_snapshots(snapshots(30), candidate)
        result = simulate_strategy(
            scored,
            candidate.execution_candidate(),
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=2.0,
        )
        self.assertGreater(result.trades, 0)


if __name__ == "__main__":
    unittest.main()
