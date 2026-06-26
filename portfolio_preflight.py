from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from okx_client import OkxApiError, OkxRestClient, load_env


BLOCK = "block"
WARN = "warn"
PASS = "pass"


@dataclass(slots=True)
class PreflightCheck:
    severity: str
    code: str
    inst_id: str
    message: str
    detail: dict[str, Any]


@dataclass(slots=True)
class ProcessSnapshot:
    pid: str
    ppid: str
    command: str


def main() -> int:
    args = parse_args()
    output_dir = Path(args.report_dir)
    checks = run_preflight(output_dir, include_account=args.include_account)
    report_path = write_preflight_report(output_dir, checks, include_account=args.include_account)
    blocked = any(check.severity == BLOCK for check in checks)
    print(f"preflight_report={report_path}")
    print(f"preflight_status={'blocked' if blocked else 'pass'}")
    return 2 if blocked else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight guard for OKX portfolio execution bundles. No trading operations.")
    parser.add_argument("report_dir", help="Portfolio report directory containing execution_intents.json.")
    parser.add_argument("--include-account", action="store_true", help="Read private OKX positions and pending orders. Does not trade.")
    return parser.parse_args()


def run_preflight(report_dir: Path, *, include_account: bool = False) -> list[PreflightCheck]:
    intents = load_execution_intents(report_dir)
    checks: list[PreflightCheck] = []
    processes = list_bot_processes()
    for intent in intents:
        checks.extend(check_intent(intent, processes))
    if include_account:
        load_env()
        checks.extend(check_account_state(intents, OkxRestClient.from_env()))
    else:
        checks.append(
            PreflightCheck(
                WARN,
                "account_check_skipped",
                "",
                "Private OKX account checks were skipped; pass --include-account to inspect positions and open orders.",
                {},
            )
        )
    if not intents:
        checks.append(PreflightCheck(BLOCK, "no_execution_intents", "", "No execution intents found.", {}))
    return checks


