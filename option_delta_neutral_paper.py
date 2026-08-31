"""Read-only paper planner for a long BTC/ETH option straddle with a swap hedge.

The planner uses the public OKX option book and Black-Scholes Greeks to answer
the first practical question: what would a small, risk-budgeted entry look like
right now? It deliberately does not contain account or order methods. Option
quotes are treated as USD and converted to USDT at 1:1 for a paper estimate.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "delta_neutral_options"
OPTION_FAMILIES = {"BTC": "BTC-USD", "ETH": "ETH-USD"}


@dataclass(frozen=True, slots=True)
class OptionLeg:
    inst_id: str
    option_type: str
    expiry_ms: int
    strike: float
    ct_val: float
    ct_mult: float
    tick_size: float
    ask_px: float
    ask_sz: float
    bid_px: float
    bid_sz: float
    delta: float
    gamma: float
    theta_day: float
    vega: float
    bid_vol: float
    ask_vol: float
    quote_ts: int
    greek_ts: int


@dataclass(frozen=True, slots=True)
class SwapSpec:
    inst_id: str
    ct_val: float
    ct_mult: float
    lot_size: float
    min_size: float
    last_px: float
    bid_px: float
    ask_px: float


@dataclass(frozen=True, slots=True)
class StraddlePair:
    underlying: str
    option_family: str
    spot_px: float
    call: OptionLeg
    put: OptionLeg
    swap: SwapSpec
    retrieved_at: str


@dataclass(frozen=True, slots=True)
class PlanMetrics:
    contracts: int
    option_units: float
    option_notional_usd: float
    premium_usdt: float
    premium_pct_equity: float
    theta_per_day_usdt: float
    theta_pct_equity: float
    net_option_delta_units: float
    delta_threshold_units: float
    initial_delta_breach: bool
    hedge_contracts: float
    hedge_side: str
    hedge_units: float
    residual_delta_units: float
    hedge_notional_usd: float
    hedge_margin_usdt: float
    option_round_trip_spread_usdt: float
    hedge_round_trip_spread_usdt: float
    total_round_trip_spread_usdt: float
    spread_pct_entry_premium: float
    gamma_pnl_at_jump_usdt: float
    estimated_max_jump_loss_usdt: float
    estimated_max_jump_loss_pct: float
    estimated_no_move_day_pnl_usdt: float


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return []
    return [row for row in payload["data"] if isinstance(row, dict)]


def _round_nearest(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("step must be positive")
    return math.floor(value / step + 0.5) * step


def _iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000.0, timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only long straddle delta-neutral paper planner")
    parser.add_argument("--bases", nargs="+", choices=sorted(OPTION_FAMILIES), default=["BTC", "ETH"])
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--min-hours-to-expiry", type=float, default=20.0)
    parser.add_argument("--premium-budget-pct", type=float, default=5.0)
    parser.add_argument("--max-theta-day-pct", type=float, default=0.50)
    parser.add_argument("--max-hedge-margin-pct", type=float, default=10.0)
    parser.add_argument("--max-jump-loss-pct", type=float, default=0.50)
    parser.add_argument("--jump-shock-pct", type=float, default=1.0)
    parser.add_argument("--delta-threshold-pct", type=float, default=5.0)
    parser.add_argument("--hedge-interval-hours", type=float, default=6.0)
    parser.add_argument("--max-hedges-per-day", type=int, default=4)
    parser.add_argument("--hedge-leverage", type=float, default=1.0)
    parser.add_argument("--max-contracts", type=int, default=100_000)
    parser.add_argument("--output-dir", default="")
    return parser.parse_args()


def fetch_straddle_pair(client: OkxRestClient, base: str, *, now_ms: int, min_hours: float) -> StraddlePair:
    family = OPTION_FAMILIES[base]
    instruments = _rows(client.request("GET", "/api/v5/public/instruments", params={"instType": "OPTION", "uly": family}))
    tickers = {row.get("instId"): row for row in _rows(client.request("GET", "/api/v5/market/tickers", params={"instType": "OPTION", "uly": family}))}
    summaries = {row.get("instId"): row for row in _rows(client.request("GET", "/api/v5/public/opt-summary", params={"uly": family}))}
    index_rows = _rows(client.request("GET", "/api/v5/market/index-tickers", params={"instId": family}))
    spot = _num(index_rows[0].get("idxPx")) if index_rows else 0.0
    if spot <= 0:
        raise ValueError(f"{base}: public index price unavailable")

    min_expiry = now_ms + int(min_hours * 3_600_000)
    by_expiry: dict[int, dict[float, dict[str, OptionLeg]]] = {}
    for instrument in instruments:
        inst_id = str(instrument.get("instId") or "")
        # _UM is the linear USD-settled option family suited to a USDT swap hedge.
        if "_UM-" not in inst_id or instrument.get("state") != "live":
            continue
        expiry = int(_num(instrument.get("expTime")))
        if expiry < min_expiry or expiry <= now_ms:
            continue
        option_type = str(instrument.get("optType") or "").upper()
        if option_type not in {"C", "P"}:
            continue
        ticker = tickers.get(inst_id, {})
        summary = summaries.get(inst_id, {})
        ask_px = _num(ticker.get("askPx"))
        ask_sz = _num(ticker.get("askSz"))
        bid_px = _num(ticker.get("bidPx"))
        bid_sz = _num(ticker.get("bidSz"))
        if ask_px <= 0 or ask_sz <= 0:
            continue
        leg = OptionLeg(
            inst_id=inst_id,
            option_type=option_type,
            expiry_ms=expiry,
            strike=_num(instrument.get("stk")),
            ct_val=_num(instrument.get("ctVal"), 1.0),
            ct_mult=_num(instrument.get("ctMult"), 1.0),
            tick_size=_num(instrument.get("tickSz"), 0.0001),
            ask_px=ask_px,
            ask_sz=ask_sz,
            bid_px=bid_px,
            bid_sz=bid_sz,
            delta=_num(summary.get("deltaBS") or summary.get("delta")),
            gamma=_num(summary.get("gammaBS") or summary.get("gamma")),
            theta_day=_num(summary.get("thetaBS") or summary.get("theta")),
            vega=_num(summary.get("vegaBS") or summary.get("vega")),
            bid_vol=_num(summary.get("bidVol")),
            ask_vol=_num(summary.get("askVol")),
            quote_ts=int(_num(ticker.get("ts"))),
            greek_ts=int(_num(summary.get("ts"))),
        )
        by_expiry.setdefault(expiry, {}).setdefault(leg.strike, {})[option_type] = leg

    choices: list[tuple[float, float, int, OptionLeg, OptionLeg]] = []
    for expiry, strikes in by_expiry.items():
        for strike, legs in strikes.items():
            call, put = legs.get("C"), legs.get("P")
            if call is None or put is None or call.gamma <= 0 or put.gamma <= 0:
                continue
            spread = (call.ask_px - call.bid_px if call.bid_px > 0 else call.ask_px)
            spread += put.ask_px - put.bid_px if put.bid_px > 0 else put.ask_px
            choices.append((abs(strike / spot - 1.0), spread / max(spot * call.ct_mult * call.ct_val, 1e-12), expiry, call, put))
    if not choices:
        raise ValueError(f"{base}: no paired _UM call/put with executable asks after {min_hours:g}h")
    _, _, expiry, call, put = min(choices, key=lambda item: (item[2], item[0], item[1]))

    swap_id = f"{base}-USDT-SWAP"
    swap_rows = _rows(client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP", "instId": swap_id}))
    if not swap_rows:
        raise ValueError(f"{base}: {swap_id} metadata unavailable")
    swap_ticker_rows = _rows(client.request("GET", "/api/v5/market/ticker", params={"instId": swap_id}))
    swap_ticker = swap_ticker_rows[0] if swap_ticker_rows else {}
    swap_meta = swap_rows[0]
    swap = SwapSpec(
        inst_id=swap_id,
        ct_val=_num(swap_meta.get("ctVal"), 1.0),
        ct_mult=_num(swap_meta.get("ctMult"), 1.0),
        lot_size=_num(swap_meta.get("lotSz"), 0.01),
        min_size=_num(swap_meta.get("minSz"), 0.01),
        last_px=_num(swap_ticker.get("last"), spot),
        bid_px=_num(swap_ticker.get("bidPx"), _num(swap_ticker.get("last"), spot)),
        ask_px=_num(swap_ticker.get("askPx"), _num(swap_ticker.get("last"), spot)),
    )
    return StraddlePair(base, family, spot, call, put, swap, _iso_ms(now_ms))


def _metrics(pair: StraddlePair, contracts: int, *, equity: float, delta_threshold_pct: float, jump_shock_pct: float, hedge_leverage: float) -> PlanMetrics:
    call, put, swap = pair.call, pair.put, pair.swap
    units = contracts * call.ct_val * call.ct_mult
    option_notional = units * pair.spot_px
    premium = (call.ask_px * call.ct_val * call.ct_mult + put.ask_px * put.ct_val * put.ct_mult) * contracts
    theta = (call.theta_day * call.ct_val * call.ct_mult + put.theta_day * put.ct_val * put.ct_mult) * contracts
    delta = (call.delta * call.ct_val * call.ct_mult + put.delta * put.ct_val * put.ct_mult) * contracts
    # Delta is measured in underlying units, so the threshold must use the
    # single-leg underlying quantity rather than its USD notional.
    threshold = units * delta_threshold_pct / 100.0
    swap_units = swap.ct_val * swap.ct_mult
    desired_contracts = -delta / swap_units if swap_units > 0 else 0.0
    hedge_contracts = _round_nearest(desired_contracts, swap.lot_size)
    if abs(hedge_contracts) < swap.min_size / 2.0:
        hedge_contracts = 0.0
    hedge_units = hedge_contracts * swap_units
    residual = delta + hedge_units
    hedge_notional = abs(hedge_units) * pair.spot_px
    hedge_margin = hedge_notional / max(hedge_leverage, 1e-12)
    option_spread = (
        max(0.0, call.ask_px - call.bid_px) * call.ct_val * call.ct_mult
        + max(0.0, put.ask_px - put.bid_px) * put.ct_val * put.ct_mult
    ) * contracts
    hedge_spread = abs(hedge_units) * max(0.0, swap.ask_px - swap.bid_px)
    total_spread = option_spread + hedge_spread
    shock = pair.spot_px * jump_shock_pct / 100.0
    gamma = (call.gamma * call.ct_val * call.ct_mult + put.gamma * put.ct_val * put.ct_mult) * contracts
    pnl_up = residual * shock + 0.5 * gamma * shock * shock + theta
    pnl_down = -residual * shock + 0.5 * gamma * shock * shock + theta
    no_move = theta
    max_loss = max(0.0, -pnl_up, -pnl_down, -no_move) + total_spread
    return PlanMetrics(
        contracts=contracts,
        option_units=units,
        option_notional_usd=option_notional,
        premium_usdt=premium,
        premium_pct_equity=premium / equity * 100.0,
        theta_per_day_usdt=theta,
        theta_pct_equity=abs(theta) / equity * 100.0,
        net_option_delta_units=delta,
        delta_threshold_units=threshold,
        initial_delta_breach=abs(delta) > threshold,
        hedge_contracts=abs(hedge_contracts),
        hedge_side="buy" if hedge_contracts > 0 else "sell" if hedge_contracts < 0 else "none",
        hedge_units=hedge_units,
        residual_delta_units=residual,
        hedge_notional_usd=hedge_notional,
        hedge_margin_usdt=hedge_margin,
        option_round_trip_spread_usdt=option_spread,
        hedge_round_trip_spread_usdt=hedge_spread,
        total_round_trip_spread_usdt=total_spread,
        spread_pct_entry_premium=total_spread / premium * 100.0 if premium > 0 else 0.0,
        gamma_pnl_at_jump_usdt=0.5 * gamma * shock * shock,
        estimated_max_jump_loss_usdt=max_loss,
        estimated_max_jump_loss_pct=max_loss / equity * 100.0,
        estimated_no_move_day_pnl_usdt=no_move - total_spread,
    )


def size_plan(pair: StraddlePair, *, equity: float, premium_budget_pct: float, max_theta_day_pct: float, max_hedge_margin_pct: float, max_jump_loss_pct: float, jump_shock_pct: float, delta_threshold_pct: float, hedge_leverage: float, max_contracts: int) -> PlanMetrics:
    if equity <= 0 or min(premium_budget_pct, max_theta_day_pct, max_hedge_margin_pct, max_jump_loss_pct) <= 0:
        raise ValueError("equity and risk budgets must be positive")
    best: PlanMetrics | None = None
    for contracts in range(1, max_contracts + 1):
        metrics = _metrics(pair, contracts, equity=equity, delta_threshold_pct=delta_threshold_pct, jump_shock_pct=jump_shock_pct, hedge_leverage=hedge_leverage)
        if metrics.premium_pct_equity > premium_budget_pct:
            break
        if metrics.theta_pct_equity > max_theta_day_pct:
            continue
        if metrics.hedge_margin_usdt / equity * 100.0 > max_hedge_margin_pct:
            continue
        if metrics.estimated_max_jump_loss_pct > max_jump_loss_pct:
            continue
        best = metrics
    if best is None:
        raise ValueError("risk budgets permit no option contract")
    return best


def shock_scenarios(pair: StraddlePair, metrics: PlanMetrics, *, jump_shock_pct: float, delta_threshold_pct: float) -> list[dict[str, Any]]:
    call, put, swap = pair.call, pair.put, pair.swap
    gamma = (call.gamma + put.gamma) * call.ct_val * call.ct_mult * metrics.contracts
    rows = []
    for shock_pct in (-jump_shock_pct, -jump_shock_pct / 2.0, 0.0, jump_shock_pct / 2.0, jump_shock_pct):
        dpx = pair.spot_px * shock_pct / 100.0
        option_delta = metrics.net_option_delta_units + gamma * dpx
        threshold = metrics.option_units * delta_threshold_pct / 100.0
        trigger = abs(option_delta + metrics.hedge_units) > threshold
        desired = _round_nearest(-option_delta / (swap.ct_val * swap.ct_mult), swap.lot_size)
        extra = desired - (metrics.hedge_units / (swap.ct_val * swap.ct_mult))
        rows.append({
            "shock_pct": shock_pct,
            "option_delta_units": option_delta,
            "net_delta_before_rehedge_units": option_delta + metrics.hedge_units,
            "threshold_units": threshold,
            "trigger": trigger,
            "target_hedge_contracts": desired,
            "additional_hedge_contracts": extra,
        })
    return rows


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.hedge_leverage <= 0 or args.max_hedges_per_day <= 0:
        raise ValueError("hedge leverage and max hedges per day must be positive")
    client = OkxRestClient()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    plans = []
    for base in args.bases:
        pair = fetch_straddle_pair(client, base, now_ms=now_ms, min_hours=args.min_hours_to_expiry)
        metrics = size_plan(pair, equity=args.equity, premium_budget_pct=args.premium_budget_pct, max_theta_day_pct=args.max_theta_day_pct, max_hedge_margin_pct=args.max_hedge_margin_pct, max_jump_loss_pct=args.max_jump_loss_pct, jump_shock_pct=args.jump_shock_pct, delta_threshold_pct=args.delta_threshold_pct, hedge_leverage=args.hedge_leverage, max_contracts=args.max_contracts)
        plans.append({
            "pair": asdict(pair),
            "metrics": asdict(metrics),
            "shockScenarios": shock_scenarios(pair, metrics, jump_shock_pct=args.jump_shock_pct, delta_threshold_pct=args.delta_threshold_pct),
        })
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "read_only_public_quote_paper_plan",
        "execution": "no account reads, no order placement",
        "assumptions": {
            "optionQuoteToUsdt": "USD option quote treated as 1:1 USDT",
            "greeks": "OKX public Black-Scholes Greeks; theta interpreted per day per underlying unit",
            "hedge": "linear USDT swap, rounded to public lot size, hedge margin estimated at configured leverage",
            "pnl": "one-day theta plus second-order gamma approximation; no historical option repricing",
        },
        "config": {key: getattr(args, key) for key in ("equity", "min_hours_to_expiry", "premium_budget_pct", "max_theta_day_pct", "max_hedge_margin_pct", "max_jump_loss_pct", "jump_shock_pct", "delta_threshold_pct", "hedge_interval_hours", "max_hedges_per_day", "hedge_leverage")},
        "plans": plans,
    }


def markdown_report(payload: dict[str, Any]) -> str:
    cfg = payload["config"]
    lines = [
        "# BTC/ETH 长 Gamma Delta 中性纸面试验",
        "",
        "> 只读 OKX 公共行情；没有读取账户、启动服务或发送订单。",
        "",
        "本次组合买入同到期、接近平值的 Call + Put，并用对应 USDT 永续把组合 Delta 拉回附近零点。入场和再平衡均为纸面动作。",
        "",
        "## 风险规则",
        "",
        f"- 纸面权益：{cfg['equity']:,.2f} USDT；保费上限 {cfg['premium_budget_pct']:.2f}%；Theta/日上限 {cfg['max_theta_day_pct']:.2f}%。",
        f"- 永续对冲保证金上限 {cfg['max_hedge_margin_pct']:.2f}%；{cfg['jump_shock_pct']:.2f}% 单次价格冲击估计损失上限 {cfg['max_jump_loss_pct']:.2f}%。",
        f"- Delta 偏离单腿目标名义的 {cfg['delta_threshold_pct']:.2f}% 触发对冲，或每 {cfg['hedge_interval_hours']:.1f} 小时检查；每日最多 {cfg['max_hedges_per_day']} 次。",
        "- 到期前应提前平仓；本报告没有持有到结算，也没有模拟结算价风险。",
        "",
        "## 当前纸面入场",
        "",
        "| 标的 | 到期 | 平值行权价 | 合约数 | 买入保费 | 往返价差 | Theta/日 | 初始 Delta | 永续对冲 | 保证金估计 | 1% Gamma PnL | 最大估计损失 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["plans"]:
        pair, metrics = item["pair"], item["metrics"]
        expiry = _iso_ms(int(pair["call"]["expiry_ms"]))
        hedge = f"{metrics['hedge_side']} {metrics['hedge_contracts']:g} {pair['swap']['inst_id']}" if metrics["hedge_side"] != "none" else "none"
        lines.append(
            f"| {pair['underlying']} | {expiry} | {pair['call']['strike']:g} | {metrics['contracts']} | "
            f"{metrics['premium_usdt']:.2f} ({metrics['premium_pct_equity']:.2f}%) | "
            f"{metrics['total_round_trip_spread_usdt']:.2f} ({metrics['spread_pct_entry_premium']:.1f}%) | "
            f"{metrics['theta_per_day_usdt']:.2f} ({metrics['theta_pct_equity']:.2f}%) | "
            f"{metrics['net_option_delta_units']:.6f} -> {metrics['residual_delta_units']:.6f} | {hedge} | "
            f"{metrics['hedge_margin_usdt']:.2f} | {metrics['gamma_pnl_at_jump_usdt']:.2f} | "
            f"{metrics['estimated_max_jump_loss_usdt']:.2f} ({metrics['estimated_max_jump_loss_pct']:.2f}%) |"
        )
    lines.extend(["", "## Delta 触发情景", "", "以下只用当前 Gamma 做二阶近似，不代表真实期权历史回测。", "", "| 标的 | 价格冲击 | 对冲前净 Delta | 阈值 | 是否触发 | 目标永续仓位 |", "| --- | ---: | ---: | ---: | --- | ---: |"])
    for item in payload["plans"]:
        base = item["pair"]["underlying"]
        for row in item["shockScenarios"]:
            lines.append(f"| {base} | {row['shock_pct']:+.2f}% | {row['net_delta_before_rehedge_units']:.6f} | {row['threshold_units']:.6f} | {'是' if row['trigger'] else '否'} | {row['target_hedge_contracts']:+.2f} |")
    lines.extend(["", "## 限制", "", "- OKX 当前公共快照没有提供足够长的逐期权历史 bid/ask 和 IV 序列，因此这里是可执行性/风险预算试验，不是收益回测。", "- 期权报价以 USD 展示，纸面成本按 1:1 USDT 估算；实际下单前必须核对账户结算币种、合约乘数和手续费。", "- Gamma 跳空损益未包含盘口冲击、IV 跳变、基差、资金费率、保证金规则和提前平仓滑点。", ""])
    return "\n".join(lines)


def resolve_output_dir(value: str) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else OUTPUT_ROOT / path
    return OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> int:
    args = parse_args()
    payload = build_payload(args)
    output_dir = resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"output_dir={output_dir}")
    for item in payload["plans"]:
        pair, metrics = item["pair"], item["metrics"]
        print(f"{pair['underlying']} expiry={_iso_ms(int(pair['call']['expiry_ms']))} strike={pair['call']['strike']:g} contracts={metrics['contracts']} premium={metrics['premium_usdt']:.2f} theta_day={metrics['theta_per_day_usdt']:.2f} hedge={metrics['hedge_side']}:{metrics['hedge_contracts']:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
