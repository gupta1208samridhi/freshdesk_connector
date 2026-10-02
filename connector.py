"""Read-only Freshdesk API client and ticket connector (standard library only)."""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ConnectorError(Exception):
    """Safe, user-facing connector error."""


class NotFoundError(ConnectorError):
    pass


class RateLimitError(ConnectorError):
    pass


class UpstreamError(ConnectorError):
    pass


@dataclass
class FreshdeskClient:
    domain: str
    api_key: str
    timeout: float = 15.0
    max_retries: int = 2
    opener: Callable[..., Any] = urlopen
    sleeper: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        self.domain = self.domain.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,61}[a-z0-9]", self.domain):
            raise ValueError("FRESHDESK_DOMAIN must be a Freshdesk subdomain only")
        if not self.api_key or not self.api_key.strip():
            raise ValueError("FRESHDESK_API_KEY is required")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5")
        self.base_url = f"https://{self.domain}.freshdesk.com/api/v2"

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Invalid API path")
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}/{path}{query}"
        token = base64.b64encode(f"{self.api_key}:X".encode("utf-8")).decode("ascii")
        headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
        for attempt in range(self.max_retries + 1):
            request = Request(url, headers=headers, method="GET")
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 404:
                    raise NotFoundError("Freshdesk ticket was not found") from None
                if exc.code == 429:
                    if attempt >= self.max_retries:
                        raise RateLimitError("Freshdesk rate limit reached; retry later") from None
                    delay = _retry_after(exc.headers.get("Retry-After"), fallback=2**attempt)
                    self.sleeper(delay)
                    continue
                if exc.code in (500, 502, 503, 504) and attempt < self.max_retries:
                    self.sleeper(min(2**attempt, 8))
                    continue
                if exc.code in (401, 403):
                    raise ConnectorError("Freshdesk authentication or permission check failed") from None
                raise UpstreamError(f"Freshdesk returned HTTP {exc.code}") from None
            except (TimeoutError, URLError):
                if attempt >= self.max_retries:
                    raise UpstreamError("Could not reach Freshdesk after bounded retries") from None
                self.sleeper(min(2**attempt, 8))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise UpstreamError("Freshdesk returned an invalid JSON response") from None
        raise UpstreamError("Freshdesk request failed")


def _retry_after(value: str | None, fallback: int) -> int:
    try:
        return max(1, min(int(value or fallback), 30))
    except (TypeError, ValueError):
        return max(1, min(fallback, 30))


TICKET_FIELDS = (
    "id",
    "subject",
    "description_text",
    "status",
    "priority",
    "type",
    "created_at",
    "updated_at",
    "requester_id",
    "responder_id",
    "group_id",
    "tags",
    "due_by",
)


def safe_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Allowlist fields; omit email addresses, attachment URLs, and arbitrary fields."""
    safe = {key: ticket[key] for key in TICKET_FIELDS if key in ticket}
    description = safe.get("description_text")
    if isinstance(description, str) and len(description) > 4000:
        safe["description_text"] = description[:4000] + "… [truncated]"
    return safe


class FreshdeskConnector:
    def __init__(self, client: FreshdeskClient):
        self.client = client

    def list_tickets(self, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        _validate_page(page)
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        tickets = self.client.get("tickets", {"page": page, "per_page": per_page})
        if not isinstance(tickets, list):
            raise UpstreamError("Freshdesk returned an unexpected ticket list")
        return {"tickets": [safe_ticket(t) for t in tickets], "page": page, "per_page": per_page}

    def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        _validate_id(ticket_id)
        ticket = self.client.get(f"tickets/{ticket_id}")
        if not isinstance(ticket, dict):
            raise UpstreamError("Freshdesk returned an unexpected ticket")
        return safe_ticket(ticket)

    def search_tickets(self, query: str, page: int = 1) -> dict[str, Any]:
        _validate_page(page)
        if not isinstance(query, str) or not query.strip() or len(query) > 512:
            raise ValueError("query must contain 1–512 characters")
        response = self.client.get("search/tickets", {"query": query.strip(), "page": page})
        if not isinstance(response, dict) or not isinstance(response.get("results"), list):
            raise UpstreamError("Freshdesk returned an unexpected search response")
        return {
            "results": [safe_ticket(t) for t in response["results"]],
            "total": response.get("total"),
            "page": page,
        }


def _validate_page(page: int) -> None:
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= 10000:
        raise ValueError("page must be between 1 and 10000")


def _validate_id(ticket_id: int) -> None:
    if not isinstance(ticket_id, int) or isinstance(ticket_id, bool) or ticket_id <= 0:
        raise ValueError("ticket_id must be a positive integer")

