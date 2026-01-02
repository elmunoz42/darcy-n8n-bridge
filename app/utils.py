from __future__ import annotations

import json
from typing import Any

from .mcp_models import MCPContent, MCPResult


class ToolExecutionError(Exception):
    """Raised when a tool suffers an expected runtime failure."""


def format_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return str(data)


def as_mcp_text(content: str) -> MCPResult:
    return MCPResult(content=[MCPContent(text=content)])
