from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_server


class DashboardRuntimeConfigTest(unittest.TestCase):
    def test_read_bot_runtime_config_defaults_missing_inst_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "runtime.json"
            runtime_path.write_text('{"lower":"1","cashReservePct":"15"}', encoding="utf-8")

            with patch.object(dashboard_server, "BOT_RUNTIME_CONFIG", runtime_path):
                payload = dashboard_server.read_bot_runtime_config()

        self.assertEqual(payload["instId"], "BEAT-USDT-SWAP")
        self.assertEqual(payload["cashReservePct"], "15")

    def test_write_bot_runtime_config_persists_inst_id_and_cash_reserve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "runtime.json"
            with patch.object(dashboard_server, "BOT_RUNTIME_CONFIG", runtime_path):
                payload = dashboard_server.write_bot_runtime_config(
                    {
                        "instId": "BEAT-USDT-SWAP",
                        "lower": "1.7",
                        "cashReservePct": "20",
                    }
                )
                saved = json.loads(runtime_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["instId"], "BEAT-USDT-SWAP")
        self.assertEqual(saved["instId"], "BEAT-USDT-SWAP")
        self.assertEqual(saved["cashReservePct"], "20")

    def test_build_grid_bot_args_includes_cash_reserve_pct(self) -> None:
        args = dashboard_server.build_grid_bot_args(
            {
                "instId": "BEAT-USDT-SWAP",
                "lower": "1.7",
                "upper": "1.9",
                "cashReservePct": "25",
            },
            runtime_config_path=Path("/tmp/runtime.json"),
            action_log_path=Path("/tmp/actions.jsonl"),
            bot_prefix="gb",
            once=True,
            live=False,
        )

        index = args.index("--cash-reserve-pct")
        self.assertEqual(args[index + 1], "25")

    def test_parse_bot_diagnostics_extracts_rolling_adaptive(self) -> None:
        diagnostics = dashboard_server.parse_bot_diagnostics(
            [
                "rolling_adaptive leverage=4x grid=18.8bps order_margin=14.8% max_margin=66.2% tp=30.1bps sl=700bps rolling window=20 avg_abs=14.3bps shock=56.4bps trend=-74.1bps risk=0.718 min_contract_margin=0.39",
                "sizing order_sz=0 max_position=0 margin_pct basis=0.30 min_margin=0.39 reserve_margin=0.63",
                "[12:00:00] mark=100 last=100 range=95-105 step=0.5 state=inside long=0 short=0",
            ],
            True,
        )

        self.assertEqual(diagnostics["rollingAdaptive"]["leverage"], "4")
        self.assertEqual(diagnostics["rollingAdaptive"]["gridBps"], "18.8")
        self.assertEqual(diagnostics["rollingAdaptive"]["riskScore"], "0.718")
        self.assertEqual(diagnostics["sizing"]["orderSz"], "0")
        self.assertIn("basis=0.30", diagnostics["sizing"]["note"])
        self.assertEqual(diagnostics["sizing"]["basis"], "0.30")

    def test_parse_bot_diagnostics_extracts_edge(self) -> None:
        diagnostics = dashboard_server.parse_bot_diagnostics(
            [
                "[12:00:00] mark=100 last=100 range=95-105 step=0.5 state=inside long=0 short=0",
                "edge gross=8.11bps net_est=1.11bps min_net=1bps fees=open 2bps close 5bps",
            ],
            True,
        )

        self.assertEqual(diagnostics["edge"]["grossBps"], "8.11")
        self.assertEqual(diagnostics["edge"]["netEstBps"], "1.11")
        self.assertEqual(diagnostics["edge"]["minNetBps"], "1")

    def test_build_portfolio_backtest_args_includes_trading_mode(self) -> None:
        args = dashboard_server.build_portfolio_backtest_args({"tradingMode": "live"})

        index = args.index("--trading-mode")
        self.assertEqual(args[index + 1], "live")
        trend_index = args.index("--trend-filter")
        self.assertEqual(args[trend_index + 1], "compare")

    def test_parse_portfolio_backtest_log_detects_completed_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "portfolio_backtest_stdout.log"
            log_path.write_text(
                "\n--- portfolio backtest start 2026-06-24T22:22:34+00:00 ---\n"
                "command=/venv/bin/python /opt/okx-quant/portfolio_backtest.py --backtest-limit 300\n"
                "portfolio_report=/opt/okx-quant/reports/portfolio/20260624T222240Z\n",
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "PORTFOLIO_BACKTEST_LOG", log_path):
                payload = dashboard_server.parse_portfolio_backtest_log()

        self.assertEqual(payload["state"], "completed")
        self.assertEqual(payload["returnCode"], 0)
        self.assertEqual(payload["startedAt"], "2026-06-24T22:22:34+00:00")
        self.assertTrue(payload["reportPath"].endswith("20260624T222240Z"))

    def test_compute_account_pnl_includes_recent_windows(self) -> None:
        now_ms = int(dashboard_server.datetime.now(dashboard_server.timezone.utc).timestamp() * 1000)
        fills = [
            {"fillTime": str(now_ms), "fillPnl": "1", "fee": "-0.1"},
            {"fillTime": str(now_ms - 6 * 60 * 60 * 1000), "fillPnl": "2", "fee": "-0.2"},
            {"fillTime": str(now_ms - 25 * 60 * 60 * 1000), "fillPnl": "3", "fee": "-0.3"},
        ]
        positions = [{"upl": "0.5", "posSide": "long"}]
        pnl = dashboard_server.compute_account_pnl(positions, fills)

        self.assertEqual(pnl["estimatedTotal"], "5.9")
        self.assertEqual(pnl["recent5h"], "0.9")
        self.assertEqual(pnl["recent5hFillCount"], 1)
        self.assertEqual(pnl["recent24h"], "2.7")
        self.assertEqual(pnl["recent24hFillCount"], 2)

    def test_require_portfolio_live_report_blocks_paper_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            (report_dir / "rebalance_plan.json").write_text(json.dumps({"tradingMode": "paper"}), encoding="utf-8")
            (report_dir / "execution_intents.json").write_text(
                json.dumps({"execution": {"trading_mode": "paper"}}),
                encoding="utf-8",
            )

            with self.assertRaises(PermissionError):
                dashboard_server.require_portfolio_live_report(report_dir)

    def test_require_portfolio_live_report_allows_live_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_dir = Path(tmpdir)
            (report_dir / "rebalance_plan.json").write_text(json.dumps({"tradingMode": "live"}), encoding="utf-8")
            (report_dir / "execution_intents.json").write_text(
                json.dumps({"execution": {"trading_mode": "live"}}),
                encoding="utf-8",
            )

            dashboard_server.require_portfolio_live_report(report_dir)

    def test_portfolio_bot_status_finds_running_process_by_inst_id_when_runtime_path_changed(self) -> None:
        intent = {
            "inst_id": "AAA-USDT-SWAP",
            "runtime_config_path": "/tmp/reports/portfolio/new/runtime_configs/aaa.json",
            "stdout_log_path": "/tmp/missing.log",
        }

        with patch.object(dashboard_server, "find_process_pid", side_effect=[None, 123]), patch.object(
            dashboard_server,
            "process_command",
            return_value="/venv/bin/python auto_grid_bot.py --inst-id AAA-USDT-SWAP --runtime-config reports/portfolio/old/runtime_configs/aaa.json",
        ), patch.object(dashboard_server, "read_json_file", return_value={"instId": "AAA-USDT-SWAP"}):
            status = dashboard_server.portfolio_bot_status_for_intent(intent)

        self.assertTrue(status["running"])
        self.assertEqual(status["pid"], 123)

    def test_command_parts_match_hints_requires_python_script_arg(self) -> None:
        actual_bot = [
            "/venv/bin/python",
            "auto_grid_bot.py",
            "--inst-id",
            "AAA-USDT-SWAP",
        ]
        checker_script = [
            "/bin/bash",
            "-lc",
            "print('auto_grid_bot.py --inst-id AAA-USDT-SWAP')",
        ]

        self.assertTrue(dashboard_server.command_parts_match_hints(actual_bot, ["auto_grid_bot.py", "AAA-USDT-SWAP"]))
        self.assertFalse(
            dashboard_server.command_parts_match_hints(checker_script, ["auto_grid_bot.py", "AAA-USDT-SWAP"])
        )

    def test_latest_portfolio_report_payload_summarizes_satellites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_root = Path(tmpdir) / "reports"
            report_dir = report_root / "20260624T000000Z"
            runtime_dir = report_dir / "runtime_configs"
            runtime_dir.mkdir(parents=True)
            (report_dir / "candidates.json").write_text('{"generatedAt":"now","candidateCount":2}', encoding="utf-8")
            (report_dir / "scores.csv").write_text(
                "rank,status,inst_id,total_return_pct,max_drawdown_pct,profit_factor,fills,win_rate_pct,risk_events\n"
                "1,ok,AAA-USDT-SWAP,2,1,1.5,4,75,0\n",
                encoding="utf-8",
            )
            (report_dir / "rebalance_plan.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "now",
                        "tradingMode": "paper",
                        "targets": [
                            {"inst_id": "AAA-USDT-SWAP", "role": "core", "weight_pct": "40"},
                            {"inst_id": "BBB-USDT-SWAP", "role": "satellite", "weight_pct": "8"},
                        ],
                        "currentExposures": [{"inst_id": "AAA-USDT-SWAP", "margin_estimate": "4", "gross_notional": "12"}],
                        "actions": [{"inst_id": "BBB-USDT-SWAP", "action": "enter"}],
                    }
                ),
                encoding="utf-8",
            )
            (report_dir / "execution_intents.json").write_text(
                json.dumps({"intents": [{"inst_id": "BBB-USDT-SWAP", "status": "runtime_config_ready"}]}),
                encoding="utf-8",
            )
            (runtime_dir / "bbb.json").write_text(
                json.dumps({"instId": "BBB-USDT-SWAP", "leverage": "3", "gridBps": "24", "poolAdaptiveRiskScore": "0.2"}),
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "PORTFOLIO_REPORT_DIR", report_root), patch.object(
                dashboard_server,
                "portfolio_live_status",
                return_value={
                    "enabled": False,
                    "mode": "locked",
                    "runningCount": 0,
                    "targetCount": 1,
                    "pnl": {"estimatedTotal": "0", "recent5h": "0", "recent5hFillCount": 0},
                },
            ):
                payload = dashboard_server.latest_portfolio_report_payload()

        self.assertIsNotNone(payload)
        self.assertEqual(payload["summary"]["satelliteCount"], 1)
        self.assertEqual(payload["summary"]["satelliteWeightPct"], "8")
        self.assertEqual(payload["summary"]["executionReadyCount"], 1)
        self.assertEqual(payload["summary"]["currentExposureCount"], 1)
        self.assertEqual(payload["summary"]["currentMarginPct"], "4")
        self.assertEqual(payload["summary"]["tradingMode"], "paper")
        action = payload["rebalance"]["actions"][0]
        self.assertEqual(action["generated_at"], "now")
        self.assertIn("目标组合新增", action["reason"])

    def test_latest_regime_research_payload_summarizes_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_root = Path(tmpdir) / "regime_model"
            report_dir = report_root / "20260625T000000Z"
            report_dir.mkdir(parents=True)
            (report_dir / "scores.csv").write_text(
                "rank,variant,inst_id,score,total_return_pct,max_drawdown_pct,profit_factor,fills,risk_events,bars,latest_signal,latest_confidence,latest_allowed_sides,model_path,error\n"
                "1,baseline,AAA-USDT-SWAP,-10,-2,4,1,10,3,100,off,1,,,\n"
                "1,rf,AAA-USDT-SWAP,2,1,1,2,4,0,100,range,0.9,\"long,short\",model.joblib,\n"
                "2,rf,BBB-USDT-SWAP,-1,-1,2,1,3,1,100,mixed,0.4,,model.joblib,\n",
                encoding="utf-8",
            )
            (report_dir / "model_metrics.json").write_text(
                json.dumps({"generatedAt": "now", "rf": {"samples": 100, "accuracy": 0.6}, "hmm": {"samples": 90, "accuracy_vs_weak_labels": 0.5}}),
                encoding="utf-8",
            )

            with patch.object(dashboard_server, "REGIME_REPORT_DIR", report_root):
                payload = dashboard_server.latest_regime_research_payload()

        self.assertIsNotNone(payload)
        self.assertEqual(payload["bestVariant"]["variant"], "rf")
        self.assertEqual(payload["bestVariant"]["totalRiskEvents"], 1)
        self.assertEqual(payload["bestVariant"]["riskEventDeltaVsBaseline"], -2)
        self.assertEqual(payload["models"]["rf"]["samples"], 100)
        self.assertEqual(payload["quantDinger"]["license"], "Apache-2.0")


if __name__ == "__main__":
    unittest.main()
