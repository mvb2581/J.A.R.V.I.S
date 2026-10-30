"""Testes das ferramentas de arquivos com o PathGuard real."""

from __future__ import annotations

from pathlib import Path

from backend.tools.filesystem import (
    CopyFileTool,
    CreateDirectoryTool,
    CreateFileTool,
    DeleteFileTool,
    EditFileTool,
    GetFileInfoTool,
    ListDirectoryTool,
    MoveFileTool,
    OrganizeFolderTool,
    ReadFileTool,
    SearchFilesTool,
)


async def test_create_and_read_file(tool_context, workspace: Path) -> None:
    target = workspace / "nota.txt"
    created = await CreateFileTool().run(
        {"path": str(target), "content": "Olá, senhor."}, tool_context
    )
    assert created.success is True
    assert target.read_text(encoding="utf-8") == "Olá, senhor."

    read = await ReadFileTool().run({"path": str(target)}, tool_context)
    assert read.success is True
    assert read.data["content"] == "Olá, senhor."
    assert read.data["truncated"] is False


async def test_create_file_requires_overwrite(tool_context, workspace: Path) -> None:
    target = workspace / "existente.txt"
    target.write_text("antigo", encoding="utf-8")
    refused = await CreateFileTool().run(
        {"path": str(target), "content": "novo"}, tool_context
    )
    assert refused.success is False
    assert "já existe" in refused.error

    replaced = await CreateFileTool().run(
        {"path": str(target), "content": "novo", "overwrite": True}, tool_context
    )
    assert replaced.success is True
    assert target.read_text(encoding="utf-8") == "novo"


async def test_read_file_truncates(tool_context, workspace: Path) -> None:
    target = workspace / "grande.txt"
    target.write_text("x" * 500, encoding="utf-8")
    result = await ReadFileTool().run({"path": str(target), "max_chars": 100}, tool_context)
    assert result.success is True
    assert len(result.data["content"]) == 100
    assert result.data["truncated"] is True


async def test_edit_file_requires_unique_match(tool_context, workspace: Path) -> None:
    target = workspace / "codigo.py"
    target.write_text("valor = 1\nvalor = 1\n", encoding="utf-8")
    ambiguous = await EditFileTool().run(
        {"path": str(target), "old_text": "valor = 1", "new_text": "valor = 2"},
        tool_context,
    )
    assert ambiguous.success is False
    assert "aparece 2 vezes" in ambiguous.error

    replaced = await EditFileTool().run(
        {
            "path": str(target),
            "old_text": "valor = 1",
            "new_text": "valor = 2",
            "replace_all": True,
        },
        tool_context,
    )
    assert replaced.success is True
    assert target.read_text(encoding="utf-8") == "valor = 2\nvalor = 2\n"

    missing = await EditFileTool().run(
        {"path": str(target), "old_text": "inexistente", "new_text": "x"}, tool_context
    )
    assert missing.success is False


async def test_list_directory_hides_sensitive_files(tool_context, workspace: Path) -> None:
    (workspace / "visivel.txt").write_text("ok", encoding="utf-8")
    (workspace / ".env").write_text("SEGREDO=1", encoding="utf-8")
    result = await ListDirectoryTool().run({"path": str(workspace)}, tool_context)
    assert result.success is True
    names = {entry["name"] for entry in result.data["entries"]}
    assert "visivel.txt" in names
    assert ".env" not in names


async def test_search_files_finds_by_name(tool_context, workspace: Path) -> None:
    (workspace / "projetos").mkdir()
    (workspace / "projetos" / "jarvis.py").write_text("print('oi')", encoding="utf-8")
    (workspace / "projetos" / "outro.txt").write_text("oi", encoding="utf-8")
    result = await SearchFilesTool().run(
        {"query": "jarvis", "root": str(workspace)}, tool_context
    )
    assert result.success is True
    assert [entry["name"] for entry in result.data["results"]] == ["jarvis.py"]


async def test_create_directory_move_and_copy(tool_context, workspace: Path) -> None:
    folder = workspace / "nova" / "subpasta"
    created = await CreateDirectoryTool().run({"path": str(folder)}, tool_context)
    assert created.success is True
    assert folder.is_dir()

    source = workspace / "origem.txt"
    source.write_text("conteúdo", encoding="utf-8")
    moved = await MoveFileTool().run(
        {"source": str(source), "destination": str(folder / "destino.txt")}, tool_context
    )
    assert moved.success is True
    assert not source.exists()
    assert (folder / "destino.txt").read_text(encoding="utf-8") == "conteúdo"

    copied = await CopyFileTool().run(
        {"source": str(folder / "destino.txt"), "destination": str(workspace / "copia.txt")},
        tool_context,
    )
    assert copied.success is True
    assert (workspace / "copia.txt").read_text(encoding="utf-8") == "conteúdo"


async def test_move_and_delete_refuse_authorized_root(tool_context, workspace: Path) -> None:
    moved = await MoveFileTool().run(
        {"source": str(workspace), "destination": str(workspace.parent / "outra")},
        tool_context,
    )
    assert moved.success is False

    deleted = await DeleteFileTool().run(
        {"path": str(workspace), "recursive": True, "permanent": True}, tool_context
    )
    assert deleted.success is False
    assert "raiz" in deleted.error


async def test_delete_file_permanently(tool_context, workspace: Path) -> None:
    target = workspace / "apagar.txt"
    target.write_text("x", encoding="utf-8")
    result = await DeleteFileTool().run(
        {"path": str(target), "permanent": True}, tool_context
    )
    assert result.success is True
    assert not target.exists()


async def test_organize_folder_dry_run_and_apply(tool_context, workspace: Path) -> None:
    (workspace / "foto.png").write_bytes(b"\x89PNG")
    (workspace / "documento.pdf").write_bytes(b"%PDF")
    dry = await OrganizeFolderTool().run({"path": str(workspace), "dry_run": True}, tool_context)
    assert dry.success is True
    assert dry.data["dry_run"] is True
    assert len(dry.data["plan"]) == 2
    assert (workspace / "foto.png").exists()

    applied = await OrganizeFolderTool().run(
        {"path": str(workspace), "dry_run": False}, tool_context
    )
    assert applied.success is True
    assert len(applied.data["moved"]) == 2
    assert (workspace / "Imagens" / "foto.png").exists()
    assert (workspace / "Documentos" / "documento.pdf").exists()


async def test_file_info(tool_context, workspace: Path) -> None:
    target = workspace / "info.txt"
    target.write_text("12345", encoding="utf-8")
    result = await GetFileInfoTool().run({"path": str(target)}, tool_context)
    assert result.success is True
    assert result.data["size"] == 5
    assert result.data["suffix"] == ".txt"


async def test_read_sensitive_and_outside_paths_are_blocked(
    tool_context, workspace: Path, tmp_path: Path
) -> None:
    secret = workspace / ".env"
    secret.write_text("CHAVE=segredo", encoding="utf-8")
    blocked = await ReadFileTool().run({"path": str(secret)}, tool_context)
    assert blocked.success is False
    assert "sensível" in blocked.error

    outside = tmp_path / "fora.txt"
    outside.write_text("x", encoding="utf-8")
    denied = await ReadFileTool().run({"path": str(outside)}, tool_context)
    assert denied.success is False
    assert "Acesso negado" in denied.error


async def test_unknown_arguments_are_rejected(tool_context, workspace: Path) -> None:
    result = await ReadFileTool().run(
        {"path": str(workspace / "x.txt"), "argumento_extra": True}, tool_context
    )
    assert result.success is False
    assert "Argumentos inválidos" in result.error
