from __future__ import annotations

import copy
import unittest

import numpy as np

import qqq_pure_stock_monte_carlo as mc


def synthetic_panel(ratios: list[list[float]], weights: list[float]) -> mc.EpisodePanel:
    values = np.asarray(ratios, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    symbols = tuple(f"S{index}" for index in range(values.shape[1]))
    cube = values[None, :, :]
    return mc.EpisodePanel(
        symbols=symbols,
        signal_dates=("2024-01-31",),
        ratios=cube,
        valid=np.ones(cube.shape[:2], dtype=bool),
        weights=np.asarray([weights], dtype=float),
        raw_gross=np.asarray([sum(abs(value) for value in weights)], dtype=float),
        initial_prices=np.full(values.shape[1], 100.0),
        source_dates=(tuple(f"2024-02-{day + 1:02d}" for day in range(len(values))),),
        fingerprint="synthetic",
    )


def run_synthetic(
    panel: mc.EpisodePanel,
    variant: dict,
    *,
    leverage: float = 1.0,
    cost_bps: float = 0.0,
    funding: np.ndarray | None = None,
) -> mc.PathResults:
    days = panel.ratios.shape[1]
    draws = mc.BootstrapDraws(
        episodes=np.zeros((1, 1), dtype=np.int16),
        funding=np.zeros((1, 1, days), dtype=np.int16),
    )
    rates = (
        funding
        if funding is not None
        else np.zeros((1, len(panel.symbols)), dtype=float)
    )
    return mc.simulate_paths(
        panel,
        rates,
        draws,
        initial_equity=100.0,
        leverage=leverage,
        quantity_increment=0.01,
        per_side_bps=cost_bps,
        funding_multiplier=1.0,
        maintenance_margin_fraction=0.05,
        liquidation_penalty_bps=0.0,
        hard_stop_fraction=0.15,
        exit_variant=variant,
    )


FIXED = {
    "key": "fixed_take_profit_10pct",
    "type": "fixed_take_profit",
    "takeProfitPct": 10.0,
}
TRAILING = {
    "key": "trailing_profit_6pct_4pct",
    "type": "trailing_take_profit",
    "activationPct": 6.0,
    "givebackPercentagePoints": 4.0,
}


class RegistryAndDataTests(unittest.TestCase):
    def test_registry_is_frozen_development_only(self) -> None:
        registry = mc.read_json(mc.DEFAULT_REGISTRY_PATH)
        mc.validate_registry(registry)
        self.assertFalse(registry["study"]["paperOrLiveAuthorized"])
        self.assertEqual(
            registry["protocol"]["classification"],
            "development_only_risk_stress_on_inspected_history",
        )
        self.assertEqual(
            registry["study"]["portfolio"]["leverageScenarios"],
            [2.0, 3.0, 5.0, 10.0],
        )

    def test_registry_hash_rejects_parameter_tampering(self) -> None:
        registry = mc.read_json(mc.DEFAULT_REGISTRY_PATH)
        changed = copy.deepcopy(registry)
        changed["study"]["exits"]["hardStopLossPct"] = 14.0
        with self.assertRaisesRegex(ValueError, "registryId"):
            mc.validate_registry(changed)

    def test_episode_panel_excludes_dash_and_normalizes_factor_gross(self) -> None:
        registry = mc.read_json(mc.DEFAULT_REGISTRY_PATH)
        panel = mc.build_episode_panel(registry)
        self.assertEqual(len(panel.symbols), 29)
        self.assertNotIn("DASH", panel.symbols)
        self.assertEqual(len(panel.signal_dates), 24)
        np.testing.assert_allclose(np.abs(panel.weights).sum(axis=1), 1.0)
        self.assertGreaterEqual(panel.valid.sum(axis=1).min(), 19)


class SizingAndExitTests(unittest.TestCase):
    def test_quantity_floor_preserves_cap_and_direction(self) -> None:
        quantities = mc.floor_quantities(
            np.asarray([[0.6, -0.4]]),
            np.asarray([100.0]),
            np.asarray([[333.0, 50.0]]),
            leverage=2.0,
            increment=0.01,
        )
        np.testing.assert_allclose(quantities, [[0.36, -1.60]])
        gross = float((np.abs(quantities) * [[333.0, 50.0]]).sum())
        self.assertLessEqual(gross, 200.0)

    def test_fixed_profit_triggers_at_close_and_exits_next_close(self) -> None:
        result = run_synthetic(synthetic_panel([[1.11], [1.0]], [1.0]), FIXED)
        self.assertAlmostEqual(result.terminal_equity[0], 111.0)
        self.assertEqual(result.fixed_profit_exits[0], 1)
        self.assertEqual(result.stop_exits[0], 0)

    def test_trailing_profit_uses_peak_then_exits_next_close(self) -> None:
        result = run_synthetic(
            synthetic_panel([[1.07], [102.0 / 107.0], [1.0]], [1.0]),
            TRAILING,
        )
        self.assertAlmostEqual(result.terminal_equity[0], 102.0)
        self.assertEqual(result.trailing_profit_exits[0], 1)

    def test_hard_stop_exits_on_next_close(self) -> None:
        result = run_synthetic(synthetic_panel([[0.84], [1.0]], [1.0]), FIXED)
        self.assertAlmostEqual(result.terminal_equity[0], 84.0)
        self.assertEqual(result.stop_exits[0], 1)
        self.assertEqual(result.fixed_profit_exits[0], 0)

    def test_high_leverage_close_breach_triggers_liquidation_proxy(self) -> None:
        result = run_synthetic(
            synthetic_panel([[0.94]], [1.0]),
            FIXED,
            leverage=10.0,
        )
        self.assertTrue(result.liquidated[0])
        self.assertFalse(result.ruined[0])
        self.assertAlmostEqual(result.terminal_equity[0], 40.0)

    def test_positive_funding_costs_a_long_contract(self) -> None:
        result = run_synthetic(
            synthetic_panel([[1.0]], [1.0]),
            FIXED,
            funding=np.asarray([[0.001]]),
        )
        self.assertAlmostEqual(result.funding_pnl_usdt[0], -0.1)
        self.assertAlmostEqual(result.terminal_equity[0], 99.9)

    def test_path_accounting_reconciles(self) -> None:
        result = run_synthetic(
            synthetic_panel([[1.05], [1.0]], [1.0]),
            FIXED,
            cost_bps=10.0,
            funding=np.asarray([[0.0001]]),
        )
        reconstructed = (
            100.0
            + result.price_pnl_usdt[0]
            + result.funding_pnl_usdt[0]
            - result.transaction_cost_usdt[0]
            - result.liquidation_penalty_usdt[0]
        )
        self.assertAlmostEqual(result.terminal_equity[0], reconstructed, places=10)


if __name__ == "__main__":
    unittest.main()
