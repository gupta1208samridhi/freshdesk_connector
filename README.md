# Freshdesk read-only agent connector

This project implements **Assignment 3: Build a private connector for a merchant tool**. It exposes Freshdesk ticket list, get, and search operations as MCP tools over stdio. The connector is read-only and uses only Python's standard library.

## What it can do

- List tickets with bounded pagination.
- Get one ticket by ID.
- Search tickets with Freshdesk's native search syntax.
- Return a small allowlist of ticket fields to the agent. Descriptions are capped at 4,000 characters; contact email addresses and attachment URLs are omitted.
- Use Freshdesk API-key authentication and retry rate-limited or transient requests a limited number of times.

## What it cannot do

- Create, update, delete, reply to, or otherwise change tickets.
- Read conversations, attachments, contacts, or account settings.
- Bypass Freshdesk permissions. The API key has the account access granted to its Freshdesk user; use a dedicated least-privilege account where possible.
- Guarantee a search returns every matching ticket. Freshdesk search has its own query syntax, indexing behavior, and result limits.

The connector does not retain ticket data. In live mode, the agent host receives the selected fields when it calls a tool. Review your organization's data-handling rules before connecting real accounts.

## Requirements

- Python 3.10 or later.
- A Freshdesk account and API key only for live mode.

No Python packages need to be installed.

## Run the offline end-to-end demo

From this directory:

```bash
python server.py
```

The server starts in offline demo mode by default and loads ten fictional tickets. Connect it to an MCP host using stdio, then call `freshdesk_list_tickets`, `freshdesk_get_ticket`, or `freshdesk_search_tickets`. The included test also starts this server as a subprocess and exercises MCP initialization, tool discovery, and tool calls.

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Connect a real Freshdesk account

Set the following environment variables in the MCP host configuration. Do not commit credentials or put them in this repository.

```bash
export FRESHDESK_DEMO_MODE=false
export FRESHDESK_DOMAIN=your-company
export FRESHDESK_API_KEY=your-api-key
python server.py
```

`FRESHDESK_DOMAIN` is the Freshdesk subdomain only, such as `acme` for `https://acme.freshdesk.com`. The connector rejects non-Freshdesk hosts and always uses HTTPS.

Example MCP host configuration (adjust the path for your machine):

```json
{
  "mcpServers": {
    "freshdesk-readonly": {
      "command": "python",
      "args": ["/absolute/path/to/razorpay_freshdesk_connector/server.py"],
      "env": {
        "FRESHDESK_DEMO_MODE": "false",
        "FRESHDESK_DOMAIN": "your-company",
        "FRESHDESK_API_KEY": "${FRESHDESK_API_KEY}"
      }
    }
  }
}
```

Some MCP hosts do not expand environment-variable references inside JSON. In that case, configure the secret through the host's secure environment settings.

## Tools

### `freshdesk_list_tickets`

Inputs: `page` (1–10000, default 1), `per_page` (1–100, default 20).

### `freshdesk_get_ticket`

Inputs: `ticket_id` (positive integer).

### `freshdesk_search_tickets`

Inputs: `query` (Freshdesk search query, 1–512 characters), `page` (1–10000, default 1).

Example query: `status:2 AND priority:4`. Freshdesk expects ticket search predicates and may impose indexing and result-window constraints. Use the syntax supported by your Freshdesk plan.

## Authentication and rate limits

The live connector sends the API key using HTTP Basic authentication with the API key as username and `X` as password, as documented by Freshdesk. It honors `Retry-After` on HTTP 429 responses and retries a bounded number of transient 5xx responses. It does not attempt unbounded retries or a shared account-wide rate limiter; production deployments should add a centralized limiter if multiple workers share the Freshdesk account.

## Tests and evaluation

The standard-library test suite covers authentication headers, URL encoding, pagination bounds, field filtering, 404 handling, `Retry-After` behavior, search, and a full offline MCP stdio round-trip. All test tickets are fictional; no API key or customer data is included.

## References

- [Freshdesk API v2 documentation](https://developers.freshdesk.com/api/)
- [Model Context Protocol specification](https://modelcontextprotocol.io/specification/)

## Assumptions and long-term improvements

- This submission uses a Freshdesk API key because the assignment permits an API-key flow. For a multi-merchant product, replace per-user static keys with OAuth, tenant-scoped secret storage, rotation, and an audited authorization layer.
- The MCP stdio implementation intentionally supports only initialization, tool discovery, and tool calls needed for this connector. For a production deployment, use the official MCP SDK, add structured observability without logging ticket bodies, and integration-test against a Freshdesk sandbox.
- Permissions and available fields depend on the Freshdesk account and API key. The connector fails closed on non-HTTPS and non-Freshdesk domains.
