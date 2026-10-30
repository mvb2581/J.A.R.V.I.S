"""Execução controlada de comandos PowerShell/CMD com classificação de risco."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from typing import Any

import psutil

from backend.core.utils import truncate
from backend.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

_READ_ONLY = re.compile(
    r"^\s*(get-|gci\b|gi\b|gc\b|gps\b|gsv\b|gv\b|gl\b|gm\b|sls\b|select-string\b|"
    r"dir\b|ls\b|pwd\b|cd\b|whoami\b|hostname\b|systeminfo\b|ipconfig\b|ping\b|"
    r"tracert\b|nslookup\b|where\b|which\b|tree\b|type\b|cat\b|more\b|findstr\b|"
    r"echo\b|git\s+(status|log|diff|show|branch|remote|rev-parse|ls-files)\b|"
    r"npm\s+(--version|list|ls|view)\b|pip\s+(list|show|--version)\b|"
    r"python\s+--version\b|py\s+--version\b|node\s+--version\b|"
    r"test-path\b|measure-object\b|resolve-path\b|get-filehash\b|"
    r"get-nettcpconnection\b|test-netconnection\b|get-ciminstance\b|get-wmiobject\b|"
    r"find\b|head\b|tail\b|wc\b|du\b|df\b)",
    re.IGNORECASE,
)

_CRITICAL = re.compile(
    r"(remove-item|\brm\b|\bdel\b|\berase\b|\brd\b|\brmdir\b|format-volume|\bformat\b|"
    r"clear-disk|initialize-disk|diskpart|bcdedit|bootrec|vssadmin|wbadmin|cipher|fsutil|"
    r"reg\s+(add|delete)|sc\s+(delete|config)|net\s+(user|localgroup)|"
    r"shutdown|restart-computer|stop-computer|stop-service|set-service|"
    r"disable-[a-z]|enable-[a-z]|set-executionpolicy|takeown|icacls|"
    r"new-localuser|set-localuser|set-mppreference|add-mppreference|"
    r"netsh\s+advfirewall|set-netfirewallprofile|wevtutil\s+cl|"
    r"schtasks\s+/(create|delete|change)|taskkill|stop-process)",
    re.IGNORECASE,
)

_WRITE = re.compile(
    r"(new-item|set-content|add-content|out-file|copy-item|move-item|rename-item|"
    r"mkdir|\bmd\b|\bcopy\b|\bmove\b|\bren\b|pip\s+install|npm\s+install|yarn\s+add|"
    r"pnpm\s+add|python\s+\S|py\s+\S|node\s+\S|npm\s+run|start-process|"
    r"invoke-webrequest|invoke-restmethod|curl\b|wget\b|tar\b|expand-archive|"
    r"compress-archive|setx\b|choco\b|winget\s+install|scoop\s+install|"
    r"git\s+(add|commit|push|pull|checkout|merge|rebase|reset|clean|stash)|"
    r">|>>)",
    re.IGNORECASE,
)

_FORBIDDEN = [
    (re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE), "formatação de unidade"),
    (re.compile(r"\bdiskpart\b", re.IGNORECASE), "particionamento de disco"),
    (re.compile(r"\b(clear-disk|initialize-disk)\b", re.IGNORECASE), "apagamento de disco"),
    (re.compile(r"\bbcdedit\b", re.IGNORECASE), "alteração do boot do Windows"),
    (re.compile(r"\bbootrec\b", re.IGNORECASE), "reparo/alteração do boot"),
    (re.compile(r"(remove-item|\brm\b|\brd\b|\brmdir\b).*(c:\\|c:/)\s*(\*|$)", re.IGNORECASE), "remoção da raiz da unidade"),
    (re.compile(r"(remove-item|\brm\b|\brd\b|\brmdir\b).*c:\\windows", re.IGNORECASE), "remoção da pasta do Windows"),
    (re.compile(r"(disable|set-mppreference|add-mppreference).*(defender|antivirus|firewall)", re.IGNORECASE), "desativação de mecanismo de segurança"),
    (re.compile(r"(netsh\s+advfirewall\s+set|set-netfirewallprofile).*(off|disable)", re.IGNORECASE), "desativação do firewall"),
    (re.compile(r"\breg\s+delete\s+(hklm|hkey_local_machine)", re.IGNORECASE), "exclusão de registro do sistema"),
    (re.compile(r"\b(vssadmin|wbadmin)\s+delete\b", re.IGNORECASE), "exclusão de backups/sombras"),
]

_SENSITIVE_COMMAND = re.compile(
    r"(\.env\b|id_rsa|id_ed25519|\.ssh\\|\.aws\\|secrets\.json|jarvis\.db|"
    r"login data|logins\.json|key4\.db|\.git-credentials|\.npmrc)",
    re.IGNORECASE,
)


def classify_command(command: str) -> tuple[int, str]:
    normalized = command.strip()
    if not normalized:
        return 2, "comando vazio"
    segments = [segment for segment in re.split(r"\s*(?:;|&&|\|\||\n|\|)\s*", normalized) if segment]
    levels: list[tuple[int, str]] = []
    for segment in segments or [normalized]:
        if _CRITICAL.search(segment):
            levels.append((3, "comando crítico ou administrativo"))
        elif _WRITE.search(segment):
            levels.append((2, "comando que pode modificar dados ou executar código"))
        elif _READ_ONLY.search(segment):
            levels.append((1, "consulta somente leitura"))
        else:
            levels.append((2, "comando não classificado como somente leitura"))
    return max(levels, key=lambda item: item[0])


def forbidden_reason(command: str) -> str | None:
    for pattern, reason in _FORBIDDEN:
        if pattern.search(command):
            return reason
    return None


class ExecuteTerminalCommandTool(BaseTool):
    name = "execute_terminal_command"
    description = (
        "Executa um comando PowerShell (ou CMD) e retorna saída, erro e código de saída. "
        "Comandos de leitura podem rodar direto; comandos que modificam dados exigem confirmação; "
        "comandos críticos exigem confirmação explícita. Comandos destrutivos do sistema são bloqueados."
    )
    permission_level = 2
    category = "terminal"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "minLength": 1, "maxLength": 4000},
            "cwd": {"type": "string", "description": "Diretório de trabalho autorizado."},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
            "shell": {"type": "string", "enum": ["powershell", "cmd"], "default": "powershell"},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def get_permission_level(self, arguments: dict[str, Any]) -> int:
        return classify_command(arguments.get("command", ""))[0]

    def summarize(self, arguments: dict[str, Any]) -> str:
        level, reason = classify_command(arguments.get("command", ""))
        return f"Executar no terminal (nível {level}, {reason}): {truncate(arguments.get('command', ''), 180)}"

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        settings = context.runtime_settings
        if not settings.terminal_enabled:
            return ToolResult.fail("A execução de comandos está desativada nas configurações")
        command = arguments["command"].strip()
        reason = forbidden_reason(command)
        if reason:
            return ToolResult.fail(
                f"Comando bloqueado pela política de segurança ({reason}). "
                "Execute essa operação manualmente se ela for realmente necessária."
            )
        if _SENSITIVE_COMMAND.search(command):
            return ToolResult.fail(
                "Comando bloqueado: ele referencia arquivo ou diretório sensível "
                "(credenciais, cofre ou banco de memória)."
            )
        if sys.platform != "win32":
            return ToolResult.fail("O terminal do JARVIS está implementado para Windows")
        cwd = context.path_guard.resolve(arguments.get("cwd") or str(context.user_home), must_exist=True)
        if not cwd.is_dir():
            return ToolResult.fail(f"O diretório de trabalho não existe: {cwd}")
        timeout = min(
            int(arguments.get("timeout_seconds") or settings.terminal_timeout_seconds),
            settings.terminal_timeout_seconds,
            300,
        )
        shell = arguments.get("shell", "powershell")
        if shell == "cmd":
            executable = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
        else:
            executable = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ]
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                executable,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível iniciar o terminal: {exc}")
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(process)
            stdout, stderr = process.communicate()
        duration_ms = round((time.monotonic() - started) * 1000)
        limit = settings.max_terminal_output_chars
        output_truncated = len(stdout) > limit or len(stderr) > limit
        stdout = stdout[:limit]
        stderr = stderr[:limit]
        payload = {
            "command": command,
            "shell": shell,
            "cwd": str(cwd),
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": output_truncated,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
        }
        if timed_out:
            return ToolResult.fail(
                f"Comando interrompido após {timeout}s (timeout)", data=payload
            )
        if process.returncode != 0:
            detail = (stderr or stdout).strip()
            return ToolResult.fail(
                f"Comando retornou código {process.returncode}" + (f": {truncate(detail, 300)}" if detail else ""),
                data=payload,
            )
        display = f"Comando concluído em {duration_ms} ms" + (" (saída truncada)" if output_truncated else "")
        return ToolResult.ok(payload, display=display)


def _kill_tree(process: subprocess.Popen[str]) -> None:
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass
        _gone, alive = psutil.wait_procs([parent, *children], timeout=2)
        for item in alive:
            try:
                item.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass
