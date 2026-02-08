"""Persistent memory service (MongoDB + Qdrant).

Design goals:
- Source of truth: MongoDB (raw ingests + per-user summary/profile)
- Retrieval: Qdrant vector search filtered by user phone number
- API surface: ingest + search

This follows the same pattern as existing voice server → backend API flow.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastembed import TextEmbedding
from loguru import logger
from pymongo.database import Database
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import settings
from app.database import get_database


def _now_utc_iso() -> str:
    return datetime.utcnow().isoformat()


def _stable_point_id(user_phone: str, text: str, source: Optional[Dict[str, Any]]) -> str:
    """Create a deterministic id to avoid duplicate inserts."""
    h = hashlib.sha256()
    h.update(user_phone.encode("utf-8"))
    h.update(b"\n")
    h.update(text.encode("utf-8"))
    if source:
        h.update(b"\n")
        h.update(str(sorted(source.items())).encode("utf-8"))
    return h.hexdigest()


class MemoryService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
        self._embedder = TextEmbedding(model_name=settings.MEMORY_EMBED_MODEL)
        self._qdrant = QdrantClient(url=settings.QDRANT_URL)
        self._collection = settings.QDRANT_COLLECTION
        self._ensure_indexes()
        self._ensure_qdrant_collection()

    # ------------------------- MongoDB -------------------------
    def _ensure_indexes(self):
        try:
            self.db.user_memory_events.create_index([("user_phone", 1), ("created_at", -1)])
            self.db.user_memory_profile.create_index("user_phone", unique=True)
        except Exception as e:
            logger.warning(f"Failed to ensure MongoDB indexes: {e}")

    # ------------------------- Qdrant -------------------------
    def _ensure_qdrant_collection(self):
        try:
            existing = {c.name for c in self._qdrant.get_collections().collections}
            if self._collection in existing:
                return

            # Determine embedding dimension by running one sample embed.
            dim = len(next(self._embedder.embed(["hello"])) )
            self._qdrant.create_collection(
                collection_name=self._collection,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )
            # Payload index for filtering by user
            self._qdrant.create_payload_index(
                collection_name=self._collection,
                field_name="user_phone",
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )
            logger.info(f"Created Qdrant collection={self._collection} dim={dim}")
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collection: {e}")

    def _embed(self, texts: List[str]) -> List[List[float]]:
        return [list(v) for v in self._embedder.embed(texts)]

    # ------------------------- Public API -------------------------
    def ingest(
        self,
        *,
        user_phone: str,
        text: str,
        source: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Store a memory event and index it for vector search."""
        created_at = _now_utc_iso()
        event = {
            "user_phone": user_phone,
            "text": text,
            "source": source or {},
            "tags": tags or [],
            "created_at": created_at,
        }

        # Mongo insert (always)
        mongo_id = self.db.user_memory_events.insert_one(event).inserted_id

        # Vector upsert (best-effort)
        try:
            point_id = _stable_point_id(user_phone, text, source)
            vec = self._embed([text])[0]
            payload = {
                "user_phone": user_phone,
                "text": text,
                "created_at": created_at,
                "source": source or {},
                "tags": tags or [],
            }
            self._qdrant.upsert(
                collection_name=self._collection,
                points=[qm.PointStruct(id=point_id, vector=vec, payload=payload)],
                wait=False,
            )
        except Exception as e:
            logger.warning(f"Vector upsert failed (continuing): {e}")

        # Update lightweight profile summary (Option A)
        self._update_profile_summary(user_phone=user_phone, text=text)

        return {"status": "success", "mongo_id": str(mongo_id)}

    def search(
        self,
        *,
        user_phone: str,
        query: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Return profile + vector hits for this user."""
        profile = self.db.user_memory_profile.find_one({"user_phone": user_phone}) or {}
        profile_out = {
            "user_phone": user_phone,
            "summary": profile.get("summary", ""),
            "updated_at": profile.get("updated_at"),
        }

        hits: List[Dict[str, Any]] = []
        try:
            qvec = self._embed([query])[0]
            res = self._qdrant.search(
                collection_name=self._collection,
                query_vector=qvec,
                limit=top_k,
                query_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="user_phone",
                            match=qm.MatchValue(value=user_phone),
                        )
                    ]
                ),
            )
            for r in res:
                payload = r.payload or {}
                hits.append(
                    {
                        "score": r.score,
                        "text": payload.get("text", ""),
                        "created_at": payload.get("created_at"),
                        "tags": payload.get("tags", []),
                        "source": payload.get("source", {}),
                    }
                )
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        return {"profile": profile_out, "hits": hits}

    # ------------------------- Profile summary (MVP) -------------------------
    def _update_profile_summary(self, *, user_phone: str, text: str):
        """MVP: keep a rolling last-updated + append-only summary.

        Later we can replace this with an LLM summarizer in backend.
        """
        try:
            existing = self.db.user_memory_profile.find_one({"user_phone": user_phone})
            summary = (existing or {}).get("summary", "").strip()

            # Keep it bounded
            new_line = text.strip().replace("\n", " ")
            if len(new_line) > 240:
                new_line = new_line[:240] + "…"

            # Append
            updated = (summary + "\n" + new_line).strip() if summary else new_line
            if len(updated) > 2000:
                updated = updated[-2000:]

            self.db.user_memory_profile.update_one(
                {"user_phone": user_phone},
                {"$set": {"summary": updated, "updated_at": _now_utc_iso()}},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Profile summary update failed: {e}")


memory_service = MemoryService()
