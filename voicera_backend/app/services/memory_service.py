"""Fact-based persistent memory service (Qdrant + Gemini).

Design:
- Two Qdrant collections: voicera_facts (per-fact, deduped) and voicera_summaries (per-call)
- Fact extraction: Gemini LLM extracts atomic facts from each user turn
- Fact dedup: before storing, check if a semantically matching fact already exists
- Summary generation: Gemini LLM summarizes full call transcript post-call
- Retrieval: vector search for per-turn, filtered scroll for bootstrap
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastembed import TextEmbedding
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phone normalization (India-first)
# ---------------------------------------------------------------------------


def normalize_phone_e164(phone: str, *, default_cc: str = "91") -> str:
    """Normalize phone numbers to E.164-like format.

    Examples:
      "08071387434" -> "+918071387434"
      "8071387434"  -> "+918071387434"
      "+918071..."  -> "+918071..."
      "918071..."   -> "+918071..."
    """
    if not phone:
        return ""

    p = str(phone).strip().replace(" ", "")
    if not p:
        return ""

    if p.startswith("+"):
        digits = "+" + "".join(ch for ch in p[1:] if ch.isdigit())
    else:
        digits = "".join(ch for ch in p if ch.isdigit())

    if digits.startswith("+"):
        return digits

    if digits.startswith("0") and len(digits) >= 11:
        return f"+{default_cc}{digits[1:]}"

    if digits.startswith(default_cc) and len(digits) > len(default_cc) + 6:
        return f"+{digits}"

    if len(digits) == 10:
        return f"+{default_cc}{digits}"

    return f"+{digits}"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(user_phone: str, text: str) -> str:
    """Deterministic point ID (UUID) from phone + text to avoid duplicates.

    Qdrant only accepts UUIDs or unsigned integers as point IDs.
    We derive a UUID v5 (SHA-1 based, deterministic) using a fixed namespace.
    """
    namespace = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    return str(uuid.uuid5(namespace, f"{user_phone}\n{text}"))


# ---------------------------------------------------------------------------
# Gemini LLM helpers
# ---------------------------------------------------------------------------


def _get_gemini_client() -> genai.Client:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")
    return genai.Client(api_key=api_key)


FACT_EXTRACTION_PROMPT = """You are a fact extractor. Given an exchange between an agent and a user, extract all factual information about the user.

Rules:
- Extract ONLY facts about the user (name, location, job interest, skills, education, experience, preferences, etc.)
- Each fact must be a short, self-contained statement (e.g. "Name is Surya", "Lives in Chennai", "Interested in data entry")
- Do NOT extract opinions, greetings, or conversational filler
- Do NOT extract facts about the agent
- If there are no facts to extract, return an empty array
- Return ONLY a valid JSON array of strings, nothing else

Agent said: "{agent_message}"
User responded: "{user_response}"

Extract facts as JSON array:"""


SUMMARY_PROMPT_DEFAULT = """Summarize this phone conversation in 2-3 concise sentences. Focus on:
- Who the caller is (name, location if mentioned)
- What they were calling about / what was discussed
- Key outcome or next steps

Keep it brief and factual. This summary will be used to give context in future calls with the same person.

Conversation transcript:
{transcript}

