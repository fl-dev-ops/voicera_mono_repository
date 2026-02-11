"""Public evaluation report endpoints."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from app.services.evaluation_service import (
    generate_evaluation_from_meeting,
    get_or_generate_evaluation,
)

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/{meeting_id}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def generate_evaluation(meeting_id: str):
    """
    Generate evaluation for a meeting and persist report.

    Public / unauthenticated by design for shareable report generation.
    """
    result = generate_evaluation_from_meeting(meeting_id)
    if isinstance(result, dict) and result.get("status") == "fail":
        raise HTTPException(
            status_code=int(result.get("status_code", 400)),
            detail=result.get("message", "Failed to generate evaluation"),
        )
    return result


@router.get("/{meeting_id}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_evaluation(meeting_id: str):
    """
    Fetch evaluation for a meeting.

    If report is not already generated, generate on-demand.
    Public / unauthenticated to support direct frontend URL access.
    """
    result = get_or_generate_evaluation(meeting_id)
    if isinstance(result, dict) and result.get("status") == "fail":
        raise HTTPException(
            status_code=int(result.get("status_code", 400)),
            detail=result.get("message", "Failed to fetch evaluation"),
        )
    return result
