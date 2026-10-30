"""Captura de tela e automação de mouse/teclado."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from backend.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ScreenshotTool(BaseTool):
    name = "screenshot"
    description = (
        "Captura a tela atual e salva como PNG. Sem path, salva em data/screenshots. "
        "A imagem não é enviada ao modelo; retorna o caminho do arquivo."
    )
    permission_level = 1
    category = "automation"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Arquivo .png de destino (opcional)."},
            "all_screens": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            from PIL import ImageGrab
        except ImportError:
            return ToolResult.fail("Pillow não está instalado; captura de tela indisponível")
        if arguments.get("path"):
            path = context.path_guard.resolve(arguments["path"], for_write=True)
            if path.suffix.lower() != ".png":
                path = path.with_suffix(".png")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = context.data_dir / "screenshots" / f"jarvis_{timestamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            image = ImageGrab.grab(all_screens=bool(arguments.get("all_screens", True)))
            image.save(path, "PNG")
        except Exception as exc:
            return ToolResult.fail(f"Não foi possível capturar a tela: {exc}")
        return ToolResult.ok(
            {"path": str(path), "width": image.width, "height": image.height},
            display=f"Captura salva em {path}",
        )


class ComputerInteractionTool(BaseTool):
    name = "computer_interaction"
    description = (
        "Automação real de mouse e teclado: mover, clicar, arrastar, rolar, digitar, pressionar teclas "
        "e atalhos. Ações de entrada exigem confirmação. Use get_mouse_position/get_screen_size para "
        "consultar o estado sem alterar nada."
    )
    permission_level = 2
    category = "automation"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "move_mouse",
                    "click",
                    "double_click",
                    "right_click",
                    "drag",
                    "scroll",
                    "type_text",
                    "press_key",
                    "hotkey",
                    "get_mouse_position",
                    "get_screen_size",
                ],
            },
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "x2": {"type": "integer"},
            "y2": {"type": "integer"},
            "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            "clicks": {"type": "integer", "minimum": 1, "maximum": 5, "default": 1},
            "amount": {"type": "integer", "minimum": -50, "maximum": 50, "default": -3},
            "text": {"type": "string", "maxLength": 5000},
            "key": {"type": "string", "maxLength": 40},
            "keys": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "duration": {"type": "number", "minimum": 0, "maximum": 10, "default": 0.2},
            "interval": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.02},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def get_permission_level(self, arguments: dict[str, Any]) -> int:
        return 1 if arguments.get("action", "").startswith("get_") else 2

    def summarize(self, arguments: dict[str, Any]) -> str:
        action = arguments.get("action", "?")
        if action in {"type_text", "press_key", "hotkey"}:
            return f"Automação de teclado: {action}"
        if action in {"click", "double_click", "right_click", "drag", "scroll", "move_mouse"}:
            return f"Automação de mouse: {action}"
        return f"Interação com o computador: {action}"

    def _gui(self) -> Any:
        try:
            import pyautogui
        except ImportError as exc:
            raise RuntimeError("pyautogui não está instalado") from exc
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        return pyautogui

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        action = arguments["action"]
        try:
            gui = self._gui()
            width, height = gui.size()
            if action == "get_mouse_position":
                position = gui.position()
                return ToolResult.ok(
                    {"x": position.x, "y": position.y, "screen_width": width, "screen_height": height},
                    display=f"Mouse em ({position.x}, {position.y})",
                )
            if action == "get_screen_size":
                return ToolResult.ok(
                    {"width": width, "height": height},
                    display=f"Tela: {width}x{height}",
                )
            if action == "move_mouse":
                x, y = _require_point(arguments, "x", "y", width, height)
                gui.moveTo(x, y, duration=float(arguments.get("duration", 0.2)))
            elif action in {"click", "double_click", "right_click"}:
                x, y = _optional_point(arguments, width, height)
                button = "right" if action == "right_click" else arguments.get("button", "left")
                clicks = 2 if action == "double_click" else int(arguments.get("clicks", 1))
                if x is None:
                    gui.click(button=button, clicks=clicks)
                else:
                    gui.click(x=x, y=y, button=button, clicks=clicks)
            elif action == "drag":
                x, y = _require_point(arguments, "x", "y", width, height)
                x2, y2 = _require_point(arguments, "x2", "y2", width, height)
                gui.moveTo(x, y)
                gui.dragTo(x2, y2, duration=float(arguments.get("duration", 0.2)), button=arguments.get("button", "left"))
            elif action == "scroll":
                amount = int(arguments.get("amount", -3))
                x, y = _optional_point(arguments, width, height)
                if x is None:
                    gui.scroll(amount)
                else:
                    gui.scroll(amount, x=x, y=y)
            elif action == "type_text":
                text = arguments.get("text")
                if text is None:
                    return ToolResult.fail("Informe text para action=type_text")
                gui.write(text, interval=float(arguments.get("interval", 0.02)))
            elif action == "press_key":
                key = arguments.get("key")
                if not key:
                    return ToolResult.fail("Informe key para action=press_key")
                gui.press(key, presses=int(arguments.get("clicks", 1)))
            elif action == "hotkey":
                keys = arguments.get("keys") or []
                if not keys:
                    return ToolResult.fail("Informe keys para action=hotkey")
                gui.hotkey(*keys)
            else:  # pragma: no cover
                return ToolResult.fail(f"Ação não suportada: {action}")
        except Exception as exc:
            return ToolResult.fail(f"Falha na automação: {exc}")
        return ToolResult.ok({"action": action}, display=f"Interação executada: {action}")


def _require_point(arguments: dict[str, Any], x_key: str, y_key: str, width: int, height: int) -> tuple[int, int]:
    x, y = arguments.get(x_key), arguments.get(y_key)
    if x is None or y is None:
        raise ValueError(f"Informe {x_key} e {y_key}")
    x, y = int(x), int(y)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"Coordenada fora da tela ({width}x{height}): {x},{y}")
    return x, y


def _optional_point(arguments: dict[str, Any], width: int, height: int) -> tuple[int | None, int | None]:
    if arguments.get("x") is None and arguments.get("y") is None:
        return None, None
    return _require_point(arguments, "x", "y", width, height)
