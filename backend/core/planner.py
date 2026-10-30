"""Planejamento explícito de tarefas complexas, visível na interface."""

from __future__ import annotations

import logging
from typing import Any

from backend.core.events import EventBus
from backend.core.utils import utc_now
from backend.database.repositories import ConversationRepository

logger = logging.getLogger(__name__)

PLAN_STATUSES = {"pending", "in_progress", "done", "blocked"}


class TaskPlanner:
    def __init__(self, conversations: ConversationRepository, event_bus: EventBus) -> None:
        self.conversations = conversations
        self.event_bus = event_bus

    def normalize(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, step in enumerate(steps[:20], start=1):
            title = str(step.get("title", "")).strip()
            if not title:
                continue
            status = str(step.get("status", "pending")).lower()
            if status not in PLAN_STATUSES:
                status = "pending"
            normalized.append(
                {
                    "id": index,
                    "title": title[:240],
                    "status": status,
                    "note": str(step.get("note", ""))[:300],
                }
            )
        return normalized

    async def set_plan(self, conversation_id: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        plan = self.normalize(steps)
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            raise ValueError("Conversa não encontrada")
        metadata = dict(conversation.metadata or {})
        metadata["plan"] = plan
        metadata["plan_updated_at"] = utc_now()
        self.conversations.update_metadata(conversation_id, metadata)
        await self.event_bus.publish(
            "plan.updated", {"conversation_id": conversation_id, "plan": plan}
        )
        return plan

    def get_plan(self, conversation_id: str) -> list[dict[str, Any]]:
        conversation = self.conversations.get(conversation_id)
        if conversation is None:
            return []
        plan = conversation.metadata.get("plan", [])
        return plan if isinstance(plan, list) else []

    async def clear(self, conversation_id: str) -> None:
        await self.set_plan(conversation_id, [])
