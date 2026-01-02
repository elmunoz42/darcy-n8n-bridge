from __future__ import annotations

from functools import lru_cache
from typing import Optional, Set

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mcp_api_key: str = Field(..., alias="MCP_API_KEY")
    n8n_base_url: str = Field(..., alias="N8N_BASE_URL")
    n8n_api_key: str = Field(..., alias="N8N_API_KEY")
    n8n_workflow_allowlist: Optional[Set[str]] = Field(None, alias="N8N_WORKFLOW_ALLOWLIST")
    http_timeout_seconds: float = Field(10.0, alias="HTTP_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @field_validator("n8n_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("n8n_workflow_allowlist", mode="before")
    @classmethod
    def parse_allowlist(cls, value: Optional[str]) -> Optional[Set[str]]:
        if value is None:
            return None
        if isinstance(value, set):
            return value or None
        items = {item.strip() for item in str(value).split(",") if item.strip()}
        return items or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
