# DarcyIQ ↔ n8n MCP Bridge

A FastAPI-based MCP bridge that lets DarcyIQ talk to an n8n instance using JSON-RPC over HTTP. The bridge exposes the MCP surface (`initialize`, `tools/list`, `tools/call`) and translates tool invocations into n8n REST API calls authenticated via `X-N8N-API-KEY`.

## Features
- Darcy-compatible JSON-RPC endpoint with header-based API key authentication (`X-API-Key` or `api_key`).
- Tools for listing workflows, running workflows, inspecting executions, and retrieving bridge-tracked runs.
- Configurable workflow allowlist for extra guardrails.
- Friendly error messages for common n8n problems (missing trigger nodes, auth failures, connectivity issues).
- In-memory tracker that records executions launched through the bridge.

## Requirements
- Python 3.11+
- n8n instance with REST API access and an API key (`X-N8N-API-KEY`).

## Quick Start (local)
1. Copy the sample environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and set:
   - `MCP_API_KEY`
   - `N8N_BASE_URL` (no trailing slash)
   - `N8N_API_KEY`
   - Optional: `N8N_WORKFLOW_ALLOWLIST`
3. Install dependencies and start the server:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```

The bridge listens on `POST /`. Keep the session running to accept Darcy requests.

## Docker
```bash
docker compose up --build
```
The container reads configuration from `.env` and exposes port `8080` by default.

## DarcyIQ Connector Setup
- **SSE Endpoint URL:** `https://<your-bridge-host>/`
- **HTTP Method:** `POST`
- **Auth Header:** either `X-API-Key: <MCP_API_KEY>` _or_ `api_key: <MCP_API_KEY>`
- **Content Type:** `application/json`

DarcyIQ will send JSON-RPC messages to `/`. The bridge returns MCP responses with tool output encoded as text content.

## Available Tools
| Tool | Description |
| --- | --- |
| `n8n_list_workflows` | Paginated workflow listing with optional `active` filter. |
| `n8n_get_workflow` | Retrieve a workflow by ID. |
| `n8n_run_workflow` | Execute a workflow; optionally track the run locally. |
| `n8n_list_executions` | List executions with optional workflow filter. |
| `n8n_get_execution` | Fetch execution details. |
| `darcy_tracking_list` | Show executions started through this bridge during the current runtime. |

## JSON-RPC Contract
- **Endpoint:** `POST /`
- **Methods:** `initialize`, `tools/list`, `tools/call`
- **Response shape:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": "<same as request>",
    "result": {
      "content": [
        {"type": "text", "text": "..."}
      ]
    }
  }
  ```
- **Errors:** Validation errors surface as JSON-RPC errors. Tool-level issues return a success envelope containing a readable error message in `result.content[0].text`.

## curl Examples
Replace `<bridge-url>` with your host and `<MCP_API_KEY>` with the configured key.

List tools:
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <MCP_API_KEY>" \
  https://<bridge-url>/ \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list"}'
```

List workflows:
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "api_key: <MCP_API_KEY>" \
  https://<bridge-url>/ \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"n8n_list_workflows","arguments":{"limit":10}}}'
```

Run a workflow:
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <MCP_API_KEY>" \
  https://<bridge-url>/ \
  -d '{"jsonrpc":"2.0","id":"3","method":"tools/call","params":{"name":"n8n_run_workflow","arguments":{"workflow_id":"12","payload":{"trigger":"cli"}}}}'
```

## Troubleshooting
- **401 Unauthorized:** Ensure the request includes `X-API-Key` or `api_key` exactly and that the value matches `MCP_API_KEY`.
- **Workflow missing trigger:** n8n returns HTTP 400 when a workflow lacks a trigger node. The bridge relays this as `n8n rejected the run: the workflow is missing a trigger node.` Add a trigger node or run the workflow manually from within n8n.
- **n8n connectivity errors:** Verify `N8N_BASE_URL`, network reachability, and that the n8n API key is valid. The bridge reports `Unable to reach n8n API` when the request fails at the network layer.
- **Allowlist violations:** When `N8N_WORKFLOW_ALLOWLIST` is set, only workflows in that set can be listed or invoked. Update the allowlist or remove it if you need broader access.

## Testing
```bash
pytest
```

The test suite currently covers configuration parsing and MCP result helpers. Extend the suite with integration tests against a test n8n instance as needed for your deployment.
