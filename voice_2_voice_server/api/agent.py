"""LiveKit Voice Agent — replaces bot.py / Pipecat pipeline.

Architecture:
- VoiceraAgent (Agent subclass) handles STT/LLM/TTS pipeline selection,
  memory bootstrap, per-turn fact retrieval/extraction, greeting, and
  post-call recording/summarization.
- STT: Deepgram (nova-2)
- TTS: Sarvam  (bulbul:v2)
- LLM: OpenAI | Gemini
- All providers are commercial LiveKit plugins — no custom node overrides.
- Entrypoint: `entrypoint(ctx: JobContext)` is called by the LiveKit Workers SDK
  for every room dispatched to this agent process.
"""

from __future__ import annotations

import asyncio
import os
import time
import traceback
from datetime import datetime
from typing import Optional

from loguru import logger
from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
)
from livekit.agents.llm import ChatContext, ChatMessage
from livekit import rtc
from livekit.plugins import silero

from .services import (
    create_livekit_stt,
    create_livekit_tts,
    create_livekit_llm,
    ServiceCreationError,
)
from .backend_utils import (
    fetch_agent_config_from_backend,
    create_meeting_in_backend,
    memory_bootstrap,
    memory_summarize,
    fetch_meeting_internal,
)
from .call_recording_utils import submit_call_recording
from storage.minio_client import MinIOStorage

load_dotenv(override=False)

FACTS_TAG = "KNOWN_FACTS:\n"


# ============================================================================
# Per-turn memory helpers (ported from VoiceraMemoryProcessor)
# ============================================================================


