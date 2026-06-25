from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
REGIME_REPORT_DIR = PROJECT_ROOT / "reports" / "regime_model"
PRODUCT_NAME = "Doubao Quant"
PRODUCT_NAME_CN = "豆包 Quant"
QUANTDINGER_SOURCE = "github.com/brokermr810/QuantDinger"
QUANTDINGER_LICENSE = "Apache-2.0"
STRATEGY_CONTRACT = "QuantDinger signal/execution standard v1 adapted for OKX grid execution"
DEFAULT_ML_CONFIDENCE = Decimal("0.52")


@dataclass(slots=True)
class MlRegimeProfile:
    enabled: bool
    mode: str
    model_path: str
    min_confidence: Decimal
    report_dir: str
    generated_at: str
    variant: str
    score_delta_vs_baseline: Decimal
    return_delta_vs_baseline: Decimal
    drawdown_delta_vs_baseline: Decimal
    risk_event_delta_vs_baseline: int
    note: str


def latest_ml_regime_profile(
    *,
    requested_mode: str = "auto",
    model_path: str | Path = "",
    min_confidence: Decimal = DEFAULT_ML_CONFIDENCE,
    report_root: Path = REGIME_REPORT_DIR,
) -> MlRegimeProfile:
    requested_mode = normalize_mode(requested_mode)
    explicit_model_path = str(model_path or "")
    if requested_mode == "off":
        return disabled_profile("disabled by request", min_confidence=min_confidence)

    report_dir = latest_regime_report_dir(report_root)
    if not report_dir:
        if requested_mode in {"rf", "hmm"} and explicit_model_path:
            return MlRegimeProfile(
                enabled=True,
                mode=requested_mode,
                model_path=explicit_model_path,
                min_confidence=min_confidence,
                report_dir="",
                generated_at="",
                variant=requested_mode,
                score_delta_vs_baseline=Decimal("0"),
                return_delta_vs_baseline=Decimal("0"),
                drawdown_delta_vs_baseline=Decimal("0"),
                risk_event_delta_vs_baseline=0,
                note="explicit model path without research report",
            )
        return disabled_profile("no regime research report found", min_confidence=min_confidence)

    rows = read_csv_rows(report_dir / "scores.csv")
    metrics = read_json_file(report_dir / "model_metrics.json")
    summaries = variant_summaries(rows)
    baseline = summaries.get("baseline", {})
    generated_at = str(metrics.get("generatedAt") or file_mtime_iso(report_dir))

    candidate_modes = [requested_mode] if requested_mode in {"rf", "hmm", "rules"} else ["rf", "hmm", "rules"]
    chosen: dict[str, Any] | None = None
    for mode in sorted(
        [summary for name, summary in summaries.items() if name in candidate_modes],
        key=lambda row: (dec(row.get("avgScore")), row.get("ml_priority", 0)),
        reverse=True,
    ):
        path = model_path_for_mode(report_dir, str(mode["variant"]), explicit_model_path)
        if mode["variant"] in {"rf", "hmm"} and not path:
            continue
        chosen = {**mode, "modelPath": path}
        break

    if not chosen:
        return disabled_profile(
            f"no usable regime variant for request={requested_mode}",
            min_confidence=min_confidence,
            report_dir=report_dir,
            generated_at=generated_at,
        )

    mode = str(chosen["variant"])
    model_path_text = str(chosen.get("modelPath") or "")
    score_delta = dec(chosen.get("avgScore")) - dec(baseline.get("avgScore"))
    return_delta = dec(chosen.get("avgReturnPct")) - dec(baseline.get("avgReturnPct"))
    drawdown_delta = dec(chosen.get("avgMaxDrawdownPct")) - dec(baseline.get("avgMaxDrawdownPct"))
    risk_delta = int(chosen.get("totalRiskEvents") or 0) - int(baseline.get("totalRiskEvents") or 0)
    return MlRegimeProfile(
        enabled=mode != "off",
        mode=mode,
        model_path=model_path_text,
        min_confidence=min_confidence,
        report_dir=str(report_dir),
        generated_at=generated_at,
        variant=mode,
        score_delta_vs_baseline=score_delta,
        return_delta_vs_baseline=return_delta,
        drawdown_delta_vs_baseline=drawdown_delta,
        risk_event_delta_vs_baseline=risk_delta,
        note=f"{PRODUCT_NAME} selected {mode} regime gate from latest research report",
    )


