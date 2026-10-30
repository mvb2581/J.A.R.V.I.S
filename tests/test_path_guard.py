"""Testes do isolamento de caminhos e bloqueio de arquivos sensíveis."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.tools.path_guard import PathAccessError, PathGuard


@pytest.fixture
def guard(tmp_path: Path) -> PathGuard:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return PathGuard(
        [str(workspace)],
        data_dir=data_dir,
        block_sensitive=True,
        base_dir=workspace,
    )


def test_allows_paths_inside_authorized_root(guard: PathGuard, tmp_path: Path) -> None:
    target = tmp_path / "workspace" / "projeto" / "arquivo.txt"
    assert guard.resolve(str(target), for_write=True) == target.resolve()


def test_blocks_paths_outside_authorized_roots(guard: PathGuard, tmp_path: Path) -> None:
    with pytest.raises(PathAccessError):
        guard.resolve(str(tmp_path / "fora.txt"))


def test_blocks_traversal_out_of_root(guard: PathGuard) -> None:
    with pytest.raises(PathAccessError):
        guard.resolve("../fora.txt")


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        "id_rsa",
        "secrets.json",
        "jarvis.db",
        "cofre.kdbx",
        "chave.pfx",
        "login data",
    ],
)
def test_blocks_sensitive_files(guard: PathGuard, tmp_path: Path, name: str) -> None:
    target = tmp_path / "workspace" / name
    target.write_text("conteudo", encoding="utf-8")
    with pytest.raises(PathAccessError):
        guard.resolve(str(target), must_exist=True)


def test_blocks_sensitive_directories(guard: PathGuard, tmp_path: Path) -> None:
    target = tmp_path / "workspace" / ".ssh" / "config"
    target.parent.mkdir()
    target.write_text("Host *", encoding="utf-8")
    with pytest.raises(PathAccessError):
        guard.resolve(str(target), must_exist=True)


def test_sensitive_can_be_allowed_explicitly(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    guard = PathGuard(
        [str(workspace)],
        data_dir=data_dir,
        block_sensitive=False,
        base_dir=workspace,
    )
    target = workspace / ".env"
    target.write_text("CHAVE=1", encoding="utf-8")
    assert guard.resolve(str(target), must_exist=True) == target.resolve()


def test_missing_path_raises_when_required(guard: PathGuard, tmp_path: Path) -> None:
    with pytest.raises(PathAccessError):
        guard.resolve(str(tmp_path / "workspace" / "nao-existe.txt"), must_exist=True)


def test_data_dir_is_implicitly_allowed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    guard = PathGuard([str(workspace)], data_dir=data_dir)
    target = data_dir / "screenshots" / "tela.png"
    assert guard.resolve(str(target), for_write=True) == target.resolve()
    with pytest.raises(PathAccessError):
        guard.resolve(str(data_dir / "jarvis.db"))


def test_empty_path_is_rejected(guard: PathGuard) -> None:
    with pytest.raises(PathAccessError):
        guard.resolve("   ")