def load_execution_intents(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "execution_intents.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    intents = payload.get("intents", [])
    return intents if isinstance(intents, list) else []


def check_intent(intent: dict[str, Any], processes: list[ProcessSnapshot]) -> list[PreflightCheck]:
    inst_id = str(intent.get("inst_id", ""))
    checks: list[PreflightCheck] = []
    status = str(intent.get("status", ""))
    command = str(intent.get("dry_run_command", ""))
    runtime_path = Path(str(intent.get("runtime_config_path", ""))) if intent.get("runtime_config_path") else None

    if status == "manual_review_reduce":
        checks.append(
            PreflightCheck(
                BLOCK,
                "manual_reduce_required",
                inst_id,
                "This intent implies decrease/exit and requires an explicit manual reduce workflow.",
                {"action": intent.get("action", "")},
            )
        )
        return checks

    if status == "rebalance_reduce_ready":
        if "--live" in command.split():
            checks.append(PreflightCheck(BLOCK, "live_flag_present", inst_id, "Dry-run reduce command unexpectedly contains --live.", {}))
        else:
            checks.append(PreflightCheck(PASS, "no_live_flag", inst_id, "Dry-run reduce command does not contain --live.", {}))
        if "--once" not in command.split():
            checks.append(PreflightCheck(BLOCK, "once_flag_missing", inst_id, "Dry-run reduce command must include --once.", {}))
        else:
            checks.append(PreflightCheck(PASS, "once_flag_present", inst_id, "Dry-run reduce command includes --once.", {}))
        checks.append(
            PreflightCheck(
                WARN,
                "reduce_only_rebalance",
                inst_id,
                "This intent is a reduce-only rebalance action; review current positions before live execution.",
                {"action": intent.get("action", ""), "deltaMargin": intent.get("delta_margin", "")},
            )
        )
        return checks

    if status != "runtime_config_ready":
        checks.append(
            PreflightCheck(
                WARN,
                "intent_not_executable",
                inst_id,
                "Intent is not a generated runtime config target.",
                {"status": status},
            )
        )
        return checks

    if "--live" in command.split():
        checks.append(PreflightCheck(BLOCK, "live_flag_present", inst_id, "Dry-run command unexpectedly contains --live.", {}))
    else:
        checks.append(PreflightCheck(PASS, "no_live_flag", inst_id, "Dry-run command does not contain --live.", {}))

    if "--once" not in command.split():
        checks.append(PreflightCheck(BLOCK, "once_flag_missing", inst_id, "Dry-run command must include --once.", {}))
    else:
        checks.append(PreflightCheck(PASS, "once_flag_present", inst_id, "Dry-run command includes --once.", {}))

    if runtime_path is None or not runtime_path.exists():
        checks.append(
            PreflightCheck(
                BLOCK,
                "runtime_config_missing",
                inst_id,
                "Runtime config draft is missing.",
                {"path": str(runtime_path or "")},
            )
        )
    else:
        checks.extend(check_runtime_config(inst_id, runtime_path))

    matching_processes = [process for process in processes if inst_id and inst_id in process.command]
    if matching_processes:
        adoptable_processes, foreign_processes = split_bot_processes(intent, matching_processes)
        if adoptable_processes:
            checks.append(
                PreflightCheck(
                    WARN,
                    "bot_process_already_running",
                    inst_id,
                    "A matching portfolio bot process is already running and can be adopted.",
                    {"processes": [asdict(process) for process in adoptable_processes]},
                )
            )
        if not foreign_processes:
            checks.append(PreflightCheck(PASS, "no_foreign_bot_process", inst_id, "No foreign bot process found for this instrument.", {}))
        else:
            checks.append(
                PreflightCheck(
                    BLOCK,
                    "foreign_bot_process_already_running",
                    inst_id,
                    "A foreign bot process for this instrument is already running.",
                    {"processes": [asdict(process) for process in foreign_processes]},
                )
            )
    else:
        checks.append(PreflightCheck(PASS, "no_matching_bot_process", inst_id, "No running bot process found for this instrument.", {}))
    return checks


def split_bot_processes(
    intent: dict[str, Any],
    processes: list[ProcessSnapshot],
) -> tuple[list[ProcessSnapshot], list[ProcessSnapshot]]:
    runtime_path = str(intent.get("runtime_config_path") or "")
    bot_prefix = str(intent.get("bot_prefix") or "")
    inst_id = str(intent.get("inst_id") or "")
    owned: list[ProcessSnapshot] = []
    foreign: list[ProcessSnapshot] = []
    for process in processes:
        command_parts = command_tokens(process.command)
        process_runtime_path = option_value(command_parts, "--runtime-config")
        process_bot_prefix = option_value(command_parts, "--bot-prefix")
        same_runtime = runtime_path and process_runtime_path == runtime_path and (not bot_prefix or process_bot_prefix == bot_prefix)
        same_portfolio_bot = (
            inst_id
            and inst_id in process.command
            and bot_prefix
            and process_bot_prefix == bot_prefix
            and is_portfolio_runtime_path(process_runtime_path)
        )
        if same_runtime or same_portfolio_bot:
            owned.append(process)
        else:
            foreign.append(process)
    return owned, foreign


def is_portfolio_runtime_path(value: str) -> bool:
    return "/reports/portfolio/" in value or value.startswith("reports/portfolio/")


def command_tokens(command: str) -> list[str]:
    try:
        import shlex

        return shlex.split(command)
    except Exception:
        return command.split()


def option_value(command_parts: list[str], option: str) -> str:
    try:
        index = command_parts.index(option)
        return command_parts[index + 1]
    except Exception:
        return ""


def check_runtime_config(inst_id: str, runtime_path: Path) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            PreflightCheck(
                BLOCK,
                "runtime_config_invalid_json",
                inst_id,
                "Runtime config draft is not valid JSON.",
                {"path": str(runtime_path), "error": str(exc)},
            )
        ]

    if payload.get("instId") != inst_id:
        checks.append(
            PreflightCheck(
                BLOCK,
                "runtime_config_inst_mismatch",
                inst_id,
                "Runtime config instId does not match execution intent.",
                {"path": str(runtime_path), "runtimeInstId": payload.get("instId")},
            )
        )
    else:
        checks.append(PreflightCheck(PASS, "runtime_config_inst_match", inst_id, "Runtime config instId matches intent.", {}))

    if payload.get("portfolioGenerated") is not True:
        checks.append(
            PreflightCheck(
                BLOCK,
                "runtime_config_not_portfolio_generated",
                inst_id,
                "Runtime config is missing portfolioGenerated=true.",
                {"path": str(runtime_path)},
            )
        )
    else:
        checks.append(PreflightCheck(PASS, "runtime_config_portfolio_generated", inst_id, "Runtime config is marked portfolioGenerated.", {}))

    for key in ("lower", "upper", "orderSz", "maxPosition", "leverage"):
        value = payload.get(key)
        if value in (None, "", "0", "0.0"):
            checks.append(
                PreflightCheck(
                    BLOCK,
                    "runtime_config_bad_value",
                    inst_id,
                    f"Runtime config field {key} is missing or zero.",
                    {"path": str(runtime_path), "field": key, "value": value},
                )
            )
    return checks


