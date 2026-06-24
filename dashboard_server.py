from __future__ import annotations

import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from okx_client import OkxApiError, OkxRestClient, load_env


APP_DIR = Path(__file__).parent / "web"
TRADE_LOG = Path(__file__).parent / "data" / "okx" / "trade_actions.jsonl"
BOT_ACTION_LOG = Path(__file__).parent / "data" / "okx" / "grid_bot_actions.jsonl"
BOT_STDOUT_LOG = Path(__file__).parent / "data" / "okx" / "grid_bot_stdout.log"
BOT_RUNTIME_CONFIG = Path(__file__).parent / "data" / "okx" / "grid_bot_runtime_config.json"
BOT_PID_FILE = Path(__file__).parent / "data" / "okx" / "grid_bot.pid"
RE_BOT_INST_ID = "RE-USDT-SWAP"
RE_BOT_PREFIX = "gr"
RE_BOT_ACTION_LOG = Path(__file__).parent / "data" / "okx" / "re_grid_bot_actions.jsonl"
RE_BOT_STDOUT_LOG = Path(__file__).parent / "data" / "okx" / "re_grid_bot_stdout.log"
RE_BOT_RUNTIME_CONFIG = Path(__file__).parent / "data" / "okx" / "re_grid_bot_runtime_config.json"
RE_BOT_PID_FILE = Path(__file__).parent / "data" / "okx" / "re_grid_bot.pid"
HOST = "127.0.0.1"
PORT = 8765
BOT_PROCESS: subprocess.Popen | None = None
BOT_STARTED_AT: str | None = None
BOT_COMMAND: list[str] | None = None
RE_BOT_PROCESS: subprocess.Popen | None = None
RE_BOT_STARTED_AT: str | None = None
RE_BOT_COMMAND: list[str] | None = None

RE_BOT_DEFAULTS: dict[str, Any] = {
    "instId": RE_BOT_INST_ID,
    "lower": "0.78",
    "upper": "0.88",
    "leverage": "5",
    "gridBps": "25",
    "minNetBps": "5",
    "softBps": "35",
    "hardBps": "60",
    "mode": "adaptive",
    "adaptiveWidthBps": "420",
    "adaptiveMinWidthBps": "260",
    "adaptiveMaxWidthBps": "700",
    "adaptiveVolMultiplier": "12",
    "rangeDriftMode": "cooldown",
    "rangeDriftWeightBps": "2500",
    "rangeDriftMaxBps": "250",
    "sizingMode": "margin_pct",
    "orderMarginPct": "10",
    "maxMarginPct": "30",
    "orderSz": "1",
    "maxPosition": "1",
    "maxOpenOrdersPerSide": "1",
    "maxActionsPerCycle": "3",
    "interval": "8",
    "ordType": "post_only",
    "totalProfitTp": "0",
    "totalProfitTpPct": "5",
    "totalProfitTpCap": "0.5",
    "totalProfitAction": "checkpoint",
    "minTpProfit": "0",
    "minTpBps": "180",
    "totalLossSl": "0",
    "totalLossSlPct": "3",
    "totalLossSlCap": "0.5",
    "positionLossSlBps": "550",
    "missedTpOrdType": "limit",
    "missedTpSlippageBps": "20",
    "hardStopOrdType": "market",
    "hardStopSlippageBps": "50",
    "riskCooldown": "60",
    "recenterOnCooldown": True,
    "trendFilter": "auto",
    "trendLookback": "8",
    "trendThresholdBps": "70",
    "regimeFilter": "ma_cross",
    "regimeBar": "15m",
    "regimeShortMa": "5",
    "regimeLongMa": "20",
    "regimeDiffBps": "50",
    "regimeConfirmBars": "3",
    "oneWayOpen": True,
    "cancelOnStop": True,
}

BOT_RUNTIME_KEYS = {
    "lower",
    "upper",
    "leverage",
    "gridBps",
    "minNetBps",
    "softBps",
    "hardBps",
    "orderSz",
    "maxPosition",
    "maxOpenOrdersPerSide",
    "maxActionsPerCycle",
    "interval",
    "ordType",
    "mode",
    "adaptiveWidthBps",
    "adaptiveMinWidthBps",
    "adaptiveMaxWidthBps",
    "adaptiveVolMultiplier",
    "rangeDriftMode",
    "rangeDriftWeightBps",
    "rangeDriftMaxBps",
    "sizingMode",
    "orderMarginPct",
    "maxMarginPct",
    "totalProfitTp",
    "totalProfitTpPct",
    "totalProfitTpCap",
    "totalProfitAction",
    "minTpProfit",
    "totalLossSl",
    "totalLossSlPct",
    "totalLossSlCap",
    "positionLossSlBps",
    "minTpBps",
    "missedTpOrdType",
    "missedTpSlippageBps",
    "hardStopOrdType",
    "hardStopSlippageBps",
    "riskCooldown",
    "cancelOnStop",
    "recenterOnCooldown",
    "trendFilter",
    "trendLookback",
    "trendThresholdBps",
    "regimeFilter",
    "regimeBar",
    "regimeShortMa",
    "regimeLongMa",
    "regimeDiffBps",
    "regimeConfirmBars",
    "oneWayOpen",
}


@dataclass(slots=True)
class StrategyParams:
    inst_id: str = "BEAT-USDT-SWAP"
    lower: Decimal = Decimal("1.74")
    upper: Decimal = Decimal("1.82")
    leverage: Decimal = Decimal("3")
    target_grid_bps: Decimal = Decimal("25")
    min_net_bps: Decimal = Decimal("5")
    soft_stop_bps: Decimal = Decimal("35")
    hard_stop_bps: Decimal = Decimal("60")
    mode: str = "adaptive"
    adaptive_width_bps: Decimal = Decimal("420")
    adaptive_min_width_bps: Decimal = Decimal("260")
    adaptive_max_width_bps: Decimal = Decimal("700")
    adaptive_vol_multiplier: Decimal = Decimal("12")
    range_drift_mode: str = "cooldown"
    range_drift_weight_bps: Decimal = Decimal("2500")
    range_drift_max_bps: Decimal = Decimal("250")
    sizing_mode: str = "fixed"
    order_sz: Decimal = Decimal("0.1")
    max_position: Decimal = Decimal("0.3")
    order_margin_pct: Decimal = Decimal("35")
    max_margin_pct: Decimal = Decimal("70")
    total_profit_tp: Decimal = Decimal("0")
    total_profit_tp_pct: Decimal = Decimal("5")
    total_profit_tp_cap: Decimal = Decimal("0.5")
    min_tp_profit: Decimal = Decimal("0")
    total_loss_sl: Decimal = Decimal("0")
    total_loss_sl_pct: Decimal = Decimal("3")
    total_loss_sl_cap: Decimal = Decimal("0.5")
    position_loss_sl_bps: Decimal = Decimal("550")
    min_tp_bps: Decimal = Decimal("200")
    trend_filter: str = "auto"
    trend_lookback: int = 8
    trend_threshold_bps: Decimal = Decimal("70")
    regime_filter: str = "ma_cross"
    regime_bar: str = "15m"
    regime_short_ma: int = 5
    regime_long_ma: int = 20
    regime_diff_bps: Decimal = Decimal("50")
    regime_confirm_bars: int = 3
    one_way_open: bool = True


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "OKXQuantDashboard/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/snapshot":
            self.handle_snapshot(parsed.query)
            return
        if parsed.path == "/api/bot/status":
            self.handle_bot_status()
            return
        if parsed.path == "/api/bot/config":
            self.handle_bot_config_get()
            return
        if parsed.path == "/api/re-bot/status":
            self.handle_re_bot_status()
            return
        if parsed.path == "/api/re-bot/config":
            self.handle_re_bot_config_get()
            return
        self.handle_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/trade/preview":
            self.handle_trade(preview_only=True)
            return
        if parsed.path == "/api/trade/order":
            self.handle_trade(preview_only=False)
            return
        if parsed.path == "/api/trade/cancel":
            self.handle_cancel()
            return
        if parsed.path == "/api/trade/set-leverage":
            self.handle_set_leverage()
            return
        if parsed.path == "/api/bot/start":
            self.handle_bot_start()
            return
        if parsed.path == "/api/bot/stop":
            self.handle_bot_stop()
            return
        if parsed.path == "/api/bot/config":
            self.handle_bot_config_update()
            return
        if parsed.path == "/api/re-bot/start":
            self.handle_re_bot_start()
            return
        if parsed.path == "/api/re-bot/dry-run-once":
            self.handle_re_bot_dry_run_once()
            return
        if parsed.path == "/api/re-bot/stop":
            self.handle_re_bot_stop()
            return
        if parsed.path == "/api/re-bot/config":
            self.handle_re_bot_config_update()
            return
        self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def handle_snapshot(self, query: str) -> None:
        params = parse_params(query)
        try:
            snapshot = build_snapshot(params)
        except OkxApiError as exc:
            self.send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "okxCode": exc.okx_code,
                    "okxMsg": exc.okx_msg,
                    "response": exc.response,
                },
                status=502,
            )
            return
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=500)
            return
        self.send_json({"ok": True, "data": snapshot})

    def handle_trade(self, *, preview_only: bool) -> None:
        try:
            payload = self.read_json()
            plan = build_order_plan(payload)
            if preview_only or payload.get("dryRun", True):
                self.send_json({"ok": True, "dryRun": True, "plan": plan})
                return

            require_live_enabled()
            require_confirmation(payload, plan)
            load_env()
            client = OkxRestClient.from_env()
            response = client.place_order(**plan["okxOrder"])
            log_trade_action("place_order", plan, response)
            self.send_json({"ok": True, "dryRun": False, "plan": plan, "response": response})
        except OkxApiError as exc:
            self.send_json({"ok": False, "error": str(exc), "okxCode": exc.okx_code, "response": exc.response}, status=502)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_cancel(self) -> None:
        try:
            payload = self.read_json()
            if payload.get("dryRun", True):
                self.send_json({"ok": True, "dryRun": True, "plan": payload})
                return
            require_live_enabled()
            load_env()
            client = OkxRestClient.from_env()
            response = client.cancel_order(
                inst_id=str(payload["instId"]),
                ord_id=payload.get("ordId") or None,
                cl_ord_id=payload.get("clOrdId") or None,
            )
            log_trade_action("cancel_order", payload, response)
            self.send_json({"ok": True, "dryRun": False, "response": response})
        except OkxApiError as exc:
            self.send_json({"ok": False, "error": str(exc), "okxCode": exc.okx_code, "response": exc.response}, status=502)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_set_leverage(self) -> None:
        try:
            payload = self.read_json()
            plan = {
                "inst_id": str(payload["instId"]),
                "lever": str(payload["lever"]),
                "mgn_mode": str(payload.get("mgnMode", "cross")),
                "pos_side": payload.get("posSide") or None,
            }
            if payload.get("dryRun", True):
                self.send_json({"ok": True, "dryRun": True, "plan": plan})
                return
            require_live_enabled()
            load_env()
            client = OkxRestClient.from_env()
            response = client.set_leverage(**plan)
            log_trade_action("set_leverage", plan, response)
            self.send_json({"ok": True, "dryRun": False, "response": response})
        except OkxApiError as exc:
            self.send_json({"ok": False, "error": str(exc), "okxCode": exc.okx_code, "response": exc.response}, status=502)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_bot_status(self) -> None:
        self.send_json({"ok": True, "data": bot_status()})

    def handle_bot_config_get(self) -> None:
        self.send_json({"ok": True, "data": read_bot_runtime_config()})

    def handle_bot_start(self) -> None:
        try:
            payload = self.read_json()
            status = start_bot(payload)
            self.send_json({"ok": True, "data": status})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_bot_stop(self) -> None:
        try:
            status = stop_bot()
            self.send_json({"ok": True, "data": status})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_bot_config_update(self) -> None:
        try:
            payload = self.read_json()
            config = write_bot_runtime_config(payload)
            self.send_json({"ok": True, "data": {"running": bot_status()["running"], "config": config}})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_re_bot_status(self) -> None:
        self.send_json({"ok": True, "data": re_bot_status()})

    def handle_re_bot_config_get(self) -> None:
        self.send_json({"ok": True, "data": read_re_bot_runtime_config()})

    def handle_re_bot_start(self) -> None:
        try:
            payload = self.read_json()
            status = start_re_bot(payload, once=False)
            self.send_json({"ok": True, "data": status})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_re_bot_dry_run_once(self) -> None:
        try:
            payload = self.read_json()
            payload["live"] = False
            payload["setLeverage"] = False
            status = start_re_bot(payload, once=True)
            self.send_json({"ok": True, "data": status})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_re_bot_stop(self) -> None:
        try:
            status = stop_re_bot()
            self.send_json({"ok": True, "data": status})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_re_bot_config_update(self) -> None:
        try:
            payload = self.read_json()
            config = write_re_bot_runtime_config(payload)
            self.send_json({"ok": True, "data": {"running": re_bot_status()["running"], "config": config}})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_static(self, request_path: str) -> None:
        if request_path in ("", "/"):
            file_path = APP_DIR / "index.html"
        else:
            file_path = (APP_DIR / request_path.lstrip("/")).resolve()
            if APP_DIR.resolve() not in file_path.parents and file_path != APP_DIR.resolve():
                self.send_error(403)
                return

        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0:
            return {}
        return json.loads(self.rfile.read(size).decode("utf-8"))


