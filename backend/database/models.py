"""Modelos de domínio independentes do framework web."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.core.utils import json_loads


@dataclass(slots=True)
class ConversationRecord:
    id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    last_message: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ConversationRecord:
        return cls(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived=bool(row.get("archived", 0)),
            metadata=json_loads(row.get("metadata"), {}) or {},
            message_count=int(row.get("message_count", 0) or 0),
            last_message=row.get("last_message") or "",
        )


@dataclass(slots=True)
class MessageRecord:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MessageRecord:
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            role=row["role"],
            content=row.get("content") or "",
            created_at=row["created_at"],
            tool_calls=json_loads(row.get("tool_calls")),
            tool_call_id=row.get("tool_call_id"),
            name=row.get("name"),
            metadata=json_loads(row.get("metadata"), {}) or {},
        )

    def to_llm(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = self.tool_calls
            message["content"] = self.content or None
        if self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        if self.name:
            message["name"] = self.name
        return message


@dataclass(slots=True)
class MemoryRecord:
    id: str
    category: str
    content: str
    source: str
    persistent: bool
    conversation_id: str | None
    created_at: str
    updated_at: str
    last_used_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MemoryRecord:
        return cls(
            id=row["id"],
            category=row["category"],
            content=row["content"],
            source=row.get("source") or "user",
            persistent=bool(row.get("persistent", 1)),
            conversation_id=row.get("conversation_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row.get("last_used_at"),
        )


@dataclass(slots=True)
class ActionRecord:
    id: str
    tool_name: str
    arguments: dict[str, Any]
    permission_level: int
    status: str
    summary: str
    created_at: str
    conversation_id: str | None = None
    tool_call_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ActionRecord:
        return cls(
            id=row["id"],
            tool_name=row["tool_name"],
            arguments=json_loads(row.get("arguments"), {}) or {},
            permission_level=int(row.get("permission_level", 1)),
            status=row["status"],
            summary=row.get("summary") or "",
            created_at=row["created_at"],
            conversation_id=row.get("conversation_id"),
            tool_call_id=row.get("tool_call_id"),
            result=json_loads(row.get("result")),
            error=row.get("error"),
            completed_at=row.get("completed_at"),
        )
