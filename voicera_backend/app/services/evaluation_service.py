"""
Evaluation service that generates forever-learning-compatible evaluation reports
from existing voicera meeting artifacts (transcript + metadata).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging
import re

from app.database import get_database
from app.services.meeting_service import fetch_meeting_details, parse_transcript

logger = logging.getLogger(__name__)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _to_int_score(value: float) -> int:
    return int(round(_clamp(value, 0, 100)))


def _cefr_from_score(score: int) -> str:
    # Keep parity with forever-learning score-to-CEFR thresholds
    if score >= 90:
        return "C2"
    if score >= 75:
        return "C1"
    if score >= 60:
        return "B2"
    if score >= 40:
        return "B1"
    if score >= 20:
        return "A2"
    return "A1"


def _performance_level(score: int) -> str:
    if score < 30:
        return "Needs Improvement"
    if score < 50:
        return "Developing"
    if score < 70:
        return "Competent"
    if score < 85:
        return "Proficient"
    return "Expert"


def _count_sentences(text: str) -> int:
    if not text:
        return 0
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text))


def _derive_scores(user_text: str, user_turns: int, words: int, sentences: int) -> Dict[str, int]:
    avg_sentence_len = (words / sentences) if sentences > 0 else 0
    avg_turn_len = (words / user_turns) if user_turns > 0 else 0
    filler_count = len(re.findall(r"\b(um+|uh+|like|you know|hmm+)\b", user_text.lower()))
    filler_ratio = (filler_count / words) if words > 0 else 1

    communication = _to_int_score(35 + avg_sentence_len * 2.2 + avg_turn_len * 0.45)
    structure = _to_int_score(30 + avg_sentence_len * 2 + (8 if re.search(r"\b(first|then|because|finally|also)\b", user_text.lower()) else 0))
    confidence = _to_int_score(40 + avg_turn_len * 0.7 - filler_ratio * 350)
    fluency = _to_int_score(42 + avg_sentence_len * 1.8 - filler_ratio * 380)
    self_awareness = _to_int_score(38 + (12 if re.search(r"\b(learn|improve|next time|better|mistake|feedback)\b", user_text.lower()) else 0) + avg_sentence_len * 1.3)

    return {
        "communication": communication,
        "structure": structure,
        "confidence": confidence,
        "fluency": fluency,
        "selfAwareness": self_awareness,
    }


def _feedback(scores: Dict[str, int], words: int, sentences: int) -> Dict[str, List[str]]:
    good: List[str] = []
    improve: List[str] = []

    if scores["communication"] >= 65:
        good.append("You shared your ideas clearly and made it easy to follow your thoughts.")
    else:
        improve.append("Try shorter, clear sentences so your ideas sound easier to understand.")

    if scores["fluency"] >= 65:
        good.append("Your speaking flow was smooth in many parts. Nice steady pace.")
    else:
        improve.append("Pause less and avoid filler words like um to sound more fluent.")

    if scores["structure"] >= 65:
        good.append("You kept your answers organized. That makes you sound more professional.")
    else:
        improve.append("Use simple order: first, then, result. It helps your answer feel structured.")

    if words >= 120:
        good.append("You gave detailed answers, which shows effort and good engagement.")
    else:
        improve.append("Add one more detail or example in each answer to sound stronger.")

    if sentences < 6:
        improve.append("Speak in complete sentences more often to improve clarity and confidence.")

    while len(good) < 3:
        good.append("You showed good effort and kept trying through the whole conversation.")
    while len(improve) < 3:
        improve.append("Practice daily for a few minutes. Small steps will make you better fast.")

    return {
        "whatDidGood": good[:3],
        "whatToImprove": improve[:3],
    }


def generate_evaluation_from_meeting(meeting_id: str) -> Dict[str, Any]:
    meeting = fetch_meeting_details(meeting_id)
    if not meeting:
        return {"status": "fail", "status_code": 404, "message": "Session not found"}

    transcript_content = meeting.get("transcript_content")
    if not transcript_content:
        return {
            "status": "fail",
            "status_code": 400,
            "message": "No transcript available for this session",
        }

    messages = parse_transcript(transcript_content)
    user_messages = [m for m in messages if m.get("role") == "user"]
    user_text = " ".join((m.get("content") or "").strip() for m in user_messages).strip()

    words = _word_count(user_text)
    sentences = _count_sentences(user_text)
    user_turns = len([m for m in user_messages if (m.get("content") or "").strip()])

    scores = _derive_scores(user_text, user_turns, words, sentences)
    overall_score = _to_int_score(sum(scores.values()) / max(len(scores), 1))
    confidence_score = round(_clamp(scores["confidence"] / 100, 0, 1), 2)
    talk_time_seconds = int(round(words / 2.6))  # ~156 words/min

    feedback = _feedback(scores, words, sentences)

    evaluation = {
        "scores": scores,
        "overallScore": overall_score,
        "performanceLevel": _performance_level(overall_score),
        "confidenceScore": confidence_score,
        "cefrLevel": _cefr_from_score(overall_score),
        "stats": {
            "sentences": sentences,
            "words": words,
            "talkTimeSeconds": talk_time_seconds,
        },
        "whatDidGood": feedback["whatDidGood"],
        "whatToImprove": feedback["whatToImprove"],
        "sessionId": meeting_id,
        "evaluatedAt": datetime.now(timezone.utc).isoformat(),
        "agentType": meeting.get("agent_type"),
    }

    db = get_database()
    meeting_table = db["CallLogs"]
    meeting_table.update_one(
        {"meeting_id": meeting_id},
        {
            "$set": {
                "evaluation_scores": scores,
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
