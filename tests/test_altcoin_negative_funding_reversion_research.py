from __future__ import annotations

import copy
import unittest

import pandas as pd

import altcoin_negative_funding_reversion_research as research


def config() -> dict:
    payload = research.read_json(research.DEFAULT_PREREGISTRATION)
    return copy.deepcopy(payload)


def v2_config() -> dict:
    payload = research.read_json(research.V2_PREREGISTRATION)
    return copy.deepcopy(payload)


def v3_config() -> dict:
    payload = research.read_json(research.V3_PREREGISTRATION)
    return copy.deepcopy(payload)


def v4_config() -> dict:
    payload = research.read_json(research.V4_PREREGISTRATION)
    return copy.deepcopy(payload)


def candle_frame(
    start: str,
    periods: int,
    *,
    open_price: float = 100.0,
    close_price: float = 100.0,
    volume: float = 1_000_000.0,
) -> pd.DataFrame:
    times = pd.date_range(start, periods=periods, freq="5min", tz="UTC")
    closes = [
        open_price + (close_price - open_price) * index / max(1, periods - 1)
        for index in range(periods)
    ]
    return pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": [value * 1.001 for value in closes],
            "low": [value * 0.999 for value in closes],
            "close": closes,
            "volume": volume,
        }
    )


def funding_frame(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "funding_time": [pd.Timestamp(at) for at, _ in rows],
            "realized_rate": [rate for _, rate in rows],
        }
    )


class FrozenSignalTests(unittest.TestCase):
    def test_signal_uses_current_realized_funding_and_enters_later(self) -> None:
        cfg = config()
        cfg["universe"]["contractValue"]["DOGE-USDT-SWAP"] = 1.0
        candles = candle_frame(
            "2026-01-01T08:00:00Z", 73 * 12 + 2, open_price=100.0, close_price=125.0
        )
        decision_at = pd.Timestamp("2026-01-04T08:00:00Z")
        funding = funding_frame(
            [
                ("2026-01-04T00:00:00Z", -0.0010),
                ("2026-01-04T08:00:00Z", -0.0007),
            ]
        )

        row = research.point_features(
            cfg, "DOGE-USDT-SWAP", decision_at, candles, funding
        )

        self.assertTrue(row["eligibleBeforeRank"])
        self.assertGreaterEqual(row["priceReturn"], 0.20)
        self.assertAlmostEqual(row["fundingImprovement"], 0.0003)
        self.assertEqual(row["entryAt"], "2026-01-04T08:05:00Z")

    def test_future_funding_is_not_visible(self) -> None:
        cfg = config()
        candles = candle_frame(
            "2026-01-01T07:55:00Z", 73 * 12 + 2, open_price=100.0, close_price=125.0
        )
        funding = funding_frame(
            [
                ("2026-01-04T00:00:00Z", -0.0010),
                ("2026-01-04T08:00:00Z", -0.0007),
            ]
        )

        row = research.point_features(
            cfg,
            "DOGE-USDT-SWAP",
            pd.Timestamp("2026-01-04T07:55:00Z"),
            candles,
            funding,
        )

        self.assertFalse(row["eligibleBeforeRank"])
        self.assertIn("funding_observation_missing", row["reasons"])

    def test_v4_accepts_moderate_earlier_funding_that_v3_rejects(self) -> None:
        candles = candle_frame(
            "2026-01-01T08:00:00Z", 73 * 12 + 2,
            open_price=100.0, close_price=125.0,
        )
        funding = funding_frame([
            ("2026-01-04T00:00:00Z", -0.0004),
            ("2026-01-04T08:00:00Z", -0.0001),
        ])
        decision_at = pd.Timestamp("2026-01-04T08:00:00Z")

        v3_row = research.point_features(
            v3_config(), "BEAT-USDT-SWAP", decision_at, candles, funding
        )
        v4_row = research.point_features(
            v4_config(), "BEAT-USDT-SWAP", decision_at, candles, funding
        )

        self.assertFalse(v3_row["eligibleBeforeRank"])
        self.assertIn("earlier_funding_not_negative_enough", v3_row["reasons"])
        self.assertTrue(v4_row["eligibleBeforeRank"])


