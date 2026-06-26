from __future__ import annotations

import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backtest.okx_grid_backtest import Candle
from market_selector import MarketCandidate, MarketSelectorConfig
from portfolio_allocator import AllocationConfig
from portfolio_backtest import (
    PortfolioBacktestConfig,
    contract_size_for_margin,
    grid_config_for_candidate,
    latest_ml_regime_profile,
    pool_window_bars,
    pool_window_metrics,
    rank_rows,
    run_portfolio_backtest,
    select_trend_backtest,
)
from scoring import ScoreWeights


class FakeClient:
    def request(self, method, path, *, params=None, body=None, private=False):
        raise AssertionError("empty candidate test should not call OKX")


def candidate() -> MarketCandidate:
    return MarketCandidate(
        inst_id="AAA-USDT-SWAP",
        inst_family="AAA-USDT",
        base_ccy="AAA",
        quote_ccy="USDT",
        settle_ccy="USDT",
        ct_val=Decimal("1"),
        tick_sz=Decimal("0.01"),
        lot_sz=Decimal("1"),
        min_sz=Decimal("1"),
        state="live",
        last=Decimal("100"),
        bid_px=Decimal("99.99"),
        ask_px=Decimal("100.01"),
        spread_bps=Decimal("2"),
        quote_volume_24h=Decimal("10000000"),
        volume_24h=Decimal("100000"),
    )


