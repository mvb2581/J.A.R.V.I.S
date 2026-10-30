"""Testes da normalização de argumentos vindos de modelos locais."""

from __future__ import annotations

from typing import Any

import pytest

from backend.tools.base import BaseTool, ToolContext, ToolResult, ToolValidationError


class ExampleTool(BaseTool):
    name = "example"
    parameters = {
        "type": "object",
        "properties": {
            "flag": {"type": "boolean"},
            "count": {"type": "integer"},
            "ratio": {"type": "number"},
            "labels": {"type": "array", "items": {"type": "string"}},
            "options": {
                "type": "object",
                "properties": {"enabled": {"type": "boolean"}},
                "additionalProperties": False,
            },
            "mode": {"type": "string", "enum": ["fast", "safe"]},
        },
        "required": ["flag"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok(arguments)


def test_coerces_primitive_and_nested_values() -> None:
    tool = ExampleTool()
    original = {
        "flag": "false",
        "count": "3",
        "ratio": "1.5",
        "labels": '["a", "b"]',
        "options": '{"enabled": "true"}',
        "mode": "fast",
    }

    normalized = tool.validate_arguments(original)

    assert normalized == {
        "flag": False,
        "count": 3,
        "ratio": 1.5,
        "labels": ["a", "b"],
        "options": {"enabled": True},
        "mode": "fast",
    }
    assert original["flag"] == "false"


def test_keeps_valid_values_untouched() -> None:
    tool = ExampleTool()
    arguments = {"flag": True, "count": 2, "ratio": 0.5, "labels": ["x"]}

    assert tool.validate_arguments(arguments) == arguments


def test_rejects_non_boolean_text() -> None:
    tool = ExampleTool()

    with pytest.raises(ToolValidationError, match="flag"):
        tool.validate_arguments({"flag": "talvez"})


def test_rejects_unknown_properties_after_coercion() -> None:
    tool = ExampleTool()

    with pytest.raises(ToolValidationError):
        tool.validate_arguments({"flag": "true", "extra": "não permitido"})


def test_coerces_integer_enum_and_numeric_strings() -> None:
    class EnumTool(BaseTool):
        name = "enum"
        parameters = {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "enum": [1, 2, 3]},
                "enabled": {"enum": [True, False]},
            },
            "additionalProperties": False,
        }

        async def execute(
            self, arguments: dict[str, Any], context: ToolContext
        ) -> ToolResult:
            return ToolResult.ok(arguments)

    normalized = EnumTool().validate_arguments({"level": "2", "enabled": "false"})

    assert normalized == {"level": 2, "enabled": False}
