from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import research_forward as rf


def candle(at: datetime, *, high: float, low: float, close: float) -> dict:
    return {
        "ts": int(at.timestamp() * 1000),
        "time": rf.iso_utc(at),
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
        "confirm": "1",
    }


def event() -> dict:
    return {
        "id": "cpi-2026-08-12",
        "scheduledAt": "2026-08-12T12:30:00+00:00",
        "sourceDate": "2026-08-12",
    }


def pre_event_candles() -> list[dict]:
    scheduled = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)
    return [
        candle(scheduled - timedelta(minutes=5 * offset), high=101.0, low=99.0, close=100.0)
        for offset in range(12, 0, -1)
    ]


class FrozenRegistryTests(unittest.TestCase):
    def test_registry_has_three_non_trading_models_and_stable_ids(self) -> None:
        first = rf.build_registry("2026-08-08T18:00:00Z")
        second = rf.build_registry("2026-08-08T18:00:00Z")

        self.assertEqual(first["registryId"], second["registryId"])
        self.assertEqual(len(first["models"]), 3)
        self.assertTrue(all(model["paperOrLiveAuthorized"] is False for model in first["models"]))
        self.assertEqual(first["models"][0]["modelId"], "qqq-pit-1fda3d7e14f137bf")

    def test_registry_validation_detects_content_tampering(self) -> None:
        registry = rf.build_registry("2026-08-08T18:00:00Z")
        registry["models"][1]["basis"]["preEventRangeBars"] = 13

        with self.assertRaisesRegex(ValueError, "registryId"):
            rf.validate_registry(registry)


class EventNormalizationTests(unittest.TestCase):
    def test_matches_exact_ticker_and_computes_point_in_time_surprise(self) -> None:
        payload = {
            "status": "ok",
            "result": [
                {
                    "id": "398051",
                    "ticker": "ECONOMICS:USIRYY",
                    "date": "2026-08-12T12:30:00.000Z",
                    "actualRaw": 3.5,
                    "forecastRaw": 3.4,
                    "previousRaw": 3.5,
                    "source": "Bureau of Labour Statistics",
                    "source_url": "https://www.bls.gov/",
                }
            ],
        }
        matched, status = rf.match_tradingview_event(payload, event())

        self.assertEqual(status, "matched")
        self.assertEqual(matched["id"], "398051")
        with patch.object(rf, "first_previous_value", return_value=3.4):
            row = rf.normalize_event_observation(
                event(),
                payload,
                captured_at=datetime(2026, 8, 12, 13, tzinfo=timezone.utc),
                source_url="https://example.test",
                raw_path="events/raw/test.json",
                raw_sha256="abc",
                market_candles=[],
            )
        self.assertTrue(row["dataComplete"])
        self.assertAlmostEqual(row["surprise"], 0.1)
        self.assertAlmostEqual(row["surpriseScore"], 1.0)
        self.assertAlmostEqual(row["revision"], 0.1)

    def test_incomplete_consensus_never_becomes_significant(self) -> None:
        payload = {
            "result": [
                {
                    "id": "398051",
                    "ticker": "ECONOMICS:USIRYY",
                    "date": "2026-08-12T12:30:00.000Z",
                    "actualRaw": 3.5,
                    "forecastRaw": None,
                    "previousRaw": 3.4,
                }
            ]
        }
        with patch.object(rf, "first_previous_value", return_value=3.4):
            row = rf.normalize_event_observation(
                event(),
                payload,
                captured_at=datetime(2026, 8, 12, 13, tzinfo=timezone.utc),
                source_url="https://example.test",
                raw_path="events/raw/test.json",
                raw_sha256="abc",
                market_candles=pre_event_candles(),
            )
        self.assertFalse(row["dataComplete"])
        self.assertIsNone(row["surpriseScore"])
        self.assertEqual(row["gate"]["decision"], "no_trade")


