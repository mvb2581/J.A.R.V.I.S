"""Repositórios SQLite. Toda a persistência passa por esta camada."""

from __future__ import annotations

import re
from typing import Any

from backend.core.utils import json_dumps, json_loads, new_id, utc_now
from backend.database.database import Database
from backend.database.models import (
    ActionRecord,
    ConversationRecord,
    MemoryRecord,
    MessageRecord,
)

_CONVERSATION_SELECT = """
SELECT c.*,
       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
       (SELECT m.content FROM messages m
         WHERE m.conversation_id = c.id
         ORDER BY m.created_at DESC, m.rowid DESC LIMIT 1) AS last_message
FROM conversations c
"""

_STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das", "em", "no",
    "na", "nos", "nas", "para", "por", "com", "sem", "que", "e", "ou", "meu",
    "minha", "meus", "minhas", "eu", "voce", "você", "jarvis", "favor",
}


class ConversationRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, title: str = "Nova conversa", metadata: dict[str, Any] | None = None) -> ConversationRecord:
        conversation_id = new_id("conv")
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (conversation_id, title.strip() or "Nova conversa", now, now, json_dumps(metadata or {})),
            )
        record = self.get(conversation_id)
        if record is None:  # pragma: no cover - falha improvável de consistência
            raise RuntimeError("Não foi possível criar a conversa")
        return record

    def get(self, conversation_id: str) -> ConversationRecord | None:
        row = self.db.fetchone(_CONVERSATION_SELECT + " WHERE c.id = ?", (conversation_id,))
        return ConversationRecord.from_row(row) if row else None

    def ensure(self, conversation_id: str | None, title: str = "Nova conversa") -> ConversationRecord:
        if conversation_id:
            existing = self.get(conversation_id)
            if existing:
                return existing
        return self.create(title)

    def list(self, limit: int = 100, include_archived: bool = False) -> list[ConversationRecord]:
        where = "" if include_archived else " WHERE c.archived = 0"
        rows = self.db.fetchall(
            _CONVERSATION_SELECT + where + " ORDER BY c.updated_at DESC LIMIT ?",
            (limit,),
        )
        return [ConversationRecord.from_row(row) for row in rows]

    def touch(self, conversation_id: str) -> None:
        self.db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now(), conversation_id)
        )

    def update_title(self, conversation_id: str, title: str) -> None:
        self.db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title.strip() or "Nova conversa", utc_now(), conversation_id),
        )

    def set_archived(self, conversation_id: str, archived: bool) -> None:
        self.db.execute(
            "UPDATE conversations SET archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, utc_now(), conversation_id),
        )

    def update_metadata(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE conversations SET metadata = ?, updated_at = ? WHERE id = ?",
            (json_dumps(metadata), utc_now(), conversation_id),
        )

    def delete(self, conversation_id: str) -> None:
        self.db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


class MessageRepository:
    def __init__(self, db: Database, conversations: ConversationRepository) -> None:
        self.db = db
        self.conversations = conversations

    def add(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        message_id = new_id("msg")
        now = utc_now()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, role, content, tool_calls, tool_call_id, name, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content or "",
                    json_dumps(tool_calls) if tool_calls else None,
                    tool_call_id,
                    name,
                    json_dumps(metadata or {}),
                    now,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
            )
        record = self.get(message_id)
        if record is None:  # pragma: no cover
            raise RuntimeError("Não foi possível salvar a mensagem")
        return record

    def get(self, message_id: str) -> MessageRecord | None:
        row = self.db.fetchone("SELECT * FROM messages WHERE id = ?", (message_id,))
        return MessageRecord.from_row(row) if row else None

    def list(self, conversation_id: str, limit: int | None = None) -> list[MessageRecord]:
        if limit:
            rows = self.db.fetchall(
                """
                SELECT * FROM (
                    SELECT *, rowid AS _rowid FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC, rowid DESC LIMIT ?
                ) ORDER BY created_at ASC, _rowid ASC
                """,
                (conversation_id, limit),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC",
                (conversation_id,),
            )
        return [MessageRecord.from_row(row) for row in rows]

    def count(self, conversation_id: str) -> int:
        row = self.db.fetchone(
            "SELECT COUNT(*) AS total FROM messages WHERE conversation_id = ?", (conversation_id,)
        )
        return int(row["total"]) if row else 0

    def delete(self, message_id: str) -> None:
        self.db.execute("DELETE FROM messages WHERE id = ?", (message_id,))


class MemoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        content: str,
        *,
        category: str = "other",
        source: str = "user",
        persistent: bool = True,
        conversation_id: str | None = None,
    ) -> MemoryRecord:
        memory_id = new_id("mem")
        now = utc_now()
        self.db.execute(
            """
            INSERT INTO memories(
                id, category, content, source, persistent, conversation_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                category,
                content.strip(),
                source,
                1 if persistent else 0,
                conversation_id,
                now,
                now,
            ),
        )
        record = self.get(memory_id)
        if record is None:  # pragma: no cover
            raise RuntimeError("Não foi possível salvar a memória")
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        row = self.db.fetchone("SELECT * FROM memories WHERE id = ?", (memory_id,))
        return MemoryRecord.from_row(row) if row else None

    def list(
        self,
        *,
        category: str | None = None,
        persistent: bool | None = None,
        limit: int = 200,
    ) -> list[MemoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if persistent is not None:
            clauses.append("persistent = ?")
            params.append(1 if persistent else 0)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self.db.fetchall(
            f"SELECT * FROM memories{where} ORDER BY updated_at DESC LIMIT ?", tuple(params)
        )
        return [MemoryRecord.from_row(row) for row in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        include_temporary: bool = False,
        conversation_id: str | None = None,
    ) -> list[MemoryRecord]:
        terms = [
            term for term in re.findall(r"[\wÀ-ÿ]{3,}", query.lower()) if term not in _STOPWORDS
        ][:8]
        if not terms:
            return self.list(persistent=True, limit=limit)
        visibility = "persistent = 1"
        params: list[Any] = []
        if include_temporary and conversation_id:
            visibility = "(persistent = 1 OR conversation_id = ?)"
            params.append(conversation_id)
        like_clauses = " OR ".join("LOWER(content) LIKE ?" for _ in terms)
        params.extend(f"%{term}%" for term in terms)
        rows = self.db.fetchall(
            f"SELECT * FROM memories WHERE {visibility} AND ({like_clauses}) LIMIT 500",
            tuple(params),
        )
        scored: list[tuple[float, MemoryRecord]] = []
        for row in rows:
            record = MemoryRecord.from_row(row)
            content = record.content.lower()
            score = sum(2.0 for term in terms if term in content)
            score += sum(1.0 for term in terms if term in record.category.lower())
            score += 0.2 if record.persistent else 0.0
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        results = [record for _, record in scored[:limit]]
        if results:
            self.mark_used([record.id for record in results])
        return results

    def mark_used(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        now = utc_now()
        with self.db.transaction() as conn:
            conn.executemany(
                "UPDATE memories SET last_used_at = ? WHERE id = ?",
                [(now, memory_id) for memory_id in memory_ids],
            )

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        category: str | None = None,
        persistent: bool | None = None,
    ) -> MemoryRecord | None:
        current = self.get(memory_id)
        if current is None:
            return None
        self.db.execute(
            "UPDATE memories SET content = ?, category = ?, persistent = ?, updated_at = ? WHERE id = ?",
            (
                content.strip() if content is not None else current.content,
                category or current.category,
                1 if (persistent if persistent is not None else current.persistent) else 0,
                utc_now(),
                memory_id,
            ),
        )
        return self.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        return self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,)) > 0

    def delete_expired_temporary(self, ttl_hours: int) -> int:
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(hours=ttl_hours)).isoformat().replace("+00:00", "Z")
        return self.db.execute(
            "DELETE FROM memories WHERE persistent = 0 AND created_at < ?", (cutoff,)
        )


class ActionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        permission_level: int,
        summary: str,
        status: str = "executing",
        conversation_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> ActionRecord:
        action_id = new_id("act")
        self.db.execute(
            """
            INSERT INTO actions(
                id, conversation_id, tool_call_id, tool_name, arguments,
                permission_level, status, summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                conversation_id,
                tool_call_id,
                tool_name,
                json_dumps(arguments),
                permission_level,
                status,
                summary,
                utc_now(),
            ),
        )
        record = self.get(action_id)
        if record is None:  # pragma: no cover
            raise RuntimeError("Não foi possível registrar a ação")
        return record

    def get(self, action_id: str) -> ActionRecord | None:
        row = self.db.fetchone("SELECT * FROM actions WHERE id = ?", (action_id,))
        return ActionRecord.from_row(row) if row else None

    def update(
        self,
        action_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        completed: bool = True,
    ) -> ActionRecord | None:
        self.db.execute(
            """
            UPDATE actions SET status = ?, result = ?, error = ?, completed_at = ? WHERE id = ?
            """,
            (
                status,
                json_dumps(result) if result is not None else None,
                error,
                utc_now() if completed else None,
                action_id,
            ),
        )
        return self.get(action_id)

    def list(
        self,
        *,
        conversation_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ActionRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if conversation_id:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        rows = self.db.fetchall(
            f"SELECT * FROM actions{where} ORDER BY created_at DESC, rowid DESC LIMIT ?",
            tuple(params),
        )
        return [ActionRecord.from_row(row) for row in rows]

    def pending(self, conversation_id: str | None = None) -> list[ActionRecord]:
        return self.list(conversation_id=conversation_id, status="pending", limit=50)


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return json_loads(row["value"], default) if row else default

    def set(self, key: str, value: Any) -> None:
        self.db.execute(
            """
            INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, json_dumps(value), utc_now()),
        )

    def all(self) -> dict[str, Any]:
        rows = self.db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: json_loads(row["value"]) for row in rows}

    def delete(self, key: str) -> None:
        self.db.execute("DELETE FROM settings WHERE key = ?", (key,))
