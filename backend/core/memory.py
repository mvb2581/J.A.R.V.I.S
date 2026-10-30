"""Serviço de memória de longo prazo com busca contextual."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from backend.core.events import EventBus
from backend.core.settings_service import SettingsService
from backend.core.utils import is_probably_secret, truncate
from backend.database.models import MemoryRecord
from backend.database.repositories import MemoryRepository

logger = logging.getLogger(__name__)

_CATEGORY_LABELS = {
    "preference": "preferência",
    "fact": "fato",
    "project": "projeto",
    "contact": "contato",
    "other": "outro",
}


class MemoryManager:
    def __init__(
        self,
        repository: MemoryRepository,
        settings: SettingsService,
        event_bus: EventBus,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.event_bus = event_bus

    def cleanup_expired(self) -> int:
        ttl = self.settings.get().temporary_memory_ttl_hours
        removed = self.repository.delete_expired_temporary(ttl)
        if removed:
            logger.info("Removidas %s memórias temporárias expiradas", removed)
        return removed

    def add(
        self,
        content: str,
        *,
        category: str = "other",
        persistent: bool = True,
        source: str = "user",
        conversation_id: str | None = None,
    ) -> MemoryRecord:
        content = content.strip()
        if len(content) < 2:
            raise ValueError("A memória precisa ter pelo menos 2 caracteres")
        if len(content) > 2000:
            raise ValueError("A memória excede o limite de 2000 caracteres")
        if is_probably_secret(content):
            raise ValueError("A memória parece conter uma credencial; não armazene segredos")
        record = self.repository.add(
            content,
            category=category,
            persistent=persistent,
            source=source,
            conversation_id=conversation_id,
        )
        logger.info("Memória criada: %s (%s)", record.id, record.category)
        return record

    def list(
        self,
        *,
        category: str | None = None,
        persistent: bool | None = None,
        limit: int = 200,
    ) -> list[MemoryRecord]:
        return self.repository.list(category=category, persistent=persistent, limit=limit)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        include_temporary: bool = True,
        conversation_id: str | None = None,
    ) -> list[MemoryRecord]:
        return self.repository.search(
            query,
            limit=limit,
            include_temporary=include_temporary,
            conversation_id=conversation_id,
        )

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        category: str | None = None,
        persistent: bool | None = None,
    ) -> MemoryRecord | None:
        if content is not None:
            content = content.strip()
            if not content:
                raise ValueError("O conteúdo da memória não pode ser vazio")
            if is_probably_secret(content):
                raise ValueError("A memória parece conter uma credencial")
        return self.repository.update(
            memory_id, content=content, category=category, persistent=persistent
        )

    def delete(self, memory_id: str) -> bool:
        return self.repository.delete(memory_id)

    def retrieve_context(
        self, query: str, conversation_id: str | None = None, limit: int = 6
    ) -> list[MemoryRecord]:
        settings = self.settings.get()
        if not settings.auto_memory_search or not query.strip():
            return []
        return self.repository.search(
            query,
            limit=limit,
            include_temporary=True,
            conversation_id=conversation_id,
        )

    def as_prompt(self, records: list[MemoryRecord]) -> str:
        if not records:
            return ""
        lines = ["Memórias relevantes autorizadas pelo usuário (use apenas se fizer sentido):"]
        for record in records:
            label = _CATEGORY_LABELS.get(record.category, record.category)
            scope = "persistente" if record.persistent else "temporária"
            lines.append(f"- [{label}/{scope}] {truncate(record.content, 500)}")
        return "\n".join(lines)

    def as_dict(self, record: MemoryRecord) -> dict[str, Any]:
        return asdict(record)
