from __future__ import annotations

import unittest
from datetime import date

import numpy as np
import pandas as pd

from qqq_active_enhancement_research import (
    fact_records,
    factor_ic_rows,
    fundamental_snapshot_asof,
    industry_bucket,
    latest_fact_asof,
    neutral_weights,
    prepare_fundamental_records,
    rebalance_dates,
    simulate_overlay,
)


def company_facts() -> dict:
    def row(value: float, filed: str, *, start: str | None = "2023-01-01", end: str = "2023-12-31", form: str = "10-K") -> dict:
        result = {"val": value, "filed": filed, "end": end, "form": form, "fp": "FY", "accn": filed}
        if start:
            result["start"] = start
        return result

    return {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": [row(1000, "2024-02-15"), row(9999, "2024-04-15")]}},
                "NetIncomeLoss": {"units": {"USD": [row(100, "2024-02-15"), row(-900, "2024-04-15")]}},
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [row(120, "2024-02-15"), row(-800, "2024-04-15")]}
                },
                "GrossProfit": {"units": {"USD": [row(400, "2024-02-15")] }},
                "Assets": {"units": {"USD": [row(2000, "2024-02-15", start=None)]}},
                "StockholdersEquity": {"units": {"USD": [row(800, "2024-02-15", start=None)]}},
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {"shares": [row(10, "2024-02-15"), row(20, "2024-05-01", start="2024-01-01", end="2024-03-31", form="10-Q")]}
                },
            }
        }
    }


class QqqActiveEnhancementResearchTests(unittest.TestCase):
    def test_sec_fact_is_unavailable_until_after_actual_filed_date(self) -> None:
        records = fact_records(company_facts(), ("Revenues",), units=("USD",), annual_only=True)
        self.assertIsNone(latest_fact_asof(records, date(2024, 2, 15)))
        self.assertEqual(latest_fact_asof(records, date(2024, 2, 16))["value"], 1000)
        self.assertEqual(latest_fact_asof(records, date(2024, 4, 16))["value"], 9999)

    def test_fundamental_snapshot_does_not_backfill_future_amendment(self) -> None:
        prepared = prepare_fundamental_records(company_facts())
        before = fundamental_snapshot_asof(prepared, date(2024, 4, 1), 50.0)
        after = fundamental_snapshot_asof(prepared, date(2024, 4, 16), 50.0)
        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        self.assertAlmostEqual(before.roa, 0.05)
        self.assertAlmostEqual(after.roa, -0.45)
        self.assertEqual(before.latest_filed, "2024-02-15")

    def test_neutral_weights_obey_all_limits(self) -> None:
        symbols = [f"S{value}" for value in range(12)]
        frame = pd.DataFrame(
            {
                "industry": ["tech"] * 6 + ["consumer"] * 6,
                "beta": np.linspace(0.7, 1.3, 12),
                "size_z": np.linspace(-1.5, 1.5, 12),
                "composite": [1.5, 0.9, 0.4, -0.2, -0.8, -1.4, 1.2, 0.7, 0.1, -0.3, -0.9, -1.1],
            },
            index=symbols,
        )
        covariance = np.diag(np.linspace(0.04, 0.09, 12))
        weights, diagnostics = neutral_weights(frame, covariance)
        self.assertTrue(diagnostics.success)
        self.assertLessEqual(weights.abs().sum(), 0.200000001)
        self.assertLessEqual(weights.abs().max(), 0.015000001)
        self.assertLessEqual(diagnostics.ex_ante_tracking_error, 0.030000001)
        self.assertLess(diagnostics.dollar_residual, 1e-10)
        self.assertLess(diagnostics.beta_residual, 1e-10)
        self.assertLess(diagnostics.size_residual, 1e-10)
        self.assertLess(diagnostics.industry_residual, 1e-10)

    def test_overlay_holds_weights_between_rebalances(self) -> None:
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        returns = pd.DataFrame({"QQQ": 0.0, "A": 0.01, "B": -0.01}, index=dates)
        weights = {dates[0]: pd.Series({"A": 0.01, "B": -0.01})}
        daily, trades = simulate_overlay(
            returns,
            weights,
            transaction_cost_bps=0.0,
            short_borrow_bps=0.0,
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(len(daily), 4)
        self.assertTrue((daily["activeNetReturn"] > 0).all())
        self.assertTrue((daily["gross"] == 0.02).all())

    def test_monthly_schedule_uses_last_trading_day(self) -> None:
        calendar = pd.date_range("2024-01-02", "2024-02-29", freq="B")
        dates = rebalance_dates(calendar, "monthly")
        self.assertEqual([value.date().isoformat() for value in dates], ["2024-01-31"])

    def test_monthly_schedule_never_treats_partial_last_month_as_complete(self) -> None:
        calendar = pd.date_range("2024-01-02", "2024-03-08", freq="B")
        dates = rebalance_dates(calendar, "monthly")
        self.assertEqual(
            [value.date().isoformat() for value in dates],
            ["2024-01-31", "2024-02-29"],
        )

    def test_neutralized_ic_uses_actual_active_weight_direction(self) -> None:
        dates = pd.to_datetime(["2024-01-31", "2024-02-29"])
        symbols = [f"S{value}" for value in range(6)]
        signal = pd.DataFrame(
            {
                "momentum": np.arange(6),
                "quality": np.arange(6),
                "value": np.arange(6),
                "low_residual_volatility": np.arange(6),
                "composite": np.arange(6),
            },
            index=symbols,
        )
        signals = {dates[0]: signal, dates[1]: signal}
        active = pd.Series(np.linspace(-0.01, 0.01, 6), index=symbols)
        prices = {
            symbol: pd.DataFrame(
                {"adj_close": [100.0, 100.0 * (1.0 + active[symbol])]}, index=dates
            )
            for symbol in symbols
        }
        rows = factor_ic_rows(signals, prices, {dates[0]: active, dates[1]: active})
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["neutralized_composite"], 1.0)
        self.assertGreater(rows[0]["activePeriodReturn"], 0)

    def test_sic_mapping_is_broad_and_deterministic(self) -> None:
        self.assertEqual(industry_bucket("3674"), "information_technology")
        self.assertEqual(industry_bucket("2834"), "health_care")
        self.assertEqual(industry_bucket("5331"), "consumer")


if __name__ == "__main__":
    unittest.main()
