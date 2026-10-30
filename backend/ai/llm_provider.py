"""Interface comum dos provedores de LLM e cliente HTTP resiliente."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.ai.types import LLMResponse, ProviderStatus
from backend.core.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from backend.core.utils import truncate

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    name = "provider"
    label = "Provedor"
    requires_api_key = True
    model_hints: list[str] = []

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout = timeout

    def ensure_configured(self) -> None:
        if self.requires_api_key and not self.api_key:
            raise ProviderConfigurationError(
                f"{self.label} não está configurado. Informe a chave de API em Configurações "
                "ou defina a variável de ambiente correspondente."
            )
        if not self.base_url:
            raise ProviderConfigurationError(
                f"{self.label} não tem URL base configurada. Ajuste em Configurações."
            )

    @property
    def headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        retries: int = 2,
    ) -> Any:
        self.ensure_configured()
        headers = {**self.headers, **(extra_headers or {})}
        url = self._url(path)
        last_error: Exception | None = None
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=15.0),
            follow_redirects=True,
        ) as client:
            for attempt in range(retries + 1):
                try:
                    response = await client.request(method, url, headers=headers, json=payload)
                except httpx.TimeoutException as exc:
                    last_error = exc
                    if attempt < retries:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise ProviderConnectionError(
                        f"{self.label} não respondeu em {self.timeout:.0f}s. "
                        "Verifique a conexão e a URL base."
                    ) from exc
                except httpx.HTTPError as exc:
                    last_error = exc
                    if attempt < retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise ProviderConnectionError(
                        f"Não foi possível conectar a {self.label} em {self.base_url}: {exc}"
                    ) from exc
                if response.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                self._raise_for_status(response)
                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderResponseError(
                        f"{self.label} retornou uma resposta que não é JSON: "
                        f"{truncate(response.text, 300)}"
                    ) from exc
        raise ProviderConnectionError(
            f"Falha de conexão com {self.label}: {last_error or 'erro desconhecido'}"
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        body = truncate(response.text or "", 500)
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                f"{self.label} recusou a autenticação ({response.status_code}). "
                "Confira a chave de API e as permissões da conta.",
                detail=body,
            )
        if response.status_code == 404:
            raise ProviderResponseError(
                f"{self.label} não encontrou o endpoint ou modelo solicitado (404). "
                "Confira a URL base e o nome do modelo.",
                detail=body,
            )
        if response.status_code == 429:
            raise ProviderRateLimitError(
                f"{self.label} atingiu o limite de requisições (429). Aguarde e tente novamente.",
                detail=body,
            )
        if response.status_code == 400:
            raise ProviderResponseError(
                f"{self.label} rejeitou a requisição (400): {body}",
                detail=body,
            )
        raise ProviderResponseError(
            f"{self.label} retornou erro HTTP {response.status_code}: {body}",
            detail=body,
        )

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        raise NotImplementedError

    async def list_models(self) -> list[str]:
        data = await self._request_json("GET", "/models")
        models: list[str] = []
        if isinstance(data, dict):
            for item in data.get("data", []):
                if isinstance(item, dict) and item.get("id"):
                    models.append(str(item["id"]))
            for item in data.get("models", []):
                if isinstance(item, dict) and item.get("name"):
                    models.append(str(item["name"]))
        return sorted(dict.fromkeys(models))

    async def check_connection(self) -> ProviderStatus:
        try:
            models = await self.list_models()
            return ProviderStatus(
                provider=self.name,
                configured=True,
                reachable=True,
                message="Conexão estabelecida",
                models=models,
            )
        except Exception as exc:
            return ProviderStatus(
                provider=self.name,
                configured=bool(self.api_key) or not self.requires_api_key,
                reachable=False,
                message=str(exc),
                models=self.model_hints,
            )