def check_account_state(intents: list[dict[str, Any]], client: OkxRestClient) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    candidates = load_candidate_metadata(intents)
    try:
        positions_payload = client.get_positions("SWAP").get("data", [])
    except OkxApiError as exc:
        return [
            PreflightCheck(
                BLOCK,
                "account_read_failed",
                "",
                "Failed to read OKX account positions.",
                {"error": str(exc), "okxCode": exc.okx_code},
            )
        ]
    try:
        equity = account_equity(client.get_balance())
    except OkxApiError as exc:
        equity = Decimal("0")
        checks.append(
            PreflightCheck(
                WARN,
                "balance_read_failed",
                "",
                "Failed to read OKX account balance; min contract capacity check was skipped.",
                {"error": str(exc), "okxCode": exc.okx_code},
            )
        )
    for intent in intents:
        inst_id = str(intent.get("inst_id", ""))
        if not inst_id:
            continue
        action = str(intent.get("action", ""))
        try:
            positions = [
                item for item in positions_payload
                if item.get("instId") == inst_id and str(item.get("pos", "0")) not in ("", "0", "0.0")
            ]
            orders = client.get_pending_orders(inst_id).get("data", [])
            algos = client.get_pending_algo_orders(ord_type="conditional", inst_id=inst_id, inst_type="SWAP").get("data", [])
        except OkxApiError as exc:
            checks.append(
                PreflightCheck(
                    BLOCK,
                    "account_read_failed",
                    inst_id,
                    "Failed to read OKX account state.",
                    {"error": str(exc), "okxCode": exc.okx_code},
                )
            )
            continue
        if positions and action in {"enter", "increase", "hold"}:
            checks.append(
                PreflightCheck(
                    WARN,
                    "existing_position",
                    inst_id,
                    "Existing position found for this instrument.",
                    {"count": len(positions), "positions": summarize_positions(positions)},
                )
            )
        elif positions and action in {"decrease", "exit"}:
            checks.append(
                PreflightCheck(
                    PASS,
                    "existing_position_for_reduce",
                    inst_id,
                    "Existing position found for reduce/exit intent.",
                    {"count": len(positions), "positions": summarize_positions(positions)},
                )
            )
        else:
            checks.append(PreflightCheck(PASS, "no_existing_position", inst_id, "No existing position found.", {}))
        if orders:
            owned_orders, foreign_orders = split_bot_orders(intent, orders)
            if owned_orders:
                checks.append(
                    PreflightCheck(
                        WARN,
                        "bot_pending_orders_exist",
                        inst_id,
                        "Pending normal orders from this portfolio bot prefix exist and can be adopted.",
                        {"count": len(owned_orders), "orders": summarize_orders(owned_orders)},
                    )
                )
            if not foreign_orders:
                checks.append(PreflightCheck(PASS, "no_foreign_pending_orders", inst_id, "No foreign pending normal orders found.", {}))
                checks.append(PreflightCheck(PASS, "no_pending_orders", inst_id, "No blocking pending normal orders found.", {}))
            else:
                checks.append(
                    PreflightCheck(
                        BLOCK,
                        "pending_orders_exist",
                        inst_id,
                        "Foreign pending normal orders exist for this instrument.",
                        {"count": len(foreign_orders), "orders": summarize_orders(foreign_orders)},
                    )
                )
        else:
            checks.append(PreflightCheck(PASS, "no_pending_orders", inst_id, "No pending normal orders found.", {}))
        if algos:
            owned_algos, foreign_algos = split_bot_algos(intent, algos)
            if owned_algos:
                checks.append(
                    PreflightCheck(
                        WARN,
                        "bot_pending_algo_orders_exist",
                        inst_id,
                        "Pending conditional algo orders from this portfolio bot prefix exist and can be adopted.",
                        {"count": len(owned_algos), "algos": summarize_algos(owned_algos)},
                    )
                )
            if not foreign_algos:
                checks.append(PreflightCheck(PASS, "no_foreign_pending_algo_orders", inst_id, "No foreign pending conditional algo orders found.", {}))
                checks.append(PreflightCheck(PASS, "no_pending_algo_orders", inst_id, "No blocking pending conditional algo orders found.", {}))
            else:
                checks.append(
                    PreflightCheck(
                        BLOCK,
                        "pending_algo_orders_exist",
                        inst_id,
                        "Foreign pending conditional algo orders exist for this instrument.",
                        {"count": len(foreign_algos), "algos": summarize_algos(foreign_algos)},
                    )
                )
        else:
            checks.append(PreflightCheck(PASS, "no_pending_algo_orders", inst_id, "No pending conditional algo orders found.", {}))
        if action in {"enter", "increase", "hold"} and equity > 0:
            checks.extend(check_min_contract_capacity(intent, candidates.get(inst_id, {}), equity))
    return checks


