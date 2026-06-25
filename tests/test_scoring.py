from __future__ import annotations

import unittest
from dataclasses import dataclass
from decimal import Decimal

from scoring import ScoreWeights, score_backtest


@dataclass(slots=True)
class Result:
    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    profit_factor: Decimal
    fills: int
    risk_events: int


class ScoringTest(unittest.TestCase):
    def test_score_rewards_return_profit_factor_and_fills(self) -> None:
        score = score_backtest(
            Result(
                total_return_pct=Decimal("2"),
                max_drawdown_pct=Decimal("0.5"),
                profit_factor=Decimal("1.8"),
                fills=10,
                risk_events=0,
            ),
            ScoreWeights(),
        )

        self.assertGreater(score.score, Decimal("0"))
        self.assertEqual(score.return_component, Decimal("8"))
        self.assertEqual(score.drawdown_component, Decimal("1.5"))
        self.assertEqual(score.fill_component, Decimal("2.5"))

    def test_score_penalizes_risk_events_and_no_trades(self) -> None:
        score = score_backtest(
            Result(
                total_return_pct=Decimal("0"),
                max_drawdown_pct=Decimal("1"),
                profit_factor=Decimal("0"),
                fills=0,
                risk_events=2,
            ),
            ScoreWeights(),
        )

        self.assertEqual(score.risk_penalty, Decimal("14"))
        self.assertEqual(score.no_trade_penalty, Decimal("20"))
        self.assertLess(score.score, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
