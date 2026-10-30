"""Testes do MemoryManager e das heurísticas de segurança."""

from __future__ import annotations

import pytest

from backend.core.memory import MemoryManager
from backend.core.utils import human_bytes, is_probably_secret, normalize_text, truncate


@pytest.fixture
def manager(repositories, settings_service, event_bus) -> MemoryManager:
    return MemoryManager(repositories.memories, settings_service, event_bus)


def test_add_and_search(manager: MemoryManager) -> None:
    record = manager.add(
        "O usuário prefere respostas em português", category="preference"
    )
    assert record.category == "preference"
    results = manager.search("português")
    assert [item.id for item in results] == [record.id]


def test_add_rejects_short_and_secret(manager: MemoryManager) -> None:
    with pytest.raises(ValueError):
        manager.add("x")
    with pytest.raises(ValueError):
        manager.add("minha senha: super-secreta-123")


def test_update_rejects_secret(manager: MemoryManager) -> None:
    record = manager.add("Conteúdo normal")
    with pytest.raises(ValueError):
        manager.update(record.id, content="api_key=abcdefghijklmnop")


def test_temporary_memory_is_scoped_to_conversation(manager: MemoryManager) -> None:
    temporary = manager.add(
        "Contexto temporário do projeto", persistent=False, conversation_id="conv_1"
    )
    assert manager.search("temporário", conversation_id="conv_2") == []
    assert manager.search("temporário", conversation_id="conv_1")[0].id == temporary.id


def test_as_prompt_labels(manager: MemoryManager) -> None:
    records = [
        manager.add("Prefiro respostas curtas", category="preference"),
        manager.add("Projeto usa FastAPI", category="project", persistent=False),
    ]
    prompt = manager.as_prompt(records)
    assert "preferência/persistente" in prompt
    assert "projeto/temporária" in prompt
    assert manager.as_prompt([]) == ""


def test_retrieve_context_respects_setting(
    manager: MemoryManager, settings_service
) -> None:
    manager.add("Gosto de café sem açúcar", category="preference")
    assert manager.retrieve_context("café")
    settings_service.update({"auto_memory_search": False})
    assert manager.retrieve_context("café") == []


def test_cleanup_expired(manager: MemoryManager, repositories) -> None:
    record = manager.add("Temporária antiga", persistent=False)
    repositories.memories.db.execute(
        "UPDATE memories SET created_at = ? WHERE id = ?",
        ("2020-01-01T00:00:00.000Z", record.id),
    )
    assert manager.cleanup_expired() == 1


def test_secret_heuristics() -> None:
    assert is_probably_secret("sk-abcdefghijklmnopqrstuvwxyz123456")
    assert is_probably_secret("api_key = abcdefghijklmnop")
    assert is_probably_secret("senha: super-secreta-123")
    assert not is_probably_secret("Gosto de café sem açúcar")
    assert not is_probably_secret("O projeto fica em C:\\Projetos")


def test_text_utilities() -> None:
    assert normalize_text("  Járvis, você está AÍ? ") == "jarvis, voce esta ai?"
    assert truncate("abcdefghij", 5) == "abcd…"
    assert truncate("abc", 5) == "abc"
    assert human_bytes(0) == "0 B"
    assert human_bytes(2048) == "2.0 KB"
