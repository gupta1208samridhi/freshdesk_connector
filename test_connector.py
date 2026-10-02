from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connector import (  # noqa: E402
    ConnectorError,
    FreshdeskClient,
    FreshdeskConnector,
    NotFoundError,
    RateLimitError,
    safe_ticket,
)
from demo_data import DemoConnector, TICKETS  # noqa: E402
from server import TOOLS, handle_message  # noqa: E402


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class LocalHandler(BaseHTTPRequestHandler):
    requests = []
    status = 200
    headers = {}
    payload = []

    def do_GET(self):
        type(self).requests.append((self.path, self.headers.get("Authorization")))
        body = json.dumps(type(self).payload).encode()
        self.send_response(type(self).status)
        for key, value in type(self).headers.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if type(self).status != 204:
            self.wfile.write(body)

    def log_message(self, *_args):
        pass


class ConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), LocalHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        LocalHandler.requests = []
        LocalHandler.status = 200
        LocalHandler.headers = {}
        LocalHandler.payload = []

    def live_connector(self, retries=0, sleeper=lambda _seconds: None):
        client = FreshdeskClient("example", "secret-key", max_retries=retries, sleeper=sleeper)
        client.base_url = f"http://127.0.0.1:{self.server.server_port}/api/v2"
        return FreshdeskConnector(client)

    def test_auth_pagination_and_allowlist(self):
        LocalHandler.payload = [{"id": 9, "subject": "Hello", "email": "private@example.test", "attachments": [{"attachment_url": "secret"}]}]
        result = self.live_connector().list_tickets(page=2, per_page=5)
        self.assertEqual(result["tickets"], [{"id": 9, "subject": "Hello"}])
        path, auth = LocalHandler.requests[0]
        self.assertEqual(parse_qs(urlparse(path).query), {"page": ["2"], "per_page": ["5"]})
        expected = "Basic " + base64.b64encode(b"secret-key:X").decode()
        self.assertEqual(auth, expected)

    def test_search_url_encodes_query(self):
        LocalHandler.payload = {"results": [{"id": 3, "subject": "urgent"}], "total": 1}
        result = self.live_connector().search_tickets("status:2 AND priority:4", page=2)
        self.assertEqual(result["total"], 1)
        path = LocalHandler.requests[0][0]
        self.assertEqual(parse_qs(urlparse(path).query), {"query": ["status:2 AND priority:4"], "page": ["2"]})

    def test_bounds_and_domain_validation(self):
        conn = self.live_connector()
        with self.assertRaises(ValueError):
            conn.list_tickets(per_page=101)
        with self.assertRaises(ValueError):
            conn.get_ticket(0)
        with self.assertRaises(ValueError):
            conn.search_tickets("")
        with self.assertRaises(ValueError):
            FreshdeskClient("https://evil.example", "x")

    def test_404_maps_to_safe_not_found(self):
        LocalHandler.status = 404
        with self.assertRaises(NotFoundError):
            self.live_connector().get_ticket(15)

    def test_429_respects_retry_after_and_retries(self):
        LocalHandler.status = 429
        LocalHandler.headers = {"Retry-After": "3"}
        sleeps = []
        with self.assertRaises(RateLimitError):
            self.live_connector(retries=1, sleeper=sleeps.append).list_tickets()
        self.assertEqual(sleeps, [3])
        self.assertEqual(len(LocalHandler.requests), 2)

    def test_description_truncation_and_no_private_fields(self):
        ticket = safe_ticket({"id": 1, "description_text": "x" * 4100, "email": "hidden@example.test", "custom_fields": {"private": "x"}})
        self.assertTrue(ticket["description_text"].endswith("… [truncated]"))
        self.assertNotIn("email", ticket)
        self.assertNotIn("custom_fields", ticket)

    def test_demo_has_ten_fictional_records_and_search(self):
        demo = DemoConnector()
        self.assertEqual(len(TICKETS), 10)
        self.assertEqual(demo.get_ticket(1001)["id"], 1001)
        self.assertEqual(demo.search_tickets("autopay")["total"], 1)
        self.assertEqual(len(demo.list_tickets(per_page=100)["tickets"]), 10)

    def test_mcp_tools_and_errors(self):
        demo = DemoConnector()
        initialized = handle_message(demo, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "freshdesk-readonly-connector")
        listed = handle_message(demo, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual([tool["name"] for tool in listed["result"]["tools"]], [tool["name"] for tool in TOOLS])
        called = handle_message(demo, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "freshdesk_get_ticket", "arguments": {"ticket_id": 1001}}})
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(payload["id"], 1001)
        self.assertFalse(called["result"]["isError"])
        rejected = handle_message(demo, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "freshdesk_get_ticket", "arguments": {"ticket_id": 1, "write": True}}})
        self.assertTrue(rejected["result"]["isError"])

    def test_stdio_end_to_end_subprocess(self):
        root = Path(__file__).resolve().parents[1]
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "freshdesk_search_tickets", "arguments": {"query": "autopay"}}},
        ]
        proc = subprocess.run(
            [sys.executable, "server.py"], cwd=root,
            input="\n".join(json.dumps(m) for m in messages) + "\n",
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2])
        results = json.loads(responses[1]["result"]["content"][0]["text"])
        self.assertEqual(results["total"], 1)


if __name__ == "__main__":
    unittest.main()
