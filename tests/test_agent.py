"""Testes do loop do agente, confirmações e retomada."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.core.agent import _sanitize_history
from backend.core.errors import ValidationError
from backend.database.models import MessageRecord
from tests.conftest import FakeProvider, response, tool_call


async def test_agent_returns_final_response(build_jarvis, repositories) -> None:
    provider = FakeProvider([response("Olá, senhor. Sistemas online.")])
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    assert result.final_text == "Olá, senhor. Sistemas online."
    assert result.steps == 1
    assert result.cancelled is False
    assert provider.requests[0]["tools"]
    messages = repositories.messages.list(conversation.id)
    assert [message.role for message in messages] == ["assistant"]
    assert messages[0].content == result.final_text


async def test_assistant_chat_creates_conversation_and_titles_it(
    build_jarvis, repositories
) -> None:
    provider = FakeProvider([response("Resposta do JARVIS")])
    jarvis = build_jarvis(provider)

    payload = await jarvis.assistant.chat("Olá JARVIS, tudo bem?")

    assert payload["conversation_id"]
    assert payload["user_message"]["content"] == "Olá JARVIS, tudo bem?"
    assert payload["assistant_message"]["content"] == "Resposta do JARVIS"
    conversation = repositories.conversations.get(payload["conversation_id"])
    assert conversation is not None
    assert conversation.title == "Olá JARVIS, tudo bem?"
    assert conversation.message_count == 2


async def test_assistant_rejects_empty_message(build_jarvis) -> None:
    jarvis = build_jarvis(FakeProvider([]))
    with pytest.raises(ValidationError):
        await jarvis.assistant.chat("   ")


async def test_level1_tool_executes_automatically(
    build_jarvis, repositories, workspace: Path
) -> None:
    provider = FakeProvider(
        [
            response("", calls=[tool_call("get_system_information", {})]),
            response("Sistema consultado."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    assert result.final_text == "Sistema consultado."
    actions = repositories.actions.list(conversation_id=conversation.id)
    assert len(actions) == 1
    assert actions[0].status == "executed"
    assert actions[0].permission_level == 1
    roles = [message.role for message in repositories.messages.list(conversation.id)]
    assert roles == ["assistant", "tool", "assistant"]


async def test_string_boolean_arguments_are_coerced(
    build_jarvis, repositories
) -> None:
    provider = FakeProvider(
        [
            response(
                "",
                calls=[
                    tool_call("get_system_information", {"include_gpu": "false"})
                ],
            ),
            response("Sistema consultado."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    actions = repositories.actions.list(conversation_id=conversation.id)
    assert len(actions) == 1
    assert actions[0].status == "executed"
    assert actions[0].arguments["include_gpu"] is False
    assert result.final_text == "Sistema consultado."


async def test_level2_tool_pauses_for_confirmation_and_resumes(
    build_jarvis, repositories, workspace: Path
) -> None:
    target = workspace / "confirmado.txt"
    provider = FakeProvider(
        [
            response(
                "",
                calls=[
                    tool_call("create_file", {"path": str(target), "content": "dados"})
                ],
            ),
            response("Arquivo criado após a confirmação, senhor."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    assert len(result.pending_actions) == 1
    action = result.pending_actions[0]
    assert action.status == "pending"
    assert action.permission_level == 2
    assert not target.exists()
    assert result.final_text.startswith("Preciso da sua confirmação")

    approval = await jarvis.assistant.approve_action(action.id, approve=True)

    assert target.read_text(encoding="utf-8") == "dados"
    assert approval["action"]["status"] == "executed"
    assert approval["assistant_message"]["content"].startswith("Arquivo criado")
    assert repositories.actions.pending(conversation.id) == []


async def test_denied_action_is_not_executed(
    build_jarvis, repositories, workspace: Path
) -> None:
    target = workspace / "negado.txt"
    provider = FakeProvider(
        [
            response(
                "",
                calls=[
                    tool_call("create_file", {"path": str(target), "content": "dados"})
                ],
            ),
            response("Entendido, não criarei o arquivo."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)
    action = result.pending_actions[0]
    approval = await jarvis.assistant.approve_action(action.id, approve=False)

    assert not target.exists()
    assert approval["action"]["status"] == "denied"
    assert approval["assistant_message"]["content"] == "Entendido, não criarei o arquivo."


async def test_level3_blocked_when_disabled(
    build_jarvis, repositories, settings_service, workspace: Path
) -> None:
    settings_service.update({"allow_level3": False})
    provider = FakeProvider(
        [
            response("", calls=[tool_call("delete_file", {"path": str(workspace / "x.txt")})]),
            response("Ação bloqueada."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    actions = repositories.actions.list(conversation_id=conversation.id)
    assert len(actions) == 1
    assert actions[0].status == "blocked"
    assert actions[0].permission_level == 3
    assert result.pending_actions == []
    assert result.final_text == "Ação bloqueada."


async def test_unknown_tool_is_reported_to_the_model(
    build_jarvis, repositories
) -> None:
    provider = FakeProvider(
        [
            response("", calls=[tool_call("ferramenta_inexistente", {})]),
            response("Não consegui usar essa ferramenta."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    tool_message = repositories.messages.list(conversation.id)[1]
    assert tool_message.role == "tool"
    assert "Ferramenta desconhecida" in tool_message.content
    assert result.final_text == "Não consegui usar essa ferramenta."


async def test_invalid_arguments_are_reported_to_the_model(
    build_jarvis, repositories
) -> None:
    provider = FakeProvider(
        [
            response("", calls=[tool_call("read_file", {"caminho": "x.txt"})]),
            response("Argumentos inválidos, senhor."),
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    await jarvis.agent.run(conversation.id)

    tool_message = repositories.messages.list(conversation.id)[1]
    assert "Argumentos inválidos" in tool_message.content


async def test_max_agent_steps(build_jarvis, repositories, settings_service) -> None:
    settings_service.update({"max_agent_steps": 1})
    provider = FakeProvider(
        [response("", calls=[tool_call("get_system_information", {})])]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()

    result = await jarvis.agent.run(conversation.id)

    assert "limite de 1 etapas" in result.final_text
    assert len(provider.requests) == 1


async def test_cancelled_before_start_does_not_call_provider(
    build_jarvis, repositories
) -> None:
    provider = FakeProvider([])
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()
    cancel_event = asyncio.Event()
    cancel_event.set()

    result = await jarvis.agent.run(conversation.id, cancel_event=cancel_event)

    assert result.cancelled is True
    assert provider.requests == []
    assert result.final_text == "Operação interrompida pelo usuário."


async def test_pending_action_blocks_new_messages(build_jarvis, repositories, workspace: Path) -> None:
    target = workspace / "pendente.txt"
    provider = FakeProvider(
        [
            response(
                "",
                calls=[
                    tool_call("create_file", {"path": str(target), "content": "x"})
                ],
            )
        ]
    )
    jarvis = build_jarvis(provider)
    conversation = repositories.conversations.create()
    await jarvis.agent.run(conversation.id)

    with pytest.raises(ValidationError):
        await jarvis.assistant.chat("Outra mensagem", conversation_id=conversation.id)


def _message(
    role: str,
    content: str = "",
    *,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
) -> MessageRecord:
    return MessageRecord(
        id=f"msg_{role}_{content[:4]}_{tool_call_id or ''}",
        conversation_id="conv_test",
        role=role,
        content=content,
        created_at="2026-01-01T00:00:00.000Z",
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
    )


def _call(call_id: str) -> list[dict]:
    return [
        {
            "id": call_id,
            "type": "function",
            "function": {"name": "x", "arguments": "{}"},
        }
    ]


def test_sanitize_history_keeps_valid_tool_pairs() -> None:
    records = [
        _message("user", "olá"),
        _message("assistant", "", tool_calls=_call("call_1")),
        _message("tool", "{}", tool_call_id="call_1"),
        _message("assistant", "pronto"),
    ]
    sanitized = _sanitize_history(records, 10)
    assert [record.role for record in sanitized] == ["user", "assistant", "tool", "assistant"]


def test_sanitize_history_removes_orphan_tool_calls() -> None:
    records = [
        _message("user", "olá"),
        _message("assistant", "", tool_calls=_call("call_sem_resposta")),
        _message("assistant", "resposta"),
    ]
    sanitized = _sanitize_history(records, 10)
    assert [record.role for record in sanitized] == ["user", "assistant"]
    assert sanitized[-1].content == "resposta"


def test_sanitize_history_keeps_content_without_tool_calls() -> None:
    records = [
        _message("user", "olá"),
        _message("assistant", "vou verificar", tool_calls=_call("call_orfao")),
        _message("assistant", "resposta"),
    ]
    sanitized = _sanitize_history(records, 10)
    assert sanitized[1].content == "vou verificar"
    assert sanitized[1].tool_calls is None


def test_sanitize_history_removes_leading_tool_messages() -> None:
    records = [
        _message("tool", "{}", tool_call_id="call_1"),
        _message("user", "olá"),
    ]
    sanitized = _sanitize_history(records, 10)
    assert [record.role for record in sanitized] == ["user"]
