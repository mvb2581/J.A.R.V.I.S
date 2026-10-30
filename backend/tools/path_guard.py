"""Validação de caminhos e proteção de arquivos sensíveis."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from backend.core.errors import PermissionDeniedError


class PathAccessError(PermissionDeniedError):
    code = "path_not_allowed"


_SENSITIVE_DIR_NAMES = {
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
    ".kube",
    ".password-store",
    "gcloud",
}

_SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".git-credentials",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "secrets.json",
    "login data",
    "login data for account",
    "cookies",
    "key4.db",
    "logins.json",
    "jarvis.db",
    "jarvis.db-wal",
    "jarvis.db-shm",
}

_SENSITIVE_SUFFIXES = {".pfx", ".p12", ".kdbx", ".key"}


class PathGuard:
    def __init__(
        self,
        allowed_roots: Iterable[str | Path],
        *,
        data_dir: str | Path,
        block_sensitive: bool = True,
        base_dir: str | Path | None = None,
    ) -> None:
        self.base_dir = Path(base_dir or Path.home()).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.block_sensitive = block_sensitive
        roots: list[Path] = []
        for raw in [*allowed_roots, self.data_dir]:
            try:
                path = Path(os.path.expandvars(str(raw))).expanduser().resolve()
            except OSError:
                continue
            if path not in roots:
                roots.append(path)
        self.allowed_roots = roots

    def _within(self, path: Path, root: Path) -> bool:
        try:
            common = os.path.commonpath([os.path.normcase(str(path)), os.path.normcase(str(root))])
        except ValueError:
            return False
        return common == os.path.normcase(str(root))

    def is_allowed(self, path: Path) -> bool:
        return any(self._within(path, root) for root in self.allowed_roots)

    def is_sensitive(self, path: Path) -> bool:
        if not self.block_sensitive:
            return False
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            resolved = path
        if self._within(resolved, self.data_dir) and resolved.name in {
            "jarvis.db",
            "jarvis.db-wal",
            "jarvis.db-shm",
            "secrets.json",
        }:
            return True
        parts = [part.lower() for part in resolved.parts]
        if any(part in _SENSITIVE_DIR_NAMES for part in parts):
            return True
        name = resolved.name.lower()
        if name in _SENSITIVE_FILE_NAMES or name.startswith(".env."):
            return True
        if resolved.suffix.lower() in _SENSITIVE_SUFFIXES:
            return True
        # Perfis de navegador e cofres de credenciais.
        joined = "/".join(parts)
        if "user data" in joined and name in {"login data", "cookies", "web data", "local state"}:
            return True
        return False

    def resolve(
        self,
        raw_path: str,
        *,
        must_exist: bool = False,
        for_write: bool = False,
    ) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise PathAccessError("Informe um caminho de arquivo ou pasta")
        expanded = os.path.expandvars(raw_path.strip())
        path = Path(expanded).expanduser()
        if not path.is_absolute():
            path = self.base_dir / path
        try:
            resolved = path.resolve(strict=must_exist)
        except FileNotFoundError as exc:
            raise PathAccessError(f"Caminho não encontrado: {path}") from exc
        except OSError as exc:
            raise PathAccessError(f"Caminho inválido: {path} ({exc})") from exc
        if not self.is_allowed(resolved):
            roots = ", ".join(str(root) for root in self.allowed_roots)
            raise PathAccessError(
                f"Acesso negado a '{resolved}'. Diretórios autorizados: {roots}. "
                "Ajuste os diretórios autorizados nas configurações."
            )
        if self.is_sensitive(resolved):
            raise PathAccessError(
                f"Acesso bloqueado a arquivo sensível: {resolved.name}. "
                "Credenciais e cofres não são expostos ao agente."
            )
        return resolved

    def describe(self) -> list[str]:
        return [str(root) for root in self.allowed_roots]
