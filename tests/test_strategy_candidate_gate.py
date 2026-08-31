from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from strategy_candidate_gate import GateConfig, build_gate_payload


FIELDS = [
    "inst_id",
    "strategy",
    "params",
    "regime_filter",
    "allowed_regimes",
    "passed",
    "selected_windows",
    "passed_windows",
    "pass_rate_pct",
    "total_test_return_pct",
    "median_test_return_pct",
    "worst_test_return_pct",
    "mean_test_drawdown_pct",
    "mean_test_exposure_pct",
    "total_test_trades",
    "score",
]


def write_aggregate(path: Path, rows: list[dict[str, str]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with (path / "aggregate.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            payload = {field: "" for field in FIELDS}
            payload.update(row)
            writer.writerow(payload)


ROW_FIELDS = ["window", "inst_id", "strategy", "params", "regime_filter", "allowed_regimes", "test_return_pct"]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with (path / "rows.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ROW_FIELDS)
        writer.writeheader()
        for row in rows:
            payload = {field: "" for field in ROW_FIELDS}
            payload.update(row)
            writer.writerow(payload)


def row_for_window(window: int, test_return_pct: str) -> dict[str, str]:
    return {
        "window": str(window),
        "inst_id": "AAA-USDT-SWAP",
        "strategy": "time_series_momentum",
        "params": '{"slow": 55, "fast": 13}',
        "regime_filter": "all",
        "allowed_regimes": "all",
        "test_return_pct": test_return_pct,
    }


def passed_row(**overrides: str) -> dict[str, str]:
    row = {
        "inst_id": "AAA-USDT-SWAP",
        "strategy": "time_series_momentum",
        "params": '{"slow": 55, "fast": 13}',
        "regime_filter": "all",
        "allowed_regimes": "all",
        "passed": "true",
        "selected_windows": "4",
        "passed_windows": "3",
        "pass_rate_pct": "75",
        "total_test_return_pct": "2.5",
        "median_test_return_pct": "0.4",
        "worst_test_return_pct": "-1.5",
        "mean_test_drawdown_pct": "2.0",
        "mean_test_exposure_pct": "80",
        "total_test_trades": "40",
        "score": "1.2",
    }
    row.update(overrides)
    return row


class StrategyCandidateGateTest(unittest.TestCase):
    def test_rejects_profitable_strategy_without_registered_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row(strategy="ema_cross")])
            write_aggregate(confirm, [passed_row(strategy="ema_cross")])

            payload = build_gate_payload(primary, confirm, GateConfig())

        self.assertEqual(payload["approvedCandidates"], [])
        self.assertEqual(payload["summary"]["unverifiedPrimaryRejected"], 1)
        self.assertEqual(payload["summary"]["unverifiedConfirmRejected"], 1)

    def test_approved_candidate_embeds_strategy_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row()])
            write_aggregate(confirm, [passed_row()])

            payload = build_gate_payload(primary, confirm, GateConfig())

        evidence = payload["approvedCandidates"][0]["strategyEvidence"]
        self.assertEqual(evidence["strategy"], "time_series_momentum")
        self.assertTrue(any(source["kind"] == "journal" for source in evidence["sources"]))

    def test_activity_gate_rejects_low_exposure_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row(mean_test_exposure_pct="35")])
            write_aggregate(confirm, [passed_row(mean_test_exposure_pct="70")])

            payload = build_gate_payload(primary, confirm, GateConfig(min_mean_exposure_pct=60))

        self.assertEqual(payload["summary"]["primaryPassed"], 0)
        self.assertEqual(payload["approvedCandidates"], [])

    def test_approves_candidate_only_when_same_key_passes_both_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row()])
            write_aggregate(confirm, [passed_row(params='{"fast":13,"slow":55}', total_test_return_pct="1.1")])

            payload = build_gate_payload(primary, confirm, GateConfig())

        self.assertEqual(payload["summary"]["primaryPassed"], 1)
        self.assertEqual(payload["summary"]["confirmPassed"], 1)
        self.assertEqual(payload["summary"]["intersection"], 1)
        self.assertEqual(payload["summary"]["approved"], 1)
        candidate = payload["approvedCandidates"][0]
        self.assertEqual(candidate["instId"], "AAA-USDT-SWAP")
        self.assertEqual(candidate["params"], {"fast": 13, "slow": 55})
        self.assertEqual(candidate["combined"]["minTotalReturnPct"], 1.1)

    def test_rejects_candidates_without_strict_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row(params='{"fast":13,"slow":55}')])
            write_aggregate(confirm, [passed_row(params='{"fast":21,"slow":89}')])

            payload = build_gate_payload(primary, confirm, GateConfig())

        self.assertEqual(payload["summary"]["primaryPassed"], 1)
        self.assertEqual(payload["summary"]["confirmPassed"], 1)
        self.assertEqual(payload["summary"]["intersection"], 0)
        self.assertEqual(payload["approvedCandidates"], [])

    def test_strategy_match_confirms_family_and_keeps_primary_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(
                primary,
                [passed_row(params='{"fast":21,"slow":55}', regime_filter="trend", score="4")],
            )
            write_aggregate(
                confirm,
                [passed_row(params='{"fast":13,"slow":34}', regime_filter="all", score="3")],
            )

            payload = build_gate_payload(primary, confirm, GateConfig(match_mode="strategy"))

        self.assertEqual(payload["summary"]["intersection"], 1)
        self.assertEqual(payload["summary"]["approved"], 1)
        candidate = payload["approvedCandidates"][0]
        self.assertEqual(candidate["params"], {"fast": 21, "slow": 55})
        self.assertEqual(candidate["regimeFilter"], "trend")
        self.assertEqual(candidate["confirmation"]["params"], {"fast": 13, "slow": 34})
        self.assertEqual(candidate["matchMode"], "strategy")

    def test_strategy_match_hysteresis_survives_parameter_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_primary = root / "first_primary"
            first_confirm = root / "first_confirm"
            next_primary = root / "next_primary"
            next_confirm = root / "next_confirm"
            write_aggregate(first_primary, [passed_row(params='{"fast":13,"slow":34}')])
            write_aggregate(first_confirm, [passed_row(params='{"fast":13,"slow":34}')])
            write_aggregate(next_primary, [passed_row(params='{"fast":21,"slow":55}')])
            write_aggregate(next_confirm, [passed_row(params='{"fast":13,"slow":34}')])
            config = GateConfig(match_mode="strategy", enter_streak=2, exit_misses=2)

            first = build_gate_payload(
                first_primary,
                first_confirm,
                config,
                previous_payload={"approvedCandidates": [], "pendingCandidates": []},
            )
            second = build_gate_payload(next_primary, next_confirm, config, previous_payload=first)

        self.assertEqual(first["approvedCandidates"], [])
        self.assertEqual(len(first["pendingCandidates"]), 1)
        self.assertEqual(len(second["approvedCandidates"]), 1)
        self.assertEqual(second["approvedCandidates"][0]["passStreak"], 2)
        self.assertEqual(second["approvedCandidates"][0]["params"], {"fast": 21, "slow": 55})

    def test_dsr_threshold_rejects_candidate_with_weak_window_returns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row()])
            write_aggregate(confirm, [passed_row()])
            # Barely-positive noisy window returns cannot clear a 95% DSR bar.
            noisy = ["0.4", "-0.3", "0.5", "-0.2", "0.35", "-0.25"]
            write_rows(primary, [row_for_window(index, value) for index, value in enumerate(noisy)])
            write_rows(confirm, [row_for_window(index, value) for index, value in enumerate(noisy)])

            strict = build_gate_payload(primary, confirm, GateConfig(min_dsr_prob=0.95))
            relaxed = build_gate_payload(primary, confirm, GateConfig())

        self.assertEqual(strict["approvedCandidates"], [])
        self.assertEqual(strict["summary"]["dsrRejected"], 1)
        self.assertEqual(len(relaxed["approvedCandidates"]), 1)
        self.assertIsNotNone(relaxed["approvedCandidates"][0]["dsrProbMin"])

    def test_hysteresis_pending_until_enter_streak_and_carry_until_exit_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            empty_primary = root / "empty_primary"
            empty_confirm = root / "empty_confirm"
            write_aggregate(primary, [passed_row()])
            write_aggregate(confirm, [passed_row()])
            write_aggregate(empty_primary, [passed_row(passed="false")])
            write_aggregate(empty_confirm, [passed_row(passed="false")])
            config = GateConfig(enter_streak=2, exit_misses=2)

            first = build_gate_payload(primary, confirm, config, previous_payload={"approvedCandidates": [], "pendingCandidates": []})
            second = build_gate_payload(primary, confirm, config, previous_payload=first)
            third = build_gate_payload(empty_primary, empty_confirm, config, previous_payload=second)
            fourth = build_gate_payload(empty_primary, empty_confirm, config, previous_payload=third)

        # First pass: pending only (streak 1 < 2). Second pass: promoted.
        self.assertEqual(first["approvedCandidates"], [])
        self.assertEqual(len(first["pendingCandidates"]), 1)
        self.assertEqual(len(second["approvedCandidates"]), 1)
        self.assertEqual(second["approvedCandidates"][0]["passStreak"], 2)
        # First miss: carried forward. Second consecutive miss: dropped.
        self.assertEqual(len(third["approvedCandidates"]), 1)
        self.assertTrue(third["approvedCandidates"][0]["carriedForward"])
        self.assertEqual(third["approvedCandidates"][0]["missStreak"], 1)
        self.assertEqual(fourth["approvedCandidates"], [])
        self.assertEqual(len(fourth["droppedCandidates"]), 1)

    def test_no_previous_gate_keeps_fresh_candidates_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            primary = root / "primary"
            confirm = root / "confirm"
            write_aggregate(primary, [passed_row()])
            write_aggregate(confirm, [passed_row()])

            payload = build_gate_payload(primary, confirm, GateConfig(enter_streak=2, exit_misses=2))

        self.assertEqual(len(payload["approvedCandidates"]), 1)
        self.assertEqual(payload["approvedCandidates"][0]["passStreak"], 2)


if __name__ == "__main__":
    unittest.main()
