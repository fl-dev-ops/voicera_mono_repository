"""Tool/function calling handlers for Pipecat voice bot.

Provides tool schemas and async handlers for the Kavya screening agent:
- query_question_bank: Search screening question bank
- query_job_profiles: Search available job profiles
- score_cefr: Score student English using CEFR framework
- save_screening_result: Save final screening result to backend

Uses Pipecat 0.0.101 FunctionSchema / ToolsSchema / FunctionCallParams API.
"""

import json
import random
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from .tool_data import QUESTION_BANK, JOB_PROFILES


# ============================================================================
# CEFR level ordering for comparison
# ============================================================================

CEFR_ORDER: List[str] = ["A1", "A2", "B1", "B2", "C1"]


# ============================================================================
# 1a. Tool Schemas
# ============================================================================

TOOL_SCHEMAS: Dict[str, FunctionSchema] = {
    "query_question_bank": FunctionSchema(
        name="query_question_bank",
        description=(
            "Search the screening question bank. Returns a question to ask "
            "the student based on job category, question type, difficulty "
            "level, and skill to assess."
        ),
        properties={
            "job_category": {
                "type": "string",
                "enum": ["customer_support", "data_entry", "delivery", "general"],
                "description": "Job category to filter questions for",
            },
            "question_type": {
                "type": "string",
                "enum": [
                    "intro",
                    "motivation",
                    "situational",
                    "behavioral",
                    "self_awareness",
                ],
                "description": "Type of question to ask",
            },
            "difficulty": {
                "type": "string",
                "enum": ["easy", "medium", "hard"],
                "description": "Difficulty level based on student's current performance",
            },
            "assesses": {
                "type": "string",
                "description": (
                    "Specific skill to assess "
                    "(e.g., fluency, coherence, empathy, patience)"
                ),
            },
        },
        required=["job_category", "question_type", "difficulty"],
    ),
    "query_job_profiles": FunctionSchema(
        name="query_job_profiles",
        description=(
            "Search available job profiles. Returns matching jobs based on "
            "category, required skills, or minimum English level."
        ),
        properties={
            "category": {
                "type": "string",
                "enum": ["customer_support", "data_entry", "delivery", "general"],
            },
            "min_english_level": {
                "type": "string",
                "enum": ["A1", "A2", "B1", "B2"],
                "description": (
                    "Maximum English level requirement to filter by "
                    "(returns jobs at or below this level)"
                ),
            },
            "skills": {
                "type": "string",
                "description": (
                    "Comma-separated skills to match (e.g., 'communication, patience')"
                ),
            },
        },
        required=[],
    ),
    "score_cefr": FunctionSchema(
        name="score_cefr",
        description=(
            "Score a student's English response using CEFR framework. "
            "Call this after each student answer to assess their English "
            "proficiency. Returns scoring instructions."
        ),
        properties={
            "student_response": {
                "type": "string",
                "description": (
                    "The student's verbatim response (from STT transcription)"
                ),
            },
            "question_asked": {
                "type": "string",
                "description": "The question that was asked",
            },
            "question_type": {
                "type": "string",
                "enum": [
                    "intro",
                    "motivation",
                    "situational",
                    "behavioral",
                    "self_awareness",
                ],
            },
        },
        required=["student_response", "question_asked"],
    ),
    "save_screening_result": FunctionSchema(
        name="save_screening_result",
        description=(
            "Save the final screening result when the interview is complete. "
            "Call this at the end of the screening conversation with the "
            "complete assessment."
        ),
        properties={
            "candidate_name": {"type": "string"},
            "location": {"type": "string"},
            "job_interest": {"type": "string"},
            "questions_asked": {"type": "integer"},
            "cefr_scores": {
                "type": "string",
                "description": "JSON array of per-question CEFR scores",
            },
            "overall_cefr": {
                "type": "string",
                "enum": ["A1", "A2", "B1", "B2", "C1"],
            },
            "skills_demonstrated": {
                "type": "string",
                "description": "Comma-separated list of demonstrated skills",
            },
            "outcome": {
                "type": "string",
                "enum": ["QUALIFIED", "NEEDS_PREP", "FOLLOW_UP"],
            },
            "next_step": {"type": "string"},
            "notes": {"type": "string"},
        },
        required=["candidate_name", "outcome", "overall_cefr"],
    ),
}


# ============================================================================
# 1b. Handler Functions
# ============================================================================


