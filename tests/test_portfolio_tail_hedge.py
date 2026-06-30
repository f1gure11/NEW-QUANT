from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from decimal import Decimal
from pathlib import Path

from market_selector import MarketCandidate
from okx_client import OkxApiError
import portfolio_tail_hedge as tail_hedge
from portfolio_allocator import CurrentExposure, TargetAllocation
from portfolio_tail_hedge import (
    TailHedgeConfig,
    build_tail_hedge_plan,
    hedge_order_payload,
    run_once,
    write_tail_hedge_outputs,
)


def candidate(inst_id: str = "BTC-USDT-SWAP", last: str = "50000") -> MarketCandidate:
    return MarketCandidate(
        inst_id=inst_id,
        inst_family=inst_id.removesuffix("-SWAP"),
        base_ccy=inst_id.split("-")[0],
        quote_ccy="USDT",
        settle_ccy="USDT",
        ct_val=Decimal("0.01"),
        tick_sz=Decimal("0.1"),
        lot_sz=Decimal("0.01"),
        min_sz=Decimal("0.01"),
        state="live",
        last=Decimal(last),
        bid_px=Decimal(last),
        ask_px=Decimal(last),
        spread_bps=Decimal("1"),
        quote_volume_24h=Decimal("1000000000"),
        volume_24h=Decimal("1000"),
    )


def target(inst_id: str = "AAA-USDT-SWAP") -> TargetAllocation:
    return TargetAllocation(
        inst_id=inst_id,
        rank=1,
        role="core",
        score=Decimal("1"),
        weight_pct=Decimal("40"),
        target_margin=Decimal("40"),
        target_notional=Decimal("120"),
        last=Decimal("100"),
        order_sz=Decimal("1"),
        max_position=Decimal("3"),
        pool_window_hours=Decimal("5"),
        pool_window_bars=300,
        pool_avg_abs_bps=Decimal("10"),
        pool_shock_bps=Decimal("150"),
        pool_trend_bps=Decimal("-420"),
        reason="test",
        risk_events=5,
    )


