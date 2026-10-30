"""Pesquisa e automação básica do navegador padrão."""

from __future__ import annotations

import logging
import time
import urllib.parse
import webbrowser
from typing import Any

from backend.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

_SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
}


def _open_url(url: str) -> bool:
    return bool(webbrowser.open(url, new=2))


class BrowserSearchTool(BaseTool):
    name = "browser_search"
    description = "Abre uma pesquisa no navegador padrão (Google, Bing ou DuckDuckGo)."
    permission_level = 1
    category = "browser"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "engine": {"type": "string", "enum": list(_SEARCH_ENGINES), "default": "google"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        engine = arguments.get("engine", "google")
        url = _SEARCH_ENGINES[engine].format(query=urllib.parse.quote_plus(arguments["query"]))
        if not _open_url(url):
            return ToolResult.fail("Não foi possível abrir o navegador padrão")
        return ToolResult.ok(
            {"query": arguments["query"], "engine": engine, "url": url},
            display=f"Pesquisando por “{arguments['query']}” no {engine}",
        )


class OpenUrlTool(BaseTool):
    name = "open_url"
    description = "Abre uma URL http/https no navegador padrão."
    permission_level = 1
    category = "browser"
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 2048}},
        "required": ["url"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raw = arguments["url"].strip()
        if not raw.lower().startswith(("http://", "https://")):
            raw = "https://" + raw
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ToolResult.fail("URL inválida; use http:// ou https://")
        if not _open_url(raw):
            return ToolResult.fail("Não foi possível abrir o navegador padrão")
        return ToolResult.ok({"url": raw}, display=f"Abrindo {parsed.netloc}")


class BrowserAutomationTool(BaseTool):
    name = "browser_automation"
    description = (
        "Automatiza o navegador ativo com teclado e mouse: abrir URL, nova aba, fechar aba, recarregar, "
        "voltar, avançar, focar barra de endereço, digitar texto, pressionar tecla e atalhos. "
        "As ações de teclado agem sobre a janela em foco e exigem confirmação."
    )
    permission_level = 2
    category = "browser"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "open_url",
                    "new_tab",
                    "close_tab",
                    "reload",
                    "back",
                    "forward",
                    "focus_address_bar",
                    "type_text",
                    "press_key",
                    "hotkey",
                ],
            },
            "url": {"type": "string", "maxLength": 2048},
            "text": {"type": "string", "maxLength": 2000},
            "key": {"type": "string", "maxLength": 40},
            "keys": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def get_permission_level(self, arguments: dict[str, Any]) -> int:
        return 1 if arguments.get("action") == "open_url" else 2

    def summarize(self, arguments: dict[str, Any]) -> str:
        return f"Automação do navegador: {arguments.get('action')}"

    def _pyautogui(self) -> Any:
        try:
            import pyautogui
        except ImportError as exc:
            raise RuntimeError("pyautogui não está instalado") from exc
        pyautogui.FAILSAFE = True
        return pyautogui

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        action = arguments["action"]
        if action == "open_url":
            url = arguments.get("url", "").strip()
            if not url:
                return ToolResult.fail("Informe url para action=open_url")
            if not url.lower().startswith(("http://", "https://")):
                url = "https://" + url
            if not _open_url(url):
                return ToolResult.fail("Não foi possível abrir o navegador padrão")
            return ToolResult.ok({"url": url}, display=f"Abrindo {url}")
        try:
            gui = self._pyautogui()
            if action == "new_tab":
                gui.hotkey("ctrl", "t")
            elif action == "close_tab":
                gui.hotkey("ctrl", "w")
            elif action == "reload":
                gui.press("f5")
            elif action == "back":
                gui.hotkey("alt", "left")
            elif action == "forward":
                gui.hotkey("alt", "right")
            elif action == "focus_address_bar":
                gui.hotkey("ctrl", "l")
            elif action == "type_text":
                text = arguments.get("text")
                if text is None:
                    return ToolResult.fail("Informe text para action=type_text")
                gui.write(text, interval=0.02)
            elif action == "press_key":
                key = arguments.get("key")
                if not key:
                    return ToolResult.fail("Informe key para action=press_key")
                gui.press(key)
            elif action == "hotkey":
                keys = arguments.get("keys") or []
                if not keys:
                    return ToolResult.fail("Informe keys para action=hotkey")
                gui.hotkey(*keys)
            else:  # pragma: no cover - enum validado
                return ToolResult.fail(f"Ação não suportada: {action}")
            time.sleep(0.15)
        except Exception as exc:
            return ToolResult.fail(f"Falha na automação do navegador: {exc}")
        return ToolResult.ok({"action": action}, display=f"Automação executada: {action}")
