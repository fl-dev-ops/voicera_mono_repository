"""
Call recording API routes.
"""
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from app.models.schemas import CallRecordingCreate
from app.services import call_recording_service
from app.services.evaluation_service import trigger_auto_evaluation_if_needed
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/call-recordings", tags=["call-recordings"])

@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def save_call_recording(recording_data: CallRecordingCreate, background_tasks: BackgroundTasks):
    """
    Save or update call recording data.
    
    This endpoint is called by the voice server after a call completes.
    It updates the meeting record with recording URLs, transcript, and call metadata.
    
    Note: This endpoint is currently unauthenticated for service-to-service calls.
    Consider adding API key authentication or service token in production.
    
    Args:
        recording_data: Call recording data including URLs and transcript
        
    Returns:
        Updated meeting document
    """
    result = call_recording_service.save_call_recording(recording_data)
    
    if isinstance(result, dict) and result.get("status") == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Failed to save call recording")
        )

    # Non-blocking auto-evaluation trigger after recording artifacts are persisted.
    # Failures must not break call finalization response.
    try:
        background_tasks.add_task(
            trigger_auto_evaluation_if_needed,
            recording_data.call_sid,
            False,
        )
    except Exception as exc:
        logger.error(
            "[auto-eval] unable to schedule background task meeting_id=%s error=%s",
            recording_data.call_sid,
            str(exc),
        )

    return result
