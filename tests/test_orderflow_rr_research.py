from __future__ import annotations

import unittest

from orderflow_rr_research import (
    OrderFlowSnapshot,
    OrderFlowTrade,
    StrategyCandidate,
    factor_score,
    normalized_ofi,
    signed_consensus,
    simulate_strategy,
    summarize_trades,
)


def snapshot(
    index: int,
    *,
    bid: float = 99.99,
    ask: float = 100.0,
    book: float = 0.0,
    trade: float = 0.0,
    ofi: float = 0.0,
) -> OrderFlowSnapshot:
    mid = (bid + ask) / 2.0
    return OrderFlowSnapshot(
        ts=1_800_000_000_000 + index * 60_000,
        bid=bid,
        ask=ask,
        mid=mid,
        spread_bps=(ask - bid) / mid * 10_000.0,
        book_imbalance=book,
        trade_imbalance=trade,
        ofi=ofi,
    )


class OrderFlowRewardRiskTests(unittest.TestCase):
    def test_normalized_ofi_uses_price_and_queue_changes(self) -> None:
        value = normalized_ofi(
            (100.0, 10.0, 101.0, 10.0),
            (100.0, 15.0, 101.0, 5.0),
        )
        self.assertAlmostEqual(value, 0.5)
        self.assertGreater(
            normalized_ofi(
                (100.0, 10.0, 101.0, 10.0),
                (100.5, 12.0, 101.0, 10.0),
            ),
            0.0,
        )

    def test_consensus_and_absorption_factors_require_current_agreement(self) -> None:
        agreeing = snapshot(0, book=0.7, trade=0.4, ofi=-0.2)
        opposing = snapshot(0, book=0.7, trade=-0.4, ofi=0.2)
        self.assertAlmostEqual(signed_consensus(0.7, 0.4), 0.4)
        self.assertEqual(factor_score(agreeing, "book_trade_consensus"), 0.4)
        self.assertEqual(factor_score(opposing, "book_trade_consensus"), 0.0)
        self.assertEqual(factor_score(opposing, "absorption_reversal"), 0.4)

    def test_executable_quote_take_profit_includes_two_sided_fees(self) -> None:
        rows = [
            snapshot(0, trade=0.8),
            snapshot(1, bid=100.60, ask=100.61),
        ]
        result = simulate_strategy(
            rows,
            StrategyCandidate("trade_flow_momentum", 0.2, 40.0, 15.0, 10),
            fee_bps_per_side=5.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=2.0,
            record_trades=True,
        )
        self.assertEqual(result.trades, 1)
        self.assertEqual(result.tp_exits, 1)
        self.assertEqual(result.wins, 1)
        self.assertGreater(result.trade_rows[0].net_pnl_bps, 49.0)
        self.assertLess(result.trade_rows[0].net_pnl_bps, 51.0)

    def test_latency_uses_prior_snapshot_signal_and_later_entry_quote(self) -> None:
        rows = [
            snapshot(0, trade=0.8),
            snapshot(1, bid=100.99, ask=101.0),
            snapshot(2, bid=101.60, ask=101.61),
        ]
        candidate = StrategyCandidate("trade_flow_momentum", 0.2, 40.0, 15.0, 10)
        immediate = simulate_strategy(
            rows,
            candidate,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=2.0,
            record_trades=True,
        )
        delayed = simulate_strategy(
            rows,
            candidate,
            fee_bps_per_side=0.0,
            slippage_bps_per_side=0.0,
            max_spread_bps=2.0,
            latency_bars=1,
            record_trades=True,
        )
        self.assertEqual(immediate.trade_rows[0].entry_ts, rows[0].ts)
        self.assertEqual(delayed.trade_rows[0].entry_ts, rows[1].ts)
        self.assertGreater(delayed.trade_rows[0].entry_price, immediate.trade_rows[0].entry_price)

    def test_realized_payoff_and_breakeven_win_rate_are_reported(self) -> None:
        trades = [
            OrderFlowTrade(1, 2, 1, 1.0, 100.0, 101.0, "take_profit", 1, 50.0, -5.0, 60.0),
            OrderFlowTrade(3, 4, -1, -1.0, 100.0, 101.0, "stop_loss", 1, -25.0, -30.0, 5.0),
        ]
        result = summarize_trades(
            trades,
            100_000.0,
            100_050.0,
            0.1,
            record_trades=True,
        )
        self.assertAlmostEqual(result.win_rate_pct, 50.0)
        self.assertAlmostEqual(result.payoff_ratio, 2.0)
        self.assertAlmostEqual(result.breakeven_win_rate_pct, 100.0 / 3.0)
        self.assertAlmostEqual(result.expectancy_bps, 12.5)
        self.assertAlmostEqual(result.profit_factor, 2.0)


if __name__ == "__main__":
    unittest.main()
