"""Utilidades compartilhadas pelo backend."""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any


def utc_now() -> str:
    """Timestamp ISO-8601 em UTC, ordenável lexicograficamente."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}_{value}" if prefix else value


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def normalize_text(value: str) -> str:
    """Minúsculas, sem acentos e com espaços normalizados."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def truncate(value: str, limit: int, suffix: str = "…") -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - len(suffix))] + suffix


def human_bytes(value: float | int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} TB"


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:3]}…{value[-3:]}"


def is_probably_secret(value: str) -> bool:
    """Heurística para evitar gravar credenciais na memória."""
    patterns = [
        r"\bsk-[A-Za-z0-9_\-]{16,}\b",
        r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b",
        r"\bAIza[0-9A-Za-z_\-]{30,}\b",
        r"\bghp_[A-Za-z0-9]{30,}\b",
        r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b",
        r"(?i)\b(api[_-]?key|token|senha|password|secret)\b\s*[:=]\s*\S{8,}",
        r"\b[A-Fa-f0-9]{40,}\b",
    ]
    return any(re.search(pattern, value) for pattern in patterns)


def coerce_json_safe(value: Any, max_depth: int = 8) -> Any:
    """Converte valores arbitrários em estruturas serializáveis em JSON."""
    if max_depth <= 0:
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {
            str(key): coerce_json_safe(item, max_depth - 1) for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [coerce_json_safe(item, max_depth - 1) for item in value]
    return str(value)
