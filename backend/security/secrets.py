"""Cofre local de chaves de API usando DPAPI do Windows.

As chaves digitadas na interface são cifradas com a conta Windows atual
(``CryptProtectData``) e gravadas em ``data/secrets.json``. O arquivo não pode
ser reutilizado em outra conta/máquina. Variáveis de ambiente continuam
suportadas e têm precedência.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

from backend.core.utils import utc_now

logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"deepseek", "openai", "anthropic", "custom", "ollama"}


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _protect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise SecretStoreError(
            "O cofre DPAPI requer Windows. Use variáveis de ambiente para as chaves de API."
        )
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    buffer = ctypes.create_string_buffer(data)
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "JARVIS API key",
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(blob_out),
    )
    if not ok:
        raise SecretStoreError(f"Falha ao cifrar a chave com DPAPI: {ctypes.WinError()}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    if sys.platform != "win32":
        raise SecretStoreError("O cofre DPAPI requer Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    buffer = ctypes.create_string_buffer(data)
    blob_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    description = wintypes.LPWSTR()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        ctypes.byref(description),
        None,
        None,
        None,
        0x1,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise SecretStoreError(f"Falha ao decifrar a chave com DPAPI: {ctypes.WinError()}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if description:
            kernel32.LocalFree(description)
        kernel32.LocalFree(blob_out.pbData)


class SecretStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "secrets": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SecretStoreError(f"Não foi possível ler o cofre local: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("secrets"), dict):
            raise SecretStoreError("Formato inválido do cofre local")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd, temp_name = tempfile.mkstemp(
            prefix=".secrets-", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def set(self, provider: str, value: str) -> None:
        provider = provider.lower().strip()
        if provider not in VALID_PROVIDERS:
            raise SecretStoreError(f"Provedor inválido: {provider}")
        data = self._load()
        if not value.strip():
            data["secrets"].pop(provider, None)
        else:
            encrypted = _protect(value.strip().encode("utf-8"))
            data["secrets"][provider] = {
                "blob": base64.b64encode(encrypted).decode("ascii"),
                "updated_at": utc_now(),
            }
        self._save(data)
        logger.info("Chave do provedor %s atualizada no cofre local", provider)

    def get(self, provider: str) -> str:
        provider = provider.lower().strip()
        data = self._load()
        entry = data["secrets"].get(provider)
        if not entry:
            return ""
        try:
            raw = base64.b64decode(entry["blob"])
            return _unprotect(raw).decode("utf-8")
        except (KeyError, ValueError, SecretStoreError) as exc:
            logger.warning("Não foi possível ler a chave de %s: %s", provider, exc)
            return ""

    def delete(self, provider: str) -> None:
        provider = provider.lower().strip()
        data = self._load()
        if data["secrets"].pop(provider, None) is not None:
            self._save(data)
            logger.info("Chave do provedor %s removida do cofre local", provider)

    def configured(self) -> dict[str, bool]:
        data = self._load()
        result = {provider: False for provider in VALID_PROVIDERS}
        for provider in data["secrets"]:
            if provider in result:
                result[provider] = True
        return result

    def describe(self) -> dict[str, str]:
        """Retorna apenas metadados; nunca devolve o valor das chaves."""
        data = self._load()
        return {
            provider: entry.get("updated_at", "")
            for provider, entry in data["secrets"].items()
            if isinstance(entry, dict)
        }
