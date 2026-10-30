"""Abertura/fechamento de aplicativos e controle de janelas do Windows."""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

import psutil

from backend.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

_PROTECTED_PROCESSES = {
    "system",
    "system idle process",
    "registry",
    "memory compression",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "smss.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "explorer.exe",
    "sihost.exe",
    "ctfmon.exe",
    "taskhostw.exe",
    "audiodg.exe",
    "securityhealthservice.exe",
    "msmpeng.exe",
}

_ALIASES = {
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "code": "vscode",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "notepad": "notepad",
    "bloco de notas": "notepad",
    "explorer": "explorer",
    "explorador de arquivos": "explorer",
    "terminal": "terminal",
    "windows terminal": "terminal",
    "powershell": "powershell",
    "cmd": "cmd",
    "prompt de comando": "cmd",
    "calculadora": "calculator",
    "calculator": "calculator",
    "paint": "paint",
    "spotify": "spotify",
    "vlc": "vlc",
    "discord": "discord",
    "steam": "steam",
    "word": "word",
    "excel": "excel",
    "powerpoint": "powerpoint",
    "outlook": "outlook",
    "teams": "teams",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
}

_APP_CANDIDATES: dict[str, dict[str, list[str]]] = {
    "vscode": {
        "paths": [
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%ProgramFiles%\Microsoft VS Code\Code.exe",
        ],
        "commands": ["code.cmd", "code"],
    },
    "chrome": {
        "paths": [
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        ],
        "commands": ["chrome.exe", "chrome"],
    },
    "edge": {
        "paths": [
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        ],
        "commands": ["msedge.exe", "msedge"],
    },
    "firefox": {
        "paths": [
            r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
        ],
        "commands": ["firefox.exe", "firefox"],
    },
    "notepad": {"paths": [r"%WINDIR%\System32\notepad.exe"], "commands": ["notepad.exe"]},
    "explorer": {"paths": [r"%WINDIR%\explorer.exe"], "commands": ["explorer.exe"]},
    "terminal": {"paths": [r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"], "commands": ["wt.exe"]},
    "powershell": {"paths": [r"%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe"], "commands": ["powershell.exe"]},
    "cmd": {"paths": [r"%WINDIR%\System32\cmd.exe"], "commands": ["cmd.exe"]},
    "calculator": {"paths": [r"%WINDIR%\System32\calc.exe"], "commands": ["calc.exe"]},
    "paint": {"paths": [r"%WINDIR%\System32\mspaint.exe"], "commands": ["mspaint.exe"]},
    "spotify": {
        "paths": [r"%APPDATA%\Spotify\Spotify.exe", r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"],
        "commands": ["Spotify.exe"],
    },
    "vlc": {"paths": [r"%ProgramFiles%\VideoLAN\VLC\vlc.exe"], "commands": ["vlc.exe"]},
    "discord": {
        "paths": [r"%LOCALAPPDATA%\Discord\Update.exe", r"%LOCALAPPDATA%\Discord\app-*\Discord.exe"],
        "commands": ["Discord.exe"],
    },
    "steam": {"paths": [r"%ProgramFiles(x86)%\Steam\steam.exe"], "commands": ["steam.exe"]},
    "word": {"commands": ["winword.exe"]},
    "excel": {"commands": ["excel.exe"]},
    "powerpoint": {"commands": ["powerpnt.exe"]},
    "outlook": {"commands": ["outlook.exe"]},
    "teams": {"commands": ["ms-teams.exe", "Teams.exe"]},
    "telegram": {"commands": ["Telegram.exe"]},
    "whatsapp": {"commands": ["WhatsApp.exe"]},
}

_START_MENU_CACHE: tuple[float, list[Path]] = (0.0, [])


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(path)).expanduser()


def _start_menu_shortcuts() -> list[Path]:
    global _START_MENU_CACHE
    now = time.monotonic()
    if now - _START_MENU_CACHE[0] < 120 and _START_MENU_CACHE[1]:
        return _START_MENU_CACHE[1]
    roots = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    shortcuts: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for current, _dirs, files in os.walk(root):
            for filename in files:
                if filename.lower().endswith((".lnk", ".url")):
                    shortcuts.append(Path(current) / filename)
                    if len(shortcuts) >= 3000:
                        break
            if len(shortcuts) >= 3000:
                break
    _START_MENU_CACHE = (now, shortcuts)
    return shortcuts


def _find_shortcut(name: str) -> Path | None:
    target = _normalize(name)
    shortcuts = _start_menu_shortcuts()
    exact = [path for path in shortcuts if _normalize(path.stem) == target]
    if exact:
        return exact[0]
    partial = [path for path in shortcuts if target in _normalize(path.stem)]
    if partial:
        partial.sort(key=lambda path: len(path.stem))
        return partial[0]
    return None


def _resolve_known_app(name: str) -> tuple[str, Path] | None:
    key = _ALIASES.get(_normalize(name), _normalize(name))
    spec = _APP_CANDIDATES.get(key)
    if not spec:
        return None
    for raw in spec.get("paths", []):
        candidate = _expand(raw)
        if "*" in str(candidate):
            matches = sorted(candidate.parent.glob(candidate.name))
            for match in matches:
                if match.exists():
                    return key, match
        elif candidate.exists():
            return key, candidate
    for command in spec.get("commands", []):
        found = shutil.which(command)
        if found:
            return key, Path(found)
    return None


def _launch(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in {".cmd", ".bat"}:
        subprocess.Popen(
            [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(path)],
            close_fds=True,
            cwd=str(path.parent),
        )
        return
    if suffix in {".lnk", ".url"}:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    subprocess.Popen([str(path)], close_fds=True, cwd=str(path.parent))


class OpenApplicationTool(BaseTool):
    name = "open_application"
    description = (
        "Abre um aplicativo instalado no Windows pelo nome conhecido (vscode, chrome, edge, spotify, "
        "notepad, terminal, etc.) ou pelo nome de um atalho do Menu Iniciar."
    )
    permission_level = 1
    category = "applications"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 120},
        },
        "required": ["name"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        name = arguments["name"].strip()
        known = _resolve_known_app(name)
        if known:
            key, path = known
            try:
                _launch(path)
            except OSError as exc:
                return ToolResult.fail(f"Não foi possível abrir {name}: {exc}")
            return ToolResult.ok(
                {"name": key, "path": str(path), "method": "known_app"},
                display=f"Abrindo {key}",
            )
        shortcut = _find_shortcut(name)
        if shortcut:
            try:
                _launch(shortcut)
            except OSError as exc:
                return ToolResult.fail(f"Não foi possível abrir o atalho {shortcut.name}: {exc}")
            return ToolResult.ok(
                {"name": name, "path": str(shortcut), "method": "start_menu"},
                display=f"Abrindo {shortcut.stem}",
            )
        return ToolResult.fail(
            f"Aplicativo não encontrado: {name}. Use um nome de atalho do Menu Iniciar ou "
            "informe o caminho com open_path."
        )


class OpenPathTool(BaseTool):
    name = "open_path"
    description = "Abre uma pasta, arquivo ou atalho no aplicativo padrão do Windows."
    permission_level = 1
    category = "applications"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], must_exist=True)
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível abrir {path}: {exc}")
        return ToolResult.ok({"path": str(path)}, display=f"Abrindo {path.name}")


