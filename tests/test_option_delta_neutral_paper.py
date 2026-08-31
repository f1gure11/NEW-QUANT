from __future__ import annotations

import unittest

from option_delta_neutral_paper import (
    OptionLeg,
    StraddlePair,
    SwapSpec,
    _metrics,
    shock_scenarios,
    size_plan,
)


def pair() -> StraddlePair:
    common = dict(
        expiry_ms=2_000_000,
        strike=100.0,
        ct_val=1.0,
        ct_mult=1.0,
        tick_size=0.1,
        ask_px=2.0,
        ask_sz=100.0,
        bid_px=1.9,
        bid_sz=100.0,
        gamma=0.1,
        theta_day=-0.01,
        vega=0.1,
        bid_vol=0.2,
        ask_vol=0.21,
        quote_ts=1_000,
        greek_ts=1_000,
    )
    return StraddlePair(
        underlying="TEST",
        option_family="TEST-USD",
        spot_px=100.0,
        call=OptionLeg(inst_id="TEST-C", option_type="C", delta=0.6, **common),
        put=OptionLeg(inst_id="TEST-P", option_type="P", delta=-0.4, **common),
        swap=SwapSpec(
            inst_id="TEST-USDT-SWAP",
            ct_val=1.0,
            ct_mult=1.0,
            lot_size=0.1,
            min_size=0.1,
            last_px=100.0,
            bid_px=99.9,
            ask_px=100.1,
        ),
        retrieved_at="2026-01-01T00:00:00+00:00",
    )


class OptionDeltaNeutralPaperTests(unittest.TestCase):
    def test_delta_threshold_is_in_underlying_units(self) -> None:
        metrics = _metrics(
            pair(),
            1,
            equity=1_000.0,
            delta_threshold_pct=5.0,
            jump_shock_pct=1.0,
            hedge_leverage=1.0,
        )
        self.assertAlmostEqual(metrics.delta_threshold_units, 0.05)
        self.assertTrue(metrics.initial_delta_breach)
        self.assertAlmostEqual(metrics.residual_delta_units, 0.0)

    def test_size_plan_respects_premium_and_theta_budgets(self) -> None:
        metrics = size_plan(
            pair(),
            equity=1_000.0,
            premium_budget_pct=1.0,
            max_theta_day_pct=0.10,
            max_hedge_margin_pct=10.0,
            max_jump_loss_pct=1.0,
            jump_shock_pct=1.0,
            delta_threshold_pct=5.0,
            hedge_leverage=1.0,
            max_contracts=1_000,
        )
        self.assertLessEqual(metrics.premium_pct_equity, 1.0)
        self.assertLessEqual(metrics.theta_pct_equity, 0.10)

    def test_shock_scenarios_rehedge_after_delta_breach(self) -> None:
        metrics = _metrics(
            pair(),
            10,
            equity=1_000.0,
            delta_threshold_pct=5.0,
            jump_shock_pct=1.0,
            hedge_leverage=1.0,
        )
        rows = shock_scenarios(
            pair(), metrics, jump_shock_pct=1.0, delta_threshold_pct=5.0
        )
        one_pct = next(row for row in rows if row["shock_pct"] == 1.0)
        self.assertTrue(one_pct["trigger"])
        self.assertNotEqual(one_pct["additional_hedge_contracts"], 0.0)


if __name__ == "__main__":
    unittest.main()
