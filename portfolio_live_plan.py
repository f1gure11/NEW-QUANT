from __future__ import annotations

import argparse
import csv
import json
import shlex
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIVE_PLAN_FIELDS = [
    "inst_id",
    "status",
    "live_command",
    "systemd_draft_path",
    "note",
]


@dataclass(slots=True)
class LivePlanItem:
    inst_id: str
    status: str
    live_command: str
    systemd_draft_path: str
    note: str


def main() -> int:
    args = parse_args()
    report_dir = Path(args.report_dir)
    items = write_live_plan(report_dir)
    blocked = any(item.status != "ready" for item in items)
    print(f"live_plan={report_dir / 'live_plan.json'}")
    print(f"live_plan_status={'blocked' if blocked else 'ready'}")
    return 2 if blocked else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate live start drafts from a passed portfolio preflight report. Does not start bots.")
    parser.add_argument("report_dir", help="Portfolio report directory containing execution_intents.json and preflight_report.json.")
    return parser.parse_args()


def write_live_plan(
    report_dir: Path,
    inst_ids: set[str] | None = None,
    *,
    allow_blocked_preflight: bool = False,
) -> list[LivePlanItem]:
    intents = load_intents(report_dir)
    if inst_ids:
        intents = [intent for intent in intents if str(intent.get("inst_id", "")) in inst_ids]
    preflight = load_preflight(report_dir)
    items = build_live_plan_items(report_dir, intents, preflight, allow_blocked_preflight=allow_blocked_preflight)
    systemd_dir = report_dir / "systemd"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        if item.status == "ready" and item.systemd_draft_path:
            Path(item.systemd_draft_path).write_text(systemd_unit_draft(item), encoding="utf-8")

    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "dashboard_live_start_plan",
        "status": live_plan_status(items),
        "items": [item_to_dict(item) for item in items],
    }
    (report_dir / "live_plan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with (report_dir / "live_plan.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=LIVE_PLAN_FIELDS)
        writer.writeheader()
        for item in items:
            row = item_to_dict(item)
            writer.writerow({field: row.get(field, "") for field in LIVE_PLAN_FIELDS})
    write_live_plan_markdown(report_dir / "live_plan.md", payload)
    return items


def build_live_plan_items(
    report_dir: Path,
    intents: list[dict[str, Any]],
    preflight: dict[str, Any],
    *,
    allow_blocked_preflight: bool = False,
) -> list[LivePlanItem]:
    trading_mode = report_trading_mode(report_dir, intents)
    if trading_mode != "live":
        return [
            LivePlanItem(
                inst_id="",
                status="blocked",
                live_command="",
                systemd_draft_path="",
                note=f"rebalance report tradingMode must be live, got {trading_mode}",
            )
        ]

    if not preflight.get("includeAccount") and not allow_blocked_preflight:
        return [
            LivePlanItem(
                inst_id="",
                status="blocked",
                live_command="",
                systemd_draft_path="",
                note="preflight_report.json must have status=pass and includeAccount=true unless blocked preflight is explicitly allowed",
            )
        ]

    preflight_checks = preflight.get("checks", [])
    has_preflight_details = isinstance(preflight_checks, list) and bool(preflight_checks)
    if preflight.get("status") != "pass" and not allow_blocked_preflight and not has_preflight_details:
        return [
            LivePlanItem(
                inst_id="",
                status="blocked",
                live_command="",
                systemd_draft_path="",
                note="preflight_report.json must have status=pass and includeAccount=true unless blocked preflight is explicitly allowed",
            )
        ]

    global_preflight_blocks = preflight_block_notes(preflight, "")
    if global_preflight_blocks and not allow_blocked_preflight:
        return [
            LivePlanItem(
                inst_id="",
                status="blocked",
                live_command="",
                systemd_draft_path="",
                note="preflight blocked: " + "; ".join(global_preflight_blocks),
            )
        ]

    items: list[LivePlanItem] = []
    for intent in intents:
        inst_id = str(intent.get("inst_id", ""))
        if intent.get("status") == "rebalance_reduce_ready":
            items.append(
                LivePlanItem(
                    inst_id=inst_id,
                    status="review_only",
                    live_command="",
                    systemd_draft_path="",
                    note="reduce-only rebalance can be executed once by dashboard after account-aware preflight",
                )
            )
            continue
        if intent.get("status") != "runtime_config_ready":
            items.append(
                LivePlanItem(
                    inst_id=inst_id,
                    status="blocked",
                    live_command="",
                    systemd_draft_path="",
                    note=f"intent status is {intent.get('status')}",
                )
            )
            continue
        preflight_blocks = preflight_block_notes(preflight, inst_id)
        if preflight_blocks and not allow_blocked_preflight:
            items.append(
                LivePlanItem(
                    inst_id=inst_id,
                    status="blocked",
                    live_command="",
                    systemd_draft_path="",
                    note="preflight blocked: " + "; ".join(preflight_blocks),
                )
            )
            continue
        dry_run_command = str(intent.get("dry_run_command", ""))
        if "--live" in shlex.split(dry_run_command):
            items.append(
                LivePlanItem(
                    inst_id=inst_id,
                    status="blocked",
                    live_command="",
                    systemd_draft_path="",
                    note="dry-run command already contains --live",
                )
            )
            continue
        runtime_path = Path(str(intent.get("runtime_config_path", "")))
        if not runtime_path.exists():
            items.append(
                LivePlanItem(
                    inst_id=inst_id,
                    status="blocked",
                    live_command="",
                    systemd_draft_path="",
                    note="runtime config draft missing",
                )
            )
            continue
        live_command = live_command_from_dry_run(dry_run_command)
        systemd_path = report_dir / "systemd" / f"okx-portfolio-{safe_unit_name(inst_id)}.service.draft"
        items.append(
            LivePlanItem(
                inst_id=inst_id,
                status="ready",
                live_command=live_command,
                systemd_draft_path=str(systemd_path),
                note=(
                    "ready for dashboard live start after explicitly allowed blocked account-aware preflight"
                    if allow_blocked_preflight and preflight.get("status") != "pass"
                    else "ready for dashboard live start after account-aware preflight"
                ),
            )
        )
    if not items:
        items.append(LivePlanItem("", "blocked", "", "", "no execution intents found"))
    return items


