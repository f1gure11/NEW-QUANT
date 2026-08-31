from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strategy_evidence import evidence_payload, is_strategy_evidence_backed


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "strategy_candidates"
EULER_MASCHERONI = 0.5772156649015329


@dataclass(slots=True)
class GateConfig:
    min_windows: int = 3
    min_pass_rate_pct: float = 60.0
    min_total_return_pct: float = 0.0
    min_median_return_pct: float = 0.0
    min_worst_return_pct: float = -3.0
    min_total_trades: int = 30
    min_mean_exposure_pct: float = 0.0
    min_dsr_prob: float = 0.0
    enter_streak: int = 1
    exit_misses: int = 1
    match_mode: str = "exact"
    require_strategy_evidence: bool = True


@dataclass(frozen=True, slots=True)
class CandidateKey:
    inst_id: str
    strategy: str
    params: str
    regime_filter: str
    allowed_regimes: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> CandidateKey:
        return cls(
            inst_id=row.get("inst_id", ""),
            strategy=row.get("strategy", ""),
            params=normalize_params(row.get("params", "")),
            regime_filter=row.get("regime_filter", "all") or "all",
            allowed_regimes=row.get("allowed_regimes", "all") or "all",
        )

    def stable_id(self) -> str:
        payload = {
            "inst_id": self.inst_id,
            "strategy": self.strategy,
            "params": json.loads(self.params),
            "regime_filter": self.regime_filter,
            "allowed_regimes": self.allowed_regimes,
        }
        return json.dumps(payload, sort_keys=True)