async def handle_query_question_bank(params: FunctionCallParams) -> None:
    """Filter in-memory QUESTION_BANK and return a matching question.

    Filters by job_category, question_type, difficulty (all required).
    If `assesses` is provided, further filters where the question's assesses
    list contains that skill. Picks a random match if multiple found.
    """
    args = params.arguments
    job_category = args.get("job_category")
    question_type = args.get("question_type")
    difficulty = args.get("difficulty")
    assesses = args.get("assesses")

    logger.info(
        f"query_question_bank: category={job_category}, "
        f"type={question_type}, difficulty={difficulty}, assesses={assesses}"
    )

    matches = [
        q
        for q in QUESTION_BANK
        if q.get("job_category") == job_category
        and q.get("type") == question_type
        and q.get("difficulty") == difficulty
    ]

    # Optional skill filter
    if assesses and matches:
        skill_lower = assesses.lower().strip()
        skill_matches = [
            q
            for q in matches
            if skill_lower in [s.lower() for s in q.get("assesses", [])]
        ]
        # Only narrow down if we actually found skill-specific matches
        if skill_matches:
            matches = skill_matches

    if matches:
        question = random.choice(matches)
        logger.info(f"query_question_bank: returning {question.get('question_id')}")
        await params.result_callback(question)
    else:
        logger.info("query_question_bank: no matching question found")
        await params.result_callback(
            {"message": "No matching question found for the given criteria."}
        )


async def handle_query_job_profiles(params: FunctionCallParams) -> None:
    """Filter in-memory JOB_PROFILES and return matching profiles.

    All filters are optional:
    - category: exact match on job category
    - min_english_level: return jobs at or below this CEFR level
    - skills: comma-separated string; match jobs with at least one overlapping skill
    """
    args = params.arguments
    category = args.get("category")
    min_english_level = args.get("min_english_level")
    skills_str = args.get("skills")

    logger.info(
        f"query_job_profiles: category={category}, "
        f"min_english_level={min_english_level}, skills={skills_str}"
    )

    matches = list(JOB_PROFILES)

    # Filter by category
    if category:
        matches = [j for j in matches if j.get("category") == category]

    # Filter by CEFR level (jobs at or below the given level)
    if min_english_level and min_english_level in CEFR_ORDER:
        max_idx = CEFR_ORDER.index(min_english_level)
        matches = [
            j
            for j in matches
            if j.get("min_english_level") in CEFR_ORDER[: max_idx + 1]
        ]

    # Filter by skills (at least one match)
    if skills_str:
        requested_skills = {s.strip().lower() for s in skills_str.split(",")}
        matches = [
            j
            for j in matches
            if requested_skills & {s.lower() for s in j.get("key_skills", [])}
        ]

    logger.info(f"query_job_profiles: returning {len(matches)} profiles")
    await params.result_callback({"profiles": matches, "count": len(matches)})


async def handle_score_cefr(params: FunctionCallParams) -> None:
    """Return scoring instructions for the LLM to self-score using CEFR rubric.

    Option A: LLM self-scores. We return a structured instruction dict
    containing the student response and question, and the LLM uses its
    system prompt rubric to fill in the CEFR score.
    """
    args = params.arguments
    student_response = args.get("student_response", "")
    question_asked = args.get("question_asked", "")
    question_type = args.get("question_type", "unknown")

    logger.info(
        f"score_cefr: question_type={question_type}, "
        f"response_length={len(student_response)}"
    )

    await params.result_callback(
        {
            "instruction": (
                "Score this response using the CEFR rubric in your system prompt. "
                "Evaluate fluency, coherence, vocabulary range, and grammatical "
                "accuracy. Return a CEFR level (A1/A2/B1/B2/C1) and brief "
                "justification. Keep the score internal — do NOT share it with "
                "the student."
            ),
            "student_response": student_response,
            "question_asked": question_asked,
            "question_type": question_type,
        }
    )


