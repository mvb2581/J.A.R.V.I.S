"""Erros de domínio com códigos estáveis para a API."""

from __future__ import annotations

from typing import Any


class JarvisError(Exception):
    code = "jarvis_error"
    status_code = 500

    def __init__(self, message: str, *, detail: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if code:
            self.code = code

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


class ValidationError(JarvisError):
    code = "validation_error"
    status_code = 422


class NotFoundError(JarvisError):
    code = "not_found"
    status_code = 404


class PermissionDeniedError(JarvisError):
    code = "permission_denied"
    status_code = 403


class ToolExecutionError(JarvisError):
    code = "tool_execution_error"
    status_code = 400


class ProviderError(JarvisError):
    code = "provider_error"
    status_code = 502


class ProviderConfigurationError(ProviderError):
    code = "provider_not_configured"
    status_code = 503


class ProviderAuthenticationError(ProviderError):
    code = "provider_auth_error"
    status_code = 401


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limit"
    status_code = 429


class ProviderConnectionError(ProviderError):
    code = "provider_connection_error"
    status_code = 503


class ProviderResponseError(ProviderError):
    code = "provider_response_error"
    status_code = 502


class CancelledError(JarvisError):
    code = "cancelled"
    status_code = 409
