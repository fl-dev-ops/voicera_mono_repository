"""Screening results endpoints for Kavya screening agent."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user, verify_api_key
from app.database import get_database
from app.models.schemas import ScreeningResultCreate, ScreeningResultResponse

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screening-results", tags=["screening"])


# ============================================================================
# Bot Endpoint (API Key Authentication)
# ============================================================================


@router.post(
    "", response_model=ScreeningResultResponse, status_code=status.HTTP_201_CREATED
)
async def create_screening_result(
    data: ScreeningResultCreate,
    _: bool = Depends(verify_api_key),
):
    """
    Create or update a screening result (service-to-service endpoint).

    Requires X-API-Key header for authentication.
    Uses upsert on meeting_id so re-calling for the same meeting updates
    instead of duplicating.
    """
    try:
        db = get_database()
        now = datetime.now(timezone.utc).isoformat()

        doc = data.model_dump()
        doc["updated_at"] = now

        db["ScreeningResults"].update_one(
            {"meeting_id": data.meeting_id},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

        # Fetch the saved document to return
        saved = db["ScreeningResults"].find_one({"meeting_id": data.meeting_id})
        if saved:
            saved.pop("_id", None)
        return saved

    except Exception as e:
        logger.error(f"Error creating screening result: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create screening result: {str(e)}",
        )


# ============================================================================
# Frontend Endpoints (User JWT Authentication)
# ============================================================================


@router.get("", response_model=List[ScreeningResultResponse])
async def list_screening_results(
    outcome: Optional[str] = Query(
        None, description="Filter by outcome (QUALIFIED, NEEDS_PREP, FOLLOW_UP)"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of records to return"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    List screening results for the current user's organization (protected endpoint).

    Results are sorted by created_at descending (newest first).
    Optionally filter by outcome.
    """
    try:
        db = get_database()
        org_id = current_user["org_id"]

        query: Dict[str, Any] = {"org_id": org_id}
        if outcome:
            query["outcome"] = outcome

        cursor = (
            db["ScreeningResults"]
            .find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        results = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)

        return results

    except Exception as e:
        logger.error(f"Error listing screening results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list screening results: {str(e)}",
        )


@router.get("/{meeting_id}", response_model=ScreeningResultResponse)
async def get_screening_result(
    meeting_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get a single screening result by meeting_id (protected endpoint).

    Only returns results belonging to the current user's organization.
    """
    try:
        db = get_database()
        org_id = current_user["org_id"]

        doc = db["ScreeningResults"].find_one(
            {"meeting_id": meeting_id, "org_id": org_id}
        )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Screening result not found for meeting_id: {meeting_id}",
            )

        doc.pop("_id", None)
        return doc

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting screening result: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get screening result: {str(e)}",
        )
