from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pandas as pd

from aggressive_sector_plan import (
    active_session_date,
    build_sector_plan,
    intraday_confirmation,
    load_playbook,
    resolve_sector_data_config,
)


def synthetic_candles(inst_id: str, sessions: int = 20) -> pd.DataFrame:
    rows = []
    start = datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc)
    day = 0
    current = start
    while day < sessions:
        if current.weekday() < 5:
            base = Decimal("100") + Decimal(day)
            for bar in range(78):
                timestamp = current + timedelta(minutes=5 * bar)
                rows.append(
                    {
                        "time": timestamp,
                        "open": float(base),
                        "high": float(base + Decimal("2")),
                        "low": float(base - Decimal("2")),
                        "close": float(base + Decimal("1")),
                        "volume": 1.0,
                        "inst_id": inst_id,
                        "timeframe": "5m",
                    }
                )
            day += 1
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def loader(inst_id: str, timeframe: str) -> pd.DataFrame:
    assert timeframe == "5m"
    return synthetic_candles(inst_id)


def current_session_candles(inst_id: str, direction: str) -> pd.DataFrame:
    rows = []
    start = datetime(2026, 8, 12, 13, 30, tzinfo=timezone.utc)
    for bar in range(6):
        if bar < 3:
            open_, high, low, close = Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100")
        elif direction == "long":
            open_, high, low, close = Decimal("101"), Decimal("103"), Decimal("100.5"), Decimal("102")
        else:
            open_, high, low, close = Decimal("99"), Decimal("99.5"), Decimal("97"), Decimal("98")
        rows.append(
            {
                "time": start + timedelta(minutes=5 * bar),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 10.0,
                "inst_id": inst_id,
                "timeframe": "5m",
            }
        )
    return pd.DataFrame(rows)


def session_map(inst_ids: list[str], direction: str) -> dict[str, pd.DataFrame]:
    return {inst_id: current_session_candles(inst_id, direction) for inst_id in inst_ids}


METADATA = {
    "SNDK-USDT-SWAP": {"state": "live", "ctVal": "1", "lotSz": "0.001", "minSz": "0.001", "tickSz": "0.01"},
    "SOXL-USDT-SWAP": {"state": "live", "ctVal": "1", "lotSz": "0.01", "minSz": "0.01", "tickSz": "0.01"},
    "TSLA-USDT-SWAP": {"state": "live", "ctVal": "1", "lotSz": "0.01", "minSz": "0.01", "tickSz": "0.01"},
    "XAU-USDT-SWAP": {"state": "live", "ctVal": "0.001", "lotSz": "1", "minSz": "1", "tickSz": "0.1"},
}


