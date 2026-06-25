from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from portfolio_rebalancer import (
    load_rebalance_targets,
    reduce_orders_for_target,
    run_once,
)


def position(pos_side: str, pos: str = "10") -> dict:
    return {
        "instId": "AAA-USDT-SWAP",
        "posSide": pos_side,
        "pos": pos,
        "markPx": "100",
        "lotSz": "1",
    }


class PortfolioRebalancerTest(unittest.TestCase):
    def test_reduce_orders_exit_full_position(self) -> None:
        target = load_target(action="exit", current="20", target="0", delta="-20")

        orders = reduce_orders_for_target(
            target,
            [position("long", "10"), position("short", "4")],
            ord_type="market",
            slippage_bps=Decimal("50"),
            min_reduce_margin=Decimal("0.05"),
        )

        self.assertEqual([(order.side, order.pos_side, order.sz) for order in orders], [("sell", "long", Decimal("10")), ("buy", "short", Decimal("4"))])

    def test_reduce_orders_scales_by_margin_delta(self) -> None:
        target = load_target(action="decrease", current="20", target="12", delta="-8")

        orders = reduce_orders_for_target(
            target,
            [position("long", "10")],
            ord_type="market",
            slippage_bps=Decimal("50"),
            min_reduce_margin=Decimal("0.05"),
        )

        self.assertEqual(orders[0].sz, Decimal("4"))

    def test_load_targets_and_dry_run_without_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            (report_dir / "rebalance_plan.json").write_text(
                json.dumps(
                    {
                        "actions": [
                            {
                                "inst_id": "AAA-USDT-SWAP",
                                "action": "exit",
                                "current_margin": "20",
                                "target_margin": "0",
                                "delta_margin": "-20",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            targets = load_rebalance_targets(report_dir)
            with redirect_stdout(StringIO()):
                orders = run_once(
                    object(),
                    SimpleNamespace(
                        report_dir=str(report_dir),
                        inst_id="",
                        log_path=str(report_dir / "rebalancer.jsonl"),
                        live=False,
                        include_account=False,
                        ord_type="market",
                        slippage_bps="50",
                        min_reduce_margin="0.05",
                        cancel_pending=False,
                        cancel_algos=False,
                    ),
                )

        self.assertEqual(targets[0].inst_id, "AAA-USDT-SWAP")
        self.assertEqual(orders, [])


def load_target(*, action: str, current: str, target: str, delta: str):
    return load_rebalance_targets_from_payload(
        {
            "actions": [
                {
                    "inst_id": "AAA-USDT-SWAP",
                    "action": action,
                    "current_margin": current,
                    "target_margin": target,
                    "delta_margin": delta,
                }
            ]
        }
    )[0]


def load_rebalance_targets_from_payload(payload: dict):
    with tempfile.TemporaryDirectory() as tmpdir:
        report_dir = Path(tmpdir)
        (report_dir / "rebalance_plan.json").write_text(json.dumps(payload), encoding="utf-8")
        return load_rebalance_targets(report_dir)


if __name__ == "__main__":
    unittest.main()