class CloseApplicationTool(BaseTool):
    name = "close_application"
    description = (
        "Encerra um aplicativo pelo nome do processo ou PID. Processos críticos do Windows e o "
        "próprio JARVIS são protegidos."
    )
    permission_level = 2
    category = "applications"
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "maxLength": 120},
            "pid": {"type": "integer", "minimum": 1},
        },
        "anyOf": [{"required": ["name"]}, {"required": ["pid"]}],
        "additionalProperties": False,
    }

    def summarize(self, arguments: dict[str, Any]) -> str:
        target = arguments.get("name") or f"PID {arguments.get('pid')}"
        return f"Encerrar o aplicativo {target}"

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        targets: list[psutil.Process] = []
        if arguments.get("pid"):
            try:
                targets = [psutil.Process(int(arguments["pid"]))]
            except (psutil.NoSuchProcess, ValueError):
                return ToolResult.fail(f"PID não encontrado: {arguments['pid']}")
        else:
            wanted = _normalize(arguments["name"]).removesuffix(".exe")
            for process in psutil.process_iter(["name"]):
                name = _normalize(process.info.get("name") or "").removesuffix(".exe")
                if name == wanted:
                    targets.append(process)
        if not targets:
            return ToolResult.fail(f"Nenhum processo encontrado para {arguments.get('name') or arguments.get('pid')}")
        closed: list[dict[str, Any]] = []
        errors: list[str] = []
        protected_pids = {os.getpid(), psutil.Process(os.getpid()).ppid()}
        for process in targets:
            try:
                name = _normalize(process.name())
                if name in _PROTECTED_PROCESSES or process.pid in protected_pids:
                    errors.append(f"{process.name()} (PID {process.pid}) é protegido")
                    continue
                process.terminate()
                try:
                    process.wait(timeout=3)
                except psutil.TimeoutExpired:
                    process.kill()
                closed.append({"pid": process.pid, "name": process.name()})
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
                errors.append(f"PID {process.pid}: {exc}")
        if not closed:
            return ToolResult.fail("; ".join(errors) or "Não foi possível encerrar o aplicativo")
        display = f"Encerrado(s): {', '.join(item['name'] for item in closed)}"
        if errors:
            display += f" ({len(errors)} falha(s))"
        return ToolResult.ok({"closed": closed, "errors": errors}, display=display)