class AggressiveSectorPlanTest(unittest.TestCase):
    def test_semiconductor_allocates_price_risk_between_fixed_legs(self) -> None:
        plan = build_sector_plan(
            sector="semiconductor",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            candles_loader=loader,
            generated_at="2026-08-12T00:00:00Z",
        )

        self.assertEqual(plan["status"], "reference_only")
        self.assertEqual(plan["risk"]["priceRiskBudget"], "0.84")
        self.assertEqual(sum(Decimal(item["legPriceRiskBudget"]) for item in plan["items"]), Decimal("0.84"))
        self.assertEqual([item["riskWeight"] for item in plan["items"]], ["0.6", "0.4"])
        self.assertTrue(all(item["atrAsOf"] for item in plan["items"]))

    def test_long_and_short_protection_levels_have_correct_direction(self) -> None:
        long_plan = build_sector_plan(
            sector="ev_growth",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            entry_prices={"TSLA-USDT-SWAP": Decimal("102")},
            market_metadata={"TSLA-USDT-SWAP": METADATA["TSLA-USDT-SWAP"]},
            candles_loader=loader,
            current_session_candles=session_map(["TSLA-USDT-SWAP"], "long"),
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        )
        short_plan = build_sector_plan(
            sector="ev_growth",
            direction="short",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            entry_prices={"TSLA-USDT-SWAP": Decimal("98")},
            market_metadata={"TSLA-USDT-SWAP": METADATA["TSLA-USDT-SWAP"]},
            candles_loader=loader,
            current_session_candles=session_map(["TSLA-USDT-SWAP"], "short"),
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        )

        long_item = long_plan["items"][0]
        short_item = short_plan["items"][0]
        self.assertEqual(long_plan["status"], "ready_for_review")
        self.assertLess(Decimal(long_item["stopLossPrice"]), Decimal(long_item["entryPrice"]))
        self.assertGreater(Decimal(long_item["takeProfit1Price"]), Decimal(long_item["entryPrice"]))
        self.assertEqual(
            Decimal(long_item["takeProfit1Size"]) + Decimal(long_item["takeProfit2Size"]),
            Decimal(long_item["size"]),
        )
        self.assertEqual(short_plan["status"], "ready_for_review")
        self.assertGreater(Decimal(short_item["stopLossPrice"]), Decimal(short_item["entryPrice"]))
        self.assertLess(Decimal(short_item["takeProfit1Price"]), Decimal(short_item["entryPrice"]))

    def test_leverage_outside_two_to_five_is_blocked(self) -> None:
        plan = build_sector_plan(
            sector="semiconductor",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("6"),
            candles_loader=loader,
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertIn("between_2_and_5", plan["reason"])

    def test_missing_one_leg_entry_stays_blocked(self) -> None:
        plan = build_sector_plan(
            sector="semiconductor",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            entry_prices={"SNDK-USDT-SWAP": Decimal("100")},
            market_metadata=METADATA,
            candles_loader=loader,
            current_session_candles=session_map(["SNDK-USDT-SWAP", "SOXL-USDT-SWAP"], "long"),
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(plan["status"], "blocked")
        missing = next(item for item in plan["items"] if item["instId"] == "SOXL-USDT-SWAP")
        self.assertEqual(missing["reason"], "actual_entry_price_required_after_manual_confirmation")

    def test_invalid_data_does_not_become_reference_only(self) -> None:
        def empty_loader(inst_id: str, timeframe: str) -> pd.DataFrame:
            return pd.DataFrame()

        plan = build_sector_plan(
            sector="ev_growth",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            candles_loader=empty_loader,
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["items"][0]["reason"], "no_complete_us_sessions")

    def test_intraday_gate_requires_vwap_and_opening_range_confirmation(self) -> None:
        playbook = load_playbook()
        long_gate = intraday_confirmation(
            current_session_candles("TSLA-USDT-SWAP", "long"),
            direction="long",
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
            data_config=playbook["data"],
            execution_config=playbook["execution"],
        )
        wrong_direction = intraday_confirmation(
            current_session_candles("TSLA-USDT-SWAP", "long"),
            direction="short",
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
            data_config=playbook["data"],
            execution_config=playbook["execution"],
        )

        self.assertEqual(long_gate["status"], "confirmed")
        self.assertTrue(long_gate["checks"]["vwapPassed"])
        self.assertTrue(long_gate["checks"]["openingRangePassed"])
        self.assertEqual(wrong_direction["status"], "blocked")
        self.assertFalse(wrong_direction["checks"]["vwapPassed"])
        self.assertFalse(wrong_direction["checks"]["openingRangePassed"])

    def test_entry_prices_do_not_bypass_intraday_gate(self) -> None:
        plan = build_sector_plan(
            sector="ev_growth",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            entry_prices={"TSLA-USDT-SWAP": Decimal("102")},
            market_metadata={"TSLA-USDT-SWAP": METADATA["TSLA-USDT-SWAP"]},
            candles_loader=loader,
            current_session_candles=session_map(["TSLA-USDT-SWAP"], "long"),
            as_of=datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["items"][0]["reason"], "entry_gate_outside_us_weekday_session")

    def test_take_profit_configuration_drives_levels_and_split(self) -> None:
        playbook = deepcopy(load_playbook())
        playbook["risk"]["takeProfit1R"] = 0.5
        playbook["risk"]["takeProfit2R"] = 2.0
        playbook["risk"]["takeProfit1ClosePct"] = 25.0
        plan = build_sector_plan(
            sector="ev_growth",
            direction="long",
            equity=Decimal("100"),
            leverage=Decimal("3"),
            entry_prices={"TSLA-USDT-SWAP": Decimal("102")},
            playbook=playbook,
            market_metadata={"TSLA-USDT-SWAP": METADATA["TSLA-USDT-SWAP"]},
            candles_loader=loader,
            current_session_candles=session_map(["TSLA-USDT-SWAP"], "long"),
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        )

        item = plan["items"][0]
        self.assertEqual(plan["status"], "ready_for_review")
        self.assertEqual(plan["risk"]["takeProfit1R"], "0.5")
        self.assertEqual(plan["risk"]["takeProfit2R"], "2.0")
        self.assertEqual(Decimal(item["takeProfit1Size"]), Decimal("0.14"))
        self.assertEqual(
            Decimal(item["takeProfit1Size"]) + Decimal(item["takeProfit2Size"]),
            Decimal(item["size"]),
        )
        self.assertEqual(item["takeProfit1Price"], "103.79")
        self.assertEqual(item["takeProfit2Price"], "109.14")

    def test_entry_price_far_from_public_close_is_blocked(self) -> None:
        plan = build_sector_plan(
            sector="ev_growth",
            direction="long",
            equity=Decimal("42"),
            leverage=Decimal("3"),
            entry_prices={"TSLA-USDT-SWAP": Decimal("90")},
            market_metadata={"TSLA-USDT-SWAP": METADATA["TSLA-USDT-SWAP"]},
            candles_loader=loader,
            current_session_candles=session_map(["TSLA-USDT-SWAP"], "long"),
            as_of=datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["items"][0]["reason"], "entry_price_too_far_from_latest_public_close")

    def test_precious_metals_uses_comex_overnight_session(self) -> None:
        playbook = load_playbook()
        data = resolve_sector_data_config(playbook, playbook["sectors"]["precious_metals"])
        self.assertEqual(data["sessionOpen"], "18:00")
        self.assertEqual(data["sessionClose"], "17:00")
        wednesday_night = datetime(2026, 8, 13, 3, 52, tzinfo=timezone.utc)
        session_date = active_session_date(
            wednesday_night,
            session_timezone="America/New_York",
            session_open=time.fromisoformat("18:00"),
            session_close=time.fromisoformat("17:00"),
        )
        self.assertEqual(session_date.isoformat(), "2026-08-13")

    def test_gold_short_confirms_below_comex_vwap_and_opening_range(self) -> None:
        rows = []
        start = datetime(2026, 8, 12, 22, 0, tzinfo=timezone.utc)
        for bar in range(12):
            if bar < 3:
                open_, high, low, close = Decimal("4410"), Decimal("4412"), Decimal("4408"), Decimal("4410")
            else:
                open_, high, low, close = Decimal("4406"), Decimal("4407"), Decimal("4400"), Decimal("4402")
            rows.append(
                {
                    "time": start + timedelta(minutes=5 * bar),
                    "open": float(open_),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": 10.0,
                    "inst_id": "XAU-USDT-SWAP",
                    "timeframe": "5m",
                }
            )
        playbook = load_playbook()
        data = resolve_sector_data_config(playbook, playbook["sectors"]["precious_metals"])
        gate = intraday_confirmation(
            pd.DataFrame(rows),
            direction="short",
            as_of=datetime(2026, 8, 12, 23, 5, tzinfo=timezone.utc),
            data_config=data,
            execution_config=playbook["execution"],
        )
        self.assertEqual(gate["status"], "confirmed")
        self.assertEqual(gate["sessionDate"], "2026-08-13")
        self.assertTrue(gate["checks"]["vwapPassed"])
        self.assertTrue(gate["checks"]["openingRangePassed"])


if __name__ == "__main__":
    unittest.main()