def report_trading_mode(report_dir: Path, intents: list[dict[str, Any]]) -> str:
    payload: dict[str, Any] = {}
    path = report_dir / "rebalance_plan.json"
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            payload = loaded if isinstance(loaded, dict) else {}
        except Exception:
            payload = {}
    mode = str(payload.get("tradingMode") or "").strip()
    if mode in {"backtest", "paper", "live"}:
        return mode
    if any(str(item.get("dry_run_command", "")).find("--live") >= 0 for item in intents):
        return "live"
    return "backtest"


def preflight_block_notes(preflight: dict[str, Any], inst_id: str) -> list[str]:
    checks = preflight.get("checks", [])
    if not isinstance(checks, list):
        return []
    notes = []
    for check in checks:
        if not isinstance(check, dict) or check.get("severity") != "block":
            continue
        check_inst_id = str(check.get("inst_id") or check.get("instId") or "")
        if check_inst_id != inst_id:
            continue
        code = str(check.get("code") or "preflight_block")
        message = str(check.get("message") or "").strip()
        notes.append(f"{code}: {message}" if message else code)
    return notes


def live_command_from_dry_run(dry_run_command: str) -> str:
    parts = shlex.split(dry_run_command)
    parts = [part for part in parts if part != "--once"]
    if "--set-leverage" not in parts:
        parts.append("--set-leverage")
    if "--live" not in parts:
        parts.append("--live")
    if "--confirm-live" not in parts:
        parts.extend(["--confirm-live", "I_UNDERSTAND"])
    return " ".join(shlex.quote(part) for part in parts)


def live_plan_status(items: list[LivePlanItem]) -> str:
    if any(item.status == "ready" for item in items):
        if any(item.status not in {"ready", "review_only"} for item in items):
            return "partial"
        return "ready"
    return "blocked"


def systemd_unit_draft(item: LivePlanItem) -> str:
    command = item.live_command
    if command.startswith("PYTHONPATH=. "):
        command = command.removeprefix("PYTHONPATH=. ")
    return "\n".join(
        [
            "[Unit]",
            f"Description=OKX Portfolio Grid Bot {item.inst_id}",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "User=okxbot",
            "Group=okxbot",
            "WorkingDirectory=/opt/okx-quant",
            "Environment=PYTHONUNBUFFERED=1",
            "Environment=PYTHONPATH=.",
            f"ExecStart=/opt/okx-quant/{command}",
            "Restart=on-failure",
            "RestartSec=15",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def write_live_plan_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Portfolio Live Start Draft",
        "",
        "This file is a dashboard live start plan. It does not mean the bots were started.",
        "",
        f"- Generated: `{payload['generatedAt']}`",
        f"- Status: `{payload['status']}`",
        "",
        "| Instrument | Status | Systemd Draft | Note |",
        "| --- | --- | --- | --- |",
    ]
    for item in payload["items"]:
        lines.append(
            f"| {item['inst_id']} | {item['status']} | {Path(item['systemd_draft_path']).name if item['systemd_draft_path'] else ''} | {item['note']} |"
        )
    lines.extend(
        [
            "",
            "Manual safeguards before using any live command:",
            "",
            "- Dashboard live start reruns account-aware preflight immediately before start.",
            "- Runtime-ready enter/increase/hold items can be started as live bots.",
            "- Reduce/exit items remain one-shot reduce-only operations and are review-only in this plan.",
            "- Review sizing, trend selection, and TP/SL values before enabling live mode.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_intents(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "execution_intents.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    intents = payload.get("intents", [])
    return intents if isinstance(intents, list) else []


def load_preflight(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "preflight_report.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def safe_unit_name(inst_id: str) -> str:
    return inst_id.lower().replace("-usdt-swap", "").replace("_", "-")


def item_to_dict(item: LivePlanItem) -> dict[str, Any]:
    return asdict(item)


if __name__ == "__main__":
    raise SystemExit(main())
