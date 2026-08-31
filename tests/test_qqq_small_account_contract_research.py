from __future__ import annotations

import unittest
from datetime import date

import numpy as np

from qqq_small_account_contract_research import (
    ContractRule,
    RiskSnapshot,
    all_minimum_active_book,
    backtest_book,
    contract_rules_from_payloads,
    core_contract_size,
    funding_cash_pnl,
    optimize_active_book,
    position_options,
)
from qqq_intraday_flat_research import FundingPoint
from qqq_intraday_flat_research import SessionExecution


def rule(symbol: str, *, lot: float = 0.01, minimum: float = 0.01) -> ContractRule:
    return ContractRule(
        symbol=symbol,
        contract=f"{symbol}-USDT-SWAP",
        ct_val=1.0,
        lot_sz=lot,
        min_sz=minimum,
        last=100.0,
        max_leverage=20.0,
        captured_at="2026-08-08T00:00:00Z",
    )


class QqqSmallAccountContractResearchTests(unittest.TestCase):
    def test_public_rule_converts_contract_lot_to_notional(self) -> None:
        instruments = {
            "data": [
                {
                    "instId": "AAA-USDT-SWAP",
                    "state": "live",
                    "ctVal": "1",
                    "lotSz": "0.01",
                    "minSz": "0.01",
                    "lever": "20",
                }
            ]
        }
        tickers = {"data": [{"instId": "AAA-USDT-SWAP", "last": "250", "ts": "1"}]}
        parsed = contract_rules_from_payloads(instruments, tickers, ["AAA"])["AAA"]
        self.assertAlmostEqual(parsed.min_notional(250.0), 2.5)

    def test_one_minimum_lot_exception_does_not_allow_two_large_lots(self) -> None:
        large = rule("AAA")
        self.assertEqual(position_options(large, 500.0, 100.0), [0, 1])

    def test_optimizer_uses_real_lots_and_keeps_neutral_pair(self) -> None:
        symbols = ("AAA", "BBB")
        rules = {symbol: rule(symbol) for symbol in symbols}
        risk = RiskSnapshot(
            symbols=symbols,
            beta={"AAA": 1.0, "BBB": 1.0},
            covariance=np.diag([0.04, 0.04]),
        )
        book = optimize_active_book(
            {"AAA": 0.01, "BBB": -0.01},
            {"AAA": 100.0, "BBB": 100.0},
            100.0,
            rules,
            risk,
            {"AAA": "tech", "BBB": "tech"},
        )
        self.assertTrue(book.feasible)
        self.assertEqual(book.contracts, {"AAA": 0.01, "BBB": -0.01})
        self.assertAlmostEqual(book.active_gross, 2.0)
        self.assertAlmostEqual(book.active_net, 0.0)
        self.assertAlmostEqual(book.beta_residual, 0.0)

    def test_core_size_fills_cap_without_exceeding_it(self) -> None:
        qqq = rule("QQQ")
        size = core_contract_size(qqq, 700.0, 100.0, 6.0, 1.2)
        self.assertEqual(size, 0.16)
        self.assertLessEqual(size * 700.0 + 6.0, 120.0)

    def test_all_minimum_book_keeps_every_nonzero_direction(self) -> None:
        symbols = ("AAA", "BBB", "CCC")
        rules = {
            "AAA": rule("AAA"),
            "BBB": rule("BBB", lot=0.1, minimum=0.1),
            "CCC": rule("CCC"),
        }
        risk = RiskSnapshot(
            symbols=symbols,
            beta={symbol: 1.0 for symbol in symbols},
            covariance=np.diag([0.04, 0.04, 0.04]),
        )
        book = all_minimum_active_book(
            {"AAA": 0.01, "BBB": -0.01, "CCC": 0.0},
            {symbol: 100.0 for symbol in symbols},
            100.0,
            rules,
            risk,
            {symbol: "tech" for symbol in symbols},
        )
        self.assertEqual(book.contracts, {"AAA": 0.01, "BBB": -0.1, "CCC": 0.0})
        self.assertEqual(book.selected_positions, 2)

    def test_positive_funding_is_paid_by_long_contract(self) -> None:
        points = [FundingPoint(100, 0.001)]
        self.assertAlmostEqual(funding_cash_pnl(points, 0, 200, 0.01, 1.0, 500.0), -0.005)
        self.assertAlmostEqual(funding_cash_pnl(points, 0, 200, -0.01, 1.0, 500.0), 0.005)

    def test_daily_guard_reduces_core_after_drawdown(self) -> None:
        sessions = {
            "QQQ": {
                "2026-06-01": SessionExecution("2026-06-01", 100, 200, 100.0, 80.0),
                "2026-06-02": SessionExecution("2026-06-02", 300, 400, 80.0, 80.0),
            },
            "AAA": {
                "2026-06-01": SessionExecution("2026-06-01", 100, 200, 100.0, 100.0),
                "2026-06-02": SessionExecution("2026-06-02", 300, 400, 100.0, 100.0),
            },
        }
        frame, _, _ = backtest_book(
            ["2026-06-01", "2026-06-02"],
            ["AAA"],
            sessions,
            {"QQQ": [], "AAA": []},
            {date(2026, 5, 31): {"AAA": 0.01}},
            {},
            {"AAA": "tech"},
            {"QQQ": rule("QQQ"), "AAA": rule("AAA")},
            initial_equity=100.0,
            gross_cap=1.2,
            cost_bps_per_side=0.0,
            active_mode="none",
        )
        self.assertLessEqual(float(frame.iloc[-1]["grossExposure"]), 1.2 + 1e-12)


if __name__ == "__main__":
    unittest.main()
