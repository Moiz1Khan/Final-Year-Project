"""
ChromaDB-backed semantic search for productivity objects (tasks, emails).

This is separate from MemoryStore's `synq_memories` collection so app data
doesn't mix with conversational memories.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ProductivityVectorStore:
    def __init__(self, *, api_key: Optional[str], collection_name: str):
        self.api_key = api_key
        self.collection_name = collection_name
        self._coll = None

    def _get_collection(self):
        if self._coll is not None:
            return self._coll
        if not self.api_key:
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
            self._coll = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            return self._coll
        except Exception:
            return None

    def upsert(
        self,
        *,
        doc_id: str,
        user_id: int,
        document: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        coll = self._get_collection()
        if coll is None:
            return
        md = {"user_id": str(user_id)}
        if metadata:
            md.update({k: str(v) for k, v in metadata.items() if v is not None})
        try:
            coll.upsert(ids=[doc_id], documents=[document], metadatas=[md])
        except Exception:
            # Don't break core functionality if vector DB fails.
            pass

    def query(self, *, user_id: int, query_text: str, top_k: int = 5) -> List[str]:
        coll = self._get_collection()
        if coll is None:
            return []
        try:
            res = coll.query(
                query_texts=[query_text],
                n_results=top_k,
                where={"user_id": str(user_id)},
            )
            docs = (res or {}).get("documents") or []
            if docs and docs[0]:
                return docs[0]
        except Exception:
            pass
        return []


def task_doc(title: str, notes: str = "", due_at: str = "", status: str = "", priority: str = "") -> str:
    return (
        f"Task: {title}\n"
        f"Notes: {notes}\n"
        f"Due: {due_at}\n"
        f"Status: {status}\n"
        f"Priority: {priority}\n"
    )


def email_doc(from_email: str, subject: str, snippet: str = "") -> str:
    return f"From: {from_email}\nSubject: {subject}\nSnippet: {snippet}\n"

