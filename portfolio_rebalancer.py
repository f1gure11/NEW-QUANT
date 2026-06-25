from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

from okx_client import OkxApiError, OkxRestClient, load_env
from scoring import plain


LOG_PATH = Path("data") / "okx" / "portfolio_rebalancer_actions.jsonl"


@dataclass(slots=True)
class RebalanceTarget:
    inst_id: str
    action: str
    current_margin: Decimal
    target_margin: Decimal
    delta_margin: Decimal


@dataclass(slots=True)
class ReduceOrder:
    inst_id: str
    side: str
    pos_side: str
    sz: Decimal
    ord_type: str
    px: Decimal | None
    reason: str


def main() -> int:
    global LOG_PATH
    args = parse_args()
    LOG_PATH = Path(args.log_path)
    if args.live:
        require_live_permission(args.confirm_live)
        load_env()
    client = OkxRestClient.from_env() if args.live or args.include_account else public_client_from_env()
    while True:
        try:
            run_once(client, args)
        except OkxApiError as exc:
            log_event("okx_error", {"error": str(exc), "code": exc.okx_code, "response": exc.response})
            print(f"OKX error: {exc}")
        if args.once:
            break
        time.sleep(args.interval)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute reduce-only portfolio rebalance actions from a portfolio report.")
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--inst-id", default="", help="Limit reduce actions to one instrument.")
    parser.add_argument("--log-path", default=str(LOG_PATH))
    parser.add_argument("--ord-type", choices=("market", "limit"), default="market")
    parser.add_argument("--slippage-bps", default="50")
    parser.add_argument("--cancel-pending", action="store_true")
    parser.add_argument("--cancel-algos", action="store_true")
    parser.add_argument("--min-reduce-margin", default="0.05")
    parser.add_argument("--include-account", action="store_true", help="Use private account reads in dry-run mode.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=60)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live", default="")
    return parser.parse_args()


def run_once(client: OkxRestClient, args: argparse.Namespace) -> list[ReduceOrder]:
    targets = load_rebalance_targets(Path(args.report_dir), args.inst_id)
    if not targets:
        print("No decrease/exit rebalance actions found.")
        return []
    if not (args.live or args.include_account):
        for target in targets:
            print(
                f"DRY reduce plan {target.inst_id} action={target.action} "
                f"delta_margin={plain(target.delta_margin)}; pass --include-account to size reduce-only orders."
            )
        log_event("dry_plan_without_account", {"targets": [target_to_dict(target) for target in targets]})
        return []

    positions = client.get_positions("SWAP").get("data", [])
    orders: list[ReduceOrder] = []
    for target in targets:
        target_positions = [
            item for item in positions
            if item.get("instId") == target.inst_id and abs(dec(item.get("pos"))) > 0
        ]
        target_orders = reduce_orders_for_target(
            target,
            target_positions,
            ord_type=args.ord_type,
            slippage_bps=dec(args.slippage_bps),
            min_reduce_margin=dec(args.min_reduce_margin),
        )
        if not target_orders:
            print(f"No reduce needed for {target.inst_id} action={target.action}.")
            continue
        if args.cancel_pending:
            cancel_pending_orders(client, target.inst_id, live=args.live)
        if args.cancel_algos:
            cancel_pending_algos(client, target.inst_id, live=args.live)
        for order in target_orders:
            place_reduce_order(client, order, live=args.live)
        orders.extend(target_orders)
    return orders