class EventGateTests(unittest.TestCase):
    def test_three_closes_outside_range_confirms_breakout(self) -> None:
        scheduled = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)
        post = [candle(scheduled + timedelta(minutes=5 * index), high=103, low=101.5, close=102) for index in range(3)]

        result = rf.classify_event_gate(event(), [*pre_event_candles(), *post], surprise_score=1.2)

        self.assertEqual(result["decision"], "breakout_long")

    def test_breach_then_three_inside_closes_confirms_reversal(self) -> None:
        scheduled = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)
        breach = [
            candle(scheduled + timedelta(minutes=5 * index), high=102 if index == 0 else 101, low=99.5, close=100)
            for index in range(3)
        ]
        inside = [
            candle(scheduled + timedelta(minutes=15 + 5 * index), high=100.5, low=99.5, close=100)
            for index in range(3)
        ]

        result = rf.classify_event_gate(event(), [*pre_event_candles(), *breach, *inside], surprise_score=1.2)

        self.assertEqual(result["decision"], "reversal_short")

    def test_small_surprise_is_no_trade_even_after_breakout(self) -> None:
        scheduled = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)
        post = [candle(scheduled + timedelta(minutes=5 * index), high=103, low=101.5, close=102) for index in range(3)]

        result = rf.classify_event_gate(event(), [*pre_event_candles(), *post], surprise_score=0.9)

        self.assertEqual(result["reason"], "surprise_below_frozen_threshold")
        self.assertEqual(result["decision"], "no_trade")


class MaturityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = rf.build_registry("2026-08-08T18:00:00Z")

    def test_qqq_counts_only_new_signal_dates_after_boundary(self) -> None:
        model = copy.deepcopy(rf.model_by_key(self.registry, "qqq_monthly_active_enhancement"))
        model["maturity"] = {
            "minimumNewSignalDates": 2,
            "preferredNewSignalDates": 3,
            "minimumForwardDays": 20,
            "minimumCompleteMarketObservationRatio": 0.9,
        }
        rows = [
            {"capturedAt": "2026-08-09T00:00:00Z", "observationType": "market", "marketCoverage": 1.0},
            {"capturedAt": "2026-08-31T23:00:00Z", "observationType": "signal_decision", "signalDate": "2026-08-31"},
            {"capturedAt": "2026-08-31T23:05:00Z", "observationType": "market", "marketCoverage": 1.0},
            {"capturedAt": "2026-09-30T23:00:00Z", "observationType": "signal_decision", "signalDate": "2026-09-30"},
            {"capturedAt": "2026-09-30T23:05:00Z", "observationType": "market", "marketCoverage": 1.0},
        ]

        result = rf.qqq_maturity(model, rows)

        self.assertEqual(result["newSignalDates"], ["2026-08-31", "2026-09-30"])
        self.assertEqual(result["status"], "mature_for_single_frozen_evaluation")

    def test_event_maturity_uses_latest_complete_row_per_event(self) -> None:
        model = copy.deepcopy(rf.model_by_key(self.registry, "qqq_event_breakout_reversal_gate"))
        model["maturity"] = {
            "minimumCompleteEvents": 1,
            "minimumEventsPerFamily": 0,
            "minimumDirectionalDecisions": 1,
        }
        rows = [
            {"capturedAt": "2026-08-12T12:35:00Z", "eventId": "cpi-2026-08-12", "family": "cpi", "dataComplete": False, "gate": {"status": "waiting", "decision": "no_trade"}},
            {"capturedAt": "2026-08-12T13:00:00Z", "eventId": "cpi-2026-08-12", "family": "cpi", "dataComplete": True, "gate": {"status": "resolved", "decision": "breakout_long"}},
        ]

        result = rf.event_maturity(model, rows)

        self.assertEqual(result["completeEvents"], 1)
        self.assertEqual(result["directionalDecisions"], 1)
        self.assertEqual(result["status"], "mature_for_single_frozen_evaluation")

    def test_daily_observation_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(rf, "RESEARCH_DIR", Path(tmpdir)):
            model_id = "test-model"
            captured = datetime(2026, 8, 9, tzinfo=timezone.utc)
            rf.append_jsonl(
                rf.observation_path(model_id, captured),
                {
                    "capturedAt": rf.iso_utc(captured),
                    "observationDate": "2026-08-09",
                    "observationType": "signal_decision",
                },
            )

            self.assertFalse(rf.already_observed_today(model_id, captured))
            rf.append_jsonl(
                rf.observation_path(model_id, captured),
                {
                    "capturedAt": rf.iso_utc(captured),
                    "observationDate": "2026-08-09",
                    "observationType": "market",
                },
            )
            self.assertTrue(rf.already_observed_today(model_id, captured))
            self.assertFalse(rf.already_observed_today(model_id, captured + timedelta(days=1)))


class QQQForwardDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        registry = rf.build_registry("2026-08-08T18:00:00Z")
        self.model = copy.deepcopy(rf.model_by_key(registry, "qqq_monthly_active_enhancement"))

    def test_rejects_changed_frozen_universe_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            changed = Path(tmpdir) / "universe.csv"
            changed.write_text("symbol,cik,industry\nAMD,2488,changed\n", encoding="utf-8")
            with patch.object(rf, "QQQ_UNIVERSE_PATH", changed):
                with self.assertRaisesRegex(ValueError, "checksum changed"):
                    rf.frozen_qqq_universe(self.model)

    def test_records_one_json_safe_decision_per_signal_date(self) -> None:
        signal_date = pd.Timestamp("2026-08-31")
        signal = pd.DataFrame(
            {
                "momentum": [np.float64(0.5)],
                "quality": [np.float64(0.4)],
                "value": [np.float64(0.3)],
                "low_residual_volatility": [np.float64(0.2)],
                "composite": [np.float64(0.35)],
                "beta": [np.float64(1.1)],
                "size_z": [np.float64(0.1)],
                "latest_filed": [pd.Timestamp("2026-08-15")],
                "fiscal_end": ["2026-06-30"],
                "industry": ["information_technology"],
            },
            index=["AMD"],
        )
        history = (
            {signal_date: pd.Series({"AMD": np.float64(0.01)})},
            [{"rebalanceDate": "2026-08-31", "gross": np.float64(0.01)}],
            {signal_date: signal},
        )
        artifacts = [
            {"path": "research/test/input-1", "sha256": "a"},
            {"path": "research/test/input-2", "sha256": "b"},
            {"path": "research/test/input-3", "sha256": "c"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(rf, "RESEARCH_DIR", Path(tmpdir)), patch.object(
            rf, "frozen_qqq_universe", return_value={"AMD": {"cik": "2488"}}
        ), patch.object(rf, "load_yahoo_daily", return_value=pd.DataFrame()), patch.object(
            rf, "load_company_facts", return_value={}
        ), patch.object(rf, "prepare_fundamental_records", return_value={}), patch.object(
            rf, "build_weight_history", return_value=history
        ), patch.object(rf, "archive_qqq_inputs", return_value=artifacts):
            first = rf.generate_qqq_forward_decision(
                self.model, datetime(2026, 9, 2, 23, 17, tzinfo=timezone.utc)
            )
            second = rf.generate_qqq_forward_decision(
                self.model, datetime(2026, 9, 3, 23, 17, tzinfo=timezone.utc)
            )
            rows = rf.read_jsonl(Path(tmpdir))

        self.assertEqual(first["status"], "recorded")
        self.assertEqual(second["status"], "no_new_completed_month")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["signalDate"], "2026-08-31")
        self.assertEqual(rows[0]["latestFactors"]["AMD"]["latest_filed"], "2026-08-15T00:00:00")
        self.assertFalse(rows[0]["paperOrLiveAuthorized"])
        json.dumps(rows[0])

    def test_archives_price_and_sec_inputs_with_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            research_root = project_root / "data_lake" / "research"
            data_root = research_root / "model" / "working_inputs"
            price = data_root / "prices" / "QQQ_1d_10y.csv"
            facts = data_root / "sec" / "CIK0000002488_companyfacts.json"
            price.parent.mkdir(parents=True)
            facts.parent.mkdir(parents=True)
            price.write_text("date,close\n2026-08-31,100\n", encoding="utf-8")
            facts.write_text('{"facts":{}}\n', encoding="utf-8")
            with patch.object(rf, "PROJECT_ROOT", project_root), patch.object(
                rf, "RESEARCH_DIR", research_root
            ):
                artifacts = rf.archive_qqq_inputs(
                    data_root,
                    "model",
                    datetime(2026, 9, 2, 23, 17, tzinfo=timezone.utc),
                )

            self.assertEqual(len(artifacts), 2)
            for artifact in artifacts:
                archived = project_root / "data_lake" / artifact["path"]
                self.assertTrue(archived.is_file())
                self.assertEqual(artifact["sha256"], rf.sha256_file(archived))


if __name__ == "__main__":
    unittest.main()
