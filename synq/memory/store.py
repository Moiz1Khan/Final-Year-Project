"""MemoryStore - save conversations, retrieve context, semantic search."""

from datetime import datetime
from typing import List, Optional, Tuple

from synq.memory.db import get_connection, init_db


class MemoryStore:
    """
    Full memory: conversations, extracted memories, scheduled items.
    Semantic recall via ChromaDB when available.
    """

    def __init__(
        self,
        db_path=None,
        api_key: Optional[str] = None,
        use_vector_search: bool = True,
    ):
        self.db_path = db_path
        self.api_key = api_key
        self.use_vector_search = use_vector_search and bool(api_key)
        self._chroma = None
        self._chroma_collection = None
        init_db(db_path)

    def _get_chroma(self):
        """Lazy init ChromaDB. Returns None if unavailable."""
        if self._chroma is not None:
            return self._chroma_collection
        if not self.use_vector_search:
            return None
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            from synq.memory.db import get_db_path
            root = get_db_path().parent / "chroma"
            root.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(root))
            ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=self.api_key,
                model_name="text-embedding-3-small",
            )
            self._chroma_collection = client.get_or_create_collection(
                name="synq_memories",
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._chroma = client
            return self._chroma_collection
        except Exception:
            self.use_vector_search = False
            return None

    def ensure_user(self, user_id: Optional[int] = None) -> int:
        """Return user_id. Create default if None."""
        conn = get_connection(self.db_path)
        try:
            if user_id is not None:
                cur = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                if cur.fetchone():
                    return user_id
            cur = conn.execute("SELECT id FROM users LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else 1
        finally:
            conn.close()

    def save_turn(self, user_id: int, role: str, content: str) -> None:
        """Save one message (user or assistant)."""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent(self, user_id: int, limit: int = 20) -> List[Tuple[str, str]]:
        """Get last N turns as [(role, content), ...]."""
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT role, content FROM conversations
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()
            return [(r["role"], r["content"]) for r in reversed(rows)]
        finally:
            conn.close()

    def add_memory(self, user_id: int, memory_type: str, content: str) -> None:
        """Add extracted memory. memory_type: fact, preference, event."""
        conn = get_connection(self.db_path)
        last_id = None
        try:
            conn.execute(
                "INSERT INTO memories (user_id, memory_type, content) VALUES (?, ?, ?)",
                (user_id, memory_type, content),
            )
            conn.commit()
            last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        finally:
            conn.close()

        coll = self._get_chroma()
        if coll is not None and last_id is not None:
            try:
                coll.add(
                    ids=[f"m_{user_id}_{last_id}"],
                    documents=[content],
                    metadatas=[{"user_id": str(user_id), "type": memory_type}],
                )
            except Exception:
                pass

    def get_relevant_memories(
        self, user_id: int, query: str, top_k: int = 5
    ) -> List[str]:
        """Semantic search over memories. Falls back to recent if no vector DB."""
        coll = self._get_chroma()
        if coll is not None:
            try:
                results = coll.query(
                    query_texts=[query],
                    n_results=top_k,
                    where={"user_id": str(user_id)},
                )
                if results and results["documents"] and results["documents"][0]:
                    return results["documents"][0]
            except Exception:
                pass

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT content FROM memories
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, top_k),
            )
            return [r["content"] for r in cur.fetchall()]
        finally:
            conn.close()

    def get_upcoming_scheduled(self, user_id: int, hours_ahead: int = 48) -> List[dict]:
        """Get scheduled items due in next N hours."""
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                SELECT id, type, title, due_at, metadata
                FROM scheduled
                WHERE user_id = ? AND notified = 0
                AND datetime(due_at) <= datetime('now', ? || ' hours')
                ORDER BY due_at ASC
                LIMIT 10
                """,
                (user_id, f"+{hours_ahead}"),
            )
            return [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "title": r["title"],
                    "due_at": r["due_at"],
                }
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def add_scheduled(
        self,
        user_id: int,
        type_: str,
        title: str,
        due_at: str,
        metadata: Optional[str] = None,
    ) -> int:
        """Add scheduled item. Returns id."""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO scheduled (user_id, type, title, due_at, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, type_, title, due_at, metadata or ""),
            )
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        finally:
            conn.close()