def _format_facts_block(facts: list, *, max_chars: int = 1200) -> str:
    """Format a list of facts into a system message block."""
    if not facts:
        return ""
    fact_lines = [
        f"- {f.get('fact', '').strip()}" for f in facts if f.get("fact", "").strip()
    ]
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


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format."""
    p = str(phone).strip().replace(" ", "")
    if p.startswith("0"):
        p = "+91" + p[1:]
    elif not p.startswith("+") and len(p) == 10:
        p = "+91" + p
    elif not p.startswith("+") and p.startswith("91"):
        p = "+" + p
    return p


# ============================================================================
# VoiceraAgent — main agent class
# ============================================================================


class VoiceraAgent(Agent):
    """Voicera voice agent built on LiveKit Agents SDK.

    Instantiated once per call with all call-specific state pre-loaded.
    Uses Deepgram STT + Sarvam TTS + OpenAI/Gemini LLM via LiveKit plugins.
    """

    def __init__(
        self,
        *,
        agent_config: dict,
        call_sid: str,
        agent_type: str,
        user_phone: Optional[str] = None,
        call_data: dict,
        call_start_time: float,
        start_time_utc: str,
        storage: MinIOStorage,
        initial_instructions: str,
    ):
        super().__init__(instructions=initial_instructions)

        self._agent_config = agent_config
        self._call_sid = call_sid
        self._agent_type = agent_type
        self._user_phone = user_phone
        self._call_data = call_data
        self._call_start_time = call_start_time
        self._start_time_utc = start_time_utc
        self._storage = storage

        self._enable_memory: bool = agent_config.get("enable_memory", True)
        if isinstance(self._enable_memory, str):
            self._enable_memory = self._enable_memory.lower() in ("true", "1", "yes")
        self._enable_memory_each_turn: bool = os.getenv(
            "ENABLE_MEMORY_EACH_TURN", "true"
        ).lower() in ("true", "1", "yes")
        self._memory_top_k: int = int(os.getenv("MEMORY_TOP_K", "5"))

        self._last_user_text: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def on_enter(self) -> None:
        """Called when agent joins the room and session is active."""
        greeting = self._agent_config.get("greeting_message", "")
        if greeting.strip():
            logger.info(f"Sending greeting: {greeting[:60]}")
            await self.session.generate_reply(instructions=greeting)

    async def on_exit(self) -> None:
        """Called when the agent is about to leave the room."""
        logger.info(f"Agent exiting call {self._call_sid}")

    # ------------------------------------------------------------------
    # Per-turn memory hook
    # ------------------------------------------------------------------

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Called after each user turn, before LLM is invoked.

        Responsibilities:
        1. Capture transcript line
        2. Retrieve relevant facts from Qdrant and inject into context
        3. Fire background fact extraction (non-blocking)
        """
        user_text = new_message.content if isinstance(new_message.content, str) else ""
        if not user_text.strip():
            return

        # Transcript capture
        timestamp = datetime.utcnow().isoformat()
        self._call_data["transcript_lines"].append(f"[{timestamp}] user: {user_text}")
        logger.info(f"Transcript [user]: {user_text[:80]}")

        # Dedup
        if self._last_user_text == user_text:
            return
        self._last_user_text = user_text

        # Per-turn memory retrieval
        if self._user_phone and self._enable_memory and self._enable_memory_each_turn:
            await self._inject_facts_into_context(turn_ctx, user_text)
            asyncio.create_task(self._extract_facts_background(turn_ctx, user_text))

    async def _inject_facts_into_context(
        self, turn_ctx: ChatContext, user_text: str
    ) -> None:
        """Search Qdrant facts and inject as system message into turn context."""
        try:
            from .backend_utils import memory_search_facts

            facts = await memory_search_facts(
                user_phone=self._user_phone,
                query=user_text,
                top_k=self._memory_top_k,
            )
            if facts:
                logger.info(
                    f"Memory retrieval: {len(facts)} facts for '{user_text[:50]}'"
                )
                block = _format_facts_block(facts)
                if block:
                    turn_ctx.messages[:] = [
                        m
                        for m in turn_ctx.messages
                        if not (
                            m.role == "system"
                            and isinstance(m.content, str)
                            and m.content.startswith(FACTS_TAG)
                        )
                    ]
                    insert_at = (
                        1
                        if turn_ctx.messages and turn_ctx.messages[0].role == "system"
                        else 0
                    )
                    turn_ctx.messages.insert(
                        insert_at,
                        ChatMessage(role="system", content=block),
                    )
            else:
                logger.debug(f"Memory retrieval: no facts for '{user_text[:50]}'")
                turn_ctx.messages[:] = [
                    m
                    for m in turn_ctx.messages
                    if not (
                        m.role == "system"
                        and isinstance(m.content, str)
                        and m.content.startswith(FACTS_TAG)
                    )
                ]
        except Exception as e:
            logger.warning(f"Memory injection failed (continuing): {e}")

    async def _extract_facts_background(
        self, turn_ctx: ChatContext, user_text: str
    ) -> None:
        """Fire-and-forget background fact extraction."""
        try:
            from .backend_utils import memory_extract_and_store

            agent_msg = ""
            for m in reversed(turn_ctx.messages):
                if (
                    m.role == "assistant"
                    and isinstance(m.content, str)
                    and m.content.strip()
                ):
                    agent_msg = m.content.strip()
                    break

            source = {}
            if self._call_sid:
                source["call_sid"] = self._call_sid
            if self._agent_type:
                source["agent_type"] = self._agent_type

            result = await memory_extract_and_store(
                user_phone=self._user_phone,
                agent_message=agent_msg,
                user_response=user_text,
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

    # ------------------------------------------------------------------
    # Assistant turn transcript capture
    # ------------------------------------------------------------------

    async def on_agent_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Called after each assistant turn — capture transcript line."""
        text = new_message.content if isinstance(new_message.content, str) else ""
        if text.strip():
            timestamp = datetime.utcnow().isoformat()
            self._call_data["transcript_lines"].append(
                f"[{timestamp}] assistant: {text}"
            )
            logger.info(f"Transcript [assistant]: {text[:80]}")


# ============================================================================
# Call teardown helpers
# ============================================================================


async def _save_call_data(
    call_sid: str,
    call_data: dict,
    storage: MinIOStorage,
) -> None:
    """Persist in-memory audio chunks and transcript to MinIO."""
    if (
        call_data.get("audio_chunks")
        and call_data.get("audio_sample_rate")
        and call_data.get("audio_num_channels")
    ):
        try:
            await storage.save_recording_from_chunks(
                call_sid,
                call_data["audio_chunks"],
                call_data["audio_sample_rate"],
                call_data["audio_num_channels"],
            )
            total = sum(len(c) for c in call_data["audio_chunks"])
            logger.info(
                f"Saved {len(call_data['audio_chunks'])} audio chunks ({total} bytes)"
            )
        except Exception as e:
            logger.error(f"Failed to save audio recording: {e}")
    else:
        logger.warning(f"No audio data to save for {call_sid}")

    if call_data.get("transcript_lines"):
        try:
            await storage.save_transcript_from_lines(
                call_sid, call_data["transcript_lines"]
            )
            logger.info(f"Saved {len(call_data['transcript_lines'])} transcript lines")
        except Exception as e:
            logger.error(f"Failed to save transcript: {e}")
    else:
        logger.warning(f"No transcript data to save for {call_sid}")


async def _post_call_summarize(
    call_sid: str,
    call_data: dict,
    agent_config: dict,
    user_phone: Optional[str],
    enable_memory: bool,
) -> None:
    """Generate and store post-call summary in Qdrant."""
    if user_phone and enable_memory and call_data.get("transcript_lines"):
        try:
            transcript_text = "\n".join(call_data["transcript_lines"])
            summary_prompt = agent_config.get("summary_prompt")
            result = await memory_summarize(
                user_phone=user_phone,
                transcript=transcript_text,
                call_id=call_sid,
                summary_prompt=summary_prompt,
            )
            if result:
                logger.info(
                    f"Post-call summary: stored={result.get('stored', False)} "
                    f"for {user_phone} call={call_sid}"
                )
        except Exception as e:
            logger.warning(f"Memory summarize failed (continuing): {e}")


# ============================================================================
# JobProcess — warm-up (runs once per worker process)
# ============================================================================


def prewarm(proc: JobProcess) -> None:
    """Pre-load Silero VAD model weights to avoid cold-start latency."""
    logger.info("Prewarming Silero VAD model...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Silero VAD model loaded.")


# ============================================================================
# Entrypoint — called per room/call by LiveKit Workers
# ============================================================================


async def _resolve_sip_details(ctx: JobContext, call_sid: str) -> dict:
    """Inspect SIP participant attributes AFTER session is started.

    Returns dict with keys: inbound, from_number, to_number.
    Must be called after the session has started and participants have joined.
    """
    inbound_call: bool = False
    from_number: Optional[str] = None
    to_number: Optional[str] = None

    # Give a moment for participants to populate after session start
    for _attempt in range(6):
        for participant in ctx.room.remote_participants.values():
            attrs = participant.attributes or {}
            direction = attrs.get("sip.callDirection", "")
            inbound_call = direction == "inbound"
            from_number = attrs.get("sip.phoneNumber") or None
            to_number = attrs.get("sip.trunkPhoneNumber") or None
            logger.info(
                f"SIP participant: direction={direction}, "
                f"from={from_number}, to={to_number}"
            )
            return {
                "inbound": inbound_call,
                "from_number": from_number,
                "to_number": to_number,
            }
        await asyncio.sleep(0.5)

    logger.warning("No SIP participant found after 3s — using defaults")
    return {"inbound": False, "from_number": None, "to_number": None}


async def _post_start_setup(
    ctx: JobContext,
    agent: "VoiceraAgent",
    session: "AgentSession",
    agent_config: dict,
    agent_type: str,
    call_sid: str,
    start_time_utc: str,
) -> None:
    """Background setup that runs AFTER session.start() has answered the call.

    Resolves SIP participant details, creates meeting record, bootstraps memory,
    and updates the agent's user_phone for per-turn memory hooks.
    This runs concurrently so the caller hears the greeting immediately.
    """
    try:
        # 1. Resolve SIP participant details
        sip = await _resolve_sip_details(ctx, call_sid)
        inbound_call = sip["inbound"]
        from_number = sip["from_number"]
        to_number = sip["to_number"]

        # 2. Create meeting record
        meeting_payload = {
            "meeting_id": call_sid,
            "agent_type": agent_type,
            "org_id": agent_config.get("org_id"),
            "start_time_utc": start_time_utc,
            "end_time_utc": "",
            "inbound": inbound_call,
            "from_number": from_number,
            "to_number": to_number,
            "call_busy": False,
            "created_at": start_time_utc,
        }
        meeting_created = await create_meeting_in_backend(meeting_payload)
        if meeting_created:
            logger.info(f"Meeting record created: {call_sid}")
        else:
            logger.warning(
                f"Failed to create meeting record for {call_sid} — "
                "memory and recording may be incomplete"
            )

        # 3. Resolve user phone
        user_phone: Optional[str] = None
        meeting = None
        for attempt in range(4):
            meeting = await fetch_meeting_internal(call_sid)
            if meeting:
                break
            if attempt < 3:
                logger.debug(
                    f"Meeting not found yet (attempt {attempt + 1}/4), retrying in 0.5s..."
                )
                await asyncio.sleep(0.5)

        if not meeting:
            logger.warning(
                "Could not fetch meeting after 4 attempts — user_phone will be None"
            )

        if meeting:
            is_inbound = meeting.get("inbound")
            if is_inbound is True:
                raw_phone = meeting.get("from_number")
            elif is_inbound is False:
                raw_phone = meeting.get("to_number")
            else:
                raw_phone = None
            if raw_phone:
                user_phone = _normalize_phone(raw_phone)

        logger.info(
            f"Resolved user_phone={user_phone} "
            f"(inbound={meeting.get('inbound') if meeting else 'N/A'})"
        )

        # 4. Update agent's user_phone so per-turn memory hooks work
        agent._user_phone = user_phone

        # 5. Memory bootstrap (inject into agent instructions if available)
        enable_memory: bool = agent_config.get("enable_memory", True)
        if isinstance(enable_memory, str):
            enable_memory = enable_memory.lower() in ("true", "1", "yes")

        if user_phone and enable_memory:
            try:
                mem = await memory_bootstrap(user_phone=user_phone)
                if mem:
                    facts = mem.get("facts") or []
                    summaries = mem.get("summaries") or []
                    lines = []
                    if facts:
                        fact_lines = [
                            f"- {f.get('fact', '').strip()}"
                            for f in facts
                            if f.get("fact", "").strip()
                        ]
                        if fact_lines:
                            lines.append(
                                "KNOWN FACTS ABOUT THIS USER:\n" + "\n".join(fact_lines)
                            )
                    if summaries:
                        summary_lines = []
                        for s in summaries:
                            text = (s.get("summary") or "").strip()
                            if text:
                                call_id = s.get("call_id", "unknown")
                                summary_lines.append(f"[call {call_id}] {text}")
                        if summary_lines:
                            lines.append(
                                "RECENT CALL SUMMARIES:\n" + "\n".join(summary_lines)
                            )
                    if lines:
                        memory_block = (
                            "You have persistent memory about this user. "
                            "Use it to personalize. If something conflicts "
                            "with what the user says now, prefer what they say now.\n\n"
                            + "\n\n".join(lines)
                        )
                        logger.info(
                            f"Memory bootstrap: {len(facts)} facts, "
                            f"{len(summaries)} summaries for {user_phone}"
                        )
                        # Update agent instructions with memory block
                        current = agent.instructions or ""
                        agent._instructions = (
                            current + "\n\n" + memory_block if current else memory_block
                        )
            except Exception as e:
                logger.warning(f"Memory bootstrap failed (continuing): {e}")

    except Exception as e:
        logger.error(f"Post-start setup error: {e}")
        logger.debug(traceback.format_exc())


async def entrypoint(ctx: JobContext) -> None:
    """Main entrypoint for each inbound or outbound SIP call.

    The LiveKit Worker dispatches a Job for every room.
    Room name = call_sid / LiveKit room name.
    Agent metadata (agent_id) is passed via room metadata (JSON) or
    participant attributes set by the dispatch rule.

    IMPORTANT: We do NOT call ctx.connect() manually — session.start()
    handles the room connection.  This matches the official Vobiz+LiveKit
    inbound example (https://github.com/vobiz-ai/Livekit-vobiz-inbound).
    """
    call_start_time = time.monotonic()
    start_time_utc = datetime.utcnow().isoformat()

    room: rtc.Room = ctx.room
    room_name: str = room.name
    call_sid = room_name

    logger.info(f"New call: room={room_name}")

    # -------------------------------------------------------------------------
    # Resolve agent_id from room metadata or job attributes
    # -------------------------------------------------------------------------
    agent_id: Optional[str] = None
    try:
        import json as _json

        # Try room metadata first
        meta = room.metadata or ""
        if meta.strip().startswith("{"):
            meta_dict = _json.loads(meta)
            agent_id = meta_dict.get("agent_id")
    except Exception:
        pass

    # Try job attributes (set by dispatch rule's `attributes` field)
    if not agent_id:
        try:
            job_attrs = ctx.job.attributes or {}
            agent_id = job_attrs.get("agent_id")
        except Exception:
            pass

    if not agent_id:
        agent_id = os.getenv("DEFAULT_AGENT_ID")

    if not agent_id:
        logger.error(
            "No agent_id found in room metadata, job attributes, or DEFAULT_AGENT_ID env var. Aborting."
        )
        return

    logger.info(f"Resolved agent_id={agent_id} for room={room_name}")

    # -------------------------------------------------------------------------
    # Fetch agent config from backend
    # -------------------------------------------------------------------------
    agent_config = await fetch_agent_config_from_backend(agent_id)
    if not agent_config:
        logger.error(f"Failed to fetch agent config for agent_id={agent_id}. Aborting.")
        return

    agent_type: str = agent_config.get("agent_type", agent_id)
    logger.info(f"Agent config loaded: agent_type={agent_type}")

    # -------------------------------------------------------------------------
    # Build STT / TTS / LLM plugins
    # -------------------------------------------------------------------------
    llm_config = agent_config.get("llm_model", {})
    stt_config = agent_config.get("stt_model", {})
    tts_config = agent_config.get("tts_model", {})

    language = agent_config.get("language")
    if language:
        if not stt_config.get("language"):
            stt_config["language"] = language
        if not tts_config.get("language"):
            tts_config["language"] = language

    stt_plugin = create_livekit_stt(stt_config)
    tts_plugin = create_livekit_tts(tts_config)
    llm_plugin = create_livekit_llm(llm_config)

    # -------------------------------------------------------------------------
    # Shared call state
    # -------------------------------------------------------------------------
    call_data = {
        "audio_chunks": [],
        "audio_sample_rate": None,
        "audio_num_channels": None,
        "transcript_lines": [],
    }
    storage = MinIOStorage.from_env()

    # -------------------------------------------------------------------------
    # Memory — will be resolved post-start; use system prompt for now
    # -------------------------------------------------------------------------
    enable_memory: bool = agent_config.get("enable_memory", True)
    if isinstance(enable_memory, str):
        enable_memory = enable_memory.lower() in ("true", "1", "yes")
    logger.info(f"Persistent memory: {'ENABLED' if enable_memory else 'DISABLED'}")

    system_prompt: str = agent_config.get("system_prompt", "") or ""

    # -------------------------------------------------------------------------
    # VAD
    # -------------------------------------------------------------------------
    vad = ctx.proc.userdata.get("vad") or silero.VAD.load()

    # -------------------------------------------------------------------------
    # Instantiate agent (user_phone resolved later in background)
    # -------------------------------------------------------------------------
    agent = VoiceraAgent(
        agent_config=agent_config,
        call_sid=call_sid,
        agent_type=agent_type,
        user_phone=None,  # resolved in _post_start_setup
        call_data=call_data,
        call_start_time=call_start_time,
        start_time_utc=start_time_utc,
        storage=storage,
        initial_instructions=system_prompt,
    )

    # -------------------------------------------------------------------------
    # Build AgentSession
    # -------------------------------------------------------------------------
    from livekit.plugins import turn_detector as td

    session_kwargs: dict = dict(
        vad=vad,
        stt=stt_plugin,
        tts=tts_plugin,
        llm=llm_plugin,
    )

    enable_smart_turn = os.getenv("ENABLE_SMART_TURN", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    if enable_smart_turn:
        try:
            session_kwargs["turn_detection"] = td.MultilingualModel()
            logger.info("Turn detection: MultilingualModel ENABLED")
        except Exception as e:
            logger.warning(
                f"Could not load MultilingualModel: {e} — using default turn detection"
            )

    session = AgentSession(**session_kwargs)

    # -------------------------------------------------------------------------
    # Start session — this connects to the room and answers the SIP call.
    # DO NOT call ctx.connect() before this — session.start() handles it.
    # Matches official Vobiz+LiveKit inbound example.
    # -------------------------------------------------------------------------
    try:
        await session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                # Don't close when caller briefly disconnects (matches official example)
                close_on_disconnect=False,
            ),
        )

        # Kick off background setup (SIP details, meeting, memory) without
        # blocking the call — the caller hears the greeting immediately.
        asyncio.create_task(
            _post_start_setup(
                ctx=ctx,
                agent=agent,
                session=session,
                agent_config=agent_config,
                agent_type=agent_type,
                call_sid=call_sid,
                start_time_utc=start_time_utc,
            )
        )

        await ctx.wait_for_shutdown()

    except Exception as e:
        logger.error(f"Session error: {type(e).__name__}: {e}")
        logger.debug(traceback.format_exc())
    finally:
        duration = time.monotonic() - call_start_time
        logger.info(f"Call ended after {duration:.1f}s — saving data for {call_sid}")

        await _save_call_data(call_sid, call_data, storage)

        await _post_call_summarize(
            call_sid=call_sid,
            call_data=call_data,
            agent_config=agent_config,
            user_phone=agent._user_phone,  # may have been set by _post_start_setup
            enable_memory=enable_memory,
        )

        await submit_call_recording(
            call_sid=call_sid,
            agent_type=agent_type,
            agent_config=agent_config,
            storage=storage,
            call_start_time=call_start_time,
        )
