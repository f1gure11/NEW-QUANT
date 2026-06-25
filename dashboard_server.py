from __future__ import annotations

import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from doubao_quant import quant_metadata
from okx_client import OkxApiError, OkxRestClient, load_env
from portfolio_live_plan import write_live_plan as write_portfolio_live_plan
from portfolio_preflight import run_preflight as run_portfolio_preflight
from portfolio_preflight import write_preflight_report as write_portfolio_preflight_report


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
ETH_BOT_INST_ID = "ETH-USDT-SWAP"
ETH_BOT_PREFIX = "ethg"
ETH_BOT_ACTION_LOG = Path(__file__).parent / "data" / "okx" / "eth_rolling_actions.jsonl"
ETH_BOT_STDOUT_LOG = Path(__file__).parent / "data" / "okx" / "eth_rolling_stdout.log"
ETH_BOT_RUNTIME_CONFIG = Path(__file__).parent / "data" / "okx" / "eth_rolling_runtime_config.json"
HOST = "127.0.0.1"
PORT = 8765
BOT_PROCESS: subprocess.Popen | None = None
BOT_STARTED_AT: str | None = None
BOT_COMMAND: list[str] | None = None
RE_BOT_PROCESS: subprocess.Popen | None = None
RE_BOT_STARTED_AT: str | None = None
RE_BOT_COMMAND: list[str] | None = None
PORTFOLIO_BACKTEST_PROCESS: subprocess.Popen | None = None
PORTFOLIO_BACKTEST_STARTED_AT: str | None = None
PORTFOLIO_BACKTEST_LOG = Path(__file__).parent / "data" / "okx" / "portfolio_backtest_stdout.log"
PORTFOLIO_REPORT_DIR = Path(__file__).parent / "reports" / "portfolio"
REGIME_REPORT_DIR = Path(__file__).parent / "reports" / "regime_model"
PORTFOLIO_BOT_PROCESSES: dict[str, subprocess.Popen] = {}
PORTFOLIO_BOT_STARTED_AT: dict[str, str] = {}
PORTFOLIO_BOT_COMMANDS: dict[str, list[str]] = {}
PORTFOLIO_ACCOUNT_CACHE: dict[str, Any] = {}
PORTFOLIO_ACCOUNT_CACHE_TTL_SECONDS = 20.0

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
    "exchangeStopEnabled": False,
    "exchangeStopBps": "650",
    "exchangeStopTriggerPxType": "mark",
    "exchangeStopRepriceBps": "5",
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
    "instId",
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
    "cashReservePct",
    "totalProfitTp",
    "totalProfitTpPct",
    "totalProfitTpCap",
    "totalProfitAction",
    "minTpProfit",
    "totalLossSl",
    "totalLossSlPct",
    "totalLossSlCap",
    "positionLossSlBps",
    "exchangeStopEnabled",
    "exchangeStopBps",
    "exchangeStopTriggerPxType",
    "exchangeStopRepriceBps",
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
    exchange_stop_enabled: bool = False
    exchange_stop_bps: Decimal = Decimal("650")
    exchange_stop_trigger_px_type: str = "mark"
    exchange_stop_reprice_bps: Decimal = Decimal("5")
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
        if parsed.path == "/api/eth-bot/status":
            self.handle_eth_bot_status()
            return
        if parsed.path == "/api/portfolio/latest":
            self.handle_portfolio_latest()
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
        if parsed.path == "/api/portfolio/backtest/start":
            self.handle_portfolio_backtest_start()
            return
        if parsed.path == "/api/portfolio/live/start":
            self.handle_portfolio_live_start()
            return
        if parsed.path == "/api/portfolio/live/stop":
            self.handle_portfolio_live_stop()
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

    def handle_eth_bot_status(self) -> None:
        self.send_json({"ok": True, "data": eth_bot_status()})

    def handle_portfolio_latest(self) -> None:
        self.send_json({"ok": True, "data": portfolio_status()})

    def handle_portfolio_backtest_start(self) -> None:
        try:
            payload = self.read_json()
            self.send_json({"ok": True, "data": start_portfolio_backtest(payload)})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_portfolio_live_start(self) -> None:
        try:
            payload = self.read_json()
            self.send_json({"ok": True, "data": start_portfolio_live(payload)})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_portfolio_live_stop(self) -> None:
        try:
            payload = self.read_json()
            self.send_json({"ok": True, "data": stop_portfolio_live(payload)})
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def handle_static(self, request_path: str) -> None:
        if request_path in ("", "/"):
            file_path = APP_DIR / "index.html"
        elif request_path in ("/view", "/view/"):
            file_path = APP_DIR / "view.html"
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
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
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
        "exchangeStop": exchange_stop_preview(params),
        "minTpBps": str(params.min_tp_bps),
    }


def exchange_stop_preview(params: StrategyParams) -> dict[str, Any]:
    price_bps = params.exchange_stop_bps / params.leverage if params.leverage > 0 else Decimal("0")
    return {
        "enabled": params.exchange_stop_enabled,
        "bps": str(params.exchange_stop_bps),
        "priceBps": str(price_bps),
        "triggerPxType": params.exchange_stop_trigger_px_type,
        "repriceBps": str(params.exchange_stop_reprice_bps),
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


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "portfolio"


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


def recent_fill_pnl(fills: list[dict[str, Any]], *, hours: int) -> tuple[Decimal, int]:
    since_ms = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)
    recent = [fill for fill in fills if fill_time_ms(fill) >= since_ms]
    pnl = sum((dec(fill.get("fillPnl"), Decimal("0")) + dec(fill.get("fee"), Decimal("0")) for fill in recent), Decimal("0"))
    return pnl, len(recent)


