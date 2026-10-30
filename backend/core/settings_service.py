"""Preferências persistentes com validação e cache."""

from __future__ import annotations

import logging
import threading
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from backend.config.settings import (
    AppSettings,
    RuntimeSettings,
    build_initial_runtime_settings,
)
from backend.core.errors import ValidationError
from backend.database.repositories import SettingsRepository

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "runtime_settings"


class SettingsService:
    def __init__(self, app_settings: AppSettings, repository: SettingsRepository) -> None:
        self.app_settings = app_settings
        self.repository = repository
        self._lock = threading.RLock()
        self._cache: RuntimeSettings | None = None

    def get(self) -> RuntimeSettings:
        with self._lock:
            if self._cache is not None:
                return self._cache.model_copy(deep=True)
            stored = self.repository.get(_SETTINGS_KEY)
            initial = build_initial_runtime_settings(self.app_settings)
            if isinstance(stored, dict):
                try:
                    self._cache = RuntimeSettings.model_validate(stored)
                except PydanticValidationError:
                    logger.exception("Configurações persistidas inválidas; usando padrões")
                    self._cache = initial
            else:
                self._cache = initial
            return self._cache.model_copy(deep=True)

    def update(self, patch: dict[str, Any]) -> RuntimeSettings:
        with self._lock:
            current = self.get().model_dump()
            unknown = set(patch) - set(RuntimeSettings.model_fields)
            if unknown:
                raise ValidationError(f"Campos desconhecidos: {', '.join(sorted(unknown))}")
            current.update(patch)
            try:
                updated = RuntimeSettings.model_validate(current)
            except PydanticValidationError as exc:
                messages = []
                for error in exc.errors():
                    location = ".".join(str(part) for part in error["loc"])
                    messages.append(f"{location}: {error['msg']}")
                raise ValidationError("; ".join(messages)) from exc
            self.repository.set(_SETTINGS_KEY, updated.model_dump())
            self._cache = updated
            logger.info("Configurações atualizadas: provedor=%s modelo=%s", updated.provider, updated.model)
            return updated.model_copy(deep=True)

    def reset(self) -> RuntimeSettings:
        with self._lock:
            initial = build_initial_runtime_settings(self.app_settings)
            self.repository.set(_SETTINGS_KEY, initial.model_dump())
            self._cache = initial
            return initial.model_copy(deep=True)