class PortfolioTailHedgeTest(unittest.TestCase):
    def test_build_tail_hedge_plan_triggers_opposite_short_for_net_long(self) -> None:
        exposure = CurrentExposure(
            inst_id="AAA-USDT-SWAP",
            long_notional=Decimal("180"),
            short_notional=Decimal("20"),
            net_notional=Decimal("160"),
            gross_notional=Decimal("200"),
            margin_estimate=Decimal("50"),
        )

        plan = build_tail_hedge_plan(
            targets=[target()],
            current_exposures={"AAA-USDT-SWAP": exposure},
            candidates=[candidate()],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(
                hedge_ratio=Decimal("0.5"),
                trigger_net_exposure_pct=Decimal("100"),
                trigger_shock_bps=Decimal("120"),
                trigger_trend_bps=Decimal("350"),
                trigger_risk_events=4,
                min_hedge_notional=Decimal("10"),
                max_hedge_margin_pct=Decimal("20"),
                hedge_leverage=Decimal("3"),
            ),
            generated_at="2026-06-30T00:00:00Z",
        )

        self.assertEqual(plan.status, "triggered")
        self.assertEqual(plan.net_notional, Decimal("160"))
        self.assertGreaterEqual(len(plan.trigger_reasons), 3)
        self.assertEqual(len(plan.actions), 1)
        self.assertEqual(plan.actions[0].inst_id, "BTC-USDT-SWAP")
        self.assertEqual(plan.actions[0].side, "sell")
        self.assertEqual(plan.actions[0].pos_side, "short")
        self.assertEqual(plan.actions[0].action, "increase")
        self.assertFalse(plan.actions[0].reduce_only)
        self.assertEqual(plan.actions[0].target_notional, Decimal("60"))
        self.assertEqual(plan.actions[0].target_hedge_ratio, Decimal("0.5"))
        self.assertEqual(plan.actions[0].hedge_level, "fixed")
        self.assertEqual(plan.actions[0].sz, Decimal("0.12"))
        self.assertEqual(plan.actions[0].estimated_px, Decimal("50000"))

    def test_build_tail_hedge_plan_watches_without_account_exposures(self) -> None:
        plan = build_tail_hedge_plan(
            targets=[target()],
            current_exposures={},
            candidates=[candidate()],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(),
        )

        self.assertEqual(plan.status, "no_account")
        self.assertEqual(plan.actions, [])
        self.assertIn("include-account", plan.note)

    def test_write_outputs_and_dry_run_order_payload(self) -> None:
        exposure = CurrentExposure(
            inst_id="AAA-USDT-SWAP",
            long_notional=Decimal("0"),
            short_notional=Decimal("160"),
            net_notional=Decimal("-160"),
            gross_notional=Decimal("160"),
            margin_estimate=Decimal("50"),
        )
        plan = build_tail_hedge_plan(
            targets=[target()],
            current_exposures={"AAA-USDT-SWAP": exposure},
            candidates=[candidate()],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(
                hedge_ratio=Decimal("0.25"),
                trigger_net_exposure_pct=Decimal("100"),
                min_hedge_notional=Decimal("10"),
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            write_tail_hedge_outputs(Path(tmpdir), plan)
            payload = json.loads((Path(tmpdir) / "hedge_plan.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "triggered")
        self.assertEqual(payload["actions"][0]["side"], "buy")
        self.assertEqual(payload["actions"][0]["reduce_only"], False)
        order = hedge_order_payload(payload["actions"][0], Namespace(ord_type="", slippage_bps="20"))
        self.assertEqual(order["inst_id"], "BTC-USDT-SWAP")
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["pos_side"], "long")
        self.assertFalse(order["reduce_only"])
        self.assertNotIn("px", order)

        limit_order = hedge_order_payload(payload["actions"][0], Namespace(ord_type="limit", slippage_bps="20"))
        self.assertEqual(limit_order["ord_type"], "limit")
        self.assertEqual(limit_order["px"], "50100")

    def test_dynamic_tail_hedge_uses_stress_ratio_and_margin_cap(self) -> None:
        exposure = CurrentExposure(
            inst_id="AAA-USDT-SWAP",
            long_notional=Decimal("220"),
            short_notional=Decimal("0"),
            net_notional=Decimal("220"),
            gross_notional=Decimal("220"),
            margin_estimate=Decimal("50"),
        )

        plan = build_tail_hedge_plan(
            targets=[target()],
            current_exposures={"AAA-USDT-SWAP": exposure},
            candidates=[candidate()],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(
                mode="dynamic",
                hedge_ratio=Decimal("0.35"),
                stress_hedge_ratio=Decimal("0.70"),
                trigger_net_exposure_pct=Decimal("100"),
                stress_net_exposure_pct=Decimal("180"),
                full_hedge_net_exposure_pct=Decimal("999"),
                max_hedge_margin_pct=Decimal("20"),
                stress_hedge_max_margin_pct=Decimal("40"),
                hedge_leverage=Decimal("3"),
            ),
        )

        self.assertEqual(plan.status, "triggered")
        self.assertEqual(plan.target_hedge_level, "stress")
        self.assertEqual(plan.target_hedge_ratio, Decimal("0.70"))
        self.assertEqual(plan.target_hedge_notional, Decimal("120"))
        self.assertEqual(plan.actions[0].target_notional, Decimal("120"))
        self.assertEqual(plan.actions[0].sz, Decimal("0.24"))

    def test_dynamic_tail_hedge_uses_full_ratio_for_extreme_risk(self) -> None:
        exposure = CurrentExposure(
            inst_id="AAA-USDT-SWAP",
            long_notional=Decimal("260"),
            short_notional=Decimal("0"),
            net_notional=Decimal("260"),
            gross_notional=Decimal("260"),
            margin_estimate=Decimal("50"),
        )

        plan = build_tail_hedge_plan(
            targets=[target()],
            current_exposures={"AAA-USDT-SWAP": exposure},
            candidates=[candidate()],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(
                mode="dynamic",
                hedge_ratio=Decimal("0.35"),
                stress_hedge_ratio=Decimal("0.70"),
                full_hedge_ratio=Decimal("1"),
                trigger_net_exposure_pct=Decimal("100"),
                full_hedge_net_exposure_pct=Decimal("240"),
                full_hedge_max_margin_pct=Decimal("100"),
                hedge_leverage=Decimal("3"),
            ),
        )

        self.assertEqual(plan.status, "triggered")
        self.assertEqual(plan.target_hedge_level, "full")
        self.assertEqual(plan.target_hedge_ratio, Decimal("1"))
        self.assertEqual(plan.target_hedge_notional, Decimal("260"))
        self.assertEqual(plan.actions[0].target_notional, Decimal("260"))
        self.assertEqual(plan.actions[0].sz, Decimal("0.52"))

    def test_non_crypto_exposure_uses_same_instrument_hedge(self) -> None:
        exposure = CurrentExposure(
            inst_id="XAU-USDT-SWAP",
            long_notional=Decimal("150"),
            short_notional=Decimal("0"),
            net_notional=Decimal("150"),
            gross_notional=Decimal("150"),
            margin_estimate=Decimal("50"),
        )

        plan = build_tail_hedge_plan(
            targets=[target("XAU-USDT-SWAP")],
            current_exposures={"XAU-USDT-SWAP": exposure},
            candidates=[candidate("BTC-USDT-SWAP"), candidate("XAU-USDT-SWAP", last="2500")],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(
                mode="dynamic",
                hedge_ratio=Decimal("1"),
                trigger_net_exposure_pct=Decimal("100"),
                max_hedge_margin_pct=Decimal("100"),
                hedge_leverage=Decimal("3"),
            ),
        )

        self.assertEqual(plan.status, "triggered")
        self.assertEqual(plan.actions[0].inst_id, "XAU-USDT-SWAP")
        self.assertEqual(plan.actions[0].action, "increase")
        self.assertEqual(plan.actions[0].side, "sell")
        self.assertEqual(plan.actions[0].pos_side, "short")
        self.assertFalse(plan.actions[0].reduce_only)

    def test_non_crypto_exposure_without_metadata_reduces_same_position(self) -> None:
        exposure = CurrentExposure(
            inst_id="XAU-USDT-SWAP",
            long_sz=Decimal("4"),
            long_notional=Decimal("200"),
            short_notional=Decimal("0"),
            net_notional=Decimal("200"),
            gross_notional=Decimal("200"),
            margin_estimate=Decimal("50"),
        )

        plan = build_tail_hedge_plan(
            targets=[target("XAU-USDT-SWAP")],
            current_exposures={"XAU-USDT-SWAP": exposure},
            candidates=[candidate("BTC-USDT-SWAP")],
            score_rows=[],
            equity=Decimal("100"),
            config=TailHedgeConfig(
                mode="dynamic",
                hedge_ratio=Decimal("0.5"),
                trigger_net_exposure_pct=Decimal("100"),
                stress_net_exposure_pct=Decimal("999"),
                max_hedge_margin_pct=Decimal("100"),
                hedge_leverage=Decimal("3"),
            ),
        )

        self.assertEqual(plan.status, "triggered")
        self.assertEqual(plan.actions[0].inst_id, "XAU-USDT-SWAP")
        self.assertEqual(plan.actions[0].action, "reduce")
        self.assertEqual(plan.actions[0].side, "sell")
        self.assertEqual(plan.actions[0].pos_side, "long")
        self.assertTrue(plan.actions[0].reduce_only)
        self.assertEqual(plan.actions[0].sz, Decimal("2.0"))

    def test_live_run_skips_when_current_net_direction_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(report_dir)
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "ETH-USDT-SWAP",
                        "posSide": "short",
                        "pos": "1",
                        "notionalUsd": "200",
                    }
                ]
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(placed, [])
        self.assertEqual(client.orders, [])
        self.assertEqual(client.leverage_calls, [])

    def test_live_run_skips_when_existing_same_direction_hedge_is_enough(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(report_dir, target_notional="60", size="0.12")
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "AAA-USDT-SWAP",
                        "posSide": "long",
                        "pos": "1",
                        "notionalUsd": "180",
                    },
                    {
                        "instId": "BTC-USDT-SWAP",
                        "posSide": "short",
                        "pos": "0.12",
                        "notionalUsd": "60",
                    },
                ]
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(placed, [])
        self.assertEqual(client.orders, [])
        self.assertEqual(client.leverage_calls, [])

    def test_live_run_places_remaining_hedge_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(report_dir, target_notional="60", size="0.12")
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "AAA-USDT-SWAP",
                        "posSide": "long",
                        "pos": "1",
                        "notionalUsd": "180",
                    },
                    {
                        "instId": "BTC-USDT-SWAP",
                        "posSide": "short",
                        "pos": "0.04",
                        "notionalUsd": "20",
                    },
                ]
            )

            placed = run_once(client, hedge_args(report_dir))
            second = run_once(client, hedge_args(report_dir))
            self.assertTrue(tail_hedge.STATE_PATH.exists())

        self.assertEqual(len(placed), 1)
        self.assertEqual(second, [])
        self.assertEqual(client.orders[0]["sz"], "0.07")
        self.assertEqual(client.orders[0]["side"], "sell")
        self.assertEqual(client.orders[0]["pos_side"], "short")
        self.assertEqual(client.leverage_calls[0]["lever"], "3")

    def test_live_run_uses_action_dynamic_hedge_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(
                report_dir,
                target_notional="180",
                size="0.36",
                target_hedge_ratio="1",
                max_margin_pct="100",
            )
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "AAA-USDT-SWAP",
                        "posSide": "long",
                        "pos": "1",
                        "notionalUsd": "180",
                    }
                ]
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(len(placed), 1)
        self.assertEqual(client.orders[0]["sz"], "0.36")

    def test_auto_live_run_cancels_non_reduce_pending_before_hedge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(report_dir, target_notional="60", size="0.12")
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "AAA-USDT-SWAP",
                        "posSide": "long",
                        "pos": "1",
                        "notionalUsd": "180",
                    }
                ],
                pending=[
                    {"instId": "BTC-USDT-SWAP", "ordId": "open", "clOrdId": "open", "side": "buy", "posSide": "long", "sz": "0.01", "px": "49000", "reduceOnly": "false"},
                    {"instId": "BTC-USDT-SWAP", "ordId": "tp", "clOrdId": "tp", "side": "sell", "posSide": "long", "sz": "0.01", "px": "51000", "reduceOnly": "true"},
                ],
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(len(placed), 1)
        self.assertEqual(client.canceled[0][0]["ordId"], "open")
        self.assertEqual(len(client.canceled[0]), 1)

    def test_auto_live_run_continues_when_lower_leverage_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(report_dir, target_notional="60", size="0.12")
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "AAA-USDT-SWAP",
                        "posSide": "long",
                        "pos": "1",
                        "notionalUsd": "180",
                    }
                ],
                leverage_error=OkxApiError("OKX API error 59108", okx_code="59108"),
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(len(placed), 1)
        self.assertEqual(client.orders[0]["sz"], "0.12")

    def test_auto_live_run_shrinks_order_to_available_margin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(report_dir, target_notional="60", size="0.12")
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "AAA-USDT-SWAP",
                        "posSide": "long",
                        "pos": "1",
                        "notionalUsd": "180",
                    }
                ],
                available_usdt="2.5",
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(len(placed), 1)
        self.assertEqual(client.orders[0]["sz"], "0.01")

    def test_live_reduce_only_fallback_does_not_need_margin_or_leverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_plan(
                report_dir,
                inst_id="XAU-USDT-SWAP",
                action_kind="reduce",
                side="sell",
                pos_side="long",
                reduce_only=True,
                target_notional="100",
                size="2",
            )
            tail_hedge.STATE_PATH = report_dir / "state.json"
            tail_hedge.LOG_PATH = report_dir / "actions.jsonl"
            client = FakeHedgeClient(
                positions=[
                    {
                        "instId": "XAU-USDT-SWAP",
                        "posSide": "long",
                        "pos": "4",
                        "notionalUsd": "200",
                    }
                ],
                available_usdt="0",
            )

            placed = run_once(client, hedge_args(report_dir))

        self.assertEqual(len(placed), 1)
        self.assertEqual(client.leverage_calls, [])
        self.assertEqual(client.orders[0]["inst_id"], "XAU-USDT-SWAP")
        self.assertEqual(client.orders[0]["side"], "sell")
        self.assertEqual(client.orders[0]["pos_side"], "long")
        self.assertTrue(client.orders[0]["reduce_only"])


