---
Kavya Screening Agent — Full Implementation Plan
Executive Summary
Build an agentic voice screening bot ("Kavya") on top of the existing Pipecat 0.0.101 voice pipeline. The core change is adding tool/function calling to the voice bot — a capability Pipecat fully supports but that has zero usage in the current codebase. Everything else (telephony, audio pipeline, memory, storage, backend API) stays as-is.
---
Architecture: What Changes vs What Stays
STAYS THE SAME (no changes)                    CHANGES / NEW
─────────────────────────────────               ──────────────────────────────
✅ Vobiz telephony integration                  🔨 Tool definitions in bot.py
✅ FastAPI server + WebSocket endpoint           🔨 Tool handler functions (new module)
✅ VobizFrameSerializer                          🔨 Question Bank data + query logic
✅ MinIO storage (recordings/transcripts)        🔨 Job Profiles data + query logic
✅ Backend API (meetings, agents, memory)         🔨 CEFR scoring logic
✅ Memory system (search/ingest)                  🔨 Screening state tracker
✅ Post-call recording submission                 🔨 Structured call summary submission
✅ VAD + Smart Turn v3                            🔧 Agent config schema (add tools field)
✅ STT/TTS service factories                      🔧 VAD tuning for interview pace
✅ Evaluation service (post-call)                 🔧 Backend: new screening_results collection
✅ Docker / docker-compose                        🔧 Backend: screening results API endpoints
---
Phase 0: Foundation — Tool Calling Infrastructure
Goal: Wire up Pipecat's function calling system in bot.py so any agent can use tools.
Files: api/bot.py, api/services.py
Effort: 1 day
0.1 Add tool support to the pipeline assembly (bot.py)
Currently, LLMContext is created with only messages:
# CURRENT (bot.py line 180-185)
context = LLMContext(context_messages)
Change to accept tools from agent config:
# NEW
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
# Build tools from agent_config if present
tools_config = agent_config.get("tools")
tools_schema = None
if tools_config:
    from .tool_handlers import build_tools_schema, register_tool_handlers
    tools_schema = build_tools_schema(tools_config)
context = LLMContext(
    context_messages,
    tools=tools_schema,
    tool_choice="auto",
)
0.2 Register tool handlers on the LLM service
After llm = create_llm_service(llm_config):
if tools_config:
    register_tool_handlers(llm, tools_config, agent_config)
0.3 Key design decision: Tools are agent-config-driven
Tools are not hardcoded. The agent_config specifies which tools this agent has access to. This means:
- A sales agent has no tools (current behavior, unchanged)
- The Kavya screening agent has question_bank, job_profiles, score_cefr, save_screening_result
- Future agents can have different tool sets
Agent config schema addition:
{
  agent_config: {
    system_prompt: ...,
    llm_model: { ... },
    stt_model: { ... },
    tts_model: { ... },
    tools: [question_bank, job_profiles, score_cefr, save_screening_result]
  }
}
---
Phase 1: Tool Handlers Module
Goal: Create the tool handler functions that the LLM can invoke during conversation.
Files: New api/tool_handlers.py, new api/tool_data/ directory
Effort: 2-3 days
1.1 New file: api/tool_handlers.py
This is the central module that:
1. Defines FunctionSchema for each tool
2. Implements the async handler for each tool
3. Provides build_tools_schema() and register_tool_handlers() functions
"""Tool/function calling handlers for agentic voice bots.
Tools are registered on the LLM service and invoked by the model during conversation.
Each tool follows Pipecat's FunctionCallParams pattern.
"""
from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
# ── Tool Registry ──
TOOL_SCHEMAS = { ... }  # name -> FunctionSchema
def build_tools_schema(tool_names: list[str]) -> ToolsSchema:
    """Build ToolsSchema from list of tool names in agent config."""
    schemas = [TOOL_SCHEMAS[name] for name in tool_names if name in TOOL_SCHEMAS]
    return ToolsSchema(standard_tools=schemas)
def register_tool_handlers(llm, tool_names: list[str], agent_config: dict):
    """Register handler functions on the LLM for each tool."""
    for name in tool_names:
        if name in TOOL_HANDLERS:
            handler = TOOL_HANDLERS[name]
            # Some handlers need agent_config context (e.g., org_id for saving results)
            if name in CONTEXT_AWARE_TOOLS:
                handler = _wrap_with_context(handler, agent_config)
            llm.register_function(name, handler)
