"""FastAPI helper server for LiveKit SIP management and outbound call initiation.

This server runs alongside the LiveKit Worker process (main.py).
Exposes an HTTP API for:
  - POST /livekit/sip/inbound-trunk   — create a LiveKit SIP inbound trunk (Vobiz → LiveKit)
  - POST /livekit/sip/outbound-trunk  — create a LiveKit SIP outbound trunk (LiveKit → Vobiz)
  - DELETE /livekit/sip/trunk/{id}    — delete an inbound or outbound trunk
  - POST /livekit/sip/dispatch-rule   — create a dispatch rule (phone number → agent)
  - DELETE /livekit/sip/dispatch-rule/{id} — delete a dispatch rule
  - POST /outbound/call/              — initiate an outbound SIP call via LiveKit
  - GET  /health                      — health check

Inbound calls are routed to the Worker via LiveKit SIP dispatch rules.
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from typing import Optional

from api.backend_utils import fetch_agent_config_from_backend

load_dotenv(override=False)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────


class SIPInboundTrunkRequest(BaseModel):
    """Request body for creating a LiveKit SIP inbound trunk.

    The inbound trunk tells LiveKit how to accept calls arriving from your
    Vobiz SIP domain and which phone numbers belong to this trunk.
    """

    name: str = "Vobiz Inbound Trunk"
    # E.164 phone numbers that belong to this trunk (e.g. ["+918888800000"])
    numbers: list[str]
    # Vobiz SIP credentials (used for digest auth on inbound calls)
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None
    # Optional: restrict which Vobiz SIP server IPs may send calls.
    # Defaults to ["0.0.0.0/0"] so LiveKit accepts INVITEs from any Vobiz server.
    allowed_addresses: Optional[list[str]] = None
    # Vobiz sipAddress domain (e.g. "822ede2f-0dbe-4e05-8474-6ec0272be24e.sip.vobiz.ai").
    # When provided, the Vobiz trunk's inbound_destination will be automatically
    # patched to point at this LiveKit SIP ingress after the trunk is created.
    vobiz_sip_domain: Optional[str] = None


class SIPOutboundTrunkRequest(BaseModel):
    """Request body for creating a LiveKit SIP outbound trunk.

    The outbound trunk tells LiveKit where to send calls that your agents
    initiate (i.e. your Vobiz SIP domain + credentials).
    """

    name: str = "Vobiz Outbound Trunk"
    # Vobiz SIP domain/address (e.g. "sip.vobiz.com" or "your-domain.sip.vobiz.com")
    address: str
    # E.164 caller-ID numbers on this trunk (e.g. ["+918888800000"])
    numbers: list[str]
    auth_username: Optional[str] = None
    auth_password: Optional[str] = None


class SIPDispatchRuleRequest(BaseModel):
    """Request body for creating a LiveKit SIP dispatch rule.

    A dispatch rule maps an inbound phone number to a specific agent.
    Each call to `phone_number` creates a new room whose metadata carries
    `agent_id`, so the Worker knows which agent config to load.
    """

    # The DID/to-number that this rule matches (E.164)
    phone_number: str
    # The agent that should handle calls to this number
    agent_id: str
    # The inbound trunk this rule is attached to
    trunk_id: str
    name: Optional[str] = None


class OutboundCallRequest(BaseModel):
    """Request body for initiating an outbound SIP call."""

    customer_number: str
    agent_id: str
    caller_id: Optional[str] = None
    custom_field: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Shared LiveKit API context helper
# ─────────────────────────────────────────────────────────────────────────────


def _livekit_creds() -> tuple[str, str, str]:
    """Return (url, api_key, api_secret) or raise ValueError if any are missing."""
    url = os.environ.get("LIVEKIT_URL", "")
    key = os.environ.get("LIVEKIT_API_KEY", "")
    secret = os.environ.get("LIVEKIT_API_SECRET", "")
    if not all([url, key, secret]):
        raise ValueError(
            "Missing LiveKit env vars: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET"
        )
    return url, key, secret


# ─────────────────────────────────────────────────────────────────────────────
# SIP trunk helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _create_inbound_trunk(req: SIPInboundTrunkRequest) -> dict:
    """Register a Vobiz SIP inbound trunk with LiveKit.

    After creating the trunk, if `req.vobiz_sip_domain` is provided the
    Vobiz trunk's `inbound_destination` is automatically patched to point at
    this project's LiveKit SIP ingress so inbound calls are forwarded correctly.
    """
    import httpx
    import livekit.api as lk_api
    from livekit.protocol.sip import (
        CreateSIPInboundTrunkRequest,
        SIPInboundTrunkInfo,
    )

    url, key, secret = _livekit_creds()

    # Default to allow all addresses so LiveKit accepts INVITEs from any
    # Vobiz server (required — empty list causes LiveKit to reject all INVITEs).
    effective_allowed = (
        req.allowed_addresses if req.allowed_addresses else ["0.0.0.0/0"]
    )

    trunk_info = SIPInboundTrunkInfo(
        name=req.name,
        numbers=req.numbers,
        allowed_addresses=effective_allowed,
        **({"auth_username": req.auth_username} if req.auth_username else {}),
        **({"auth_password": req.auth_password} if req.auth_password else {}),
    )
    async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
        result = await lk.sip.create_inbound_trunk(
            CreateSIPInboundTrunkRequest(trunk=trunk_info)
        )
    logger.info(f"Created inbound trunk: {result.sip_trunk_id}")

    # ── Auto-patch Vobiz inbound_destination ──────────────────────────────────
    if req.vobiz_sip_domain:
        await _patch_vobiz_inbound_destination(req.vobiz_sip_domain)

    return {"sip_trunk_id": result.sip_trunk_id, "name": result.name}


async def _patch_vobiz_inbound_destination(vobiz_sip_domain: str) -> None:
    """Patch the Vobiz trunk so it forwards inbound calls to our LiveKit SIP ingress.

    Args:
        vobiz_sip_domain: The sipAddress value from the wizard, e.g.
            "822ede2f-0dbe-4e05-8474-6ec0272be24e.sip.vobiz.ai"
    """
    import httpx

    # Derive Vobiz trunk ID: strip ".sip.vobiz.ai" suffix
    VOBIZ_SIP_SUFFIX = ".sip.vobiz.ai"
    if vobiz_sip_domain.endswith(VOBIZ_SIP_SUFFIX):
        vobiz_trunk_id = vobiz_sip_domain[: -len(VOBIZ_SIP_SUFFIX)]
    else:
        # Fallback: use the full domain as-is (handles custom formats)
        vobiz_trunk_id = vobiz_sip_domain

    # Resolve the LiveKit SIP ingress hostname.
    #
    # Prefer the explicit LIVEKIT_SIP_URI env var (e.g. "sip:3fivytj7n7h.sip.livekit.cloud")
    # because the SIP subdomain often differs from the LIVEKIT_URL WebSocket hostname.
    # Fall back to deriving from LIVEKIT_URL only if the env var is not set.
    livekit_sip_uri = os.environ.get("LIVEKIT_SIP_URI", "")
    if livekit_sip_uri:
        # Strip "sip:" prefix if present → "3fivytj7n7h.sip.livekit.cloud"
        livekit_sip_ingress = livekit_sip_uri.removeprefix("sip:")
    else:
        # Fallback: derive from LIVEKIT_URL (may be wrong if SIP subdomain differs)
        livekit_url = os.environ.get("LIVEKIT_URL", "")
        livekit_host = (
            livekit_url.removeprefix("wss://")
            .removeprefix("ws://")
            .removeprefix("https://")
            .removeprefix("http://")
        )
        subdomain = livekit_host.split(".")[0]
        livekit_sip_ingress = f"{subdomain}.sip.livekit.cloud"
        logger.warning(
            "LIVEKIT_SIP_URI not set — derived SIP ingress from LIVEKIT_URL: "
            f"{livekit_sip_ingress}. This may be incorrect if the SIP subdomain differs."
        )

    # Vobiz API credentials
    auth_id = os.environ.get("VOBIZ_AUTH_ID", "")
    auth_token = os.environ.get("VOBIZ_AUTH_TOKEN", "")
    api_base = os.environ.get("VOBIZ_API_BASE", "https://api.vobiz.ai/api/v1")

    if not auth_id or not auth_token:
        logger.warning(
            "VOBIZ_AUTH_ID / VOBIZ_AUTH_TOKEN not set — skipping Vobiz inbound_destination patch"
        )
        return

    patch_url = f"{api_base}/account/{auth_id}/trunks/{vobiz_trunk_id}"
    payload = {"inbound_destination": livekit_sip_ingress}
    headers = {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json",
    }

    logger.info(
        f"Patching Vobiz trunk {vobiz_trunk_id}: inbound_destination={livekit_sip_ingress}"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.put(patch_url, json=payload, headers=headers)
        if resp.status_code not in (200, 204):
            logger.error(
                f"Vobiz PATCH failed: status={resp.status_code} body={resp.text}"
            )
            raise RuntimeError(
                f"Vobiz inbound_destination patch failed ({resp.status_code}): {resp.text}"
            )
    logger.info(
        f"Vobiz trunk {vobiz_trunk_id} inbound_destination set to {livekit_sip_ingress}"
    )


async def _create_outbound_trunk(req: SIPOutboundTrunkRequest) -> dict:
    """Register a Vobiz SIP outbound trunk with LiveKit."""
    import livekit.api as lk_api
    from livekit.protocol.sip import (
        CreateSIPOutboundTrunkRequest,
        SIPOutboundTrunkInfo,
    )

    url, key, secret = _livekit_creds()
    trunk_info = SIPOutboundTrunkInfo(
        name=req.name,
        address=req.address,
        numbers=req.numbers,
        **({"auth_username": req.auth_username} if req.auth_username else {}),
        **({"auth_password": req.auth_password} if req.auth_password else {}),
    )
    async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
        result = await lk.sip.create_outbound_trunk(
            CreateSIPOutboundTrunkRequest(trunk=trunk_info)
        )
    logger.info(f"Created outbound trunk: {result.sip_trunk_id}")
    return {"sip_trunk_id": result.sip_trunk_id, "name": result.name}


async def _delete_trunk(trunk_id: str) -> dict:
    """Delete a LiveKit SIP trunk (inbound or outbound)."""
    import livekit.api as lk_api
    from livekit.protocol.sip import DeleteSIPTrunkRequest

    url, key, secret = _livekit_creds()
    async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
        await lk.sip.delete_trunk(DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))
    logger.info(f"Deleted trunk: {trunk_id}")
    return {"deleted": trunk_id}


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch rule helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _create_dispatch_rule(req: SIPDispatchRuleRequest) -> dict:
    """Create a LiveKit SIP dispatch rule mapping a phone number to an agent.

    Uses SIPDispatchRuleIndividual so each inbound call to `phone_number`
    gets its own room.  A ``RoomAgentDispatch`` is attached via
    ``room_config`` so that LiveKit automatically dispatches the call to
    the worker registered as ``voicera-agent`` (must match the
    ``agent_name`` in ``WorkerOptions``).  Room metadata carries
    ``agent_id`` so the worker knows which agent config to load.
    """
    import json as _json

    import livekit.api as lk_api
    from livekit.protocol.sip import (
        CreateSIPDispatchRuleRequest,
        SIPDispatchRule,
        SIPDispatchRuleIndividual,
        SIPDispatchRuleInfo,
    )

    url, key, secret = _livekit_creds()

    # Agent name must match WorkerOptions(agent_name=...) in main.py
    AGENT_NAME = "voicera-agent"

    rule_name = req.name or f"Agent {req.agent_id} — {req.phone_number}"
    # Room prefix: each call gets a unique room named "<prefix><random>"
    room_prefix = f"call-{req.agent_id}-"

    rule_info = SIPDispatchRuleInfo(
        name=rule_name,
        # metadata is stored on the dispatch rule itself (used for auditing)
        metadata=_json.dumps(
            {"agent_id": req.agent_id, "phone_number": req.phone_number}
        ),
        trunk_ids=[req.trunk_id],
        # Only trigger for calls to this specific number
        inbound_numbers=[req.phone_number],
        rule=SIPDispatchRule(
            dispatch_rule_individual=SIPDispatchRuleIndividual(room_prefix=room_prefix)
        ),
        # These attributes are set on the SIP participant when it joins the room,
        # making agent_id available to the Worker via participant attributes as well.
        attributes={"agent_id": req.agent_id},
    )

    # Attach RoomAgentDispatch so LiveKit dispatches to the correct worker.
    # This mirrors the official Vobiz+LiveKit inbound example.
    rule_info.room_config.CopyFrom(
        lk_api.RoomConfiguration(
            agents=[lk_api.RoomAgentDispatch(agent_name=AGENT_NAME)],
        )
    )

    async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
        result = await lk.sip.create_dispatch_rule(
            CreateSIPDispatchRuleRequest(dispatch_rule=rule_info)
        )

    logger.info(
        f"Created dispatch rule: {result.sip_dispatch_rule_id} "
        f"phone={req.phone_number} agent={req.agent_id}"
    )
    return {
        "sip_dispatch_rule_id": result.sip_dispatch_rule_id,
        "name": result.name,
        "agent_id": req.agent_id,
        "phone_number": req.phone_number,
    }


async def _delete_dispatch_rule(rule_id: str) -> dict:
    """Delete a LiveKit SIP dispatch rule."""
    import livekit.api as lk_api
    from livekit.protocol.sip import DeleteSIPDispatchRuleRequest

    url, key, secret = _livekit_creds()
    async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
        await lk.sip.delete_dispatch_rule(
            DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        )
    logger.info(f"Deleted dispatch rule: {rule_id}")
    return {"deleted": rule_id}


# ─────────────────────────────────────────────────────────────────────────────
# Outbound call helper
# ─────────────────────────────────────────────────────────────────────────────


async def _make_outbound_sip_call(
    customer_number: str,
    agent_id: str,
    caller_id: Optional[str] = None,
) -> dict:
    """Initiate an outbound SIP call via LiveKit.

    LiveKit creates a room, the SIP trunk dials out, and the Worker picks up
    the room to run the agent.

    Room metadata carries the agent_id so the agent entrypoint knows which
    agent config to load.

    The outbound trunk ID is resolved in order:
      1. Per-agent `livekit_outbound_trunk_id` fetched from the backend.
      2. `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` env var (global fallback).

    Returns the LiveKit API response dict.
    """
    import livekit.api as lk_api
    from livekit.protocol.sip import CreateSIPParticipantRequest

    livekit_url = os.environ.get("LIVEKIT_URL", "")
    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")

    if not all([livekit_url, api_key, api_secret]):
        raise ValueError(
            "Missing LiveKit env vars: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET"
        )

    # Resolve outbound trunk: prefer per-agent value, fall back to env var.
    trunk_id = os.environ.get("LIVEKIT_SIP_OUTBOUND_TRUNK_ID", "")
    agent_config = await fetch_agent_config_from_backend(agent_id)
    if agent_config:
        per_agent_trunk = agent_config.get("livekit_outbound_trunk_id", "")
        if per_agent_trunk:
            trunk_id = per_agent_trunk
            logger.info(f"Using per-agent outbound trunk: {trunk_id}")

    if not trunk_id:
        raise ValueError(
            "No outbound SIP trunk configured. Set livekit_outbound_trunk_id on the "
            "agent or LIVEKIT_SIP_OUTBOUND_TRUNK_ID env var."
        )

    # Room name acts as the call SID (must be unique per call)
    import uuid

    room_name = f"call-{uuid.uuid4().hex[:12]}"
    room_metadata = json.dumps({"agent_id": agent_id})

    logger.info(
        f"Outbound SIP call: {customer_number} via trunk={trunk_id} "
        f"room={room_name} agent={agent_id}"
    )

    async with lk_api.LiveKitAPI(
        url=livekit_url,
        api_key=api_key,
        api_secret=api_secret,
    ) as lk:
        # Ensure room exists with metadata before dialing
        await lk.room.create_room(
            lk_api.CreateRoomRequest(
                name=room_name,
                metadata=room_metadata,
            )
        )

        response = await lk.sip.create_sip_participant(
            CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=customer_number,
                room_name=room_name,
                participant_identity=f"sip-{customer_number}",
                participant_name=customer_number,
                **({"sip_number": caller_id} if caller_id else {}),
            )
        )

    logger.info(f"Outbound call initiated: participant={response.participant_identity}")
    return {
        "room_name": room_name,
        "participant_identity": response.participant_identity,
        "sip_call_id": getattr(response, "sip_call_id", None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Voicera Voice Server",
    description="LiveKit SIP outbound call API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"service": "Voicera Voice Server (LiveKit)", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ─────────────────────────────────────────────────────────────────────────────
# LiveKit SIP management endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/livekit/sip/inbound-trunk")
async def create_inbound_trunk(request: SIPInboundTrunkRequest):
    """Create a LiveKit SIP inbound trunk from Vobiz credentials.

    Call this once per Vobiz account to register the inbound trunk.
    Save the returned `sip_trunk_id` — you need it when creating dispatch rules.
    """
    try:
        result = await _create_inbound_trunk(request)
        return JSONResponse(status_code=201, content={"status": "success", **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create inbound trunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/livekit/sip/outbound-trunk")
async def create_outbound_trunk(request: SIPOutboundTrunkRequest):
    """Create a LiveKit SIP outbound trunk from Vobiz credentials.

    Call this once per Vobiz account to register the outbound trunk.
    Save the returned `sip_trunk_id` as LIVEKIT_SIP_OUTBOUND_TRUNK_ID.
    """
    try:
        result = await _create_outbound_trunk(request)
        return JSONResponse(status_code=201, content={"status": "success", **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create outbound trunk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/livekit/sip/trunk/{trunk_id}")
async def delete_trunk(trunk_id: str):
    """Delete a LiveKit SIP trunk (inbound or outbound)."""
    try:
        result = await _delete_trunk(trunk_id)
        return JSONResponse(status_code=200, content={"status": "success", **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete trunk {trunk_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/livekit/sip/dispatch-rule")
async def create_dispatch_rule(request: SIPDispatchRuleRequest):
    """Create a LiveKit SIP dispatch rule mapping a phone number to an agent.

    Call this every time a phone number is assigned to an agent.
    Save the returned `sip_dispatch_rule_id` on the agent record.
    """
    try:
        result = await _create_dispatch_rule(request)
        return JSONResponse(status_code=201, content={"status": "success", **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create dispatch rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/livekit/sip/dispatch-rule/{rule_id}")
async def delete_dispatch_rule(rule_id: str):
    """Delete a LiveKit SIP dispatch rule."""
    try:
        result = await _delete_dispatch_rule(rule_id)
        return JSONResponse(status_code=200, content={"status": "success", **result})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete dispatch rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/outbound/call/")
async def make_outbound_call(request: OutboundCallRequest):
    """Initiate an outbound SIP call via LiveKit."""
    try:
        result = await _make_outbound_sip_call(
            customer_number=request.customer_number,
            agent_id=request.agent_id,
            caller_id=request.caller_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Outbound call initiated",
                "customer_number": request.customer_number,
                "agent_id": request.agent_id,
                **result,
            },
        )
    except ValueError as e:
        logger.error(f"Bad request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Outbound call failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def run_server(host: str = "0.0.0.0", port: int = 7860, log_level: str = "info"):
    """Run the FastAPI helper server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    run_server()
