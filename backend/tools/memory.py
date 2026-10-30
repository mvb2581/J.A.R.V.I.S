"""Ferramentas de memória de longo prazo, sempre visíveis e gerenciáveis."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from backend.core.utils import is_probably_secret
from backend.tools.base import BaseTool, ToolContext, ToolResult


def _require_repo(context: ToolContext) -> Any:
    if context.memory_repo is None:
        raise RuntimeError("Repositório de memória indisponível")
    return context.memory_repo


def _as_dict(record: Any) -> dict[str, Any]:
    return asdict(record)


class SaveMemoryTool(BaseTool):
    name = "save_memory"
    description = (
        "Salva uma preferência, fato ou informação de projeto que o usuário pediu explicitamente para "
        "lembrar. Nunca salve senhas, tokens, chaves de API ou dados sensíveis."
    )
    permission_level = 1
    category = "memory"
    blocking = False
    parameters = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "minLength": 2, "maxLength": 2000},
            "category": {
                "type": "string",
                "enum": ["preference", "fact", "project", "contact", "other"],
                "default": "other",
            },
            "persistent": {"type": "boolean", "default": True},
        },
        "required": ["content"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        content = arguments["content"].strip()
        if is_probably_secret(content):
            return ToolResult.fail(
                "A informação parece conter uma credencial. Não armazene segredos na memória."
            )
        repo = _require_repo(context)
        record = repo.add(
            content,
            category=arguments.get("category", "other"),
            source="assistant",
            persistent=bool(arguments.get("persistent", True)),
            conversation_id=context.conversation_id,
        )
        return ToolResult.ok(
            _as_dict(record),
            display=f"Memória salva: {content[:120]}",
        )


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "Pesquisa memórias persistentes e temporárias por palavras-chave."
    permission_level = 1
    category = "memory"
    blocking = False
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 300},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        repo = _require_repo(context)
        records = repo.search(
            arguments["query"],
            limit=int(arguments.get("limit", 8)),
            include_temporary=True,
            conversation_id=context.conversation_id,
        )
        return ToolResult.ok(
            {"memories": [_as_dict(record) for record in records]},
            display=f"{len(records)} memória(s) encontrada(s)",
        )


class ListMemoriesTool(BaseTool):
    name = "list_memories"
    description = "Lista as memórias armazenadas, opcionalmente filtrando por categoria."
    permission_level = 1
    category = "memory"
    blocking = False
    parameters = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["preference", "fact", "project", "contact", "other"],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30},
        },
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        repo = _require_repo(context)
        records = repo.list(category=arguments.get("category"), limit=int(arguments.get("limit", 30)))
        return ToolResult.ok(
            {"memories": [_as_dict(record) for record in records]},
            display=f"{len(records)} memória(s) listada(s)",
        )


class DeleteMemoryTool(BaseTool):
    name = "delete_memory"
    description = "Exclui uma memória pelo ID. Use search_memory ou list_memories para obter o ID."
    permission_level = 2
    category = "memory"
    blocking = False
    parameters = {
        "type": "object",
        "properties": {"memory_id": {"type": "string", "minLength": 3, "maxLength": 80}},
        "required": ["memory_id"],
        "additionalProperties": False,
    }

    def summarize(self, arguments: dict[str, Any]) -> str:
        return f"Excluir memória {arguments.get('memory_id', '?')}"

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        repo = _require_repo(context)
        deleted = repo.delete(arguments["memory_id"])
        if not deleted:
            return ToolResult.fail("Memória não encontrada")
        return ToolResult.ok({"memory_id": arguments["memory_id"]}, display="Memória excluída")
