"""Testes da camada SQLite, repositórios e serviço de configurações."""

from __future__ import annotations

import pytest

from backend.core.errors import ValidationError
from backend.database.database import Database
from backend.database.repositories import (
    ActionRepository,
    ConversationRepository,
    MemoryRepository,
    MessageRepository,
    SettingsRepository,
)


def test_migrations_are_versioned(database: Database) -> None:
    rows = database.fetchall("SELECT version FROM schema_migrations ORDER BY version")
    assert [row["version"] for row in rows] == [1]
    assert database.health() is True


def test_initialize_is_idempotent(database: Database) -> None:
    database.initialize()
    database.initialize()
    assert database.health() is True


def test_conversation_crud_and_metadata(database: Database) -> None:
    conversations = ConversationRepository(database)
    created = conversations.create("  Minha conversa  ")
    assert created.title == "Minha conversa"

    conversations.update_title(created.id, "Novo título")
    conversations.update_metadata(created.id, {"plan": [{"title": "Passo 1"}]})
    updated = conversations.get(created.id)
    assert updated is not None
    assert updated.title == "Novo título"
    assert updated.metadata["plan"][0]["title"] == "Passo 1"

    conversations.set_archived(created.id, True)
    assert conversations.list() == []
    assert len(conversations.list(include_archived=True)) == 1

    conversations.delete(created.id)
    assert conversations.get(created.id) is None


def test_messages_are_ordered_and_roundtrip_tool_calls(database: Database) -> None:
    conversations = ConversationRepository(database)
    messages = MessageRepository(database, conversations)
    conversation = conversations.create("Teste")

    user = messages.add(conversation.id, "user", "Olá")
    tool_calls = [
        {"id": "call_1", "type": "function", "function": {"name": "x", "arguments": "{}"}}
    ]
    assistant = messages.add(conversation.id, "assistant", "", tool_calls=tool_calls)
    tool = messages.add(
        conversation.id, "tool", '{"success": true}', tool_call_id="call_1", name="x"
    )

    listed = messages.list(conversation.id)
    assert [message.id for message in listed] == [user.id, assistant.id, tool.id]
    assert listed[1].tool_calls == tool_calls
    assert listed[2].tool_call_id == "call_1"
    assert listed[2].to_llm()["name"] == "x"

    refreshed = conversations.get(conversation.id)
    assert refreshed is not None
    assert refreshed.message_count == 3
    assert refreshed.last_message == '{"success": true}'


def test_message_limit_returns_latest_in_order(database: Database) -> None:
    conversations = ConversationRepository(database)
    messages = MessageRepository(database, conversations)
    conversation = conversations.create("Teste")
    created = [messages.add(conversation.id, "user", f"mensagem {index}") for index in range(5)]
    latest = messages.list(conversation.id, limit=2)
    assert [message.id for message in latest] == [created[-2].id, created[-1].id]


def test_memory_repository_search_and_update(database: Database) -> None:
    memories = MemoryRepository(database)
    first = memories.add(
        "Prefiro respostas curtas e objetivas", category="preference", persistent=True
    )
    second = memories.add(
        "Projeto JARVIS usa Python", category="project", persistent=False, conversation_id="conv_1"
    )

    results = memories.search("respostas curtas")
    assert [record.id for record in results] == [first.id]

    temporary = memories.search(
        "Python", include_temporary=True, conversation_id="conv_1"
    )
    assert [record.id for record in temporary] == [second.id]
    hidden = memories.search("Python", include_temporary=True, conversation_id="conv_2")
    assert hidden == []

    updated = memories.update(second.id, content="Projeto JARVIS usa FastAPI", persistent=True)
    assert updated is not None
    assert updated.content == "Projeto JARVIS usa FastAPI"
    assert updated.persistent is True

    assert memories.delete(first.id) is True
    assert memories.delete(first.id) is False


def test_memory_cleanup_expired(database: Database) -> None:
    memories = MemoryRepository(database)
    record = memories.add("Memória temporária antiga", persistent=False)
    database.execute(
        "UPDATE memories SET created_at = ? WHERE id = ?",
        ("2020-01-01T00:00:00.000Z", record.id),
    )
    assert memories.delete_expired_temporary(24) == 1
    assert memories.get(record.id) is None


def test_action_repository_lifecycle(database: Database) -> None:
    actions = ActionRepository(database)
    action = actions.create(
        tool_name="create_file",
        arguments={"path": "x.txt"},
        permission_level=2,
        summary="Criar x.txt",
        status="pending",
        conversation_id="conv_1",
        tool_call_id="call_1",
    )
    assert actions.pending("conv_1")[0].id == action.id

    updated = actions.update(
        action.id, status="executed", result={"success": True}, error=None
    )
    assert updated is not None
    assert updated.status == "executed"
    assert updated.result == {"success": True}
    assert updated.completed_at is not None
    assert actions.pending("conv_1") == []


def test_settings_repository_and_service_persist(database: Database) -> None:
    repository = SettingsRepository(database)
    repository.set("tema", {"modo": "escuro"})
    assert repository.get("tema") == {"modo": "escuro"}
    assert repository.all()["tema"] == {"modo": "escuro"}
    repository.delete("tema")
    assert repository.get("tema") is None


def test_settings_service_validates_and_persists(
    settings_service, repositories, app_settings
) -> None:
    updated = settings_service.update({"temperature": 0.9, "max_agent_steps": 5})
    assert updated.temperature == 0.9

    fresh = settings_service.__class__(app_settings, repositories.settings)
    assert fresh.get().max_agent_steps == 5

    with pytest.raises(ValidationError):
        settings_service.update({"campo_inexistente": True})
    with pytest.raises(ValidationError):
        settings_service.update({"temperature": 5.0})

    reset = settings_service.reset()
    assert reset.temperature == 0.3