def quant_metadata(profile: MlRegimeProfile | None = None) -> dict[str, Any]:
    payload = {
        "product": PRODUCT_NAME,
        "productCn": PRODUCT_NAME_CN,
        "strategyContract": STRATEGY_CONTRACT,
        "quantDingerSource": QUANTDINGER_SOURCE,
        "quantDingerLicense": QUANTDINGER_LICENSE,
        "liveSafety": "paper/read-only by default; live requires server unlock, preflight, and explicit confirmation",
    }
    if profile is not None:
        payload["mlRegime"] = profile_to_dict(profile)
    return payload


def profile_to_dict(profile: MlRegimeProfile) -> dict[str, Any]:
    payload = asdict(profile)
    payload["min_confidence"] = plain(profile.min_confidence)
    payload["score_delta_vs_baseline"] = plain(profile.score_delta_vs_baseline)
    payload["return_delta_vs_baseline"] = plain(profile.return_delta_vs_baseline)
    payload["drawdown_delta_vs_baseline"] = plain(profile.drawdown_delta_vs_baseline)
    return payload


def latest_regime_report_dir(report_root: Path = REGIME_REPORT_DIR) -> Path | None:
    if not report_root.exists():
        return None
    dirs = [path for path in report_root.iterdir() if path.is_dir() and (path / "scores.csv").exists()]
    if not dirs:
        return None
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dirs[0]


def variant_summaries(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("error"):
            continue
        variant = str(row.get("variant") or "")
        if variant:
            grouped.setdefault(variant, []).append(row)

    output: dict[str, dict[str, Any]] = {}
    for variant, items in grouped.items():
        count = Decimal(len(items))
        if count <= 0:
            continue
        output[variant] = {
            "variant": variant,
            "symbols": len(items),
            "avgScore": sum((dec(row.get("score")) for row in items), Decimal("0")) / count,
            "avgReturnPct": sum((dec(row.get("total_return_pct")) for row in items), Decimal("0")) / count,
            "avgMaxDrawdownPct": sum((dec(row.get("max_drawdown_pct")) for row in items), Decimal("0")) / count,
            "totalRiskEvents": sum(int(dec(row.get("risk_events"))) for row in items),
            "ml_priority": {"rf": 3, "hmm": 2, "rules": 1, "baseline": 0}.get(variant, 0),
        }
    return output


def model_path_for_mode(report_dir: Path, mode: str, explicit_model_path: str = "") -> str:
    if mode == "rules":
        return ""
    if explicit_model_path and mode in {"rf", "hmm"}:
        return explicit_model_path
    filename = {"rf": "regime_rf.joblib", "hmm": "regime_hmm.joblib"}.get(mode)
    if not filename:
        return ""
    path = report_dir / filename
    return str(path) if path.exists() else ""


def disabled_profile(
    note: str,
    *,
    min_confidence: Decimal = DEFAULT_ML_CONFIDENCE,
    report_dir: Path | None = None,
    generated_at: str = "",
) -> MlRegimeProfile:
    return MlRegimeProfile(
        enabled=False,
        mode="off",
        model_path="",
        min_confidence=min_confidence,
        report_dir=str(report_dir or ""),
        generated_at=generated_at,
        variant="off",
        score_delta_vs_baseline=Decimal("0"),
        return_delta_vs_baseline=Decimal("0"),
        drawdown_delta_vs_baseline=Decimal("0"),
        risk_event_delta_vs_baseline=0,
        note=note,
    )


def normalize_mode(value: str) -> str:
    mode = str(value or "auto").strip().lower()
    return mode if mode in {"auto", "off", "rules", "rf", "hmm"} else "auto"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def file_mtime_iso(path: Path) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")
