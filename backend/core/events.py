"""Barramento de eventos e estado de execução compartilhado."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    online: bool = True
    listening: bool = False
    thinking: bool = False
    executing: bool = False
    speaking: bool = False
    detail: str = ""
    error: str | None = None
    active_tool: str | None = None
    active_conversation_id: str | None = None

    @property
    def state(self) -> str:
        if self.error:
            return "error"
        if self.speaking:
            return "speaking"
        if self.listening:
            return "listening"
        if self.executing:
            return "executing"
        if self.thinking:
            return "thinking"
        return "idle"

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state
        return payload


@dataclass
class Event:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": self.data, "timestamp": self.timestamp}


class EventBus:
    """Fan-out assíncrono com publicação segura a partir de threads."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    def _enqueue(self, payload: dict[str, Any]) -> None:
        for queue in list(self._queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.debug("Fila de eventos cheia; evento descartado")

    async def publish(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        self._enqueue(Event(event_type, data or {}).to_dict())

    def publish_threadsafe(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        payload = Event(event_type, data or {}).to_dict()
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._enqueue(payload)
        else:
            loop.call_soon_threadsafe(self._enqueue, payload)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._queues.add(queue)
        try:
            yield queue
        finally:
            self._queues.discard(queue)


class StateManager:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._state = RuntimeState()

    @property
    def state(self) -> RuntimeState:
        return self._state

    def snapshot(self) -> dict[str, Any]:
        return self._state.snapshot()

    async def update(self, **changes: Any) -> dict[str, Any]:
        for key, value in changes.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
        snapshot = self._state.snapshot()
        await self.event_bus.publish("runtime.state", snapshot)
        return snapshot

    def update_threadsafe(self, **changes: Any) -> None:
        loop = self.event_bus._loop  # acesso interno intencional para integração com threads
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            asyncio.create_task(self.update(**changes))
        else:
            asyncio.run_coroutine_threadsafe(self.update(**changes), loop)

    async def reset(self) -> dict[str, Any]:
        return await self.update(
            listening=False,
            thinking=False,
            executing=False,
            speaking=False,
            detail="",
            error=None,
            active_tool=None,
        )
