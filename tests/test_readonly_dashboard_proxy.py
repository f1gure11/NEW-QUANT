from __future__ import annotations

import unittest

from readonly_dashboard_proxy import readonly_auth_enabled, readonly_upstream_path


class ReadonlyDashboardProxyTest(unittest.TestCase):
    def test_view_paths_map_to_readonly_page(self) -> None:
        self.assertEqual(readonly_upstream_path("/"), "/view.html")
        self.assertEqual(readonly_upstream_path("/view"), "/view.html")
        self.assertEqual(readonly_upstream_path("/view/"), "/view.html")

    def test_allows_only_read_api_paths(self) -> None:
        self.assertEqual(readonly_upstream_path("/api/portfolio/latest"), "/api/portfolio/latest")
        self.assertEqual(readonly_upstream_path("/api/snapshot?instId=BEAT-USDT-SWAP"), "")
        self.assertEqual(readonly_upstream_path("/api/bot/status"), "")
        self.assertEqual(readonly_upstream_path("/api/re-bot/config"), "")
        self.assertEqual(readonly_upstream_path("/api/eth-bot/status"), "")
        self.assertEqual(readonly_upstream_path("/api/bot/stop"), "")
        self.assertEqual(readonly_upstream_path("/api/trade/order"), "")

    def test_allows_only_view_static_assets(self) -> None:
        self.assertEqual(readonly_upstream_path("/view.js"), "/view.js")
        self.assertEqual(readonly_upstream_path("/view.css"), "/view.css")
        self.assertEqual(readonly_upstream_path("/app.js"), "")
        self.assertEqual(readonly_upstream_path("/index.html"), "")

    def test_auth_is_optional_by_default(self) -> None:
        self.assertFalse(readonly_auth_enabled(None))
        self.assertFalse(readonly_auth_enabled(""))
        self.assertFalse(readonly_auth_enabled("false"))
        self.assertTrue(readonly_auth_enabled("true"))
        self.assertTrue(readonly_auth_enabled("1"))


if __name__ == "__main__":
    unittest.main()
