from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import us_equity_mean_reversion_research as mr


class RegistryTests(unittest.TestCase):
    def test_registry_is_frozen_and_trading_disabled(self) -> None:
        registry = mr.read_json(mr.DEFAULT_REGISTRY_PATH)

        mr.validate_registry(registry)

        self.assertFalse(registry["study"]["paperOrLiveAuthorized"])
        self.assertEqual(registry["study"]["portfolio"]["grossLeverageScenarios"], list(range(2, 11)))
        self.assertEqual(registry["study"]["portfolio"]["fractionalShareIncrement"], 0.01)

    def test_registry_rejects_parameter_tampering(self) -> None:
        registry = mr.read_json(mr.DEFAULT_REGISTRY_PATH)
        changed = copy.deepcopy(registry)
        changed["study"]["portfolios"][0]["formationSessions"] = 4

        with self.assertRaisesRegex(ValueError, "modelId"):
            mr.validate_registry(changed)


class SignalTests(unittest.TestCase):
    def test_cross_sectional_reversal_longs_losers_and_shorts_winners(self) -> None:
        prices = np.ones((7, 10), dtype=float) * 100.0
        prices[5] = np.arange(95.0, 105.0)
        config = {"formationSessions": 5, "rebalanceEverySessions": 5, "tailNamesPerSide": 2}

        targets = mr.cross_sectional_targets(prices, np.asarray([5, 6]), config)

        np.testing.assert_allclose(targets[5][:2], [0.25, 0.25])
        np.testing.assert_allclose(targets[5][-2:], [-0.25, -0.25])
        self.assertAlmostEqual(float(np.abs(targets[5]).sum()), 1.0)

    def test_distance_pair_selection_is_disjoint(self) -> None:
        base = np.linspace(1.0, 1.1, 252)
        prices = np.column_stack(
            [base, base * 1.001, base[::-1], base[::-1] * 1.001, np.linspace(1.0, 1.3, 252), np.linspace(1.3, 1.0, 252)]
        )

        pairs = mr.select_distance_pairs(prices, 3)

        members = [member for left, right, *_ in pairs for member in (left, right)]
        self.assertEqual(len(members), len(set(members)))

    def test_fractional_sizing_floors_without_exceeding_target(self) -> None:
        quantities = mr.floor_target_quantities(
            np.asarray([0.5, -0.5]),
            np.asarray([333.0, 80.0]),
            equity=1000.0,
            leverage=2,
            increment=0.01,
        )

        np.testing.assert_allclose(quantities, [3.0, -12.5])
        self.assertLessEqual(float(np.dot(np.abs(quantities), [333.0, 80.0])), 2000.0)


class SimulationTests(unittest.TestCase):
    def test_signal_executes_at_next_close_and_costs_round_trip(self) -> None:
        prices = np.asarray([[100.0, 100.0], [100.0, 100.0], [110.0, 90.0]])
        dates = pd.date_range("2020-01-01", periods=3, freq="B")
        result = mr.simulate(
            strategy="test",
            split="train",
            prices=prices,
            dates=dates,
            locations=np.asarray([0, 1, 2]),
            targets={0: np.asarray([0.5, -0.5])},
            leverage=2,
            cost_profile={"key": "base", "transactionPerSideBps": 10.0, "annualLongFinancingPct": 0.0, "annualShortBorrowPct": 0.0},
            portfolio={
                "initialEquityUsd": 1000.0,
                "fractionalShareIncrement": 0.01,
                "marginProxy": {"maintenanceMarginPctOfGross": 5.0, "liquidationPenaltyBpsOfGross": 50.0},
            },
        )

        self.assertGreater(result.price_pnl_usd, 199.0)
        self.assertAlmostEqual(result.transaction_cost_usd, 4.0, places=6)
        self.assertEqual(result.trade_orders, 4)
        self.assertFalse(result.liquidated)

    def test_high_leverage_loss_triggers_margin_proxy(self) -> None:
        prices = np.asarray([[100.0, 100.0], [100.0, 100.0], [94.0, 106.0]])
        dates = pd.date_range("2020-01-01", periods=3, freq="B")
        result = mr.simulate(
            strategy="test",
            split="train",
            prices=prices,
            dates=dates,
            locations=np.asarray([0, 1, 2]),
            targets={0: np.asarray([0.5, -0.5])},
            leverage=10,
            cost_profile={"key": "gross", "transactionPerSideBps": 0.0, "annualLongFinancingPct": 0.0, "annualShortBorrowPct": 0.0},
            portfolio={
                "initialEquityUsd": 1000.0,
                "fractionalShareIncrement": 0.01,
                "marginProxy": {"maintenanceMarginPctOfGross": 5.0, "liquidationPenaltyBpsOfGross": 50.0},
            },
        )

        self.assertTrue(result.liquidated)
        self.assertGreater(result.liquidation_penalty_usd, 0.0)

    def test_report_has_all_frozen_scenario_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = mr.run(mr.DEFAULT_REGISTRY_PATH, Path(tmpdir))

            self.assertEqual(len(payload["results"]), 243)
            keys = {
                (row["strategy"], row["split"], row["leverage"], row["cost_profile"])
                for row in payload["results"]
            }
            self.assertEqual(len(keys), 243)
            for row in payload["results"]:
                reconstructed = (
                    row["initial_equity"]
                    + row["price_pnl_usd"]
                    - row["transaction_cost_usd"]
                    - row["financing_cost_usd"]
                    - row["short_borrow_cost_usd"]
                    - row["liquidation_penalty_usd"]
                )
                self.assertAlmostEqual(row["terminal_equity"], reconstructed, places=7)
            self.assertTrue((Path(tmpdir) / "summary.json").is_file())
            self.assertTrue((Path(tmpdir) / "scenario_rows.csv").is_file())
            self.assertTrue((Path(tmpdir) / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