def build_snapshot(params: StrategyParams) -> dict[str, Any]:
    load_env()
    client = OkxRestClient.from_env()
    try:
        client.timeout = float(os.getenv("OKX_DASHBOARD_TIMEOUT", "4"))
    except ValueError:
        client.timeout = 4.0

    meta = one(client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP", "instId": params.inst_id}))
    ticker = one(client.request("GET", "/api/v5/market/ticker", params={"instId": params.inst_id}))
    mark = one(client.request("GET", "/api/v5/public/mark-price", params={"instType": "SWAP", "instId": params.inst_id}))
    funding = one(client.request("GET", "/api/v5/public/funding-rate", params={"instId": params.inst_id}))
    price_limit = one(client.request("GET", "/api/v5/public/price-limit", params={"instId": params.inst_id}))
    open_interest = one(client.request("GET", "/api/v5/public/open-interest", params={"instType": "SWAP", "instId": params.inst_id}))
    books = one(client.request("GET", "/api/v5/market/books", params={"instId": params.inst_id, "sz": "50"}))
    trades = client.request("GET", "/api/v5/market/trades", params={"instId": params.inst_id, "limit": "50"}).get("data", [])
    candles = client.request("GET", "/api/v5/market/candles", params={"instId": params.inst_id, "bar": "1m", "limit": "180"}).get("data", [])
    regime_candles = []
    if params.regime_filter == "ma_cross":
        regime_candles = client.request(
            "GET",
            "/api/v5/market/candles",
            params={
                "instId": params.inst_id,
                "bar": params.regime_bar,
                "limit": str(max(80, params.regime_long_ma + params.regime_confirm_bars + 10)),
            },
        ).get("data", [])

    fee = one(
        client.request(
            "GET",
            "/api/v5/account/trade-fee",
            params={"instType": "SWAP", "instFamily": family_from_inst_id(params.inst_id)},
            private=True,
        )
    )
    account = one(client.get_account_config())
    balance = one(client.get_balance())
    positions = client.get_positions("SWAP").get("data", [])
    beat_positions = [item for item in positions if item.get("instId") == params.inst_id]
    pending_orders = client.get_pending_orders(params.inst_id).get("data", [])
    fills = client.get_fills(inst_id=params.inst_id, inst_type="SWAP", limit="100").get("data", [])
    pnl = compute_pnl(beat_positions, fills)

    strategy = compute_strategy(
        params,
        meta,
        ticker,
        mark,
        fee,
        candles,
        regime_candles,
        books,
        balance,
        beat_positions,
        pending_orders,
        bot_prefix_for_inst_id(params.inst_id),
    )

    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": serialize_params(params),
        "account": sanitize_account(account),
        "balance": sanitize_balance(balance),
        "positions": beat_positions,
        "pendingOrders": pending_orders,
        "fills": fills[:50],
        "pnl": pnl,
        "trading": {
            "liveEnabled": is_live_enabled(),
            "defaultDryRun": True,
            "tradeLog": str(TRADE_LOG),
        },
        "market": {
            "meta": meta,
            "ticker": ticker,
            "mark": mark,
            "funding": funding,
            "priceLimit": price_limit,
            "openInterest": open_interest,
            "fee": fee,
            "books": books,
            "trades": trades,
            "candles": normalize_candles(candles),
            "regimeCandles": normalize_candles(regime_candles),
        },
        "strategy": strategy,
    }


