"""Registro extensível de ferramentas do JARVIS."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from backend.tools.applications import (
    CloseApplicationTool,
    ManageWindowsTool,
    OpenApplicationTool,
    OpenPathTool,
)
from backend.tools.automation import ComputerInteractionTool, ScreenshotTool
from backend.tools.base import BaseTool, ToolContext, ToolResult
from backend.tools.browser import BrowserAutomationTool, BrowserSearchTool, OpenUrlTool
from backend.tools.filesystem import (
    CopyFileTool,
    CreateDirectoryTool,
    CreateFileTool,
    DeleteFileTool,
    EditFileTool,
    GetFileInfoTool,
    ListDirectoryTool,
    MoveFileTool,
    OrganizeFolderTool,
    ReadFileTool,
    SearchFilesTool,
)
from backend.tools.memory import DeleteMemoryTool, ListMemoriesTool, SaveMemoryTool, SearchMemoryTool
from backend.tools.planning import UpdatePlanTool
from backend.tools.system import (
    ControlMediaTool,
    ControlVolumeTool,
    GetProcessListTool,
    GetResourceUsageTool,
    GetSystemInformationTool,
)
from backend.tools.terminal import ExecuteTerminalCommandTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self, tools: Iterable[BaseTool] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ValueError("Toda ferramenta precisa de um nome")
        if tool.name in self._tools:
            raise ValueError(f"Ferramenta duplicada: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all(self) -> list[BaseTool]:
        return sorted(self._tools.values(), key=lambda tool: (tool.category, tool.name))

    def definitions(self, enabled_only: bool = True) -> list[dict[str, Any]]:
        tools = self.all()
        if enabled_only:
            tools = [tool for tool in tools if tool.enabled]
        return [tool.definition() for tool in tools]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "permission_level": tool.permission_level,
                "parameters": tool.parameters,
                "enabled": tool.enabled,
            }
            for tool in self.all()
        ]

    async def run(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult.fail(f"Ferramenta desconhecida: {name}")
        return await tool.run(arguments, context)


def build_default_registry() -> ToolRegistry:
    """Instancia todas as ferramentas. Adicionar uma ferramenta é só registrá-la aqui."""
    tools: list[BaseTool] = [
        # Arquivos
        SearchFilesTool(),
        ListDirectoryTool(),
        ReadFileTool(),
        GetFileInfoTool(),
        CreateFileTool(),
        EditFileTool(),
        CreateDirectoryTool(),
        MoveFileTool(),
        CopyFileTool(),
        DeleteFileTool(),
        OrganizeFolderTool(),
        # Aplicativos e janelas
        OpenApplicationTool(),
        OpenPathTool(),
        CloseApplicationTool(),
        ManageWindowsTool(),
        # Terminal
        ExecuteTerminalCommandTool(),
        # Sistema
        GetSystemInformationTool(),
        GetResourceUsageTool(),
        GetProcessListTool(),
        ControlVolumeTool(),
        ControlMediaTool(),
        # Navegador
        BrowserSearchTool(),
        OpenUrlTool(),
        BrowserAutomationTool(),
        # Automação
        ScreenshotTool(),
        ComputerInteractionTool(),
        # Memória e planejamento
        SaveMemoryTool(),
        SearchMemoryTool(),
        ListMemoriesTool(),
        DeleteMemoryTool(),
        UpdatePlanTool(),
    ]
    return ToolRegistry(tools)
