"""Provedores compatíveis com OpenAI Chat Completions."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.ai.llm_provider import LLMProvider
from backend.ai.types import LLMResponse, ToolCall, content_to_text, parse_arguments
from backend.core.errors import ProviderResponseError
from backend.core.utils import new_id

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"
    label = "API compatível com OpenAI"
    requires_api_key = True

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

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
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            data = await self._request_json("POST", "/chat/completions", payload=payload)
        except ProviderResponseError as exc:
            message = str(exc).lower()
            if any(token in message for token in ("max_tokens", "temperature", "unsupported parameter")):
                # Modelos de raciocínio podem exigir max_completion_tokens e rejeitar temperature.
                payload.pop("temperature", None)
                if "max_tokens" in payload:
                    payload["max_completion_tokens"] = payload.pop("max_tokens")
                data = await self._request_json(
                    "POST", "/chat/completions", payload=payload, retries=0
                )
            else:
                raise
        return self._parse_response(data, model)

    def _parse_response(self, data: Any, model: str) -> LLMResponse:
        if not isinstance(data, dict):
            raise ProviderResponseError(f"{self.label} retornou uma resposta inesperada")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            error = data.get("error")
            raise ProviderResponseError(
                f"{self.label} não retornou escolhas na resposta"
                + (f": {error}" if error else "")
            )
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        content = content_to_text(message.get("content"))
        tool_calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            if not isinstance(raw_call, dict):
                continue
            function = raw_call.get("function") or {}
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            raw_arguments = function.get("arguments")
            arguments, parse_error = parse_arguments(raw_arguments)
            if isinstance(raw_arguments, dict):
                raw_arguments = json.dumps(raw_arguments, ensure_ascii=False)
            tool_calls.append(
                ToolCall(
                    id=str(raw_call.get("id") or new_id("call")),
                    name=name,
                    arguments=arguments,
                    raw_arguments=raw_arguments or "",
                    parse_error=parse_error,
                )
            )
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage=usage,
            model=str(data.get("model") or model),
            provider=self.name,
        )


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    label = "OpenAI"
    model_hints = ["gpt-4.1", "gpt-4o", "gpt-4o-mini", "o3-mini"]


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    label = "DeepSeek"
    model_hints = ["deepseek-chat", "deepseek-reasoner"]


class CustomOpenAIProvider(OpenAICompatibleProvider):
    name = "custom"
    label = "API personalizada"
    requires_api_key = False