1.2 Tool: query_question_bank
Schema:
FunctionSchema(
    name="query_question_bank",
    description="Search the screening question bank. Returns a question to ask the student based on job category, question type, difficulty level, and skill to assess.",
    properties={
        "job_category": {
            "type": "string",
            "enum": ["customer_support", "data_entry", "delivery", "general"],
            "description": "Job category to filter questions for"
        },
        "question_type": {
            "type": "string",
            "enum": ["intro", "motivation", "situational", "behavioral", "self_awareness"],
            "description": "Type of question to ask"
        },
        "difficulty": {
            "type": "string",
            "enum": ["easy", "medium", "hard"],
            "description": "Difficulty level based on student's current performance"
        },
        "assesses": {
            "type": "string",
            "description": "Specific skill to assess (e.g., fluency, coherence, empathy, patience)"
        },
    },
    required=["job_category", "question_type", "difficulty"],
)
Handler: Queries an in-memory JSON dataset. Returns question text + metadata.
Data source: api/tool_data/question_bank.json — a JSON file with ~50-100 questions loaded at startup. No database needed for MVP.
1.3 Tool: query_job_profiles
Schema:
FunctionSchema(
    name="query_job_profiles",
    description="Search available job profiles. Returns matching jobs based on category, required skills, or minimum English level.",
    properties={
        "category": {
            "type": "string",
            "enum": ["customer_support", "data_entry", "delivery", "general"],
        },
        "min_english_level": {
            "type": "string",
            "enum": ["A1", "A2", "B1", "B2"],
            "description": "Maximum English level requirement to filter by (returns jobs at or below this level)"
        },
        "skills": {
            "type": "string",
            "description": "Comma-separated skills to match (e.g., 'communication, patience')"
        },
    },
    required=[],
)
Handler: Queries an in-memory JSON dataset. Returns matching job profiles.
Data source: api/tool_data/job_profiles.json — ~10-20 job profiles.
1.4 Tool: score_cefr
Schema:
FunctionSchema(
    name="score_cefr",
    description="Score a student's English response using CEFR framework. Call this after each student answer to assess their English proficiency. Returns fluency, accuracy, coherence, range scores and overall CEFR level.",
    properties={
        "student_response": {
            "type": "string",
            "description": "The student's verbatim response (from STT transcription)"
        },
        "question_asked": {
            "type": "string",
            "description": "The question that was asked"
        },
        "question_type": {
            "type": "string",
            "enum": ["intro", "motivation", "situational", "behavioral", "self_awareness"],
        },
    },
    required=["student_response", "question_asked"],
)
Handler — two options:
Option A (MVP — LLM self-scores): The handler returns a prompt-based instruction telling the LLM to score the response. The LLM already has the CEFR rubric in its system prompt, so the "tool result" is really just a structured template the LLM fills in. This is fast (no extra API call) but less consistent.
async def handle_score_cefr(params: FunctionCallParams):
    # The LLM scores the response itself based on the rubric in system prompt.
    # We return a structured template for it to reason through.
    result = {
        "instruction": "Score this response using the CEFR rubric in your system prompt. "
                       "Provide scores for fluency, accuracy, coherence, range (0-4 each) "
                       "and determine overall CEFR level.",
        "student_response": params.arguments["student_response"],
        "question_asked": params.arguments["question_asked"],
    }
    await params.result_callback(result)
Option B (Production — dedicated scorer): A separate fast LLM call (gpt-4o-mini or gemini-flash) that returns structured JSON scores. More consistent, ~300-500ms latency.
async def handle_score_cefr(params: FunctionCallParams):
    import httpx
    # Call a lightweight scoring endpoint (could be backend API or direct LLM call)
    scores = await _call_cefr_scorer(
        params.arguments["student_response"],
        params.arguments["question_asked"],
    )
    await params.result_callback(scores)
