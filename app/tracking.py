from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel


class DarcyExecutionRecord(BaseModel):
    execution_id: Optional[str]
    workflow_id: str
    payload: Dict[str, Any]
    started_at: datetime


class RunTracker:
    def __init__(self, max_entries: int = 200) -> None:
        self._entries: Deque[DarcyExecutionRecord] = deque(maxlen=max_entries)
        self._lock = asyncio.Lock()

    async def add_entry(
        self,
        *,
        workflow_id: str,
        execution_id: Optional[str],
        payload: Dict[str, Any],
    ) -> None:
        record = DarcyExecutionRecord(
            workflow_id=workflow_id,
            execution_id=execution_id,
            payload=payload,
            started_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._entries.appendleft(record)

    async def list_entries(self) -> List[DarcyExecutionRecord]:
        async with self._lock:
            return list(self._entries)
