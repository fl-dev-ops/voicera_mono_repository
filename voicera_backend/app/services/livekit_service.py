"""
LiveKit service for handling SIP trunk management, dispatch rules, and outbound calls.
"""

import json
import logging
from typing import Dict, Any, Optional

import livekit.api as lk_api
from livekit.protocol.sip import (
    CreateSIPInboundTrunkRequest,
    CreateSIPOutboundTrunkRequest,
    CreateSIPDispatchRuleRequest,
    DeleteSIPTrunkRequest,
    DeleteSIPDispatchRuleRequest,
    SIPInboundTrunkInfo,
    SIPOutboundTrunkInfo,
    SIPDispatchRuleInfo,
    SIPDispatchRule,
    SIPDispatchRuleIndividual,
)
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _livekit_creds() -> tuple[str, str, str]:
    """Return (url, api_key, api_secret) or raise ValueError if any are missing."""
    url = settings.LIVEKIT_URL
    key = settings.LIVEKIT_API_KEY
    secret = settings.LIVEKIT_API_SECRET
    if not all([url, key, secret]):
        raise ValueError(
            "Missing LiveKit env vars: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET"
        )
    return url, key, secret


async def create_inbound_trunk(
    name: str,
    numbers: list[str],
    auth_username: Optional[str] = None,
    auth_password: Optional[str] = None,
    allowed_addresses: Optional[list[str]] = None,
    vobiz_sip_domain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a LiveKit SIP inbound trunk.

    Args:
        name: Name for the trunk
        numbers: List of E.164 phone numbers
        auth_username: Optional SIP auth username
        auth_password: Optional SIP auth password
        allowed_addresses: List of allowed IP addresses (default: ["0.0.0.0/0"])
        vobiz_sip_domain: Optional Vobiz SIP domain to auto-patch inbound destination

    Returns:
        Dict with status, message, and trunk_id
    """
    try:
        url, key, secret = _livekit_creds()

        # Default to allow all addresses
        effective_allowed = allowed_addresses if allowed_addresses else ["0.0.0.0/0"]

        trunk_info = SIPInboundTrunkInfo(
            name=name,
            numbers=numbers,
            allowed_addresses=effective_allowed,
            **({"auth_username": auth_username} if auth_username else {}),
            **({"auth_password": auth_password} if auth_password else {}),
        )

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            result = await lk.sip.create_inbound_trunk(
                CreateSIPInboundTrunkRequest(trunk=trunk_info)
            )

        logger.info(f"Created inbound trunk: {result.sip_trunk_id}")

        # Note: Vobiz patching requires a Vobiz trunk to exist first.
        # For now, we skip this since Vobiz integration requires additional setup.
        # The LiveKit trunk is created successfully and can receive calls.

        return {
            "status": "success",
            "message": "Inbound trunk created successfully",
            "sip_trunk_id": result.sip_trunk_id,
            "name": result.name,
        }

    except ValueError as e:
        return {"status": "fail", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to create inbound trunk: {e}")
        return {"status": "fail", "message": f"Error creating inbound trunk: {str(e)}"}


async def create_outbound_trunk(
    name: str,
    address: str,
    numbers: list[str],
    auth_username: Optional[str] = None,
    auth_password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a LiveKit SIP outbound trunk.

    Args:
        name: Name for the trunk
        address: SIP address (e.g., sip.vobiz.com)
        numbers: List of E.164 caller-ID numbers
        auth_username: Optional SIP auth username
        auth_password: Optional SIP auth password

    Returns:
        Dict with status, message, and trunk_id
    """
    try:
        url, key, secret = _livekit_creds()

        trunk_info = SIPOutboundTrunkInfo(
            name=name,
            address=address,
            numbers=numbers,
            **({"auth_username": auth_username} if auth_username else {}),
            **({"auth_password": auth_password} if auth_password else {}),
        )

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            result = await lk.sip.create_outbound_trunk(
                CreateSIPOutboundTrunkRequest(trunk=trunk_info)
            )

        logger.info(f"Created outbound trunk: {result.sip_trunk_id}")

        return {
            "status": "success",
            "message": "Outbound trunk created successfully",
            "sip_trunk_id": result.sip_trunk_id,
            "name": result.name,
        }

    except ValueError as e:
        return {"status": "fail", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to create outbound trunk: {e}")
        return {"status": "fail", "message": f"Error creating outbound trunk: {str(e)}"}


async def delete_trunk(trunk_id: str) -> Dict[str, Any]:
    """
    Delete a LiveKit SIP trunk (inbound or outbound).

    Args:
        trunk_id: The SIP trunk ID to delete

    Returns:
        Dict with status and message
    """
    try:
        url, key, secret = _livekit_creds()

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            await lk.sip.delete_trunk(DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))

        logger.info(f"Deleted trunk: {trunk_id}")

        return {
            "status": "success",
            "message": f"Trunk {trunk_id} deleted successfully",
        }

    except ValueError as e:
        return {"status": "fail", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to delete trunk {trunk_id}: {e}")
        return {"status": "fail", "message": f"Error deleting trunk: {str(e)}"}


async def create_dispatch_rule(
    phone_number: str,
    agent_id: str,
    trunk_id: str,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a LiveKit SIP dispatch rule mapping a phone number to an agent.

    Args:
        phone_number: E.164 phone number
        agent_id: Agent identifier
        trunk_id: Inbound trunk ID
        name: Optional rule name

    Returns:
        Dict with status, message, and rule_id
    """
    try:
        import uuid

        url, key, secret = _livekit_creds()

        # Agent name from config
        agent_name = settings.LIVEKIT_AGENT_NAME

        rule_name = name or f"Agent {agent_id} — {phone_number}"
        room_prefix = "call-"

        rule_info = SIPDispatchRuleInfo(
            name=rule_name,
            metadata=json.dumps({"agent_id": agent_id, "phone_number": phone_number}),
            trunk_ids=[trunk_id],
            rule=SIPDispatchRule(
                dispatch_rule_individual=SIPDispatchRuleIndividual(
                    room_prefix=room_prefix
                )
            ),
            attributes={"agent_id": agent_id},
        )

        # Attach RoomAgentDispatch for agent dispatch
        rule_info.room_config.CopyFrom(
            lk_api.RoomConfiguration(
                agents=[lk_api.RoomAgentDispatch(agent_name=agent_name)]
            )
        )

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            result = await lk.sip.create_dispatch_rule(
                CreateSIPDispatchRuleRequest(dispatch_rule=rule_info)
            )

        logger.info(
            f"Created dispatch rule: {result.sip_dispatch_rule_id} "
            f"phone={phone_number} agent={agent_id}"
        )

        return {
            "status": "success",
            "message": "Dispatch rule created successfully",
            "sip_dispatch_rule_id": result.sip_dispatch_rule_id,
            "name": result.name,
            "agent_id": agent_id,
            "phone_number": phone_number,
        }

    except ValueError as e:
        return {"status": "fail", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to create dispatch rule: {e}")
        return {"status": "fail", "message": f"Error creating dispatch rule: {str(e)}"}


async def delete_dispatch_rule(rule_id: str) -> Dict[str, Any]:
    """
    Delete a LiveKit SIP dispatch rule.

    Args:
        rule_id: The SIP dispatch rule ID to delete

    Returns:
        Dict with status and message
    """
    try:
        url, key, secret = _livekit_creds()

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            await lk.sip.delete_dispatch_rule(
                DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
            )

        logger.info(f"Deleted dispatch rule: {rule_id}")

        return {
            "status": "success",
            "message": f"Dispatch rule {rule_id} deleted successfully",
        }

    except ValueError as e:
        return {"status": "fail", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to delete dispatch rule {rule_id}: {e}")
        return {"status": "fail", "message": f"Error deleting dispatch rule: {str(e)}"}


async def make_outbound_sip_call(
    customer_number: str,
    agent_id: str,
    caller_id: Optional[str] = None,
    custom_field: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Initiate an outbound SIP call via LiveKit SIP Participant.

    This uses the create_sip_participant API which:
    1. Creates a call via Vobiz trunk
    2. When person answers, they join the LiveKit room as participant
    3. Your AI agent joins the same room

    Args:
        customer_number: The phone number to call (E.164 format)
        agent_id: The agent ID to use for the call
        caller_id: Optional caller ID number
        custom_field: Optional custom metadata

    Returns:
        Dict with status, message, and room_name
    """
    import uuid

    # Validate agent exists before dispatching
    from app.services.agent_service import fetch_agent_config_by_id

    agent = fetch_agent_config_by_id(agent_id)
    if not agent:
        return {"status": "fail", "message": f"Agent {agent_id} not found"}

    # Check agent has outbound trunk configured
    outbound_trunk_id = agent.get("livekit_outbound_trunk_id")
    if not outbound_trunk_id:
        return {
            "status": "fail",
            "message": f"Agent {agent_id} does not have an outbound trunk configured",
        }

    try:
        url, key, secret = _livekit_creds()

        # Room name acts as the call SID
        room_name = f"call-{uuid.uuid4().hex[:12]}"

        # Metadata passed to the agent entrypoint
        dispatch_metadata = json.dumps(
            {
                "phone_number": customer_number,
                "agent_id": agent_id,
                **({"caller_id": caller_id} if caller_id else {}),
                **({"custom_field": custom_field} if custom_field else {}),
            }
        )

        agent_name = settings.LIVEKIT_AGENT_NAME
        logger.info(
            f"Outbound call: dispatching agent={agent_name} to room={room_name} "
            f"for {customer_number} (agent_id={agent_id})"
        )

        async with lk_api.LiveKitAPI(url=url, api_key=key, api_secret=secret) as lk:
            await lk.agent_dispatch.create_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room_name,
                    metadata=dispatch_metadata,
                )
            )

        logger.info(
            f"Agent dispatched to room={room_name} — agent will dial {customer_number}"
        )

        return {
            "status": "success",
            "message": "Outbound call initiated",
            "room_name": room_name,
            "agent_id": agent_id,
            "customer_number": customer_number,
        }

    except ValueError as e:
        return {"status": "fail", "message": str(e)}
    except Exception as e:
        logger.error(f"Failed to initiate outbound call: {e}")
        return {
            "status": "fail",
            "message": f"Error initiating outbound call: {str(e)}",
        }


async def _patch_vobiz_inbound_destination(vobiz_sip_domain: str) -> None:
    """
    Patch the Vobiz trunk so it forwards inbound calls to our LiveKit SIP ingress.

    Args:
        vobiz_sip_domain: The sipAddress value (e.g., "xxx.sip.vobiz.ai")
    """
    # Derive Vobiz trunk ID: strip ".sip.vobiz.ai" suffix
    VOBIZ_SIP_SUFFIX = ".sip.vobiz.ai"
    if vobiz_sip_domain.endswith(VOBIZ_SIP_SUFFIX):
        vobiz_trunk_id = vobiz_sip_domain[: -len(VOBIZ_SIP_SUFFIX)]
    else:
        vobiz_trunk_id = vobiz_sip_domain

    # Resolve LiveKit SIP ingress hostname
    if settings.LIVEKIT_SIP_URI:
        livekit_sip_ingress = settings.LIVEKIT_SIP_URI.removeprefix("sip:")
    else:
        # Fallback: derive from LIVEKIT_URL
        livekit_url = settings.LIVEKIT_URL
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
    if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
        logger.warning(
            "VOBIZ_AUTH_ID / VOBIZ_AUTH_TOKEN not set — skipping Vobiz inbound_destination patch"
        )
        return

    patch_url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/trunks/{vobiz_trunk_id}"
    payload = {"inbound_destination": livekit_sip_ingress}
    headers = {
        "X-Auth-ID": settings.VOBIZ_AUTH_ID,
        "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json",
    }

    logger.info(
        f"Patching Vobiz trunk {vobiz_trunk_id}: inbound_destination={livekit_sip_ingress}"
    )

    try:
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
    except Exception as e:
        logger.error(f"Failed to patch Vobiz inbound destination: {e}")
        raise


async def delete_agent_resources(
    dispatch_rule_id: Optional[str] = None,
    inbound_trunk_id: Optional[str] = None,
    outbound_trunk_id: Optional[str] = None,
    vobiz_trunk_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Delete all LiveKit and Vobiz resources associated with an agent.

    Args:
        dispatch_rule_id: LiveKit dispatch rule ID to delete
        inbound_trunk_id: LiveKit inbound trunk ID to delete
        outbound_trunk_id: LiveKit outbound trunk ID to delete
        vobiz_trunk_id: Vobiz trunk ID to delete

    Returns:
        Dict with status and details of what was deleted
    """
    deleted = []
    failed = []

    # 1. Delete LiveKit Dispatch Rule
    if dispatch_rule_id:
        try:
            result = await delete_dispatch_rule(dispatch_rule_id)
            if result.get("status") == "success":
                deleted.append(f"LiveKit dispatch rule: {dispatch_rule_id}")
            else:
                failed.append(
                    f"Dispatch rule {dispatch_rule_id}: {result.get('message')}"
                )
        except Exception as e:
            failed.append(f"Dispatch rule {dispatch_rule_id}: {str(e)}")

    # 2. Delete LiveKit Inbound Trunk
    if inbound_trunk_id:
        try:
            result = await delete_trunk(inbound_trunk_id)
            if result.get("status") == "success":
                deleted.append(f"LiveKit inbound trunk: {inbound_trunk_id}")
            else:
                failed.append(
                    f"Inbound trunk {inbound_trunk_id}: {result.get('message')}"
                )
        except Exception as e:
            failed.append(f"Inbound trunk {inbound_trunk_id}: {str(e)}")

    # 3. Delete LiveKit Outbound Trunk
    if outbound_trunk_id:
        try:
            result = await delete_trunk(outbound_trunk_id)
            if result.get("status") == "success":
                deleted.append(f"LiveKit outbound trunk: {outbound_trunk_id}")
            else:
                failed.append(
                    f"Outbound trunk {outbound_trunk_id}: {result.get('message')}"
                )
        except Exception as e:
            failed.append(f"Outbound trunk {outbound_trunk_id}: {str(e)}")

    # 4. Delete Vobiz Trunk
    if vobiz_trunk_id:
        try:
            await _delete_vobiz_trunk(vobiz_trunk_id)
            deleted.append(f"Vobiz trunk: {vobiz_trunk_id}")
        except Exception as e:
            failed.append(f"Vobiz trunk {vobiz_trunk_id}: {str(e)}")

    if failed:
        return {
            "status": "partial",
            "message": "Some resources failed to delete",
            "deleted": deleted,
            "failed": failed,
        }

    return {
        "status": "success",
        "message": "All resources deleted successfully",
        "deleted": deleted,
    }


async def _delete_vobiz_trunk(vobiz_trunk_id: str) -> None:
    """Delete a Vobiz trunk via API."""
    if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
        logger.warning(
            "VOBIZ_AUTH_ID / VOBIZ_AUTH_TOKEN not set — skipping Vobiz trunk deletion"
        )
        return

    delete_url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/trunks/{vobiz_trunk_id}"
    headers = {
        "X-Auth-ID": settings.VOBIZ_AUTH_ID,
        "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
    }

    logger.info(f"Deleting Vobiz trunk: {vobiz_trunk_id}")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(delete_url, headers=headers)
        if resp.status_code not in (200, 204):
            logger.error(
                f"Vobiz delete failed: status={resp.status_code} body={resp.text}"
            )
            raise RuntimeError(f"Failed to delete Vobiz trunk: {resp.text}")

    logger.info(f"Vobiz trunk deleted: {vobiz_trunk_id}")
