"""Dependências e serialização compartilhadas pelas rotas."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import Request

from backend.container import Container
from backend.core.errors import NotFoundError


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - inicialização sempre define
        raise RuntimeError("Container da aplicação não inicializado")
    return container


def conversation_dict(record: Any) -> dict[str, Any]:
    return asdict(record)


def message_dict(record: Any) -> dict[str, Any]:
    return asdict(record)


def action_dict(record: Any) -> dict[str, Any]:
    return asdict(record)


def memory_dict(record: Any) -> dict[str, Any]:
    return asdict(record)


def require_conversation(container: Container, conversation_id: str) -> Any:
    record = container.conversations.get(conversation_id)
    if record is None:
        raise NotFoundError("Conversa não encontrada")
    return record
