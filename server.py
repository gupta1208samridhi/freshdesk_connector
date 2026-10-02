"""Minimal MCP stdio server exposing read-only Freshdesk ticket tools."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from connector import ConnectorError, FreshdeskClient, FreshdeskConnector
from demo_data import DemoConnector


TOOLS = [
    {
        "name": "freshdesk_list_tickets",
        "description": "List Freshdesk tickets. Read-only; returns allowlisted fields and bounded pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {"page": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 1}, "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
    },
    {
        "name": "freshdesk_get_ticket",
        "description": "Get one Freshdesk ticket by numeric ID. Read-only; omits contact emails and attachments.",
        "inputSchema": {"type": "object", "properties": {"ticket_id": {"type": "integer", "minimum": 1}}, "required": ["ticket_id"], "additionalProperties": False},
    },
    {
        "name": "freshdesk_search_tickets",
        "description": "Search Freshdesk tickets using Freshdesk's native search query syntax. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 512}, "page": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 1}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


def build_connector() -> Any:
    if os.getenv("FRESHDESK_DEMO_MODE", "true").strip().lower() not in ("0", "false", "no"):
        return DemoConnector()
    domain = os.getenv("FRESHDESK_DOMAIN", "")
    api_key = os.getenv("FRESHDESK_API_KEY", "")
    return FreshdeskConnector(FreshdeskClient(domain=domain, api_key=api_key))


def _call_tool(connector: Any, name: str, args: dict[str, Any]) -> Any:
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")
    allowed = {
        "freshdesk_list_tickets": {"page", "per_page"},
        "freshdesk_get_ticket": {"ticket_id"},
        "freshdesk_search_tickets": {"query", "page"},
    }
    if name not in allowed:
        raise ValueError("Unknown tool")
    if set(args) - allowed[name]:
        raise ValueError("Unsupported tool argument")
    if name == "freshdesk_list_tickets":
        return connector.list_tickets(**args)
    if name == "freshdesk_get_ticket":
        return connector.get_ticket(**args)
    return connector.search_tickets(**args)


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def handle_message(connector: Any, message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        requested = params.get("protocolVersion", "2024-11-05")
        return _response(request_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "freshdesk-readonly-connector", "version": "1.0.0"},
        })
    if method == "ping":
        return _response(request_id, {})
    if method == "tools/list":
        return _response(request_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            result = _call_tool(connector, name, arguments)
            return _response(request_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False})
        except (ConnectorError, ValueError, TypeError) as exc:
            return _response(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}


def main() -> None:
    try:
        connector = build_connector()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                continue
            response = handle_message(connector, message)
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    main()