class FakeHedgeClient:
    def __init__(
        self,
        *,
        positions: list[dict] | None = None,
        pending: list[dict] | None = None,
        leverage_error: Exception | None = None,
        available_usdt: str = "100",
    ) -> None:
        self.positions = positions or []
        self.pending = pending or []
        self.leverage_error = leverage_error
        self.available_usdt = available_usdt
        self.orders: list[dict] = []
        self.leverage_calls: list[dict] = []
        self.canceled: list[list[dict]] = []

    def get_positions(self, _inst_type: str) -> dict:
        return {"data": self.positions}

    def get_pending_orders(self, _inst_id: str) -> dict:
        return {"data": self.pending}

    def get_ticker(self, _inst_id: str) -> dict:
        return {"data": [{"last": "50000"}]}

    def get_balance(self) -> dict:
        return {"data": [{"details": [{"ccy": "USDT", "availBal": self.available_usdt}]}]}

    def request(self, _method: str, _path: str, *, params=None, body=None, private=False) -> dict:
        inst_id = (params or {}).get("instId", "BTC-USDT-SWAP")
        return {
            "data": [
                {
                    "instId": inst_id,
                    "ctVal": "0.01",
                    "lotSz": "0.01",
                    "minSz": "0.01",
                }
            ]
        }

    def set_leverage(self, **payload):
        self.leverage_calls.append(payload)
        if self.leverage_error:
            raise self.leverage_error
        return {"data": [payload]}

    def place_order(self, **payload):
        self.orders.append(payload)
        return {"data": [payload]}

    def cancel_orders(self, payload: list[dict]) -> dict:
        self.canceled.append(payload)
        return {"data": payload}


