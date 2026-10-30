"""Fábrica de provedores a partir das configurações e do cofre de chaves."""

from __future__ import annotations

import logging
from typing import Any

from backend.ai.anthropic_provider import AnthropicProvider
from backend.ai.llm_provider import LLMProvider
from backend.ai.ollama_provider import OllamaProvider
from backend.ai.openai_provider import (
    CustomOpenAIProvider,
    DeepSeekProvider,
    OpenAIProvider,
)
from backend.ai.types import ProviderStatus
from backend.config.settings import AppSettings, RuntimeSettings
from backend.core.errors import ProviderConfigurationError
from backend.security.secrets import SecretStore, SecretStoreError

logger = logging.getLogger(__name__)

PROVIDER_ORDER = ["deepseek", "openai", "anthropic", "ollama", "custom"]

PROVIDER_LABELS = {
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "ollama": "Ollama (local)",
    "custom": "API compatível com OpenAI",
}


class ProviderFactory:
    def __init__(self, app_settings: AppSettings, secret_store: SecretStore) -> None:
        self.app_settings = app_settings
        self.secret_store = secret_store

    def key_for(self, provider: str) -> tuple[str, str]:
        """Retorna (chave, origem). Variáveis de ambiente têm precedência."""
        env_key = self.app_settings.env_api_keys.get(provider, "")
        if env_key:
            return env_key, "env"
        try:
            stored = self.secret_store.get(provider)
        except SecretStoreError as exc:
            logger.warning("Cofre de chaves indisponível: %s", exc)
            stored = ""
        if stored:
            return stored, "store"
        return "", "none"

    def base_url_for(self, provider: str) -> str:
        return {
            "deepseek": self.app_settings.deepseek_base_url,
            "openai": self.app_settings.openai_base_url,
            "anthropic": self.app_settings.anthropic_base_url,
            "ollama": self.app_settings.ollama_base_url,
            "custom": self.app_settings.custom_base_url,
        }.get(provider, "")

    def create(self, settings: RuntimeSettings) -> LLMProvider:
        provider = settings.provider
        api_key, _origin = self.key_for(provider)
        base_url = self.base_url_for(provider)
        timeout = self.app_settings.request_timeout
        if provider == "deepseek":
            return DeepSeekProvider(api_key=api_key, base_url=base_url, timeout=timeout)
        if provider == "openai":
            return OpenAIProvider(api_key=api_key, base_url=base_url, timeout=timeout)
        if provider == "anthropic":
            return AnthropicProvider(api_key=api_key, base_url=base_url, timeout=timeout)
        if provider == "ollama":
            return OllamaProvider(
                api_key="",
                base_url=base_url,
                timeout=timeout,
                num_ctx=self.app_settings.ollama_num_ctx,
            )
        if provider == "custom":
            if not base_url:
                raise ProviderConfigurationError(
                    "Configure a URL base da API personalizada em Configurações ou no .env "
                    "(JARVIS_CUSTOM_BASE_URL)."
                )
            return CustomOpenAIProvider(api_key=api_key, base_url=base_url, timeout=timeout)
        raise ProviderConfigurationError(f"Provedor desconhecido: {provider}")

    def describe(self, current: RuntimeSettings) -> list[dict[str, Any]]:
        descriptions: list[dict[str, Any]] = []
        store_configured = self.secret_store.configured()
        for provider in PROVIDER_ORDER:
            api_key, origin = self.key_for(provider)
            base_url = self.base_url_for(provider)
            configured = bool(api_key) or provider in {"ollama", "custom"}
            if provider == "custom":
                configured = bool(base_url)
            descriptions.append(
                {
                    "id": provider,
                    "label": PROVIDER_LABELS[provider],
                    "requires_key": provider not in {"ollama", "custom"},
                    "configured": configured,
                    "key_source": origin,
                    "key_configured_in_store": bool(store_configured.get(provider)),
                    "base_url": base_url,
                    "model_hints": self._model_hints(provider),
                    "current": provider == current.provider,
                }
            )
        return descriptions

    def _model_hints(self, provider: str) -> list[str]:
        try:
            if provider == "deepseek":
                return DeepSeekProvider.model_hints
            if provider == "openai":
                return OpenAIProvider.model_hints
            if provider == "anthropic":
                return AnthropicProvider.model_hints
            if provider == "ollama":
                return OllamaProvider.model_hints
        except Exception:  # pragma: no cover
            pass
        return []

    async def test_connection(self, provider_id: str) -> ProviderStatus:
        settings = RuntimeSettings(
            provider=provider_id,  # type: ignore[arg-type]
            model="test",
        )
        provider = self.create(settings)
        return await provider.check_connection()

    async def list_models(self, provider_id: str) -> list[str]:
        settings = RuntimeSettings(
            provider=provider_id,  # type: ignore[arg-type]
            model="test",
        )
        provider = self.create(settings)
        return await provider.list_models()
