from __future__ import annotations

import unittest

import numpy as np

from factor_filter_cycle_research import (
    causal_ewma,
    causal_kalman,
    candidate_variant,
    downsample_snapshots,
    mrmr_select,
    market_session,
    spearman_correlation,
    stability_elasticnet_select,
    stable_ic_select,
    truncate_histories,
)
from orderflow_rr_research import OrderFlowSnapshot, StrategyCandidate, simulate_strategy


def snapshot(index: int) -> OrderFlowSnapshot:
    return OrderFlowSnapshot(index, 99.0, 101.0, 100.0, 2.0, 0.0, 0.0, 0.0)


class FactorFilterCycleResearchTests(unittest.TestCase):
    def test_downsampling_is_fixed_and_backward_only(self) -> None:
        rows = [snapshot(index) for index in range(10)]
        self.assertEqual([item.ts for item in downsample_snapshots(rows, 3)], [0, 3, 6, 9])

    def test_explicit_cutoff_freezes_appending_history(self) -> None:
        rows = [snapshot(index) for index in range(10)]
        frozen = truncate_histories({"BTC": rows}, 5)
        self.assertEqual([item.ts for item in frozen["BTC"]], list(range(6)))

    def test_americas_session_is_new_york_regular_hours_and_dst_aware(self) -> None:
        from datetime import datetime, timezone

        winter = int(datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc).timestamp() * 1_000)
        summer = int(datetime(2026, 7, 6, 14, 0, tzinfo=timezone.utc).timestamp() * 1_000)
        summer_open = int(datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc).timestamp() * 1_000)
        summer_close = int(datetime(2026, 7, 6, 20, 0, tzinfo=timezone.utc).timestamp() * 1_000)
        weekend = int(datetime(2026, 7, 5, 14, 0, tzinfo=timezone.utc).timestamp() * 1_000)
        self.assertEqual(market_session(winter), "americas")
        self.assertEqual(market_session(summer), "americas")
        self.assertEqual(market_session(summer_open), "americas")
        self.assertEqual(market_session(summer_close), "non_americas")
        self.assertEqual(market_session(weekend), "non_americas")
        self.assertEqual(candidate_variant("x", "americas"), "x__americas")

    def test_session_filter_closes_at_boundary_and_blocks_outside_entries(self) -> None:
        rows = [
            OrderFlowSnapshot(index, 99.0, 101.0, 100.0, 2.0, 0.0, 1.0, 0.0)
            for index in range(6)
        ]
        result = simulate_strategy(
            rows,
            StrategyCandidate("trade_flow_momentum", 0.5, 10_000.0, 10_000.0, 90),
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=3.0,
            active_predicate=lambda row: row.ts < 2,
            record_trades=True,
        )
        self.assertEqual(result.trades, 1)
        self.assertEqual(result.trade_rows[0].entry_ts, 0)
        self.assertEqual(result.trade_rows[0].exit_ts, 2)
        self.assertEqual(result.time_exits, 1)

    def test_spearman_detects_monotone_signal(self) -> None:
        values = np.arange(20.0)
        self.assertAlmostEqual(spearman_correlation(values, values**3), 1.0)

    def test_stable_ic_prefers_block_stable_signal(self) -> None:
        target = np.tile(np.arange(50.0), 4)
        stable = target + np.sin(np.arange(200.0)) * 0.01
        flipping = target.copy()
        flipping[50:100] *= -1
        flipping[150:] *= -1
        noise = np.sin(np.arange(200.0) * 1.73)
        values = np.column_stack([stable, flipping, noise])
        blocks = np.repeat(np.arange(4), 50)
        selected, _ = stable_ic_select(values, target, blocks, max_features=1)
        self.assertEqual(selected.tolist(), [0])

    def test_mrmr_avoids_duplicate_when_diverse_signal_exists(self) -> None:
        rng = np.random.default_rng(11)
        first = rng.normal(size=500)
        diverse = rng.normal(size=500)
        target = first + diverse
        duplicate = first * 1.001
        values = np.column_stack([first, duplicate, diverse])
        selected, _ = mrmr_select(values, target, max_features=2)
        self.assertIn(2, selected)
        self.assertFalse(0 in selected and 1 in selected)

    def test_stability_elasticnet_returns_bounded_unique_features(self) -> None:
        rng = np.random.default_rng(7)
        values = rng.normal(size=(400, 8))
        target = values[:, 2] * 3.0 - values[:, 5] * 2.0 + rng.normal(scale=0.1, size=400)
        blocks = np.repeat(np.arange(4), 100)
        selected, diagnostics = stability_elasticnet_select(values, target, blocks, max_features=3)
        self.assertEqual(len(set(selected.tolist())), 3)
        self.assertIn(2, selected)
        self.assertIn(5, selected)
        self.assertEqual(diagnostics["subsamples"], 6)

    def test_causal_filters_do_not_change_prefix_when_future_is_appended(self) -> None:
        prefix = np.asarray([0.0, 1.0, -1.0, 0.5])
        extended = np.concatenate([prefix, [100.0, -100.0]])
        np.testing.assert_allclose(causal_ewma(prefix), causal_ewma(extended)[: len(prefix)])
        np.testing.assert_allclose(causal_kalman(prefix), causal_kalman(extended)[: len(prefix)])


if __name__ == "__main__":
    unittest.main()
