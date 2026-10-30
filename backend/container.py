"""Montagem das dependências da aplicação (composition root)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.ai.factory import ProviderFactory
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
from backend.security.secrets import SecretStore
from backend.tools.registry import ToolRegistry, build_default_registry
from backend.voice.service import VoiceService
from backend.voice.text_to_speech import TTSService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Container:
    app_settings: AppSettings
    data_dir: Path
    database: Database
    event_bus: EventBus
    state: StateManager
    settings_service: SettingsService
    secret_store: SecretStore
    provider_factory: ProviderFactory
    conversations: ConversationRepository
    messages: MessageRepository
    memory_repository: MemoryRepository
    actions: ActionRepository
    settings_repository: SettingsRepository
    memory_manager: MemoryManager
    planner: TaskPlanner
    registry: ToolRegistry
    permissions: PermissionManager
    agent: Agent
    assistant: AssistantService
    tts: TTSService
    voice: VoiceService

    def shutdown(self) -> None:
        try:
            self.voice.recognizer.stop()
        except Exception:
            logger.exception("Falha ao encerrar o reconhecimento de voz")
        try:
            self.tts.shutdown()
        except Exception:
            logger.exception("Falha ao encerrar a síntese de voz")


def build_container(app_settings: AppSettings) -> Container:
    app_settings.ensure_directories()
    database = Database(app_settings.db_path)
    database.initialize()

    event_bus = EventBus()
    state = StateManager(event_bus)

    conversations = ConversationRepository(database)
    messages = MessageRepository(database, conversations)
    memory_repository = MemoryRepository(database)
    actions = ActionRepository(database)
    settings_repository = SettingsRepository(database)

    settings_service = SettingsService(app_settings, settings_repository)
    secret_store = SecretStore(app_settings.secrets_path)
    provider_factory = ProviderFactory(app_settings, secret_store)

    memory_manager = MemoryManager(memory_repository, settings_service, event_bus)
    planner = TaskPlanner(conversations, event_bus)
    registry = build_default_registry()
    permissions = PermissionManager(settings_service)

    agent = Agent(
        app_settings=app_settings,
        settings=settings_service,
        provider_factory=provider_factory,
        registry=registry,
        permissions=permissions,
        conversations=conversations,
        messages=messages,
        actions=actions,
        memory=memory_manager,
        planner=planner,
        event_bus=event_bus,
        state=state,
    )

    tts = TTSService(
        settings_service,
        event_bus,
        state,
        data_dir=app_settings.data_dir,
    )

    assistant = AssistantService(
        agent=agent,
        conversations=conversations,
        messages=messages,
        actions=actions,
        settings=settings_service,
        planner=planner,
        registry=registry,
        event_bus=event_bus,
        state=state,
        tts=tts,
    )

    voice = VoiceService(
        assistant=assistant,
        settings=settings_service,
        event_bus=event_bus,
        state=state,
        tts=tts,
    )

    return Container(
        app_settings=app_settings,
        data_dir=app_settings.data_dir,
        database=database,
        event_bus=event_bus,
        state=state,
        settings_service=settings_service,
        secret_store=secret_store,
        provider_factory=provider_factory,
        conversations=conversations,
        messages=messages,
        memory_repository=memory_repository,
        actions=actions,
        settings_repository=settings_repository,
        memory_manager=memory_manager,
        planner=planner,
        registry=registry,
        permissions=permissions,
        agent=agent,
        assistant=assistant,
        tts=tts,
        voice=voice,
    )
