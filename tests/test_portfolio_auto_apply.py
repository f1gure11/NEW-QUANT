from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import portfolio_auto_apply
from portfolio_auto_apply import BotProcess, build_apply_plan, hot_update_runtime, live_command_from_dry_run, run


class PortfolioAutoApplyTest(unittest.TestCase):
    def test_build_apply_plan_hot_updates_running_targets_and_starts_missing(self) -> None:
        runtime_intents = {
            "AAA-USDT-SWAP": {"runtime_config_path": "reports/portfolio/new/runtime_configs/aaa.json"},
            "BBB-USDT-SWAP": {"runtime_config_path": "reports/portfolio/new/runtime_configs/bbb.json"},
        }
        processes = {
            "AAA-USDT-SWAP": BotProcess(
                inst_id="AAA-USDT-SWAP",
                pid=123,
                runtime_path=Path("reports/portfolio/old/runtime_configs/aaa.json"),
                command=[],
            )
        }

        plan = build_apply_plan(
            report_dir=Path("reports/portfolio/new"),
            runtime_intents=runtime_intents,
            reduce_intents={},
            actions={"AAA-USDT-SWAP": "hold", "BBB-USDT-SWAP": "enter"},
            processes=processes,
        )

        self.assertEqual(plan.hot_update_insts, ["AAA-USDT-SWAP"])
        self.assertEqual(plan.start_insts, ["BBB-USDT-SWAP"])
        self.assertEqual(plan.stop_insts, [])

    def test_build_apply_plan_stops_and_restarts_decrease_target(self) -> None:
        runtime_intents = {"AAA-USDT-SWAP": {"runtime_config_path": "new.json"}}
        reduce_intents = {"AAA-USDT-SWAP": {"dry_run_command": "reduce"}}
        processes = {
            "AAA-USDT-SWAP": BotProcess(
                inst_id="AAA-USDT-SWAP",
                pid=123,
                runtime_path=Path("reports/portfolio/old/runtime_configs/aaa.json"),
                command=[],
            )
        }

        plan = build_apply_plan(
            report_dir=Path("reports/portfolio/new"),
            runtime_intents=runtime_intents,
            reduce_intents=reduce_intents,
            actions={"AAA-USDT-SWAP": "decrease"},
            processes=processes,
        )

        self.assertEqual(plan.stop_insts, ["AAA-USDT-SWAP"])
        self.assertEqual(plan.reduce_insts, ["AAA-USDT-SWAP"])
        self.assertEqual(plan.start_insts, ["AAA-USDT-SWAP"])
        self.assertEqual(plan.hot_update_insts, [])

    def test_build_apply_plan_stops_running_bot_that_is_no_longer_target_even_without_reduce(self) -> None:
        processes = {
            "AAA-USDT-SWAP": BotProcess(
                inst_id="AAA-USDT-SWAP",
                pid=123,
                runtime_path=Path("reports/portfolio/old/runtime_configs/aaa.json"),
                command=[],
            ),
            "OLD-USDT-SWAP": BotProcess(
                inst_id="OLD-USDT-SWAP",
                pid=124,
                runtime_path=Path("reports/portfolio/old/runtime_configs/old.json"),
                command=[],
            ),
        }

        plan = build_apply_plan(
            report_dir=Path("reports/portfolio/new"),
            runtime_intents={"AAA-USDT-SWAP": {"runtime_config_path": "new.json"}},
            reduce_intents={},
            actions={"AAA-USDT-SWAP": "hold"},
            processes=processes,
        )

        self.assertEqual(plan.stop_insts, ["OLD-USDT-SWAP"])
        self.assertEqual(plan.hot_update_insts, ["AAA-USDT-SWAP"])
        self.assertEqual(plan.start_insts, [])

    def test_build_apply_plan_limits_trade_changes(self) -> None:
        plan = build_apply_plan(
            report_dir=Path("reports/portfolio/new"),
            runtime_intents={"AAA-USDT-SWAP": {}, "BBB-USDT-SWAP": {}},
            reduce_intents={"OLD-USDT-SWAP": {}},
            actions={"AAA-USDT-SWAP": "enter", "BBB-USDT-SWAP": "enter", "OLD-USDT-SWAP": "exit"},
            processes={
                "OLD-USDT-SWAP": BotProcess("OLD-USDT-SWAP", 1, Path("reports/portfolio/old/runtime_configs/old.json"), []),
            },
            max_changes=2,
        )

        self.assertEqual(plan.stop_insts, ["OLD-USDT-SWAP"])
        self.assertEqual(plan.reduce_insts, ["OLD-USDT-SWAP"])
        self.assertEqual(plan.start_insts, ["AAA-USDT-SWAP"])
        self.assertEqual(plan.skipped_insts, ["BBB-USDT-SWAP"])

    def test_hot_update_runtime_copies_new_payload_to_running_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "new.json"
            dest = root / "old.json"
            source.write_text(json.dumps({"instId": "AAA-USDT-SWAP", "interval": "8"}), encoding="utf-8")
            dest.write_text(json.dumps({"instId": "AAA-USDT-SWAP", "interval": "2"}), encoding="utf-8")
            process = BotProcess("AAA-USDT-SWAP", 123, dest, [])

            with patch.object(portfolio_auto_apply, "LOG_PATH", root / "actions.jsonl"), patch("builtins.print"):
                result = hot_update_runtime(root, process, {"runtime_config_path": str(source)})
            saved = json.loads(dest.read_text(encoding="utf-8"))

        self.assertEqual(result["instId"], "AAA-USDT-SWAP")
        self.assertEqual(saved["interval"], "8")
        self.assertEqual(saved["autoAppliedFromReport"], str(root))

    def test_live_command_from_dry_run_reuses_report_reduce_command(self) -> None:
        command = live_command_from_dry_run(
            "PYTHONPATH=. .venv/bin/python portfolio_rebalancer.py --report-dir reports/portfolio/x "
            "--inst-id OLD-USDT-SWAP --ord-type limit --slippage-bps 12 --once"
        )

        self.assertEqual(command[1], "portfolio_rebalancer.py")
        self.assertIn("--ord-type", command)
        self.assertIn("limit", command)
        self.assertIn("--slippage-bps", command)
        self.assertIn("12", command)
        self.assertIn("--live", command)
        self.assertIn("--confirm-live", command)

    def test_run_blocks_empty_target_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = root / "report"
            report.mkdir()
            (report / "execution_intents.json").write_text(
                json.dumps({"intents": [{"inst_id": "OLD-USDT-SWAP", "status": "rebalance_reduce_ready"}]}),
                encoding="utf-8",
            )
            (report / "rebalance_plan.json").write_text(
                json.dumps({"actions": [{"inst_id": "OLD-USDT-SWAP", "action": "exit"}]}),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "report_dir": str(report),
                    "force": True,
                    "confirm_live": "",
                    "dry_run": True,
                    "max_changes": 0,
                    "dashboard_url": "http://127.0.0.1:8765",
                    "allow_blocked_start": False,
                    "stop_timeout": 1,
                    "post_reduce_delay": 0,
                },
            )()

            with patch.object(portfolio_auto_apply, "LOG_PATH", root / "actions.jsonl"), patch.object(
                portfolio_auto_apply,
                "STATE_PATH",
                root / "state.json",
            ), patch("builtins.print"):
                with self.assertRaises(RuntimeError):
                    run(args)


if __name__ == "__main__":
    unittest.main()
