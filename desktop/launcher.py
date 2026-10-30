"""Janela desktop com WebView2 (pywebview) e fallback para o navegador.

O JARVIS é servido localmente pelo FastAPI. Em vez de duplicar a interface,
a janela nativa aponta para ``http://127.0.0.1:<porta>``. Quando o runtime
WebView2 não está instalado, o launcher abre o navegador padrão.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

WEBVIEW2_CLIENT_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

_REGISTRY_LOCATIONS = (
    (
        "HKLM_WOW64",
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients",
    ),
    ("HKLM", r"SOFTWARE\Microsoft\EdgeUpdate\Clients"),
    ("HKCU", r"Software\Microsoft\EdgeUpdate\Clients"),
)


class DesktopError(RuntimeError):
    """Falha ao abrir a janela nativa."""


def project_root() -> Path:
    """Raiz do projeto em desenvolvimento ou pasta extraída pelo PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def app_icon_path() -> Path:
    return project_root() / "assets" / "jarvis.ico"


def prepare_process() -> None:
    """DPI nítido, console UTF-8 e agrupamento correto na barra de tarefas."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover - console sem suporte
            pass
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:  # pragma: no cover
        pass
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # pragma: no cover - depende da versão do Windows
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "JARVIS.PersonalAssistant"
        )
    except Exception:  # pragma: no cover
        pass


def webview2_version() -> str | None:
    """Retorna a versão do runtime WebView2 Evergreen, se instalado."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows sempre tem winreg
        return None

    hives = {
        "HKLM_WOW64": winreg.HKEY_LOCAL_MACHINE,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKCU": winreg.HKEY_CURRENT_USER,
    }
    for hive_name, base_path in _REGISTRY_LOCATIONS:
        path = f"{base_path}\\{WEBVIEW2_CLIENT_ID}"
        try:
            with winreg.OpenKey(hives[hive_name], path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version and str(version) not in {"", "0.0.0.0"}:
            return str(version)
    return None


def webview_available() -> bool:
    """True quando há pywebview e runtime WebView2 utilizáveis."""
    if sys.platform != "win32":
        return False
    if webview2_version() is None:
        return False
    try:
        import webview  # noqa: F401
    except Exception:
        logger.debug("pywebview indisponível", exc_info=True)
        return False
    return True


def open_window(
    url: str,
    *,
    title: str = "J.A.R.V.I.S",
    width: int = 1500,
    height: int = 940,
    min_size: tuple[int, int] = (1080, 700),
    debug: bool = False,
    storage_path: str | Path | None = None,
    icon: str | Path | None = None,
    hidden: bool = False,
) -> None:
    """Abre a janela nativa e bloqueia até ser fechada.

    Levanta :class:`DesktopError` quando o pywebview não consegue iniciar,
    permitindo que o chamador caia para o navegador.
    """
    try:
        import webview
    except Exception as exc:  # pragma: no cover - ambiente sem pywebview
        raise DesktopError("pywebview não está instalado neste ambiente.") from exc

    if storage_path is not None:
        Path(storage_path).mkdir(parents=True, exist_ok=True)

    icon_value = str(icon) if icon and Path(icon).is_file() else None

    try:
        webview.create_window(
            title,
            url,
            width=width,
            height=height,
            min_size=min_size,
            background_color="#03070f",
            text_select=True,
            confirm_close=False,
            zoomable=True,
            hidden=hidden,
        )
        webview.start(
            gui="edgechromium",
            debug=debug,
            private_mode=False,
            storage_path=str(storage_path) if storage_path else None,
            icon=icon_value,
        )
    except Exception as exc:  # pragma: no cover - falha do runtime
        raise DesktopError(f"Não foi possível abrir a janela desktop: {exc}") from exc


def open_in_browser(url: str) -> bool:
    """Abre a URL no navegador padrão; retorna False em caso de falha."""
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        logger.exception("Falha ao abrir o navegador padrão")
        return False


def show_message(message: str, *, title: str = "JARVIS", error: bool = False) -> None:
    """Mostra uma caixa de diálogo nativa (ou stderr fora do Windows)."""
    if sys.platform == "win32":
        try:
            flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
            ctypes.windll.user32.MessageBoxW(None, message, title, flags)
            return
        except Exception:  # pragma: no cover
            pass
    print(f"{title}: {message}", file=sys.stderr)