def split_bot_orders(intent: dict[str, Any], orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prefix = str(intent.get("bot_prefix") or "")
    if not prefix:
        return [], orders
    owned: list[dict[str, Any]] = []
    foreign: list[dict[str, Any]] = []
    for order in orders:
        cl_ord_id = str(order.get("clOrdId") or order.get("cl_ord_id") or "")
        (owned if cl_ord_id.startswith(prefix) else foreign).append(order)
    return owned, foreign


def split_bot_algos(intent: dict[str, Any], algos: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prefix = str(intent.get("bot_prefix") or "")
    stop_prefix = f"xs{prefix}" if prefix else ""
    if not stop_prefix:
        return [], algos
    owned: list[dict[str, Any]] = []
    foreign: list[dict[str, Any]] = []
    for algo in algos:
        algo_cl_ord_id = str(algo.get("algoClOrdId") or algo.get("algo_cl_ord_id") or "")
        (owned if algo_cl_ord_id.startswith(stop_prefix) else foreign).append(algo)
    return owned, foreign


def load_candidate_metadata(intents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    report_dirs: set[Path] = set()
    for intent in intents:
        runtime_path = intent.get("runtime_config_path")
        if not runtime_path:
            continue
        path = Path(str(runtime_path))
        if path.parent.name == "runtime_configs":
            report_dirs.add(path.parent.parent)
    candidates: dict[str, dict[str, Any]] = {}
    for report_dir in report_dirs:
        path = report_dir / "candidates.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in payload.get("candidates", []):
            if isinstance(item, dict) and item.get("inst_id"):
                candidates[str(item["inst_id"])] = item
    return candidates


def check_min_contract_capacity(
    intent: dict[str, Any],
    candidate: dict[str, Any],
    equity: Decimal,
) -> list[PreflightCheck]:
    inst_id = str(intent.get("inst_id", ""))
    runtime_path = Path(str(intent.get("runtime_config_path", ""))) if intent.get("runtime_config_path") else None
    if not runtime_path or not runtime_path.exists():
        return []
    try:
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not candidate:
        return [
            PreflightCheck(
                WARN,
                "candidate_metadata_missing",
                inst_id,
                "Candidate metadata is missing; min contract capacity check was skipped.",
                {"runtimeConfigPath": str(runtime_path)},
            )
        ]

    mark = dec(candidate.get("last"))
    ct_val = dec(candidate.get("ct_val"))
    min_sz = dec(candidate.get("min_sz"))
    leverage = max(dec(runtime.get("leverage")), Decimal("1"))
    max_margin_pct = dec(runtime.get("maxMarginPct"))
    if mark <= 0 or ct_val <= 0 or min_sz <= 0 or max_margin_pct <= 0:
        return [
            PreflightCheck(
                WARN,
                "min_contract_capacity_unavailable",
                inst_id,
                "Insufficient metadata for min contract capacity check.",
                {
                    "mark": plain(mark),
                    "ctVal": plain(ct_val),
                    "minSz": plain(min_sz),
                    "maxMarginPct": plain(max_margin_pct),
                },
            )
        ]
    min_contract_margin = min_sz * ct_val * mark / leverage
    min_contract_margin_pct = min_contract_margin / equity * Decimal("100")
    detail = {
        "equity": plain(equity),
        "mark": plain(mark),
        "ctVal": plain(ct_val),
        "minSz": plain(min_sz),
        "leverage": plain(leverage),
        "minContractMargin": plain(min_contract_margin),
        "minContractMarginPct": plain(min_contract_margin_pct),
        "maxMarginPct": plain(max_margin_pct),
        "orderSz": str(runtime.get("orderSz", "")),
        "maxPosition": str(runtime.get("maxPosition", "")),
    }
    if min_contract_margin_pct > max_margin_pct:
        return [
            PreflightCheck(
                WARN,
                "min_contract_exceeds_margin_cap",
                inst_id,
                "Minimum contract margin exceeds runtime maxMarginPct; live bot may resolve open sizing to zero.",
                detail,
            )
        ]
    return [
        PreflightCheck(
            PASS,
            "min_contract_within_margin_cap",
            inst_id,
            "Minimum contract margin fits within runtime maxMarginPct.",
            detail,
        )
    ]


def account_equity(balance_payload: dict[str, Any]) -> Decimal:
    data = balance_payload.get("data", [])
    account = data[0] if data else {}
    equity = dec(account.get("totalEq"))
    for item in account.get("details", []) or []:
        if item.get("ccy") == "USDT":
            return dec(item.get("eq"), equity)
    return equity


def write_preflight_report(report_dir: Path, checks: list[PreflightCheck], *, include_account: bool) -> Path:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blocked = any(check.severity == BLOCK for check in checks)
    payload = {
        "generatedAt": generated_at,
        "status": "blocked" if blocked else "pass",
        "includeAccount": include_account,
        "checks": [check_to_dict(check) for check in checks],
    }
    json_path = report_dir / "preflight_report.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_preflight_markdown(report_dir / "preflight_report.md", generated_at, checks, include_account=include_account)
    return json_path


def write_preflight_markdown(path: Path, generated_at: str, checks: list[PreflightCheck], *, include_account: bool) -> None:
    blocked = any(check.severity == BLOCK for check in checks)
    lines = [
        "# Portfolio Execution Preflight",
        "",
        f"- Generated: `{generated_at}`",
        f"- Status: `{'blocked' if blocked else 'pass'}`",
        f"- Account checks: `{'included' if include_account else 'skipped'}`",
        "",
        "| Severity | Code | Instrument | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in checks:
        lines.append(f"| {check.severity} | {check.code} | {check.inst_id} | {check.message} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def list_bot_processes() -> list[ProcessSnapshot]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,cmd="],
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    processes = []
    current_pid = str(os.getpid())
    for raw_line in result.stdout.splitlines():
        parts = raw_line.strip().split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid, ppid, command = parts
        if pid == current_pid:
            continue
        if "auto_grid_bot.py" in command or "portfolio_rebalancer.py" in command:
            processes.append(ProcessSnapshot(pid=pid, ppid=ppid, command=command))
    return processes


def summarize_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "posSide": item.get("posSide"),
            "pos": item.get("pos"),
            "avgPx": item.get("avgPx"),
            "upl": item.get("upl"),
        }
        for item in positions[:20]
    ]


def summarize_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ordId": item.get("ordId"),
            "clOrdId": item.get("clOrdId"),
            "side": item.get("side"),
            "posSide": item.get("posSide"),
            "sz": item.get("sz"),
            "px": item.get("px"),
            "reduceOnly": item.get("reduceOnly"),
        }
        for item in orders[:20]
    ]


def summarize_algos(algos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "algoId": item.get("algoId"),
            "algoClOrdId": item.get("algoClOrdId"),
            "side": item.get("side"),
            "posSide": item.get("posSide"),
            "sz": item.get("sz"),
            "slTriggerPx": item.get("slTriggerPx"),
        }
        for item in algos[:20]
    ]


def check_to_dict(check: PreflightCheck) -> dict[str, Any]:
    return asdict(check)


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


if __name__ == "__main__":
    raise SystemExit(main())
