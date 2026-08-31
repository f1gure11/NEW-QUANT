from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import qqq_exit_overlay_forward as qef


UTC = timezone.utc
INST = "AMD-USDT-SWAP"
COSTS = {"basePerSideBps": 10.0, "stressPerSideBps": 20.0}


def panel(rows: list[tuple[datetime, float, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            (INST, "open"): [row[1] for row in rows],
            (INST, "close"): [row[2] for row in rows],
        },
        index=pd.DatetimeIndex([row[0] for row in rows]),
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    return frame


def cohort(boundary: datetime, side: int = 1) -> qef.SignalCohort:
    return qef.SignalCohort("2026-07-31", boundary, {INST: side * 0.10})


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = qef.read_json(qef.DEFAULT_REGISTRY_PATH)

    def test_registry_is_frozen_forward_only_with_named_variants(self) -> None:
        qef.validate_registry(self.registry, now=datetime(2026, 8, 10, 17, 6, tzinfo=UTC))

        self.assertFalse(self.registry["study"]["paperOrLiveAuthorized"])
        self.assertEqual(
            [row["key"] for row in self.registry["study"]["basis"]["variants"]],
            [
                "monthly_control",
                "fixed_take_profit_10pct",
                "trailing_profit_6pct_4pct",
                "biweekly_20session_trend_review",
            ],
        )
        self.assertEqual(self.registry["study"]["maturity"]["minimumForwardDays"], 365)

    def test_registry_validation_detects_parameter_tampering(self) -> None:
        changed = copy.deepcopy(self.registry)
        changed["study"]["basis"]["variants"][1]["takeProfitBps"] = 900

        with self.assertRaisesRegex(ValueError, "registryId"):
            qef.validate_registry(changed)


class ExitSimulationTests(unittest.TestCase):
    def test_rebalance_turnover_splits_reductions_increases_and_flips(self) -> None:
        cases = [
            (0.0, 0.10, (0.0, 0.10)),
            (0.10, 0.05, (0.05, 0.0)),
            (0.05, 0.10, (0.0, 0.05)),
            (0.10, -0.05, (0.10, 0.05)),
            (-0.10, 0.0, (0.10, 0.0)),
        ]
        for prior, target, expected in cases:
            with self.subTest(prior=prior, target=target):
                self.assertEqual(qef.rebalance_turnover(prior, target), expected)

    def test_monthly_rebalance_charges_only_target_weight_delta(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 100.0),
            (datetime(2026, 8, 12, 13, 35, tzinfo=UTC), 100.0, 100.0),
            (datetime(2026, 8, 12, 13, 40, tzinfo=UTC), 100.0, 100.0),
        ]
        cohorts = [
            cohort(boundary),
            qef.SignalCohort(
                "2026-08-31",
                datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
                {INST: 0.05},
            ),
        ]
        variant = {"key": "control", "type": "monthly_hold", "stopLossBps": 1500}

        result = qef.simulate_variant(panel(rows), {INST: []}, cohorts, variant, COSTS)

        self.assertEqual(result["closedTradeCount"], 1)
        self.assertEqual(result["openLegs"], 1)
        self.assertEqual(result["exitReasons"], {"monthly_signal_rebalance": 1})
        self.assertAlmostEqual(result["turnoverPct"], 15.0)
        self.assertAlmostEqual(result["baseCostPct"], 0.015)

    def test_unchanged_monthly_target_has_no_round_trip_cost(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 100.0),
            (datetime(2026, 8, 12, 13, 35, tzinfo=UTC), 100.0, 100.0),
        ]
        cohorts = [
            cohort(boundary),
            qef.SignalCohort(
                "2026-08-31",
                datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
                {INST: 0.10},
            ),
        ]
        variant = {"key": "control", "type": "monthly_hold", "stopLossBps": 1500}

        result = qef.simulate_variant(panel(rows), {INST: []}, cohorts, variant, COSTS)

        self.assertAlmostEqual(result["turnoverPct"], 10.0)
        self.assertAlmostEqual(result["baseCostPct"], 0.01)

    def test_rebalance_to_zero_attributes_exit_cost_to_closed_leg(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 100.0),
            (datetime(2026, 8, 12, 13, 35, tzinfo=UTC), 100.0, 100.0),
        ]
        cohorts = [
            cohort(boundary),
            qef.SignalCohort(
                "2026-08-31",
                datetime(2026, 8, 11, 14, 0, tzinfo=UTC),
                {},
            ),
        ]
        variant = {"key": "control", "type": "monthly_hold", "stopLossBps": 1500}

        result = qef.simulate_variant(panel(rows), {INST: []}, cohorts, variant, COSTS)

        self.assertAlmostEqual(result["turnoverPct"], 20.0)
        self.assertAlmostEqual(result["baseCostPct"], 0.02)
        self.assertAlmostEqual(result["trades"][0]["baseCostContribution"], 0.0002)
        self.assertAlmostEqual(result["trades"][0]["netContribution"], -0.0002)

    def test_fixed_take_profit_exits_on_next_bar_and_does_not_reenter(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 111.0),
            (datetime(2026, 8, 11, 13, 40, tzinfo=UTC), 110.0, 110.0),
            (datetime(2026, 8, 11, 13, 45, tzinfo=UTC), 109.0, 109.0),
        ]
        variant = {
            "key": "fixed",
            "type": "fixed_take_profit",
            "stopLossBps": 1500,
            "takeProfitBps": 1000,
        }

        result = qef.simulate_variant(panel(rows), {INST: []}, [cohort(boundary)], variant, COSTS)

        self.assertEqual(result["entryCount"], 1)
        self.assertEqual(result["closedTradeCount"], 1)
        self.assertEqual(result["openLegs"], 0)
        self.assertEqual(result["exitReasons"], {"take_profit": 1})
        self.assertEqual(result["trades"][0]["exitTime"], "2026-08-11T13:40:00Z")
        self.assertAlmostEqual(result["grossReturnPct"], 1.0)
        self.assertAlmostEqual(result["netReturnPct"], 0.98)

    def test_trailing_exit_uses_peak_favorable_return_and_next_open(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 107.0),
            (datetime(2026, 8, 11, 13, 40, tzinfo=UTC), 106.0, 102.0),
            (datetime(2026, 8, 11, 13, 45, tzinfo=UTC), 101.0, 101.0),
        ]
        variant = {
            "key": "trailing",
            "type": "trailing_take_profit",
            "stopLossBps": 1500,
            "activationBps": 600,
            "givebackBps": 400,
        }

        result = qef.simulate_variant(panel(rows), {INST: []}, [cohort(boundary)], variant, COSTS)

        self.assertEqual(result["exitReasons"], {"trailing_take_profit": 1})
        self.assertEqual(result["trades"][0]["exitPrice"], 101.0)
        self.assertEqual(result["openLegs"], 0)

    def test_negative_funding_is_a_cost_to_a_short(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 100.0),
            (datetime(2026, 8, 11, 13, 40, tzinfo=UTC), 100.0, 100.0),
        ]
        funding = {INST: [(datetime(2026, 8, 11, 13, 37, tzinfo=UTC), -0.001)]}
        variant = {"key": "control", "type": "monthly_hold", "stopLossBps": 1500}

        result = qef.simulate_variant(panel(rows), funding, [cohort(boundary, side=-1)], variant, COSTS)

        self.assertAlmostEqual(result["fundingReturnPct"], -0.01)

    def test_biweekly_review_waits_for_twenty_forward_sessions(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        rows: list[tuple[datetime, float, float]] = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 100.0)
        ]
        sessions = pd.bdate_range("2026-08-11", periods=20)
        for index, session in enumerate(sessions):
            local = pd.Timestamp(session.date(), tz=qef.NY_TZ) + pd.Timedelta(hours=15, minutes=55)
            at = local.tz_convert("UTC").to_pydatetime()
            close = 100.0 - index * 0.5
            rows.append((at, close, close))
        final_at = rows[-1][0] + timedelta(minutes=5)
        rows.append((final_at, 90.0, 90.0))
        variant = {
            "key": "trend",
            "type": "biweekly_trend_review",
            "stopLossBps": 1500,
            "lookbackSessions": 20,
            "reviewEverySessions": 10,
        }

        result = qef.simulate_variant(panel(rows), {INST: []}, [cohort(boundary)], variant, COSTS)

        self.assertEqual(result["closedTradeCount"], 1)
        self.assertEqual(result["exitReasons"], {"biweekly_trend_review": 1})
        self.assertEqual(result["trades"][0]["exitTime"], qef.iso_utc(final_at))

    def test_trend_history_remains_contiguous_while_leg_is_flat(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        sessions = pd.bdate_range("2026-08-11", periods=30)
        rows: list[tuple[datetime, float, float]] = [
            (datetime(2026, 8, 11, 13, 35, tzinfo=UTC), 100.0, 100.0)
        ]
        second_available_at: datetime | None = None
        for index, session in enumerate(sessions):
            close_local = pd.Timestamp(session.date(), tz=qef.NY_TZ) + pd.Timedelta(hours=15, minutes=55)
            close_at = close_local.tz_convert("UTC").to_pydatetime()
            close = 100.0 - index * 0.5
            if index == 29:
                entry_local = pd.Timestamp(session.date(), tz=qef.NY_TZ) + pd.Timedelta(hours=9, minutes=35)
                rows.append((entry_local.tz_convert("UTC").to_pydatetime(), close, close))
            rows.append((close_at, close, close))
            if index == 19:
                rows.append((close_at + timedelta(minutes=5), close, close))
            if index == 28:
                second_available_at = close_at + timedelta(minutes=5)
        rows.append((rows[-1][0] + timedelta(minutes=5), rows[-1][1], rows[-1][2]))
        self.assertIsNotNone(second_available_at)
        cohorts = [
            cohort(boundary),
            qef.SignalCohort("2026-08-31", second_available_at, {INST: 0.10}),
        ]
        variant = {
            "key": "trend",
            "type": "biweekly_trend_review",
            "stopLossBps": 1500,
            "lookbackSessions": 20,
            "reviewEverySessions": 10,
        }

        result = qef.simulate_variant(panel(rows), {INST: []}, cohorts, variant, COSTS)

        self.assertEqual(result["closedTradeCount"], 2)
        self.assertEqual(result["exitReasons"], {"biweekly_trend_review": 2})
        self.assertEqual(result["openLegs"], 0)


class DataBoundaryTests(unittest.TestCase):
    def test_market_panel_excludes_pre_boundary_and_incomplete_bars(self) -> None:
        boundary = datetime(2026, 8, 10, 17, 5, tzinfo=UTC)
        captured = datetime(2026, 8, 10, 17, 20, tzinfo=UTC)
        source = pd.DataFrame(
            {
                "time": pd.to_datetime(
                    [
                        "2026-08-10T17:00:00Z",
                        "2026-08-10T17:05:00Z",
                        "2026-08-10T17:10:00Z",
                        "2026-08-10T17:15:00Z",
                        "2026-08-10T17:20:00Z",
                    ],
                    utc=True,
                ),
                "open": [1, 2, 3, 4, 5],
                "close": [1, 2, 3, 4, 5],
            }
        )
        with patch.object(qef, "load_candles", return_value=source):
            result, coverage = qef.build_market_panel([INST], boundary, captured)

        self.assertEqual(list(result.index), list(pd.to_datetime([
            "2026-08-10T17:05:00Z",
            "2026-08-10T17:10:00Z",
            "2026-08-10T17:15:00Z",
        ], utc=True)))
        self.assertEqual(coverage["commonBarCoverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
