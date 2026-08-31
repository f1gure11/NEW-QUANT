from __future__ import annotations

import unittest

from option_staged_hedge_research import contract_multiplier, execute_hedge_change, resolve_output_dir, staged_rows, summarize_rows


def bbo(inst_id: str, ts: int, bid: float, ask: float) -> dict:
    return {
        "capturedTs": ts,
        "instId": inst_id,
        "channel": "bbo-tbt",
        "data": {"bids": [[str(bid), "10"]], "asks": [[str(ask), "10"]]},
    }


class StagedHedgeResearchTests(unittest.TestCase):
    def test_contract_multiplier_uses_value_and_multiplier(self) -> None:
        self.assertEqual(contract_multiplier({"ctVal": 2, "ctMult": 0.01}), 0.02)

    def test_relative_output_stays_under_research_reports(self) -> None:
        self.assertTrue(str(resolve_output_dir("sample")).endswith("reports/delta_neutral_options/sample"))

    def test_hedge_change_uses_opposite_side_and_fee(self) -> None:
        quote = {"bid": 100.0, "ask": 101.0}
        cash, fee = execute_hedge_change(2.0, quote, fee_bps=10.0)
        self.assertEqual(cash, -202.0)
        self.assertAlmostEqual(fee, 0.201)
        cash, fee = execute_hedge_change(-2.0, quote, fee_bps=10.0)
        self.assertEqual(cash, 200.0)
        self.assertAlmostEqual(fee, 0.201)

    def test_staged_first_leg_is_hedged_and_closed(self) -> None:
        structure = {
            "name": "BTC_atm",
            "base": "BTC",
            "kind": "atm",
            "spot": 100.0,
            "expiryMs": 100_000,
            "call": {"instId": "CALL", "optionType": "C", "strike": 100.0, "initialBid": 9.0, "initialAsk": 11.0, "ctMult": 0.01},
            "put": {"instId": "PUT", "optionType": "P", "strike": 100.0, "initialBid": 9.0, "initialAsk": 11.0, "ctMult": 0.01},
        }
        cohort = {
            "structure": "BTC_atm",
            "base": "BTC",
            "kind": "atm",
            "policy": "midpoint",
            "createdTs": 1_000,
            "expiresTs": 5_000,
            "legs": {
                "call": {"limitPx": 10.0, "askTouchTs": 2_000},
                "put": {"limitPx": 10.0, "askTouchTs": None},
            },
        }
        events = [
            bbo("BTC-USDT-SWAP", 1_000, 100.0, 101.0),
            bbo("CALL", 2_000, 9.0, 10.0),
            bbo("BTC-USDT-SWAP", 2_000, 100.0, 101.0),
            bbo("CALL", 5_000, 9.0, 10.0),
            bbo("BTC-USDT-SWAP", 5_000, 100.0, 101.0),
        ]
        rows = staged_rows(
            [cohort],
            events,
            [structure],
            {"CALL": {"delta": 0.5}, "PUT": {"delta": -0.5}},
            option_fee_bps=3.0,
            hedge_fee_bps=5.0,
            hedge_quote_age_seconds=3.0,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filled_legs"], 1)
        self.assertEqual(rows[0]["first_leg"], "call")
        self.assertFalse(rows[0]["hedge_missing"])
        self.assertIsNotNone(rows[0]["total_pnl_usd"])
        self.assertLess(rows[0]["hedge_cash_usd"], 0.0)
        self.assertGreater(rows[0]["hedge_fees_usd"], 0.0)

    def test_summary_excludes_unfilled_zero_pnl_from_filled_median(self) -> None:
        rows = [
            {"structure": "BTC_atm", "policy": "midpoint", "filled_legs": 0, "both_filled": False, "hedge_missing": False, "first_fill_wait_seconds": None, "total_pnl_usd": 0.0, "option_fees_usd": 0.0, "hedge_fees_usd": 0.0},
            {"structure": "BTC_atm", "policy": "midpoint", "filled_legs": 1, "both_filled": False, "hedge_missing": False, "first_fill_wait_seconds": 10.0, "total_pnl_usd": -2.0, "option_fees_usd": 0.1, "hedge_fees_usd": 0.2},
        ]
        summary = summarize_rows(rows)[0]
        self.assertEqual(summary["firstLegCohorts"], 1)
        self.assertEqual(summary["medianTotalPnlUsd"], -2.0)


if __name__ == "__main__":
    unittest.main()
