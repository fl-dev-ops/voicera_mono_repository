"""LiveKit Voice Agent — replaces bot.py / Pipecat pipeline.

Architecture:
- VoiceraAgent (Agent subclass) handles STT/LLM/TTS pipeline selection,
  memory bootstrap, per-turn fact retrieval/extraction, greeting, and
  post-call recording/summarization.
- STT: Deepgram (nova-3)
- TTS: Sarvam  (bulbul:v3)
- LLM: OpenAI (gpt-4o)
- All providers are commercial LiveKit plugins — no custom node overrides.
- Entrypoint: `entrypoint(ctx: JobContext)` is called by the LiveKit Workers SDK
  for every room dispatched to this agent process.

Telephony integration follows the official LiveKit docs:
  https://docs.livekit.io/telephony/agents-integration/
  https://github.com/livekit-examples/outbound-caller-python

Inbound: dispatch rule creates room → dispatches agent → agent answers
Outbound: API creates agent dispatch with metadata → agent connects →
          agent dials via CreateSIPParticipant → call connects
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import time
import traceback
from datetime import datetime
from typing import Optional

from loguru import logger
from dotenv import load_dotenv

from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    get_job_context,
)
from livekit.agents.llm import ChatContext, ChatMessage
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
from .egress_service import (
    start_room_audio_egress,
    stop_egress,
    wait_for_egress_completion,
    upload_transcript_json,
)
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
        is_outbound: bool = False,
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
        self._is_outbound = is_outbound
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

        # SIP participant reference (set after dial for outbound)
        self.sip_participant: Optional[rtc.RemoteParticipant] = None

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def on_enter(self) -> None:
        """Called when agent joins the room and session is active.

        For inbound calls: greet immediately.
        For outbound calls: greeting is sent after callee joins (see outbound
        flow below), so do not greet here.
        """
        if self._is_outbound:
            logger.info("Outbound call — will send greeting after participant joins")
            return

        greeting = self._agent_config.get("greeting_message", "")
        if greeting.strip():
            logger.info(f"Sending greeting (inbound): {greeting[:60]}")
            # Use direct TTS for greeting to avoid LLM round-trip latency.
            await self.session.say(greeting)
            timestamp = datetime.utcnow().isoformat()
            self._call_data["transcript_lines"].append(
                f"[{timestamp}] assistant: {greeting}"
            )
            self._call_data["transcript_turns"].append(
                {"ts": timestamp, "speaker": "assistant", "text": greeting}
            )

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
        self._call_data["transcript_turns"].append(
            {"ts": timestamp, "speaker": "user", "text": user_text}
        )
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
            self._call_data["transcript_turns"].append(
                {"ts": timestamp, "speaker": "assistant", "text": text}
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

            transcript_json = {
                "call_sid": call_sid,
                "saved_at": datetime.utcnow().isoformat(),
                "lines": call_data["transcript_lines"],
                "turns": call_data.get("transcript_turns", []),
            }
            transcript_json_object = await upload_transcript_json(
                storage=storage,
                call_sid=call_sid,
                transcript_data=transcript_json,
            )
            call_data["transcript_json_url"] = (
                f"minio://transcripts/{transcript_json_object}"
            )
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

    Per the official docs, SIP participant attributes are:
      - sip.phoneNumber:      caller's phone number (inbound) or dialed number (outbound)
      - sip.trunkPhoneNumber: trunk phone number (DID dialed into for inbound, caller-ID for outbound)
      - sip.ruleID:           dispatch rule ID — non-empty for inbound, empty for outbound
      - sip.trunkID:          trunk ID used for the call
      - sip.callID:           LiveKit SIP call ID
    There is NO "sip.callDirection" attribute.
    """
    inbound_call: bool = False
    from_number: Optional[str] = None
    to_number: Optional[str] = None

    # Give a moment for participants to populate after session start
    for _attempt in range(6):
        for participant in ctx.room.remote_participants.values():
            attrs = participant.attributes or {}
            # sip.ruleID is set for inbound calls (dispatch rule routed the call)
            # and empty/absent for outbound calls
            rule_id = attrs.get("sip.ruleID", "")
            inbound_call = bool(rule_id)
            phone_number = attrs.get("sip.phoneNumber") or None
            trunk_phone = attrs.get("sip.trunkPhoneNumber") or None

            if inbound_call:
                # Inbound: phoneNumber = caller, trunkPhoneNumber = DID dialed
                from_number = phone_number
                to_number = trunk_phone
            else:
                # Outbound: phoneNumber = dialed number, trunkPhoneNumber = our caller-ID
                from_number = trunk_phone
                to_number = phone_number

            logger.info(
                f"SIP participant: inbound={inbound_call}, ruleID={rule_id}, "
                f"phoneNumber={phone_number}, trunkPhone={trunk_phone}, "
                f"resolved from={from_number}, to={to_number}"
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
    is_outbound: bool = False,
    outbound_phone: Optional[str] = None,
) -> None:
    """Background setup that runs AFTER session.start() has answered the call.

    Resolves SIP participant details, creates meeting record, bootstraps memory,
    and updates the agent's user_phone for per-turn memory hooks.
    This runs concurrently so the caller hears the greeting immediately.
    """
    try:
        # 1. Resolve SIP participant details
        if is_outbound and outbound_phone:
            # For outbound, we already know the details
            inbound_call = False
            from_number = None  # our trunk number (resolved below if needed)
            to_number = outbound_phone
            user_phone = _normalize_phone(outbound_phone)
            logger.info(f"Outbound call: user_phone={user_phone}")
        else:
            # For inbound, inspect SIP participant attributes
            sip = await _resolve_sip_details(ctx, call_sid)
            inbound_call = sip["inbound"]
            from_number = sip["from_number"]
            to_number = sip["to_number"]
            user_phone = None

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
        if not is_outbound:
            # For inbound, resolve from meeting record
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
                is_inbound_meeting = meeting.get("inbound")
                if is_inbound_meeting is True:
                    raw_phone = meeting.get("from_number")
                elif is_inbound_meeting is False:
                    raw_phone = meeting.get("to_number")
                else:
                    raw_phone = None
                if raw_phone:
                    user_phone = _normalize_phone(raw_phone)

        logger.info(f"Resolved user_phone={user_phone} (outbound={is_outbound})")

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
                            "You have persistent memory about this user from previous calls. "
                            "This is a NEW conversation — do NOT resume or reference the "
                            "previous conversation directly. Use the memory context only to "
                            "personalize (e.g. knowing the user's name, preferences). "
                            "If something conflicts with what the user says now, prefer "
                            "what they say now.\n\n" + "\n\n".join(lines)
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

    INBOUND flow (dispatch rule creates room):
      - Dispatch rule creates room + dispatches this agent
      - agent_id comes from job attributes or DEFAULT_AGENT_ID
      - Agent greets immediately after session.start()

    OUTBOUND flow (API dispatches agent with metadata):
      - server.py calls CreateAgentDispatchRequest with metadata containing
        phone_number and agent_id
      - Agent connects to room, starts session, then dials via CreateSIPParticipant
      - Agent waits for user to speak first (no greeting)

    Follows official LiveKit telephony docs:
      https://docs.livekit.io/telephony/agents-integration/
      https://github.com/livekit-examples/outbound-caller-python
    """
    call_start_time = time.monotonic()
    start_time_utc = datetime.utcnow().isoformat()

    room: rtc.Room = ctx.room
    room_name: str = room.name
    call_sid = room_name

    logger.info(f"New call: room={room_name}")

    # -------------------------------------------------------------------------
    # Parse job metadata — outbound calls include phone_number + agent_id
    # -------------------------------------------------------------------------
    dial_info: Optional[dict] = None
    phone_number: Optional[str] = None
    agent_id: Optional[str] = None

    try:
        meta_str = ctx.job.metadata or ""
        if meta_str.strip().startswith("{"):
            dial_info = _json.loads(meta_str)
            phone_number = dial_info.get("phone_number")
            agent_id = dial_info.get("agent_id")
            if phone_number:
                logger.info(f"Outbound call detected: phone_number={phone_number}")
    except Exception as e:
        logger.debug(f"No valid JSON in job metadata: {e}")

    is_outbound = phone_number is not None

    # -------------------------------------------------------------------------
    # Resolve agent_id (fallback chain)
    # -------------------------------------------------------------------------
    if not agent_id:
        try:
            # Try room metadata (legacy)
            room_meta = room.metadata or ""
            if room_meta.strip().startswith("{"):
                room_meta_dict = _json.loads(room_meta)
                agent_id = room_meta_dict.get("agent_id")
        except Exception:
            pass

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
            "No agent_id found in job metadata, room metadata, "
            "job attributes, or DEFAULT_AGENT_ID env var. Aborting."
        )
        return

    logger.info(
        f"Resolved agent_id={agent_id} for room={room_name} (outbound={is_outbound})"
    )

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
    # Shared call state (fresh per call — no carryover)
    # -------------------------------------------------------------------------
    call_data = {
        "audio_chunks": [],
        "audio_sample_rate": None,
        "audio_num_channels": None,
        "transcript_lines": [],
        "transcript_turns": [],
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
    # For outbound: we already know the user_phone from dial_info
    # -------------------------------------------------------------------------
    outbound_user_phone = _normalize_phone(phone_number) if phone_number else None

    agent = VoiceraAgent(
        agent_config=agent_config,
        call_sid=call_sid,
        agent_type=agent_type,
        is_outbound=is_outbound,
        user_phone=outbound_user_phone,  # known for outbound, resolved later for inbound
        call_data=call_data,
        call_start_time=call_start_time,
        start_time_utc=start_time_utc,
        storage=storage,
        initial_instructions=system_prompt,
    )

    # -------------------------------------------------------------------------
    # Build AgentSession
    # -------------------------------------------------------------------------
    from livekit.plugins.turn_detector.english import EnglishModel

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
            session_kwargs["turn_detection"] = EnglishModel()
            logger.info("Turn detection: EnglishModel ENABLED")
        except Exception as e:
            logger.warning(
                f"Could not load EnglishModel: {e} — using default turn detection"
            )

    session = AgentSession(**session_kwargs)

    # -------------------------------------------------------------------------
    # Register shutdown callback — runs when the room disconnects or
    # ctx.shutdown() is called.  This is where we persist call data.
    # -------------------------------------------------------------------------
    async def _on_shutdown(reason: str = "") -> None:
        duration = time.monotonic() - call_start_time
        logger.info(
            f"Call ended after {duration:.1f}s — saving data for {call_sid} "
            f"(reason={reason!r})"
        )

        recording_url = f"minio://recordings/calls/{call_sid}.mp3"

        # Stop LiveKit Egress recording
        if egress_id:
            try:
                logger.info(f"Stopping egress: {egress_id}")
                await stop_egress(egress_id)
                info = await wait_for_egress_completion(egress_id, timeout=90)
                if info and info.get("files"):
                    first_file = info["files"][0]
                    location = first_file.get("location")
                    filename = first_file.get("filename")
                    if location:
                        recording_url = location
                    elif filename:
                        recording_url = f"minio://recordings/{filename}"
                    logger.info("Egress output for %s: %s", call_sid, recording_url)
                else:
                    logger.warning(
                        "Egress completed without file output for %s (egress_id=%s)",
                        call_sid,
                        egress_id,
                    )
            except Exception as e:
                logger.warning(f"Error stopping egress: {e}")

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
            recording_url=recording_url,
            transcript_json_url=call_data.get("transcript_json_url"),
        )

    ctx.add_shutdown_callback(_on_shutdown)

    # -------------------------------------------------------------------------
    # Connect to room — required per official docs
    # For inbound: room already exists (dispatch rule created it)
    # For outbound: room created by CreateAgentDispatch
    # -------------------------------------------------------------------------
    logger.info(f"Connecting to room: {room_name}")
    await ctx.connect()

    # -------------------------------------------------------------------------
    # Start LiveKit Egress for call recording
    # This records the call audio to S3/MinIO
    # -------------------------------------------------------------------------
    egress_id = None
    enable_egress = os.getenv("ENABLE_EGRESS_RECORDING", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    if enable_egress:
        try:
            egress_id = await start_room_audio_egress(
                room_name=room_name,
                call_sid=call_sid,
                audio_format="mp3",
            )
            if egress_id:
                logger.info(f"Egress started: {egress_id}")
            else:
                logger.warning("Failed to start egress recording")
        except Exception as e:
            logger.warning(f"Error starting egress: {e}")

    # -------------------------------------------------------------------------
    # Start session — this answers the SIP call for inbound.
    # For outbound, we start the session BEFORE dialing so the agent is ready
    # to listen as soon as the callee picks up.
    # -------------------------------------------------------------------------
    session_started = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                close_on_disconnect=False,
            ),
        )
    )

    if is_outbound:
        # -----------------------------------------------------------------
        # OUTBOUND: Dial the phone number via SIP
        # Per docs: agent starts session first, then creates SIP participant
        # -----------------------------------------------------------------
        outbound_trunk_id = os.environ.get("LIVEKIT_SIP_OUTBOUND_TRUNK_ID", "")

        # Check per-agent trunk override
        per_agent_trunk = agent_config.get("livekit_outbound_trunk_id", "")
        if per_agent_trunk:
            outbound_trunk_id = per_agent_trunk

        if not outbound_trunk_id:
            logger.error("No outbound SIP trunk configured. Aborting outbound call.")
            ctx.shutdown()
            return

        participant_identity = phone_number  # use phone number as identity

        logger.info(
            f"Dialing {phone_number} via trunk={outbound_trunk_id} in room={room_name}"
        )

        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=outbound_trunk_id,
                    sip_call_to=phone_number,
                    participant_identity=participant_identity,
                    # Block until the callee answers (or call fails)
                    wait_until_answered=True,
                )
            )
            logger.info(f"Outbound call answered: {phone_number}")

            # Wait for session to be fully started
            await session_started

            # Wait for the SIP participant to join the room
            participant = await ctx.wait_for_participant(identity=participant_identity)
            agent.sip_participant = participant
            logger.info(f"SIP participant joined: {participant.identity}")

            # Send greeting only after callee is connected to avoid speaking
            # into an empty room during outbound setup.
            outbound_greeting = agent_config.get("greeting_message", "")
            if isinstance(outbound_greeting, str) and outbound_greeting.strip():
                await asyncio.sleep(0.25)
                logger.info(f"Sending greeting (outbound): {outbound_greeting[:60]}")
                await session.say(outbound_greeting)
                timestamp = datetime.utcnow().isoformat()
                call_data["transcript_lines"].append(
                    f"[{timestamp}] assistant: {outbound_greeting}"
                )
                call_data["transcript_turns"].append(
                    {
                        "ts": timestamp,
                        "speaker": "assistant",
                        "text": outbound_greeting,
                    }
                )

        except Exception as e:
            logger.error(f"Outbound call failed: {e}")
            ctx.shutdown()
            return
    else:
        # -----------------------------------------------------------------
        # INBOUND: Just wait for session to start — greeting handled by on_enter
        # -----------------------------------------------------------------
        await session_started

    # -------------------------------------------------------------------------
    # Kick off background setup (meeting record, memory bootstrap) without
    # blocking the call.
    # -------------------------------------------------------------------------
    asyncio.create_task(
        _post_start_setup(
            ctx=ctx,
            agent=agent,
            session=session,
            agent_config=agent_config,
            agent_type=agent_type,
            call_sid=call_sid,
            start_time_utc=start_time_utc,
            is_outbound=is_outbound,
            outbound_phone=phone_number if is_outbound else None,
        )
    )