def load_rebalance_targets(report_dir: Path, inst_id: str = "") -> list[RebalanceTarget]:
    path = report_dir / "rebalance_plan.json"
    if not path.exists():
        raise FileNotFoundError(f"rebalance plan missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    targets = []
    for item in payload.get("actions", []):
        action = str(item.get("action", ""))
        item_inst_id = str(item.get("inst_id", ""))
        if action not in {"decrease", "exit"}:
            continue
        if inst_id and item_inst_id != inst_id:
            continue
        targets.append(
            RebalanceTarget(
                inst_id=item_inst_id,
                action=action,
                current_margin=dec(item.get("current_margin")),
                target_margin=dec(item.get("target_margin")),
                delta_margin=dec(item.get("delta_margin")),
            )
        )
    return targets


def reduce_orders_for_target(
    target: RebalanceTarget,
    positions: list[dict[str, Any]],
    *,
    ord_type: str,
    slippage_bps: Decimal,
    min_reduce_margin: Decimal,
) -> list[ReduceOrder]:
    if target.current_margin <= 0:
        return []
    reduce_margin = target.current_margin if target.action == "exit" else max(Decimal("0"), -target.delta_margin)
    if reduce_margin < min_reduce_margin:
        return []
    ratio = min(Decimal("1"), reduce_margin / target.current_margin)
    orders: list[ReduceOrder] = []
    for position in positions:
        pos_side = str(position.get("posSide", ""))
        if pos_side not in {"long", "short"}:
            continue
        size = abs(dec(position.get("pos")))
        if size <= 0:
            continue
        lot_sz = dec(position.get("lotSz"), Decimal("0"))
        reduce_size = size if target.action == "exit" else round_size_down(size * ratio, lot_sz)
        if reduce_size <= 0:
            continue
        mark_px = dec(position.get("markPx"), dec(position.get("last"), dec(position.get("avgPx"))))
        side = "sell" if pos_side == "long" else "buy"
        px = None if ord_type == "market" else close_limit_price(side, mark_px, slippage_bps)
        orders.append(
            ReduceOrder(
                inst_id=target.inst_id,
                side=side,
                pos_side=pos_side,
                sz=reduce_size,
                ord_type=ord_type,
                px=px,
                reason=target.action,
            )
        )
    return orders


def cancel_pending_orders(client: OkxRestClient, inst_id: str, *, live: bool) -> None:
    orders = client.get_pending_orders(inst_id).get("data", [])
    payload = [
        {"instId": inst_id, "ordId": order.get("ordId", ""), "clOrdId": order.get("clOrdId", "")}
        for order in orders
    ]
    if payload and live:
        response = client.cancel_orders(payload)
    else:
        response = {"dryRun": True, "data": payload}
    print(f"{'LIVE' if live else 'DRY'} cancel_pending {inst_id} count={len(payload)}")
    log_event("cancel_pending", {"live": live, "instId": inst_id, "orders": payload, "response": response})


def cancel_pending_algos(client: OkxRestClient, inst_id: str, *, live: bool) -> None:
    algos = client.get_pending_algo_orders(ord_type="conditional", inst_id=inst_id, inst_type="SWAP").get("data", [])
    payload = [
        {"instId": inst_id, "algoId": algo.get("algoId", "")}
        for algo in algos
        if algo.get("algoId")
    ]
    if payload and live:
        response = client.cancel_algo_orders(payload)
    else:
        response = {"dryRun": True, "data": payload}
    print(f"{'LIVE' if live else 'DRY'} cancel_algos {inst_id} count={len(payload)}")
    log_event("cancel_algos", {"live": live, "instId": inst_id, "algos": payload, "response": response})


def place_reduce_order(client: OkxRestClient, order: ReduceOrder, *, live: bool) -> None:
    payload: dict[str, Any] = {
        "inst_id": order.inst_id,
        "td_mode": "cross",
        "side": order.side,
        "ord_type": order.ord_type,
        "sz": plain(order.sz),
        "pos_side": order.pos_side,
        "reduce_only": True,
        "cl_ord_id": reduce_client_order_id(order),
    }
    if order.px is not None:
        payload["px"] = plain(order.px)
    if live:
        response = client.place_order(**payload)
    else:
        response = {"dryRun": True, "data": [payload]}
    print(
        f"{'LIVE' if live else 'DRY'} reduce {order.reason} {order.inst_id} "
        f"{order.side} {order.pos_side} {plain(order.sz)} @{plain(order.px) if order.px else 'MKT'}"
    )
    log_event("reduce_order", {"live": live, "order": order_to_dict(order), "payload": payload, "response": response})


def close_limit_price(side: str, mark_px: Decimal, slippage_bps: Decimal) -> Decimal:
    if mark_px <= 0:
        return Decimal("0")
    bump = slippage_bps / Decimal("10000")
    return mark_px * (Decimal("1") + bump) if side == "buy" else mark_px * (Decimal("1") - bump)


def round_size_down(value: Decimal, lot_sz: Decimal) -> Decimal:
    if lot_sz <= 0:
        return value
    return (value / lot_sz).to_integral_value(rounding=ROUND_DOWN) * lot_sz


def reduce_client_order_id(order: ReduceOrder) -> str:
    prefix = "prb"
    side = "b" if order.side == "buy" else "s"
    pos = "l" if order.pos_side == "long" else "s"
    stamp = str(int(time.time() * 1000))[-8:]
    return f"{prefix}{side}{pos}{stamp}"[:32]


def require_live_permission(confirm_live: str) -> None:
    if confirm_live != "I_UNDERSTAND":
        raise RuntimeError("Live trading requires --confirm-live I_UNDERSTAND")


def public_client_from_env() -> OkxRestClient:
    import os

    return OkxRestClient(
        base_url=os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/"),
        proxy_url=os.getenv("OKX_PROXY", ""),
        user_agent=os.getenv("OKX_USER_AGENT", "curl/8.10.1"),
    )


def log_event(kind: str, payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "kind": kind,
        "payload": jsonable(payload),
    }
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def target_to_dict(target: RebalanceTarget) -> dict[str, Any]:
    return jsonable(asdict(target))


def order_to_dict(order: ReduceOrder) -> dict[str, Any]:
    return jsonable(asdict(order))


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


if __name__ == "__main__":
    raise SystemExit(main())
