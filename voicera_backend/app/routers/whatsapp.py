"""
WhatsApp messaging API routes.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Dict, Any, List, Optional

from app.models.schemas import WhatsAppSendRequest, WhatsAppMessageResponse
from app.services import whatsapp_service
from app.auth import get_current_user, verify_api_key

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ============================================================================
# Bot Endpoints (API Key Authentication - used by voice server)
# ============================================================================


@router.post("/send/internal", response_model=Dict[str, Any])
async def send_whatsapp_internal(
    request: WhatsAppSendRequest,
    _: bool = Depends(verify_api_key),
):
    """
    Send a WhatsApp message (bot/internal endpoint).

    Used by the voice server to send post-call notifications.
    Requires X-API-Key header for authentication.
    """
    result = whatsapp_service.send_whatsapp_message(
        to=request.to,
        body=request.body,
        meeting_id=request.meeting_id,
        agent_type=request.agent_type,
        org_id=request.org_id,
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "Failed to send WhatsApp message"),
        )

    return result


@router.post("/notify/post-call", response_model=Dict[str, Any])
async def send_post_call_notification(
    to: str,
    meeting_id: str,
    agent_type: str,
    duration: Optional[float] = None,
    org_id: Optional[str] = None,
    _: bool = Depends(verify_api_key),
):
    """
    Send a post-call notification to the student (bot endpoint).

    Requires X-API-Key header for authentication.
    """
    result = whatsapp_service.send_post_call_notification(
        to=to,
        meeting_id=meeting_id,
        agent_type=agent_type,
        duration=duration,
        org_id=org_id,
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "Failed to send post-call notification"),
        )

    return result


# ============================================================================
# Frontend Endpoints (User JWT Authentication)
# ============================================================================


@router.post("/send", response_model=Dict[str, Any])
async def send_whatsapp_message(
    request: WhatsAppSendRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Send a WhatsApp message (frontend endpoint).

    Requires JWT Bearer token for authentication.
    """
    # Use org_id from the authenticated user if not provided
    org_id = request.org_id or current_user.get("org_id")

    result = whatsapp_service.send_whatsapp_message(
        to=request.to,
        body=request.body,
        meeting_id=request.meeting_id,
        agent_type=request.agent_type,
        org_id=org_id,
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("error", "Failed to send WhatsApp message"),
        )

    return result


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_whatsapp_history(
    current_user: Dict[str, Any] = Depends(get_current_user),
    meeting_id: Optional[str] = Query(None, description="Filter by meeting ID"),
    limit: int = Query(50, ge=1, le=200, description="Max records to return"),
    skip: int = Query(0, ge=0, description="Records to skip for pagination"),
):
    """
    Get WhatsApp message history for the user's organization.

    Requires JWT Bearer token for authentication.
    """
    org_id = current_user.get("org_id")

    messages = whatsapp_service.get_message_history(
        org_id=org_id,
        meeting_id=meeting_id,
        limit=limit,
        skip=skip,
    )

    return messages


@router.get("/history/{meeting_id}", response_model=List[Dict[str, Any]])
async def get_whatsapp_history_by_meeting(
    meeting_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get WhatsApp messages for a specific meeting/call.

    Requires JWT Bearer token for authentication.
    """
    messages = whatsapp_service.get_message_history(
        org_id=current_user.get("org_id"),
        meeting_id=meeting_id,
    )

    return messages
