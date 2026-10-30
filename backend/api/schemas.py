"""Schemas Pydantic da API HTTP."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(None, max_length=80)
    source: Literal["text", "voice"] = "text"
    speak: bool | None = None


class ApproveRequest(StrictModel):
    approve: bool
    speak: bool | None = None


class ConversationCreateRequest(StrictModel):
    title: str = Field("Nova conversa", min_length=1, max_length=120)


class ConversationUpdateRequest(StrictModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    archived: bool | None = None


class MemoryCreateRequest(StrictModel):
    content: str = Field(min_length=2, max_length=2000)
    category: Literal["preference", "fact", "project", "contact", "other"] = "other"
    persistent: bool = True
    conversation_id: str | None = Field(None, max_length=80)


class MemoryUpdateRequest(StrictModel):
    content: str | None = Field(None, min_length=2, max_length=2000)
    category: Literal["preference", "fact", "project", "contact", "other"] | None = None
    persistent: bool | None = None


class SettingsUpdateRequest(StrictModel):
    values: dict[str, Any]


class ProviderKeyRequest(StrictModel):
    api_key: str = Field(max_length=500)


class VoiceStartRequest(StrictModel):
    continuous: bool | None = None


class SpeakRequest(StrictModel):
    text: str = Field(min_length=1, max_length=6000)


class PlanStepRequest(StrictModel):
    title: str = Field(min_length=2, max_length=240)
    status: Literal["pending", "in_progress", "done", "blocked"] = "pending"
    note: str = Field("", max_length=300)


class PlanUpdateRequest(StrictModel):
    steps: list[PlanStepRequest] = Field(max_length=20)


class SearchQuery(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(8, ge=1, le=50)
