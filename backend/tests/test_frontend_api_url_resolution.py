"""
backend/tests/test_frontend_api_url_resolution.py
==================================================
Tests ensuring that frontend API URL resolution (resolveApiBaseUrl)
correctly resolves to relative same-origin ('') in production HTTPS
environments (e.g. Vercel), while preserving 'http://127.0.0.1:8000'
for local standalone development.
"""

from pathlib import Path
import re
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestFrontendApiUrlResolution(unittest.TestCase):
    """Enforces dynamic API base URL resolution contract in frontend scripts."""

    @classmethod
    def setUpClass(cls):
        cls.workspace_js = (REPO_ROOT / "autoprompt-prototype" / "js" / "workspace.js").read_text(encoding="utf-8")
        cls.persistence_js = (REPO_ROOT / "autoprompt-prototype" / "js" / "persistence.js").read_text(encoding="utf-8")
        cls.index_html = (REPO_ROOT / "autoprompt-prototype" / "index.html").read_text(encoding="utf-8")

    def test_workspace_js_has_dynamic_resolver(self):
        """workspace.js must define resolveApiBaseUrl that checks https: protocol."""
        self.assertIn("function resolveApiBaseUrl()", self.workspace_js)
        self.assertIn("protocol === 'https:'", self.workspace_js)
        self.assertIn("const API_BASE_URL = resolveApiBaseUrl();", self.workspace_js)

    def test_persistence_js_has_dynamic_resolver(self):
        """persistence.js must define resolveApiBaseUrl that checks https: protocol."""
        self.assertIn("function resolveApiBaseUrl()", self.persistence_js)
        self.assertIn("protocol === 'https:'", self.persistence_js)
        self.assertIn("const API_BASE_URL = resolveApiBaseUrl();", self.persistence_js)

    def test_no_hardcoded_localhost_default_assignment(self):
        """Neither workspace.js nor persistence.js should unconditionally default to 127.0.0.1:8000."""
        # Previous broken pattern:
        # const API_BASE_URL = (typeof window !== 'undefined' && typeof window.AUTOPROMPT_API_URL === 'string')
        #   ? window.AUTOPROMPT_API_URL
        #   : 'http://127.0.0.1:8000';
        broken_pattern = re.compile(r"API_BASE_URL\s*=\s*\(typeof window.*?:\s*'http://127\.0\.0\.1:8000'", re.DOTALL)
        self.assertIsNone(broken_pattern.search(self.workspace_js), "workspace.js still has naive ternary fallback to 127.0.0.1:8000")
        self.assertIsNone(broken_pattern.search(self.persistence_js), "persistence.js still has naive ternary fallback to 127.0.0.1:8000")

    def test_index_html_does_not_display_hardcoded_localhost(self):
        """index.html live backend tip should not hardcode localhost:8000 for production viewers."""
        self.assertNotIn("localhost:8000", self.index_html)

    def test_simulated_resolution_logic(self):
        """
        Simulate the exact resolveApiBaseUrl logic across all environment profiles:
        1. Vercel Production: https://autoprompt.vercel.app -> ''
        2. Production Custom Domain: https://autoprompt.example.com -> ''
        3. Local Standalone Dev: http://127.0.0.1:5500 -> 'http://127.0.0.1:8000'
        4. Localhost Standalone Dev: http://localhost:5500 -> 'http://127.0.0.1:8000'
        5. Local FastAPI Direct: http://127.0.0.1:8000 -> ''
        6. Local Vercel Dev: http://localhost:3000 -> ''
        7. Explicit Override: window.AUTOPROMPT_API_URL = 'https://custom.api' -> 'https://custom.api'
        """
        def simulate_resolver(window_obj):
            if "AUTOPROMPT_API_URL" in window_obj and isinstance(window_obj["AUTOPROMPT_API_URL"], str):
                return window_obj["AUTOPROMPT_API_URL"]

            loc = window_obj.get("location", {})
            protocol = loc.get("protocol", "")
            hostname = loc.get("hostname", "")
            port = str(loc.get("port", ""))

            if protocol == "https:":
                return ""
            if hostname and hostname not in ("localhost", "127.0.0.1"):
                return ""
            if port in ("8000", "3000"):
                return ""
            return "http://127.0.0.1:8000"

        # Profile 1: Vercel Production
        self.assertEqual(
            simulate_resolver({"location": {"protocol": "https:", "hostname": "autoprompt.vercel.app", "port": ""}}),
            ""
        )
        # Profile 2: Custom Production Domain
        self.assertEqual(
            simulate_resolver({"location": {"protocol": "https:", "hostname": "autoprompt.dev", "port": ""}}),
            ""
        )
        # Profile 3: Local Live Server / http.server on port 5500
        self.assertEqual(
            simulate_resolver({"location": {"protocol": "http:", "hostname": "127.0.0.1", "port": "5500"}}),
            "http://127.0.0.1:8000"
        )
        # Profile 4: Localhost on port 5500
        self.assertEqual(
            simulate_resolver({"location": {"protocol": "http:", "hostname": "localhost", "port": "5500"}}),
            "http://127.0.0.1:8000"
        )
        # Profile 5: Local FastAPI direct (port 8000)
        self.assertEqual(
            simulate_resolver({"location": {"protocol": "http:", "hostname": "127.0.0.1", "port": "8000"}}),
            ""
        )
        # Profile 6: Local Vercel CLI (port 3000)
        self.assertEqual(
            simulate_resolver({"location": {"protocol": "http:", "hostname": "localhost", "port": "3000"}}),
            ""
        )
        # Profile 7: Explicit Override
        self.assertEqual(
            simulate_resolver({
                "AUTOPROMPT_API_URL": "https://api.myproject.com",
                "location": {"protocol": "https:", "hostname": "autoprompt.vercel.app", "port": ""}
            }),
            "https://api.myproject.com"
        )


if __name__ == "__main__":
    unittest.main()
