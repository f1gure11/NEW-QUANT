from __future__ import annotations

import unittest

from gex_estimator import calculate_gex, market_base_and_quote, spot_turnover_usd, swap_turnover_usd


class GexEstimatorTest(unittest.TestCase):
    def test_okx_contract_multiplier_is_applied_to_open_interest(self) -> None:
        now_ms = 1_700_000_000_000
        instruments = [
            {
                "instId": "BTC-USD-TEST-100-C",
                "state": "live",
                "expTime": str(now_ms + 86_400_000),
                "stk": "100",
                "optType": "C",
                "ctMult": "0.1",
            },
            {
                "instId": "BTC-USD-TEST-100-P",
                "state": "live",
                "expTime": str(now_ms + 86_400_000),
                "stk": "100",
                "optType": "P",
                "ctMult": "0.1",
            },
        ]
        result = calculate_gex(
            underlying="BTC",
            option_family="BTC-USD",
            spot_price=100,
            instruments=instruments,
            open_interest=[
                {"instId": "BTC-USD-TEST-100-C", "oi": "10", "oiCcy": "1"},
                {"instId": "BTC-USD-TEST-100-P", "oi": "10", "oiCcy": "1"},
            ],
            summaries=[
                {"instId": "BTC-USD-TEST-100-C", "gammaBS": "0.2"},
                {"instId": "BTC-USD-TEST-100-P", "gammaBS": "0.1"},
            ],
            now_ms=now_ms,
        )

        # call: .2 × 1 coin × 100² × 1%; put: -.1 × 1 coin × 100² × 1%.
        self.assertEqual(result["netGex"], 10.0)
        self.assertEqual(result["callOiUnderlying"], 1.0)
        self.assertEqual(result["putOiUnderlying"], 1.0)
        self.assertEqual(result["regime"], "positive_gamma")

    def test_market_turnover_helpers_use_quote_notional(self) -> None:
        self.assertEqual(spot_turnover_usd({"last": "100", "vol24h": "12"}), 1200.0)
        self.assertAlmostEqual(
            swap_turnover_usd(
                {"last": "100", "vol24h": "12"},
                {"ctType": "linear", "ctVal": "0.1"},
            ),
            120.0,
        )
        self.assertAlmostEqual(
            swap_turnover_usd(
                {"last": "100", "vol24h": "12"},
                {"ctType": "inverse", "ctVal": "10"},
            ),
            120.0,
        )

    def test_market_id_parsing_and_profile_are_stable(self) -> None:
        self.assertEqual(market_base_and_quote("ETH-USDT", "SPOT"), ("ETH", "USDT"))
        self.assertEqual(market_base_and_quote("ETH-USDT-SWAP", "SWAP"), ("ETH", "USDT"))
        self.assertEqual(market_base_and_quote("USDT-TRY", "SPOT"), ("USDT", "TRY"))


if __name__ == "__main__":
    unittest.main()
