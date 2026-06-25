from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from doubao_quant import latest_ml_regime_profile, quant_metadata


class DoubaoQuantTest(unittest.TestCase):
    def test_latest_ml_regime_profile_selects_best_available_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_root = Path(tmpdir)
            report = report_root / "20260625T000000Z"
            report.mkdir()
            (report / "regime_rf.joblib").write_bytes(b"rf")
            (report / "regime_hmm.joblib").write_bytes(b"hmm")
            (report / "model_metrics.json").write_text('{"generatedAt":"now"}', encoding="utf-8")
            (report / "scores.csv").write_text(
                "rank,variant,inst_id,score,total_return_pct,max_drawdown_pct,profit_factor,fills,risk_events,error\n"
                "1,baseline,AAA,-10,-2,4,1,10,3,\n"
                "1,hmm,AAA,1,0,2,1,5,1,\n"
                "1,rf,AAA,2,1,1,2,4,0,\n",
                encoding="utf-8",
            )

            profile = latest_ml_regime_profile(report_root=report_root)

        self.assertTrue(profile.enabled)
        self.assertEqual(profile.mode, "rf")
        self.assertTrue(profile.model_path.endswith("regime_rf.joblib"))
        self.assertEqual(profile.return_delta_vs_baseline, Decimal("3"))
        self.assertEqual(profile.risk_event_delta_vs_baseline, -3)

    def test_quant_metadata_includes_quantdinger_lineage(self) -> None:
        metadata = quant_metadata()

        self.assertEqual(metadata["productCn"], "豆包 Quant")
        self.assertEqual(metadata["quantDingerLicense"], "Apache-2.0")


if __name__ == "__main__":
    unittest.main()
