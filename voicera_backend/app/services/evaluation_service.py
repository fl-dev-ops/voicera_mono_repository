"""
Evaluation service using the exact forever-learning evaluator stack:
- Provider/SDK: Google Gemini via google-genai (new SDK)
- Model: gemini-flash-lite-latest
- Input path: audio-first evaluation (no transcript heuristics)
- Output contract: forever-learning mock interview JSON format
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from app.config import settings
from app.database import get_database
from app.services.meeting_service import fetch_meeting_details
from app.storage.minio_client import MinIOStorage

logger = logging.getLogger(__name__)


FOREVER_LEARNING_MODEL = "gemini-flash-lite-latest"


def _get_mime_type_from_url(url: str) -> str:
    url_l = (url or "").lower()
    if ".mp3" in url_l:
        return "audio/mpeg"
    if ".wav" in url_l:
        return "audio/wav"
    if ".webm" in (url or "").lower():
        return "audio/webm"
    return "audio/mp4"


def _parse_json_from_model_text(text: str) -> Dict[str, Any]:
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        raise ValueError("Invalid response format from AI model")
    return json.loads(json_match.group(0))


def _fetch_recording_bytes(recording_url: str) -> bytes:
    if not recording_url:
        raise ValueError("No audio recording available for this session")

    # Path 1: minio://bucket/object
    if recording_url.startswith("minio://"):
        storage = MinIOStorage()
        parsed = storage.parse_minio_url(recording_url)
        if not parsed:
            raise ValueError(f"Invalid recording URL format: {recording_url}")

        bucket_name, object_name = parsed
        if not storage.object_exists(bucket_name, object_name):
            raise ValueError(f"Recording file not found: {object_name}")

        response = storage.client.get_object(bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    # Path 2: HTTP(S)
    if recording_url.startswith("http://") or recording_url.startswith("https://"):
        import httpx

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(recording_url)
            resp.raise_for_status()
            return resp.content

    raise ValueError(f"Unsupported recording URL format: {recording_url}")


def _build_mock_interview_prompt() -> str:
    """
    Keep this aligned with forever-learning's mock interview evaluation contract.
    """
    return """
You are a friendly interview coach giving personal feedback directly to the person who just completed this mock interview. Write as if you're having a one-on-one conversation with them.

IMPORTANT: Never use "candidate", "user", or "the person". Always address them directly as "you" or "your". Make the feedback feel personal and encouraging, like a mentor giving tips to help them succeed.

Analyze this mock interview and provide scores on a 0-100 scale for these areas:

1. Communication - How clearly did you express your thoughts? Was your articulation effective?
2. Structure - Did you use frameworks like STAR? Were your answers logically organized?
3. Confidence - How composed and professional did you appear under pressure?
4. Fluency - Did you speak smoothly without excessive pauses or filler words?
5. Self-Awareness - Did you show reflection, acknowledge growth areas, and demonstrate a growth mindset?