class ExitAndAccountingTests(unittest.TestCase):
    def signal(self, entry_at: str = "2026-01-01T00:05:00Z") -> research.Signal:
        return research.Signal(
            decision_at=pd.Timestamp("2026-01-01T00:00:00Z"),
            entry_at=pd.Timestamp(entry_at),
            inst_id="DOGE-USDT-SWAP",
            rank=1,
            price_return=0.25,
            turnover_usdt=20_000_000.0,
            earlier_funding=-0.001,
            latest_funding=-0.0007,
            funding_improvement=0.0003,
        )

    def test_big_bearish_hour_exits_at_next_five_minute_open(self) -> None:
        cfg = config()
        candles = candle_frame("2026-01-01T00:00:00Z", 30)
        bearish = candles["time"].between(
            pd.Timestamp("2026-01-01T01:00:00Z"),
            pd.Timestamp("2026-01-01T01:55:00Z"),
        )
        steps = list(range(int(bearish.sum())))
        values = [100.0 - 5.0 * index / (len(steps) - 1) for index in steps]
        candles.loc[bearish, "open"] = values
        candles.loc[bearish, "close"] = values
        candles.loc[bearish, "high"] = [value + 0.2 for value in values]
        candles.loc[bearish, "low"] = [value - 0.2 for value in values]
        candles.loc[
            candles["time"] == pd.Timestamp("2026-01-01T02:00:00Z"), "open"
        ] = 94.8

        plan = research.plan_trade(cfg, self.signal(), candles)

        self.assertEqual(plan.exit_reason, "big_bearish_candle_take_profit")
        self.assertEqual(plan.exit_at, pd.Timestamp("2026-01-01T02:00:00Z"))
        self.assertLessEqual(plan.bearish_hour_return, -0.04)

    def test_negative_funding_costs_an_open_short(self) -> None:
        cfg = config()
        cfg["costs"]["takerFeePerSideBps"] = 0.0
        cfg["costs"]["adverseSlippagePerSideBps"] = 0.0
        candles = candle_frame("2026-01-01T00:05:00Z", 98)
        signal = self.signal()
        plan = research.TradePlan(
            signal=signal,
            entry_at=pd.Timestamp("2026-01-01T00:05:00Z"),
            entry_reference=100.0,
            exit_at=pd.Timestamp("2026-01-01T08:05:00Z"),
            exit_reference=100.0,
            exit_reason="time_exit",
            bearish_hour_return=None,
            bearish_close_location=None,
        )
        funding = funding_frame(
            [("2026-01-01T08:00:00Z", -0.0010)]
        )

        result = research.simulate_portfolio(
            cfg,
            [plan],
            {"DOGE-USDT-SWAP": candles},
            {"DOGE-USDT-SWAP": funding},
            cost_multiplier=0.0,
            include_funding=True,
        )

        self.assertLess(result["fundingPnl"], 0.0)
        self.assertLess(result["returnPct"], 0.0)

    def test_no_stop_v2_models_isolated_liquidation(self) -> None:
        cfg = v2_config()
        candles = candle_frame("2026-01-01T00:05:00Z", 4)
        candles.loc[1, "high"] = 146.0

        plan = research.plan_trade(cfg, self.signal(), candles)

        self.assertEqual(plan.exit_reason, "modeled_liquidation")
        self.assertEqual(plan.exit_at, pd.Timestamp("2026-01-01T00:10:00Z"))
        self.assertAlmostEqual(plan.exit_reference, 145.725)