class PortfolioBacktestTest(unittest.TestCase):
    def test_contract_size_respects_lot_and_min_size(self) -> None:
        size = contract_size_for_margin(
            equity=Decimal("100"),
            margin_pct=Decimal("10"),
            leverage=Decimal("3"),
            mark_px=Decimal("19"),
            ct_val=Decimal("0.1"),
            lot_sz=Decimal("0.1"),
            min_sz=Decimal("0.5"),
        )

        self.assertEqual(size, Decimal("15.7"))

    def test_rank_rows_places_successes_first(self) -> None:
        rows = rank_rows(
            [
                {"inst_id": "ERR", "status": "error", "score": ""},
                {"inst_id": "LOW", "status": "ok", "score": Decimal("1")},
                {"inst_id": "HIGH", "status": "ok", "score": Decimal("2")},
            ]
        )

        self.assertEqual([row["inst_id"] for row in rows], ["HIGH", "LOW", "ERR"])
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[1]["rank"], 2)
        self.assertEqual(rows[2]["rank"], "")

    def test_pool_window_metrics_uses_recent_5h_window(self) -> None:
        candles = [
            Candle(ts=index, open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal(100 + index), volume=Decimal("1"))
            for index in range(400)
        ]
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
            backtest_bar="1m",
            pool_window_hours=Decimal("5"),
        )

        metrics = pool_window_metrics(candles, config)

        self.assertEqual(pool_window_bars(config), 300)
        self.assertEqual(metrics["pool_window_bars"], 300)
        self.assertGreater(metrics["pool_avg_abs_bps"], Decimal("0"))
        self.assertGreater(metrics["pool_trend_bps"], Decimal("0"))

    def test_trend_compare_selects_better_backtest_variant(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
            trend_filter="compare",
        )
        candles = [
            Candle(ts=index, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1"))
            for index in range(40)
        ]

        def fake_run_variant(_candidate, _candles, _config, *, trend_filter):
            score = Decimal("3") if trend_filter == "auto" else Decimal("1")
            return {"trend_filter": trend_filter, "result": SimpleNamespace(), "score": SimpleNamespace(score=score)}

        with patch("portfolio_backtest.run_candidate_variant", side_effect=fake_run_variant) as mocked:
            selected, baseline, auto_trend = select_trend_backtest(candidate(), candles, config)

        self.assertEqual([call.kwargs["trend_filter"] for call in mocked.call_args_list], ["off", "auto"])
        self.assertEqual(selected["trend_filter"], "auto")
        self.assertEqual(baseline["trend_filter"], "off")
        self.assertEqual(auto_trend["trend_filter"], "auto")

    def test_grid_config_for_candidate_applies_selected_trend_filter(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
            trend_filter="compare",
        )
        candles = [
            Candle(ts=index, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1"))
            for index in range(40)
        ]

        backtest_config = grid_config_for_candidate(candidate(), candles, config, trend_filter="auto")

        self.assertEqual(backtest_config.trend_filter, "auto")
        self.assertEqual(backtest_config.trend_lookback, config.trend_lookback)
        self.assertEqual(backtest_config.trend_threshold_bps, config.trend_threshold_bps)

    def test_default_grid_config_uses_active_rolling_profile(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
        )
        candles = [
            Candle(ts=index, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1"))
            for index in range(40)
        ]

        backtest_config = grid_config_for_candidate(candidate(), candles, config)

        self.assertEqual(backtest_config.grid_bps, Decimal("10"))
        self.assertEqual(backtest_config.min_tp_bps, Decimal("30"))
        self.assertEqual(backtest_config.total_loss_sl_pct, Decimal("4"))
        self.assertEqual(backtest_config.position_loss_sl_bps, Decimal("700"))
        self.assertEqual(backtest_config.max_open_orders_per_side, 5)
        self.assertEqual(backtest_config.max_actions_per_bar, 12)
        self.assertFalse(backtest_config.one_way_open)
        self.assertEqual(backtest_config.regime_filter, "off")
        self.assertEqual(backtest_config.trend_filter, "off")

    def test_grid_config_uses_latest_ml_regime_profile(self) -> None:
        profile = latest_ml_regime_profile(requested_mode="off")
        profile.enabled = True
        profile.mode = "rf"
        profile.model_path = "/tmp/regime_rf.joblib"
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
            ml_profile=profile,
        )
        candles = [
            Candle(ts=index, open=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close=Decimal("100"), volume=Decimal("1"))
            for index in range(40)
        ]

        backtest_config = grid_config_for_candidate(candidate(), candles, config)

        self.assertEqual(backtest_config.market_regime_filter, "rf")
        self.assertEqual(backtest_config.market_regime_model_path, "/tmp/regime_rf.joblib")
        self.assertEqual(backtest_config.market_regime_min_confidence, Decimal("0.52"))
        self.assertEqual(backtest_config.market_regime_mixed_policy, "price_anchor")

    def test_empty_candidates_write_reports(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
            backtest_pages=1,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("portfolio_backtest.select_candidates", return_value=[]):
                output_dir = run_portfolio_backtest(FakeClient(), config, tmpdir)

            candidates = json.loads((Path(output_dir) / "candidates.json").read_text(encoding="utf-8"))
            with (Path(output_dir) / "scores.csv").open("r", encoding="utf-8", newline="") as file:
                scores = list(csv.DictReader(file))
            rebalance = json.loads((Path(output_dir) / "rebalance_plan.json").read_text(encoding="utf-8"))
            summary = (Path(output_dir) / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(candidates["candidateCount"], 0)
        self.assertEqual(scores, [])
        self.assertEqual(rebalance["targets"], [])
        self.assertEqual(rebalance["actions"], [])
        self.assertIn("No candidates completed a backtest.", summary)

    def test_execution_runtime_uses_portfolio_cash_reserve_pct(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=1),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(cash_reserve_pct=Decimal("3"), max_risk_events=99),
            backtest_pages=1,
        )
        row = {
            "rank": 1,
            "status": "ok",
            "inst_id": "AAA-USDT-SWAP",
            "score": Decimal("1"),
            "fills": 10,
            "risk_events": 0,
            "quote_volume_24h": Decimal("10000000"),
            "pool_window_hours": Decimal("5"),
            "pool_window_bars": 300,
            "pool_avg_abs_bps": Decimal("5"),
            "pool_shock_bps": Decimal("10"),
            "pool_trend_bps": Decimal("0"),
            "total_return_pct": Decimal("1"),
            "max_drawdown_pct": Decimal("1"),
            "profit_factor": Decimal("1.5"),
            "win_rate_pct": Decimal("60"),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("portfolio_backtest.select_candidates", return_value=[candidate()]), patch(
                "portfolio_backtest.backtest_candidate",
                return_value=row,
            ):
                output_dir = run_portfolio_backtest(FakeClient(), config, tmpdir)
            runtime_path = Path(output_dir) / "runtime_configs" / "aaa_usdt_swap.json"
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))

        self.assertEqual(runtime["cashReservePct"], "3")

    def test_summary_explains_filtered_candidates_when_no_targets(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=1),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(max_risk_events=2),
            backtest_pages=1,
        )
        row = {
            "rank": 1,
            "status": "ok",
            "inst_id": "AAA-USDT-SWAP",
            "score": Decimal("1"),
            "fills": 10,
            "risk_events": 3,
            "quote_volume_24h": Decimal("10000000"),
            "pool_window_hours": Decimal("5"),
            "pool_window_bars": 300,
            "pool_avg_abs_bps": Decimal("5"),
            "pool_shock_bps": Decimal("10"),
            "pool_trend_bps": Decimal("0"),
            "total_return_pct": Decimal("1"),
            "max_drawdown_pct": Decimal("1"),
            "profit_factor": Decimal("1.5"),
            "win_rate_pct": Decimal("60"),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("portfolio_backtest.select_candidates", return_value=[candidate()]), patch(
                "portfolio_backtest.backtest_candidate",
                return_value=row,
            ):
                output_dir = run_portfolio_backtest(FakeClient(), config, tmpdir)
            summary = (Path(output_dir) / "summary.md").read_text(encoding="utf-8")

        self.assertIn("## Run Parameters", summary)
        self.assertIn("## Eligibility Diagnostics", summary)
        self.assertIn("risk events 3 > max 2", summary)
        self.assertIn("No target allocations were generated because every successful candidate was filtered out", summary)

    def test_empty_report_contains_doubao_quant_metadata(self) -> None:
        config = PortfolioBacktestConfig(
            selector=MarketSelectorConfig(top_n=0),
            score_weights=ScoreWeights(),
            allocation=AllocationConfig(),
            backtest_pages=1,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("portfolio_backtest.select_candidates", return_value=[]):
                output_dir = run_portfolio_backtest(FakeClient(), config, tmpdir)
            candidates = json.loads((Path(output_dir) / "candidates.json").read_text(encoding="utf-8"))
            rebalance = json.loads((Path(output_dir) / "rebalance_plan.json").read_text(encoding="utf-8"))

        self.assertEqual(candidates["product"]["productCn"], "豆包 Quant")
        self.assertEqual(rebalance["product"]["quantDingerLicense"], "Apache-2.0")


if __name__ == "__main__":
    unittest.main()
