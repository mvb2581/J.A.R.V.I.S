"""Tipos normalizados para conversas e chamadas de ferramentas entre provedores."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""
    parse_error: str | None = None

    def to_openai(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.raw_arguments or json.dumps(self.arguments, ensure_ascii=False)},
        }


@dataclass(slots=True)
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    provider: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


@dataclass(slots=True)
class ProviderStatus:
    provider: str
    configured: bool
    reachable: bool
    message: str
    models: list[str] = field(default_factory=list)


def parse_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    """Aceita string JSON (OpenAI) ou objeto (Ollama) e devolve argumentos + erro."""
    if isinstance(raw, dict):
        return raw, None
    if raw is None:
        return {}, None
    if isinstance(raw, str):
        if not raw.strip():
            return {}, None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {}, f"JSON inválido nos argumentos da ferramenta: {exc}"
        if not isinstance(value, dict):
            return {}, "Os argumentos da ferramenta devem ser um objeto JSON"
        return value, None
    return {}, f"Tipo de argumentos não suportado: {type(raw).__name__}"


def content_to_text(content: Any) -> str:
    """Normaliza content string ou lista de blocos de conteúdo."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") in {"text", "output_text"}:
                    parts.append(str(block.get("text", "")))
                elif "content" in block and isinstance(block["content"], str):
                    parts.append(block["content"])
        return "\n".join(part for part in parts if part)
    return str(content)
