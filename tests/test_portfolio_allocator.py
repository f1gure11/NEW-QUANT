from __future__ import annotations

import unittest
from decimal import Decimal

from market_selector import MarketCandidate
from portfolio_allocator import (
    AllocationConfig,
    CurrentExposure,
    build_rebalance_actions,
    build_target_allocations,
    capped_weights,
)


def candidate(inst_id: str, last: str = "100") -> MarketCandidate:
    return MarketCandidate(
        inst_id=inst_id,
        inst_family=inst_id.removesuffix("-SWAP"),
        base_ccy=inst_id.split("-")[0],
        quote_ccy="USDT",
        settle_ccy="USDT",
        ct_val=Decimal("1"),
        tick_sz=Decimal("0.01"),
        lot_sz=Decimal("1"),
        min_sz=Decimal("1"),
        state="live",
        last=Decimal(last),
        bid_px=Decimal(last),
        ask_px=Decimal(last),
        spread_bps=Decimal("1"),
        quote_volume_24h=Decimal("10000000"),
        volume_24h=Decimal("100000"),
    )


class PortfolioAllocatorTest(unittest.TestCase):
    def test_capped_weights_redistribute_after_top_cap(self) -> None:
        weights = capped_weights(
            [Decimal("100"), Decimal("1")],
            allocatable_pct=Decimal("80"),
            max_weight_pct=Decimal("50"),
            min_weight_pct=Decimal("5"),
        )

        self.assertEqual(weights, [Decimal("50"), Decimal("30")])

    def test_target_allocations_filter_and_size_contracts(self) -> None:
        rows = [
            {"inst_id": "AAA-USDT-SWAP", "status": "ok", "rank": 1, "score": Decimal("10"), "fills": 5, "risk_events": 0, "quote_volume_24h": 1},
            {"inst_id": "BBB-USDT-SWAP", "status": "ok", "rank": 2, "score": Decimal("8"), "fills": 0, "risk_events": 0, "quote_volume_24h": 1},
            {"inst_id": "CCC-USDT-SWAP", "status": "ok", "rank": 3, "score": Decimal("7"), "fills": 3, "risk_events": 3, "quote_volume_24h": 1},
        ]
        targets = build_target_allocations(
            rows,
            [candidate("AAA-USDT-SWAP"), candidate("BBB-USDT-SWAP"), candidate("CCC-USDT-SWAP")],
            AllocationConfig(max_symbols=3, min_fills=1, max_risk_events=2, cash_reserve_pct=Decimal("20"), max_weight_pct=Decimal("40")),
            equity=Decimal("100"),
            leverage=Decimal("3"),
        )

        self.assertEqual([target.inst_id for target in targets], ["AAA-USDT-SWAP"])
        self.assertEqual(targets[0].weight_pct, Decimal("40"))
        self.assertEqual(targets[0].target_margin, Decimal("40"))
        self.assertEqual(targets[0].max_position, Decimal("1"))

    def test_target_allocations_split_core_and_satellite_at_90_pct_deploy(self) -> None:
        rows = [
            {"inst_id": "AAA-USDT-SWAP", "status": "ok", "rank": 1, "score": Decimal("20"), "fills": 5, "risk_events": 0, "quote_volume_24h": 1},
            {"inst_id": "BBB-USDT-SWAP", "status": "ok", "rank": 2, "score": Decimal("18"), "fills": 5, "risk_events": 0, "quote_volume_24h": 1},
            {"inst_id": "CCC-USDT-SWAP", "status": "ok", "rank": 3, "score": Decimal("12"), "fills": 5, "risk_events": 0, "quote_volume_24h": 1},
            {"inst_id": "DDD-USDT-SWAP", "status": "ok", "rank": 4, "score": Decimal("10"), "fills": 5, "risk_events": 0, "quote_volume_24h": 1},
        ]

        targets = build_target_allocations(
            rows,
            [candidate("AAA-USDT-SWAP"), candidate("BBB-USDT-SWAP"), candidate("CCC-USDT-SWAP"), candidate("DDD-USDT-SWAP")],
            AllocationConfig(),
            equity=Decimal("100"),
            leverage=Decimal("3"),
        )

        self.assertEqual(sum((target.weight_pct for target in targets), Decimal("0")), Decimal("90"))
        self.assertEqual([target.role for target in targets], ["core", "core", "satellite", "satellite"])
        self.assertGreaterEqual(sum(target.weight_pct for target in targets), Decimal("75"))

    def test_rebalance_actions_classify_enter_hold_and_exit(self) -> None:
        targets = build_target_allocations(
            [{"inst_id": "AAA-USDT-SWAP", "status": "ok", "rank": 1, "score": Decimal("10"), "fills": 5, "risk_events": 0, "quote_volume_24h": 1}],
            [candidate("AAA-USDT-SWAP")],
            AllocationConfig(cash_reserve_pct=Decimal("60"), min_fills=1, max_weight_pct=Decimal("40")),
            equity=Decimal("100"),
            leverage=Decimal("3"),
        )
        actions = build_rebalance_actions(
            targets,
            {
                "AAA-USDT-SWAP": CurrentExposure(inst_id="AAA-USDT-SWAP", gross_notional=Decimal("120"), margin_estimate=Decimal("39")),
                "OLD-USDT-SWAP": CurrentExposure(inst_id="OLD-USDT-SWAP", gross_notional=Decimal("30"), margin_estimate=Decimal("10")),
            },
            AllocationConfig(default_equity=Decimal("100"), rebalance_threshold_pct=Decimal("5"), close_missing=True),
        )

        by_id = {action.inst_id: action for action in actions}
        self.assertEqual(by_id["AAA-USDT-SWAP"].action, "hold")
        self.assertEqual(by_id["OLD-USDT-SWAP"].action, "exit")


if __name__ == "__main__":
    unittest.main()
