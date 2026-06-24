from __future__ import annotations

import unittest
from decimal import Decimal

from backtest.okx_grid_backtest import (
    Candle,
    GridBacktestConfig,
    Position,
    SimOrder,
    execute_orders,
    reconcile_sim_orders,
    resolve_output_dir,
    run_grid_backtest,
)


def synthetic_candles(count: int = 80) -> list[Candle]:
    candles = []
    base = Decimal("100")
    for index in range(count):
        drift = Decimal(index % 12 - 6) / Decimal("100")
        close = base + drift
        candles.append(
            Candle(
                ts=1_800_000_000_000 + index * 60_000,
                open=close,
                high=close + Decimal("0.25"),
                low=close - Decimal("0.25"),
                close=close,
                volume=Decimal("1000"),
            )
        )
    return candles


class GridBacktestTest(unittest.TestCase):
    def test_backtest_accounting_smoke(self) -> None:
        config = GridBacktestConfig(
            inst_id="TEST-USDT-SWAP",
            lower=Decimal("98"),
            upper=Decimal("102"),
            starting_equity=Decimal("100"),
            order_sz=Decimal("1"),
            max_position=Decimal("2"),
            ct_val=Decimal("1"),
            tick_sz=Decimal("0.01"),
            lot_sz=Decimal("1"),
            min_sz=Decimal("1"),
            regime_filter="off",
            total_loss_sl_cap=Decimal("10"),
        )
        result, fills, equity_curve = run_grid_backtest(synthetic_candles(), config)

        self.assertEqual(result.bars, 80)
        self.assertGreater(result.final_equity, Decimal("0"))
        self.assertEqual(result.fills, len(fills))
        self.assertEqual(len(equity_curve), 80)

    def test_filled_order_is_not_reconciled_back_into_book(self) -> None:
        config = GridBacktestConfig(max_actions_per_bar=4)
        candle = Candle(
            ts=1_800_000_000_000,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        )
        order = SimOrder("buy", "long", Decimal("99.5"), Decimal("1"), False, "open_long")

        _, _, actions = execute_orders(
            candle,
            [order],
            Position(),
            Position(),
            config,
            Decimal("100"),
        )
        filled_order_ids = {id(action[0]) for action in actions}
        live_orders = [item for item in [order] if id(item) not in filled_order_ids]

        self.assertTrue(actions)
        self.assertEqual(reconcile_sim_orders(live_orders, [], config.max_actions_per_bar), [])

    def test_relative_output_dir_is_under_reports_backtests(self) -> None:
        output_dir = resolve_output_dir("smoke-run", "20260624T000000Z")

        self.assertTrue(str(output_dir).endswith("reports/backtests/smoke-run"))


if __name__ == "__main__":
    unittest.main()