def compute_strategy(
    params: StrategyParams,
    meta: dict[str, Any],
    ticker: dict[str, Any],
    mark: dict[str, Any],
    fee: dict[str, Any],
    candles: list[list[str]],
    regime_candles: list[list[str]],
    books: dict[str, Any],
    balance: dict[str, Any],
    positions: list[dict[str, Any]],
    pending_orders: list[dict[str, Any]],
    bot_prefix: str = "gb",
) -> dict[str, Any]:
    tick = dec(meta.get("tickSz"), Decimal("0.0001"))
    last = dec(ticker.get("last"), Decimal("0"))
    mark_px = dec(mark.get("markPx"), last)
    one_min_stats = candle_stats(candles)
    effective_lower, effective_upper, range_note, adaptive_width_bps = compute_effective_range(
        params,
        mark_px,
        tick,
        one_min_stats,
    )
    midpoint = (effective_lower + effective_upper) / Decimal("2")
    target_step = midpoint * params.target_grid_bps / Decimal("10000")
    grid_count = max(1, int(((effective_upper - effective_lower) / target_step).to_integral_value(rounding=ROUND_HALF_UP)))
    step = round_to_tick((effective_upper - effective_lower) / Decimal(grid_count), tick)

    soft_lower = round_to_tick(effective_lower * (Decimal("1") - params.soft_stop_bps / Decimal("10000")), tick)
    soft_upper = round_to_tick(effective_upper * (Decimal("1") + params.soft_stop_bps / Decimal("10000")), tick)
    hard_lower = round_to_tick(effective_lower * (Decimal("1") - params.hard_stop_bps / Decimal("10000")), tick)
    hard_upper = round_to_tick(effective_upper * (Decimal("1") + params.hard_stop_bps / Decimal("10000")), tick)

    maker_bps = abs(dec(fee.get("makerU") or fee.get("maker"), Decimal("0"))) * Decimal("10000")
    taker_bps = abs(dec(fee.get("takerU") or fee.get("taker"), Decimal("0"))) * Decimal("10000")
    gross_grid_bps = step / midpoint * Decimal("10000") if midpoint else Decimal("0")
    net_maker_bps = gross_grid_bps - maker_bps * Decimal("2")
    net_taker_bps = gross_grid_bps - taker_bps * Decimal("2")
    conservative_net_bps = gross_grid_bps - maker_bps - taker_bps
    min_net_ok = conservative_net_bps >= params.min_net_bps

    grid_lines = []
    price = effective_lower
    index = 0
    while price <= effective_upper + tick / Decimal("2"):
        direction = "long" if price < midpoint else "short"
        take_profit = round_to_tick(price + step, tick) if direction == "long" else round_to_tick(price - step, tick)
        grid_lines.append(
            {
                "index": index,
                "price": str(round_to_tick(price, tick)),
                "direction": direction,
                "takeProfit": str(take_profit),
            }
        )
        price += step
        index += 1

    book_stats = depth_stats(books, meta, ticker)
    state = strategy_state(mark_px, effective_lower, effective_upper, soft_lower, soft_upper, hard_lower, hard_upper)
    sizing = sizing_preview(params, meta, mark_px, balance, pending_orders, bot_prefix)
    risk = risk_targets(params, balance)
    min_tp_profit_bps_value = min_tp_profit_bps(params, meta, sizing)
    effective_min_tp_bps = max(params.min_tp_bps, min_tp_profit_bps_value)
    regime = regime_preview(params, regime_candles)
    trend = trend_preview(params, candles, mark_px, midpoint, tick, positions, regime)

    return {
        "mode": params.mode,
        "outerLower": str(params.lower),
        "outerUpper": str(params.upper),
        "effectiveLower": str(effective_lower),
        "effectiveUpper": str(effective_upper),
        "rangeNote": range_note,
        "adaptiveWidthBps": float(adaptive_width_bps),
        "rangeDriftMode": params.range_drift_mode,
        "rangeDriftWeightBps": float(params.range_drift_weight_bps),
        "rangeDriftMaxBps": float(params.range_drift_max_bps),
        "rangeDriftPreview": drift_preview(params, mark_px, tick),
        "gridCount": grid_count,
        "step": str(step),
        "grossGridBps": float(gross_grid_bps),
        "netMakerBps": float(net_maker_bps),
        "netTakerBps": float(net_taker_bps),
        "conservativeNetBps": float(conservative_net_bps),
        "minNetBps": float(params.min_net_bps),
        "minNetOk": min_net_ok,
        "makerRoundTripBps": float(maker_bps * Decimal("2")),
        "takerRoundTripBps": float(taker_bps * Decimal("2")),
        "softLower": str(soft_lower),
        "softUpper": str(soft_upper),
        "hardLower": str(hard_lower),
        "hardUpper": str(hard_upper),
        "midpoint": str(midpoint),
        "state": state,
        "trend": trend,
        "regime": regime,
        "risk": risk,
        "minTpProfit": str(params.min_tp_profit),
        "minTpBps": float(effective_min_tp_bps),
        "minTpProfitBps": float(min_tp_profit_bps_value),
        "gridLines": grid_lines,
        "oneMinute": one_min_stats,
        "book": book_stats,
        "sizing": sizing,
        "minOrderNotional": str(dec(meta.get("minSz"), Decimal("0")) * dec(meta.get("ctVal"), Decimal("0")) * last),
        "minOrderMargin": str((dec(meta.get("minSz"), Decimal("0")) * dec(meta.get("ctVal"), Decimal("0")) * last) / params.leverage),
    }


def compute_effective_range(
    params: StrategyParams,
    mark_px: Decimal,
    tick: Decimal,
    one_min_stats: dict[str, Any],
) -> tuple[Decimal, Decimal, str, Decimal]:
    if params.mode != "adaptive" or mark_px <= 0:
        return params.lower, params.upper, "fixed", Decimal("0")

    avg_abs_bps = dec(one_min_stats.get("avgAbsMoveBps"), Decimal("0"))
    vol_width_bps = avg_abs_bps * params.adaptive_vol_multiplier
    width_bps = max(params.adaptive_width_bps, vol_width_bps, params.adaptive_min_width_bps)
    width_bps = min(width_bps, params.adaptive_max_width_bps)
    half = width_bps / Decimal("20000")
    raw_lower = round_to_tick(mark_px * (Decimal("1") - half), tick)
    raw_upper = round_to_tick(mark_px * (Decimal("1") + half), tick)
    lower = max(params.lower, raw_lower)
    upper = min(params.upper, raw_upper)

    if upper <= lower:
        return params.lower, params.upper, "adaptive clipped to fixed", width_bps
    return lower, upper, f"adaptive width {plain(width_bps)} bps", width_bps


def drift_preview(params: StrategyParams, mark_px: Decimal, tick: Decimal) -> dict[str, Any]:
    if params.range_drift_mode == "off" or params.range_drift_weight_bps <= 0 or mark_px <= 0:
        return {"mode": params.range_drift_mode, "enabled": False}
    width = params.upper - params.lower
    if width <= 0:
        return {"mode": params.range_drift_mode, "enabled": False}
    midpoint = (params.lower + params.upper) / Decimal("2")
    shift = (mark_px - midpoint) * min(max(params.range_drift_weight_bps, Decimal("0")), Decimal("10000")) / Decimal("10000")
    max_shift = midpoint * max(params.range_drift_max_bps, Decimal("0")) / Decimal("10000")
    if max_shift > 0:
        shift = max(-max_shift, min(shift, max_shift))
    new_lower = round_to_tick(params.lower + shift, tick)
    new_upper = round_to_tick(new_lower + width, tick)
    return {
        "mode": params.range_drift_mode,
        "enabled": True,
        "weightBps": str(params.range_drift_weight_bps),
        "maxBps": str(params.range_drift_max_bps),
        "shift": str(shift),
        "nextLower": str(new_lower),
        "nextUpper": str(new_upper),
    }


def sizing_preview(
    params: StrategyParams,
    meta: dict[str, Any],
    mark_px: Decimal,
    balance: dict[str, Any],
    pending_orders: list[dict[str, Any]] | None = None,
    bot_prefix: str = "gb",
) -> dict[str, Any]:
    lot = dec(meta.get("lotSz"), Decimal("0.1"))
    min_sz = dec(meta.get("minSz"), Decimal("0.1"))
    ct_val = dec(meta.get("ctVal"), Decimal("0"))
    if params.sizing_mode != "margin_pct":
        order_sz = round_size(max(params.order_sz, min_sz), lot)
        max_position = round_size(max(params.max_position, min_sz), lot) if params.max_position > 0 else Decimal("0")
        return {
            "mode": "fixed",
            "orderSz": str(order_sz),
            "maxPosition": str(max_position),
            "orderMargin": "",
            "maxMargin": "",
            "basisMargin": "",
            "available": "",
            "reservedOpenMargin": "",
            "effectiveAvailable": "",
            "markPx": str(mark_px),
        }

    equity, available = balance_summary(balance)
    reserved_open_margin = pending_open_margin(
        pending_orders or [],
        ct_val=ct_val,
        leverage=params.leverage,
        bot_prefix=bot_prefix,
    )
    effective_available = available + reserved_open_margin
    basis_margin = min_positive(equity, effective_available)
    if mark_px <= 0 or ct_val <= 0 or params.leverage <= 0 or basis_margin <= 0:
        return {
            "mode": "margin_pct",
            "orderSz": "0",
            "maxPosition": "0",
            "orderMargin": "0",
            "maxMargin": "0",
            "basisMargin": str(basis_margin),
            "available": str(available),
            "reservedOpenMargin": str(reserved_open_margin),
            "effectiveAvailable": str(effective_available),
            "markPx": str(mark_px),
        }

    order_margin = basis_margin * clamp_pct(params.order_margin_pct) / Decimal("100")
    order_sz = round_size(order_margin * params.leverage / (mark_px * ct_val), lot)
    if order_sz < min_sz:
        order_sz = min_sz

    max_margin = equity * clamp_pct(params.max_margin_pct) / Decimal("100")
    max_position = round_size(max_margin * params.leverage / (mark_px * ct_val), lot)
    min_margin = min_sz * ct_val * mark_px / params.leverage
    if max_position < min_sz:
        max_position = min_sz if max_margin >= min_margin else Decimal("0")
    if params.max_position > 0:
        max_position = min(params.max_position, max_position)

    return {
        "mode": "margin_pct",
        "orderSz": str(order_sz),
        "maxPosition": str(max_position),
        "orderMargin": str(order_margin),
        "maxMargin": str(max_margin),
        "basisMargin": str(basis_margin),
        "available": str(available),
        "reservedOpenMargin": str(reserved_open_margin),
        "effectiveAvailable": str(effective_available),
        "markPx": str(mark_px),
    }


def risk_targets(params: StrategyParams, balance: dict[str, Any]) -> dict[str, Any]:
    equity, _available = balance_summary(balance)
    profit_target, profit_note = pnl_threshold(
        equity,
        fixed=params.total_profit_tp,
        pct=params.total_profit_tp_pct,
        cap=params.total_profit_tp_cap,
    )
    loss_target, loss_note = pnl_threshold(
        equity,
        fixed=params.total_loss_sl,
        pct=params.total_loss_sl_pct,
        cap=params.total_loss_sl_cap,
    )
    return {
        "equity": str(equity),
        "profitTarget": str(profit_target),
        "profitNote": profit_note,
        "lossTarget": str(loss_target),
        "lossNote": loss_note,
        "positionLossSlBps": str(params.position_loss_sl_bps),
        "minTpBps": str(params.min_tp_bps),
    }


