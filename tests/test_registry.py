"""Testes do registro e dos contratos das ferramentas."""

from __future__ import annotations

from jsonschema import Draft202012Validator

from backend.tools.base import ToolContext, ToolResult
from backend.tools.registry import ToolRegistry, build_default_registry


def test_default_registry_has_31_unique_tools() -> None:
    registry = build_default_registry()
    tools = registry.all()
    names = [tool.name for tool in tools]
    assert len(tools) == 31
    assert len(names) == len(set(names))


def test_all_tool_schemas_are_valid() -> None:
    for tool in build_default_registry().all():
        Draft202012Validator.check_schema(tool.parameters)
        assert tool.parameters.get("type") == "object"
        assert tool.description.strip()
        assert 1 <= tool.permission_level <= 3
        assert tool.category.strip()


def test_definitions_have_openai_shape() -> None:
    definitions = build_default_registry().definitions()
    assert len(definitions) == 31
    for definition in definitions:
        assert definition["type"] == "function"
        function = definition["function"]
        assert function["name"]
        assert function["description"]
        assert isinstance(function["parameters"], dict)


def test_expected_tools_are_registered() -> None:
    names = {tool.name for tool in build_default_registry().all()}
    expected = {
        "search_files",
        "list_directory",
        "read_file",
        "create_file",
        "edit_file",
        "create_directory",
        "move_file",
        "copy_file",
        "delete_file",
        "organize_folder",
        "get_file_info",
        "open_application",
        "open_path",
        "close_application",
        "manage_windows",
        "execute_terminal_command",
        "get_system_information",
        "get_resource_usage",
        "get_process_list",
        "control_volume",
        "control_media",
        "browser_search",
        "open_url",
        "browser_automation",
        "screenshot",
        "computer_interaction",
        "save_memory",
        "search_memory",
        "list_memories",
        "delete_memory",
        "update_plan",
    }
    assert names == expected


def test_registry_rejects_duplicates() -> None:
    registry = build_default_registry()
    tool = registry.all()[0]
    try:
        registry.register(tool)
    except ValueError as exc:
        assert "duplicada" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("O registro deveria recusar ferramentas duplicadas")


async def test_registry_unknown_tool_returns_failure(tool_context: ToolContext) -> None:
    registry = ToolRegistry()
    result = await registry.run("inexistente", {}, tool_context)
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "desconhecida" in result.error