Summary:"""


def _extract_facts_via_llm(agent_message: str, user_response: str) -> List[str]:
    """Call Gemini to extract facts from a single exchange. Returns list of fact strings."""
    try:
        client = _get_gemini_client()
        prompt = FACT_EXTRACTION_PROMPT.format(
            agent_message=agent_message,
            user_response=user_response,
        )

        result = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            ),
        )

        text = (result.text or "").strip()
        if not text:
            return []

        facts = json.loads(text)
        if isinstance(facts, list):
            return [str(f).strip() for f in facts if f and str(f).strip()]
        return []

    except Exception as e:
        logger.warning(f"Fact extraction LLM call failed: {e}")
        return []


def _generate_summary_via_llm(
    transcript: str, summary_prompt: Optional[str] = None
) -> str:
    """Call Gemini to generate a call summary from transcript."""
    try:
        client = _get_gemini_client()
        prompt_template = summary_prompt or SUMMARY_PROMPT_DEFAULT
        prompt = prompt_template.format(transcript=transcript)

        result = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.3,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        return (result.text or "").strip()

    except Exception as e:
        logger.warning(f"Summary generation LLM call failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Memory Service
# ---------------------------------------------------------------------------


class MemoryService:
    """Fact-based persistent memory backed by Qdrant + Gemini."""

    # Fixed collection names — internal implementation detail, not configurable
    FACTS_COLLECTION = "voicera_facts"
    SUMMARIES_COLLECTION = "voicera_summaries"

    # Similarity threshold for dedup — facts above this score are considered duplicates
    DEDUP_THRESHOLD = 0.92

    def __init__(self):
        self._embedder = TextEmbedding(model_name=settings.MEMORY_EMBED_MODEL)
        self._qdrant = QdrantClient(url=settings.QDRANT_URL)
        self._facts_collection = self.FACTS_COLLECTION
        self._summaries_collection = self.SUMMARIES_COLLECTION
        self._ensure_collections()

    # -------------------- Setup --------------------

    def _ensure_collections(self):
        """Create Qdrant collections if they don't exist."""
        try:
            existing = {c.name for c in self._qdrant.get_collections().collections}
            dim = len(next(self._embedder.embed(["hello"])))

            for coll in [self._facts_collection, self._summaries_collection]:
                if coll not in existing:
                    self._qdrant.create_collection(
                        collection_name=coll,
                        vectors_config=qm.VectorParams(
                            size=dim, distance=qm.Distance.COSINE
                        ),
                    )
                    self._qdrant.create_payload_index(
                        collection_name=coll,
                        field_name="user_phone",
                        field_schema=qm.PayloadSchemaType.KEYWORD,
                    )
                    logger.info(f"Created Qdrant collection={coll} dim={dim}")

        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collections: {e}")

    def _embed(self, texts: List[str]) -> List[List[float]]:
        return [list(v) for v in self._embedder.embed(texts)]

    # -------------------- Facts: Extract & Store --------------------

    def extract_and_store_facts(
        self,
        *,
        user_phone: str,
        agent_message: str,
        user_response: str,
        source: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Extract facts from an exchange via LLM and store new ones in Qdrant.

        Returns: {facts_extracted: int, facts_stored: int, facts_skipped: int}
        """
        user_phone = normalize_phone_e164(
            user_phone, default_cc=settings.DEFAULT_COUNTRY_CODE
        )

        # Step 1: Extract facts via Gemini
        facts = _extract_facts_via_llm(agent_message, user_response)
        if not facts:
            return {"facts_extracted": 0, "facts_stored": 0, "facts_skipped": 0}

        # Step 2: Embed all facts
        vectors = self._embed(facts)

        # Step 3: Dedup — for each fact, check if a similar one already exists
        stored = 0
        skipped = 0
        created_at = _now_utc_iso()

        for fact, vec in zip(facts, vectors):
            if self._fact_exists(user_phone, vec):
                skipped += 1
                logger.debug(f"Fact dedup: skipping '{fact[:60]}...'")
                continue

            point_id = _stable_id(user_phone, fact)
            payload = {
                "user_phone": user_phone,
                "fact": fact,
                "created_at": created_at,
                "source": source or {},
            }

            try:
                self._qdrant.upsert(
                    collection_name=self._facts_collection,
                    points=[qm.PointStruct(id=point_id, vector=vec, payload=payload)],
                    wait=False,
                )
                stored += 1
                logger.info(f"Stored fact: '{fact[:80]}'")
            except Exception as e:
                logger.warning(f"Failed to store fact: {e}")

        return {
            "facts_extracted": len(facts),
            "facts_stored": stored,
            "facts_skipped": skipped,
        }

    def _fact_exists(self, user_phone: str, vector: List[float]) -> bool:
        """Check if a semantically similar fact already exists for this user."""
        try:
            results = self._qdrant.search(
                collection_name=self._facts_collection,
                query_vector=vector,
                limit=1,
                score_threshold=self.DEDUP_THRESHOLD,
                query_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="user_phone",
                            match=qm.MatchValue(value=user_phone),
                        )
                    ]
                ),
            )
            return len(results) > 0
        except Exception as e:
            logger.warning(f"Fact dedup check failed: {e}")
            return False

    # -------------------- Facts: Search --------------------

    def search_facts(
        self,
        *,
        user_phone: str,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Vector search for relevant facts. Returns list of {fact, score, created_at}."""
        user_phone = normalize_phone_e164(
            user_phone, default_cc=settings.DEFAULT_COUNTRY_CODE
        )

        try:
            qvec = self._embed([query])[0]
            results = self._qdrant.search(
                collection_name=self._facts_collection,
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

            return [
                {
                    "fact": (r.payload or {}).get("fact", ""),
                    "score": r.score,
                    "created_at": (r.payload or {}).get("created_at"),
                }
                for r in results
            ]

        except Exception as e:
            logger.warning(f"Fact search failed: {e}")
            return []

    # -------------------- Bootstrap: Get all facts + recent summaries --------------------

    def bootstrap(
        self,
        *,
        user_phone: str,
        max_facts: int = 20,
        max_summaries: int = 3,
    ) -> Dict[str, Any]:
        """Retrieve all known facts and recent call summaries for a user.

        Uses filtered scroll (no embedding needed) — fast.
        Returns: {facts: [...], summaries: [...]}
        """
        user_phone = normalize_phone_e164(
            user_phone, default_cc=settings.DEFAULT_COUNTRY_CODE
        )
        phone_filter = qm.Filter(
            must=[
                qm.FieldCondition(
                    key="user_phone",
                    match=qm.MatchValue(value=user_phone),
                )
            ]
        )

        facts = []
        try:
            results, _ = self._qdrant.scroll(
                collection_name=self._facts_collection,
                scroll_filter=phone_filter,
                limit=max_facts,
                with_payload=True,
                with_vectors=False,
            )
            for r in results:
                payload = r.payload or {}
                facts.append(
                    {
                        "fact": payload.get("fact", ""),
                        "created_at": payload.get("created_at"),
                    }
                )
        except Exception as e:
            logger.warning(f"Bootstrap facts scroll failed: {e}")

        summaries = []
        try:
            results, _ = self._qdrant.scroll(
                collection_name=self._summaries_collection,
                scroll_filter=phone_filter,
                limit=max_summaries,
                with_payload=True,
                with_vectors=False,
            )
            for r in results:
                payload = r.payload or {}
                summaries.append(
                    {
                        "summary": payload.get("summary", ""),
                        "call_id": payload.get("call_id"),
                        "created_at": payload.get("created_at"),
                    }
                )
        except Exception as e:
            logger.warning(f"Bootstrap summaries scroll failed: {e}")

        return {"facts": facts, "summaries": summaries}

    # -------------------- Summaries: Generate & Store --------------------

    def generate_and_store_summary(
        self,
        *,
        user_phone: str,
        transcript: str,
        call_id: Optional[str] = None,
        summary_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a call summary via LLM and store in Qdrant.

        Returns: {summary: str, stored: bool}
        """
        user_phone = normalize_phone_e164(
            user_phone, default_cc=settings.DEFAULT_COUNTRY_CODE
        )

        summary = _generate_summary_via_llm(transcript, summary_prompt)
        if not summary:
            return {"summary": "", "stored": False}

        # Store in summaries collection (no dedup — one per call)
        created_at = _now_utc_iso()
        point_id = _stable_id(user_phone, f"summary:{call_id or created_at}")
        vec = self._embed([summary])[0]

        payload = {
            "user_phone": user_phone,
            "summary": summary,
            "call_id": call_id,
            "created_at": created_at,
        }

        try:
            self._qdrant.upsert(
                collection_name=self._summaries_collection,
                points=[qm.PointStruct(id=point_id, vector=vec, payload=payload)],
                wait=False,
            )
            logger.info(f"Stored call summary for {user_phone}: '{summary[:80]}...'")
            return {"summary": summary, "stored": True}
        except Exception as e:
            logger.warning(f"Failed to store summary: {e}")
            return {"summary": summary, "stored": False}


# Singleton
memory_service = MemoryService()