def min_tp_profit_bps(params: StrategyParams, meta: dict[str, Any], sizing: dict[str, Any]) -> Decimal:
    if params.min_tp_profit <= 0:
        return Decimal("0")
    ct_val = dec(meta.get("ctVal"), Decimal("0"))
    order_sz = dec(sizing.get("orderSz"), Decimal("0"))
    mark_px = dec(sizing.get("markPx"), Decimal("0"))
    notional = order_sz * ct_val * mark_px
    if notional <= 0:
        return Decimal("0")
    return params.min_tp_profit / notional * Decimal("10000")


def trend_preview(
    params: StrategyParams,
    candles: list[list[str]],
    mark_px: Decimal,
    midpoint: Decimal,
    tick: Decimal,
    positions: list[dict[str, Any]],
    regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    closes = [dec(item[4], Decimal("0")) for item in candles if len(item) > 4 and dec(item[4], Decimal("0")) > 0]
    if not closes:
        change_bps = Decimal("0")
        direction = "flat"
        lookback = 0
    else:
        lookback = min(max(1, params.trend_lookback), len(closes) - 1)
        past = closes[lookback]
        change_bps = (mark_px / past - Decimal("1")) * Decimal("10000") if past > 0 else Decimal("0")
        if change_bps >= params.trend_threshold_bps:
            direction = "up"
        elif change_bps <= -params.trend_threshold_bps:
            direction = "down"
        else:
            direction = "flat"

    regime = regime or {"state": "off", "allowedOpenSides": []}
    if params.regime_filter == "ma_cross" and regime.get("state") in {"up", "down"}:
        zone = "ma-cross"
        sides = list(regime.get("allowedOpenSides") or [])
        reason = f"ma-cross {regime.get('state')} diff={regime.get('diffBps')}bps"
    elif mark_px < midpoint - tick / Decimal("2"):
        zone = "lower-half"
        sides = ["long"]
        reason = "lower-half buy-dip"
    elif mark_px > midpoint + tick / Decimal("2"):
        zone = "upper-half"
        sides = ["short"]
        reason = "upper-half sell-rally"
    else:
        zone = "midpoint"
        if params.trend_filter == "auto" and direction == "up":
            sides = ["long"]
            reason = "midpoint trend-follow long"
        elif params.trend_filter == "auto" and direction == "down":
            sides = ["short"]
            reason = "midpoint trend-follow short"
        elif mark_px <= midpoint:
            sides = ["long"]
            reason = "midpoint neutral passive-long"
        else:
            sides = ["short"]
            reason = "midpoint neutral passive-short"

    if params.trend_filter == "auto":
        strong_threshold = max(params.trend_threshold_bps * Decimal("2"), Decimal("80"))
        abs_change_bps = abs(change_bps)
        if direction == "up" and abs_change_bps >= strong_threshold:
            sides = [side for side in sides if side != "short"]
            if not sides:
                reason = f"strong-uptrend blocks new short"
        elif direction == "down" and abs_change_bps >= strong_threshold:
            sides = [side for side in sides if side != "long"]
            if not sides:
                reason = f"strong-downtrend blocks new long"

    pos = position_summary(positions)
    note = reason
    if params.one_way_open:
        if pos["long"] > 0 and pos["short"] > 0:
            sides = []
            note = "dual-position close-only"
        elif pos["short"] > 0 and "long" in sides:
            sides = []
            note = "short active blocks long"
        elif pos["long"] > 0 and "short" in sides:
            sides = []
            note = "long active blocks short"

    return {
        "filter": params.trend_filter,
        "direction": direction,
        "changeBps": float(change_bps),
        "lookback": lookback,
        "thresholdBps": float(params.trend_threshold_bps),
        "zone": zone,
        "regimeFilter": params.regime_filter,
        "regimeState": regime.get("state", "off"),
        "regimeRawState": regime.get("rawState", "off"),
        "regimeDiffBps": regime.get("diffBps", "0"),
        "oneWayOpen": params.one_way_open,
        "allowedOpenSides": sides if params.one_way_open or params.trend_filter != "off" else ["long", "short"],
        "note": note,
        "positionLong": str(pos["long"]),
        "positionShort": str(pos["short"]),
    }


def regime_preview(params: StrategyParams, candles: list[list[str]]) -> dict[str, Any]:
    if params.regime_filter != "ma_cross":
        return {"filter": params.regime_filter, "state": "off", "rawState": "off", "confirmed": True, "allowedOpenSides": ["long", "short"]}
    closed = sorted(
        [
            (int(item[0]), dec(item[4], Decimal("0")))
            for item in candles
            if len(item) > 8 and item[8] == "1" and dec(item[4], Decimal("0")) > 0
        ],
        key=lambda item: item[0],
    )
    need = params.regime_long_ma + max(0, params.regime_confirm_bars - 1)
    if len(closed) < need:
        return {
            "filter": params.regime_filter,
            "state": "range",
            "rawState": "insufficient",
            "confirmed": False,
            "allowedOpenSides": ["long", "short"],
            "bar": params.regime_bar,
            "shortMa": "",
            "longMa": "",
            "diffBps": "0",
            "confirmBars": params.regime_confirm_bars,
        }
    closes = [item[1] for item in closed]
    raw_states: list[str] = []
    latest_short_ma = Decimal("0")
    latest_long_ma = Decimal("0")
    latest_diff_bps = Decimal("0")
    for offset in range(params.regime_confirm_bars):
        end = len(closes) - offset
        window = closes[:end]
        short_ma = sum(window[-params.regime_short_ma :]) / Decimal(params.regime_short_ma)
        long_ma = sum(window[-params.regime_long_ma :]) / Decimal(params.regime_long_ma)
        diff_bps = (short_ma / long_ma - Decimal("1")) * Decimal("10000") if long_ma > 0 else Decimal("0")
        if offset == 0:
            latest_short_ma = short_ma
            latest_long_ma = long_ma
            latest_diff_bps = diff_bps
        if diff_bps >= params.regime_diff_bps:
            raw_states.append("up")
        elif diff_bps <= -params.regime_diff_bps:
            raw_states.append("down")
        else:
            raw_states.append("range")
    raw_state = raw_states[0]
    confirmed = all(item == raw_state for item in raw_states)
    state = raw_state if confirmed else "range"
    return {
        "filter": params.regime_filter,
        "state": state,
        "rawState": raw_state,
        "confirmed": confirmed,
        "allowedOpenSides": regime_allowed_sides(state),
        "bar": params.regime_bar,
        "shortMa": str(latest_short_ma),
        "longMa": str(latest_long_ma),
        "diffBps": str(latest_diff_bps),
        "thresholdBps": str(params.regime_diff_bps),
        "confirmBars": params.regime_confirm_bars,
        "recentRawStates": raw_states,
    }


def regime_allowed_sides(state: str) -> list[str]:
    if state == "up":
        return ["long"]
    if state == "down":
        return ["short"]
    return ["long", "short"]


def position_summary(positions: list[dict[str, Any]]) -> dict[str, Decimal]:
    result = {"long": Decimal("0"), "short": Decimal("0")}
    for item in positions:
        pos_side = item.get("posSide")
        size = abs(dec(item.get("pos"), Decimal("0")))
        if pos_side in result:
            result[pos_side] += size
    return result


def pnl_threshold(
    equity: Decimal,
    *,
    fixed: Decimal,
    pct: Decimal,
    cap: Decimal,
) -> tuple[Decimal, str]:
    fixed = max(Decimal("0"), fixed)
    pct = max(Decimal("0"), pct)
    cap = max(Decimal("0"), cap)
    pct_value = equity * pct / Decimal("100") if equity > 0 and pct > 0 else Decimal("0")
    if pct_value > 0:
        target = pct_value
        note_parts = [f"{plain(pct)}% equity={plain(pct_value)}"]
    elif fixed > 0:
        target = fixed
        note_parts = [f"fixed={plain(fixed)}"]
    else:
        return Decimal("0"), "disabled"
    if cap > 0 and target > cap:
        target = cap
        note_parts.append(f"cap={plain(cap)}")
    return target, ", ".join(note_parts)


def strategy_state(
    mark_px: Decimal,
    lower: Decimal,
    upper: Decimal,
    soft_lower: Decimal,
    soft_upper: Decimal,
    hard_lower: Decimal,
    hard_upper: Decimal,
) -> dict[str, str]:
    if mark_px <= hard_lower:
        return {"level": "danger", "label": "下破硬止损", "action": "平多并停止开多"}
    if mark_px >= hard_upper:
        return {"level": "danger", "label": "上破硬止损", "action": "平空并停止开空"}
    if mark_px <= soft_lower:
        return {"level": "warn", "label": "下破软止损", "action": "停止开多，观察回归"}
    if mark_px >= soft_upper:
        return {"level": "warn", "label": "上破软止损", "action": "停止开空，观察回归"}
    if lower <= mark_px <= upper:
        return {"level": "ok", "label": "区间内", "action": "按网格执行"}
    return {"level": "watch", "label": "区间外缓冲", "action": "暂停新增，等待确认"}


def candle_stats(candles: list[list[str]]) -> dict[str, Any]:
    closes = [Decimal(item[4]) for item in candles if len(item) > 4 and item[4]]
    returns: list[Decimal] = []
    for index in range(len(closes) - 1):
        prev = closes[index + 1]
        if prev:
            returns.append((closes[index] / prev - Decimal("1")) * Decimal("10000"))
    if not returns:
        return {"avgAbsMoveBps": 0, "maxAbsMoveBps": 0}
    avg_abs = sum(abs(item) for item in returns) / Decimal(len(returns))
    max_abs = max(abs(item) for item in returns)
    return {"avgAbsMoveBps": float(avg_abs), "maxAbsMoveBps": float(max_abs)}


def depth_stats(books: dict[str, Any], meta: dict[str, Any], ticker: dict[str, Any]) -> dict[str, Any]:
    ct_val = dec(meta.get("ctVal"), Decimal("0"))
    bid = dec(ticker.get("bidPx"), Decimal("0"))
    ask = dec(ticker.get("askPx"), Decimal("0"))
    mid = (bid + ask) / Decimal("2") if bid and ask else Decimal("0")
    spread_bps = (ask - bid) / mid * Decimal("10000") if mid else Decimal("0")
    return {
        "spreadBps": float(spread_bps),
        "bidDepth10": float(depth_notional(books.get("bids", [])[:10], ct_val)),
        "askDepth10": float(depth_notional(books.get("asks", [])[:10], ct_val)),
    }


def depth_notional(rows: list[list[str]], ct_val: Decimal) -> Decimal:
    total = Decimal("0")
    for row in rows:
        if len(row) >= 2:
            total += dec(row[0], Decimal("0")) * dec(row[1], Decimal("0")) * ct_val
    return total


def normalize_candles(candles: list[list[str]]) -> list[dict[str, Any]]:
    normalized = []
    for item in reversed(candles):
        if len(item) < 9:
            continue
        normalized.append(
            {
                "ts": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "vol": float(item[5]),
                "volCcy": float(item[6]),
                "volQuote": float(item[7]),
                "confirm": item[8],
            }
        )
    return normalized


def sanitize_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "acctLv": account.get("acctLv"),
        "posMode": account.get("posMode"),
        "level": account.get("level"),
        "perm": account.get("perm"),
    }


