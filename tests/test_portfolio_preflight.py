from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from portfolio_preflight import (
    BLOCK,
    PASS,
    account_equity,
    check_intent,
    check_min_contract_capacity,
    run_preflight,
    write_preflight_report,
)


def write_bundle(path: Path, *, command: str | None = None, inst_id: str = "AAA-USDT-SWAP") -> None:
    runtime_dir = path / "runtime_configs"
    runtime_dir.mkdir(parents=True)
    runtime_path = runtime_dir / "aaa_usdt_swap.json"
    runtime_path.write_text(
        json.dumps(
            {
                "instId": inst_id,
                "lower": "95",
                "upper": "105",
                "orderSz": "1",
                "maxPosition": "3",
                "leverage": "3",
                "portfolioGenerated": True,
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "intents": [
            {
                "inst_id": "AAA-USDT-SWAP",
                "action": "enter",
                "status": "runtime_config_ready",
                "runtime_config_path": str(runtime_path),
                "dry_run_command": command
                or f"PYTHONPATH=. .venv/bin/python auto_grid_bot.py --inst-id AAA-USDT-SWAP --runtime-config {runtime_path} --once",
            }
        ]
    }
    (path / "execution_intents.json").write_text(json.dumps(payload), encoding="utf-8")


class PortfolioPreflightTest(unittest.TestCase):
    def test_valid_local_bundle_passes_without_account_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir)
            with patch("portfolio_preflight.list_bot_processes", return_value=[]):
                checks = run_preflight(report_dir, include_account=False)

        severities = {check.code: check.severity for check in checks}
        self.assertEqual(severities["no_live_flag"], PASS)
        self.assertEqual(severities["once_flag_present"], PASS)
        self.assertEqual(severities["runtime_config_inst_match"], PASS)
        self.assertEqual(severities["account_check_skipped"], "warn")
        self.assertNotIn(BLOCK, {check.severity for check in checks})

    def test_live_flag_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir, command="auto_grid_bot.py --inst-id AAA-USDT-SWAP --once --live")
            with patch("portfolio_preflight.list_bot_processes", return_value=[]):
                checks = run_preflight(report_dir, include_account=False)

        self.assertIn("live_flag_present", [check.code for check in checks if check.severity == BLOCK])

    def test_missing_once_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir, command="auto_grid_bot.py --inst-id AAA-USDT-SWAP")
            with patch("portfolio_preflight.list_bot_processes", return_value=[]):
                checks = run_preflight(report_dir, include_account=False)

        self.assertIn("once_flag_missing", [check.code for check in checks if check.severity == BLOCK])

    def test_runtime_inst_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir, inst_id="BBB-USDT-SWAP")
            with patch("portfolio_preflight.list_bot_processes", return_value=[]):
                checks = run_preflight(report_dir, include_account=False)

        self.assertIn("runtime_config_inst_mismatch", [check.code for check in checks if check.severity == BLOCK])

    def test_manual_reduce_blocks(self) -> None:
        checks = check_intent(
            {"inst_id": "OLD-USDT-SWAP", "status": "manual_review_reduce", "action": "exit"},
            [],
        )

        self.assertEqual(checks[0].code, "manual_reduce_required")
        self.assertEqual(checks[0].severity, BLOCK)

    def test_reduce_rebalancer_intent_warns_but_passes_dry_run_shape(self) -> None:
        checks = check_intent(
            {
                "inst_id": "OLD-USDT-SWAP",
                "status": "rebalance_reduce_ready",
                "action": "exit",
                "dry_run_command": "PYTHONPATH=. .venv/bin/python portfolio_rebalancer.py --inst-id OLD-USDT-SWAP --once",
            },
            [],
        )

        severities = {check.code: check.severity for check in checks}
        self.assertEqual(severities["no_live_flag"], PASS)
        self.assertEqual(severities["once_flag_present"], PASS)
        self.assertEqual(severities["reduce_only_rebalance"], "warn")

    def test_write_preflight_report_outputs_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir)
            with patch("portfolio_preflight.list_bot_processes", return_value=[]):
                checks = run_preflight(report_dir, include_account=False)
            path = write_preflight_report(report_dir, checks, include_account=False)

            self.assertTrue(path.exists())
            self.assertTrue((report_dir / "preflight_report.md").exists())

    def test_min_contract_capacity_warns_when_runtime_will_size_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir)
            runtime_path = next((report_dir / "runtime_configs").glob("*.json"))
            payload = json.loads(runtime_path.read_text(encoding="utf-8"))
            payload.update({"leverage": "3", "maxMarginPct": "24"})
            runtime_path.write_text(json.dumps(payload), encoding="utf-8")

            checks = check_min_contract_capacity(
                {"inst_id": "AAA-USDT-SWAP", "runtime_config_path": str(runtime_path)},
                {"last": "63", "ct_val": "0.1", "min_sz": "1"},
                account_equity({"data": [{"totalEq": "6.4", "details": [{"ccy": "USDT", "eq": "6.4"}]}]}),
            )

        self.assertEqual(checks[0].code, "min_contract_exceeds_margin_cap")
        self.assertEqual(checks[0].severity, "warn")

    def test_min_contract_capacity_passes_when_runtime_can_trade_one_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            write_bundle(report_dir)
            runtime_path = next((report_dir / "runtime_configs").glob("*.json"))
            payload = json.loads(runtime_path.read_text(encoding="utf-8"))
            payload["maxMarginPct"] = "35"
            runtime_path.write_text(json.dumps(payload), encoding="utf-8")

            checks = check_min_contract_capacity(
                {"inst_id": "AAA-USDT-SWAP", "runtime_config_path": str(runtime_path)},
                {"last": "100", "ct_val": "0.01", "min_sz": "1"},
                account_equity({"data": [{"totalEq": "100", "details": [{"ccy": "USDT", "eq": "100"}]}]}),
            )

        self.assertEqual(checks[0].code, "min_contract_within_margin_cap")
        self.assertEqual(checks[0].severity, PASS)


if __name__ == "__main__":
    unittest.main()
