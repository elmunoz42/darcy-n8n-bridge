# DarcyIQ MCP Server Integration Guide

## Critical Requirements for DarcyIQ Compatibility

### 1. Server-Sent Events (SSE) - MANDATORY ⚠️

**DarcyIQ requires all MCP server responses to use SSE (Server-Sent Events) format.**

#### Why This Matters
- Standard JSON responses will NOT work with DarcyIQ's MCP connector
- Even if curl tests show correct JSON-RPC responses, DarcyIQ won't discover tools without SSE
- This requirement is NOT documented in most MCP examples online

#### Implementation in FastAPI

```python
from fastapi.responses import StreamingResponse
import json

async def _sse_generator(data: dict):
    """Generate SSE formatted response."""
    json_data = json.dumps(data)
    yield f"data: {json_data}\n\n"

def _sse_response(response: JSONRPCResponse) -> StreamingResponse:
    """Create SSE streaming response."""
    return StreamingResponse(
        _sse_generator(response.model_dump(exclude_none=True)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
```

#### Key Points
- Content-Type: `text/event-stream`
- Format: `data: {json}\n\n`
- Headers: no-cache, keep-alive
- **Do NOT use return type annotation** `-> StreamingResponse` in FastAPI routes (causes Pydantic errors)

### 2. Authentication Headers

DarcyIQ supports these authentication patterns:
- `X-API-Key: <token>` (recommended)
- `api_key: <token>` (alternative)
- **NOT** `Authorization: Bearer <token>`

Case-insensitive header matching is recommended:

```python
async def require_api_key(request: Request):
    headers_lower = {k.lower(): v for k, v in request.headers.items()}
    api_key = headers_lower.get("x-api-key") or headers_lower.get("api_key")
    if not api_key or api_key != settings.mcp_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
```

### 3. MCP Protocol Response Formats

#### Initialize Response
**CRITICAL**: Return direct object, NOT wrapped in text content

```python
# ✅ CORRECT
result = {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "ServerName", "version": "1.0.0"}
}
return _sse_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result))

# ❌ WRONG - Don't wrap in as_mcp_text()
result = as_mcp_text(format_json({...}))  # This breaks handshake
```

#### Tools/List Response
Return array of tool definitions with `inputSchema`:

```python
# ✅ CORRECT
result = {
    "tools": [
        {
            "name": "tool_name",
            "description": "Tool description",
            "inputSchema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    ]
}
```

#### Tools/Call Response
Wrap results in MCP text content:

```python
result = as_mcp_text(format_json(data))
return _sse_response(JSONRPCResponse.success(response_id=rpc_request.id, result=result.model_dump()))
```

## n8n-Specific Issues

### Pagination Parameters

n8n REST API uses **cursor-based pagination**, not offset:

```python
# ✅ CORRECT for n8n
params = {"limit": 50}
if cursor:
    params["cursor"] = cursor

# ❌ WRONG
params = {"limit": 50, "offset": 0}  # Will return "Unknown query parameter 'offset'"
```

### API Endpoints

```
GET  /api/v1/workflows       - List workflows (cursor, limit, active)
GET  /api/v1/workflows/{id}  - Get workflow details
POST /api/v1/workflows/{id}/run - Execute workflow
GET  /api/v1/executions      - List executions (cursor, limit, workflowId)
GET  /api/v1/executions/{id} - Get execution details
```

## Debugging Checklist

When DarcyIQ can't discover tools:

1. ✅ Check service logs show `initialize` request
2. ✅ Verify `tools/list` is being called (if not, initialize response is wrong)
3. ✅ Confirm Content-Type is `text/event-stream`
4. ✅ Verify response format starts with `data: {json}\n\n`
5. ✅ Check initialize returns direct object, not wrapped text
6. ✅ Ensure tool definitions have `inputSchema` not `input_schema`
7. ✅ Test with curl showing verbose headers (`curl -v`)

## Testing with curl

```bash
# Test SSE format
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_KEY' \
  https://your-server.com/mcp/ \
  -d '{"jsonrpc":"2.0","id":"test","method":"tools/list"}' \
  -v

# Should see:
# < Content-Type: text/event-stream; charset=utf-8
# data: {"jsonrpc":"2.0",...}
```

## Common Errors

### "Unknown query parameter 'offset'"
- **Cause**: Using offset pagination with n8n API
- **Fix**: Change to cursor-based pagination

### DarcyIQ only sees some tools
- **Cause**: Missing SSE format
- **Fix**: Convert all responses to StreamingResponse with text/event-stream

### Initialize succeeds but no tools/list call
- **Cause**: Initialize response wrapped in as_mcp_text()
- **Fix**: Return direct object for initialize

### "PydanticUndefinedAnnotation: name 'StreamingResponse' is not defined"
- **Cause**: Return type annotation on async endpoint
- **Fix**: Remove `-> StreamingResponse` from function signature

## Project Structure

```
app/
├── main.py          # FastAPI app with SSE responses
├── mcp_models.py    # JSON-RPC request/response models
├── n8n_client.py    # n8n REST API client (cursor pagination)
├── n8n_tools.py     # MCP tool registry and handlers
├── auth.py          # API key validation
├── settings.py      # Pydantic settings
├── tracking.py      # Execution tracking
└── utils.py         # Helper functions

systemd/
└── service-name.service  # Systemd unit file

.env                 # Environment variables
requirements.txt     # Python dependencies
```

## Deployment Notes

### Nginx Configuration
When proxying MCP server behind nginx, disable buffering for SSE:

```nginx
location /mcp-path/ {
    proxy_pass http://127.0.0.1:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_buffering off;  # Critical for SSE
    proxy_cache off;
}
```

### Systemd Service
```ini
[Unit]
Description=MCP Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/project
Environment="PATH=/path/to/project/.venv/bin"
ExecStart=/path/to/project/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

## Environment Variables

```bash
MCP_API_KEY=your_secret_key
N8N_BASE_URL=http://localhost:5678
N8N_API_KEY=your_n8n_api_key
N8N_WORKFLOW_ALLOWLIST=workflow_id1,workflow_id2  # Optional
HTTP_TIMEOUT_SECONDS=30
```

## Key Lessons Learned

1. **DarcyIQ requires SSE** - Not obvious from documentation or examples
2. **Initialize response format matters** - Direct object vs wrapped text determines if tools/list gets called
3. **n8n uses cursor pagination** - Not offset-based like many other APIs
4. **FastAPI type annotations** - StreamingResponse in return type causes Pydantic errors
5. **Nginx buffering** - Must be disabled for SSE to work through reverse proxy

---

**Last Updated**: January 2026  
**Tested With**: DarcyIQ MCP Connector, n8n v1.x, FastAPI 0.110.2