def sanitize_balance(balance: dict[str, Any]) -> dict[str, Any]:
    details = balance.get("details", [])
    keep = []
    for item in details:
        if item.get("ccy") in ("USDT", "USDC", "USDG") or dec(item.get("cashBal"), Decimal("0")):
            keep.append(
                {
                    "ccy": item.get("ccy"),
                    "cashBal": item.get("cashBal"),
                    "availBal": item.get("availBal"),
                    "eq": item.get("eq"),
                    "upl": item.get("upl"),
                }
            )
    return {"totalEq": balance.get("totalEq"), "details": keep}


def balance_summary(balance: dict[str, Any]) -> tuple[Decimal, Decimal]:
    equity = dec(balance.get("totalEq"), Decimal("0"))
    available = Decimal("0")
    for item in balance.get("details", []):
        if item.get("ccy") == "USDT":
            available = dec(item.get("availBal"), Decimal("0"))
            equity = equity or dec(item.get("eq"), Decimal("0"))
            break
    return equity, available


def bot_prefix_for_inst_id(inst_id: str) -> str:
    return RE_BOT_PREFIX if inst_id == RE_BOT_INST_ID else "gb"


def is_reduce_only_pending_order(order: dict[str, Any]) -> bool:
    return str(order.get("reduceOnly", "")).lower() == "true"


def pending_open_margin(
    orders: list[dict[str, Any]],
    *,
    ct_val: Decimal,
    leverage: Decimal,
    bot_prefix: str,
) -> Decimal:
    if ct_val <= 0 or leverage <= 0:
        return Decimal("0")
    total = Decimal("0")
    for order in orders:
        if not str(order.get("clOrdId", "")).startswith(bot_prefix) or is_reduce_only_pending_order(order):
            continue
        px = dec(order.get("px"), Decimal("0"))
        sz = dec(order.get("sz"), Decimal("0"))
        if px <= 0 or sz <= 0:
            continue
        total += px * sz * ct_val / leverage
    return total


def compute_pnl(positions: list[dict[str, Any]], fills: list[dict[str, Any]]) -> dict[str, Any]:
    unrealized = sum(dec(item.get("upl"), Decimal("0")) for item in positions)
    realized = sum(dec(item.get("fillPnl"), Decimal("0")) for item in fills)
    fees = sum(dec(item.get("fee"), Decimal("0")) for item in fills)
    net_realized = realized + fees
    long_upl = sum(dec(item.get("upl"), Decimal("0")) for item in positions if item.get("posSide") == "long")
    short_upl = sum(dec(item.get("upl"), Decimal("0")) for item in positions if item.get("posSide") == "short")
    buy_volume = sum(dec(item.get("fillSz"), Decimal("0")) for item in fills if item.get("side") == "buy")
    sell_volume = sum(dec(item.get("fillSz"), Decimal("0")) for item in fills if item.get("side") == "sell")
    return {
        "unrealized": str(unrealized),
        "realized": str(realized),
        "fees": str(fees),
        "netRealized": str(net_realized),
        "estimatedTotal": str(net_realized + unrealized),
        "longUpl": str(long_upl),
        "shortUpl": str(short_upl),
        "fillCount": len(fills),
        "buyVolume": str(buy_volume),
        "sellVolume": str(sell_volume),
    }


def build_order_plan(payload: dict[str, Any]) -> dict[str, Any]:
    inst_id = str(payload.get("instId", "BEAT-USDT-SWAP"))
    side = str(payload["side"]).lower()
    pos_side = str(payload["posSide"]).lower()
    px = str(payload["px"])
    sz = str(payload["sz"])
    ord_type = str(payload.get("ordType", "post_only"))
    td_mode = str(payload.get("tdMode", "cross"))
    reduce_only = bool(payload.get("reduceOnly", False))

    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if pos_side not in {"long", "short"}:
        raise ValueError("posSide must be long or short")
    if ord_type not in {"limit", "post_only"}:
        raise ValueError("ordType must be limit or post_only")
    if dec(px, Decimal("0")) <= 0:
        raise ValueError("px must be positive")
    if dec(sz, Decimal("0")) <= 0:
        raise ValueError("sz must be positive")

    cl_ord_id = payload.get("clOrdId") or make_client_order_id(pos_side, side)
    okx_order: dict[str, Any] = {
        "inst_id": inst_id,
        "td_mode": td_mode,
        "side": side,
        "pos_side": pos_side,
        "ord_type": ord_type,
        "sz": sz,
        "px": px,
        "cl_ord_id": cl_ord_id,
    }
    if payload.get("forceReduceOnly"):
        okx_order["reduce_only"] = reduce_only
    return {
        "instId": inst_id,
        "side": side,
        "posSide": pos_side,
        "px": px,
        "sz": sz,
        "ordType": ord_type,
        "tdMode": td_mode,
        "reduceOnly": reduce_only,
        "clOrdId": cl_ord_id,
        "okxOrder": okx_order,
        "notionalEstimate": str(dec(px, Decimal("0")) * dec(sz, Decimal("0")) * Decimal("10")),
    }


def require_live_enabled() -> None:
    load_env()
    if not is_live_enabled():
        raise PermissionError("Live trading is locked. Set OKX_ENABLE_LIVE_TRADING=1 in .env to enable.")


def require_confirmation(payload: dict[str, Any], plan: dict[str, Any]) -> None:
    expected = f"TRADE {plan['instId']} {plan['side'].upper()} {plan['posSide'].upper()} {plan['sz']} @ {plan['px']}"
    if payload.get("confirm") != expected:
        raise PermissionError(f"Confirmation mismatch. Expected: {expected}")


def is_live_enabled() -> bool:
    return os.getenv("OKX_ENABLE_LIVE_TRADING", "0") == "1"


