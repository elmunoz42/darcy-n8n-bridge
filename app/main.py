from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import json as json_lib
import asyncio

from .auth import require_api_key
from .mcp_models import JSONRPCRequest, JSONRPCResponse, ToolCallParams
from .n8n_client import N8NClient
from .n8n_tools import N8NToolRegistry
from .settings import get_settings
from .tracking import RunTracker
from .utils import ToolExecutionError, as_mcp_text, format_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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

# Initialize FastAPI app
app = FastAPI(
    title="n8nMCP",
    description="Model Context Protocol server for n8n workflow automation",
    version="1.0.0"
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - restrict to trusted domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://darcyiq.com",
        "https://app.darcyiq.com",
        # Add other trusted domains as needed
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "api_key"],
)


def _jsonrpc_response(response: JSONRPCResponse) -> JSONResponse:
    return JSONResponse(content=response.model_dump(exclude_none=True))


async def _sse_generator(data: dict):
    """Generate SSE formatted response."""
    json_data = json_lib.dumps(data)
    yield f"data: {json_data}\n\n"


def _sse_response(response: JSONRPCResponse) -> StreamingResponse:
    """Create SSE streaming response."""
    return StreamingResponse(
        _sse_generator(response.model_dump(exclude_none=True)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/")
async def root_get():
    """Root endpoint info - GET requests."""
    return {
        "service": "n8nMCP",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/health",
            "mcp_protocol": "POST / with JSON-RPC 2.0",
            "description": "Model Context Protocol server for n8n workflow automation"
        },
        "available_tools": [
            "n8n_list_workflows",
            "n8n_get_workflow",
            "n8n_run_workflow",
            "n8n_list_executions",
            "n8n_get_execution",
            "darcy_tracking_list"
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "n8nMCP"
    }


@app.post("/")
@limiter.limit("60/minute")
async def handle_mcp(request: Request, _: str = Depends(require_api_key)):
    try:
        raw_payload: Dict[str, Any] = await request.json()
        logger.info(f"[MCP] Received request: {raw_payload}")
    except ValueError:
        response = JSONRPCResponse.failure(response_id=None, code=-32700, message="Parse error: invalid JSON")
        return _sse_response(response)

    if not isinstance(raw_payload, dict):
        response = JSONRPCResponse.failure(response_id=None, code=-32600, message="Invalid request payload")
        return _sse_response(response)

    try:
        rpc_request = JSONRPCRequest(**raw_payload)
    except ValidationError as exc:
        logger.debug("JSON-RPC validation failed: %s", exc)
        response = JSONRPCResponse.failure(response_id=raw_payload.get("id"), code=-32600, message="Invalid JSON-RPC request")
        return _sse_response(response)

    if rpc_request.method == "initialize":
        logger.info("[MCP] Initialize request received")
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "n8nMCP",
                "version": "1.0.0"
            }
        }
        return _sse_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result))

    if rpc_request.method == "tools/list":
        logger.info("[MCP] Tools list request received")
        tools = registry.list_tools()
        logger.info(f"[MCP] Found {len(tools)} tools")
        # Transform to MCP tools list format matching WordPress MCP server
        tools_list = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["input_schema"]
            }
            for tool in tools
        ]
        result = {"tools": tools_list}
        logger.info(f"[MCP] Returning tools/list response with {len(tools_list)} tools")
        response = JSONRPCResponse.success(response_id=rpc_request.id, result=result)
        logger.info(f"[MCP] Response: {response.model_dump()}")
        return _sse_response(response)

    if rpc_request.method == "tools/call":
        try:
            params = ToolCallParams.model_validate(rpc_request.params)
        except ValidationError as exc:
            logger.debug("tools/call params validation failed: %s", exc)
            response = JSONRPCResponse.failure(response_id=rpc_request.id, code=-32602, message="Invalid tools/call params")
            return _sse_response(response)

        logger.info(f"[MCP] Tool call: {params.name} with arguments: {params.arguments}")

        try:
            result = await registry.call_tool(params.name, params.arguments)
        except ToolExecutionError as exc:
            logger.warning(f"[MCP] Tool execution failed for {params.name}: {exc}")
            error_message = f"Tool execution failed: {exc}"
            result = as_mcp_text(error_message)
            return _sse_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while running tool %s", params.name)
            result = as_mcp_text("Unexpected server error while running tool")
            return _sse_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))

        logger.info(f"[MCP] Tool {params.name} executed successfully")
        return _sse_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))

    response = JSONRPCResponse.failure(
        response_id=rpc_request.id,
        code=-32601,
        message=f"Method not found: {rpc_request.method}",
    )
    return _sse_response(response)
