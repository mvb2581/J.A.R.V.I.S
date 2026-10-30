"""Camada de acesso ao SQLite com migrações versionadas.

Cada operação abre sua própria conexão curta. Isso evita compartilhar uma
conexão entre threads (o servidor, a voz e o TTS rodam em threads distintas) e
mantém o código compatível com uma futura troca de banco via repositórios.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            metadata TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            tool_calls TEXT,
            tool_call_id TEXT,
            name TEXT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, created_at);

        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL DEFAULT 'other',
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'user',
            persistent INTEGER NOT NULL DEFAULT 1,
            conversation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
        CREATE INDEX IF NOT EXISTS idx_memories_persistent ON memories(persistent);

        CREATE TABLE IF NOT EXISTS actions (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            tool_call_id TEXT,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL DEFAULT '{}',
            permission_level INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'executing',
            summary TEXT NOT NULL DEFAULT '',
            result TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_actions_conversation
            ON actions(conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
]


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._init_lock = threading.Lock()
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def initialize(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = self.connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                    """
                )
                applied = {
                    row["version"]
                    for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
                }
                for version, script in MIGRATIONS:
                    if version in applied:
                        continue
                    logger.info("Aplicando migração do banco versão %s", version)
                    conn.executescript(script)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_migrations(version) VALUES (?)", (version,)
                    )
                    conn.commit()
                self._initialized = True
            finally:
                conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def health(self) -> bool:
        try:
            row = self.fetchone("SELECT 1 AS ok")
            return bool(row and row["ok"] == 1)
        except sqlite3.Error:
            logger.exception("Falha no health check do SQLite")
            return False