def make_client_order_id(pos_side: str, side: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S%f")[:-3]
    return f"q{stamp}{pos_side[:1]}{side[:1]}"


def log_trade_action(action: str, plan: dict[str, Any], response: dict[str, Any]) -> None:
    TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "plan": plan,
        "response": response,
    }
    with TRADE_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_grid_bot_args(
    payload: dict[str, Any],
    *,
    runtime_config_path: Path,
    action_log_path: Path,
    bot_prefix: str,
    force_inst_id: str | None = None,
    once: bool = False,
    live: bool | None = None,
) -> list[str]:
    use_live = bool(payload.get("live", False)) if live is None else live
    args = [
        sys.executable,
        "-u",
        str(Path(__file__).parent / "auto_grid_bot.py"),
        "--inst-id",
        force_inst_id or str(payload.get("instId", "BEAT-USDT-SWAP")),
        "--runtime-config",
        str(runtime_config_path),
        "--log-path",
        str(action_log_path),
        "--bot-prefix",
        bot_prefix,
        "--lower",
        str(payload.get("lower", "1.74")),
        "--upper",
        str(payload.get("upper", "1.82")),
        "--leverage",
        str(payload.get("leverage", "3")),
        "--grid-bps",
        str(payload.get("gridBps", "25")),
        "--min-net-bps",
        str(payload.get("minNetBps", "5")),
        "--soft-bps",
        str(payload.get("softBps", "35")),
        "--hard-bps",
        str(payload.get("hardBps", "60")),
        "--order-sz",
        str(payload.get("orderSz", "0.1")),
        "--max-position",
        str(payload.get("maxPosition", "0.3")),
        "--max-open-orders-per-side",
        str(payload.get("maxOpenOrdersPerSide", "1")),
        "--max-actions-per-cycle",
        str(payload.get("maxActionsPerCycle", "4")),
        "--interval",
        str(payload.get("interval", "8")),
        "--ord-type",
        str(payload.get("ordType", "post_only")),
        "--mode",
        str(payload.get("mode", "adaptive")),
        "--adaptive-width-bps",
        str(payload.get("adaptiveWidthBps", "420")),
        "--adaptive-min-width-bps",
        str(payload.get("adaptiveMinWidthBps", "260")),
        "--adaptive-max-width-bps",
        str(payload.get("adaptiveMaxWidthBps", "700")),
        "--adaptive-vol-multiplier",
        str(payload.get("adaptiveVolMultiplier", "12")),
        "--range-drift-mode",
        str(payload.get("rangeDriftMode", "cooldown")),
        "--range-drift-weight-bps",
        str(payload.get("rangeDriftWeightBps", "2500")),
        "--range-drift-max-bps",
        str(payload.get("rangeDriftMaxBps", "250")),
        "--sizing-mode",
        str(payload.get("sizingMode", "fixed")),
        "--order-margin-pct",
        str(payload.get("orderMarginPct", "35")),
        "--max-margin-pct",
        str(payload.get("maxMarginPct", "70")),
        "--total-profit-tp",
        str(payload.get("totalProfitTp", "0")),
        "--total-profit-tp-pct",
        str(payload.get("totalProfitTpPct", "0")),
        "--total-profit-tp-cap",
        str(payload.get("totalProfitTpCap", "0")),
        "--total-profit-action",
        str(payload.get("totalProfitAction", "checkpoint")),
        "--min-tp-profit",
        str(payload.get("minTpProfit", "0")),
        "--total-loss-sl",
        str(payload.get("totalLossSl", "0")),
        "--total-loss-sl-pct",
        str(payload.get("totalLossSlPct", "0")),
        "--total-loss-sl-cap",
        str(payload.get("totalLossSlCap", "0")),
        "--position-loss-sl-bps",
        str(payload.get("positionLossSlBps", "550")),
        "--min-tp-bps",
        str(payload.get("minTpBps", "200")),
        "--missed-tp-ord-type",
        str(payload.get("missedTpOrdType", "limit")),
        "--missed-tp-slippage-bps",
        str(payload.get("missedTpSlippageBps", "20")),
        "--hard-stop-ord-type",
        str(payload.get("hardStopOrdType", "market")),
        "--hard-stop-slippage-bps",
        str(payload.get("hardStopSlippageBps", "50")),
        "--risk-cooldown",
        str(payload.get("riskCooldown", "60")),
        "--trend-filter",
        str(payload.get("trendFilter", "auto")),
        "--trend-lookback",
        str(payload.get("trendLookback", "8")),
        "--trend-threshold-bps",
        str(payload.get("trendThresholdBps", "70")),
        "--regime-filter",
        str(payload.get("regimeFilter", "off")),
        "--regime-bar",
        str(payload.get("regimeBar", "15m")),
        "--regime-short-ma",
        str(payload.get("regimeShortMa", "5")),
        "--regime-long-ma",
        str(payload.get("regimeLongMa", "20")),
        "--regime-diff-bps",
        str(payload.get("regimeDiffBps", "50")),
        "--regime-confirm-bars",
        str(payload.get("regimeConfirmBars", "3")),
    ]
    if payload.get("oneWayOpen", True) is False:
        args.append("--allow-dual-open")
    if payload.get("recenterOnCooldown", True) is False:
        args.append("--no-recenter-on-cooldown")
    if use_live or payload.get("setLeverage"):
        args.append("--set-leverage")
    if payload.get("cancelOnStop"):
        args.append("--cancel-on-stop")
    if once:
        args.append("--once")
    if use_live:
        args.extend(["--live", "--confirm-live", "I_UNDERSTAND"])
    return args


def start_bot(payload: dict[str, Any]) -> dict[str, Any]:
    global BOT_PROCESS, BOT_STARTED_AT, BOT_COMMAND
    if BOT_PROCESS and BOT_PROCESS.poll() is None:
        raise RuntimeError("Grid bot is already running.")
    pid = bot_pid_from_file()
    if pid and is_process_running(pid, str(BOT_RUNTIME_CONFIG)):
        raise RuntimeError("Grid bot is already running.")

    live = bool(payload.get("live", False))
    if live:
        require_live_enabled()
        if payload.get("confirmLive") != "I_UNDERSTAND":
            raise PermissionError("Live bot requires confirmLive=I_UNDERSTAND.")

    write_bot_runtime_config(payload)
    args = build_grid_bot_args(
        payload,
        runtime_config_path=BOT_RUNTIME_CONFIG,
        action_log_path=BOT_ACTION_LOG,
        bot_prefix="gb",
        live=live,
    )

    BOT_STDOUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BOT_STDOUT_LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n--- bot start {datetime.now(timezone.utc).isoformat(timespec='seconds')} ---\n")
        log.flush()
        BOT_PROCESS = subprocess.Popen(
            args,
            cwd=Path(__file__).parent,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    BOT_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
    BOT_COMMAND = args
    BOT_PID_FILE.write_text(str(BOT_PROCESS.pid), encoding="utf-8")
    return bot_status()


def stop_bot() -> dict[str, Any]:
    global BOT_PROCESS
    if BOT_PROCESS and BOT_PROCESS.poll() is None:
        BOT_PROCESS.terminate()
        try:
            BOT_PROCESS.wait(timeout=8)
        except subprocess.TimeoutExpired:
            BOT_PROCESS.kill()
            BOT_PROCESS.wait(timeout=5)
        BOT_PROCESS = None
    else:
        pid = bot_pid_from_file()
        if pid and is_process_running(pid, "auto_grid_bot.py"):
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True, text=True)
                else:
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    if BOT_PID_FILE.exists():
        BOT_PID_FILE.unlink()
    return bot_status()