Also analyze the USER/HUMAN speaker ONLY (exclude the AI interviewer's speech entirely):
- Total complete sentences the user spoke (do NOT count sentences spoken by the AI agent)
- Total word count of the user's speech only (do NOT count words spoken by the AI agent)
- Estimated talk time in seconds (user's speaking time only, exclude AI agent's speaking time)

CRITICAL: The audio contains TWO speakers - an AI interviewer and a human user. You MUST only count sentences, words, and talk time for the HUMAN user. The AI agent asks questions - ignore those completely for stats.

Return ONLY a valid JSON response in this exact format:
{
  "scores": {
    "communication": <number 0-100>,
    "structure": <number 0-100>,
    "confidence": <number 0-100>,
    "fluency": <number 0-100>,
    "selfAwareness": <number 0-100>
  },
  "overallScore": <number 0-100>,
  "performanceLevel": "<Needs Improvement|Developing|Competent|Proficient|Expert>",
  "confidenceScore": <number 0.0-1.0>,
  "cefrLevel": "<A1|A2|B1|B2|C1|C2>",
  "stats": {
    "sentences": <number>,
    "words": <number>,
    "talkTimeSeconds": <number>
  },
  "whatDidGood": [
    "<MAX 25 words: simple, friendly praise like talking to a child>",
    "<MAX 25 words: another warm encouragement>",
    "<MAX 25 words: third positive if applicable>"
  ],
  "whatToImprove": [
    "<MAX 25 words: simple, gentle tip like talking to a child>",
    "<MAX 25 words: another easy suggestion>",
    "<MAX 25 words: third tip if applicable>"
  ]
}

STRICT RULES - MUST FOLLOW:
- Each whatDidGood item: MAXIMUM 25 words. No exceptions.
- Each whatToImprove item: MAXIMUM 25 words. No exceptions.
- Write like talking to a kindergarten student - super simple, warm, and friendly!
- Use short sentences with easy words. NO complex words or jargon.
- Examples: "You spoke really nicely!" or "Try to speak a little slower next time!"

confidenceScore (0.0-1.0): Voice clarity and confidence rating.
cefrLevel: English proficiency (A1/A2/B1/B2/C1/C2).

Performance levels:
- Needs Improvement (0-30), Developing (30-50), Competent (50-70), Proficient (70-85), Expert (85-100)

Important:
- Be encouraging but honest with realistic scores
- Focus on communication quality, not technical knowledge
- CRITICAL: Keep each feedback point under 25 words
""".strip()


def _evaluate_audio_with_gemini(recording_url: str) -> Dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        raise ValueError("Gemini API key not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    audio_bytes = _fetch_recording_bytes(recording_url)
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    mime_type = _get_mime_type_from_url(recording_url)

    prompt = _build_mock_interview_prompt()

    result = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(
                        data=base64.b64decode(audio_b64), mime_type=mime_type
                    ),
                ],
            ),
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    text = (result.text or "").strip()
    if not text:
        raise ValueError("Empty response from AI model")

    return _parse_json_from_model_text(text)


def generate_evaluation_from_meeting(meeting_id: str) -> Dict[str, Any]:
    meeting = fetch_meeting_details(meeting_id)
    if not meeting:
        return {"status": "fail", "status_code": 404, "message": "Session not found"}

    recording_url = meeting.get("recording_url")
    if not recording_url:
        return {
            "status": "fail",
            "status_code": 400,
            "message": "No audio recording available for this session",
        }

    try:
        evaluation = _evaluate_audio_with_gemini(recording_url)
    except Exception as exc:
        logger.exception("AI evaluation error for meeting %s", meeting_id)
        return {
            "status": "fail",
            "status_code": 500,
            "message": str(exc) or "Failed to evaluate session",
        }

    # Forever-learning parity: append server-side metadata
    evaluation["sessionId"] = meeting_id
    evaluation["evaluatedAt"] = datetime.now(timezone.utc).isoformat()
    evaluation["agentType"] = meeting.get("agent_type")

    db = get_database()
    meeting_table = db["CallLogs"]
    meeting_table.update_one(
        {"meeting_id": meeting_id},
        {
            "$set": {
                "evaluation_scores": evaluation.get("scores"),
                "evaluation_data": evaluation,
            }
        },
    )

    return evaluation


def get_or_generate_evaluation(meeting_id: str) -> Dict[str, Any]:
    meeting = fetch_meeting_details(meeting_id)
    if not meeting:
        return {"status": "fail", "status_code": 404, "message": "Session not found"}

    existing: Optional[Dict[str, Any]] = meeting.get("evaluation_data")
    if existing and isinstance(existing, dict):
        return existing

    return generate_evaluation_from_meeting(meeting_id)


def trigger_auto_evaluation_if_needed(
    meeting_id: str, force: bool = False
) -> Dict[str, Any]:
    """
    Auto-trigger evaluation generation after call finalization artifacts are persisted.

    Idempotent by default: skips generation when evaluation_data already exists,
    unless force=True.
    """
    meeting = fetch_meeting_details(meeting_id)
    if not meeting:
        logger.warning("[auto-eval] skip: meeting not found meeting_id=%s", meeting_id)
        return {"status": "skip", "reason": "meeting_not_found"}

    recording_url = meeting.get("recording_url")
    if not recording_url:
        logger.info("[auto-eval] skip: recording_url missing meeting_id=%s", meeting_id)
        return {"status": "skip", "reason": "recording_missing"}

    existing: Optional[Dict[str, Any]] = meeting.get("evaluation_data")
    if not force and existing and isinstance(existing, dict):
        logger.info(
            "[auto-eval] skip: evaluation already exists meeting_id=%s", meeting_id
        )
        return {"status": "skip", "reason": "already_exists"}

    logger.info("[auto-eval] start meeting_id=%s force=%s", meeting_id, force)
    result = generate_evaluation_from_meeting(meeting_id)

    if isinstance(result, dict) and result.get("status") == "fail":
        logger.error(
            "[auto-eval] failed meeting_id=%s status_code=%s message=%s",
            meeting_id,
            result.get("status_code"),
            result.get("message"),
        )
        return result

    logger.info("[auto-eval] success meeting_id=%s", meeting_id)
    return result