def main() -> int:
    args = parse_args()
    config = GateConfig(
        min_windows=args.min_windows,
        min_pass_rate_pct=args.min_pass_rate_pct,
        min_total_return_pct=args.min_total_return_pct,
        min_median_return_pct=args.min_median_return_pct,
        min_worst_return_pct=args.min_worst_return_pct,
        min_total_trades=args.min_total_trades,
        min_mean_exposure_pct=args.min_mean_exposure_pct,
        min_dsr_prob=args.min_dsr_prob,
        enter_streak=args.enter_streak,
        exit_misses=args.exit_misses,
        match_mode=args.match_mode,
    )
    primary_dir = Path(args.primary_report)
    confirm_dir = Path(args.confirm_report)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_payload = load_previous_gate(args.previous_gate)
    payload = build_gate_payload(primary_dir, confirm_dir, config, previous_payload)
    write_outputs(output_dir, payload)
    print(f"strategy_candidate_gate_report={output_dir}")
    print(
        "approved={approved} fresh={fresh} carried={carried} pending={pending} dropped={dropped} "
        "primary_passed={primary} confirm_passed={confirm} intersection={intersection}".format(
            approved=len(payload["approvedCandidates"]),
            fresh=payload["summary"]["freshApproved"],
            carried=payload["summary"]["carriedForward"],
            pending=len(payload["pendingCandidates"]),
            dropped=len(payload["droppedCandidates"]),
            primary=payload["summary"]["primaryPassed"],
            confirm=payload["summary"]["confirmPassed"],
            intersection=payload["summary"]["intersection"],
        )
    )
    return 0 if payload["approvedCandidates"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate strategy candidates using strict intersection of two walk-forward reports.")
    parser.add_argument("--primary-report", required=True, help="Primary strategy_walk_forward report directory.")
    parser.add_argument("--confirm-report", required=True, help="Confirming/alternate strategy_walk_forward report directory.")
    parser.add_argument("--min-windows", type=int, default=3)
    parser.add_argument("--min-pass-rate-pct", type=float, default=60.0)
    parser.add_argument("--min-total-return-pct", type=float, default=0.0)
    parser.add_argument("--min-median-return-pct", type=float, default=0.0)
    parser.add_argument("--min-worst-return-pct", type=float, default=-3.0)
    parser.add_argument("--min-total-trades", type=int, default=30)
    parser.add_argument(
        "--min-mean-exposure-pct",
        type=float,
        default=0.0,
        help="Require the strategy to be in-position for this mean percentage of test bars in both reports.",
    )
    parser.add_argument(
        "--min-dsr-prob",
        type=float,
        default=0.0,
        help="Deflated Sharpe Ratio probability threshold (Bailey/Lopez de Prado). Applied per report when > 0.",
    )
    parser.add_argument(
        "--previous-gate",
        default="",
        help="Previous approved_candidates.json for entry/exit hysteresis. Disabled when omitted.",
    )
    parser.add_argument("--enter-streak", type=int, default=1, help="Consecutive gate passes required before a new candidate goes live.")
    parser.add_argument("--exit-misses", type=int, default=1, help="Consecutive gate misses before a previously approved candidate is dropped.")
    parser.add_argument(
        "--match-mode",
        choices=["exact", "strategy"],
        default="exact",
        help="Match exact parameters/regime, or confirm the same instrument and strategy while executing primary-report parameters.",
    )
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def load_previous_gate(path_value: str) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_gate_payload(
    primary_dir: Path,
    confirm_dir: Path,
    config: GateConfig,
    previous_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary_rows = load_aggregate_rows(primary_dir)
    confirm_rows = load_aggregate_rows(confirm_dir)
    primary_eligible = eligible_by_key(primary_rows, config)
    confirm_eligible = eligible_by_key(confirm_rows, config)
    matched_pairs = matched_candidate_pairs(primary_eligible, confirm_eligible, config.match_mode)
    primary_dsr = report_dsr_context(primary_dir, primary_rows)
    confirm_dsr = report_dsr_context(confirm_dir, confirm_rows)
    primary_bar = report_bar(primary_dir)
    confirm_bar = report_bar(confirm_dir)
    fresh: list[dict[str, Any]] = []
    dsr_rejected: list[dict[str, Any]] = []
    for primary_key, confirm_key in matched_pairs:
        primary_row = primary_eligible[primary_key]
        confirm_row = confirm_eligible[confirm_key]
        if not combined_candidate_passes(primary_row, confirm_row, config):
            continue
        candidate = approved_candidate_payload(primary_key, primary_row, confirm_row, confirm_key=confirm_key)
        candidate["strategyEvidence"] = evidence_payload(primary_key.strategy)
        candidate["bar"] = primary_bar
        if candidate.get("confirmation"):
            candidate["confirmation"]["bar"] = confirm_bar
        candidate["matchMode"] = config.match_mode
        dsr_primary = candidate_dsr_probability(primary_key, primary_dsr)
        dsr_confirm = candidate_dsr_probability(confirm_key, confirm_dsr)
        candidate["dsrProbPrimary"] = dsr_primary
        candidate["dsrProbConfirm"] = dsr_confirm
        candidate["dsrProbMin"] = min_or_none(dsr_primary, dsr_confirm)
        if config.min_dsr_prob > 0:
            if candidate["dsrProbMin"] is None or candidate["dsrProbMin"] < config.min_dsr_prob:
                dsr_rejected.append(candidate)
                continue
        fresh.append(candidate)
    approved, pending, dropped, carried_count = apply_hysteresis(fresh, previous_payload, config)
    summary = {
        "primaryReport": str(primary_dir),
        "confirmReport": str(confirm_dir),
        "primaryRows": len(primary_rows),
        "confirmRows": len(confirm_rows),
        "primaryPassed": len(primary_eligible),
        "confirmPassed": len(confirm_eligible),
        "intersection": len(matched_pairs),
        "freshApproved": len(fresh),
        "dsrRejected": len(dsr_rejected),
        "carriedForward": carried_count,
        "approved": len(approved),
        "primaryTrials": primary_dsr["trials"],
        "confirmTrials": confirm_dsr["trials"],
        "unverifiedPrimaryRejected": count_unverified_passers(primary_rows, config),
        "unverifiedConfirmRejected": count_unverified_passers(confirm_rows, config),
    }
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "strict_walk_forward_intersection_gate" if config.match_mode == "exact" else "temporal_strategy_confirmation_gate",
        "config": asdict(config),
        "summary": summary,
        "approvedCandidates": approved,
        "pendingCandidates": pending,
        "droppedCandidates": dropped,
        "dsrRejectedCandidates": dsr_rejected,
        "primaryPassedCandidates": [candidate_row_payload(key, row) for key, row in sorted(primary_eligible.items(), key=lambda item: item[0].stable_id())],
        "confirmPassedCandidates": [candidate_row_payload(key, row) for key, row in sorted(confirm_eligible.items(), key=lambda item: item[0].stable_id())],
    }


def candidate_identity(item: dict[str, Any], match_mode: str = "exact") -> str:
    payload: dict[str, Any] = {
        "instId": str(item.get("instId", "")),
        "strategy": str(item.get("strategy", "")),
    }
    if match_mode == "exact":
        payload.update(
            {
                "params": item.get("params", {}) or {},
                "regimeFilter": str(item.get("regimeFilter", "all") or "all"),
                "allowedRegimes": sorted(str(value) for value in item.get("allowedRegimes", []) or []),
            }
        )
    return json.dumps(payload, sort_keys=True)


def apply_hysteresis(
    fresh: list[dict[str, Any]],
    previous_payload: dict[str, Any] | None,
    config: GateConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    if not previous_payload:
        for candidate in fresh:
            candidate["passStreak"] = max(1, config.enter_streak)
            candidate["missStreak"] = 0
            candidate["carriedForward"] = False
        return list(fresh), [], [], 0
    prev_active = {
        candidate_identity(item, config.match_mode): item
        for item in previous_payload.get("approvedCandidates", [])
        if isinstance(item, dict)
        and (not config.require_strategy_evidence or is_strategy_evidence_backed(str(item.get("strategy", ""))))
    }
    prev_pending = {
        candidate_identity(item, config.match_mode): item
        for item in previous_payload.get("pendingCandidates", [])
        if isinstance(item, dict)
        and (not config.require_strategy_evidence or is_strategy_evidence_backed(str(item.get("strategy", ""))))
    }
    approved: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    fresh_ids = set()
    for candidate in fresh:
        identity = candidate_identity(candidate, config.match_mode)
        fresh_ids.add(identity)
        prior = prev_active.get(identity) or prev_pending.get(identity)
        prior_streak = as_int((prior or {}).get("passStreak")) or (config.enter_streak if identity in prev_active else 0)
        candidate["passStreak"] = prior_streak + 1
        candidate["missStreak"] = 0
        candidate["carriedForward"] = False
        if candidate["passStreak"] >= config.enter_streak:
            approved.append(candidate)
        else:
            pending.append(candidate)
    carried_count = 0
    for identity, item in prev_active.items():
        if identity in fresh_ids:
            continue
        misses = as_int(item.get("missStreak")) + 1
        carried = dict(item)
        carried["missStreak"] = misses
        carried["passStreak"] = as_int(item.get("passStreak")) or config.enter_streak
        if misses < config.exit_misses:
            carried["carriedForward"] = True
            approved.append(carried)
            carried_count += 1
        else:
            carried["carriedForward"] = False
            dropped.append(carried)
    return approved, pending, dropped, carried_count


def report_dsr_context(report_dir: Path, aggregate_rows: list[dict[str, str]]) -> dict[str, Any]:
    returns_by_key = window_returns_by_key(report_dir)
    sr_values = []
    for returns in returns_by_key.values():
        sr = sharpe_ratio(returns)
        if sr is not None:
            sr_values.append(sr)
    trials = max(len(aggregate_rows), len(returns_by_key), 1)
    return {
        "returnsByKey": returns_by_key,
        "srValues": sr_values,
        "trials": trials,
    }


def window_returns_by_key(report_dir: Path) -> dict[CandidateKey, list[float]]:
    path = report_dir / "rows.csv"
    result: dict[CandidateKey, list[float]] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            key = CandidateKey.from_row(row)
            result.setdefault(key, []).append(as_float(row.get("test_return_pct")))
    return result


def candidate_dsr_probability(key: CandidateKey, context: dict[str, Any]) -> float | None:
    returns = context["returnsByKey"].get(key)
    if not returns:
        return None
    return deflated_sharpe_probability(returns, context["srValues"], context["trials"])


def sharpe_ratio(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = statistics.fmean(returns)
    std = statistics.pstdev(returns)
    if std <= 0:
        return None
    return mean / std


def deflated_sharpe_probability(returns: list[float], all_sr_values: list[float], trials: int) -> float:
    """Bailey & Lopez de Prado (2014): probability that the observed Sharpe
    exceeds the expected maximum Sharpe of `trials` unskilled strategies."""
    observations = len(returns)
    if observations < 3:
        return 0.0
    sr = sharpe_ratio(returns)
    if sr is None:
        return 0.0
    mean = statistics.fmean(returns)
    deviations = [value - mean for value in returns]
    variance = sum(d * d for d in deviations) / observations
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    skew = sum(d**3 for d in deviations) / observations / std**3
    kurt = sum(d**4 for d in deviations) / observations / std**4
    benchmark_sr = expected_max_sharpe(all_sr_values, trials)
    denominator = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denominator <= 0:
        denominator = 1e-9
    z = (sr - benchmark_sr) * math.sqrt(observations - 1.0) / math.sqrt(denominator)
    return normal_cdf(z)


def expected_max_sharpe(all_sr_values: list[float], trials: int) -> float:
    if trials < 2 or len(all_sr_values) < 2:
        return 0.0
    variance = statistics.pvariance(all_sr_values)
    if variance <= 0:
        return 0.0
    scale = math.sqrt(variance)
    return scale * (
        (1.0 - EULER_MASCHERONI) * normal_ppf(1.0 - 1.0 / trials)
        + EULER_MASCHERONI * normal_ppf(1.0 - 1.0 / (trials * math.e))
    )


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def normal_ppf(probability: float) -> float:
    """Acklam's rational approximation of the inverse normal CDF."""
    p = min(max(probability, 1e-12), 1.0 - 1e-12)
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
    p_low = 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > 1.0 - p_low:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


def min_or_none(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def load_aggregate_rows(report_dir: Path) -> list[dict[str, str]]:
    path = report_dir / "aggregate.csv"
    if not path.exists():
        raise FileNotFoundError(f"aggregate.csv not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def report_bar(report_dir: Path) -> str:
    path = report_dir / "summary.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "5m"
    return str((payload.get("config") or {}).get("bar") or "5m")


def eligible_by_key(rows: list[dict[str, str]], config: GateConfig) -> dict[CandidateKey, dict[str, str]]:
    result: dict[CandidateKey, dict[str, str]] = {}
    for row in rows:
        if row.get("passed") != "true":
            continue
        if not row_passes(row, config):
            continue
        key = CandidateKey.from_row(row)
        if config.require_strategy_evidence and not is_strategy_evidence_backed(key.strategy):
            continue
        result[key] = row
    return result


def count_unverified_passers(rows: list[dict[str, str]], config: GateConfig) -> int:
    if not config.require_strategy_evidence:
        return 0
    return sum(
        1
        for row in rows
        if row.get("passed") == "true"
        and row_passes(row, config)
        and not is_strategy_evidence_backed(row.get("strategy", ""))
    )


def row_passes(row: dict[str, str], config: GateConfig) -> bool:
    return (
        as_int(row.get("selected_windows")) >= config.min_windows
        and as_float(row.get("pass_rate_pct")) >= config.min_pass_rate_pct
        and as_float(row.get("total_test_return_pct")) > config.min_total_return_pct
        and as_float(row.get("median_test_return_pct")) > config.min_median_return_pct
        and as_float(row.get("worst_test_return_pct")) >= config.min_worst_return_pct
        and as_int(row.get("total_test_trades")) >= config.min_total_trades
        and as_float(row.get("mean_test_exposure_pct")) >= config.min_mean_exposure_pct
    )


def combined_candidate_passes(primary: dict[str, str], confirm: dict[str, str], config: GateConfig) -> bool:
    returns = [as_float(primary.get("total_test_return_pct")), as_float(confirm.get("total_test_return_pct"))]
    medians = [as_float(primary.get("median_test_return_pct")), as_float(confirm.get("median_test_return_pct"))]
    worst = min(as_float(primary.get("worst_test_return_pct")), as_float(confirm.get("worst_test_return_pct")))
    trades = as_int(primary.get("total_test_trades")) + as_int(confirm.get("total_test_trades"))
    exposure = min(
        as_float(primary.get("mean_test_exposure_pct")),
        as_float(confirm.get("mean_test_exposure_pct")),
    )
    return (
        min(returns) > config.min_total_return_pct
        and min(medians) > config.min_median_return_pct
        and worst >= config.min_worst_return_pct
        and trades >= config.min_total_trades * 2
        and exposure >= config.min_mean_exposure_pct
    )


def matched_candidate_pairs(
    primary: dict[CandidateKey, dict[str, str]],
    confirm: dict[CandidateKey, dict[str, str]],
    match_mode: str,
) -> list[tuple[CandidateKey, CandidateKey]]:
    if match_mode == "exact":
        keys = sorted(set(primary) & set(confirm), key=lambda key: key.stable_id())
        return [(key, key) for key in keys]

    primary_best = best_candidate_by_strategy(primary)
    confirm_best = best_candidate_by_strategy(confirm)
    groups = sorted(set(primary_best) & set(confirm_best))
    return [(primary_best[group], confirm_best[group]) for group in groups]


def best_candidate_by_strategy(
    rows: dict[CandidateKey, dict[str, str]],
) -> dict[tuple[str, str], CandidateKey]:
    result: dict[tuple[str, str], CandidateKey] = {}
    for key, row in rows.items():
        group = (key.inst_id, key.strategy)
        current = result.get(group)
        if current is None or candidate_row_rank(row) > candidate_row_rank(rows[current]):
            result[group] = key
    return result


def candidate_row_rank(row: dict[str, str]) -> tuple[float, float, float, int]:
    return (
        as_float(row.get("score")),
        as_float(row.get("total_test_return_pct")),
        as_float(row.get("worst_test_return_pct")),
        as_int(row.get("total_test_trades")),
    )


def approved_candidate_payload(
    key: CandidateKey,
    primary: dict[str, str],
    confirm: dict[str, str],
    *,
    confirm_key: CandidateKey | None = None,
) -> dict[str, Any]:
    confirm_key = confirm_key or key
    payload = {
        "instId": key.inst_id,
        "strategy": key.strategy,
        "params": json.loads(key.params),
        "regimeFilter": key.regime_filter,
        "allowedRegimes": [item for item in key.allowed_regimes.split(",") if item],
        "primary": metrics_payload(primary),
        "confirm": metrics_payload(confirm),
        "combined": {
            "minTotalReturnPct": min(as_float(primary.get("total_test_return_pct")), as_float(confirm.get("total_test_return_pct"))),
            "minMedianReturnPct": min(as_float(primary.get("median_test_return_pct")), as_float(confirm.get("median_test_return_pct"))),
            "worstReturnPct": min(as_float(primary.get("worst_test_return_pct")), as_float(confirm.get("worst_test_return_pct"))),
            "totalTrades": as_int(primary.get("total_test_trades")) + as_int(confirm.get("total_test_trades")),
            "meanPassRatePct": statistics.fmean([as_float(primary.get("pass_rate_pct")), as_float(confirm.get("pass_rate_pct"))]),
            "minMeanExposurePct": min(
                as_float(primary.get("mean_test_exposure_pct")),
                as_float(confirm.get("mean_test_exposure_pct")),
            ),
        },
    }
    if confirm_key != key:
        payload["confirmation"] = {
            "params": json.loads(confirm_key.params),
            "regimeFilter": confirm_key.regime_filter,
            "allowedRegimes": [item for item in confirm_key.allowed_regimes.split(",") if item],
        }
    return payload


def candidate_row_payload(key: CandidateKey, row: dict[str, str]) -> dict[str, Any]:
    return {
        "instId": key.inst_id,
        "strategy": key.strategy,
        "params": json.loads(key.params),
        "regimeFilter": key.regime_filter,
        "allowedRegimes": key.allowed_regimes,
        **metrics_payload(row),
    }


def metrics_payload(row: dict[str, str]) -> dict[str, Any]:
    return {
        "selectedWindows": as_int(row.get("selected_windows")),
        "passedWindows": as_int(row.get("passed_windows")),
        "passRatePct": as_float(row.get("pass_rate_pct")),
        "totalTestReturnPct": as_float(row.get("total_test_return_pct")),
        "medianTestReturnPct": as_float(row.get("median_test_return_pct")),
        "worstTestReturnPct": as_float(row.get("worst_test_return_pct")),
        "meanTestDrawdownPct": as_float(row.get("mean_test_drawdown_pct")),
        "totalTestTrades": as_int(row.get("total_test_trades")),
        "meanTestExposurePct": as_float(row.get("mean_test_exposure_pct")),
        "score": as_float(row.get("score")),
    }


def write_outputs(output_dir: Path, payload: dict[str, Any]) -> None:
    (output_dir / "approved_candidates.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Strategy Candidate Gate",
        "",
        (
            "Strict intersection gate over two walk-forward reports."
            if payload["config"].get("match_mode") == "exact"
            else "Temporal confirmation gate matching instrument and strategy; live parameters come from the primary report."
        ),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Primary passed | {summary['primaryPassed']} |",
        f"| Confirm passed | {summary['confirmPassed']} |",
        f"| Unverified rejected (primary/confirm) | {summary['unverifiedPrimaryRejected']} / {summary['unverifiedConfirmRejected']} |",
        f"| Intersection | {summary['intersection']} |",
        f"| Approved | {summary['approved']} |",
        "",
        "## Approved Candidates",
        "",
        "| Instrument | Strategy | Regime | Primary Ret % | Confirm Ret % | Worst % | Trades |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["approvedCandidates"]:
        lines.append(
            f"| {item['instId']} | {item['strategy']} | {item['regimeFilter']} | "
            f"{item['primary']['totalTestReturnPct']:.6f} | {item['confirm']['totalTestReturnPct']:.6f} | "
            f"{item['combined']['worstReturnPct']:.6f} | {item['combined']['totalTrades']} |"
        )
    if not payload["approvedCandidates"]:
        lines.append("| _none_ |  |  |  |  |  |  |")
    return "\n".join(lines) + "\n"


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_params(value: str) -> str:
    if not value:
        return "{}"
    return json.dumps(json.loads(value), sort_keys=True)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
