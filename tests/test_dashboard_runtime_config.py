from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
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
            with patch.object(dashboard_server, "BOT_RUNTIME_CONFIG", runtime_path), patch.dict(
                dashboard_server.os.environ,
                {"OKX_ENABLE_LEGACY_BOTS": "1"},
                clear=False,
            ):
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

    def test_legacy_bot_config_writes_are_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "runtime.json"
            with patch.object(dashboard_server, "BOT_RUNTIME_CONFIG", runtime_path), patch.dict(
                dashboard_server.os.environ,
                {"OKX_ENABLE_LEGACY_BOTS": "0"},
                clear=False,
            ):
                with self.assertRaises(PermissionError):
                    dashboard_server.write_bot_runtime_config({"instId": "BEAT-USDT-SWAP"})

    def test_legacy_bot_config_writes_can_be_enabled_for_maintenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_path = Path(tmpdir) / "runtime.json"
            with patch.object(dashboard_server, "BOT_RUNTIME_CONFIG", runtime_path), patch.dict(
                dashboard_server.os.environ,
                {"OKX_ENABLE_LEGACY_BOTS": "1"},
                clear=False,
            ):
                payload = dashboard_server.write_bot_runtime_config({"instId": "BEAT-USDT-SWAP", "lower": "1.7"})

        self.assertEqual(payload["instId"], "BEAT-USDT-SWAP")
        self.assertEqual(payload["lower"], "1.7")

    def test_is_live_enabled_loads_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("OKX_ENABLE_LIVE_TRADING=1\n", encoding="utf-8")
            with patch.object(dashboard_server, "load_env", side_effect=lambda: dashboard_server.os.environ.update({"OKX_ENABLE_LIVE_TRADING": "1"})), patch.dict(
                dashboard_server.os.environ,
                {},
                clear=True,
            ):
                enabled = dashboard_server.is_live_enabled()

        self.assertTrue(enabled)

    def test_console_unprefixed_path_supports_reverse_proxy_prefix(self) -> None:
        self.assertEqual(dashboard_server.console_unprefixed_path("/console"), "/")
        self.assertEqual(dashboard_server.console_unprefixed_path("/console/"), "/")
        self.assertEqual(dashboard_server.console_unprefixed_path("/console/api/portfolio/latest"), "/api/portfolio/latest")
        self.assertEqual(dashboard_server.console_unprefixed_path("/api/portfolio/latest"), "/api/portfolio/latest")

    def test_dashboard_systemd_unit_kills_portfolio_children_on_restart(self) -> None:
        unit = Path("deploy/systemd/okx-dashboard.service").read_text(encoding="utf-8")

        self.assertIn("KillMode=control-group", unit)
        self.assertNotIn("KillMode=process", unit)

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

    def test_parse_bot_diagnostics_ignores_previous_start_errors(self) -> None:
        diagnostics = dashboard_server.parse_bot_diagnostics(
            [
                "--- portfolio live bot start 2026-06-25T15:53:00+00:00 DOGE-USDT-SWAP ---",
                "[15:59:00] mark=1 last=1 range=0.9-1.1 step=0.01 state=inside long=0 short=0",
                "Bot error: old failure",
                "Received SIGTERM: shutting down.",
                "--- portfolio live bot start 2026-06-25T16:08:00+00:00 DOGE-USDT-SWAP ---",
                "[16:08:03] mark=1 last=1 range=0.9-1.1 step=0.01 state=inside long=0 short=0",
                "open_guard sides=short trend=flat change=1bps regime=off maDiff=0bps note=market-regime rf state=trend_down",
                "desired=5 existing_bot=0 matched=0 missing=3 stale=0 open_px_tolerance=0.001 preserve_valid_open=true",
                "LIVE place open sell short 0.04 @ 1.01 -> ok",
            ],
            True,
        )

        self.assertIsNone(diagnostics["lastError"])
        self.assertEqual(diagnostics["summary"]["level"], "ok")
        self.assertEqual(diagnostics["orderPlan"]["missing"], 3)
        self.assertEqual(len(diagnostics["actions"]), 1)

    def test_tail_lines_reads_only_recent_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "large.log"
            log_path.write_text("\n".join(f"line-{idx}" for idx in range(5000)), encoding="utf-8")
            with patch.object(dashboard_server, "TAIL_READ_BYTES", 2048):
                lines = dashboard_server.tail_lines(log_path, 5)

        self.assertEqual(lines, ["line-4995", "line-4996", "line-4997", "line-4998", "line-4999"])

    def test_portfolio_status_is_lightweight_by_default(self) -> None:
        with patch.object(dashboard_server, "portfolio_account_summary", side_effect=AssertionError("account should be skipped")), patch.object(
            dashboard_server,
            "portfolio_live_status",
            return_value={"enabled": False, "pnl": {"estimatedTotal": "0"}, "bots": []},
        ), patch.object(dashboard_server, "latest_portfolio_report_payload", return_value=None), patch.object(
            dashboard_server,
            "latest_regime_research_payload",
            side_effect=AssertionError("regime research should be skipped"),
        ):
            payload = dashboard_server.portfolio_status()

        self.assertTrue(payload["account"]["skipped"])
        self.assertIsNone(payload["regimeResearch"])

    def test_build_portfolio_backtest_args_includes_trading_mode(self) -> None:
        args = dashboard_server.build_portfolio_backtest_args(
            {
                "tradingMode": "live",
                "topN": "999",
                "targetSymbols": "999",
                "backtestPages": "99",
                "allocationMaxRiskEvents": "99",
            }
        )

        index = args.index("--trading-mode")
        self.assertEqual(args[index + 1], "live")
        trend_index = args.index("--trend-filter")
        self.assertEqual(args[trend_index + 1], "compare")
        top_index = args.index("--top-n")
        self.assertEqual(args[top_index + 1], "20")
        target_index = args.index("--target-symbols")
        self.assertEqual(args[target_index + 1], "8")
        pages_index = args.index("--backtest-pages")
        self.assertEqual(args[pages_index + 1], "3")
        risk_index = args.index("--allocation-max-risk-events")
        self.assertEqual(args[risk_index + 1], "10")
        mixed_index = args.index("--market-regime-mixed-policy")
        self.assertEqual(args[mixed_index + 1], "price_anchor")

    def test_normalize_portfolio_backtest_payload_reports_capped_values(self) -> None:
        payload = dashboard_server.normalize_portfolio_backtest_payload(
            {
                "tradingMode": "paper",
                "topN": "999",
                "targetSymbols": "999",
                "backtestPages": "99",
                "backtestLimit": "999",
                "allocationMaxRiskEvents": "99",
                "coreSymbols": "99",
            }
        )

        self.assertEqual(payload["parameters"]["topN"], 20)
        self.assertEqual(payload["parameters"]["targetSymbols"], 8)
        self.assertEqual(payload["parameters"]["backtestPages"], 3)
        self.assertEqual(payload["parameters"]["backtestLimit"], 300)
        self.assertEqual(payload["parameters"]["allocationMaxRiskEvents"], 10)
        self.assertEqual(payload["parameters"]["marketRegimeMixedPolicy"], "price_anchor")
        self.assertEqual(payload["parameters"]["coreSymbols"], 4)
        self.assertIn("topN: requested 999, capped to 20", payload["warnings"][0])
        self.assertTrue(any("allocationMaxRiskEvents: requested 99, capped to 10" in item for item in payload["warnings"]))

    def test_parse_portfolio_backtest_log_detects_completed_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "portfolio_backtest_stdout.log"
            log_path.write_text(
                "\n--- portfolio backtest start 2026-06-24T22:22:34+00:00 ---\n"
                'parameters={"topN": 20, "targetSymbols": 8}\n'
                'parameter_warnings=["topN: requested 999, capped to 20 (allowed 1-20)"]\n'
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
        self.assertEqual(payload["parameters"]["topN"], 20)
        self.assertIn("topN: requested 999, capped to 20", payload["parameterWarnings"][0])

    def test_build_dataset_archive_includes_only_dataset_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backtest_dir = root / "data" / "backtest"
            regime_dir = root / "reports" / "regime_model"
            backtest_dir.mkdir(parents=True)
            regime_dir.mkdir(parents=True)
            (backtest_dir / "BTC-USDT-SWAP_1m_120.csv").write_text("ts,open,high,low,close,volume\n", encoding="utf-8")
            (backtest_dir / "private.log").write_text("secret runtime log\n", encoding="utf-8")
            (regime_dir / "scores.csv").write_text("variant,score\nrf,1\n", encoding="utf-8")
            (regime_dir / ".env").write_text("OKX_SECRET_KEY=x\n", encoding="utf-8")

            with patch.object(
                dashboard_server,
                "DATASET_DOWNLOAD_ROOTS",
                (
                    ("data/backtest", backtest_dir),
                    ("reports/regime_model", regime_dir),
                ),
            ), patch.object(dashboard_server, "DATASET_ARCHIVE_DIR", root / "downloads"):
                zip_path, filename = dashboard_server.build_dataset_archive()
                self.assertEqual(zip_path.parent, root / "downloads")

            try:
                with zipfile.ZipFile(zip_path) as archive:
                    names = set(archive.namelist())
            finally:
                zip_path.unlink(missing_ok=True)

        self.assertTrue(filename.startswith("okx-quant-dataset-"))
        self.assertIn("okx-quant-dataset/data/backtest/BTC-USDT-SWAP_1m_120.csv", names)
        self.assertIn("okx-quant-dataset/reports/regime_model/scores.csv", names)
        self.assertIn("okx-quant-dataset/manifest.json", names)
        self.assertNotIn("okx-quant-dataset/data/backtest/private.log", names)
        self.assertNotIn("okx-quant-dataset/reports/regime_model/.env", names)

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

    def test_latest_portfolio_report_payload_shows_newest_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_root = Path(tmpdir) / "reports"
            live_dir = report_root / "20260625T090000Z"
            paper_dir = report_root / "20260625T100000Z"
            for report_dir, mode in ((live_dir, "live"), (paper_dir, "paper")):
                runtime_dir = report_dir / "runtime_configs"
                runtime_dir.mkdir(parents=True)
                (report_dir / "candidates.json").write_text("{}", encoding="utf-8")
                (report_dir / "scores.csv").write_text(
                    "rank,status,inst_id,total_return_pct,max_drawdown_pct,profit_factor,fills,win_rate_pct,risk_events\n",
                    encoding="utf-8",
                )
                (report_dir / "rebalance_plan.json").write_text(
                    json.dumps({"generatedAt": mode, "tradingMode": mode, "targets": [], "actions": []}),
                    encoding="utf-8",
                )
                (report_dir / "execution_intents.json").write_text(
                    json.dumps({"execution": {"trading_mode": mode}, "intents": []}),
                    encoding="utf-8",
                )
                (report_dir / "summary.md").write_text(mode, encoding="utf-8")

            paper_dir.touch()

            with patch.object(dashboard_server, "PORTFOLIO_REPORT_DIR", report_root), patch.object(
                dashboard_server,
                "portfolio_live_status",
                return_value={
                    "enabled": True,
                    "mode": "live",
                    "runningCount": 0,
                    "targetCount": 0,
                    "pnl": {"estimatedTotal": "0", "recent5h": "0", "recent5hFillCount": 0},
                },
            ):
                payload = dashboard_server.latest_portfolio_report_payload()
                latest_any = dashboard_server.latest_portfolio_report_dir()
                latest_live = dashboard_server.latest_portfolio_report_dir(trading_mode="live")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["name"], paper_dir.name)
        self.assertEqual(payload["summary"]["tradingMode"], "paper")
        self.assertEqual(latest_any, paper_dir)
        self.assertEqual(latest_live, live_dir)

    def test_latest_portfolio_report_payload_prefers_executable_live_over_empty_newer_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_root = Path(tmpdir) / "reports"
            executable = report_root / "20260625T090000Z"
            empty = report_root / "20260625T100000Z"
            for report_dir in (executable, empty):
                (report_dir / "runtime_configs").mkdir(parents=True)
                (report_dir / "candidates.json").write_text("{}", encoding="utf-8")
                (report_dir / "scores.csv").write_text(
                    "rank,status,inst_id,total_return_pct,max_drawdown_pct,profit_factor,fills,win_rate_pct,risk_events\n",
                    encoding="utf-8",
                )
                (report_dir / "rebalance_plan.json").write_text(
                    json.dumps({"generatedAt": report_dir.name, "tradingMode": "live", "targets": [], "actions": []}),
                    encoding="utf-8",
                )
                (report_dir / "summary.md").write_text(report_dir.name, encoding="utf-8")
            (executable / "execution_intents.json").write_text(
                json.dumps({"execution": {"trading_mode": "live"}, "intents": [{"inst_id": "AAA-USDT-SWAP", "status": "runtime_config_ready"}]}),
                encoding="utf-8",
            )
            (empty / "execution_intents.json").write_text(
                json.dumps({"execution": {"trading_mode": "live"}, "intents": []}),
                encoding="utf-8",
            )
            empty.touch()

            with patch.object(dashboard_server, "PORTFOLIO_REPORT_DIR", report_root), patch.object(
                dashboard_server,
                "portfolio_live_status",
                return_value={
                    "enabled": True,
                    "mode": "live",
                    "runningCount": 0,
                    "targetCount": 1,
                    "pnl": {"estimatedTotal": "0", "recent5h": "0", "recent5hFillCount": 0},
                },
            ):
                payload = dashboard_server.latest_portfolio_report_payload(report_dir=executable)
                latest_executable = dashboard_server.latest_portfolio_report_dir(trading_mode="live", require_execution=True)
                latest_live = dashboard_server.latest_portfolio_report_dir(trading_mode="live")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["name"], executable.name)
        self.assertEqual(latest_executable, executable)
        self.assertEqual(latest_live, empty)
        self.assertEqual(payload["candidates"].get("candidateCount"), 0)
        self.assertEqual(payload["summaryMarkdown"], "")

    def test_portfolio_preflight_block_reasons_groups_by_instrument(self) -> None:
        checks = [
            SimpleNamespace(severity="pass", code="ok", inst_id="AAA-USDT-SWAP", message="ok"),
            SimpleNamespace(severity="block", code="pending_algo_orders_exist", inst_id="BBB-USDT-SWAP", message="Pending conditional algo orders exist."),
            SimpleNamespace(severity="block", code="account_read_failed", inst_id="", message="Failed to read account."),
        ]

        reasons = dashboard_server.portfolio_preflight_block_reasons(checks)

        self.assertEqual(reasons, {"BBB-USDT-SWAP": ["pending_algo_orders_exist: Pending conditional algo orders exist."]})

    def test_run_portfolio_reduce_intents_marks_nonzero_return_as_failed(self) -> None:
        completed = SimpleNamespace(returncode=2)
        with patch.object(dashboard_server.subprocess, "run", return_value=completed), patch.object(
            dashboard_server,
            "live_command_from_dry_run",
            return_value=["python", "portfolio_rebalancer.py", "--once", "--live"],
        ):
            results = dashboard_server.run_portfolio_reduce_intents(
                [{"inst_id": "OLD-USDT-SWAP", "dry_run_command": "reduce"}],
                requested=set(),
            )

        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[0]["returnCode"], 2)

    def test_hot_update_portfolio_runtime_writes_running_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_dir = root / "report"
            runtime_dir = report_dir / "runtime_configs"
            runtime_dir.mkdir(parents=True)
            source = runtime_dir / "aaa.json"
            running = root / "running" / "aaa.json"
            source.write_text(json.dumps({"instId": "AAA-USDT-SWAP", "gridBps": "18"}), encoding="utf-8")
            running.parent.mkdir()
            running.write_text(json.dumps({"instId": "AAA-USDT-SWAP", "gridBps": "9"}), encoding="utf-8")

            result = dashboard_server.hot_update_portfolio_runtime(
                report_dir,
                {"inst_id": "AAA-USDT-SWAP", "runtime_config_path": str(source)},
                {"pid": 123, "command": ["/venv/bin/python", "auto_grid_bot.py", "--runtime-config", str(running)]},
            )
            saved = json.loads(running.read_text(encoding="utf-8"))

        self.assertEqual(result["to"], str(running))
        self.assertEqual(saved["gridBps"], "18")
        self.assertEqual(saved["dashboardHotUpdatedFromReport"], str(report_dir))

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
