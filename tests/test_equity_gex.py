from __future__ import annotations

from datetime import datetime, timezone
import unittest

from equity_gex import (
    _nasdaq_document,
    build_equity_gex_snapshot,
    calculate_equity_gex,
    parse_option_symbol,
)
from dashboard_server import gex_cache_is_fresh


class EquityGexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now_ms = int(datetime(2026, 7, 16, 15, 56, tzinfo=timezone.utc).timestamp() * 1000)

    def test_option_symbol_parser_uses_thousandths_strike_encoding(self) -> None:
        self.assertEqual(parse_option_symbol("SNDK260717C01450000"), (datetime(2026, 7, 17).date(), "C", 1450.0))
        self.assertEqual(parse_option_symbol("LAB260717P00000500"), (datetime(2026, 7, 17).date(), "P", 0.5))

    def test_fresh_cboe_rows_use_contract_size_and_sign_convention(self) -> None:
        source = {
            "source": "CBOE delayed quotes",
            "data": {
                "current_price": 100,
                "last_trade_time": "2026-07-16T11:55:00-04:00",
                "options": [
                    {
                        "option": "TEST260731C00010000",
                        "gamma": 0.2,
                        "open_interest": 10,
                    },
                    {
                        "option": "TEST260731P00010000",
                        "gamma": 0.1,
                        "open_interest": 10,
                    },
                ],
            },
        }
        result = calculate_equity_gex(
            underlying="TEST",
            inst_id="TEST-USDT-SWAP",
            option_symbol="TEST",
            source_data=source,
            now_ms=self.now_ms,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["netGex"], 10000.0)
        self.assertEqual(result["callOiContracts"], 10.0)
        self.assertEqual(result["putOiContracts"], 10.0)

    def test_nasdaq_document_normalizes_chain_for_black_scholes_gamma(self) -> None:
        raw = {
            "status": {"rCode": 200, "bCodeMessage": []},
            "data": {
                "lastTrade": "LAST TRADE: $100.00 (AS OF JUL 16, 2026 11:55 AM ET)",
                "table": {
                    "rows": [
                        {"expirygroup": "July 31, 2026", "strike": None},
                        {
                            "expirygroup": "",
                            "strike": "100.00",
                            "c_Bid": "2.80",
                            "c_Ask": "3.20",
                            "c_Openinterest": "100",
                            "p_Bid": "2.80",
                            "p_Ask": "3.20",
                            "p_Openinterest": "200",
                        },
                    ]
                },
            },
        }
        normalized = _nasdaq_document(raw, symbol="TEST", asset_class="stocks")
        result = calculate_equity_gex(
            underlying="TEST",
            inst_id="TEST-USDT-SWAP",
            option_symbol="TEST",
            source_data=normalized,
            now_ms=self.now_ms,
        )
        self.assertEqual(normalized["source"], "Nasdaq public option chain")
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["optionCount"], 0)
        self.assertIsNotNone(result["netGex"])

    def test_source_older_than_fifteen_minutes_never_exposes_gex(self) -> None:
        source = {
            "data": {
                "current_price": 100,
                "last_trade_time": "2026-07-16T11:40:59-04:00",
                "options": [
                    {"option": "TEST260731C00010000", "gamma": 0.2, "open_interest": 10},
                ],
            }
        }
        result = calculate_equity_gex(
            underlying="TEST",
            inst_id="TEST-USDT-SWAP",
            option_symbol="TEST",
            source_data=source,
            now_ms=self.now_ms,
        )
        self.assertEqual(result["status"], "stale")
        self.assertFalse(result["gexAvailable"])
        self.assertNotIn("netGex", result)

    def test_snapshot_keeps_one_bad_symbol_isolated(self) -> None:
        markets = [
            {"base": "GOOD", "instId": "GOOD-USDT-SWAP", "last": 100, "turnover24h": 20},
            {"base": "BAD", "instId": "BAD-USDT-SWAP", "last": 50, "turnover24h": 10},
        ]

        def fetch(symbol: str) -> dict[str, object]:
            if symbol == "BAD":
                raise RuntimeError("missing option chain")
            return {
                "data": {
                    "current_price": 100,
                    "last_trade_time": "2026-07-16T11:55:00-04:00",
                    "options": [
                        {"option": "GOOD260731C00010000", "gamma": 0.2, "open_interest": 10},
                    ],
                }
            }

        result = build_equity_gex_snapshot(markets, now_ms=self.now_ms, fetcher=fetch, max_workers=2)
        self.assertEqual([row["underlying"] for row in result["underlyings"]], ["GOOD", "BAD"])
        self.assertEqual(result["underlyings"][0]["status"], "ok")
        self.assertEqual(result["underlyings"][1]["status"], "unavailable")
        self.assertEqual(len(result["errors"]), 1)

    def test_cached_freshness_cannot_extend_the_fifteen_minute_limit(self) -> None:
        payload = {"equities": [{"status": "ok", "sourceTimestamp": "2026-07-16T15:00:00+00:00"}]}
        source_time = datetime.fromisoformat("2026-07-16T15:00:00+00:00").timestamp()
        self.assertTrue(gex_cache_is_fresh(payload, now=source_time + 899))
        self.assertFalse(gex_cache_is_fresh(payload, now=source_time + 901))


if __name__ == "__main__":
    unittest.main()
