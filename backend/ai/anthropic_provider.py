"""Provedor Anthropic Messages API com conversão de ferramentas."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.ai.llm_provider import LLMProvider
from backend.ai.types import LLMResponse, ToolCall, content_to_text, parse_arguments
from backend.core.errors import ProviderResponseError
from backend.core.utils import new_id

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    label = "Anthropic"
    model_hints = ["claude-sonnet-4-5", "claude-opus-4-1", "claude-3-5-haiku-latest"]

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _convert_messages(self, messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        def append(role: str, blocks: list[dict[str, Any]]) -> None:
            if not blocks:
                return
            if converted and converted[-1]["role"] == role:
                converted[-1]["content"].extend(blocks)
            else:
                converted.append({"role": role, "content": list(blocks)})

        for message in messages:
            role = message.get("role")
            content = content_to_text(message.get("content"))
            if role == "system":
                if content:
                    system_parts.append(content)
                continue
            if role == "user":
                if content:
                    append("user", [{"type": "text", "text": content}])
                continue
            if role == "assistant":
                blocks: list[dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    arguments, _error = parse_arguments(function.get("arguments"))
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.get("id") or new_id("toolu"),
                            "name": function.get("name", ""),
                            "input": arguments,
                        }
                    )
                append("assistant", blocks)
                continue
            if role == "tool":
                result_text = content or json.dumps(
                    {"success": False, "error": "resultado vazio"}, ensure_ascii=False
                )
                append(
                    "user",
                    [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id") or "",
                            "content": result_text,
                        }
                    ],
                )
        if converted and converted[0]["role"] != "user":
            converted.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continuação da conversa)"}]})
        return "\n\n".join(system_parts), converted

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        system, converted = self._convert_messages(messages)
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": item["function"]["name"],
                    "description": item["function"].get("description", ""),
                    "input_schema": item["function"].get("parameters", {"type": "object", "properties": {}}),
                }
                for item in tools
                if item.get("type") == "function" and item.get("function")
            ]
            payload["tool_choice"] = {"type": "auto"}
        data = await self._request_json("POST", "/messages", payload=payload)
        return self._parse_response(data, model)

    def _parse_response(self, data: Any, model: str) -> LLMResponse:
        if not isinstance(data, dict):
            raise ProviderResponseError("Anthropic retornou uma resposta inesperada")
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise ProviderResponseError("Anthropic não retornou blocos de conteúdo")
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                raw = block.get("input") or {}
                arguments, parse_error = parse_arguments(raw)
                tool_calls.append(
                    ToolCall(
                        id=str(block.get("id") or new_id("toolu")),
                        name=str(block.get("name") or ""),
                        arguments=arguments,
                        raw_arguments=json.dumps(raw, ensure_ascii=False),
                        parse_error=parse_error,
                    )
                )
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return LLMResponse(
            content="\n".join(part for part in text_parts if part),
            tool_calls=tool_calls,
            finish_reason=str(data.get("stop_reason") or "stop"),
            usage=usage,
            model=str(data.get("model") or model),
            provider=self.name,
        )

    async def list_models(self) -> list[str]:
        data = await self._request_json("GET", "/models")
        models: list[str] = []
        if isinstance(data, dict):
            for item in data.get("data", []):
                if isinstance(item, dict) and item.get("id"):
                    models.append(str(item["id"]))
        return sorted(dict.fromkeys(models))