Recommendation: Start with Option A. The main LLM (GPT-4o) is good enough for text-based CEFR scoring. Move to Option B if scoring consistency is a problem.
1.5 Tool: save_screening_result
Schema:
FunctionSchema(
    name="save_screening_result",
    description="Save the final screening result when the interview is complete. Call this at the end of the screening conversation with the complete assessment.",
    properties={
        "candidate_name": {"type": "string"},
        "location": {"type": "string"},
        "job_interest": {"type": "string"},
        "questions_asked": {"type": "integer"},
        "cefr_scores": {
            "type": "string",
            "description": "JSON array of per-question CEFR scores"
        },
        "overall_cefr": {
            "type": "string",
            "enum": ["A1", "A2", "B1", "B2", "C1"]
        },
        "skills_demonstrated": {
            "type": "string",
            "description": "Comma-separated list of demonstrated skills"
        },
        "outcome": {
            "type": "string",
            "enum": ["QUALIFIED", "NEEDS_PREP", "FOLLOW_UP"],
        },
        "next_step": {"type": "string"},
        "notes": {"type": "string"},
    },
    required=["candidate_name", "outcome", "overall_cefr"],
)
Handler: POSTs the structured result to the backend API. This creates a screening record linked to the meeting.
async def handle_save_screening_result(params: FunctionCallParams):
    from .backend_utils import _get_backend_url, _get_api_headers
    import httpx
    
    payload = {
        "meeting_id": params.arguments.get("_call_sid"),  # injected by wrapper
        "agent_type": params.arguments.get("_agent_type"),
        **{k: v for k, v in params.arguments.items() if not k.startswith("_")},
    }
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_get_backend_url()}/api/v1/screening-results",
            json=payload,
            headers=_get_api_headers(),
        )
        resp.raise_for_status()
    
    await params.result_callback({"status": "saved"})
---
Phase 2: Kavya System Prompt
Goal: Craft the system prompt that drives Kavya's behavior, reasoning, and tool usage.
Files: Stored in backend DB as part of agent config (no file changes)
Effort: 1-2 days of iteration
2.1 System prompt structure
You are Kavya, a warm and friendly voice screening agent for job placement.
## YOUR PERSONALITY
- Warm, patient, encouraging — like a supportive older sister
- Use simple English (Tier 2/3 city friendly)
- Speak at a moderate pace
- Always give encouragement, even when student struggles
- Never make the student feel judged or inadequate
## YOUR WORKFLOW
1. WELCOME: Greet, introduce yourself, set expectations
2. DISCOVERY: Capture name (confirm spelling), location, education, job interest
3. JOB MATCHING: Use query_job_profiles tool to find suitable roles
4. SCREENING: Ask 3-5 questions using query_question_bank tool
   - After EACH student answer, use score_cefr tool to assess
   - Adapt difficulty based on scores (low score → easier questions)
   - If student is stuck, use follow_up_hint from question bank
   - Offer think time if student seems nervous
