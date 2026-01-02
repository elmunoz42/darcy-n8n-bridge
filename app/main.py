from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .auth import require_api_key
from .mcp_models import JSONRPCRequest, JSONRPCResponse, ToolCallParams
from .n8n_client import N8NClient
from .n8n_tools import N8NToolRegistry
from .settings import get_settings
from .tracking import RunTracker
from .utils import ToolExecutionError, as_mcp_text, format_json

logger = logging.getLogger("darcyiq_n8n_bridge")

settings = get_settings()
tracker = RunTracker()
n8n_client = N8NClient(
    base_url=settings.n8n_base_url,
    api_key=settings.n8n_api_key,
    timeout_seconds=settings.http_timeout_seconds,
)
registry = N8NToolRegistry(
    client=n8n_client,
    tracker=tracker,
    allowlist=settings.n8n_workflow_allowlist,
)

app = FastAPI(title="DarcyIQ n8n MCP Bridge", version="1.0.0")


def _jsonrpc_response(response: JSONRPCResponse) -> JSONResponse:
    return JSONResponse(content=response.model_dump(exclude_none=True))


@app.post("/")
async def handle_mcp(request: Request, _: str = Depends(require_api_key)) -> JSONResponse:
    try:
        raw_payload: Dict[str, Any] = await request.json()
    except ValueError:
        response = JSONRPCResponse.failure(response_id=None, code=-32700, message="Parse error: invalid JSON")
        return _jsonrpc_response(response)

    if not isinstance(raw_payload, dict):
        response = JSONRPCResponse.failure(response_id=None, code=-32600, message="Invalid request payload")
        return _jsonrpc_response(response)

    try:
        rpc_request = JSONRPCRequest(**raw_payload)
    except ValidationError as exc:
        logger.debug("JSON-RPC validation failed: %s", exc)
        response = JSONRPCResponse.failure(response_id=raw_payload.get("id"), code=-32600, message="Invalid JSON-RPC request")
        return _jsonrpc_response(response)

    if rpc_request.method == "initialize":
        result = as_mcp_text(
            format_json(
                {
                    "name": "DarcyIQ n8n MCP Bridge",
                    "version": "1.0.0",
                    "capabilities": {"streaming": False},
                }
            )
        )
        return _jsonrpc_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))

    if rpc_request.method == "tools/list":
        tools = registry.list_tools()
        result = as_mcp_text(format_json(tools))
        return _jsonrpc_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))

    if rpc_request.method == "tools/call":
        try:
            params = ToolCallParams.model_validate(rpc_request.params)
        except ValidationError as exc:
            logger.debug("tools/call params validation failed: %s", exc)
            response = JSONRPCResponse.failure(response_id=rpc_request.id, code=-32602, message="Invalid tools/call params")
            return _jsonrpc_response(response)
        try:
            result = await registry.call_tool(params.name, params.arguments)
        except ToolExecutionError as exc:
            error_message = f"Tool execution failed: {exc}"
            result = as_mcp_text(error_message)
            return _jsonrpc_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while running tool %s", params.name)
            result = as_mcp_text("Unexpected server error while running tool")
            return _jsonrpc_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))
        return _jsonrpc_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))

    response = JSONRPCResponse.failure(
        response_id=rpc_request.id,
        code=-32601,
        message=f"Method not found: {rpc_request.method}",
    )
    return _jsonrpc_response(response)
