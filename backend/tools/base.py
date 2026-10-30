"""Contratos base para ferramentas controladas."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator

from backend.config.settings import AppSettings, RuntimeSettings
from backend.core.events import EventBus, StateManager
from backend.core.utils import coerce_json_safe, truncate
from backend.tools.coercion import coerce_arguments
from backend.tools.path_guard import PathGuard

if TYPE_CHECKING:
    from backend.database.repositories import MemoryRepository

logger = logging.getLogger(__name__)


class ToolValidationError(ValueError):
    pass


@dataclass(slots=True)
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    display: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        data: Any = None,
        *,
        display: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolResult:
        return cls(True, data=data, display=display, metadata=metadata or {})

    @classmethod
    def fail(cls, error: str, *, data: Any = None, display: str | None = None) -> ToolResult:
        return cls(False, data=data, error=error, display=display or error)

    def to_dict(self) -> dict[str, Any]:
        return coerce_json_safe(
            {
                "success": self.success,
                "data": self.data,
                "error": self.error,
                "display": self.display,
                "metadata": self.metadata,
            }
        )


@dataclass(slots=True)
class ToolContext:
    app_settings: AppSettings
    runtime_settings: RuntimeSettings
    path_guard: PathGuard
    data_dir: Path
    event_bus: EventBus
    state: StateManager
    user_home: Path = field(default_factory=Path.home)
    process_id: int = 0
    memory_repo: MemoryRepository | None = None
    conversation_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}
    permission_level: int = 1
    category: str = "general"
    enabled: bool = True
    blocking: bool = True

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def get_permission_level(self, arguments: dict[str, Any]) -> int:
        return max(1, min(3, int(self.permission_level)))

    def summarize(self, arguments: dict[str, Any]) -> str:
        payload = json.dumps(arguments, ensure_ascii=False, default=str)
        return f"{self.name}: {truncate(payload, 240)}"

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ToolValidationError("Os argumentos da ferramenta devem ser um objeto JSON")
        normalized = coerce_arguments(arguments, self.parameters)
        validator = Draft202012Validator(self.parameters)
        errors = sorted(validator.iter_errors(normalized), key=lambda error: list(error.path))
        if errors:
            details = []
            for error in errors[:5]:
                location = ".".join(str(part) for part in error.path) or "argumentos"
                details.append(f"{location}: {error.message}")
            raise ToolValidationError("; ".join(details))
        return normalized

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError

    async def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            validated = self.validate_arguments(arguments)
            result = await self.execute(validated, context)
            if not isinstance(result, ToolResult):
                return ToolResult.fail("A ferramenta retornou um resultado inválido")
            return result
        except ToolValidationError as exc:
            return ToolResult.fail(f"Argumentos inválidos: {exc}")
        except Exception as exc:  # a falha de uma ferramenta nunca derruba o agente
            logger.exception("Erro ao executar a ferramenta %s", self.name)
            return ToolResult.fail(f"Falha em {self.name}: {exc}")