5. WRAP-UP: Summarize outcome, communicate next steps, use save_screening_result tool
## TOOL USAGE RULES
- ALWAYS call query_question_bank before asking a screening question
- ALWAYS call score_cefr after each student answer (silently — don't tell student their score)
- Call query_job_profiles when you know the student's job interest
- Call save_screening_result at the end of the conversation
- Never mention tools, scores, or internal reasoning to the student
## ADAPTATION RULES
- If CEFR score < A2 after 2 questions: switch to difficulty=easy, offer more encouragement
- If student says "I don't know": use follow_up_hint, give examples
- If student gives very short answers: ask follow-up, don't move on immediately
- If student pauses > 5 seconds: gently say "Take your time" or "No rush"
- If overall CEFR < A2 after 3 questions: outcome=NEEDS_PREP, suggest practice app
- If overall CEFR >= B1: outcome=QUALIFIED, hand off to recruitment
## OUTCOME DECISIONS
- QUALIFIED: CEFR >= B1, demonstrated required skills for matched job
- NEEDS_PREP: CEFR < A2, or couldn't complete basic questions → suggest practice
- FOLLOW_UP: Mixed signals, needs another call or different assessment
## IMPORTANT
- You are on a PHONE CALL. Keep responses concise (1-3 sentences max).
- Don't read out lists or long text — this is voice, not chat.
- Use natural speech patterns: "That's great", "Good answer", "Let me think..."
- If you need time (tool call), say something natural like "Let me find the right question for you"
2.2 Greeting message
Hi, I'm Kavya. I'm here to help you find a job that's right for you. I'll ask a few simple questions — just answer in whatever way is comfortable. What's your name?
---
Phase 3: Backend API Extensions
Goal: Add screening results storage and retrieval to the backend.
Files: voicera_backend/app/routers/screening.py, voicera_backend/app/models/schemas.py
Effort: 1 day
3.1 New MongoDB collection: ScreeningResults
# In database_init.py
db.ScreeningResults.create_index("meeting_id", unique=True)
db.ScreeningResults.create_index("org_id")
db.ScreeningResults.create_index("outcome")
db.ScreeningResults.create_index("candidate_phone")
3.2 New Pydantic schemas
class ScreeningResultCreate(BaseModel):
    meeting_id: str
    agent_type: str
    org_id: Optional[str] = None
    candidate_name: Optional[str] = None
    candidate_phone: Optional[str] = None
    location: Optional[str] = None
    job_interest: Optional[str] = None
    questions_asked: Optional[int] = None
    cefr_scores: Optional[List[Dict[str, Any]]] = None
    overall_cefr: Optional[str] = None
    skills_demonstrated: Optional[List[str]] = None
    outcome: str  # QUALIFIED | NEEDS_PREP | FOLLOW_UP
    next_step: Optional[str] = None
    notes: Optional[str] = None
3.3 New router: /api/v1/screening-results
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /screening-results | API Key | Save screening result (called by voice bot tool) |
| GET | /screening-results | JWT | List screening results (frontend dashboard) |
| GET | /screening-results/{meeting_id} | JWT | Get screening result for a specific call |
3.4 Integrate with existing evaluation
The existing evaluation_service.py already does post-call audio evaluation with Gemini. The screening result from the tool call is complementary — it captures the agent's real-time assessment during the call, while the evaluation service provides a post-hoc audio analysis. Both get stored on the meeting record.
---
Phase 4: Data Files — Question Bank & Job Profiles
Goal: Create the static data that tools query.
Files: New api/tool_data/question_bank.json, api/tool_data/job_profiles.json
Effort: 1 day
4.1 Question Bank structure
[
  {
    question_id: Q001,
    question_text: Tell me about yourself — anything you'd like to share.,
    type: intro,
    difficulty: easy,
    job_category: general,
    assesses: [fluency, coherence],
    good_answer_signals: [shares personal info, organized response, comfortable speaking],
    follow_up_hint: If very short, ask about education or daily routine
  },
  {
    question_id: Q012,
    question_text: Why do you want to work in customer support?,
    type: motivation,
    difficulty: easy,
    job_category: customer_support,
    assesses: [motivation, coherence, fluency],
    good_answer_signals: [genuine interest, people-oriented, specific reason],
    follow_up_hint: Ask what they enjoy about helping people
  }
  // ... 50-100 questions
]
4.2 Job Profiles structure
[
  {
    job_id: JOB001,
    title: Customer Support Executive,
    category: customer_support,
    min_english_level: B1,
    key_skills: [communication, patience, empathy],
    typical_tasks: [Handle inbound calls, Resolve complaints, Update CRM],
    salary_range: 15K-22K,
    screening_focus: [empathy, clarity, handling pressure]
  }
  // ... 10-20 profiles
]
4.3 Data loading strategy
Load once at module import time (in-memory). These are small datasets (<100KB). No database needed.
# In api/tool_data/__init__.py
import json
from pathlib import Path
_DATA_DIR = Path(__file__).parent
def _load_json(filename):
    with open(_DATA_DIR / filename) as f:
        return json.load(f)
QUESTION_BANK = _load_json("question_bank.json")
JOB_PROFILES = _load_json("job_profiles.json")
---
Phase 5: Pipeline Integration & VAD Tuning
Goal: Wire everything together in bot.py and tune for interview-style conversations.
Files: api/bot.py, env vars
Effort: 1 day
5.1 Pipeline changes in bot.py
The pipeline processor order stays the same. The only change is how LLMContext is created (adding tools) and registering handlers on the LLM. The tool call → result → LLM re-run loop is handled automatically by Pipecat's LLMContextAggregatorPair.
# In run_bot(), after creating llm, stt, tts:
# Build tools from agent config
tools_config = agent_config.get("tools")
if tools_config:
    from .tool_handlers import build_tools_schema, register_tool_handlers
    tools_schema = build_tools_schema(tools_config)
    # Pass call context to tool handlers (call_sid, agent_type, user_phone)
    call_context = {
        "call_sid": call_data.get("call_sid"),
        "agent_type": call_data.get("agent_type"),
        "user_phone": user_phone,
    }
    register_tool_handlers(llm, tools_config, agent_config, call_context)
else:
    tools_schema = None
# Create context WITH tools
context = LLMContext(
    context_messages,
    tools=tools_schema,
    tool_choice="auto" if tools_schema else None,
)
5.2 VAD tuning for interview pace
Nervous students pause longer. Recommended env var overrides for screening agents:
# More patient turn detection for interviews
SMART_TURN_STOP_SECS=2.0          # Was 1.0 — give students more thinking time
SMART_TURN_MAX_DURATION_SECS=15.0  # Was 8.0 — allow longer answers
USER_TURN_STOP_TIMEOUT=3.0         # Was 1.5 — longer fallback timeout
VAD_STOP_SECS=0.8                  # Was 0.5 — more silence tolerance
Better approach: Make these configurable per-agent in agent_config:
{
  agent_config: {
    vad_overrides: {
      smart_turn_stop_secs: 2.0,
      smart_turn_max_duration_secs: 15.0,
      user_turn_stop_timeout: 3.0,
      vad_stop_secs: 0.8
    }
  }
}
Then in bot.py, read these before creating VAD/Smart Turn:
vad_overrides = agent_config.get("vad_overrides", {})
smart_turn_stop_secs = float(vad_overrides.get("smart_turn_stop_secs", os.getenv("SMART_TURN_STOP_SECS", "1.0")))
# ... etc
5.3 Handle tool call silence
When the LLM calls a tool, TTS pauses. For fast tools (question bank lookup: <50ms), this is imperceptible. For score_cefr (if using Option B with a separate LLM call: ~500ms), there might be a brief silence.
Mitigation: The system prompt instructs Kavya to say something natural before/after tool calls:
- Before asking a question: "Let me find a good question for you..." (while query_question_bank runs)
- After student answers: "Good answer." (while score_cefr runs)
This is handled entirely by prompt engineering — no pipeline changes needed.
---
Phase 6: Memory Integration for Screening
Goal: Leverage existing memory system for returning callers and structured screening data.
Files: Minor changes to memory ingest payload
Effort: 0.5 days
6.1 Returning caller detection
Already works. The existing memory bootstrap in bot.py fetches profile + past snippets at call start. The system prompt tells Kavya to use this:
If you have memory of this student from a previous call:
- Greet them by name: "Hi [name], good to hear from you again!"
- Reference their previous screening if available
- Don't re-ask questions you already know the answer to
6.2 Structured screening data in memory
After the call, the transcript is already ingested into memory. Additionally, the save_screening_result tool saves structured data to the backend. For future calls, the memory search will return relevant past snippets (including screening outcomes) via vector similarity.
Enhancement (optional): Also ingest a structured summary into memory:
# In bot.py finally block, after transcript ingest:
if screening_result:
    await memory_ingest(
        user_phone=user_phone,
        text=f"SCREENING RESULT: {json.dumps(screening_result)}",
        source={"call_sid": call_sid, "type": "screening_result"},
        tags=["screening_result"],
    )
---
Phase 7: Agent Config for Kavya
Goal: Create the complete agent configuration to be stored in the backend.
Effort: 0.5 days
7.1 Full Kavya agent config
{
  agent_type: kavya_screening,
  agent_id: kavya-screening-v1,
  org_id: <org_id>,
  agent_category: screening,
  greeting_message: Hi, I'm Kavya. I'm here to help you find a job that's right for you. I'll ask a few simple questions — just answer in whatever way is comfortable. What's your name?,
  agent_config: {
    system_prompt: <the full system prompt from Phase 2>,
    greeting_message: Hi, I'm Kavya. I'm here to help you find a job that's right for you. I'll ask a few simple questions — just answer in whatever way is comfortable. What's your name?,
    language: English,
    enable_memory: true,
    session_timeout_minutes: 15,
    
    llm_model: {
      name: openai,
      args: { model: gpt-4o }
    },
    stt_model: {
      name: deepgram,
      language: English (India),
      args: { model: nova-3 }
    },
    tts_model: {
      name: cartesia,
      language: English (India),
      args: {
        model: sonic-2,
        voice_id: <warm-female-indian-english-voice-id>
      }
    },
    
    tools: [
      query_question_bank,
      query_job_profiles,
      score_cefr,
      save_screening_result
    ],
    
    vad_overrides: {
      smart_turn_stop_secs: 2.0,
      smart_turn_max_duration_secs: 15.0,
      user_turn_stop_timeout: 3.0,
      vad_stop_secs: 0.8
    }
  }
}
---
Phase 8: Testing & Iteration
Goal: Validate the full flow end-to-end.
Effort: 2-3 days
8.1 Manual testing checklist
| Test Case | What to Verify |
|-----------|---------------|
| Happy path (Example 1) | Full flow: greeting → discovery → job match → 3 questions → scoring → qualified outcome |
| Struggling candidate (Example 2) | Adaptation: easier questions, encouragement, think time, NEEDS_PREP outcome |
| Returning caller | Memory: recognized by phone, personalized greeting, previous data referenced |
| Tool call latency | No awkward silences during tool calls |
| Interruption during tool call | Student speaks while tool is running — handled gracefully |
| Very short answers | Agent doesn't move on too fast, asks follow-ups |
| Long pauses (10-15s) | VAD doesn't cut off, agent waits patiently |
| Student says "I don't know" | Agent provides examples/hints |
| Call drops mid-screening | Partial data saved, can resume on callback |
| Post-call data | Screening result saved, transcript saved, evaluation generated |
8.2 Prompt iteration
The system prompt will need 5-10 iterations based on real call testing. Key things to tune:
- Tool call frequency (too many = slow, too few = no data)
- Response length (too long for voice)
- Adaptation sensitivity (when to switch difficulty)
- Natural filler phrases during tool calls
---
File Map — All Changes
voice_2_voice_server/
├── api/
│   ├── bot.py                    # MODIFY: Add tools to LLMContext, VAD overrides from config
│   ├── tool_handlers.py          # NEW: Tool schemas, handlers, registry
│   ├── tool_data/                # NEW: Static data directory
│   │   ├── __init__.py           # NEW: Data loader
│   │   ├── question_bank.json    # NEW: ~50-100 screening questions
│   │   └── job_profiles.json     # NEW: ~10-20 job profiles
│   ├── server.py                 # NO CHANGE
│   ├── services.py               # NO CHANGE
│   ├── backend_utils.py          # MINOR: Add save_screening_result helper
│   ├── memory_processor.py       # NO CHANGE
│   └── call_recording_utils.py   # NO CHANGE
│
voicera_backend/
├── app/
│   ├── routers/
│   │   └── screening.py          # NEW: Screening results CRUD endpoints
│   ├── models/
│   │   └── schemas.py            # MODIFY: Add ScreeningResultCreate/Response
│   ├── services/
│   │   └── evaluation_service.py # NO CHANGE (complementary, not replaced)
│   └── database_init.py          # MODIFY: Add ScreeningResults collection + indexes
---
Timeline Summary
| Phase | What | Effort | Dependencies |
|-------|------|--------|-------------|
| 0 | Tool calling infrastructure in bot.py | 1 day | None |
| 1 | Tool handlers module + all 4 tools | 2-3 days | Phase 0 |
| 2 | Kavya system prompt | 1-2 days | Phase 1 (needs tool names) |
| 3 | Backend API: screening results | 1 day | None (parallel with 0-2) |
| 4 | Question bank + job profiles data | 1 day | None (parallel) |
| 5 | Pipeline integration + VAD tuning | 1 day | Phases 0-4 |
| 6 | Memory integration for screening | 0.5 days | Phase 5 |
| 7 | Agent config creation | 0.5 days | Phases 2, 5 |
| 8 | Testing & prompt iteration | 2-3 days | All phases |
Total: ~10-13 days for a working, tested Kavya screening agent.
Critical path: Phase 0 → Phase 1 → Phase 5 → Phase 8
Parallelizable: Phases 2, 3, 4 can all run in parallel with Phase 1.
---
Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Tool call latency causes awkward silence | High | System prompt instructs natural filler phrases; keep tools fast (<200ms) |
| LLM calls tools too often / not enough | Medium | Tune system prompt; use tool_choice to control |
| CEFR scoring inconsistency (LLM self-scoring) | Medium | Start with Option A, move to dedicated scorer if needed |
| VAD cuts off nervous students | High | Per-agent VAD overrides; generous timeouts for screening |
| Smart Turn misinterprets thinking pauses | Medium | Higher stop_secs for screening agents |
| Tool call interrupted by user speech | Low | Pipecat handles this natively (cancel_on_interruption) |
| Question bank too small / repetitive | Medium | Start with 50, expand based on usage patterns |
| Student speaks non-English | Medium | STT set to en-IN handles Indian English; system prompt handles code-switching |