"""Rotas de gerenciamento da memória persistente."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from backend.api.deps import get_container, memory_dict
from backend.api.schemas import MemoryCreateRequest, MemoryUpdateRequest
from backend.core.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/api", tags=["memória"])


@router.get("/memories")
async def list_memories(
    request: Request,
    category: str | None = None,
    persistent: bool | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    container = get_container(request)
    records = container.memory_manager.list(
        category=category, persistent=persistent, limit=limit
    )
    return {"memories": [memory_dict(record) for record in records]}


@router.get("/memories/search")
async def search_memories(
    request: Request,
    q: str = Query(min_length=1, max_length=300),
    limit: int = Query(10, ge=1, le=50),
    conversation_id: str | None = None,
) -> dict[str, Any]:
    container = get_container(request)
    records = container.memory_manager.search(
        q, limit=limit, include_temporary=True, conversation_id=conversation_id
    )
    return {"memories": [memory_dict(record) for record in records]}


@router.post("/memories")
async def create_memory(payload: MemoryCreateRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    try:
        record = container.memory_manager.add(
            payload.content,
            category=payload.category,
            persistent=payload.persistent,
            conversation_id=payload.conversation_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await container.event_bus.publish("memory.created", {"memory": memory_dict(record)})
    return {"memory": memory_dict(record)}


@router.patch("/memories/{memory_id}")
async def update_memory(
    memory_id: str, payload: MemoryUpdateRequest, request: Request
) -> dict[str, Any]:
    container = get_container(request)
    try:
        record = container.memory_manager.update(
            memory_id,
            content=payload.content,
            category=payload.category,
            persistent=payload.persistent,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    if record is None:
        raise NotFoundError("Memória não encontrada")
    await container.event_bus.publish("memory.updated", {"memory": memory_dict(record)})
    return {"memory": memory_dict(record)}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    if not container.memory_manager.delete(memory_id):
        raise NotFoundError("Memória não encontrada")
    await container.event_bus.publish("memory.deleted", {"memory_id": memory_id})
    return {"ok": True, "memory_id": memory_id}
