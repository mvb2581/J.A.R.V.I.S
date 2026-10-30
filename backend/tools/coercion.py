"""Normalização tolerante de argumentos de ferramentas.

Modelos locais menores às vezes devolvem valores primitivos como texto, por
exemplo ``{"include_gpu": "false"}`` em vez de ``{"include_gpu": false}``.
Esta camada converte apenas os tipos declarados no JSON Schema da ferramenta;
a validação estrita continua acontecendo depois. Nenhum campo novo é criado e
nenhuma regra de permissão ou de caminho é alterada.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from jsonschema import Draft202012Validator

_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_MAX_DEPTH = 12
_NO_MATCH = object()


def coerce_arguments(
    arguments: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    """Devolve uma cópia dos argumentos com tipos compatíveis com o schema."""
    if not isinstance(arguments, dict) or not isinstance(schema, dict):
        return arguments
    coerced = _coerce_object(arguments, schema, depth=0)
    return coerced if isinstance(coerced, dict) else arguments


def _coerce_object(
    value: dict[str, Any], schema: dict[str, Any], *, depth: int
) -> dict[str, Any]:
    if depth > _MAX_DEPTH:
        return value
    result = dict(value)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, subschema in properties.items():
            if key in result and isinstance(subschema, dict):
                result[key] = _coerce_value(result[key], subschema, depth=depth + 1)
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        known = properties if isinstance(properties, dict) else {}
        for key in result:
            if key not in known:
                result[key] = _coerce_value(result[key], additional, depth=depth + 1)
    return result


def _coerce_value(value: Any, schema: dict[str, Any], *, depth: int) -> Any:
    if depth > _MAX_DEPTH or not isinstance(schema, dict):
        return value

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for subschema in all_of:
            if isinstance(subschema, dict):
                value = _coerce_value(value, subschema, depth=depth + 1)

    if "const" in schema and value != schema["const"]:
        matched = _match_enum(value, [schema["const"]])
        if matched is not _NO_MATCH:
            value = matched

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        matched = _match_enum(value, enum)
        if matched is not _NO_MATCH:
            value = matched

    for keyword in ("anyOf", "oneOf"):
        options = schema.get(keyword)
        if isinstance(options, list) and options:
            for option in options:
                if not isinstance(option, dict):
                    continue
                candidate = _coerce_value(value, option, depth=depth + 1)
                if _is_valid(candidate, option):
                    return candidate

    type_spec = schema.get("type")
    if isinstance(type_spec, str):
        type_names = [type_spec]
    elif isinstance(type_spec, list):
        type_names = [item for item in type_spec if isinstance(item, str)]
    else:
        type_names = []

    for type_name in type_names:
        candidate = _coerce_to_type(value, type_name, depth=depth + 1)
        if candidate is not _NO_MATCH:
            value = candidate
            break

    items = schema.get("items")
    if isinstance(value, list) and isinstance(items, dict):
        value = [
            _coerce_value(item, items, depth=depth + 1) for item in value
        ]
    if isinstance(value, dict):
        value = _coerce_object(value, schema, depth=depth + 1)
    return value


def _coerce_to_type(value: Any, type_name: str, *, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return _NO_MATCH

    if type_name == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
        return _NO_MATCH

    if type_name == "integer":
        if isinstance(value, bool):
            return _NO_MATCH
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and _INTEGER_RE.match(value.strip()):
            try:
                return int(value.strip())
            except ValueError:
                return _NO_MATCH
        return _NO_MATCH

    if type_name == "number":
        if isinstance(value, bool):
            return _NO_MATCH
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                return _NO_MATCH
            return number if math.isfinite(number) else _NO_MATCH
        return _NO_MATCH

    if type_name == "string":
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return _NO_MATCH

    if type_name == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return _NO_MATCH
            return parsed if isinstance(parsed, list) else _NO_MATCH
        return _NO_MATCH

    if type_name == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip().startswith("{"):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return _NO_MATCH
            return parsed if isinstance(parsed, dict) else _NO_MATCH
        return _NO_MATCH

    if type_name == "null":
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() == "null":
            return None
        return _NO_MATCH

    return _NO_MATCH


def _match_enum(value: Any, options: list[Any]) -> Any:
    if not isinstance(value, str):
        return _NO_MATCH
    normalized = value.strip().lower()
    for option in options:
        if isinstance(option, bool):
            if normalized == str(option).lower():
                return option
        elif isinstance(option, (int, float)):
            try:
                if float(value.strip()) == float(option):
                    return option
            except ValueError:
                continue
        elif isinstance(option, str) and value == option:
            return option
    return _NO_MATCH


def _is_valid(value: Any, schema: dict[str, Any]) -> bool:
    try:
        return Draft202012Validator(schema).is_valid(value)
    except Exception:  # schema inválido não deve derrubar a ferramenta
        return False