class ManageWindowsTool(BaseTool):
    name = "manage_windows"
    description = (
        "Lista, foca, minimiza, maximiza, restaura ou fecha janelas abertas. Para ações em uma janela, "
        "informe hwnd ou parte do título. Se houver ambiguidade, a ferramenta lista os candidatos."
    )
    permission_level = 1
    category = "applications"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "focus", "minimize", "maximize", "restore", "close"],
            },
            "title": {"type": "string", "maxLength": 200},
            "hwnd": {"type": "integer"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def get_permission_level(self, arguments: dict[str, Any]) -> int:
        return 2 if arguments.get("action") == "close" else 1

    def summarize(self, arguments: dict[str, Any]) -> str:
        target = arguments.get("title") or arguments.get("hwnd") or "janela"
        return f"{arguments.get('action', 'list')} na janela {target}"

    def _windows(self) -> list[dict[str, Any]]:
        if sys.platform != "win32":
            raise RuntimeError("Controle de janelas implementado para Windows")
        user32 = ctypes.windll.user32
        windows: list[dict[str, Any]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if not title:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            process_name = "?"
            try:
                process_name = psutil.Process(pid.value).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            windows.append(
                {
                    "hwnd": int(hwnd),
                    "title": title,
                    "pid": int(pid.value),
                    "process": process_name,
                    "rect": {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom,
                    },
                }
            )
            return True

        user32.EnumWindows(callback, 0)
        return windows

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        action = arguments["action"]
        try:
            windows = self._windows()
        except Exception as exc:
            return ToolResult.fail(f"Não foi possível enumerar janelas: {exc}")
        if action == "list":
            limit = int(arguments.get("limit", 50))
            return ToolResult.ok(
                {"windows": windows[:limit], "total": len(windows)},
                display=f"{min(len(windows), limit)} janela(s) aberta(s)",
            )
        hwnd = arguments.get("hwnd")
        title = (arguments.get("title") or "").strip().lower()
        if hwnd:
            matches = [window for window in windows if window["hwnd"] == int(hwnd)]
        elif title:
            matches = [window for window in windows if title in window["title"].lower()]
        else:
            return ToolResult.fail("Informe hwnd ou title para atuar em uma janela")
        if not matches:
            return ToolResult.fail("Nenhuma janela correspondente encontrada")
        if len(matches) > 1:
            return ToolResult.ok(
                {
                    "ambiguous": True,
                    "candidates": matches[:10],
                    "message": "Mais de uma janela corresponde; informe o hwnd.",
                },
                display=f"{len(matches)} janelas correspondem; informe o hwnd",
            )
        window = matches[0]
        user32 = ctypes.windll.user32
        try:
            if action == "focus":
                user32.ShowWindow(window["hwnd"], 9)  # SW_RESTORE
                focused = bool(user32.SetForegroundWindow(window["hwnd"]))
                return ToolResult.ok(
                    {"window": window, "focused": focused},
                    display=f"Focando {window['title']}" if focused else "Não foi possível focar a janela",
                )
            if action == "minimize":
                user32.ShowWindow(window["hwnd"], 6)  # SW_MINIMIZE
            elif action == "maximize":
                user32.ShowWindow(window["hwnd"], 3)  # SW_MAXIMIZE
            elif action == "restore":
                user32.ShowWindow(window["hwnd"], 9)  # SW_RESTORE
            elif action == "close":
                user32.PostMessageW(window["hwnd"], 0x0010, 0, 0)  # WM_CLOSE
        except Exception as exc:
            return ToolResult.fail(f"Falha ao executar {action}: {exc}")
        return ToolResult.ok({"window": window, "action": action}, display=f"{action}: {window['title']}")
