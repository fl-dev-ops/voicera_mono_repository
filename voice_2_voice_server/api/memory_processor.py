"""Persistent memory retrieval processor.

Inspired by Pipecat's Mem0MemoryService pattern, but backed by Voicera backend
API (/api/v1/memory/search).

Goal:
- At the beginning and on each user turn, fetch relevant context for the student
  and inject it into the LLM context as a SYSTEM message.

Notes:
- We *replace* the previous injected memory block to prevent unbounded growth.
- We keep this best-effort: if backend is down, conversation continues.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from pipecat.frames.frames import Frame, LLMMessagesFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .backend_utils import memory_search


MEMORY_TAG = "PERSISTENT_MEMORY:\n"


def _format_memory_block(mem: Dict[str, Any], *, max_chars: int = 1400) -> str:
    profile = (mem.get("profile") or {}).get("summary", "")
    hits = mem.get("hits") or []

    lines: List[str] = []
    if profile and str(profile).strip():
        lines.append("PROFILE SUMMARY:\n" + str(profile).strip())

    if hits:
        # Keep top hits and strip empties
        hit_lines = []
        for h in hits:
            t = (h or {}).get("text")
            if t and str(t).strip():
                hit_lines.append("- " + str(t).strip())
        if hit_lines:
            lines.append("RELEVANT PAST SNIPPETS:\n" + "\n".join(hit_lines[:10]))

    if not lines:
        return ""

    block = (
        MEMORY_TAG
        + "Use this persistent memory to personalize. If it conflicts with the user now, prefer the user.\n\n"
        + "\n\n".join(lines)
    )

    if len(block) > max_chars:
        block = block[: max_chars - 1] + "…"

    return block


def _strip_previous_memory(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "system" and isinstance(m.get("content"), str):
            if m["content"].startswith(MEMORY_TAG):
                continue
        out.append(m)
    return out


class VoiceraMemoryRetrievalService(FrameProcessor):
    """Injects persistent memory into LLM messages on each user turn."""

    def __init__(self, *, user_phone: str, top_k: int = 6):
        super().__init__()
        self.user_phone = user_phone
        self.top_k = top_k
        self._last_query: Optional[str] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # We only need to intercept messages going downstream to the LLM.
        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return

        if not isinstance(frame, LLMMessagesFrame):
            await self.push_frame(frame, direction)
            return

        try:
            messages = frame.messages
            context = LLMContext(messages)

            latest_user: Optional[str] = None
            for m in reversed(context.get_messages()):
                if m.get("role") == "user" and isinstance(m.get("content"), str) and m["content"].strip():
                    latest_user = m["content"].strip()
                    break

            if not latest_user:
                await self.push_frame(frame, direction)
                return

            # Avoid repeating retrieval on identical user text.
            if self._last_query == latest_user:
                await self.push_frame(frame, direction)
                return
            self._last_query = latest_user

            mem = await memory_search(user_phone=self.user_phone, query=latest_user, top_k=self.top_k)
            if not mem:
                await self.push_frame(frame, direction)
                return

            block = _format_memory_block(mem)
            if not block:
                await self.push_frame(frame, direction)
                return

            new_messages = _strip_previous_memory(context.get_messages())

            # Insert memory block right after the first system prompt if present.
            insert_at = 1 if new_messages and new_messages[0].get("role") == "system" else 0
            new_messages.insert(insert_at, {"role": "system", "content": block})

            await self.push_frame(LLMMessagesFrame(new_messages), direction)

        except Exception as e:
            logger.warning(f"Memory retrieval processor failed (continuing): {e}")
            await self.push_frame(frame, direction)
