"""Fictional tickets used only by the offline demo and test suite."""

from __future__ import annotations

from typing import Any


TICKETS: list[dict[str, Any]] = [
    {"id": 1001, "subject": "Autopay retry failed", "description_text": "Merchant reports a failed autopay attempt; asks when the next retry occurs.", "status": 2, "priority": 3, "type": "Problem", "created_at": "2026-09-20T09:00:00Z", "updated_at": "2026-09-20T09:15:00Z", "requester_id": 501, "responder_id": 12, "group_id": 4, "tags": ["payments", "autopay"], "email": "fictional1@example.test", "attachments": [{"attachment_url": "https://invalid.example/test"}]},
    {"id": 1002, "subject": "Refund status clarification", "description_text": "Customer asks for the status of a refund.", "status": 3, "priority": 2, "type": "Question", "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:30:00Z", "requester_id": 502, "responder_id": 15, "group_id": 4, "tags": ["refund"]},
    {"id": 1003, "subject": "Webhook delivery delay", "description_text": "Events arrived later than expected in the sandbox.", "status": 2, "priority": 3, "type": "Problem", "created_at": "2026-09-21T08:00:00Z", "updated_at": "2026-09-21T08:20:00Z", "requester_id": 503, "responder_id": 12, "group_id": 5, "tags": ["webhook"]},
    {"id": 1004, "subject": "Invoice copy request", "description_text": "Merchant requests a copy of a test invoice.", "status": 4, "priority": 1, "type": "Question", "created_at": "2026-09-21T11:00:00Z", "updated_at": "2026-09-21T11:05:00Z", "requester_id": 504, "responder_id": 18, "group_id": 6, "tags": ["billing"]},
    {"id": 1005, "subject": "Payment captured twice in sandbox", "description_text": "Fictional test case asks support to review two sandbox captures.", "status": 2, "priority": 4, "type": "Problem", "created_at": "2026-09-22T07:45:00Z", "updated_at": "2026-09-22T08:10:00Z", "requester_id": 505, "responder_id": 12, "group_id": 4, "tags": ["payments", "sandbox"]},
    {"id": 1006, "subject": "Card verification question", "description_text": "Merchant asks what the verification result means.", "status": 3, "priority": 2, "type": "Question", "created_at": "2026-09-22T12:30:00Z", "updated_at": "2026-09-22T12:40:00Z", "requester_id": 506, "responder_id": 15, "group_id": 5, "tags": ["cards"]},
    {"id": 1007, "subject": "Settlement report mismatch", "description_text": "A fictional report total differs from the expected sandbox value.", "status": 2, "priority": 3, "type": "Problem", "created_at": "2026-09-23T06:20:00Z", "updated_at": "2026-09-23T06:50:00Z", "requester_id": 507, "responder_id": 18, "group_id": 6, "tags": ["settlement", "reports"]},
    {"id": 1008, "subject": "API key rotation help", "description_text": "Merchant requests guidance on rotating a sandbox key.", "status": 3, "priority": 2, "type": "Question", "created_at": "2026-09-23T14:00:00Z", "updated_at": "2026-09-23T14:15:00Z", "requester_id": 508, "responder_id": 15, "group_id": 5, "tags": ["api", "security"]},
    {"id": 1009, "subject": "Checkout page loading slowly", "description_text": "Fictional merchant reports a slow page in a test environment.", "status": 2, "priority": 3, "type": "Problem", "created_at": "2026-09-24T08:00:00Z", "updated_at": "2026-09-24T08:25:00Z", "requester_id": 509, "responder_id": 12, "group_id": 4, "tags": ["checkout"]},
    {"id": 1010, "subject": "Tax field configuration", "description_text": "Merchant asks where to configure a tax field in a demo account.", "status": 4, "priority": 1, "type": "Question", "created_at": "2026-09-24T16:10:00Z", "updated_at": "2026-09-24T16:30:00Z", "requester_id": 510, "responder_id": 18, "group_id": 6, "tags": ["configuration"]},
]


class DemoConnector:
    """In-memory connector; never makes network calls or uses customer data."""

    def list_tickets(self, page: int = 1, per_page: int = 20) -> dict[str, Any]:
        from connector import _validate_page

        _validate_page(page)
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        start = (page - 1) * per_page
        return {"tickets": TICKETS[start : start + per_page], "page": page, "per_page": per_page}

    def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        from connector import NotFoundError, _validate_id, safe_ticket

        _validate_id(ticket_id)
        for ticket in TICKETS:
            if ticket["id"] == ticket_id:
                return safe_ticket(ticket)
        raise NotFoundError("Demo ticket was not found")

    def search_tickets(self, query: str, page: int = 1) -> dict[str, Any]:
        from connector import _validate_page, safe_ticket

        _validate_page(page)
        if not isinstance(query, str) or not query.strip() or len(query) > 512:
            raise ValueError("query must contain 1–512 characters")
        term = query.strip().lower()
        matches = [
            t for t in TICKETS
            if term in t["subject"].lower()
            or term in t["description_text"].lower()
            or term in " ".join(t["tags"]).lower()
            or (term.startswith("status:") and str(t["status"]) == term.split(":", 1)[1])
        ]
        start = (page - 1) * 30
        return {"results": [safe_ticket(t) for t in matches[start : start + 30]], "total": len(matches), "page": page}
