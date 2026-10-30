"""Testes de integração da API FastAPI (REST + WebSocket)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config.settings import AppSettings
from backend.main import create_app
from tests.conftest import FakeProvider, response, tool_call


@pytest.fixture
def client(app_settings: AppSettings):
    app = create_app(app_settings)
    with TestClient(app) as test_client:
        yield test_client


def install_provider(client: TestClient, provider: FakeProvider) -> None:
    container = client.app.state.container
    container.provider_factory.create = lambda _settings: provider  # type: ignore[assignment]


def test_health_and_status(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] is True

    status = client.get("/api/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["runtime"]["online"] is True
    assert payload["tools"] == 31
    assert "resources" in payload
    assert payload["database"]["healthy"] is True


def test_tools_and_providers(client: TestClient) -> None:
    tools = client.get("/api/tools").json()["tools"]
    assert len(tools) == 31
    assert all(tool["name"] for tool in tools)
    assert {tool["name"] for tool in tools} >= {
        "create_file",
        "execute_terminal_command",
        "screenshot",
        "update_plan",
        "save_memory",
    }

    providers = client.get("/api/providers").json()["providers"]
    assert [provider["id"] for provider in providers] == [
        "deepseek",
        "openai",
        "anthropic",
        "ollama",
        "custom",
    ]


def test_conversation_crud(client: TestClient) -> None:
    created = client.post("/api/conversations", json={"title": "Teste API"})
    assert created.status_code == 200
    conversation_id = created.json()["conversation"]["id"]

    listing = client.get("/api/conversations").json()["conversations"]
    assert [conversation["id"] for conversation in listing] == [conversation_id]

    renamed = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "Renomeada"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["conversation"]["title"] == "Renomeada"

    detail = client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []

    deleted = client.delete(f"/api/conversations/{conversation_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404


def test_chat_with_fake_provider(client: TestClient) -> None:
    provider = FakeProvider([response("Bem-vindo, senhor.")])
    install_provider(client, provider)

    result = client.post("/api/chat", json={"message": "Olá JARVIS"})
    assert result.status_code == 200
    payload = result.json()
    assert payload["assistant_message"]["content"] == "Bem-vindo, senhor."
    assert payload["user_message"]["content"] == "Olá JARVIS"
    assert payload["conversation"]["title"] == "Olá JARVIS"
    assert payload["messages"][-1]["role"] == "assistant"

    messages = client.get(
        f"/api/conversations/{payload['conversation_id']}/messages"
    ).json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_chat_validation_errors(client: TestClient) -> None:
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x", "extra": True}).status_code == 422


def test_confirmation_flow_via_api(
    client: TestClient, workspace: Path
) -> None:
    container = client.app.state.container
    container.settings_service.update({"allowed_roots": [str(workspace)]})
    target = workspace / "api.txt"
    provider = FakeProvider(
        [
            response(
                "",
                calls=[
                    tool_call("create_file", {"path": str(target), "content": "via api"})
                ],
            ),
            response("Arquivo criado pela API."),
        ]
    )
    install_provider(client, provider)

    chat = client.post("/api/chat", json={"message": "Crie o arquivo"}).json()
    assert len(chat["pending_actions"]) == 1
    action = chat["pending_actions"][0]
    assert action["status"] == "pending"
    assert not target.exists()

    approved = client.post(
        f"/api/actions/{action['id']}/approve", json={"approve": True, "speak": False}
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["action"]["status"] == "executed"
    assert payload["assistant_message"]["content"] == "Arquivo criado pela API."
    assert target.read_text(encoding="utf-8") == "via api"


def test_memory_crud_and_search(client: TestClient) -> None:
    created = client.post(
        "/api/memories",
        json={
            "content": "Prefiro respostas curtas e diretas",
            "category": "preference",
            "persistent": True,
        },
    )
    assert created.status_code == 200
    memory = created.json()["memory"]
    assert memory["persistent"] is True

    search = client.get("/api/memories/search", params={"q": "respostas curtas"})
    assert search.status_code == 200
    assert search.json()["memories"][0]["id"] == memory["id"]

    updated = client.patch(
        f"/api/memories/{memory['id']}",
        json={"content": "Prefiro respostas objetivas", "persistent": False},
    )
    assert updated.status_code == 200
    assert updated.json()["memory"]["content"] == "Prefiro respostas objetivas"
    assert updated.json()["memory"]["persistent"] is False

    assert client.delete(f"/api/memories/{memory['id']}").status_code == 200
    assert client.delete(f"/api/memories/{memory['id']}").status_code == 404


def test_memory_rejects_secrets(client: TestClient) -> None:
    result = client.post(
        "/api/memories",
        json={"content": "minha senha: super-secreta-123", "category": "other"},
    )
    assert result.status_code == 422
    assert "credencial" in result.json()["message"]


def test_settings_update_and_validation(client: TestClient) -> None:
    current = client.get("/api/settings").json()["settings"]
    assert current["provider"] == "ollama"

    updated = client.put(
        "/api/settings", json={"values": {"temperature": 0.7, "max_agent_steps": 6}}
    )
    assert updated.status_code == 200
    assert updated.json()["settings"]["temperature"] == 0.7
    assert updated.json()["settings"]["max_agent_steps"] == 6

    unknown = client.put("/api/settings", json={"values": {"nao_existe": 1}})
    assert unknown.status_code == 422

    invalid = client.put("/api/settings", json={"values": {"temperature": 9}})
    assert invalid.status_code == 422


def test_plan_endpoint(client: TestClient) -> None:
    conversation = client.post("/api/conversations", json={"title": "Plano"}).json()[
        "conversation"
    ]
    steps = [
        {"title": "Analisar", "status": "done", "note": "ok"},
        {"title": "Executar", "status": "in_progress", "note": ""},
    ]
    saved = client.put(
        f"/api/conversations/{conversation['id']}/plan", json={"steps": steps}
    )
    assert saved.status_code == 200
    assert saved.json()["plan"][0]["title"] == "Analisar"

    fetched = client.get(f"/api/conversations/{conversation['id']}/plan")
    assert fetched.status_code == 200
    assert len(fetched.json()["plan"]) == 2


def test_voice_status_and_stop(client: TestClient) -> None:
    status = client.get("/api/voice/status")
    assert status.status_code == 200
    assert status.json()["voice"]["wake_word"] == "jarvis"
    assert client.post("/api/voice/stop").status_code == 200


def test_websocket_hello_and_ping(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["data"]["runtime"]["online"] is True
        websocket.send_json({"type": "ping", "data": 123})
        pong = websocket.receive_json()
        assert pong["type"] == "pong"
        assert pong["data"]["timestamp"] == 123


def test_unknown_conversation_returns_404(client: TestClient) -> None:
    assert client.get("/api/conversations/conv_inexistente").status_code == 404
    assert client.get("/api/conversations/conv_inexistente/messages").status_code == 404
