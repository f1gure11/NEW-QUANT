from __future__ import annotations

import unittest
from decimal import Decimal

from market_selector import MarketSelectorConfig, candidate_from_payload, select_candidates_from_payloads


def instrument(inst_id: str, **overrides):
    payload = {
        "instId": inst_id,
        "instType": "SWAP",
        "instFamily": inst_id.removesuffix("-SWAP"),
        "baseCcy": inst_id.split("-")[0],
        "quoteCcy": "USDT",
        "settleCcy": "USDT",
        "ctVal": "1",
        "tickSz": "0.01",
        "lotSz": "1",
        "minSz": "1",
        "state": "live",
    }
    payload.update(overrides)
    return payload


def ticker(inst_id: str, **overrides):
    payload = {
        "instId": inst_id,
        "last": "100",
        "bidPx": "99.95",
        "askPx": "100.05",
        "volCcyQuote24h": "10000000",
        "vol24h": "100000",
    }
    payload.update(overrides)
    return payload


class MarketSelectorTest(unittest.TestCase):
    def test_selects_live_usdt_swaps_sorted_by_quote_volume(self) -> None:
        instruments = [
            instrument("AAA-USDT-SWAP"),
            instrument("BBB-USDT-SWAP"),
            instrument("CCC-USDC-SWAP", quoteCcy="USDC", settleCcy="USDC"),
            instrument("DDD-USDT-SWAP", state="suspend"),
        ]
        tickers = [
            ticker("AAA-USDT-SWAP", volCcyQuote24h="8000000"),
            ticker("BBB-USDT-SWAP", volCcyQuote24h="15000000"),
            ticker("CCC-USDC-SWAP", volCcyQuote24h="30000000"),
            ticker("DDD-USDT-SWAP", volCcyQuote24h="30000000"),
        ]

        candidates = select_candidates_from_payloads(
            instruments,
            tickers,
            MarketSelectorConfig(min_quote_volume=Decimal("5000000"), max_spread_bps=Decimal("20"), top_n=10),
        )

        self.assertEqual([candidate.inst_id for candidate in candidates], ["BBB-USDT-SWAP", "AAA-USDT-SWAP"])

    def test_filters_wide_spread_and_low_volume(self) -> None:
        instruments = [
            instrument("WIDE-USDT-SWAP"),
            instrument("LOW-USDT-SWAP"),
        ]
        tickers = [
            ticker("WIDE-USDT-SWAP", bidPx="99", askPx="101", volCcyQuote24h="10000000"),
            ticker("LOW-USDT-SWAP", bidPx="99.99", askPx="100.01", volCcyQuote24h="1000"),
        ]

        candidates = select_candidates_from_payloads(
            instruments,
            tickers,
            MarketSelectorConfig(min_quote_volume=Decimal("5000000"), max_spread_bps=Decimal("20"), top_n=10),
        )

        self.assertEqual(candidates, [])

    def test_candidate_uses_fallback_quote_volume(self) -> None:
        candidate = candidate_from_payload(
            instrument("AAA-USDT-SWAP", ctVal="0.1"),
            ticker("AAA-USDT-SWAP", volCcyQuote24h="", volCcy24h="", vol24h="1000", last="20"),
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.quote_volume_24h, Decimal("2000.0"))


if __name__ == "__main__":
    unittest.main()
