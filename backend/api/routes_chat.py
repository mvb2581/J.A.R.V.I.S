"""Rotas de conversas, chat, ações e planejamento."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request

from backend.api.deps import (
    action_dict,
    conversation_dict,
    get_container,
    message_dict,
    require_conversation,
)
from backend.api.schemas import (
    ApproveRequest,
    ChatRequest,
    ConversationCreateRequest,
    ConversationUpdateRequest,
    PlanUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/conversations")
async def list_conversations(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    include_archived: bool = False,
) -> dict[str, Any]:
    container = get_container(request)
    records = container.conversations.list(limit=limit, include_archived=include_archived)
    return {"conversations": [conversation_dict(record) for record in records]}


@router.post("/conversations")
async def create_conversation(
    payload: ConversationCreateRequest, request: Request
) -> dict[str, Any]:
    container = get_container(request)
    record = container.conversations.create(title=payload.title)
    await container.event_bus.publish(
        "conversation.updated", {"conversation": conversation_dict(record)}
    )
    return {"conversation": conversation_dict(record)}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    record = require_conversation(container, conversation_id)
    messages = container.messages.list(conversation_id)
    return {
        "conversation": conversation_dict(record),
        "messages": [message_dict(message) for message in messages],
        "plan": container.planner.get_plan(conversation_id),
        "pending_actions": [
            action_dict(action) for action in container.actions.pending(conversation_id)
        ],
    }


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str, payload: ConversationUpdateRequest, request: Request
) -> dict[str, Any]:
    container = get_container(request)
    require_conversation(container, conversation_id)
    if payload.title is not None:
        container.conversations.update_title(conversation_id, payload.title)
    if payload.archived is not None:
        container.conversations.set_archived(conversation_id, payload.archived)
    record = require_conversation(container, conversation_id)
    await container.event_bus.publish(
        "conversation.updated", {"conversation": conversation_dict(record)}
    )
    return {"conversation": conversation_dict(record)}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    require_conversation(container, conversation_id)
    container.conversations.delete(conversation_id)
    await container.event_bus.publish(
        "conversation.deleted", {"conversation_id": conversation_id}
    )
    return {"ok": True, "conversation_id": conversation_id}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    request: Request,
    limit: int | None = Query(None, ge=1, le=1000),
) -> dict[str, Any]:
    container = get_container(request)
    require_conversation(container, conversation_id)
    messages = container.messages.list(conversation_id, limit=limit)
    return {"messages": [message_dict(message) for message in messages]}


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    container = get_container(request)
    return await container.assistant.chat(
        payload.message,
        conversation_id=payload.conversation_id,
        source=payload.source,
        speak=payload.speak,
    )


@router.get("/actions")
async def list_actions(
    request: Request,
    conversation_id: str | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    container = get_container(request)
    actions = container.actions.list(
        conversation_id=conversation_id, status=status, limit=limit
    )
    return {"actions": [action_dict(action) for action in actions]}


@router.get("/actions/pending")
async def pending_actions(
    request: Request, conversation_id: str | None = None
) -> dict[str, Any]:
    container = get_container(request)
    return {"actions": container.assistant.pending_actions(conversation_id)}


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: str, payload: ApproveRequest, request: Request
) -> dict[str, Any]:
    container = get_container(request)
    return await container.assistant.approve_action(
        action_id, approve=payload.approve, speak=payload.speak
    )


@router.post("/actions/{action_id}/deny")
async def deny_action(action_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    return await container.assistant.approve_action(action_id, approve=False)


@router.post("/cancel")
async def cancel(request: Request, conversation_id: str | None = None) -> dict[str, Any]:
    container = get_container(request)
    return await container.assistant.cancel(conversation_id)


@router.get("/conversations/{conversation_id}/plan")
async def get_plan(conversation_id: str, request: Request) -> dict[str, Any]:
    container = get_container(request)
    require_conversation(container, conversation_id)
    return {"plan": container.planner.get_plan(conversation_id)}


@router.put("/conversations/{conversation_id}/plan")
async def update_plan(
    conversation_id: str, payload: PlanUpdateRequest, request: Request
) -> dict[str, Any]:
    container = get_container(request)
    require_conversation(container, conversation_id)
    plan = await container.planner.set_plan(
        conversation_id, [step.model_dump() for step in payload.steps]
    )
    return {"plan": plan}
