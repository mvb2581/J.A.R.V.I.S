"""Fixtures compartilhadas pelos testes do JARVIS."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.ai.types import LLMResponse, ToolCall
from backend.config.settings import AppSettings
from backend.core.agent import Agent
from backend.core.assistant import AssistantService
from backend.core.events import EventBus, StateManager
from backend.core.memory import MemoryManager
from backend.core.permissions import PermissionManager
from backend.core.planner import TaskPlanner
from backend.core.settings_service import SettingsService
from backend.database.database import Database
from backend.database.repositories import (
    ActionRepository,
    ConversationRepository,
    MemoryRepository,
    MessageRepository,
    SettingsRepository,
)
from backend.tools.base import ToolContext
from backend.tools.path_guard import PathGuard
from backend.tools.registry import ToolRegistry, build_default_registry


class FakeProvider:
    """Provedor de LLM determinístico para testes do loop do agente."""

    name = "fake"
    label = "Fake"

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        self.requests.append(
            {"messages": messages, "tools": tools, "model": model, "temperature": temperature}
        )
        if not self.responses:
            raise AssertionError("FakeProvider ficou sem respostas programadas")
        return self.responses.pop(0)


class FakeFactory:
    """Fábrica que sempre devolve o mesmo provedor falso."""

    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider

    def create(self, _settings: Any) -> FakeProvider:
        return self.provider

    def describe(self, _settings: Any) -> list[dict[str, Any]]:
        return []


def response(
    content: str = "",
    *,
    calls: list[ToolCall] | None = None,
    finish_reason: str = "stop",
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=calls or [],
        finish_reason=finish_reason,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        model="fake-model",
        provider="fake",
    )


def tool_call(name: str, arguments: dict[str, Any] | None = None) -> ToolCall:
    payload = arguments or {}
    return ToolCall(
        id=f"call_{uuid.uuid4().hex[:10]}",
        name=name,
        arguments=payload,
        raw_arguments=json.dumps(payload, ensure_ascii=False),
    )


@pytest.fixture
def app_settings(tmp_path: Path) -> AppSettings:
    settings = AppSettings(
        data_dir=tmp_path / "data",
        default_provider="ollama",
        default_model="fake-model",
        request_timeout=10.0,
    )
    settings.ensure_directories()
    return settings


@pytest.fixture
def database(app_settings: AppSettings) -> Database:
    db = Database(app_settings.db_path)
    db.initialize()
    return db


@pytest.fixture
def repositories(database: Database) -> SimpleNamespace:
    conversations = ConversationRepository(database)
    return SimpleNamespace(
        conversations=conversations,
        messages=MessageRepository(database, conversations),
        memories=MemoryRepository(database),
        actions=ActionRepository(database),
        settings=SettingsRepository(database),
    )


@pytest.fixture
def settings_service(
    app_settings: AppSettings, repositories: SimpleNamespace
) -> SettingsService:
    return SettingsService(app_settings, repositories.settings)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.fixture
def runtime(settings_service: SettingsService, workspace: Path):
    return settings_service.update(
        {
            "allowed_roots": [str(workspace)],
            "provider": "ollama",
            "model": "fake-model",
            "confirm_level2": True,
            "allow_level3": True,
        }
    )


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def state(event_bus: EventBus) -> StateManager:
    return StateManager(event_bus)


@pytest.fixture
def tool_context(
    app_settings: AppSettings,
    runtime,
    event_bus: EventBus,
    state: StateManager,
    workspace: Path,
) -> ToolContext:
    return ToolContext(
        app_settings=app_settings,
        runtime_settings=runtime,
        path_guard=PathGuard(
            runtime.allowed_roots,
            data_dir=app_settings.data_dir,
            block_sensitive=runtime.block_sensitive_files,
        ),
        data_dir=app_settings.data_dir,
        event_bus=event_bus,
        state=state,
        user_home=workspace,
    )


@pytest.fixture
def build_jarvis(
    app_settings: AppSettings,
    settings_service: SettingsService,
    repositories: SimpleNamespace,
    event_bus: EventBus,
    state: StateManager,
):
    """Cria Agent + AssistantService com um provedor falso."""

    def _build(provider: FakeProvider, registry: ToolRegistry | None = None) -> SimpleNamespace:
        registry = registry or build_default_registry()
        memory = MemoryManager(repositories.memories, settings_service, event_bus)
        planner = TaskPlanner(repositories.conversations, event_bus)
        permissions = PermissionManager(settings_service)
        agent = Agent(
            app_settings=app_settings,
            settings=settings_service,
            provider_factory=FakeFactory(provider),  # type: ignore[arg-type]
            registry=registry,
            permissions=permissions,
            conversations=repositories.conversations,
            messages=repositories.messages,
            actions=repositories.actions,
            memory=memory,
            planner=planner,
            event_bus=event_bus,
            state=state,
        )
        assistant = AssistantService(
            agent=agent,
            conversations=repositories.conversations,
            messages=repositories.messages,
            actions=repositories.actions,
            settings=settings_service,
            planner=planner,
            registry=registry,
            event_bus=event_bus,
            state=state,
            tts=None,
        )
        return SimpleNamespace(
            agent=agent,
            assistant=assistant,
            provider=provider,
            registry=registry,
            memory=memory,
            planner=planner,
            permissions=permissions,
        )

    return _build
