from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class N8NClientError(Exception):
    def __init__(self, status_code: int, message: str, payload: Optional[Any] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class N8NClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self._base_url = base_url
        self._headers = {"X-N8N-API-KEY": api_key}
        self._timeout = httpx.Timeout(timeout_seconds, read=timeout_seconds * 3)

    async def list_workflows(self, *, limit: int, offset: int, active: Optional[bool]) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if active is not None:
            params["active"] = str(active).lower()
        return await self._request("GET", "/api/v1/workflows", params=params)

    async def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/v1/workflows/{workflow_id}")

    async def run_workflow(self, workflow_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/api/v1/workflows/{workflow_id}/run",
            json=payload,
        )

    async def list_executions(
        self,
        *,
        limit: int,
        offset: int,
        workflow_id: Optional[str],
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if workflow_id:
            params["workflowId"] = workflow_id
        return await self._request("GET", "/api/v1/executions", params=params)

    async def get_execution(self, execution_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/v1/executions/{execution_id}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
            try:
                response = await client.request(method, url, params=params, json=json)
            except httpx.RequestError as exc:
                raise N8NClientError(status_code=0, message="Unable to reach n8n API", payload=str(exc)) from exc
        if response.status_code >= 400:
            message, payload = self._parse_error(response)
            raise N8NClientError(status_code=response.status_code, message=message, payload=payload)
        try:
            return response.json()
        except ValueError as exc:
            raise N8NClientError(status_code=response.status_code, message="Invalid JSON from n8n", payload=response.text) from exc

    @staticmethod
    def _parse_error(response: httpx.Response) -> tuple[str, Any]:
        default_message = f"n8n API responded with status {response.status_code}"
        try:
            payload = response.json()
        except ValueError:
            return default_message, response.text
        message = payload.get("message") or payload.get("error") or default_message
        return message, payload
