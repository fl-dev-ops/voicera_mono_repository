"""
LiveKit SIP routes for trunk management, dispatch rules, and outbound calls.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.services import livekit_service
from app.auth import get_current_user

router = APIRouter(prefix="/livekit/sip", tags=["livekit"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────


class SIPInboundTrunkRequest(BaseModel):
    """Request body for creating a LiveKit SIP inbound trunk."""

    name: str = "Vobiz Inbound Trunk"
    numbers: List[str]
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    allowed_addresses: Optional[List[str]] = None
    vobiz_sip_domain: Optional[str] = None


class SIPOutboundTrunkRequest(BaseModel):
    """Request body for creating a LiveKit SIP outbound trunk."""

    name: str = "Vobiz Outbound Trunk"
    address: str
    numbers: List[str]
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None


class SIPDispatchRuleRequest(BaseModel):
    """Request body for creating a LiveKit SIP dispatch rule."""

    phone_number: str
    agent_id: str
    trunk_id: str
    name: Optional[str] = None


class OutboundCallRequest(BaseModel):
    """Request body for initiating an outbound SIP call."""

    customer_number: str
    agent_id: str
    caller_id: Optional[str] = None
    custom_field: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# LiveKit SIP endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/inbound-trunk", status_code=status.HTTP_201_CREATED)
async def create_inbound_trunk_endpoint(
    request: SIPInboundTrunkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Create a LiveKit SIP inbound trunk.

    Protected endpoint - requires JWT authentication.
    """
    result = await livekit_service.create_inbound_trunk(
        name=request.name,
        numbers=request.numbers,
        auth_username=request.auth_username,
        auth_password=request.auth_password,
        allowed_addresses=request.allowed_addresses,
        vobiz_sip_domain=request.vobiz_sip_domain,
    )

    if result["status"] == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
        )

    return result


@router.post("/outbound-trunk", status_code=status.HTTP_201_CREATED)
async def create_outbound_trunk_endpoint(
    request: SIPOutboundTrunkRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Create a LiveKit SIP outbound trunk.

    Protected endpoint - requires JWT authentication.
    """
    result = await livekit_service.create_outbound_trunk(
        name=request.name,
        address=request.address,
        numbers=request.numbers,
        auth_username=request.auth_username,
        auth_password=request.auth_password,
    )

    if result["status"] == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
        )

    return result


@router.delete("/trunk/{trunk_id}")
async def delete_trunk_endpoint(
    trunk_id: str, current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a LiveKit SIP trunk (inbound or outbound).

    Protected endpoint - requires JWT authentication.
    """
    result = await livekit_service.delete_trunk(trunk_id)

    if result["status"] == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
        )

    return result


@router.post("/dispatch-rule", status_code=status.HTTP_201_CREATED)
async def create_dispatch_rule_endpoint(
    request: SIPDispatchRuleRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Create a LiveKit SIP dispatch rule mapping a phone number to an agent.

    Protected endpoint - requires JWT authentication.
    """
    result = await livekit_service.create_dispatch_rule(
        phone_number=request.phone_number,
        agent_id=request.agent_id,
        trunk_id=request.trunk_id,
        name=request.name,
    )

    if result["status"] == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
        )

    return result


@router.delete("/dispatch-rule/{rule_id}")
async def delete_dispatch_rule_endpoint(
    rule_id: str, current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a LiveKit SIP dispatch rule.

    Protected endpoint - requires JWT authentication.
    """
    result = await livekit_service.delete_dispatch_rule(rule_id)

    if result["status"] == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Outbound call endpoints
# ─────────────────────────────────────────────────────────────────────────────


outbound_router = APIRouter(prefix="/outbound", tags=["outbound"])


@outbound_router.post("/call/", status_code=status.HTTP_201_CREATED)
async def make_outbound_call_endpoint(
    request: OutboundCallRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Initiate an outbound SIP call via LiveKit.

    Protected endpoint - requires JWT authentication.
    """
    result = await livekit_service.make_outbound_sip_call(
        customer_number=request.customer_number,
        agent_id=request.agent_id,
        caller_id=request.caller_id,
        custom_field=request.custom_field,
    )

    if result["status"] == "fail":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"]
        )

    return result
