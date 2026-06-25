from __future__ import annotations

import unittest
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import auto_grid_bot
from rolling_adaptive import RollingAdaptiveLimits, calculate_rolling_adaptive
from tests.test_exchange_protection_stops import make_config


def candles_from_closes(closes: list[Decimal]) -> list[list[str]]:
    newest_first = list(reversed(closes))
    return [[str(index), "", "", "", str(close), "", "", "", "1"] for index, close in enumerate(newest_first)]


class RollingAdaptiveTest(unittest.TestCase):
    def test_low_volatility_keeps_leverage_and_tight_grid_near_upper_risk_limits(self) -> None:
        closes = [Decimal("100") for _ in range(40)]

        result = calculate_rolling_adaptive(
            candles_from_closes(closes),
            mark_px=Decimal("100.39"),
            equity=Decimal("100"),
            ct_val=Decimal("0.01"),
            min_sz=Decimal("1"),
            limits=RollingAdaptiveLimits(),
        )

        self.assertEqual(result.leverage, Decimal("5"))
        self.assertEqual(result.grid_bps, Decimal("18"))
        self.assertEqual(result.adaptive_width_bps, Decimal("260"))
        self.assertEqual(result.order_margin_pct, Decimal("10"))
        self.assertEqual(result.max_margin_pct, Decimal("35"))
        self.assertTrue(result.tradeable_min_contract)

    def test_high_volatility_widens_grid_reduces_leverage_and_risk(self) -> None:
        closes = [
            Decimal("100"),
            Decimal("102"),
            Decimal("97"),
            Decimal("104"),
            Decimal("95"),
            Decimal("106"),
            Decimal("94"),
            Decimal("108"),
            Decimal("92"),
            Decimal("110"),
            Decimal("90"),
            Decimal("112"),
        ]

        result = calculate_rolling_adaptive(
            candles_from_closes(closes),
            mark_px=Decimal("112"),
            equity=Decimal("100"),
            ct_val=Decimal("0.01"),
            min_sz=Decimal("1"),
            limits=RollingAdaptiveLimits(window=10),
        )

        self.assertEqual(result.leverage, Decimal("1"))
        self.assertEqual(result.grid_bps, Decimal("80"))
        self.assertEqual(result.adaptive_width_bps, Decimal("1200"))
        self.assertEqual(result.order_margin_pct, Decimal("3"))
        self.assertEqual(result.max_margin_pct, Decimal("12"))
        self.assertEqual(result.position_loss_sl_bps, Decimal("900"))
        self.assertEqual(result.exchange_stop_bps, Decimal("900"))

    def test_tiny_account_marks_min_contract_untradeable_when_margin_cap_is_too_low(self) -> None:
        closes = [Decimal("100") for _ in range(40)]

        result = calculate_rolling_adaptive(
            candles_from_closes(closes),
            mark_px=Decimal("100"),
            equity=Decimal("1"),
            ct_val=Decimal("1"),
            min_sz=Decimal("1"),
            limits=RollingAdaptiveLimits(),
        )

        self.assertFalse(result.tradeable_min_contract)
        self.assertGreater(result.min_contract_margin_pct, result.max_margin_pct)

    def test_bot_applies_rolling_result_before_sizing(self) -> None:
        config = make_config(
            rolling_adaptive_enabled=True,
            set_leverage=False,
            leverage=Decimal("5"),
            sizing_mode="fixed",
        )
        state = {
            "balance": {"totalEq": "100", "details": [{"ccy": "USDT", "availBal": "80", "eq": "100"}]},
            "meta": {"ctVal": "0.01", "minSz": "1"},
            "candles": candles_from_closes(
                [
                    Decimal("100"),
                    Decimal("102"),
                    Decimal("97"),
                    Decimal("104"),
                    Decimal("95"),
                    Decimal("106"),
                    Decimal("94"),
                    Decimal("108"),
                    Decimal("92"),
                    Decimal("110"),
                    Decimal("90"),
                    Decimal("112"),
                ]
            ),
        }

        with patch.object(auto_grid_bot, "log_event"), patch("builtins.print"):
            auto_grid_bot.apply_rolling_adaptive_config(object(), config, state, Decimal("112"))

        self.assertEqual(config.leverage, Decimal("1"))
        self.assertEqual(config.sizing_mode, "margin_pct")
        self.assertEqual(config.grid_bps, Decimal("80"))
        self.assertEqual(config.order_margin_pct, Decimal("3"))
        self.assertEqual(config.max_margin_pct, Decimal("12"))
        self.assertEqual(config.exchange_stop_bps, Decimal("900"))

    def test_live_rolling_adaptive_requires_leverage_sync(self) -> None:
        config = make_config(
            rolling_adaptive_enabled=True,
            set_leverage=False,
            live=True,
        )
        state = {
            "balance": {"totalEq": "100", "details": [{"ccy": "USDT", "availBal": "80", "eq": "100"}]},
            "meta": {"ctVal": "0.01", "minSz": "1"},
            "candles": candles_from_closes([Decimal("100") for _ in range(40)]),
        }

        with self.assertRaisesRegex(RuntimeError, "requires --set-leverage"):
            auto_grid_bot.apply_rolling_adaptive_config(object(), config, state, Decimal("100"))

    def test_live_rolling_adaptive_syncs_unsynced_leverage_after_runtime_reload(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.leverage_calls: list[dict] = []

            def set_leverage(self, **payload):
                self.leverage_calls.append(payload)
                return {"data": [payload]}

        config = make_config(
            rolling_adaptive_enabled=True,
            set_leverage=True,
            live=True,
            leverage=Decimal("7"),
            rolling_adaptive_last_leverage=Decimal("5"),
            rolling_adaptive_min_leverage=Decimal("3"),
            rolling_adaptive_max_leverage=Decimal("7"),
        )
        state = {
            "balance": {"totalEq": "100", "details": [{"ccy": "USDT", "availBal": "80", "eq": "100"}]},
            "meta": {"ctVal": "0.01", "minSz": "1"},
            "candles": candles_from_closes([Decimal("100") for _ in range(40)]),
        }
        client = FakeClient()

        with patch.object(auto_grid_bot, "log_event"), patch("builtins.print"):
            auto_grid_bot.apply_rolling_adaptive_config(client, config, state, Decimal("100"))

        self.assertEqual(config.leverage, Decimal("7"))
        self.assertEqual(config.rolling_adaptive_last_leverage, Decimal("7"))
        self.assertEqual([call["lever"] for call in client.leverage_calls], ["7", "7"])

    def test_runtime_config_without_inst_id_is_ignored_for_trading_fields(self) -> None:
        config = make_config(inst_id="ETH-USDT-SWAP", lower=Decimal("1500"))
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "runtime.json"
            runtime_path.write_text('{"lower":"1","upper":"2","leverage":"9"}', encoding="utf-8")
            with patch.object(auto_grid_bot, "RUNTIME_CONFIG_PATH", runtime_path), patch.object(
                auto_grid_bot, "log_event"
            ), patch("builtins.print"):
                auto_grid_bot.load_runtime_config(config)

        self.assertEqual(config.lower, Decimal("1500"))
        self.assertEqual(config.leverage, Decimal("5"))

    def test_runtime_config_for_other_inst_id_is_ignored(self) -> None:
        config = make_config(inst_id="ETH-USDT-SWAP", lower=Decimal("1500"))
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "runtime.json"
            runtime_path.write_text('{"instId":"BEAT-USDT-SWAP","lower":"1","upper":"2"}', encoding="utf-8")
            with patch.object(auto_grid_bot, "RUNTIME_CONFIG_PATH", runtime_path), patch.object(
                auto_grid_bot, "log_event"
            ), patch("builtins.print"):
                auto_grid_bot.load_runtime_config(config)

        self.assertEqual(config.lower, Decimal("1500"))

    def test_shutdown_handler_cancels_only_bot_open_orders(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.cancelled: list[dict] = []

            def get_pending_orders(self, _inst_id: str) -> dict:
                return {
                    "data": [
                        {"ordId": "open", "clOrdId": "tetho123", "reduceOnly": "false"},
                        {"ordId": "tp", "clOrdId": "tethc123", "reduceOnly": "true"},
                        {"ordId": "other", "clOrdId": "other123", "reduceOnly": "false"},
                    ]
                }

            def cancel_orders(self, payload: list[dict]) -> dict:
                self.cancelled.extend(payload)
                return {"data": payload}

        config = make_config(inst_id="ETH-USDT-SWAP", live=True, cancel_on_stop=True)
        client = FakeClient()
        with patch.object(auto_grid_bot, "BOT_PREFIX", "teth"), patch.object(auto_grid_bot, "log_event"), patch(
            "builtins.print"
        ):
            auto_grid_bot.install_shutdown_handlers(client, config)
            with self.assertRaises(SystemExit):
                auto_grid_bot.signal.raise_signal(auto_grid_bot.signal.SIGTERM)

        self.assertEqual(len(client.cancelled), 1)
        self.assertEqual(client.cancelled[0]["ordId"], "open")


if __name__ == "__main__":
    unittest.main()
