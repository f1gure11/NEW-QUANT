from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import research_dashboard as dashboard


class ResearchDashboardTest(unittest.TestCase):
    def test_manual_sector_inventory_cache_invalidates_on_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = root / "manifest.json"
            playbook_path = root / "config" / "aggressive_sector_playbook.json"
            playbook_path.parent.mkdir()
            manifest_path.write_text("manifest-v1", encoding="utf-8")
            playbook_path.write_text("playbook-v1", encoding="utf-8")
            previous_cache = dict(dashboard._MANUAL_SECTOR_CACHE)
            dashboard._MANUAL_SECTOR_CACHE.update({"signature": None, "payload": None})
            try:
                with patch.object(dashboard, "MANIFEST_PATH", manifest_path), patch.object(
                    dashboard,
                    "PROJECT_ROOT",
                    root,
                ), patch.object(
                    dashboard,
                    "manual_sector_inventory",
                    side_effect=[{"version": 1}, {"version": 2}],
                ) as build:
                    first = dashboard.cached_manual_sector_inventory()
                    second = dashboard.cached_manual_sector_inventory()
                    manifest_path.write_text("manifest-version-2-updated", encoding="utf-8")
                    third = dashboard.cached_manual_sector_inventory()
            finally:
                dashboard._MANUAL_SECTOR_CACHE.update(previous_cache)

        self.assertIs(first, second)
        self.assertEqual(third, {"version": 2})
        self.assertEqual(build.call_count, 2)

    def test_manual_sector_inventory_exposes_frozen_rules_and_lake_references(self) -> None:
        payload = dashboard.manual_sector_inventory()

        self.assertEqual(payload["mode"], "manual_subjective_sector_plan")
        self.assertEqual(payload["status"], "research_only")
        self.assertFalse(payload["paperOrLiveAuthorized"])
        self.assertEqual(len(payload["sectors"]), 8)
        semiconductor = next(item for item in payload["sectors"] if item["key"] == "semiconductor")
        sk_hynix = next(item for item in payload["sectors"] if item["key"] == "sk_hynix")
        gold = next(item for item in payload["sectors"] if item["key"] == "precious_metals")
        self.assertEqual([leg["instId"] for leg in semiconductor["legs"]], ["SNDK-USDT-SWAP", "SOXL-USDT-SWAP"])
        self.assertEqual([leg["instId"] for leg in sk_hynix["legs"]], ["SKHY-USDT-SWAP"])
        self.assertEqual([leg["instId"] for leg in gold["legs"]], ["XAU-USDT-SWAP"])
        self.assertEqual(semiconductor["legs"][0]["reference"]["status"], "reference_only")
        self.assertEqual(payload["risk"]["takeProfit1ClosePct"], 50.0)
        self.assertEqual(payload["execution"]["maxEntryDeviationBps"], 100)

    def test_backtest_inventory_keeps_all_mean_reversion_scenarios(self) -> None:
        qqq = {
            "decision": {"status": "research_only"},
            "results": {
                "monthly": {
                    cost: {
                        "segments": {
                            split: {
                                "annualizedActiveReturnPct": 1.0,
                                "informationRatio": 0.5,
                                "portfolioAnnualReturnPct": 11.0,
                                "benchmarkAnnualReturnPct": 10.0,
                                "portfolioMaxDrawdownPct": 5.0,
                                "averageGrossPct": 10.0,
                            }
                            for split in ("train", "validation", "test")
                        }
                    }
                    for cost in ("base", "stress")
                }
            },
        }
        mean_reversion = {
            "selection": {"status": "failed_validation_research_only"},
            "results": [
                {
                    "strategy": "pairs",
                    "split": "test",
                    "leverage": 2,
                    "cost_profile": "base",
                    "total_return_pct": -1.0,
                    "unexpected": "drop",
                }
            ],
        }

        payload = dashboard.backtest_inventory(qqq, mean_reversion)

        self.assertEqual(len(payload["qqq"]["rows"]), 6)
        self.assertEqual(len(payload["meanReversion"]["rows"]), 1)
        self.assertNotIn("unexpected", payload["meanReversion"]["rows"][0])

    def test_forward_stock_status_counts_only_tagged_post_boundary_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inst_dir = root / "aaa_usdt_swap"
            inst_dir.mkdir()
            rows = [
                {"capturedAt": "2026-01-01T00:00:00Z", "instId": "AAA-USDT-SWAP", "ok": True, "dataComplete": True},
                {
                    "capturedAt": "2026-01-01T01:00:00Z",
                    "instId": "AAA-USDT-SWAP",
                    "ok": True,
                    "dataComplete": True,
                    "research": {"modelId": "model-1"},
                },
            ]
            (inst_dir / "20260101.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            manifest = {
                "generatedAt": "2026-01-01T02:00:00Z",
                "sources": {
                    "snapshots": [
                        {
                            "inst": "aaa_usdt_swap",
                            "rows": 2,
                            "files": ["20260101.jsonl", "20260102.jsonl"],
                        }
                    ]
                },
            }
            registry = {
                "study": {
                    "modelId": "model-1",
                    "status": "preregistered_collecting",
                    "forwardBoundary": "2026-01-01T00:30:00Z",
                    "paperOrLiveAuthorized": False,
                    "universe": {"instruments": ["AAA-USDT-SWAP"]},
                    "candidateReductionMapping": {"status": "not_yet_preregistered"},
                    "maturity": {"minimumCompleteCalendarMonths": 12, "minimumIndependentReductionEvents": 100},
                }
            }
            dashboard._FORWARD_BASELINE.clear()
            with patch.object(dashboard, "SNAPSHOT_ROOT", root), patch.object(
                dashboard.datetime,
                "now",
                return_value=dashboard.parse_time("2026-01-01T02:00:00Z"),
            ):
                result = dashboard.forward_stock_status(manifest, registry)

        self.assertEqual(result["eligibleSnapshots"], 1)
        self.assertEqual(result["instruments"], 1)
        self.assertFalse(result["paperOrLiveAuthorized"])


if __name__ == "__main__":
    unittest.main()