def write_plan(
    report_dir: Path,
    *,
    inst_id: str = "BTC-USDT-SWAP",
    action_kind: str = "increase",
    side: str = "sell",
    pos_side: str = "short",
    reduce_only: bool = False,
    target_notional: str = "60",
    size: str = "0.12",
    target_hedge_ratio: str = "0.35",
    hedge_level: str = "fixed",
    max_margin_pct: str = "20",
) -> None:
    action = {
        "inst_id": inst_id,
        "action": action_kind,
        "side": side,
        "pos_side": pos_side,
        "sz": size,
        "reduce_only": reduce_only,
        "estimated_px": "50000",
        "target_notional": target_notional,
        "estimated_notional": target_notional,
        "target_hedge_ratio": target_hedge_ratio,
        "hedge_level": hedge_level,
        "max_margin_pct": max_margin_pct,
        "leverage": "3",
        "ord_type": "market",
        "status": "ready",
        "reason": "test",
        "note": "test",
    }
    payload = {
        "generated_at": tail_hedge.now_iso(),
        "mode": "plan",
        "status": "triggered",
        "equity": "100",
        "net_notional": "180",
        "target_hedge_ratio": target_hedge_ratio,
        "target_hedge_level": hedge_level,
        "target_hedge_notional": target_notional,
        "actions": [action],
        "config": {
            "hedge_ratio": target_hedge_ratio,
            "max_hedge_margin_pct": "20",
            "hedge_leverage": "3",
            "min_hedge_notional": "10",
        },
    }
    (report_dir / "hedge_plan.json").write_text(json.dumps(payload), encoding="utf-8")


def hedge_args(report_dir: Path) -> Namespace:
    return Namespace(
        report_dir=str(report_dir),
        ord_type="",
        slippage_bps="20",
        live=True,
        auto=True,
        force=False,
        max_plan_age_min="120",
        existing_hedge_threshold_pct="95",
        min_remaining_notional="10",
        set_leverage=True,
        release_hedge_margin=True,
        pause_hedge_inst_opens=False,
        margin_safety_multiplier="0.9",
    )


if __name__ == "__main__":
    unittest.main()