class RegistrationTests(unittest.TestCase):
    def test_frozen_registration_is_research_only_and_small(self) -> None:
        cfg = config()
        research.validate_preregistration(cfg)

        self.assertFalse(cfg["paperOrLiveAuthorized"])
        self.assertEqual(cfg["execution"]["leverage"], 1.0)
        self.assertLessEqual(
            cfg["execution"]["notionalFractionPerPosition"]
            * cfg["execution"]["maximumConcurrentPositions"],
            0.10,
        )

    def test_v2_is_forward_only_two_times_isolated_and_no_stop(self) -> None:
        cfg = v2_config()
        research.validate_preregistration(cfg)

        self.assertFalse(cfg["paperOrLiveAuthorized"])
        self.assertFalse(cfg["evidencePolicy"]["developmentReplayAllowed"])
        self.assertEqual(cfg["execution"]["leverage"], 2.0)
        self.assertEqual(cfg["execution"]["marginMode"], "isolated")
        self.assertEqual(cfg["execution"]["marginFractionPerPosition"], 0.05)
        self.assertEqual(cfg["execution"]["notionalFractionPerPosition"], 0.10)
        self.assertIsNone(cfg["execution"]["hardStopFraction"])

        with self.assertRaisesRegex(ValueError, "forward-only"):
            research.run_replay(cfg, research.V2_PREREGISTRATION)

    def test_v3_has_four_independent_isolated_positions_and_no_stop(self) -> None:
        cfg = v3_config()
        research.validate_preregistration(cfg)

        execution = cfg["execution"]
        self.assertFalse(cfg["paperOrLiveAuthorized"])
        self.assertFalse(cfg["evidencePolicy"]["developmentReplayAllowed"])
        self.assertEqual(cfg["signal"]["crossSectionTopN"], 4)
        self.assertEqual(cfg["signal"]["crossSectionRankBy"], "funding_improvement")
        self.assertEqual(execution["maximumConcurrentPositions"], 4)
        self.assertEqual(execution["marginMode"], "isolated")
        self.assertEqual(execution["marginFractionPerPosition"], 0.05)
        self.assertEqual(execution["maximumConcurrentMarginFraction"], 0.20)
        self.assertEqual(execution["maximumGrossNotionalFraction"], 0.40)
        self.assertIsNone(execution["hardStopFraction"])

        with self.assertRaisesRegex(ValueError, "forward-only"):
            research.run_replay(cfg, research.V3_PREREGISTRATION)

    def test_v3_rejects_shared_margin_without_a_hard_stop(self) -> None:
        cfg = v3_config()
        cfg["execution"]["marginMode"] = "cross"

        with self.assertRaisesRegex(ValueError, "requires isolated margin"):
            research.validate_preregistration(cfg)

    def test_v3_rejects_more_positions_than_the_frozen_risk_budget(self) -> None:
        cfg = v3_config()
        cfg["execution"]["maximumConcurrentPositions"] = 5

        with self.assertRaisesRegex(ValueError, "margin exceeds its configured cap"):
            research.validate_preregistration(cfg)

    def test_v4_only_relaxes_the_earlier_funding_threshold(self) -> None:
        v3 = v3_config()
        v4 = v4_config()
        research.validate_preregistration(v4)

        self.assertFalse(v4["paperOrLiveAuthorized"])
        self.assertFalse(v4["evidencePolicy"]["developmentReplayAllowed"])
        self.assertEqual(v3["universe"], v4["universe"])
        self.assertEqual(v3["execution"], v4["execution"])
        self.assertEqual(v3["costs"], v4["costs"])

        v3_signal = copy.deepcopy(v3["signal"])
        v4_signal = copy.deepcopy(v4["signal"])
        self.assertEqual(v3_signal.pop("earlierFundingMaximum"), -0.0005)
        self.assertEqual(v4_signal.pop("earlierFundingMaximum"), -0.0003)
        v3_signal.pop("fundingRule")
        v4_signal.pop("fundingRule")
        self.assertEqual(v3_signal, v4_signal)

        with self.assertRaisesRegex(ValueError, "forward-only"):
            research.run_replay(v4, research.V4_PREREGISTRATION)

    def test_v3_ranks_capacity_by_funding_improvement(self) -> None:
        cfg = v3_config()
        cfg["universe"]["instruments"] = ["A", "B"]
        cfg["universe"]["contractValue"] = {"A": 1.0, "B": 1.0}
        cfg["signal"]["crossSectionTopN"] = 1
        candles = {
            "A": candle_frame(
                "2026-01-01T08:00:00Z", 73 * 12 + 2,
                open_price=100.0, close_price=150.0,
            ),
            "B": candle_frame(
                "2026-01-01T08:00:00Z", 73 * 12 + 2,
                open_price=100.0, close_price=130.0,
            ),
        }
        funding = {
            "A": funding_frame([
                ("2026-01-04T00:00:00Z", -0.0010),
                ("2026-01-04T08:00:00Z", -0.0007),
            ]),
            "B": funding_frame([
                ("2026-01-04T00:00:00Z", -0.0012),
                ("2026-01-04T08:00:00Z", -0.0007),
            ]),
        }

        signals, audit = research.build_signals(
            cfg,
            candles,
            funding,
            pd.Timestamp("2026-01-04T08:00:00Z"),
            pd.Timestamp("2026-01-04T08:00:00Z"),
        )

        self.assertEqual([signal.inst_id for signal in signals], ["B"])
        rejected = next(row for row in audit if row["instId"] == "A")
        self.assertIn("outside_cross_section_top_n", rejected["reasons"])


if __name__ == "__main__":
    unittest.main()
