"""Fact-based persistent memory processor for Pipecat pipeline.

Two responsibilities:
1. Per-turn RETRIEVAL: search relevant facts using user's raw text, inject into LLM context
2. Per-turn EXTRACTION: after each user turn, fire async fact extraction (non-blocking)

The processor sits between context_aggregator.user() and the LLM in the pipeline.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from pipecat.frames.frames import Frame, LLMMessagesFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .backend_utils import memory_extract_and_store, memory_search_facts


FACTS_TAG = "KNOWN_FACTS:\n"


def _format_facts_block(facts: List[Dict[str, Any]], *, max_chars: int = 1200) -> str:
    """Format a list of facts into a system message block."""
    if not facts:
        return ""

    fact_lines = []
    for f in facts:
        fact_text = (f.get("fact") or "").strip()
        if fact_text:
            fact_lines.append(f"- {fact_text}")

    if not fact_lines:
        return ""

    block = (
        FACTS_TAG
        + "Use these known facts about the user to personalize. "
        + "If something conflicts with what the user says now, prefer what they say now.\n\n"
        + "\n".join(fact_lines)
    )

    if len(block) > max_chars:
        block = block[: max_chars - 1] + "…"

    return block


def _strip_previous_facts(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove any previously injected facts block from messages."""
    return [
        m
        for m in messages
        if not (
            m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and m["content"].startswith(FACTS_TAG)
        )
    ]


class VoiceraMemoryProcessor(FrameProcessor):
    """Per-turn fact retrieval + async fact extraction.

    Retrieval (blocking, before LLM):
        - Intercepts LLMMessagesFrame going downstream
        - Searches Qdrant for facts relevant to user's latest message
        - Injects matching facts as a system message

    Extraction (non-blocking, fire-and-forget):
        - After retrieval, fires an async task to extract new facts from the exchange
        - Does NOT block the pipeline
    """

    def __init__(
        self,
        *,
        user_phone: str,
        call_sid: Optional[str] = None,
        agent_type: Optional[str] = None,
        top_k: int = 5,
    ):
        super().__init__()
        self.user_phone = user_phone
        self.call_sid = call_sid
        self.agent_type = agent_type
        self.top_k = top_k
        self._last_query: Optional[str] = None
        self._last_agent_message: Optional[str] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction != FrameDirection.DOWNSTREAM or not isinstance(
            frame, LLMMessagesFrame
        ):
            await self.push_frame(frame, direction)
            return

        try:
            messages = frame.messages

            # Find the latest user message and the last agent message before it.
            # Pipecat messages may use OpenAI format {"role", "content"} or
            # Google format {"role", "parts": [{"text": "..."}]}.
            latest_user: Optional[str] = None
            latest_agent: Optional[str] = None

            for m in reversed(messages):
                role = m.get("role")
                # Extract text from either format
                content = m.get("content")
                if not isinstance(content, str) or not content.strip():
                    # Try Google/Gemini parts format
                    parts = m.get("parts")
                    if isinstance(parts, list) and parts:
                        content = (
                            parts[0].get("text") if isinstance(parts[0], dict) else None
                        )
                if not isinstance(content, str) or not content.strip():
                    continue
                if role == "user" and latest_user is None:
                    latest_user = content.strip()
                elif (
                    role in ("assistant", "model")
                    and latest_user is not None
                    and latest_agent is None
                ):
                    latest_agent = content.strip()
                    break

            if not latest_user:
                await self.push_frame(frame, direction)
                return

            # Skip if same query as last time (dedup)
            if self._last_query == latest_user:
                await self.push_frame(frame, direction)
                return
            self._last_query = latest_user

            # --- RETRIEVAL: search for relevant facts ---
            facts = await memory_search_facts(
                user_phone=self.user_phone,
                query=latest_user,
                top_k=self.top_k,
            )

            if facts:
                logger.info(
                    f"Memory retrieval: {len(facts)} facts found for '{latest_user[:50]}'"
                )
                block = _format_facts_block(facts)
                if block:
                    new_messages = _strip_previous_facts(list(messages))
                    # Insert after first system prompt
                    insert_at = (
                        1
                        if new_messages and new_messages[0].get("role") == "system"
                        else 0
                    )
                    new_messages.insert(insert_at, {"role": "system", "content": block})
                    await self.push_frame(LLMMessagesFrame(new_messages), direction)
                else:
                    await self.push_frame(frame, direction)
            else:
                logger.debug(f"Memory retrieval: no facts for '{latest_user[:50]}'")
                # Strip any stale facts block
                new_messages = _strip_previous_facts(list(messages))
                if len(new_messages) != len(messages):
                    await self.push_frame(LLMMessagesFrame(new_messages), direction)
                else:
                    await self.push_frame(frame, direction)

            # --- EXTRACTION: fire-and-forget async fact extraction ---
            # Use the agent's last message + user's response for context
            agent_msg = latest_agent or self._last_agent_message or ""
            if agent_msg:
                self._last_agent_message = agent_msg

            asyncio.create_task(self._extract_facts_background(agent_msg, latest_user))

        except Exception as e:
            logger.warning(f"Memory processor failed (continuing): {e}")
            await self.push_frame(frame, direction)

    async def _extract_facts_background(self, agent_message: str, user_response: str):
        """Fire-and-forget fact extraction. Errors are logged, never raised."""
        try:
            source = {}
            if self.call_sid:
                source["call_sid"] = self.call_sid
            if self.agent_type:
                source["agent_type"] = self.agent_type

            result = await memory_extract_and_store(
                user_phone=self.user_phone,
                agent_message=agent_message,
                user_response=user_response,
                source=source,
            )
            if result:
                extracted = result.get("facts_extracted", 0)
                stored = result.get("facts_stored", 0)
                skipped = result.get("facts_skipped", 0)
                if extracted > 0:
                    logger.info(
                        f"Memory facts: extracted={extracted}, stored={stored}, skipped={skipped}"
                    )
        except Exception as e:
            logger.warning(f"Background fact extraction failed: {e}")
