"""Ferramentas de sistema de arquivos com validação e proteção de caminhos."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.utils import human_bytes
from backend.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    "AppData",
    "$Recycle.Bin",
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "System Volume Information",
}

_CATEGORIES: dict[str, set[str]] = {
    "Imagens": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tif", ".tiff", ".heic"},
    "Documentos": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".md"},
    "Videos": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"},
    "Musicas": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Arquivos": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".iso"},
    "Instaladores": {".exe", ".msi", ".msix", ".appx"},
    "Codigo": {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".xml", ".yml", ".yaml", ".sql", ".ps1", ".bat"},
}


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")


def _file_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "is_dir": path.is_dir(),
        "size": stat.st_size,
        "size_human": human_bytes(stat.st_size),
        "modified": _iso(stat.st_mtime),
        "created": _iso(stat.st_ctime),
    }


def _atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temp, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def _read_text(path: Path, max_chars: int) -> tuple[str, str, bool, int]:
    size = path.stat().st_size
    read_limit = min(max(size, 1), max(2_000_000, max_chars * 4))
    raw = path.read_bytes()[:read_limit]
    if b"\x00" in raw[:8192]:
        raise ValueError("O arquivo parece ser binário e não pode ser lido como texto")
    encoding = "utf-8"
    text = ""
    candidates = (
        ("utf-8-sig", "utf-8", "cp1252", "latin-1")
        if raw.startswith(b"\xef\xbb\xbf")
        else ("utf-8", "cp1252", "latin-1")
    )
    for candidate in candidates:
        try:
            text = raw.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if not text and raw:
        raise ValueError("Não foi possível decodificar o arquivo como texto")
    truncated = len(text) > max_chars or size > read_limit
    return text[:max_chars], encoding, truncated, size


def _trash(path: Path) -> None:
    try:
        from send2trash import send2trash
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise RuntimeError("send2trash não está instalado; use permanent=true") from exc
    send2trash(str(path))


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = (
        "Pesquisa arquivos por nome (substring, sem diferenciar maiúsculas) dentro de um diretório "
        "autorizado. Use para localizar projetos, configurações e documentos antes de abrir ou ler."
    )
    permission_level = 1
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 200, "description": "Parte do nome do arquivo. Vazio lista arquivos."},
            "root": {"type": "string", "description": "Diretório inicial. Padrão: pasta do usuário."},
            "extensions": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
                "description": "Extensões opcionais, por exemplo ['.py', '.json'].",
            },
            "max_results": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            "include_hidden": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        query = (arguments.get("query") or "").lower().strip()
        root = context.path_guard.resolve(arguments.get("root") or str(context.user_home))
        if not root.is_dir():
            return ToolResult.fail(f"O diretório não existe: {root}")
        extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in arguments.get("extensions", [])
        }
        max_results = int(arguments.get("max_results", 50))
        max_depth = int(arguments.get("max_depth", 8))
        include_hidden = bool(arguments.get("include_hidden", False))
        base_depth = len(root.parts)
        results: list[dict[str, Any]] = []
        truncated = False
        for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.parts) - base_depth
            dirs[:] = [
                name
                for name in dirs
                if (include_hidden or not name.startswith("."))
                and name not in _SKIP_DIRS
                and not context.path_guard.is_sensitive(current_path / name)
            ]
            if depth >= max_depth:
                dirs[:] = []
            for filename in files:
                if not include_hidden and filename.startswith("."):
                    continue
                if query and query not in filename.lower():
                    continue
                if extensions and Path(filename).suffix.lower() not in extensions:
                    continue
                path = current_path / filename
                if context.path_guard.is_sensitive(path):
                    continue
                try:
                    results.append(_file_info(path))
                except OSError:
                    continue
                if len(results) >= max_results:
                    truncated = True
                    break
            if truncated:
                break
        display = (
            f"{len(results)} arquivo(s) encontrado(s) em {root}"
            + (" (limite atingido)" if truncated else "")
        )
        return ToolResult.ok(
            {"root": str(root), "query": query, "results": results, "truncated": truncated},
            display=display,
        )


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "Lista arquivos e subpastas de um diretório autorizado."
    permission_level = 1
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Diretório a listar. Padrão: pasta do usuário."},
            "include_hidden": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
        },
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments.get("path") or str(context.user_home))
        if not path.is_dir():
            return ToolResult.fail(f"Não é um diretório: {path}")
        include_hidden = bool(arguments.get("include_hidden", False))
        limit = int(arguments.get("limit", 100))
        entries: list[dict[str, Any]] = []
        try:
            children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível listar {path}: {exc}")
        for child in children:
            if not include_hidden and child.name.startswith("."):
                continue
            if context.path_guard.is_sensitive(child):
                continue
            try:
                entries.append(_file_info(child))
            except OSError:
                continue
            if len(entries) >= limit:
                break
        return ToolResult.ok(
            {"path": str(path), "entries": entries, "truncated": len(children) > len(entries)},
            display=f"{len(entries)} item(ns) em {path}",
        )


class ReadFileTool(BaseTool):
    name = "read_file"
    description = (
        "Lê o conteúdo de um arquivo de texto autorizado. Arquivos binários, credenciais e arquivos "
        "sensiveis são bloqueados. O conteúdo pode ser truncado em arquivos grandes."
    )
    permission_level = 1
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000, "default": 20000},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], must_exist=True)
        if path.is_dir():
            return ToolResult.fail(f"O caminho é um diretório: {path}")
        try:
            text, encoding, truncated, size = _read_text(path, int(arguments.get("max_chars", 20000)))
        except (OSError, ValueError) as exc:
            return ToolResult.fail(f"Não foi possível ler {path.name}: {exc}")
        return ToolResult.ok(
            {
                "path": str(path),
                "content": text,
                "encoding": encoding,
                "size": size,
                "truncated": truncated,
            },
            display=f"Lido {path.name} ({human_bytes(size)}, {encoding})" + (" — truncado" if truncated else ""),
        )


class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Cria um arquivo de texto. Não sobrescreve arquivos existentes sem overwrite=true."
    permission_level = 2
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string", "maxLength": 500000},
            "overwrite": {"type": "boolean", "default": False},
            "create_parents": {"type": "boolean", "default": True},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], for_write=True)
        if path.exists() and not arguments.get("overwrite", False):
            return ToolResult.fail(f"O arquivo já existe: {path}. Use overwrite=true para substituí-lo.")
        if not path.parent.exists() and not arguments.get("create_parents", True):
            return ToolResult.fail(f"A pasta pai não existe: {path.parent}")
        try:
            _atomic_write(path, arguments["content"])
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível criar {path}: {exc}")
        return ToolResult.ok(
            {"path": str(path), "bytes": path.stat().st_size},
            display=f"Arquivo criado: {path}",
        )


class EditFileTool(BaseTool):
    name = "edit_file"
    description = (
        "Substitui texto exato em um arquivo existente. Se old_text aparecer mais de uma vez, "
        "use replace_all=true ou forneça mais contexto."
    )
    permission_level = 2
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string", "minLength": 1},
            "new_text": {"type": "string"},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old_text", "new_text"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], must_exist=True, for_write=True)
        if path.is_dir():
            return ToolResult.fail(f"O caminho é um diretório: {path}")
        try:
            text, encoding, truncated, _ = _read_text(path, 5_000_000)
        except (OSError, ValueError) as exc:
            return ToolResult.fail(f"Não foi possível ler {path}: {exc}")
        if truncated:
            return ToolResult.fail("O arquivo é grande demais para edição segura (limite de 5 MB)")
        old_text = arguments["old_text"]
        count = text.count(old_text)
        if count == 0:
            return ToolResult.fail("O texto informado não foi encontrado no arquivo")
        if count > 1 and not arguments.get("replace_all", False):
            return ToolResult.fail(
                f"O texto aparece {count} vezes. Forneça mais contexto ou use replace_all=true."
            )
        updated = text.replace(old_text, arguments["new_text"], -1 if arguments.get("replace_all") else 1)
        try:
            _atomic_write(path, updated, encoding=encoding)
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível gravar {path}: {exc}")
        return ToolResult.ok(
            {"path": str(path), "replacements": count if arguments.get("replace_all") else 1},
            display=f"Arquivo editado: {path}",
        )


class CreateDirectoryTool(BaseTool):
    name = "create_directory"
    description = "Cria uma pasta, incluindo pastas pai quando parents=true."
    permission_level = 2
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "parents": {"type": "boolean", "default": True},
            "exist_ok": {"type": "boolean", "default": True},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], for_write=True)
        if path.exists() and not arguments.get("exist_ok", True):
            return ToolResult.fail(f"A pasta já existe: {path}")
        try:
            path.mkdir(parents=arguments.get("parents", True), exist_ok=arguments.get("exist_ok", True))
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível criar {path}: {exc}")
        return ToolResult.ok({"path": str(path)}, display=f"Pasta criada: {path}")


class MoveFileTool(BaseTool):
    name = "move_file"
    description = "Move ou renomeia um arquivo/pasta dentro dos diretórios autorizados."
    permission_level = 2
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "overwrite": {"type": "boolean", "default": False},
        },
        "required": ["source", "destination"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        source = context.path_guard.resolve(arguments["source"], must_exist=True, for_write=True)
        destination = context.path_guard.resolve(arguments["destination"], for_write=True)
        if source in context.path_guard.allowed_roots:
            return ToolResult.fail("Não é permitido mover a raiz de um diretório autorizado")
        if destination.is_dir():
            destination = destination / source.name
        if destination.exists():
            if not arguments.get("overwrite", False):
                return ToolResult.fail(f"O destino já existe: {destination}")
            if destination.is_dir():
                return ToolResult.fail("Não é seguro sobrescrever diretórios; escolha outro destino")
            destination.unlink()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível mover: {exc}")
        return ToolResult.ok(
            {"source": str(source), "destination": str(destination)},
            display=f"Movido: {source.name} → {destination}",
        )


class CopyFileTool(BaseTool):
    name = "copy_file"
    description = "Copia um arquivo ou pasta para outro local autorizado."
    permission_level = 2
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "overwrite": {"type": "boolean", "default": False},
        },
        "required": ["source", "destination"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        source = context.path_guard.resolve(arguments["source"], must_exist=True)
        destination = context.path_guard.resolve(arguments["destination"], for_write=True)
        if destination.is_dir():
            destination = destination / source.name
        if destination.exists() and not arguments.get("overwrite", False):
            return ToolResult.fail(f"O destino já existe: {destination}")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(
                    source, destination, dirs_exist_ok=arguments.get("overwrite", False)
                )
            else:
                shutil.copy2(source, destination)
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível copiar: {exc}")
        return ToolResult.ok(
            {"source": str(source), "destination": str(destination)},
            display=f"Copiado: {source.name} → {destination}",
        )


class DeleteFileTool(BaseTool):
    name = "delete_file"
    description = (
        "Remove um arquivo ou pasta. Por padrão envia para a Lixeira. Ação crítica: requer confirmação. "
        "Permanent=true apaga definitivamente."
    )
    permission_level = 3
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "permanent": {"type": "boolean", "default": False},
            "recursive": {"type": "boolean", "default": False},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def summarize(self, arguments: dict[str, Any]) -> str:
        mode = "permanentemente" if arguments.get("permanent") else "para a Lixeira"
        return f"Excluir {arguments.get('path', '?')} {mode}"

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], must_exist=True, for_write=True)
        if path in context.path_guard.allowed_roots or path == context.user_home:
            return ToolResult.fail("Não é permitido excluir a raiz de um diretório autorizado")
        was_dir = path.is_dir()
        if was_dir and not arguments.get("recursive", False):
            return ToolResult.fail("É uma pasta; use recursive=true para confirmar a remoção do conteúdo")
        permanent = bool(arguments.get("permanent", False))
        try:
            if permanent:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            else:
                _trash(path)
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível excluir {path}: {exc}")
        return ToolResult.ok(
            {"path": str(path), "permanent": permanent, "is_dir": was_dir},
            display=f"{'Apagado definitivamente' if permanent else 'Enviado para a Lixeira'}: {path}",
        )


class OrganizeFolderTool(BaseTool):
    name = "organize_folder"
    description = (
        "Organiza os arquivos de uma pasta em subpastas por tipo (Imagens, Documentos, Videos, "
        "Musicas, Arquivos, Instaladores, Codigo). Use dry_run=true para mostrar o plano antes de mover."
    )
    permission_level = 2
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "dry_run": {"type": "boolean", "default": True},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def summarize(self, arguments: dict[str, Any]) -> str:
        action = "Simular organização" if arguments.get("dry_run", True) else "Organizar arquivos"
        return f"{action} em {arguments.get('path', '?')}"

    def _category_for(self, suffix: str) -> str:
        suffix = suffix.lower()
        for category, extensions in _CATEGORIES.items():
            if suffix in extensions:
                return category
        return "Outros"

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        folder = context.path_guard.resolve(arguments["path"], must_exist=True, for_write=True)
        if not folder.is_dir():
            return ToolResult.fail(f"Não é um diretório: {folder}")
        dry_run = bool(arguments.get("dry_run", True))
        plan: list[dict[str, Any]] = []
        moved: list[dict[str, Any]] = []
        skipped: list[str] = []
        used_names: set[str] = set()
        for item in folder.iterdir():
            if not item.is_file() or item.name.startswith("."):
                continue
            category = self._category_for(item.suffix)
            target_dir = folder / category
            target = target_dir / item.name
            if target.exists() or str(target).lower() in used_names:
                stem, suffix = item.stem, item.suffix
                counter = 1
                while target.exists() or str(target).lower() in used_names:
                    target = target_dir / f"{stem} ({counter}){suffix}"
                    counter += 1
            used_names.add(str(target).lower())
            plan.append(
                {
                    "source": str(item),
                    "destination": str(target),
                    "category": category,
                    "size": item.stat().st_size,
                }
            )
            if not dry_run:
                try:
                    target_dir.mkdir(exist_ok=True)
                    shutil.move(str(item), str(target))
                    moved.append({"source": str(item), "destination": str(target)})
                except OSError as exc:
                    skipped.append(f"{item.name}: {exc}")
        display = (
            f"Plano com {len(plan)} arquivo(s) em {folder}"
            if dry_run
            else f"{len(moved)} arquivo(s) organizado(s) em {folder}; {len(skipped)} falha(s)"
        )
        return ToolResult.ok(
            {
                "path": str(folder),
                "dry_run": dry_run,
                "plan": plan,
                "moved": moved,
                "skipped": skipped,
            },
            display=display,
        )


class GetFileInfoTool(BaseTool):
    name = "get_file_info"
    description = "Retorna metadados de um arquivo ou pasta (tamanho, datas, tipo)."
    permission_level = 1
    category = "filesystem"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        path = context.path_guard.resolve(arguments["path"], must_exist=True)
        try:
            info = _file_info(path)
        except OSError as exc:
            return ToolResult.fail(f"Não foi possível consultar {path}: {exc}")
        info["suffix"] = path.suffix
        info["parent"] = str(path.parent)
        return ToolResult.ok(info, display=f"{path.name}: {info['size_human']}")
