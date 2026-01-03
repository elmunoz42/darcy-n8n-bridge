from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from .n8n_client import N8NClient, N8NClientError
from .mcp_models import MCPResult
from .tracking import RunTracker
from .utils import ToolExecutionError, as_mcp_text, format_json


class ListWorkflowsArgs(BaseModel):
    limit: int = Field(50, ge=1, le=200)
    cursor: Optional[str] = None
    active: Optional[bool] = None

    model_config = {"extra": "forbid"}


class GetWorkflowArgs(BaseModel):
    workflow_id: str

    model_config = {"extra": "forbid"}


class RunWorkflowArgs(BaseModel):
    workflow_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    track: bool = True

    model_config = {"extra": "forbid"}


class ListExecutionsArgs(BaseModel):
    limit: int = Field(20, ge=1, le=200)
    cursor: Optional[str] = None
    workflow_id: Optional[str] = None

    model_config = {"extra": "forbid"}


class GetExecutionArgs(BaseModel):
    execution_id: str

    model_config = {"extra": "forbid"}


class EmptyArgs(BaseModel):
    model_config = {"extra": "forbid"}


TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "n8n_list_workflows",
        "description": "List n8n workflows using pagination and optional active filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                "cursor": {"type": ["string", "null"], "default": None},
                "active": {"type": ["boolean", "null"], "default": None},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "n8n_get_workflow",
        "description": "Retrieve a single workflow by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"workflow_id": {"type": "string"}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "n8n_run_workflow",
        "description": "Run a workflow with an optional payload and optional tracking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "payload": {"type": "object", "default": {}},
                "track": {"type": "boolean", "default": True},
            },
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "n8n_list_executions",
        "description": "List executions with pagination and optional workflow filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
                "cursor": {"type": ["string", "null"], "default": None},
                "workflow_id": {"type": ["string", "null"], "default": None},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "n8n_get_execution",
        "description": "Retrieve execution details by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"execution_id": {"type": "string"}},
            "required": ["execution_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "darcy_tracking_list",
        "description": "List executions started through this bridge during the current runtime.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


class N8NToolRegistry:
    def __init__(
        self,
        *,
        client: N8NClient,
        tracker: RunTracker,
        allowlist: Optional[Set[str]],
    ) -> None:
        self._client = client
        self._tracker = tracker
        self._allowlist = allowlist
        self._tool_handlers = {
            "n8n_list_workflows": self._handle_list_workflows,
            "n8n_get_workflow": self._handle_get_workflow,
            "n8n_run_workflow": self._handle_run_workflow,
            "n8n_list_executions": self._handle_list_executions,
            "n8n_get_execution": self._handle_get_execution,
            "darcy_tracking_list": self._handle_tracking_list,
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        return TOOL_DEFINITIONS

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> MCPResult:
        handler = self._tool_handlers.get(name)
        if not handler:
            raise ToolExecutionError(f"Unknown tool: {name}")
        try:
            return await handler(arguments)
        except N8NClientError as exc:
            message = self._friendly_error_message(exc, tool=name)
            raise ToolExecutionError(message) from exc

    async def _handle_list_workflows(self, arguments: Dict[str, Any]) -> MCPResult:
        args = ListWorkflowsArgs(**arguments)
        payload = await self._client.list_workflows(limit=args.limit, cursor=args.cursor, active=args.active)
        filtered = self._filter_workflows(payload)
        return as_mcp_text(format_json(filtered))

    async def _handle_get_workflow(self, arguments: Dict[str, Any]) -> MCPResult:
        args = GetWorkflowArgs(**arguments)
        self._ensure_workflow_allowed(args.workflow_id)
        payload = await self._client.get_workflow(args.workflow_id)
        return as_mcp_text(format_json(payload))

    async def _handle_run_workflow(self, arguments: Dict[str, Any]) -> MCPResult:
        args = RunWorkflowArgs(**arguments)
        self._ensure_workflow_allowed(args.workflow_id)
        payload = await self._client.run_workflow(args.workflow_id, args.payload)
        execution_id = self._extract_execution_id(payload)
        if args.track:
            await self._tracker.add_entry(
                workflow_id=args.workflow_id,
                execution_id=execution_id,
                payload=args.payload,
            )
        return as_mcp_text(format_json(payload))

    async def _handle_list_executions(self, arguments: Dict[str, Any]) -> Any:
        args = ListExecutionsArgs(**arguments)
        if self._allowlist and args.workflow_id and args.workflow_id not in self._allowlist:
            raise ToolExecutionError("Workflow is not permitted by the allowlist")
        payload = await self._client.list_executions(
            limit=args.limit,
            cursor=args.cursor,
            workflow_id=args.workflow_id,
        )
        filtered = self._filter_executions(payload)
        return as_mcp_text(format_json(filtered))

    async def _handle_get_execution(self, arguments: Dict[str, Any]) -> MCPResult:
        args = GetExecutionArgs(**arguments)
        payload = await self._client.get_execution(args.execution_id)
        workflow_id = self._extract_workflow_id_from_execution(payload)
        if self._allowlist and workflow_id and workflow_id not in self._allowlist:
            raise ToolExecutionError("Execution belongs to a workflow outside the allowlist")
        return as_mcp_text(format_json(payload))

    async def _handle_tracking_list(self, arguments: Dict[str, Any]) -> MCPResult:
        _ = EmptyArgs(**arguments)
        entries = await self._tracker.list_entries()
        formatted = [
            {
                "workflow_id": entry.workflow_id,
                "execution_id": entry.execution_id,
                "payload": entry.payload,
                "started_at": entry.started_at.isoformat(),
            }
            for entry in entries
        ]
        return as_mcp_text(format_json(formatted))

    def _ensure_workflow_allowed(self, workflow_id: str) -> None:
        if self._allowlist and workflow_id not in self._allowlist:
            raise ToolExecutionError("Workflow is not permitted by the allowlist")

    def _filter_workflows(self, payload: Any) -> Any:
        if not self._allowlist:
            return payload
        if isinstance(payload, list):
            return [item for item in payload if self._is_allowed_workflow(item)]
        if isinstance(payload, dict):
            cloned = dict(payload)
            for key in ("data", "workflows", "items"):
                value = cloned.get(key)
                if isinstance(value, list):
                    filtered_items = [item for item in value if self._is_allowed_workflow(item)]
                    cloned[key] = filtered_items
                    self._update_counts(cloned, len(filtered_items))
            return cloned
        return payload

    def _filter_executions(self, payload: Any) -> Any:
        if not self._allowlist:
            return payload
        if isinstance(payload, list):
            return [item for item in payload if self._is_allowed_execution(item)]
        if isinstance(payload, dict):
            cloned = dict(payload)
            for key in ("data", "executions", "items"):
                value = cloned.get(key)
                if isinstance(value, list):
                    filtered_items = [item for item in value if self._is_allowed_execution(item)]
                    cloned[key] = filtered_items
                    self._update_counts(cloned, len(filtered_items))
            return cloned
        return payload

    def _update_counts(self, payload: Dict[str, Any], length: int) -> None:
        for key in ("count", "total", "totalCount"):
            value = payload.get(key)
            if isinstance(value, int):
                payload[key] = length

    def _is_allowed_workflow(self, item: Any) -> bool:
        if self._allowlist is None:
            return True
        workflow_id = None
        if isinstance(item, dict):
            workflow_id = item.get("id") or item.get("workflowId") or item.get("_id")
        if workflow_id is None:
            return False
        return str(workflow_id) in self._allowlist

    def _is_allowed_execution(self, item: Any) -> bool:
        if self._allowlist is None:
            return True
        if not isinstance(item, dict):
            return False
        workflow_id = item.get("workflowId") or item.get("workflow_id")
        if workflow_id is None:
            return False
        return str(workflow_id) in self._allowlist

    def _extract_execution_id(self, payload: Any) -> Optional[str]:
        if isinstance(payload, dict):
            for key in ("executionId", "execution_id", "id"):
                value = payload.get(key)
                if value is not None:
                    return str(value)
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("executionId", "id"):
                    value = data.get(key)
                    if value is not None:
                        return str(value)
        return None

    def _extract_workflow_id_from_execution(self, payload: Any) -> Optional[str]:
        if isinstance(payload, dict):
            value = payload.get("workflowId") or payload.get("workflow_id")
            if value is not None:
                return str(value)
            data = payload.get("data")
            if isinstance(data, dict):
                inner_value = data.get("workflowId") or data.get("workflow_id")
                if inner_value is not None:
                    return str(inner_value)
        return None

    def _friendly_error_message(self, error: N8NClientError, *, tool: str) -> str:
        base = str(error.args[0]) if error.args else "n8n client error"
        if error.status_code == 400:
            message_lower = base.lower()
            if "trigger" in message_lower:
                return "n8n rejected the run: the workflow is missing a trigger node."
            return f"n8n returned a bad request for {tool}: {base}"
        if error.status_code == 401:
            return "n8n API rejected the credentials"
        if error.status_code == 403:
            return "n8n API denied access to this resource"
        if error.status_code == 404:
            return "Requested resource was not found in n8n"
        if error.status_code == 0:
            return "Unable to reach n8n API"
        return f"n8n error {error.status_code}: {base}"
