from __future__ import annotations

import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import auto_grid_bot
from auto_grid_bot import (
    BotConfig,
    attached_stop_order,
    detect_triggered_exchange_stop,
    desired_exchange_stops,
    exchange_stop_trigger_price,
    missing_exchange_stops,
    stale_exchange_stops,
    sync_exchange_protection_stops,
)
from okx_client import OkxRestClient


def make_config(**overrides) -> BotConfig:
    parser = auto_grid_bot.parse_args
    with patch(
        "sys.argv",
        [
            "auto_grid_bot.py",
            "--inst-id",
            "TEST-USDT-SWAP",
            "--exchange-stop-enabled",
            "--exchange-stop-bps",
            "650",
            "--leverage",
            "5",
        ],
    ):
        args = parser()

    config = BotConfig(
        inst_id=args.inst_id,
        lower=Decimal(args.lower),
        upper=Decimal(args.upper),
        leverage=Decimal(args.leverage),
        grid_bps=Decimal(args.grid_bps),
        min_net_bps=Decimal(args.min_net_bps),
        soft_bps=Decimal(args.soft_bps),
        hard_bps=Decimal(args.hard_bps),
        order_sz=Decimal(args.order_sz),
        max_position=Decimal(args.max_position),
        max_open_orders_per_side=args.max_open_orders_per_side,
        max_actions_per_cycle=args.max_actions_per_cycle,
        interval=args.interval,
        live=args.live,
        once=args.once,
        set_leverage=args.set_leverage,
        cancel_on_stop=args.cancel_on_stop,
        ord_type=args.ord_type,
        mode=args.mode,
        adaptive_width_bps=Decimal(args.adaptive_width_bps),
        adaptive_min_width_bps=Decimal(args.adaptive_min_width_bps),
        adaptive_max_width_bps=Decimal(args.adaptive_max_width_bps),
        adaptive_vol_multiplier=Decimal(args.adaptive_vol_multiplier),
        range_drift_mode=args.range_drift_mode,
        range_drift_weight_bps=Decimal(args.range_drift_weight_bps),
        range_drift_max_bps=Decimal(args.range_drift_max_bps),
        sizing_mode=args.sizing_mode,
        order_margin_pct=Decimal(args.order_margin_pct),
        max_margin_pct=Decimal(args.max_margin_pct),
        total_profit_tp=Decimal(args.total_profit_tp),
        total_profit_tp_pct=Decimal(args.total_profit_tp_pct),
        total_profit_tp_cap=Decimal(args.total_profit_tp_cap),
        total_profit_action=args.total_profit_action,
        min_tp_profit=Decimal(args.min_tp_profit),
        total_loss_sl=Decimal(args.total_loss_sl),
        total_loss_sl_pct=Decimal(args.total_loss_sl_pct),
        total_loss_sl_cap=Decimal(args.total_loss_sl_cap),
        position_loss_sl_bps=Decimal(args.position_loss_sl_bps),
        exchange_stop_enabled=args.exchange_stop_enabled,
        exchange_stop_bps=Decimal(args.exchange_stop_bps),
        exchange_stop_trigger_px_type=args.exchange_stop_trigger_px_type,
        exchange_stop_reprice_bps=Decimal(args.exchange_stop_reprice_bps),
        min_tp_bps=Decimal(args.min_tp_bps),
        missed_tp_ord_type=args.missed_tp_ord_type,
        missed_tp_slippage_bps=Decimal(args.missed_tp_slippage_bps),
        hard_stop_ord_type=args.hard_stop_ord_type,
        hard_stop_slippage_bps=Decimal(args.hard_stop_slippage_bps),
        risk_cooldown=args.risk_cooldown,
        recenter_on_cooldown=args.recenter_on_cooldown,
        trend_filter=args.trend_filter,
        trend_lookback=args.trend_lookback,
        trend_threshold_bps=Decimal(args.trend_threshold_bps),
        regime_filter=args.regime_filter,
        regime_bar=args.regime_bar,
        regime_short_ma=args.regime_short_ma,
        regime_long_ma=args.regime_long_ma,
        regime_diff_bps=Decimal(args.regime_diff_bps),
        regime_confirm_bars=args.regime_confirm_bars,
        one_way_open=args.one_way_open,
        bot_started_ms=1,
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


class FakeClient:
    def __init__(self) -> None:
        self.placed: list[dict] = []
        self.cancelled: list[dict] = []

    def place_algo_order(self, **payload):
        self.placed.append(payload)
        return {"data": [{"algoId": "new"}]}

    def cancel_algo_orders(self, orders):
        self.cancelled.extend(orders)
        return {"data": orders}


class ExchangeProtectionStopsTest(unittest.TestCase):
    def test_trigger_price_uses_levered_bps(self) -> None:
        config = make_config(leverage=Decimal("5"), exchange_stop_bps=Decimal("650"))

        self.assertEqual(exchange_stop_trigger_price(config, "long", Decimal("100"), Decimal("0.01")), Decimal("98.70"))
        self.assertEqual(exchange_stop_trigger_price(config, "short", Decimal("100"), Decimal("0.01")), Decimal("101.30"))

    def test_desired_stop_is_reduce_only_market_conditional(self) -> None:
        config = make_config()
        positions = [{"instId": "TEST-USDT-SWAP", "posSide": "long", "pos": "2", "avgPx": "100"}]

        desired = desired_exchange_stops(config, positions, Decimal("0.01"), Decimal("1"))

        self.assertEqual(len(desired), 1)
        order = desired[0]
        self.assertEqual(order["ord_type"], "conditional")
        self.assertEqual(order["side"], "sell")
        self.assertEqual(order["pos_side"], "long")
        self.assertEqual(order["sl_ord_px"], "-1")
        self.assertEqual(order["sl_trigger_px_type"], "mark")
        self.assertTrue(order["reduce_only"])
        self.assertTrue(order["cxl_on_close_pos"])
        self.assertTrue(order["algo_cl_ord_id"].startswith("xsgb"))

    def test_attached_stop_order_uses_tick_rounded_trigger(self) -> None:
        config = make_config(leverage=Decimal("5"), exchange_stop_bps=Decimal("650"))

        order = attached_stop_order(config, "short", Decimal("100"), Decimal("0.01"))

        self.assertEqual(order["slTriggerPx"], "101.3")
        self.assertEqual(order["slOrdPx"], "-1")
        self.assertEqual(order["slTriggerPxType"], "mark")
        self.assertTrue(order["attachAlgoClOrdId"].startswith("xsgbs"))

    def test_existing_stop_repriced_when_size_changes_or_trigger_drifts(self) -> None:
        config = make_config(exchange_stop_reprice_bps=Decimal("5"))
        desired = [
            {
                "inst_id": "TEST-USDT-SWAP",
                "side": "sell",
                "pos_side": "long",
                "ord_type": "conditional",
                "sz": "2",
                "sl_trigger_px": "98.7",
                "sl_ord_px": "-1",
                "sl_trigger_px_type": "mark",
            }
        ]
        existing = [
            {
                "instId": "TEST-USDT-SWAP",
                "side": "sell",
                "posSide": "long",
                "ordType": "conditional",
                "sz": "1",
                "slTriggerPx": "98.7",
                "slOrdPx": "-1",
                "slTriggerPxType": "mark",
                "algoClOrdId": "xsgbl987",
                "algoId": "old",
            }
        ]

        self.assertEqual(stale_exchange_stops(existing, desired, config.exchange_stop_reprice_bps), existing)
        self.assertEqual(missing_exchange_stops(existing, desired, config.exchange_stop_reprice_bps), desired)

    def test_sync_cancels_old_stop_when_disabled(self) -> None:
        config = make_config(exchange_stop_enabled=False, live=True)
        client = FakeClient()
        state = {
            "positions": [],
            "pendingAlgos": [
                {
                    "instId": "TEST-USDT-SWAP",
                    "side": "sell",
                    "posSide": "long",
                    "ordType": "conditional",
                    "sz": "1",
                    "slTriggerPx": "98",
                    "slOrdPx": "-1",
                    "slTriggerPxType": "mark",
                    "algoClOrdId": "xsgbl98",
                    "algoId": "old",
                }
            ],
        }

        with patch("auto_grid_bot.log_event"), redirect_stdout(StringIO()):
            actions = sync_exchange_protection_stops(client, config, state, Decimal("0.01"), Decimal("1"))

        self.assertEqual(actions, 1)
        self.assertEqual(client.cancelled, [{"instId": "TEST-USDT-SWAP", "algoId": "old"}])
        self.assertEqual(client.placed, [])

    def test_detect_triggered_exchange_stop_after_loss_close_fill(self) -> None:
        config = make_config(bot_started_ms=1000)
        config.exchange_stop_triggers = {"long": Decimal("98.70")}
        state = {
            "positions": [{"instId": "TEST-USDT-SWAP", "posSide": "long", "pos": "0", "avgPx": ""}],
            "fills": [
                {
                    "side": "sell",
                    "posSide": "long",
                    "fillPnl": "-0.25",
                    "fillPx": "98.6",
                    "fillSz": "2",
                    "fillTime": "2000",
                    "ordId": "close",
                }
            ],
        }

        event = detect_triggered_exchange_stop(config, state)

        self.assertIsNotNone(event)
        self.assertEqual(event["posSide"], "long")
        self.assertEqual(event["triggerPx"], "98.7")
        self.assertEqual(config.exchange_stop_triggers, {})


class OkxAlgoClientTest(unittest.TestCase):
    def test_place_order_can_attach_stop(self) -> None:
        calls = []

        class RecordingClient(OkxRestClient):
            def request(self, method, path, *, params=None, body=None, private=False):
                calls.append(Namespace(method=method, path=path, params=params, body=body, private=private))
                return {"code": "0", "data": []}

        client = RecordingClient()
        attached = [{"slTriggerPx": "98.7", "slOrdPx": "-1", "slTriggerPxType": "mark"}]
        client.place_order(
            inst_id="TEST-USDT-SWAP",
            td_mode="cross",
            side="buy",
            pos_side="long",
            ord_type="post_only",
            sz="2",
            px="100",
            cl_ord_id="open",
            attach_algo_ords=attached,
        )

        call = calls[0]
        self.assertEqual(call.path, "/api/v5/trade/order")
        self.assertEqual(call.body["attachAlgoOrds"], attached)

    def test_place_algo_order_payload(self) -> None:
        calls = []

        class RecordingClient(OkxRestClient):
            def request(self, method, path, *, params=None, body=None, private=False):
                calls.append(Namespace(method=method, path=path, params=params, body=body, private=private))
                return {"code": "0", "data": []}

        client = RecordingClient()
        client.place_algo_order(
            inst_id="TEST-USDT-SWAP",
            td_mode="cross",
            side="sell",
            pos_side="long",
            ord_type="conditional",
            sz="2",
            algo_cl_ord_id="xsgbl987",
            sl_trigger_px="98.7",
            sl_ord_px="-1",
            sl_trigger_px_type="mark",
            reduce_only=True,
            cxl_on_close_pos=True,
        )

        call = calls[0]
        self.assertEqual(call.method, "POST")
        self.assertEqual(call.path, "/api/v5/trade/order-algo")
        self.assertTrue(call.private)
        self.assertEqual(call.body["algoClOrdId"], "xsgbl987")
        self.assertTrue(call.body["reduceOnly"])
        self.assertTrue(call.body["cxlOnClosePos"])


if __name__ == "__main__":
    unittest.main()
