from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from portfolio_live_plan import build_live_plan_items, live_command_from_dry_run, write_live_plan


def write_report(report_dir: Path, *, preflight_status: str = "pass", include_account: bool = True, trading_mode: str = "live") -> None:
    runtime_dir = report_dir / "runtime_configs"
    runtime_dir.mkdir(parents=True)
    runtime_path = runtime_dir / "aaa_usdt_swap.json"
    runtime_path.write_text('{"instId":"AAA-USDT-SWAP"}', encoding="utf-8")
    (report_dir / "rebalance_plan.json").write_text(
        json.dumps({"tradingMode": trading_mode, "actions": [{"inst_id": "AAA-USDT-SWAP", "action": "enter"}]}),
        encoding="utf-8",
    )
    (report_dir / "execution_intents.json").write_text(
        json.dumps(
            {
                "intents": [
                    {
                        "inst_id": "AAA-USDT-SWAP",
                        "status": "runtime_config_ready",
                        "runtime_config_path": str(runtime_path),
                        "dry_run_command": f"PYTHONPATH=. .venv/bin/python auto_grid_bot.py --inst-id AAA-USDT-SWAP --runtime-config {runtime_path} --once",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (report_dir / "preflight_report.json").write_text(
        json.dumps({"status": preflight_status, "includeAccount": include_account, "checks": []}),
        encoding="utf-8",
    )


class PortfolioLivePlanTest(unittest.TestCase):
    def test_live_command_removes_once_and_adds_live_confirmation(self) -> None:
        command = live_command_from_dry_run("PYTHONPATH=. .venv/bin/python auto_grid_bot.py --once")

        self.assertNotIn("--once", command)
        self.assertIn("--live", command)
        self.assertIn("--confirm-live I_UNDERSTAND", command)

    def test_build_live_plan_blocks_without_account_preflight(self) -> None:
        items = build_live_plan_items(Path("/tmp/missing"), [], {"status": "pass", "includeAccount": False})

        self.assertEqual(items[0].status, "blocked")

    def test_write_live_plan_outputs_ready_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_report(report_dir)
            items = write_live_plan(report_dir)

            self.assertEqual(items[0].status, "ready")
            self.assertTrue((report_dir / "live_plan.json").exists())
            self.assertTrue((report_dir / "live_plan.csv").exists())
            self.assertTrue((report_dir / "live_plan.md").exists())
            self.assertTrue(Path(items[0].systemd_draft_path).exists())

    def test_write_live_plan_blocks_failed_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_report(report_dir, preflight_status="blocked")
            items = write_live_plan(report_dir)

            self.assertEqual(items[0].status, "blocked")

    def test_write_live_plan_allows_unblocked_targets_when_other_target_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_report(report_dir)
            runtime_dir = report_dir / "runtime_configs"
            blocked_runtime = runtime_dir / "bbb_usdt_swap.json"
            blocked_runtime.write_text('{"instId":"BBB-USDT-SWAP"}', encoding="utf-8")
            execution = json.loads((report_dir / "execution_intents.json").read_text(encoding="utf-8"))
            execution["intents"].append(
                {
                    "inst_id": "BBB-USDT-SWAP",
                    "status": "runtime_config_ready",
                    "runtime_config_path": str(blocked_runtime),
                    "dry_run_command": f"PYTHONPATH=. .venv/bin/python auto_grid_bot.py --inst-id BBB-USDT-SWAP --runtime-config {blocked_runtime} --once",
                }
            )
            (report_dir / "execution_intents.json").write_text(json.dumps(execution), encoding="utf-8")
            (report_dir / "preflight_report.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "includeAccount": True,
                        "checks": [
                            {"severity": "pass", "code": "no_pending_orders", "inst_id": "AAA-USDT-SWAP", "message": ""},
                            {"severity": "block", "code": "pending_algo_orders_exist", "inst_id": "BBB-USDT-SWAP", "message": "Pending conditional algo orders exist."},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            items = write_live_plan(report_dir)
            live_plan = json.loads((report_dir / "live_plan.json").read_text(encoding="utf-8"))

        self.assertEqual([item.status for item in items], ["ready", "blocked"])
        self.assertIn("pending_algo_orders_exist", items[1].note)
        self.assertEqual(live_plan["status"], "partial")

    def test_write_live_plan_can_explicitly_allow_blocked_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_report(report_dir, preflight_status="blocked")
            items = write_live_plan(report_dir, allow_blocked_preflight=True)

            self.assertEqual(items[0].status, "ready")
            self.assertIn("explicitly allowed", items[0].note)

    def test_write_live_plan_blocks_paper_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_report(report_dir, trading_mode="paper")
            items = write_live_plan(report_dir)

            self.assertEqual(items[0].status, "blocked")
            self.assertIn("tradingMode must be live", items[0].note)

    def test_reduce_intent_is_review_only_and_does_not_block_ready_bot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_report(report_dir)
            payload = json.loads((report_dir / "execution_intents.json").read_text(encoding="utf-8"))
            payload["intents"].append(
                {
                    "inst_id": "OLD-USDT-SWAP",
                    "action": "exit",
                    "status": "rebalance_reduce_ready",
                    "dry_run_command": "PYTHONPATH=. .venv/bin/python portfolio_rebalancer.py --inst-id OLD-USDT-SWAP --once",
                }
            )
            (report_dir / "execution_intents.json").write_text(json.dumps(payload), encoding="utf-8")

            items = write_live_plan(report_dir)
            live_plan = json.loads((report_dir / "live_plan.json").read_text(encoding="utf-8"))

        self.assertEqual([item.status for item in items], ["ready", "review_only"])
        self.assertEqual(live_plan["status"], "ready")


if __name__ == "__main__":
    unittest.main()
