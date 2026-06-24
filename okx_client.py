from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen


class OkxApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        okx_code: str | None = None,
        okx_msg: str | None = None,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.okx_code = okx_code
        self.okx_msg = okx_msg
        self.response = response


def load_env(path: str | os.PathLike[str] = ".env", *, override: bool = True) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


@dataclass(slots=True)
class OkxRestClient:
    api_key: str = ""
    secret_key: str = ""
    passphrase: str = ""
    simulated_trading: bool = False
    base_url: str = "https://www.okx.com"
    proxy_url: str = ""
    user_agent: str = "curl/8.10.1"
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "OkxRestClient":
        return cls(
            api_key=os.getenv("OKX_API_KEY", ""),
            secret_key=os.getenv("OKX_SECRET_KEY", ""),
            passphrase=os.getenv("OKX_PASSPHRASE", ""),
            simulated_trading=os.getenv("OKX_SIMULATED_TRADING", "0") == "1",
            base_url=os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/"),
            proxy_url=os.getenv("OKX_PROXY", ""),
            user_agent=os.getenv("OKX_USER_AGENT", "curl/8.10.1"),
        )

    @staticmethod
    def timestamp() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        digest = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | list[Any] | None = None,
        private: bool = False,
    ) -> dict[str, Any]:
        method = method.upper()
        request_path = self._request_path(path, params)
        body_text = "" if body is None else json.dumps(body, separators=(",", ":"))

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        if private:
            self._require_credentials()
            timestamp = self.timestamp()
            headers.update(
                {
                    "OK-ACCESS-KEY": self.api_key,
                    "OK-ACCESS-SIGN": self.sign(timestamp, method, request_path, body_text),
                    "OK-ACCESS-TIMESTAMP": timestamp,
                    "OK-ACCESS-PASSPHRASE": self.passphrase,
                }
            )
            if self.simulated_trading:
                headers["x-simulated-trading"] = "1"

        data = body_text.encode("utf-8") if body_text else None
        request = Request(
            f"{self.base_url}{request_path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            opener = self._opener()
            with opener.open(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
                parsed = json.loads(payload) if payload else {}
        except HTTPError as exc:
            error_payload = exc.read().decode("utf-8", errors="replace")
            parsed_error = self._parse_json(error_payload)
            raise OkxApiError(
                f"OKX HTTP error {exc.code}: {parsed_error or error_payload}",
                status=exc.code,
                okx_code=self._okx_field(parsed_error, "code"),
                okx_msg=self._okx_field(parsed_error, "msg"),
                response=parsed_error or error_payload,
            ) from exc
        except URLError as exc:
            raise OkxApiError(f"OKX network error: {exc.reason}") from exc

        okx_code = self._okx_field(parsed, "code")
        if okx_code not in (None, "0"):
            okx_msg = self._okx_field(parsed, "msg") or "OKX returned an error"
            raise OkxApiError(
                f"OKX API error {okx_code}: {okx_msg}",
                okx_code=okx_code,
                okx_msg=okx_msg,
                response=parsed,
            )
        return parsed

    def get_server_time(self) -> dict[str, Any]:
        return self.request("GET", "/api/v5/public/time")

    def get_ticker(self, inst_id: str = "BTC-USDT") -> dict[str, Any]:
        return self.request("GET", "/api/v5/market/ticker", params={"instId": inst_id})

    def get_account_config(self) -> dict[str, Any]:
        return self.request("GET", "/api/v5/account/config", private=True)

    def get_balance(self, ccy: str | None = None) -> dict[str, Any]:
        params = {"ccy": ccy} if ccy else None
        return self.request("GET", "/api/v5/account/balance", params=params, private=True)

    def get_positions(self, inst_type: str | None = None) -> dict[str, Any]:
        params = {"instType": inst_type} if inst_type else None
        return self.request("GET", "/api/v5/account/positions", params=params, private=True)

    def place_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        ord_type: str,
        sz: str,
        px: str | None = None,
        pos_side: str | None = None,
        reduce_only: bool | None = None,
        cl_ord_id: str | None = None,
        attach_algo_ords: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        order: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
            "sz": sz,
        }
        if px is not None:
            order["px"] = px
        if pos_side is not None:
            order["posSide"] = pos_side
        if reduce_only is not None:
            order["reduceOnly"] = "true" if reduce_only else "false"
        if cl_ord_id is not None:
            order["clOrdId"] = cl_ord_id
        if attach_algo_ords:
            order["attachAlgoOrds"] = attach_algo_ords
        return self.request("POST", "/api/v5/trade/order", body=order, private=True)

    def cancel_order(
        self,
        *,
        inst_id: str,
        ord_id: str | None = None,
        cl_ord_id: str | None = None,
    ) -> dict[str, Any]:
        body = {"instId": inst_id}
        if ord_id:
            body["ordId"] = ord_id
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        return self.request("POST", "/api/v5/trade/cancel-order", body=body, private=True)

    def cancel_orders(self, orders: list[dict[str, str]]) -> dict[str, Any]:
        body = []
        for order in orders:
            item = {"instId": order["instId"]}
            if order.get("ordId"):
                item["ordId"] = order["ordId"]
            if order.get("clOrdId"):
                item["clOrdId"] = order["clOrdId"]
            body.append(item)
        return self.request("POST", "/api/v5/trade/cancel-batch-orders", body=body, private=True)

    def get_pending_orders(self, inst_id: str | None = None) -> dict[str, Any]:
        params = {"instId": inst_id} if inst_id else None
        return self.request("GET", "/api/v5/trade/orders-pending", params=params, private=True)

    def place_algo_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        ord_type: str,
        sz: str | None = None,
        pos_side: str | None = None,
        algo_cl_ord_id: str | None = None,
        sl_trigger_px: str | None = None,
        sl_ord_px: str | None = None,
        sl_trigger_px_type: str | None = None,
        reduce_only: bool | None = None,
        cxl_on_close_pos: bool | None = None,
    ) -> dict[str, Any]:
        order: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side,
            "ordType": ord_type,
        }
        if sz is not None:
            order["sz"] = sz
        if pos_side is not None:
            order["posSide"] = pos_side
        if algo_cl_ord_id is not None:
            order["algoClOrdId"] = algo_cl_ord_id
        if sl_trigger_px is not None:
            order["slTriggerPx"] = sl_trigger_px
        if sl_ord_px is not None:
            order["slOrdPx"] = sl_ord_px
        if sl_trigger_px_type is not None:
            order["slTriggerPxType"] = sl_trigger_px_type
        if reduce_only is not None:
            order["reduceOnly"] = bool(reduce_only)
        if cxl_on_close_pos is not None:
            order["cxlOnClosePos"] = bool(cxl_on_close_pos)
        return self.request("POST", "/api/v5/trade/order-algo", body=order, private=True)

    def get_pending_algo_orders(
        self,
        *,
        ord_type: str = "conditional",
        inst_id: str | None = None,
        inst_type: str | None = None,
        algo_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ordType": ord_type}
        if inst_id:
            params["instId"] = inst_id
        if inst_type:
            params["instType"] = inst_type
        if algo_id:
            params["algoId"] = algo_id
        return self.request("GET", "/api/v5/trade/orders-algo-pending", params=params, private=True)

    def cancel_algo_orders(self, orders: list[dict[str, str]]) -> dict[str, Any]:
        body = []
        for order in orders:
            item = {"instId": order["instId"], "algoId": order["algoId"]}
            body.append(item)
        return self.request("POST", "/api/v5/trade/cancel-algos", body=body, private=True)

    def get_fills(
        self,
        *,
        inst_id: str | None = None,
        inst_type: str | None = None,
        limit: str = "100",
    ) -> dict[str, Any]:
        params = {"limit": limit}
        if inst_id:
            params["instId"] = inst_id
        if inst_type:
            params["instType"] = inst_type
        return self.request("GET", "/api/v5/trade/fills", params=params, private=True)

    def set_leverage(
        self,
        *,
        inst_id: str,
        lever: str,
        mgn_mode: str = "cross",
        pos_side: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "instId": inst_id,
            "lever": lever,
            "mgnMode": mgn_mode,
        }
        if pos_side:
            body["posSide"] = pos_side
        return self.request("POST", "/api/v5/account/set-leverage", body=body, private=True)

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in (
                ("OKX_API_KEY", self.api_key),
                ("OKX_SECRET_KEY", self.secret_key),
                ("OKX_PASSPHRASE", self.passphrase),
            )
            if not value
        ]
        if missing:
            raise OkxApiError(f"Missing OKX credentials: {', '.join(missing)}")

    @staticmethod
    def _request_path(path: str, params: dict[str, Any] | None = None) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        if not params:
            return path
        clean_params = {key: value for key, value in params.items() if value is not None}
        if not clean_params:
            return path
        return f"{path}?{urlencode(clean_params, doseq=True)}"

    def _opener(self):
        if not self.proxy_url:
            return build_opener()
        return build_opener(
            ProxyHandler({"http": self.proxy_url, "https": self.proxy_url})
        )

    @staticmethod
    def _parse_json(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _okx_field(payload: Any, key: str) -> str | None:
        return payload.get(key) if isinstance(payload, dict) else None
