from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

JSONRPC_VERSION = "2.0"


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class MCPContent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class MCPResult(BaseModel):
    content: List[MCPContent]


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal[JSONRPC_VERSION] = JSONRPC_VERSION
    id: Optional[Any]
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None

    @classmethod
    def success(cls, *, response_id: Any, result: Any) -> "JSONRPCResponse":
        return cls(id=response_id, result=result)

    @classmethod
    def failure(
        cls,
        *,
        response_id: Any,
        code: int,
        message: str,
        data: Optional[Any] = None,
    ) -> "JSONRPCResponse":
        return cls(id=response_id, error=JSONRPCError(code=code, message=message, data=data))


class JSONRPCRequest(BaseModel):
    jsonrpc: str = Field(JSONRPC_VERSION)
    method: str
    params: Optional[Any] = None
    id: Optional[Any] = None

    @field_validator("jsonrpc")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if value != JSONRPC_VERSION:
            raise ValueError("Only JSON-RPC 2.0 is supported")
        return value


class ToolCallParams(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}
