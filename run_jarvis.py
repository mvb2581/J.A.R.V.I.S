"""Inicializador do JARVIS: servidor local + janela desktop.

Uso típico no Windows::

    .\\.venv\\Scripts\\python.exe run_jarvis.py

O servidor FastAPI sobe em segundo plano, a interface é aberta em uma janela
nativa (WebView2) e, ao fechá-la, o servidor é encerrado com segurança. Se o
WebView2 não estiver disponível, o JARVIS abre no navegador padrão.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from backend.config.settings import AppSettings
from backend.main import configure_logging, create_app
from desktop.launcher import (
    DesktopError,
    app_icon_path,
    open_in_browser,
    open_window,
    prepare_process,
    show_message,
    webview2_version,
    webview_available,
)

logger = logging.getLogger("jarvis.launcher")

STARTUP_TIMEOUT_SECONDS = 45.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="JARVIS — assistente pessoal de IA para Windows.",
    )
    parser.add_argument("--host", help="Endereço do servidor (padrão: JARVIS_HOST ou 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Porta do servidor (padrão: JARVIS_PORT ou 8765)")
    parser.add_argument(
        "--data-dir",
        help="Diretório de dados (padrão: ./data em dev, %%LOCALAPPDATA%%\\JARVIS no executável)",
    )
    parser.add_argument(
        "--server-only",
        action="store_true",
        help="Inicia apenas o servidor, sem abrir janela ou navegador.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Abre a interface no navegador padrão em vez da janela nativa.",
    )
    parser.add_argument("--debug", action="store_true", help="Ativa ferramentas de depuração da janela.")
    return parser.parse_args(argv)


def build_settings(args: argparse.Namespace) -> AppSettings:
    overrides: dict[str, object] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port:
        overrides["port"] = args.port
    if args.data_dir:
        overrides["data_dir"] = Path(args.data_dir)
    return AppSettings(**overrides)  # type: ignore[arg-type]


def local_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"", "0.0.0.0", "::"} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}"


def probe(url: str, timeout: float = 1.0) -> bool:
    """Confere se há uma instância saudável do JARVIS na URL."""
    try:
        response = httpx.get(f"{url}/api/health", timeout=timeout)
    except Exception:
        return False
    if response.status_code != 200:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return payload.get("app") == "JARVIS" and payload.get("status") == "ok"


def port_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


class ServerThread(threading.Thread):
    """Executa o uvicorn em segundo plano para deixar a thread principal livre."""

    def __init__(self, app: object, settings: AppSettings) -> None:
        super().__init__(name="jarvis-server", daemon=True)
        self.error: str | None = None
        config = uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            access_log=False,
            log_config=None,
            timeout_graceful_shutdown=5,
        )
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        try:
            self.server.run()
        except SystemExit as exc:
            self.error = f"o servidor encerrou com código {exc.code}"
        except BaseException as exc:  # noqa: BLE001 - reportado ao usuário
            self.error = f"{type(exc).__name__}: {exc}"
            logger.exception("Falha no servidor local")

    def stop(self, timeout: float = 10.0) -> None:
        self.server.should_exit = True
        if self.is_alive():
            self.join(timeout=timeout)
            if self.is_alive():
                logger.warning("O servidor não encerrou em %.0f segundos", timeout)


def wait_until_ready(thread: ServerThread, url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if thread.error:
            raise RuntimeError(thread.error)
        if probe(url, timeout=0.5):
            return
        if not thread.is_alive():
            raise RuntimeError(thread.error or "o servidor encerrou durante a inicialização")
        time.sleep(0.2)
    raise RuntimeError(
        f"tempo limite de {STARTUP_TIMEOUT_SECONDS:.0f}s ao aguardar o servidor em {url}"
    )


def _keep_alive() -> None:
    while True:
        time.sleep(0.5)


def run(args: argparse.Namespace) -> int:
    prepare_process()
    settings = build_settings(args)
    settings.ensure_directories()
    configure_logging(settings)

    url = local_url(settings.host, settings.port)
    logger.info("JARVIS | %s | dados=%s", url, settings.data_dir)

    server: ServerThread | None = None
    if probe(url):
        logger.info("Instância existente detectada em %s", url)
        if args.server_only:
            print(f"JARVIS já está em execução em {url}")
            return 0
    else:
        if not port_available(settings.host, settings.port):
            raise RuntimeError(
                f"A porta {settings.port} já está em uso por outro programa. "
                "Feche-o ou use --port para escolher outra porta."
            )
        server = ServerThread(create_app(settings), settings)
        server.start()
        wait_until_ready(server, url)
        logger.info("Servidor local pronto")

    try:
        if args.server_only:
            print(f"JARVIS em execução em {url} — pressione Ctrl+C para encerrar.")
            _keep_alive()
        elif args.browser or not webview_available():
            if not args.browser:
                logger.warning(
                    "Runtime WebView2 não encontrado; usando o navegador padrão. "
                    "Instale o WebView2 Evergreen para a janela nativa."
                )
            if not open_in_browser(url):
                raise RuntimeError(
                    f"Não foi possível abrir o navegador padrão. Acesse manualmente: {url}"
                )
            print(f"JARVIS aberto no navegador: {url} — pressione Ctrl+C para encerrar.")
            _keep_alive()
        else:
            logger.info("Abrindo janela desktop (WebView2 %s)", webview2_version())
            try:
                open_window(
                    url,
                    debug=args.debug,
                    storage_path=settings.data_dir / "webview",
                    icon=app_icon_path(),
                )
            except DesktopError as exc:
                logger.exception("Falha ao abrir a janela desktop")
                if not open_in_browser(url):
                    raise
                show_message(
                    f"{exc}\n\nA interface foi aberta no navegador padrão:\n{url}",
                    error=False,
                )
                _keep_alive()
    finally:
        if server is not None:
            logger.info("Encerrando servidor local…")
            server.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nJARVIS encerrado.")
        return 0
    except Exception as exc:  # noqa: BLE001 - mensagem amigável ao usuário
        logger.exception("Falha fatal ao iniciar o JARVIS")
        show_message(
            "Não foi possível iniciar o JARVIS.\n\n"
            f"{exc}\n\n"
            "Verifique os logs em data\\logs\\jarvis.log ou execute pelo "
            "terminal para ver o rastreamento completo.",
            error=True,
        )
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
