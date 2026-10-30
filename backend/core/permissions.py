"""Política de permissões em três níveis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.config.settings import RuntimeSettings
from backend.core.settings_service import SettingsService
from backend.tools.base import BaseTool


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    requires_confirmation: bool
    level: int
    reason: str
    blocked: bool = False


class PermissionManager:
    def __init__(self, settings: SettingsService) -> None:
        self.settings = settings

    def evaluate(self, tool: BaseTool, arguments: dict[str, Any]) -> PermissionDecision:
        return self.evaluate_level(tool.get_permission_level(arguments), tool.name)

    def evaluate_level(self, level: int, tool_name: str = "ferramenta") -> PermissionDecision:
        settings: RuntimeSettings = self.settings.get()
        level = max(1, min(3, int(level)))
        if not settings.allow_level3 and level >= 3:
            return PermissionDecision(
                allowed=False,
                requires_confirmation=False,
                level=3,
                reason="Ações críticas estão desativadas nas configurações (allow_level3=false)",
                blocked=True,
            )
        if level == 1:
            return PermissionDecision(
                allowed=True,
                requires_confirmation=False,
                level=1,
                reason="Ação simples autorizada",
            )
        if level == 2:
            if settings.confirm_level2:
                return PermissionDecision(
                    allowed=False,
                    requires_confirmation=True,
                    level=2,
                    reason="Ação que modifica dados exige confirmação",
                )
            return PermissionDecision(
                allowed=True,
                requires_confirmation=False,
                level=2,
                reason="Ação de nível 2 autorizada pelas configurações",
            )
        return PermissionDecision(
            allowed=False,
            requires_confirmation=True,
            level=3,
            reason="Ação crítica exige confirmação explícita do usuário",
        )