def read_bot_runtime_config() -> dict[str, Any]:
    if not BOT_RUNTIME_CONFIG.exists():
        return {}
    try:
        return json.loads(BOT_RUNTIME_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_bot_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = read_bot_runtime_config()
    for key in BOT_RUNTIME_KEYS:
        if key in payload:
            current[key] = payload[key]
    current["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    BOT_RUNTIME_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    BOT_RUNTIME_CONFIG.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def start_re_bot(payload: dict[str, Any], *, once: bool = False) -> dict[str, Any]:
    global RE_BOT_PROCESS, RE_BOT_STARTED_AT, RE_BOT_COMMAND
    if not once and RE_BOT_PROCESS and RE_BOT_PROCESS.poll() is None:
        raise RuntimeError("RE grid bot is already running.")
    pid = None if once else re_bot_pid_from_file()
    if pid and is_process_running(pid, str(RE_BOT_RUNTIME_CONFIG)):
        raise RuntimeError("RE grid bot is already running.")

    live = False if once else bool(payload.get("live", False))
    if live:
        require_live_enabled()
        if payload.get("confirmLive") != "I_UNDERSTAND":
            raise PermissionError("Live RE bot requires confirmLive=I_UNDERSTAND.")

    config = write_re_bot_runtime_config(payload)
    run_payload = {
        **config,
        "live": live,
        "setLeverage": bool(payload.get("setLeverage", False)),
        "cancelOnStop": bool(config.get("cancelOnStop", True)),
    }
    args = build_grid_bot_args(
        run_payload,
        runtime_config_path=RE_BOT_RUNTIME_CONFIG,
        action_log_path=RE_BOT_ACTION_LOG,
        bot_prefix=RE_BOT_PREFIX,
        force_inst_id=RE_BOT_INST_ID,
        once=once,
        live=live,
    )

    RE_BOT_STDOUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    if once:
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with RE_BOT_STDOUT_LOG.open("a", encoding="utf-8") as log:
            log.write(f"\n--- re bot dry-run once {started_at} ---\n")
            log.flush()
            completed = subprocess.run(
                args,
                cwd=Path(__file__).parent,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=45,
            )
        status = re_bot_status()
        status.update(
            {
                "running": False,
                "returnCode": completed.returncode,
                "startedAt": started_at,
                "command": args,
                "mode": "dry-run-once",
            }
        )
        return status

    with RE_BOT_STDOUT_LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n--- re bot start {datetime.now(timezone.utc).isoformat(timespec='seconds')} ---\n")
        log.flush()
        RE_BOT_PROCESS = subprocess.Popen(
            args,
            cwd=Path(__file__).parent,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    RE_BOT_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RE_BOT_COMMAND = args
    RE_BOT_PID_FILE.write_text(str(RE_BOT_PROCESS.pid), encoding="utf-8")
    return re_bot_status()


def stop_re_bot() -> dict[str, Any]:
    global RE_BOT_PROCESS
    if RE_BOT_PROCESS and RE_BOT_PROCESS.poll() is None:
        RE_BOT_PROCESS.terminate()
        try:
            RE_BOT_PROCESS.wait(timeout=8)
        except subprocess.TimeoutExpired:
            RE_BOT_PROCESS.kill()
            RE_BOT_PROCESS.wait(timeout=5)
        RE_BOT_PROCESS = None
    else:
        pid = re_bot_pid_from_file()
        if pid and is_process_running(pid, "auto_grid_bot.py") and is_process_running(pid, str(RE_BOT_RUNTIME_CONFIG)):
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True, text=True)
                else:
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    if RE_BOT_PID_FILE.exists():
        RE_BOT_PID_FILE.unlink()
    return re_bot_status()


def read_re_bot_runtime_config() -> dict[str, Any]:
    current = dict(RE_BOT_DEFAULTS)
    if RE_BOT_RUNTIME_CONFIG.exists():
        try:
            loaded = json.loads(RE_BOT_RUNTIME_CONFIG.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current.update(loaded)
        except Exception:
            pass
    current["instId"] = RE_BOT_INST_ID
    return current


def write_re_bot_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = read_re_bot_runtime_config()
    for key in BOT_RUNTIME_KEYS:
        if key in payload:
            current[key] = payload[key]
    current["instId"] = RE_BOT_INST_ID
    current["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    RE_BOT_RUNTIME_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    RE_BOT_RUNTIME_CONFIG.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def re_bot_pid_from_file() -> int | None:
    if not RE_BOT_PID_FILE.exists():
        return None
    try:
        return int(RE_BOT_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def re_bot_status() -> dict[str, Any]:
    running = RE_BOT_PROCESS is not None and RE_BOT_PROCESS.poll() is None
    pid = RE_BOT_PROCESS.pid if RE_BOT_PROCESS else re_bot_pid_from_file()
    if not pid:
        pid = find_process_pid(["auto_grid_bot.py", str(RE_BOT_RUNTIME_CONFIG)])
    if not running and pid:
        running = is_process_running(pid, str(RE_BOT_RUNTIME_CONFIG))
    log_lines = tail_lines(RE_BOT_STDOUT_LOG, 220)
    diagnostics = parse_bot_diagnostics(log_lines, running)
    return {
        "running": running,
        "pid": pid if running else None,
        "returnCode": RE_BOT_PROCESS.poll() if RE_BOT_PROCESS else None,
        "startedAt": RE_BOT_STARTED_AT,
        "command": RE_BOT_COMMAND,
        "runtimeConfig": read_re_bot_runtime_config(),
        "diagnostics": diagnostics,
        "logPath": str(RE_BOT_STDOUT_LOG),
        "actionLogPath": str(RE_BOT_ACTION_LOG),
        "botPrefix": RE_BOT_PREFIX,
        "logTail": "\n".join(log_lines[-80:]),
    }


def bot_pid_from_file() -> int | None:
    if not BOT_PID_FILE.exists():
        return None
    try:
        return int(BOT_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def is_process_running(pid: int, command_hint: str = "") -> bool:
    if os.name != "nt":
        try:
            cmdline = (Path("/proc") / str(pid) / "cmdline").read_text(encoding="utf-8", errors="replace")
            return bool(cmdline) and command_hint in cmdline.replace("\x00", " ")
        except Exception:
            return False

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\"; if ($p -and $p.CommandLine -like '*{command_hint}*') {{ '1' }}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "1"
    except Exception:
        return False


def find_process_pid(command_hints: list[str]) -> int | None:
    if os.name == "nt":
        try:
            hint_expr = " -and ".join([f"$p.CommandLine -like '*{hint}*'" for hint in command_hints])
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-CimInstance Win32_Process | Where-Object {{ {hint_expr} }} | Select-Object -First 1 -ExpandProperty ProcessId",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            text = result.stdout.strip()
            return int(text) if text else None
        except Exception:
            return None

    proc = Path("/proc")
    for item in proc.iterdir() if proc.exists() else []:
        if not item.name.isdigit():
            continue
        try:
            cmdline = (item / "cmdline").read_text(encoding="utf-8", errors="replace").replace("\x00", " ")
        except Exception:
            continue
        if cmdline and all(hint in cmdline for hint in command_hints):
            return int(item.name)
    return None


def bot_status() -> dict[str, Any]:
    running = BOT_PROCESS is not None and BOT_PROCESS.poll() is None
    pid = BOT_PROCESS.pid if BOT_PROCESS else bot_pid_from_file()
    if not pid:
        pid = find_process_pid(["auto_grid_bot.py", str(BOT_RUNTIME_CONFIG)])
    if not running and pid:
        running = is_process_running(pid, "auto_grid_bot.py")
    log_lines = tail_lines(BOT_STDOUT_LOG, 220)
    diagnostics = parse_bot_diagnostics(log_lines, running)
    return {
        "running": running,
        "pid": pid if running else None,
        "returnCode": BOT_PROCESS.poll() if BOT_PROCESS else None,
        "startedAt": BOT_STARTED_AT,
        "command": BOT_COMMAND,
        "runtimeConfig": read_bot_runtime_config(),
        "diagnostics": diagnostics,
        "logPath": str(BOT_STDOUT_LOG),
        "logTail": "\n".join(log_lines[-80:]),
    }


def tail_lines(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return content[-lines:]


def tail_text(path: Path, lines: int) -> str:
    return "\n".join(tail_lines(path, lines))


def parse_bot_diagnostics(lines: list[str], running: bool) -> dict[str, Any]:
    cycle: dict[str, Any] | None = None
    open_guard: dict[str, Any] | None = None
    order_plan: dict[str, Any] | None = None
    cooldown: dict[str, Any] = {"active": False}
    last_error: dict[str, Any] | None = None
    last_decision = ""
    last_cycle_index = -1
    last_error_index = -1
    actions: list[dict[str, Any]] = []

    cycle_re = re.compile(
        r"^\[(?P<time>\d\d:\d\d:\d\d)\]\s+mark=(?P<mark>\S+)\s+last=(?P<last>\S+)\s+"
        r"range=(?P<lower>\S+)-(?P<upper>\S+)\s+step=(?P<step>\S+)\s+state=(?P<state>\S+)\s+"
        r"long=(?P<long>\S+)\s+short=(?P<short>\S+)\s*(?P<note>.*)$"
    )
    open_guard_re = re.compile(
        r"^open_guard sides=(?P<sides>\S+)\s+trend=(?P<trend>\S+)\s+"
        r"change=(?P<change>\S+)bps(?:\s+regime=(?P<regime>\S+)\s+maDiff=(?P<maDiff>\S+)bps)?\s+note=(?P<note>.*)$"
    )
    desired_re = re.compile(
        r"^desired=(?P<desired>\d+)\s+existing_bot=(?P<existing>\d+)\s+"
        r"(?:(?:matched=(?P<matched>\d+)\s+)?missing=(?P<missing>\d+)\s+stale=(?P<stale>\d+))"
    )
    cooldown_re = re.compile(r"^Risk cooldown active reason=(?P<reason>\S+)\s+remaining=(?P<remaining>\d+)s")
    risk_event_re = re.compile(r"^Risk event (?P<reason>[^:]+): entering cooldown (?P<seconds>[\d.]+)s")
    hard_stop_re = re.compile(r"^Price hard stop (?P<state>\S+):")
    place_re = re.compile(
        r"^(?P<mode>LIVE|DRY) place (?P<tag>\S+)\s+(?P<side>buy|sell)\s+(?P<posSide>long|short)\s+"
        r"(?P<size>\S+)\s+@\s+(?P<price>\S+)"
    )
    cancel_re = re.compile(r"^(?P<mode>LIVE|DRY) cancel (?P<clientOrderId>\S+)\s+reason=(?P<reason>\S+)")
    cancel_all_re = re.compile(r"^(?P<mode>LIVE|DRY) cancel_all count=(?P<count>\d+)\s+reason=(?P<reason>\S+)")

    for index, line in enumerate(lines):
        if match := cycle_re.match(line):
            cycle = match.groupdict()
            last_cycle_index = index
            cooldown = {"active": False}
            continue
        if match := open_guard_re.match(line):
            sides = match.group("sides")
            open_guard = {
                "sides": [] if sides == "none" else sides.split(","),
                "trend": match.group("trend"),
                "changeBps": match.group("change"),
                "regime": match.group("regime") or "unknown",
                "maDiffBps": match.group("maDiff") or "0",
                "note": match.group("note"),
            }
            continue
        if match := desired_re.match(line):
            order_plan = {key: int(value) for key, value in match.groupdict(default="0").items()}
            continue
        if match := cooldown_re.match(line):
            cooldown = {"active": True, "reason": match.group("reason"), "remainingSeconds": int(match.group("remaining"))}
            last_decision = line
            continue
        if match := risk_event_re.match(line):
            cooldown = {"active": True, "reason": match.group("reason"), "remainingSeconds": None, "cooldownSeconds": match.group("seconds")}
            last_decision = line
            continue
        if match := hard_stop_re.match(line):
            last_decision = line
            actions.append({"kind": "risk", "text": line, "reason": match.group("state")})
            continue
        if line.startswith(("Stop state ", "Net edge too low", "Open sizing resolved", "missed_tp=", "Total profit TP hit", "Total loss hard SL hit")):
            last_decision = line
            continue
        if line.startswith(("OKX error:", "Bot error:")):
            last_error = {"text": line, "afterLastCycle": index > last_cycle_index}
            last_error_index = index
            continue
        if match := place_re.match(line):
            item = match.groupdict()
            item["kind"] = "place"
            actions.append(item)
            continue
        if match := cancel_re.match(line):
            item = match.groupdict()
            item["kind"] = "cancel"
            actions.append(item)
            continue
        if match := cancel_all_re.match(line):
            item = match.groupdict()
            item["kind"] = "cancel_all"
            actions.append(item)
            continue

    summary = summarize_bot_diagnostics(running, cycle, open_guard, order_plan, cooldown, last_error, last_error_index, last_cycle_index)
    return {
        "summary": summary,
        "cycle": cycle,
        "openGuard": open_guard,
        "orderPlan": order_plan,
        "cooldown": cooldown,
        "lastDecision": last_decision,
        "lastError": last_error,
        "actions": actions[-12:],
    }


def summarize_bot_diagnostics(
    running: bool,
    cycle: dict[str, Any] | None,
    open_guard: dict[str, Any] | None,
    order_plan: dict[str, Any] | None,
    cooldown: dict[str, Any],
    last_error: dict[str, Any] | None,
    last_error_index: int,
    last_cycle_index: int,
) -> dict[str, str]:
    if not running:
        return {"level": "stopped", "label": "未运行", "detail": "机器人进程未运行"}
    if cooldown.get("active"):
        remaining = cooldown.get("remainingSeconds")
        suffix = f"剩余 {remaining}s" if remaining is not None else "等待恢复"
        return {"level": "warn", "label": "风控冷静期", "detail": f"{cooldown.get('reason', '--')} · {suffix}"}
    if cycle and cycle.get("state") in {"hard_low", "hard_high"}:
        return {"level": "danger", "label": "硬止损触发", "detail": f"state={cycle.get('state')} · 等待平仓/冷静"}
    if last_error and last_error_index > last_cycle_index:
        return {"level": "warn", "label": "接口刚报错", "detail": last_error["text"]}
    if cycle and cycle.get("state") in {"soft_low", "soft_high", "buffer"}:
        sides = ",".join((open_guard or {}).get("sides", [])) or "none"
        return {"level": "warn", "label": "护栏限制中", "detail": f"state={cycle.get('state')} · allowed={sides}"}
    if open_guard and not open_guard.get("sides"):
        return {"level": "warn", "label": "暂停开仓", "detail": open_guard.get("note", "open_guard none")}
    if order_plan and order_plan.get("desired", 0) == 0:
        return {"level": "idle", "label": "无目标挂单", "detail": "当前条件没有生成新订单"}
    if cycle:
        return {"level": "ok", "label": "巡航交易中", "detail": f"state={cycle.get('state')} · mark={cycle.get('mark')}"}
    return {"level": "warn", "label": "等待首轮日志", "detail": "进程已启动，尚未看到完整循环"}


def parse_params(query: str) -> StrategyParams:
    values = parse_qs(query)
    return StrategyParams(
        inst_id=values.get("instId", ["BEAT-USDT-SWAP"])[0],
        lower=dec(values.get("lower", ["1.74"])[0], Decimal("1.74")),
        upper=dec(values.get("upper", ["1.82"])[0], Decimal("1.82")),
        leverage=dec(values.get("leverage", ["3"])[0], Decimal("3")),
        target_grid_bps=dec(values.get("gridBps", ["25"])[0], Decimal("25")),
        min_net_bps=dec(values.get("minNetBps", ["5"])[0], Decimal("5")),
        soft_stop_bps=dec(values.get("softBps", ["35"])[0], Decimal("35")),
        hard_stop_bps=dec(values.get("hardBps", ["60"])[0], Decimal("60")),
        mode=values.get("mode", ["adaptive"])[0],
        adaptive_width_bps=dec(values.get("adaptiveWidthBps", ["420"])[0], Decimal("420")),
        adaptive_min_width_bps=dec(values.get("adaptiveMinWidthBps", ["260"])[0], Decimal("260")),
        adaptive_max_width_bps=dec(values.get("adaptiveMaxWidthBps", ["700"])[0], Decimal("700")),
        adaptive_vol_multiplier=dec(values.get("adaptiveVolMultiplier", ["12"])[0], Decimal("12")),
        range_drift_mode=values.get("rangeDriftMode", ["cooldown"])[0],
        range_drift_weight_bps=dec(values.get("rangeDriftWeightBps", ["2500"])[0], Decimal("2500")),
        range_drift_max_bps=dec(values.get("rangeDriftMaxBps", ["250"])[0], Decimal("250")),
        sizing_mode=values.get("sizingMode", ["fixed"])[0],
        order_sz=dec(values.get("orderSz", ["0.1"])[0], Decimal("0.1")),
        max_position=dec(values.get("maxPosition", ["0.3"])[0], Decimal("0.3")),
        order_margin_pct=dec(values.get("orderMarginPct", ["35"])[0], Decimal("35")),
        max_margin_pct=dec(values.get("maxMarginPct", ["70"])[0], Decimal("70")),
        total_profit_tp=dec(values.get("totalProfitTp", ["0"])[0], Decimal("0")),
        total_profit_tp_pct=dec(values.get("totalProfitTpPct", ["5"])[0], Decimal("5")),
        total_profit_tp_cap=dec(values.get("totalProfitTpCap", ["0.5"])[0], Decimal("0.5")),
        min_tp_profit=dec(values.get("minTpProfit", ["0"])[0], Decimal("0")),
        total_loss_sl=dec(values.get("totalLossSl", ["0"])[0], Decimal("0")),
        total_loss_sl_pct=dec(values.get("totalLossSlPct", ["3"])[0], Decimal("3")),
        total_loss_sl_cap=dec(values.get("totalLossSlCap", ["0.5"])[0], Decimal("0.5")),
        position_loss_sl_bps=dec(values.get("positionLossSlBps", ["550"])[0], Decimal("550")),
        min_tp_bps=dec(values.get("minTpBps", ["200"])[0], Decimal("200")),
        trend_filter=values.get("trendFilter", ["auto"])[0],
        trend_lookback=max(1, int(dec(values.get("trendLookback", ["8"])[0], Decimal("8")))),
        trend_threshold_bps=dec(values.get("trendThresholdBps", ["70"])[0], Decimal("70")),
        regime_filter=values.get("regimeFilter", ["ma_cross"])[0],
        regime_bar=values.get("regimeBar", ["15m"])[0],
        regime_short_ma=max(1, int(dec(values.get("regimeShortMa", ["5"])[0], Decimal("5")))),
        regime_long_ma=max(2, int(dec(values.get("regimeLongMa", ["20"])[0], Decimal("20")))),
        regime_diff_bps=dec(values.get("regimeDiffBps", ["50"])[0], Decimal("50")),
        regime_confirm_bars=max(1, int(dec(values.get("regimeConfirmBars", ["3"])[0], Decimal("3")))),
        one_way_open=values.get("oneWayOpen", ["true"])[0].lower() != "false",
    )


def serialize_params(params: StrategyParams) -> dict[str, Any]:
    return {
        "instId": params.inst_id,
        "lower": str(params.lower),
        "upper": str(params.upper),
        "leverage": str(params.leverage),
        "gridBps": str(params.target_grid_bps),
        "minNetBps": str(params.min_net_bps),
        "softBps": str(params.soft_stop_bps),
        "hardBps": str(params.hard_stop_bps),
        "mode": params.mode,
        "adaptiveWidthBps": str(params.adaptive_width_bps),
        "adaptiveMinWidthBps": str(params.adaptive_min_width_bps),
        "adaptiveMaxWidthBps": str(params.adaptive_max_width_bps),
        "adaptiveVolMultiplier": str(params.adaptive_vol_multiplier),
        "rangeDriftMode": params.range_drift_mode,
        "rangeDriftWeightBps": str(params.range_drift_weight_bps),
        "rangeDriftMaxBps": str(params.range_drift_max_bps),
        "sizingMode": params.sizing_mode,
        "orderSz": str(params.order_sz),
        "maxPosition": str(params.max_position),
        "orderMarginPct": str(params.order_margin_pct),
        "maxMarginPct": str(params.max_margin_pct),
        "totalProfitTp": str(params.total_profit_tp),
        "totalProfitTpPct": str(params.total_profit_tp_pct),
        "totalProfitTpCap": str(params.total_profit_tp_cap),
        "minTpProfit": str(params.min_tp_profit),
        "totalLossSl": str(params.total_loss_sl),
        "totalLossSlPct": str(params.total_loss_sl_pct),
        "totalLossSlCap": str(params.total_loss_sl_cap),
        "positionLossSlBps": str(params.position_loss_sl_bps),
        "minTpBps": str(params.min_tp_bps),
        "trendFilter": params.trend_filter,
        "trendLookback": str(params.trend_lookback),
        "trendThresholdBps": str(params.trend_threshold_bps),
        "regimeFilter": params.regime_filter,
        "regimeBar": params.regime_bar,
        "regimeShortMa": str(params.regime_short_ma),
        "regimeLongMa": str(params.regime_long_ma),
        "regimeDiffBps": str(params.regime_diff_bps),
        "regimeConfirmBars": str(params.regime_confirm_bars),
        "oneWayOpen": params.one_way_open,
    }


def family_from_inst_id(inst_id: str) -> str:
    parts = inst_id.split("-")
    return "-".join(parts[:2])


def one(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data", [])
    return data[0] if data else {}


def dec(value: Any, default: Decimal) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def round_to_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick


def round_size(value: Decimal, lot: Decimal) -> Decimal:
    return (value / lot).to_integral_value(rounding=ROUND_DOWN) * lot


def min_positive(*values: Decimal) -> Decimal:
    positives = [value for value in values if value > 0]
    return min(positives) if positives else Decimal("0")


def clamp_pct(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(value, Decimal("100")))


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def main() -> None:
    APP_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"OKX quant dashboard running at http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
