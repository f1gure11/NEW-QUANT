from __future__ import annotations

import base64
import hmac
import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit, urlunsplit


TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def readonly_auth_enabled(flag_value: str | None) -> bool:
    return (flag_value or "").strip().lower() in TRUE_ENV_VALUES


LISTEN_HOST = os.getenv("READONLY_DASHBOARD_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("READONLY_DASHBOARD_PORT", "8770"))
TARGET_HOST = os.getenv("READONLY_DASHBOARD_TARGET_HOST", "127.0.0.1")
TARGET_PORT = int(os.getenv("READONLY_DASHBOARD_TARGET_PORT", "8765"))
AUTH_USER = os.getenv("READONLY_DASHBOARD_AUTH_USER") or os.getenv("DASHBOARD_AUTH_USER", "")
AUTH_PASSWORD = os.getenv("READONLY_DASHBOARD_AUTH_PASSWORD") or os.getenv("DASHBOARD_AUTH_PASSWORD", "")
AUTH_REQUIRED = readonly_auth_enabled(os.getenv("READONLY_DASHBOARD_AUTH_REQUIRED"))

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

ALLOWED_API_PATHS = {
    "/api/portfolio/latest",
}

ALLOWED_STATIC_PATHS = {
    "/",
    "/view",
    "/view/",
    "/view.html",
    "/view.js",
    "/view.css",
}


class ReadonlyProxyHandler(BaseHTTPRequestHandler):
    server_version = "OKXDashboardReadonlyProxy/0.1"

    def do_GET(self) -> None:
        self.proxy_readonly_request()

    def do_HEAD(self) -> None:
        self.proxy_readonly_request()

    def do_POST(self) -> None:
        self.send_error(405, "Readonly dashboard does not allow write operations")

    def do_PUT(self) -> None:
        self.send_error(405, "Readonly dashboard does not allow write operations")

    def do_PATCH(self) -> None:
        self.send_error(405, "Readonly dashboard does not allow write operations")

    def do_DELETE(self) -> None:
        self.send_error(405, "Readonly dashboard does not allow write operations")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_security_headers()
        self.end_headers()

    def proxy_readonly_request(self) -> None:
        if AUTH_REQUIRED:
            if not AUTH_USER or not AUTH_PASSWORD:
                self.send_error(503, "Readonly dashboard auth is not configured")
                return
            if not self.is_authorized():
                self.request_auth()
                return

        upstream_path = readonly_upstream_path(self.path)
        if not upstream_path:
            self.send_error(403, "Readonly dashboard path is not allowed")
            return

        upstream_method = "GET" if self.command == "HEAD" else self.command
        conn = http.client.HTTPConnection(TARGET_HOST, TARGET_PORT, timeout=30)
        try:
            conn.request(upstream_method, upstream_path, headers=self.forward_headers())
            response = conn.getresponse()
            response_body = response.read()
        except Exception as exc:
            self.send_error(502, f"Readonly dashboard upstream error: {exc}")
            return
        finally:
            conn.close()

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response_body)

    def is_authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        prefix = "Basic "
        if not header.startswith(prefix):
            return False
        try:
            decoded = base64.b64decode(header[len(prefix) :], validate=True).decode("utf-8")
        except Exception:
            return False
        expected = f"{AUTH_USER}:{AUTH_PASSWORD}"
        return hmac.compare_digest(decoded, expected)

    def request_auth(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Doubao Quant Readonly"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write("豆包 Quant authentication required.\n".encode("utf-8"))

    def forward_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS or lower in {"authorization", "host", "content-length"}:
                continue
            headers[key] = value
        headers["Host"] = f"{TARGET_HOST}:{TARGET_PORT}"
        return headers

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def readonly_upstream_path(raw_path: str) -> str:
    parsed = urlsplit(raw_path)
    path = parsed.path
    if path in {"/", "/view", "/view/"}:
        path = "/view.html"
    if path in ALLOWED_STATIC_PATHS or path in ALLOWED_API_PATHS:
        return urlunsplit(("", "", path, parsed.query, ""))
    return ""


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ReadonlyProxyHandler)
    print(
        f"豆包 Quant readonly dashboard proxy running at http://{LISTEN_HOST}:{LISTEN_PORT} "
        f"-> http://{TARGET_HOST}:{TARGET_PORT}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