async def handle_save_screening_result(params: FunctionCallParams) -> None:
    """Save the final screening result to the backend API.

    Expects injected context keys (_call_sid, _agent_type, _user_phone, _org_id)
    added by the _wrap_with_context wrapper.
    """
    args = params.arguments

    # Extract injected context (prefixed with _)
    call_sid = args.pop("_call_sid", None)
    agent_type = args.pop("_agent_type", None)
    user_phone = args.pop("_user_phone", None)
    org_id = args.pop("_org_id", None)

    # Build payload with context + all remaining LLM-provided arguments
    payload: Dict[str, Any] = {
        "meeting_id": call_sid,
        "agent_type": agent_type,
        "org_id": org_id,
        "candidate_phone": user_phone,
    }
    # Add all non-underscore-prefixed arguments from the LLM
    for key, value in args.items():
        if not key.startswith("_"):
            payload[key] = value

    # Type coercion: LLM sends cefr_scores as JSON string, backend expects List[Dict]
    if isinstance(payload.get("cefr_scores"), str):
        try:
            payload["cefr_scores"] = json.loads(payload["cefr_scores"])
        except (ValueError, TypeError):
            payload["cefr_scores"] = None

    # Type coercion: LLM sends skills_demonstrated as comma-separated string, backend expects List[str]
    if isinstance(payload.get("skills_demonstrated"), str):
        payload["skills_demonstrated"] = [
            s.strip() for s in payload["skills_demonstrated"].split(",") if s.strip()
        ]

    try:
        logger.info(
            f"save_screening_result: saving for meeting={call_sid}, "
            f"outcome={payload.get('outcome')}"
        )
        from .backend_utils import save_screening_result as _save_to_backend

        success = await _save_to_backend(payload)
        if success:
            logger.info(f"save_screening_result: saved successfully for {call_sid}")
            await params.result_callback({"status": "saved"})
        else:
            logger.error(
                f"save_screening_result: backend returned failure for {call_sid}"
            )
            await params.result_callback(
                {"status": "error", "message": "Backend save failed"}
            )
    except Exception as e:
        logger.error(f"save_screening_result: failed to save — {e}")
        await params.result_callback({"status": "error", "message": str(e)})


# ============================================================================
# 1c. Registry and Wiring
# ============================================================================

TOOL_HANDLERS: Dict[str, Any] = {
    "query_question_bank": handle_query_question_bank,
    "query_job_profiles": handle_query_job_profiles,
    "score_cefr": handle_score_cefr,
    "save_screening_result": handle_save_screening_result,
}

# Tools that need call context (call_sid, agent_type, user_phone, org_id) injected
CONTEXT_AWARE_TOOLS: Set[str] = {"save_screening_result"}


def _wrap_with_context(handler, call_context: Dict[str, Any]):
    """Wrap a tool handler to inject call context into params.arguments.

    Injects keys prefixed with _ so they don't collide with LLM-provided args:
    - _call_sid
    - _agent_type
    - _user_phone
    - _org_id

    Args:
        handler: The original async handler function
        call_context: Dict with call_sid, agent_type, user_phone, org_id

    Returns:
        New async function that injects context before calling original handler
    """

    async def wrapped(params: FunctionCallParams):
        # Inject context keys into arguments (prefixed with _)
        params.arguments["_call_sid"] = call_context.get("call_sid")
        params.arguments["_agent_type"] = call_context.get("agent_type")
        params.arguments["_user_phone"] = call_context.get("user_phone")
        params.arguments["_org_id"] = call_context.get("org_id")
        await handler(params)

    return wrapped


def build_tools_schema(tool_names: List[str]) -> ToolsSchema:
    """Build a ToolsSchema from a list of tool names.

    Unknown tool names are skipped with a warning log.

    Args:
        tool_names: List of tool names to include (e.g. ["query_question_bank", ...])

    Returns:
        ToolsSchema instance with the matching FunctionSchema definitions
    """
    schemas = []
    for name in tool_names:
        schema = TOOL_SCHEMAS.get(name)
        if schema:
            schemas.append(schema)
        else:
            logger.warning(f"build_tools_schema: unknown tool '{name}', skipping")

    logger.info(f"build_tools_schema: built schema with {len(schemas)} tools")
    return ToolsSchema(standard_tools=schemas)


def register_tool_handlers(
    llm,
    tool_names: List[str],
    agent_config: Dict[str, Any],
    call_context: Dict[str, Any],
) -> None:
    """Register tool handlers on the LLM service.

    For context-aware tools (e.g. save_screening_result), wraps the handler
    to inject call context + org_id from agent_config.

    Args:
        llm: Pipecat LLM service instance
        tool_names: List of tool names to register
        agent_config: Agent configuration dict (used for org_id)
        call_context: Dict with call_sid, agent_type, user_phone
    """
    for name in tool_names:
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            logger.warning(f"register_tool_handlers: no handler for '{name}', skipping")
            continue

        if name in CONTEXT_AWARE_TOOLS:
            # Merge org_id from agent_config into call_context for wrapping
            enriched_context = {
                **call_context,
                "org_id": agent_config.get("org_id"),
            }
            handler = _wrap_with_context(handler, enriched_context)
            logger.info(f"register_tool_handlers: registered '{name}' (context-aware)")
        else:
            logger.info(f"register_tool_handlers: registered '{name}'")

        llm.register_function(name, handler)
