"""Fábrica da aplicação FastAPI do JARVIS."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import __version__
from backend.api import routes_chat, routes_memory, routes_system, websocket
from backend.config.settings import AppSettings
from backend.container import build_container
from backend.core.errors import JarvisError

logger = logging.getLogger(__name__)


def configure_logging(settings: AppSettings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    if getattr(root, "_jarvis_configured", False):
        root.setLevel(level)
        return
    root.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%H:%M:%S"
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    try:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.logs_dir / "jarvis.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        logger.warning("Não foi possível criar o arquivo de log", exc_info=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    root._jarvis_configured = True  # type: ignore[attr-defined]


def create_app(app_settings: AppSettings | None = None) -> FastAPI:
    settings = app_settings or AppSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        configure_logging(settings)
        container = build_container(settings)
        loop = asyncio.get_running_loop()
        container.event_bus.bind_loop(loop)
        container.voice.bind_loop(loop)
        try:
            removed = container.memory_manager.cleanup_expired()
            if removed:
                logger.info("Memórias temporárias expiradas removidas: %s", removed)
        except Exception:
            logger.exception("Falha ao limpar memórias temporárias")
        app.state.container = container
        logger.info(
            "JARVIS %s iniciado | provedor=%s modelo=%s | dados=%s",
            __version__,
            settings.default_provider,
            settings.default_model,
            settings.data_dir,
        )
        try:
            yield
        finally:
            logger.info("Encerrando JARVIS…")
            container.shutdown()

    app = FastAPI(
        title="JARVIS API",
        version=__version__,
        description="Assistente pessoal de IA com controle real do Windows.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            *settings.cors_origins_list,
            "http://localhost:8765",
            "http://127.0.0.1:8765",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(JarvisError)
    async def jarvis_error_handler(_request: Request, exc: JarvisError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for error in exc.errors()[:10]:
            location = ".".join(str(part) for part in error.get("loc", []) if part != "body")
            errors.append(f"{location}: {error.get('msg', 'valor inválido')}")
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "; ".join(errors) or "Requisição inválida",
            },
        )

    app.include_router(routes_system.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_memory.router)
    app.include_router(websocket.router)

    frontend_dist: Path = settings.frontend_dist
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
        logger.info("Frontend servido de %s", frontend_dist)
    else:

        @app.get("/", include_in_schema=False)
        async def frontend_missing() -> JSONResponse:
            return JSONResponse(
                {
                    "app": "JARVIS",
                    "version": __version__,
                    "message": (
                        "Frontend não compilado. Execute `npm install && npm run build` "
                        "em frontend/ ou use o modo de desenvolvimento do Vite."
                    ),
                    "docs": "/docs",
                }
            )

    return app


app = create_app()
