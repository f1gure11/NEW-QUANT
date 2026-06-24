from __future__ import annotations

import base64
import hmac
import http.client
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


LISTEN_HOST = os.getenv("DASHBOARD_PROXY_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("DASHBOARD_PROXY_PORT", "8766"))
TARGET_HOST = os.getenv("DASHBOARD_TARGET_HOST", "127.0.0.1")
TARGET_PORT = int(os.getenv("DASHBOARD_TARGET_PORT", "8765"))
AUTH_USER = os.getenv("DASHBOARD_AUTH_USER", "")
AUTH_PASSWORD = os.getenv("DASHBOARD_AUTH_PASSWORD", "")

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


class AuthProxyHandler(BaseHTTPRequestHandler):
    server_version = "OKXDashboardAuthProxy/0.1"

    def do_GET(self) -> None:
        self.proxy_request()

    def do_HEAD(self) -> None:
        self.proxy_request()

    def do_POST(self) -> None:
        self.proxy_request()

    def do_OPTIONS(self) -> None:
        self.proxy_request()

    def proxy_request(self) -> None:
        if not AUTH_USER or not AUTH_PASSWORD:
            self.send_error(503, "Dashboard proxy auth is not configured")
            return
        if not self.is_authorized():
            self.request_auth()
            return

        body = self.read_body()
        headers = self.forward_headers(body)
        conn = http.client.HTTPConnection(TARGET_HOST, TARGET_PORT, timeout=30)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
            response_body = response.read()
        except Exception as exc:
            self.send_error(502, f"Dashboard proxy upstream error: {exc}")
            return
        finally:
            conn.close()

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() in HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
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
        self.send_header("WWW-Authenticate", 'Basic realm="OKX Quant Dashboard"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authentication required.\n")

    def read_body(self) -> bytes | None:
        length = self.headers.get("Content-Length")
        if not length:
            return None
        try:
            size = int(length)
        except ValueError:
            return None
        return self.rfile.read(size) if size > 0 else None

    def forward_headers(self, body: bytes | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in self.headers.items():
            lower = key.lower()
            if lower in HOP_BY_HOP_HEADERS or lower in {"authorization", "host", "content-length"}:
                continue
            headers[key] = value
        headers["Host"] = f"{TARGET_HOST}:{TARGET_PORT}"
        if body is not None:
            headers["Content-Length"] = str(len(body))
        return headers

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), AuthProxyHandler)
    print(
        f"OKX dashboard auth proxy running at http://{LISTEN_HOST}:{LISTEN_PORT} "
        f"-> http://{TARGET_HOST}:{TARGET_PORT}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