def compute_account_pnl(positions: list[dict[str, Any]], fills: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = compute_pnl(positions, fills)
    recent_5h, recent_5h_count = recent_fill_pnl(fills, hours=5)
    recent_24h, recent_24h_count = recent_fill_pnl(fills, hours=24)
    pnl.update(
        {
            "recent5h": plain(recent_5h),
            "recent5hFillCount": recent_5h_count,
            "recent24h": plain(recent_24h),
            "recent24hFillCount": recent_24h_count,
            "scope": "recent fills plus current unrealized PnL",
        }
    )
    return pnl


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
        "--cash-reserve-pct",
        str(payload.get("cashReservePct", "10")),
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
        "--exchange-stop-bps",
        str(payload.get("exchangeStopBps", "650")),
        "--exchange-stop-trigger-px-type",
        str(payload.get("exchangeStopTriggerPxType", "mark")),
        "--exchange-stop-reprice-bps",
        str(payload.get("exchangeStopRepriceBps", "5")),
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
    if payload.get("exchangeStopEnabled"):
        args.append("--exchange-stop-enabled")
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
        return {"instId": "BEAT-USDT-SWAP"}
    try:
        payload = json.loads(BOT_RUNTIME_CONFIG.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("instId", "BEAT-USDT-SWAP")
            return payload
        return {"instId": "BEAT-USDT-SWAP"}
    except Exception:
        return {"instId": "BEAT-USDT-SWAP"}


def write_bot_runtime_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = read_bot_runtime_config()
    for key in BOT_RUNTIME_KEYS:
        if key in payload:
            current[key] = payload[key]
    current["instId"] = str(payload.get("instId", current.get("instId", "BEAT-USDT-SWAP")))
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


def eth_bot_status() -> dict[str, Any]:
    pid = find_process_pid(["auto_grid_bot.py", str(ETH_BOT_RUNTIME_CONFIG)])
    running = bool(pid and is_process_running(pid, str(ETH_BOT_RUNTIME_CONFIG)))
    log_lines = tail_lines(ETH_BOT_STDOUT_LOG, 260)
    runtime_config = read_json_file(ETH_BOT_RUNTIME_CONFIG)
    runtime_config.setdefault("instId", ETH_BOT_INST_ID)
    return {
        "running": running,
        "pid": pid if running else None,
        "returnCode": None,
        "startedAt": None,
        "command": process_command(pid) if pid else "",
        "runtimeConfig": runtime_config,
        "diagnostics": parse_bot_diagnostics(log_lines, running),
        "logPath": str(ETH_BOT_STDOUT_LOG),
        "actionLogPath": str(ETH_BOT_ACTION_LOG),
        "botPrefix": ETH_BOT_PREFIX,
        "readOnly": True,
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
            parts = read_process_cmdline_parts(Path("/proc") / str(pid))
            return bool(parts) and command_parts_match_hints(parts, [command_hint])
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
            parts = read_process_cmdline_parts(item)
        except Exception:
            continue
        if command_parts_match_hints(parts, command_hints):
            return int(item.name)
    return None


def read_process_cmdline_parts(proc_dir: Path) -> list[str]:
    raw = (proc_dir / "cmdline").read_bytes()
    return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]


def command_parts_match_hints(parts: list[str], command_hints: list[str]) -> bool:
    if not parts:
        return False
    command_text = " ".join(parts)
    for hint in command_hints:
        if not hint:
            continue
        if hint.endswith(".py"):
            hint_name = Path(hint).name
            if not any(Path(part).name == hint_name for part in parts):
                return False
            continue
        if hint not in command_text:
            return False
    return True


def process_command(pid: int | None) -> str:
    if not pid or os.name == "nt":
        return ""
    try:
        return (Path("/proc") / str(pid) / "cmdline").read_text(encoding="utf-8", errors="replace").replace("\x00", " ").strip()
    except Exception:
        return ""


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


def file_mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return ""


def portfolio_status() -> dict[str, Any]:
    account = portfolio_account_summary()
    live = portfolio_live_status(include_pnl=False)
    if account.get("ok"):
        live["balance"] = account.get("balance", {})
        live["pnl"] = account.get("pnl", {})
    latest_report = latest_portfolio_report_payload(live=live)
    return {
        "backtest": portfolio_backtest_status(),
        "account": account,
        "live": live,
        "latestReport": latest_report,
        "regimeResearch": latest_regime_research_payload(),
    }


def portfolio_account_summary() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cached = PORTFOLIO_ACCOUNT_CACHE.get("payload")
    cached_at = PORTFOLIO_ACCOUNT_CACHE.get("capturedAt")
    if cached and isinstance(cached_at, datetime):
        age = (now - cached_at).total_seconds()
        if age < PORTFOLIO_ACCOUNT_CACHE_TTL_SECONDS:
            return {**cached, "cache": {"hit": True, "ageSeconds": round(age, 3), "stale": False}}
    try:
        load_env()
        client = OkxRestClient.from_env()
        try:
            client.timeout = float(os.getenv("OKX_DASHBOARD_TIMEOUT", "4"))
        except ValueError:
            client.timeout = 4.0
        account = one(client.get_account_config())
        balance = one(client.get_balance())
        positions = client.get_positions("SWAP").get("data", [])
        fills = client.get_fills(inst_type="SWAP", limit="100").get("data", [])
        payload = {
            "ok": True,
            "capturedAt": now.isoformat(timespec="seconds"),
            "account": sanitize_account(account),
            "balance": sanitize_balance(balance),
            "pnl": compute_account_pnl(positions, fills),
        }
        PORTFOLIO_ACCOUNT_CACHE["payload"] = payload
        PORTFOLIO_ACCOUNT_CACHE["capturedAt"] = now
        return {**payload, "cache": {"hit": False, "ageSeconds": 0, "stale": False}}
    except Exception as exc:
        if cached and isinstance(cached_at, datetime):
            age = (now - cached_at).total_seconds()
            return {
                **cached,
                "ok": True,
                "warning": str(exc),
                "cache": {"hit": True, "ageSeconds": round(age, 3), "stale": True},
            }
        return {
            "ok": False,
            "capturedAt": now.isoformat(timespec="seconds"),
            "error": str(exc),
            "account": {},
            "balance": {},
            "pnl": {},
            "cache": {"hit": False, "ageSeconds": 0, "stale": False},
        }


def portfolio_backtest_status() -> dict[str, Any]:
    process_running = PORTFOLIO_BACKTEST_PROCESS is not None and PORTFOLIO_BACKTEST_PROCESS.poll() is None
    external_pid = find_process_pid([str(Path(__file__).parent / "portfolio_backtest.py")])
    running = process_running or bool(external_pid)
    pid = PORTFOLIO_BACKTEST_PROCESS.pid if process_running and PORTFOLIO_BACKTEST_PROCESS else external_pid
    log_status = parse_portfolio_backtest_log()
    report_dir = latest_portfolio_report_dir()
    report_mtime = file_mtime_iso(report_dir / "summary.md") if report_dir else ""
    return_code = None
    if not running:
        if PORTFOLIO_BACKTEST_PROCESS:
            return_code = PORTFOLIO_BACKTEST_PROCESS.poll()
        elif log_status.get("returnCode") is not None:
            return_code = log_status.get("returnCode")
    return {
        "running": running,
        "state": "running" if running else log_status.get("state", "idle"),
        "pid": pid if running else None,
        "returnCode": return_code,
        "startedAt": PORTFOLIO_BACKTEST_STARTED_AT or log_status.get("startedAt"),
        "command": log_status.get("command", ""),
        "logPath": str(PORTFOLIO_BACKTEST_LOG),
        "lastLogAt": file_mtime_iso(PORTFOLIO_BACKTEST_LOG),
        "lastReportDir": str(report_dir) if report_dir else "",
        "lastReportAt": report_mtime,
        "latestReportPath": log_status.get("reportPath", ""),
        "logTail": tail_text(PORTFOLIO_BACKTEST_LOG, 80),
    }


def parse_portfolio_backtest_log() -> dict[str, Any]:
    if not PORTFOLIO_BACKTEST_LOG.exists():
        return {"state": "idle", "returnCode": None}
    text_value = PORTFOLIO_BACKTEST_LOG.read_text(encoding="utf-8", errors="replace")
    marker = "\n--- portfolio backtest start "
    parts = text_value.split(marker)
    last = parts[-1] if len(parts) > 1 else text_value
    lines = last.splitlines()
    started_at = ""
    if len(parts) > 1 and lines:
        started_at = lines[0].replace(" ---", "").strip()
    command = next((line.removeprefix("command=").strip() for line in lines if line.startswith("command=")), "")
    report_path = next((line.removeprefix("portfolio_report=").strip() for line in lines if line.startswith("portfolio_report=")), "")
    if report_path:
        state = "completed"
        return_code: int | None = 0
    elif "Traceback (most recent call last):" in last or "PermissionError:" in last:
        state = "failed"
        return_code = 1
    else:
        state = "unknown" if text_value.strip() else "idle"
        return_code = None
    return {
        "state": state,
        "returnCode": return_code,
        "startedAt": started_at,
        "command": command,
        "reportPath": report_path,
    }


def start_portfolio_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    global PORTFOLIO_BACKTEST_PROCESS, PORTFOLIO_BACKTEST_STARTED_AT
    if PORTFOLIO_BACKTEST_PROCESS and PORTFOLIO_BACKTEST_PROCESS.poll() is None:
        raise RuntimeError("Portfolio backtest is already running.")

    args = build_portfolio_backtest_args(payload)
    PORTFOLIO_BACKTEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_BACKTEST_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with PORTFOLIO_BACKTEST_LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n--- portfolio backtest start {PORTFOLIO_BACKTEST_STARTED_AT} ---\n")
        log.write("command=" + " ".join(args) + "\n")
        log.flush()
        PORTFOLIO_BACKTEST_PROCESS = subprocess.Popen(
            args,
            cwd=Path(__file__).parent,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    threading.Thread(target=wait_portfolio_backtest, daemon=True).start()
    return portfolio_status()


def wait_portfolio_backtest() -> None:
    if not PORTFOLIO_BACKTEST_PROCESS:
        return
    PORTFOLIO_BACKTEST_PROCESS.wait()


def start_portfolio_live(payload: dict[str, Any]) -> dict[str, Any]:
    require_live_enabled()
    report_dir = latest_portfolio_report_dir()
    if not report_dir:
        raise RuntimeError("No portfolio report found. Run a portfolio backtest first.")
    require_portfolio_live_report(report_dir)

    requested = set(str(item) for item in payload.get("instIds", []) if item)
    preflight_checks = run_portfolio_preflight(report_dir, include_account=True)
    if requested:
        preflight_checks = [check for check in preflight_checks if not check.inst_id or check.inst_id in requested]
    preflight_path = write_portfolio_preflight_report(report_dir, preflight_checks, include_account=True)
    preflight_blocked = any(check.severity == "block" for check in preflight_checks)
    if preflight_blocked and not payload.get("allowBlocked"):
        status = portfolio_status()
        status["liveStartResult"] = {
            "started": [],
            "skipped": [],
            "reduce": [],
            "preflightPath": str(preflight_path),
            "preflightStatus": "blocked",
            "mode": "live",
        }
        raise RuntimeError(f"Portfolio live preflight blocked. Review {preflight_path}.")

    live_plan_items = write_portfolio_live_plan(
        report_dir,
        requested or None,
        allow_blocked_preflight=bool(payload.get("allowBlocked")),
    )
    live_plan_by_inst = {item.inst_id: item for item in live_plan_items if item.inst_id}
    execution = read_json_file(report_dir / "execution_intents.json")
    intents = execution.get("intents", []) if isinstance(execution.get("intents", []), list) else []
    runnable = [
        item for item in intents
        if item.get("status") == "runtime_config_ready"
        and item.get("runtime_config_path")
        and item.get("action") in {"enter", "increase", "decrease", "hold"}
    ]
    reduce_intents = [
        item for item in intents
        if item.get("status") == "rebalance_reduce_ready"
        and item.get("action") in {"decrease", "exit"}
    ]
    if not runnable and not reduce_intents:
        raise RuntimeError("No runtime-ready portfolio targets found.")

    reduce_results = []
    if payload.get("executeRebalance", True):
        reduce_results = run_portfolio_reduce_intents(reduce_intents, requested=requested)
    started = []
    skipped = []
    for intent in runnable:
        inst_id = str(intent.get("inst_id", ""))
        if requested and inst_id not in requested:
            skipped.append({"instId": inst_id, "reason": "not requested"})
            continue
        live_plan_item = live_plan_by_inst.get(inst_id)
        if not live_plan_item or live_plan_item.status != "ready":
            skipped.append({"instId": inst_id, "reason": "live plan not ready"})
            continue
        status = portfolio_bot_status_for_intent(intent)
        if status.get("running"):
            skipped.append({"instId": inst_id, "reason": "already running", "pid": status.get("pid")})
            continue
        command = live_command_from_dry_run(live_plan_item.live_command, remove_once=True)
        if not command:
            skipped.append({"instId": inst_id, "reason": "empty command"})
            continue
        stdout_log = Path(str(intent.get("stdout_log_path") or Path(__file__).parent / "data" / "okx" / f"portfolio_{safe_name(inst_id)}_stdout.log"))
        stdout_log.parent.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with stdout_log.open("a", encoding="utf-8") as log:
            log.write(f"\n--- portfolio live bot start {started_at} {inst_id} ---\n")
            log.write("command=" + " ".join(command) + "\n")
            log.flush()
            process = subprocess.Popen(
                command,
                cwd=Path(__file__).parent,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        PORTFOLIO_BOT_PROCESSES[inst_id] = process
        PORTFOLIO_BOT_STARTED_AT[inst_id] = started_at
        PORTFOLIO_BOT_COMMANDS[inst_id] = command
        started.append({"instId": inst_id, "pid": process.pid})
    status = portfolio_status()
    status["liveStartResult"] = {
        "started": started,
        "skipped": skipped,
        "reduce": reduce_results,
        "preflightPath": str(preflight_path),
        "preflightStatus": "pass" if not preflight_blocked else "blocked_allowed",
        "livePlanStatus": "ready" if all(item.status == "ready" for item in live_plan_items if item.inst_id) else "partial",
        "mode": "live",
    }
    return status


def require_portfolio_live_report(report_dir: Path) -> None:
    rebalance = read_json_file(report_dir / "rebalance_plan.json")
    execution = read_json_file(report_dir / "execution_intents.json")
    execution_config = execution.get("execution", {}) if isinstance(execution.get("execution", {}), dict) else {}
    trading_mode = normalize_portfolio_trading_mode(
        rebalance.get("tradingMode")
        or execution.get("tradingMode")
        or execution_config.get("trading_mode")
        or execution.get("mode")
    )
    if trading_mode != "live":
        raise PermissionError(
            "Latest portfolio report is not a live candidate. "
            "Run portfolio backtest with trading mode=live before starting portfolio live bots."
        )


def stop_portfolio_live(payload: dict[str, Any]) -> dict[str, Any]:
    requested = set(str(item) for item in payload.get("instIds", []) if item)
    stopped = []
    live = portfolio_live_status()
    for bot in live.get("bots", []):
        inst_id = str(bot.get("instId", ""))
        if requested and inst_id not in requested:
            continue
        pid = bot.get("pid")
        process = PORTFOLIO_BOT_PROCESSES.get(inst_id)
        if process and process.poll() is None:
            terminate_process(process)
            stopped.append({"instId": inst_id, "pid": process.pid})
        elif pid:
            terminate_pid(int(pid))
            stopped.append({"instId": inst_id, "pid": pid})
        PORTFOLIO_BOT_PROCESSES.pop(inst_id, None)
    status = portfolio_status()
    status["liveStopResult"] = {"stopped": stopped}
    return status


def terminate_process(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def terminate_pid(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True, text=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def run_portfolio_reduce_intents(reduce_intents: list[dict[str, Any]], *, requested: set[str]) -> list[dict[str, Any]]:
    results = []
    log_path = Path(__file__).parent / "data" / "okx" / "portfolio_rebalancer_stdout.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for intent in reduce_intents:
        inst_id = str(intent.get("inst_id", ""))
        if requested and inst_id not in requested:
            results.append({"instId": inst_id, "status": "skipped", "reason": "not requested"})
            continue
        command = live_command_from_dry_run(str(intent.get("dry_run_command", "")), remove_once=False, set_leverage=False)
        if not command:
            results.append({"instId": inst_id, "status": "skipped", "reason": "empty command"})
            continue
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n--- portfolio reduce live once {started_at} {inst_id} ---\n")
            log.write("command=" + " ".join(command) + "\n")
            log.flush()
            completed = subprocess.run(
                command,
                cwd=Path(__file__).parent,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=90,
            )
        results.append({"instId": inst_id, "status": "done", "returnCode": completed.returncode, "logPath": str(log_path)})
    return results


def live_command_from_dry_run(dry_run_command: str, *, remove_once: bool, set_leverage: bool = True) -> list[str]:
    if not dry_run_command:
        return []
    parts = shlex_split_portable(dry_run_command)
    if parts and "=" in parts[0] and parts[0].startswith("PYTHONPATH"):
        parts = parts[1:]
    if parts and parts[0].endswith("python"):
        parts[0] = sys.executable
    elif parts and parts[0].endswith("python3"):
        parts[0] = sys.executable
    if remove_once:
        parts = [part for part in parts if part != "--once"]
    if set_leverage and "--set-leverage" not in parts:
        parts.append("--set-leverage")
    if "--live" not in parts:
        parts.append("--live")
    if "--confirm-live" not in parts:
        parts.extend(["--confirm-live", "I_UNDERSTAND"])
    return parts


def shlex_split_portable(command: str) -> list[str]:
    import shlex

    return shlex.split(command)


def portfolio_live_status(*, include_pnl: bool = True) -> dict[str, Any]:
    report_dir = latest_portfolio_report_dir()
    intents = []
    if report_dir:
        execution = read_json_file(report_dir / "execution_intents.json")
        raw_intents = execution.get("intents", []) if isinstance(execution.get("intents", []), list) else []
        intents = [item for item in raw_intents if item.get("status") == "runtime_config_ready"]
    bots = [portfolio_bot_status_for_intent(intent) for intent in intents]
    running = [bot for bot in bots if bot.get("running")]
    preflight = read_json_file(report_dir / "preflight_report.json") if report_dir else {}
    live_plan = read_json_file(report_dir / "live_plan.json") if report_dir else {}
    return {
        "enabled": is_live_enabled(),
        "mode": "live" if is_live_enabled() else "locked",
        "readOnlyMirror": True,
        "reportDir": str(report_dir) if report_dir else "",
        "runningCount": len(running),
        "targetCount": len(bots),
        "paperCount": len(intents),
        "preflightStatus": preflight.get("status", ""),
        "preflightIncludeAccount": preflight.get("includeAccount", False),
        "livePlanStatus": live_plan.get("status", ""),
        "bots": bots,
        "pnl": portfolio_live_pnl_summary() if include_pnl else {"estimatedTotal": "0", "recent5h": "0", "recent5hFillCount": 0},
    }


def portfolio_bot_status_for_intent(intent: dict[str, Any]) -> dict[str, Any]:
    inst_id = str(intent.get("inst_id", ""))
    bot_prefix = str(intent.get("bot_prefix", ""))
    runtime_path = str(intent.get("runtime_config_path", ""))
    stdout_log = Path(str(intent.get("stdout_log_path") or Path(__file__).parent / "data" / "okx" / f"portfolio_{safe_name(inst_id)}_stdout.log"))
    process = PORTFOLIO_BOT_PROCESSES.get(inst_id)
    running = bool(process and process.poll() is None)
    pid = process.pid if running and process else None
    if not pid and runtime_path:
        pid = find_process_pid(["auto_grid_bot.py", runtime_path])
    if not pid and inst_id:
        pid = find_process_pid(["auto_grid_bot.py", inst_id])
    command = process_command(pid) if pid else ""
    if not running and pid:
        running = bool(command and "auto_grid_bot.py" in command and (not inst_id or inst_id in command))
    log_lines = tail_lines(stdout_log, 220)
    diagnostics = parse_bot_diagnostics(log_lines, running)
    runtime_config = read_json_file(Path(runtime_path)) if runtime_path else {}
    return {
        "instId": inst_id,
        "action": intent.get("action", ""),
        "role": runtime_config.get("portfolioRole") or "",
        "running": running,
        "pid": pid if running else None,
        "returnCode": process.poll() if process and not running else None,
        "startedAt": PORTFOLIO_BOT_STARTED_AT.get(inst_id),
        "command": PORTFOLIO_BOT_COMMANDS.get(inst_id) or command,
        "runtimeConfigPath": runtime_path,
        "runtimeConfig": runtime_config,
        "botPrefix": bot_prefix,
        "logPath": str(stdout_log),
        "diagnostics": diagnostics,
        "logTail": "\n".join(log_lines[-80:]),
        "status": "实盘运行中" if running else "未运行",
    }


def portfolio_live_pnl_summary() -> dict[str, Any]:
    snapshot = latest_local_snapshot()
    pnl = snapshot.get("pnl", {}) if snapshot else {}
    fills = snapshot.get("fills", []) if snapshot else []
    recent_pnl, recent_count = recent_fill_pnl(fills, hours=5)
    return {
        "estimatedTotal": pnl.get("estimatedTotal", "0"),
        "recent5h": plain(recent_pnl),
        "recent5hFillCount": recent_count,
    }


def latest_local_snapshot() -> dict[str, Any]:
    try:
        return build_snapshot(StrategyParams(inst_id=ETH_BOT_INST_ID))
    except Exception:
        return {}


def fill_time_ms(fill: dict[str, Any]) -> int:
    value = fill.get("fillTime") or fill.get("ts") or "0"
    try:
        return int(value)
    except Exception:
        return 0


def build_portfolio_backtest_args(payload: dict[str, Any]) -> list[str]:
    top_n = bounded_int(payload.get("topN"), default=12, lower=1, upper=50)
    target_symbols = bounded_int(payload.get("targetSymbols"), default=6, lower=1, upper=20)
    pages = bounded_int(payload.get("backtestPages"), default=2, lower=1, upper=8)
    limit = bounded_int(payload.get("backtestLimit"), default=300, lower=80, upper=300)
    trading_mode = str(payload.get("tradingMode") or payload.get("mode") or "backtest")
    if trading_mode not in {"backtest", "paper", "live"}:
        trading_mode = "backtest"
    args = [
        sys.executable,
        str(Path(__file__).parent / "portfolio_backtest.py"),
        "--top-n",
        str(top_n),
        "--target-symbols",
        str(target_symbols),
        "--backtest-pages",
        str(pages),
        "--backtest-limit",
        str(limit),
        "--min-quote-volume",
        safe_decimal_arg(payload.get("minQuoteVolume"), "5000000"),
        "--max-spread-bps",
        safe_decimal_arg(payload.get("maxSpreadBps"), "20"),
        "--starting-equity",
        safe_decimal_arg(payload.get("startingEquity"), "100"),
        "--cash-reserve-pct",
        safe_decimal_arg(payload.get("cashReservePct"), "10"),
        "--core-symbols",
        str(bounded_int(payload.get("coreSymbols"), default=2, lower=1, upper=10)),
        "--core-weight-share-pct",
        safe_decimal_arg(payload.get("coreWeightSharePct"), "70"),
        "--satellite-max-weight-pct",
        safe_decimal_arg(payload.get("satelliteMaxWeightPct"), "12"),
        "--satellite-min-weight-pct",
        safe_decimal_arg(payload.get("satelliteMinWeightPct"), "3"),
        "--trend-filter",
        str(payload.get("trendFilter") or "compare"),
        "--market-regime-filter",
        str(payload.get("marketRegimeFilter") or "auto"),
        "--market-regime-min-confidence",
        safe_decimal_arg(payload.get("marketRegimeMinConfidence"), "0.52"),
        "--trading-mode",
        trading_mode,
    ]
    if payload.get("marketRegimeModelPath"):
        args.extend(["--market-regime-model-path", str(payload.get("marketRegimeModelPath"))])
    if payload.get("includeAccount") or trading_mode == "live":
        args.append("--include-account")
    if payload.get("refresh"):
        args.append("--refresh")
    return args


def latest_portfolio_report_payload(*, live: dict[str, Any] | None = None) -> dict[str, Any] | None:
    report_dir = latest_portfolio_report_dir()
    if not report_dir:
        return None
    candidates = read_json_file(report_dir / "candidates.json")
    rebalance = read_json_file(report_dir / "rebalance_plan.json")
    execution = read_json_file(report_dir / "execution_intents.json")
    live_plan = read_json_file(report_dir / "live_plan.json")
    preflight = read_json_file(report_dir / "preflight_report.json")
    scores = read_csv_file(report_dir / "scores.csv", limit=50)
    runtime_configs = read_portfolio_runtime_configs(report_dir)
    live = live or portfolio_live_status(include_pnl=False)
    annotate_rebalance_actions(rebalance)
    return {
        "reportDir": str(report_dir),
        "name": report_dir.name,
        "generatedAt": rebalance.get("generatedAt") or candidates.get("generatedAt") or "",
        "product": rebalance.get("product") or candidates.get("product") or quant_metadata(),
        "summary": portfolio_report_summary(scores, rebalance, execution, runtime_configs, live),
        "candidates": candidates,
        "scores": scores,
        "rebalance": rebalance,
        "execution": execution,
        "preflight": preflight,
        "livePlan": live_plan,
        "runtimeConfigs": runtime_configs,
        "live": live,
        "summaryMarkdown": (report_dir / "summary.md").read_text(encoding="utf-8", errors="replace") if (report_dir / "summary.md").exists() else "",
    }


def annotate_rebalance_actions(rebalance: dict[str, Any]) -> None:
    actions = rebalance.get("actions")
    if not isinstance(actions, list):
        return
    generated_at = str(rebalance.get("generatedAt") or "")
    allocation = rebalance.get("allocation", {}) if isinstance(rebalance.get("allocation", {}), dict) else {}
    threshold = allocation.get("rebalance_threshold_pct", "2")
    for action in actions:
        if not isinstance(action, dict):
            continue
        action.setdefault("generated_at", generated_at)
        action.setdefault("rebalance_threshold_pct", threshold)
        action.setdefault("reason", rebalance_action_reason(action, threshold))


def rebalance_action_reason(action: dict[str, Any], threshold: Any = "2") -> str:
    note = str(action.get("note") or "")
    action_name = str(action.get("action") or "")
    delta = dec(action.get("delta_weight_pct"), Decimal("0"))
    threshold_text = plain(dec(threshold, Decimal("0")))
    if not note:
        note = {
            "enter": "new target allocation",
            "increase": "below target allocation",
            "decrease": "above target allocation",
            "exit": "not selected by target portfolio",
            "hold": "within threshold",
        }.get(action_name, "")
    note_text = {
        "new target allocation": "目标组合新增该合约",
        "below target allocation": "当前权重低于目标权重",
        "above target allocation": "当前权重高于目标权重",
        "close missing target": "该合约不在目标组合内",
        "not selected by target portfolio": "该合约不在目标组合内",
        "within threshold": "偏离未超过调仓阈值",
    }.get(note, note or "组合权重偏离检查")
    if action_name == "hold":
        return f"{note_text}，偏离 {plain(abs(delta))}% 未达到 {threshold_text}% 阈值。"
    return f"{note_text}，偏离 {plain(abs(delta))}% 达到 {threshold_text}% 调仓阈值。"


def latest_portfolio_report_dir() -> Path | None:
    if not PORTFOLIO_REPORT_DIR.exists():
        return None
    dirs = [path for path in PORTFOLIO_REPORT_DIR.iterdir() if path.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dirs[0]


def latest_regime_research_payload() -> dict[str, Any] | None:
    report_dir = latest_regime_research_dir()
    if not report_dir:
        return None
    scores = read_csv_file(report_dir / "scores.csv", limit=500)
    metrics = read_json_file(report_dir / "model_metrics.json")
    config = read_json_file(report_dir / "config.json")
    summary_markdown = (report_dir / "summary.md").read_text(encoding="utf-8", errors="replace") if (report_dir / "summary.md").exists() else ""
    variant_rows = regime_variant_summary(scores)
    best_variant = best_regime_variant(variant_rows)
    return {
        "reportDir": str(report_dir),
        "name": report_dir.name,
        "generatedAt": metrics.get("generatedAt") or file_mtime_iso(report_dir),
        "bestVariant": best_variant,
        "variantSummary": variant_rows,
        "topRows": regime_top_rows(scores),
        "models": {
            "rf": regime_model_summary(metrics.get("rf", {})),
            "hmm": regime_model_summary(metrics.get("hmm", {})),
        },
        "config": config,
        "summaryMarkdown": summary_markdown,
        "quantDinger": {
            "source": "github.com/brokermr810/QuantDinger",
            "commit": "b3b3c5c",
            "license": "Apache-2.0",
            "integration": "signal/execution standard and monitoring-report shape only; no live execution code vendored",
        },
    }


def latest_regime_research_dir() -> Path | None:
    if not REGIME_REPORT_DIR.exists():
        return None
    dirs = [path for path in REGIME_REPORT_DIR.iterdir() if path.is_dir() and (path / "scores.csv").exists()]
    if not dirs:
        return None
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dirs[0]


def regime_variant_summary(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    variants: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("error"):
            continue
        variant = str(row.get("variant") or "")
        if variant:
            variants.setdefault(variant, []).append(row)
    output: list[dict[str, Any]] = []
    for variant, items in sorted(variants.items()):
        if not items:
            continue
        count = Decimal(len(items))
        output.append(
            {
                "variant": variant,
                "symbols": len(items),
                "avgReturnPct": plain(sum((dec(row.get("total_return_pct"), Decimal("0")) for row in items), Decimal("0")) / count),
                "avgMaxDrawdownPct": plain(sum((dec(row.get("max_drawdown_pct"), Decimal("0")) for row in items), Decimal("0")) / count),
                "avgScore": plain(sum((dec(row.get("score"), Decimal("0")) for row in items), Decimal("0")) / count),
                "totalFills": sum(int(dec(row.get("fills"), Decimal("0"))) for row in items),
                "totalRiskEvents": sum(int(dec(row.get("risk_events"), Decimal("0"))) for row in items),
                "positiveSymbols": sum(1 for row in items if dec(row.get("total_return_pct"), Decimal("0")) > 0),
            }
        )
    return output


def best_regime_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [row for row in rows if row.get("variant") != "baseline"]
    if not candidates:
        return {}
    best = max(candidates, key=lambda row: dec(row.get("avgScore"), Decimal("-999999")))
    baseline = next((row for row in rows if row.get("variant") == "baseline"), {})
    return {
        **best,
        "scoreDeltaVsBaseline": plain(dec(best.get("avgScore"), Decimal("0")) - dec(baseline.get("avgScore"), Decimal("0"))) if baseline else "",
        "returnDeltaVsBaseline": plain(dec(best.get("avgReturnPct"), Decimal("0")) - dec(baseline.get("avgReturnPct"), Decimal("0"))) if baseline else "",
        "drawdownDeltaVsBaseline": plain(dec(best.get("avgMaxDrawdownPct"), Decimal("0")) - dec(baseline.get("avgMaxDrawdownPct"), Decimal("0"))) if baseline else "",
        "riskEventDeltaVsBaseline": int(best.get("totalRiskEvents") or 0) - int(baseline.get("totalRiskEvents") or 0) if baseline else "",
        "recommendation": "research_only_gate_not_live_default",
    }


def regime_top_rows(rows: list[dict[str, str]], *, per_variant: int = 6) -> list[dict[str, Any]]:
    ok_rows = [row for row in rows if not row.get("error")]
    output = []
    for variant in sorted({str(row.get("variant") or "") for row in ok_rows}):
        items = [row for row in ok_rows if row.get("variant") == variant]
        items.sort(key=lambda row: int(dec(row.get("rank"), Decimal("999999"))))
        for row in items[:per_variant]:
            output.append(
                {
                    "variant": row.get("variant", ""),
                    "rank": row.get("rank", ""),
                    "instId": row.get("inst_id", ""),
                    "score": row.get("score", ""),
                    "totalReturnPct": row.get("total_return_pct", ""),
                    "maxDrawdownPct": row.get("max_drawdown_pct", ""),
                    "fills": row.get("fills", ""),
                    "riskEvents": row.get("risk_events", ""),
                    "latestSignal": row.get("latest_signal", ""),
                    "latestConfidence": row.get("latest_confidence", ""),
                    "latestAllowedSides": row.get("latest_allowed_sides", ""),
                }
            )
    return output


def regime_model_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        "samples": payload.get("samples", 0),
        "classes": payload.get("classes", []),
        "labelCounts": payload.get("label_counts", {}),
        "accuracy": payload.get("accuracy"),
        "states": payload.get("states"),
        "stateMap": payload.get("state_map", {}),
        "stateConfidence": payload.get("state_confidence", {}),
        "accuracyVsWeakLabels": payload.get("accuracy_vs_weak_labels"),
    }


def portfolio_report_summary(
    scores: list[dict[str, str]],
    rebalance: dict[str, Any],
    execution: dict[str, Any],
    runtime_configs: list[dict[str, Any]],
    live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = rebalance.get("targets", []) if isinstance(rebalance.get("targets", []), list) else []
    actions = rebalance.get("actions", []) if isinstance(rebalance.get("actions", []), list) else []
    exposures = rebalance.get("currentExposures", []) if isinstance(rebalance.get("currentExposures", []), list) else []
    intents = execution.get("intents", []) if isinstance(execution.get("intents", []), list) else []
    ok_scores = [row for row in scores if row.get("status") == "ok"]
    satellites = [target for target in targets if target.get("role") == "satellite"]
    core = [target for target in targets if target.get("role") == "core"]
    runtime_by_inst = {item.get("instId"): item for item in runtime_configs}
    trend_checked = [row for row in ok_scores if str(row.get("trend_filter_checked", "")).lower() in {"true", "1", "yes"}]
    trend_auto = [row for row in ok_scores if row.get("selected_trend_filter") == "auto"]
    market_regime_rows = [row for row in ok_scores if row.get("market_regime_filter") and row.get("market_regime_filter") != "off"]
    live = live or {}
    trading_mode = normalize_portfolio_trading_mode(rebalance.get("tradingMode") or execution.get("mode") or "backtest")
    return {
        "tradingMode": trading_mode,
        "paperMode": trading_mode in {"backtest", "paper"},
        "liveCandidateMode": trading_mode == "live",
        "scoreCount": len(scores),
        "okScoreCount": len(ok_scores),
        "targetCount": len(targets),
        "coreCount": len(core),
        "satelliteCount": len(satellites),
        "actionCount": len(actions),
        "currentExposureCount": len(exposures),
        "executionReadyCount": sum(1 for item in intents if item.get("status") == "runtime_config_ready"),
        "targetWeightPct": sum_decimal(target.get("weight_pct") for target in targets),
        "satelliteWeightPct": sum_decimal(target.get("weight_pct") for target in satellites),
        "currentMarginPct": sum_decimal(exposure.get("margin_estimate") for exposure in exposures),
        "currentGrossNotional": sum_decimal(exposure.get("gross_notional") for exposure in exposures),
        "liveRunningCount": live.get("runningCount", 0),
        "liveTargetCount": live.get("targetCount", 0),
        "liveEnabled": live.get("enabled", False),
        "liveMode": live.get("mode", "locked"),
        "estimatedTotalPnl": (live.get("pnl") or {}).get("estimatedTotal", "0"),
        "recent5hPnl": (live.get("pnl") or {}).get("recent5h", "0"),
        "recent5hFillCount": (live.get("pnl") or {}).get("recent5hFillCount", 0),
        "trendCheckedCount": len(trend_checked),
        "trendAutoSelectedCount": len(trend_auto),
        "trendOffSelectedCount": len([row for row in ok_scores if row.get("selected_trend_filter") == "off"]),
        "marketRegimeActiveCount": len(market_regime_rows),
        "marketRegimeModes": sorted({row.get("market_regime_filter") for row in market_regime_rows if row.get("market_regime_filter")}),
        "marketRegimeSignals": count_by_key(market_regime_rows, "market_regime_signal"),
        "mlScoreDeltaVsBaseline": first_nonempty((row.get("ml_score_delta_vs_baseline") for row in ok_scores), ""),
        "mlReturnDeltaVsBaseline": first_nonempty((row.get("ml_return_delta_vs_baseline") for row in ok_scores), ""),
        "mlDrawdownDeltaVsBaseline": first_nonempty((row.get("ml_drawdown_delta_vs_baseline") for row in ok_scores), ""),
        "mlRiskEventDeltaVsBaseline": first_nonempty((row.get("ml_risk_event_delta_vs_baseline") for row in ok_scores), ""),
        "actionsByType": count_by_key(actions, "action"),
        "intentsByStatus": count_by_key(intents, "status"),
        "adaptivePreview": [
            {
                "instId": target.get("inst_id"),
                "role": target.get("role"),
                "weightPct": target.get("weight_pct"),
                "poolAvgAbsBps": target.get("pool_avg_abs_bps"),
                "poolShockBps": target.get("pool_shock_bps"),
                "poolTrendBps": target.get("pool_trend_bps"),
                "leverage": runtime_by_inst.get(target.get("inst_id"), {}).get("leverage"),
                "gridBps": runtime_by_inst.get(target.get("inst_id"), {}).get("gridBps"),
                "minTpBps": runtime_by_inst.get(target.get("inst_id"), {}).get("minTpBps"),
                "positionLossSlBps": runtime_by_inst.get(target.get("inst_id"), {}).get("positionLossSlBps"),
                "exchangeStopBps": runtime_by_inst.get(target.get("inst_id"), {}).get("exchangeStopBps"),
                "totalProfitTpPct": runtime_by_inst.get(target.get("inst_id"), {}).get("totalProfitTpPct"),
                "totalLossSlPct": runtime_by_inst.get(target.get("inst_id"), {}).get("totalLossSlPct"),
                "backtestTotalReturnPct": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestTotalReturnPct"),
                "backtestMaxDrawdownPct": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestMaxDrawdownPct"),
                "backtestProfitFactor": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestProfitFactor"),
                "backtestFills": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestFills"),
                "backtestRiskEvents": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestRiskEvents"),
                "backtestRiskRewardScore": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestRiskRewardScore"),
                "backtestTargetSlRatio": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestTargetSlRatio"),
                "backtestRiskRewardNote": runtime_by_inst.get(target.get("inst_id"), {}).get("backtestRiskRewardNote"),
                "riskScore": runtime_by_inst.get(target.get("inst_id"), {}).get("poolAdaptiveRiskScore"),
                "trendFilter": runtime_by_inst.get(target.get("inst_id"), {}).get("trendFilter"),
                "trendFilterChecked": runtime_by_inst.get(target.get("inst_id"), {}).get("trendFilterChecked"),
                "trendScoreDelta": runtime_by_inst.get(target.get("inst_id"), {}).get("trendScoreDelta"),
                "marketRegimeFilter": runtime_by_inst.get(target.get("inst_id"), {}).get("marketRegimeFilter"),
                "marketRegimeSignal": runtime_by_inst.get(target.get("inst_id"), {}).get("marketRegimeSignal"),
                "marketRegimeConfidence": runtime_by_inst.get(target.get("inst_id"), {}).get("marketRegimeConfidence"),
                "marketRegimeAllowedSides": runtime_by_inst.get(target.get("inst_id"), {}).get("marketRegimeAllowedSides"),
                "mlScoreDeltaVsBaseline": runtime_by_inst.get(target.get("inst_id"), {}).get("mlScoreDeltaVsBaseline"),
                "mlReturnDeltaVsBaseline": runtime_by_inst.get(target.get("inst_id"), {}).get("mlReturnDeltaVsBaseline"),
                "mlDrawdownDeltaVsBaseline": runtime_by_inst.get(target.get("inst_id"), {}).get("mlDrawdownDeltaVsBaseline"),
                "mlRiskEventDeltaVsBaseline": runtime_by_inst.get(target.get("inst_id"), {}).get("mlRiskEventDeltaVsBaseline"),
                "note": runtime_by_inst.get(target.get("inst_id"), {}).get("poolAdaptiveNote"),
            }
            for target in targets
        ],
    }


def read_portfolio_runtime_configs(report_dir: Path) -> list[dict[str, Any]]:
    runtime_dir = report_dir / "runtime_configs"
    if not runtime_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(runtime_dir.glob("*.json")):
        payload = read_json_file(path)
        if payload:
            payload["_path"] = str(path)
            rows.append(payload)
    return rows


def normalize_portfolio_trading_mode(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"backtest", "paper", "live"}:
        return text
    if text in {"dry_run", "dry_run_execution_bundle", "manual_live_start_draft"}:
        return "paper"
    if text in {"live_candidate", "dashboard_live_start_plan"}:
        return "live"
    return "backtest"


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_csv_file(path: Path, *, limit: int = 100) -> list[dict[str, str]]:
    if not path.exists():
        return []
    import csv

    with path.open("r", encoding="utf-8", newline="") as file:
        return [row for _, row in zip(range(limit), csv.DictReader(file))]


def sum_decimal(values: Any) -> str:
    total = Decimal("0")
    for value in values:
        total += dec(value, Decimal("0"))
    return plain(total)


def count_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "") or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def first_nonempty(values: Any, default: Any = "") -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return default


def bounded_int(value: Any, *, default: int, lower: int, upper: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lower, min(upper, number))


def safe_decimal_arg(value: Any, default: str) -> str:
    number = dec(value, Decimal(default))
    return plain(number)


def parse_bot_diagnostics(lines: list[str], running: bool) -> dict[str, Any]:
    cycle: dict[str, Any] | None = None
    open_guard: dict[str, Any] | None = None
    order_plan: dict[str, Any] | None = None
    rolling_adaptive: dict[str, Any] | None = None
    sizing: dict[str, Any] | None = None
    edge: dict[str, Any] | None = None
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
    rolling_re = re.compile(
        r"^rolling_adaptive leverage=(?P<leverage>\S+)x\s+grid=(?P<gridBps>\S+)bps\s+"
        r"order_margin=(?P<orderMarginPct>\S+)%\s+max_margin=(?P<maxMarginPct>\S+)%\s+"
        r"tp=(?P<minTpBps>\S+)bps\s+sl=(?P<positionLossSlBps>\S+)bps\s+"
        r"rolling window=(?P<window>\d+)\s+avg_abs=(?P<avgAbsBps>\S+)bps\s+"
        r"shock=(?P<shockBps>\S+)bps\s+trend=(?P<trendBps>\S+)bps\s+"
        r"risk=(?P<riskScore>\S+)\s+min_contract_margin=(?P<minContractMargin>\S+)"
    )
    sizing_re = re.compile(r"^sizing order_sz=(?P<orderSz>\S+)\s+max_position=(?P<maxPosition>\S+)\s+(?P<note>.*)$")
    edge_re = re.compile(
        r"^edge gross=(?P<grossBps>\S+)bps\s+net_est=(?P<netEstBps>\S+)bps\s+"
        r"min_net=(?P<minNetBps>\S+)bps\s+fees=(?P<fees>.*)$"
    )

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
        if match := rolling_re.match(line):
            rolling_adaptive = match.groupdict()
            continue
        if match := sizing_re.match(line):
            sizing = match.groupdict()
            sizing.update(parse_key_values(match.group("note")))
            continue
        if match := edge_re.match(line):
            edge = match.groupdict()
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
        "rollingAdaptive": rolling_adaptive,
        "sizing": sizing,
        "edge": edge,
        "cooldown": cooldown,
        "lastDecision": last_decision,
        "lastError": last_error,
        "actions": actions[-12:],
    }


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in text.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        values[key] = value
    return values


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
        exchange_stop_enabled=values.get("exchangeStopEnabled", ["false"])[0].lower() == "true",
        exchange_stop_bps=dec(values.get("exchangeStopBps", ["650"])[0], Decimal("650")),
        exchange_stop_trigger_px_type=values.get("exchangeStopTriggerPxType", ["mark"])[0],
        exchange_stop_reprice_bps=dec(values.get("exchangeStopRepriceBps", ["5"])[0], Decimal("5")),
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
        "exchangeStopEnabled": params.exchange_stop_enabled,
        "exchangeStopBps": str(params.exchange_stop_bps),
        "exchangeStopTriggerPxType": params.exchange_stop_trigger_px_type,
        "exchangeStopRepriceBps": str(params.exchange_stop_reprice_bps),
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
    print(f"豆包 Quant dashboard running at http://{HOST}:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
