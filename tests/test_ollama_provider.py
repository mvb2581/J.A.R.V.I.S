"""Testes do provedor Ollama: payload e contexto configurável."""

from __future__ import annotations

from typing import Any

import pytest

from backend.ai.ollama_provider import OllamaProvider


async def test_chat_sends_configured_context(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OllamaProvider(
        api_key="",
        base_url="http://127.0.0.1:11434",
        timeout=5.0,
        num_ctx=8192,
    )
    captured: dict[str, Any] = {}

    async def fake_request_json(
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"message": {"content": "ok"}, "done": True}

    monkeypatch.setattr(provider, "_request_json", fake_request_json)

    result = await provider.chat(
        [{"role": "user", "content": "olá"}],
        None,
        model="llama3.1:8b",
    )

    assert result.content == "ok"
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/chat"
    options = captured["payload"]["options"]
    assert options["num_ctx"] == 8192
    assert options["num_predict"] == 2048
