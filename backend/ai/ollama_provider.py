"""Provedor Ollama para modelos locais."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.ai.llm_provider import LLMProvider
from backend.ai.types import LLMResponse, ToolCall, content_to_text, parse_arguments
from backend.core.errors import ProviderResponseError
from backend.core.utils import new_id

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"
    label = "Ollama (local)"
    requires_api_key = False
    model_hints = ["llama3.1", "qwen2.5", "mistral", "deepseek-r1"]

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
        num_ctx: int = 8192,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, timeout=timeout)
        self.num_ctx = max(2048, min(32768, int(num_ctx)))

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            item: dict[str, Any] = {"role": role, "content": content_to_text(message.get("content"))}
            if role == "assistant" and message.get("tool_calls"):
                calls: list[dict[str, Any]] = []
                for call in message["tool_calls"]:
                    function = call.get("function") or {}
                    arguments, _ = parse_arguments(function.get("arguments"))
                    calls.append(
                        {
                            "id": call.get("id") or new_id("call"),
                            "type": "function",
                            "function": {"name": function.get("name", ""), "arguments": arguments},
                        }
                    )
                item["tool_calls"] = calls
            if role == "tool":
                if message.get("name"):
                    item["tool_name"] = message["name"]
                if message.get("tool_call_id"):
                    item["tool_call_id"] = message["tool_call_id"]
            converted.append(item)
        return converted

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._convert_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools
        data = await self._request_json("POST", "/api/chat", payload=payload)
        if not isinstance(data, dict):
            raise ProviderResponseError("Ollama retornou uma resposta inesperada")
        if data.get("error"):
            raise ProviderResponseError(f"Ollama retornou um erro: {data['error']}")
        message = data.get("message") or {}
        tool_calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function") or {}
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            arguments, parse_error = parse_arguments(function.get("arguments"))
            tool_calls.append(
                ToolCall(
                    id=str(raw_call.get("id") or new_id("call")),
                    name=name,
                    arguments=arguments,
                    raw_arguments=json.dumps(arguments, ensure_ascii=False),
                    parse_error=parse_error,
                )
            )
        return LLMResponse(
            content=content_to_text(message.get("content")),
            tool_calls=tool_calls,
            finish_reason="stop" if data.get("done", True) else "length",
            usage={
                "prompt_tokens": data.get("prompt_eval_count"),
                "completion_tokens": data.get("eval_count"),
            },
            model=str(data.get("model") or model),
            provider=self.name,
        )

    async def list_models(self) -> list[str]:
        data = await self._request_json("GET", "/api/tags")
        models: list[str] = []
        if isinstance(data, dict):
            for item in data.get("models", []):
                if isinstance(item, dict) and item.get("name"):
                    models.append(str(item["name"]))
        return sorted(dict.fromkeys(models))
