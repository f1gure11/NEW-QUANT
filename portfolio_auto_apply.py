from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from okx_client import load_env


PROJECT_ROOT = Path(__file__).resolve().parent
REPORT_ROOT = PROJECT_ROOT / "reports" / "portfolio"
LOG_PATH = PROJECT_ROOT / "data" / "okx" / "portfolio_auto_apply_actions.jsonl"
STATE_PATH = PROJECT_ROOT / "data" / "okx" / "portfolio_auto_apply_state.json"
LOCK_PATH = PROJECT_ROOT / "data" / "okx" / "portfolio_auto_apply.lock"


@dataclass(slots=True)
class BotProcess:
    inst_id: str
    pid: int
    runtime_path: Path
    command: list[str]


@dataclass(slots=True)
class ApplyPlan:
    report_dir: str
    target_insts: list[str]
    reduce_insts: list[str]
    exit_insts: list[str]
    decrease_insts: list[str]
    stop_insts: list[str]
    hot_update_insts: list[str]
    start_insts: list[str]
    skipped_insts: list[str]


def main() -> int:
    args = parse_args()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("portfolio auto apply already running; skipping.")
            return 0
        return run(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply the latest live portfolio report to running portfolio bots.")
    parser.add_argument("--report-dir", default="", help="Report directory to apply. Defaults to the latest portfolio report.")
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8765")
    parser.add_argument("--max-changes", type=int, default=0, help="Max stop/start/reduce changes. 0 means unlimited.")
    parser.add_argument("--allow-blocked-start", action="store_true", help="Pass allowBlocked=true to dashboard starts.")
    parser.add_argument("--confirm-live", default="")
    parser.add_argument("--force", action="store_true", help="Apply even when live trading env guard is locked.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stop-timeout", type=float, default=12.0)
    parser.add_argument("--post-reduce-delay", type=float, default=2.0)
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    report_dir = resolve_report_dir(args.report_dir)
    require_live_guard(args)
    runtime_intents, reduce_intents = load_execution_intents(report_dir)
    actions = load_rebalance_actions(report_dir)
    processes = list_portfolio_bot_processes()
    plan = build_apply_plan(
        report_dir=report_dir,
        runtime_intents=runtime_intents,
        reduce_intents=reduce_intents,
        actions=actions,
        processes=processes,
        max_changes=args.max_changes,
    )
    print(json.dumps({"autoApplyPlan": asdict(plan)}, indent=2))
    log_event("plan", asdict(plan))
    if not plan.target_insts:
        log_event("blocked_empty_targets", {"reportDir": str(report_dir), "plan": asdict(plan)})
        raise RuntimeError("Auto apply blocked: latest portfolio report has no target instruments.")

    if args.dry_run:
        write_state(report_dir, plan, {"dryRun": True})
        return 0

    for inst_id in plan.stop_insts:
        process = processes.get(inst_id)
        if process:
            stop_process(process, timeout=args.stop_timeout)

    for inst_id in plan.reduce_insts:
        intent = reduce_intents.get(inst_id)
        if not intent:
            raise RuntimeError(f"Reduce intent missing for {inst_id}.")
        run_reduce_once(report_dir, inst_id, intent)
        if args.post_reduce_delay > 0:
            time.sleep(args.post_reduce_delay)

    processes = list_portfolio_bot_processes()
    hot_updates = []
    for inst_id in plan.hot_update_insts:
        process = processes.get(inst_id)
        intent = runtime_intents.get(inst_id)
        if process and intent:
            hot_updates.append(hot_update_runtime(report_dir, process, intent))

    processes = list_portfolio_bot_processes()
    start_insts = [inst_id for inst_id in plan.start_insts if inst_id not in processes]
    start_result = {}
    if start_insts:
        start_result = dashboard_start(
            args.dashboard_url,
            start_insts,
            allow_blocked=args.allow_blocked_start,
        )

    result = {
        "stopped": plan.stop_insts,
        "reduced": plan.reduce_insts,
        "hotUpdates": hot_updates,
        "startInsts": start_insts,
        "startResult": start_result,
        "skippedInsts": plan.skipped_insts,
    }
    log_event("applied", {"reportDir": str(report_dir), **result})
    write_state(report_dir, plan, result)
    print(json.dumps({"autoApplyResult": result}, indent=2))
    return 0


def require_live_guard(args: argparse.Namespace) -> None:
    load_env()
    if args.force:
        return
    if os.getenv("OKX_ENABLE_LIVE_TRADING", "0") != "1":
        raise PermissionError("Live trading is locked. Set OKX_ENABLE_LIVE_TRADING=1 before auto applying.")
    if args.confirm_live != "I_UNDERSTAND":
        raise PermissionError("Portfolio auto apply requires --confirm-live I_UNDERSTAND.")


def resolve_report_dir(value: str) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = REPORT_ROOT / path
        if not path.exists():
            raise FileNotFoundError(f"Portfolio report not found: {path}")
        return path
    latest = latest_report_dir()
    if not latest:
        raise FileNotFoundError("No portfolio report found.")
    return latest


def latest_report_dir() -> Path | None:
    if not REPORT_ROOT.exists():
        return None
    dirs = [path for path in REPORT_ROOT.iterdir() if path.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dirs[0]


def load_execution_intents(report_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = read_json(report_dir / "execution_intents.json")
    runtime: dict[str, dict[str, Any]] = {}
    reduce: dict[str, dict[str, Any]] = {}
    for intent in payload.get("intents", []) if isinstance(payload.get("intents", []), list) else []:
        inst_id = str(intent.get("inst_id", ""))
        if not inst_id:
            continue
        if intent.get("status") == "runtime_config_ready" and intent.get("runtime_config_path"):
            runtime[inst_id] = intent
        elif intent.get("status") == "rebalance_reduce_ready":
            reduce[inst_id] = intent
    return runtime, reduce


def load_rebalance_actions(report_dir: Path) -> dict[str, str]:
    payload = read_json(report_dir / "rebalance_plan.json")
    actions: dict[str, str] = {}
    for item in payload.get("actions", []) if isinstance(payload.get("actions", []), list) else []:
        inst_id = str(item.get("inst_id", ""))
        action = str(item.get("action", ""))
        if inst_id:
            actions[inst_id] = action
    return actions


def build_apply_plan(
    *,
    report_dir: Path,
    runtime_intents: dict[str, dict[str, Any]],
    reduce_intents: dict[str, dict[str, Any]],
    actions: dict[str, str],
    processes: dict[str, BotProcess],
    max_changes: int = 0,
) -> ApplyPlan:
    target_insts = sorted(runtime_intents)
    target_set = set(target_insts)
    reduce_insts = sorted(reduce_intents)
    exit_insts = sorted(inst for inst in reduce_insts if actions.get(inst) == "exit")
    decrease_insts = sorted(inst for inst in reduce_insts if actions.get(inst) == "decrease")
    stop_insts = sorted(inst for inst in processes if inst not in target_set or inst in reduce_insts)

    current_target_processes = sorted(inst for inst in target_insts if inst in processes and inst not in stop_insts)
    hot_update_insts = current_target_processes
    start_insts = sorted(inst for inst in target_insts if inst not in processes or inst in stop_insts)
    change_order = unique_ordered([*stop_insts, *reduce_insts, *start_insts])
    skipped: list[str] = []
    if max_changes > 0 and len(change_order) > max_changes:
        allowed = set(change_order[:max_changes])
        skipped = [inst for inst in change_order[max_changes:]]
        stop_insts = [inst for inst in stop_insts if inst in allowed]
        reduce_insts = [inst for inst in reduce_insts if inst in allowed]
        exit_insts = [inst for inst in exit_insts if inst in allowed]
        decrease_insts = [inst for inst in decrease_insts if inst in allowed]
        start_insts = [inst for inst in start_insts if inst in allowed]
        hot_update_insts = [inst for inst in hot_update_insts if inst not in skipped]

    return ApplyPlan(
        report_dir=str(report_dir),
        target_insts=target_insts,
        reduce_insts=reduce_insts,
        exit_insts=exit_insts,
        decrease_insts=decrease_insts,
        stop_insts=stop_insts,
        hot_update_insts=hot_update_insts,
        start_insts=start_insts,
        skipped_insts=skipped,
    )


def unique_ordered(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def list_portfolio_bot_processes() -> dict[str, BotProcess]:
    processes: dict[str, BotProcess] = {}
    proc = Path("/proc")
    if not proc.exists():
        return processes
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            raw = (item / "cmdline").read_bytes()
        except Exception:
            continue
        parts = [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]
        if not parts or not any(part.endswith("auto_grid_bot.py") or part == "auto_grid_bot.py" for part in parts):
            continue
        if "--inst-id" not in parts or "--runtime-config" not in parts:
            continue
        try:
            inst_id = parts[parts.index("--inst-id") + 1]
            runtime_path = Path(parts[parts.index("--runtime-config") + 1])
        except Exception:
            continue
        if not is_portfolio_runtime_path(runtime_path):
            continue
        processes[inst_id] = BotProcess(inst_id=inst_id, pid=int(item.name), runtime_path=runtime_path, command=parts)
    return processes


def is_portfolio_runtime_path(path: Path) -> bool:
    text = str(path)
    return "/reports/portfolio/" in text or text.startswith("reports/portfolio/")


def stop_process(process: BotProcess, *, timeout: float) -> None:
    print(f"Stopping {process.inst_id} pid={process.pid}")
    log_event("stop_bot", {"instId": process.inst_id, "pid": process.pid, "runtimePath": str(process.runtime_path)})
    try:
        os.kill(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not (Path("/proc") / str(process.pid)).exists():
            return
        time.sleep(0.25)
    try:
        os.kill(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def run_reduce_once(report_dir: Path, inst_id: str, intent: dict[str, Any]) -> None:
    command = live_command_from_dry_run(str(intent.get("dry_run_command", "")))
    if not command:
        raise RuntimeError(f"Reduce command missing for {inst_id}.")
    print("Running reduce " + " ".join(command))
    log_event("reduce_once", {"instId": inst_id, "reportDir": str(report_dir), "command": command})
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    log_event(
        "reduce_once_result",
        {
            "instId": inst_id,
            "returnCode": completed.returncode,
            "stdoutTail": completed.stdout[-4000:],
            "stderrTail": completed.stderr[-4000:],
        },
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Reduce failed for {inst_id}: returnCode={completed.returncode}")


def live_command_from_dry_run(dry_run_command: str) -> list[str]:
    if not dry_run_command:
        return []
    parts = shlex.split(dry_run_command)
    while parts and is_env_assignment(parts[0]):
        parts = parts[1:]
    if parts and Path(parts[0]).name in {"python", "python3"}:
        parts[0] = sys.executable
    if "--live" not in parts:
        parts.append("--live")
    if "--confirm-live" not in parts:
        parts.extend(["--confirm-live", "I_UNDERSTAND"])
    return parts


def is_env_assignment(value: str) -> bool:
    if "=" not in value:
        return False
    key = value.split("=", 1)[0]
    return key.replace("_", "A").isalnum() and not key[:1].isdigit()


def hot_update_runtime(report_dir: Path, process: BotProcess, intent: dict[str, Any]) -> dict[str, Any]:
    source_path = Path(str(intent.get("runtime_config_path", "")))
    if not source_path.exists():
        raise FileNotFoundError(f"Runtime config missing for {process.inst_id}: {source_path}")
    payload = read_json(source_path)
    payload["autoAppliedFromReport"] = str(report_dir)
    payload["autoAppliedAt"] = now_iso()
    process.runtime_path.parent.mkdir(parents=True, exist_ok=True)
    process.runtime_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result = {"instId": process.inst_id, "from": str(source_path), "to": str(process.runtime_path), "pid": process.pid}
    log_event("hot_update_runtime", result)
    print(f"Hot updated {process.inst_id} runtime {process.runtime_path}")
    return result


def dashboard_start(dashboard_url: str, inst_ids: list[str], *, allow_blocked: bool) -> dict[str, Any]:
    payload = {
        "instIds": inst_ids,
        "executeRebalance": False,
        "tradingMode": "live",
        "allowBlocked": allow_blocked,
    }
    response = post_json(dashboard_url.rstrip("/") + "/api/portfolio/live/start", payload)
    log_event("dashboard_start", {"payload": payload, "response": response})
    return response


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Dashboard HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Dashboard request failed: {exc}") from exc
    parsed = json.loads(body)
    if not parsed.get("ok"):
        raise RuntimeError(f"Dashboard start failed: {parsed.get('error')}")
    return parsed


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_state(report_dir: Path, plan: ApplyPlan, result: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": now_iso(),
        "reportDir": str(report_dir),
        "plan": asdict(plan),
        "result": result,
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def log_event(kind: str, payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now_iso(), "kind": kind, "payload": payload}
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


if __name__ == "__main__":
    raise SystemExit(main())
