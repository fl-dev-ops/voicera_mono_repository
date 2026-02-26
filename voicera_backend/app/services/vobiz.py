"""
Vobiz service for handling Vobiz API operations.
"""

from typing import Dict, Any
from app.config import settings
import httpx
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


async def create_vobiz_application(agent_type: str, answer_url: str) -> Dict[str, Any]:
    """
    Create a Vobiz application via API.

    Args:
        agent_type: Agent type identifier (used as app_name)
        answer_url: Answer URL for the application

    Returns:
        Dict with status, message, and app_id if successful
    """
    try:
        # Validate that Vobiz credentials are configured
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/Account/{settings.VOBIZ_AUTH_ID}/Application/"

        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        # Prepare request body
        payload = {
            "app_name": agent_type,
            "answer_url": answer_url,
            "answer_method": "POST",
        }

        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract app_id from response if available
            app_id = data.get("app_id") or data.get("id") or data.get("application_id")

            logger.info(
                f"Vobiz application created successfully for agent_type: {agent_type}"
            )
            return {
                "status": "success",
                "message": "Vobiz application created successfully",
                "app_id": app_id,
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error creating Vobiz application: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def delete_vobiz_application(application_id: str) -> Dict[str, Any]:
    """
    Delete a Vobiz application via API.

    Args:
        application_id: Vobiz application ID to delete

    Returns:
        Dict with status and message
    """
    try:
        # Validate that Vobiz credentials are configured
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/Account/{settings.VOBIZ_AUTH_ID}/Application/{application_id}/"

        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        }

        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()

            logger.info(f"Vobiz application deleted successfully: {application_id}")
            return {
                "status": "success",
                "message": "Vobiz application deleted successfully",
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error deleting Vobiz application: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def link_number_to_application(
    phone_number: str, application_id: str
) -> Dict[str, Any]:
    """
    Link a phone number to a Vobiz application via API.

    Args:
        phone_number: Phone number to link (e164 format)
        application_id: Vobiz application ID

    Returns:
        Dict with status and message
    """
    try:
        # Validate that Vobiz credentials are configured
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/numbers/{phone_number}/application"

        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        # Prepare request body
        payload = {"application_id": application_id}

        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            logger.info(
                f"Phone number {phone_number} linked to application {application_id} successfully"
            )
            return {
                "status": "success",
                "message": f"Phone number linked to application successfully",
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error linking phone number to application: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def unlink_number_from_application(phone_number: str) -> Dict[str, Any]:
    """
    Unlink a phone number from a Vobiz application via API.

    Args:
        phone_number: Phone number to unlink (e164 format)

    Returns:
        Dict with status and message
    """
    try:
        # Validate that Vobiz credentials are configured
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/numbers/{phone_number}/application"

        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        }

        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()

            logger.info(
                f"Phone number {phone_number} unlinked from application successfully"
            )
            return {
                "status": "success",
                "message": "Phone number unlinked from application successfully",
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error unlinking phone number from application: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


# =============================================================================
# Vobiz Trunk Management (for LiveKit Integration)
# =============================================================================


async def create_trunk(
    name: str,
    trunk_direction: str = "both",
    inbound_destination: str = None,
    trunk_status: str = "enabled",
    secure: bool = False,
) -> Dict[str, Any]:
    """
    Create a Vobiz SIP trunk.

    Args:
        name: Name for the trunk
        trunk_direction: "outbound", "inbound", or "both"
        inbound_destination: SIP URI for inbound calls (e.g., LiveKit SIP URI)
        trunk_status: "enabled" or "disabled"
        secure: Whether to use TLS/SRTP

    Returns:
        Dict with status, trunk_id, sip_domain, etc.
    """
    try:
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/trunks"

        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        payload = {
            "name": name,
            "trunk_direction": trunk_direction,
            "trunk_status": trunk_status,
            "secure": secure,
            "transport": "tls",  # LiveKit requires TLS
        }

        if inbound_destination:
            payload["inbound_destination"] = inbound_destination

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            trunk_id = data.get("trunk_id")
            sip_domain = (
                data.get("trunk_domain") or f"{trunk_id}.sip.vobiz.ai"
                if trunk_id
                else None
            )

            logger.info(f"Vobiz trunk created: {trunk_id}")
            return {
                "status": "success",
                "message": "Vobiz trunk created successfully",
                "trunk_id": trunk_id,
                "sip_domain": sip_domain,
                "trunk_direction": trunk_direction,
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error creating Vobiz trunk: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def add_trunk_credentials(
    trunk_id: str, username: str, password: str
) -> Dict[str, Any]:
    """
    Add credentials to a Vobiz trunk.

    Args:
        trunk_id: The trunk ID to add credentials to
        username: SIP username
        password: SIP password

    Returns:
        Dict with status and credential_uuid
    """
    try:
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/trunks/{trunk_id}/credentials"

        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        payload = {"username": username, "password": password}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            # Handle 204 No Content response
            if response.status_code == 204:
                logger.info(f"Added credentials to trunk {trunk_id}")
                return {
                    "status": "success",
                    "message": "Credentials added successfully",
                    "credential_uuid": None,
                }

            data = response.json()
            credential_uuid = data.get("credential_uuid") or data.get("id")

            logger.info(f"Added credentials to trunk {trunk_id}")
            return {
                "status": "success",
                "message": "Credentials added successfully",
                "credential_uuid": credential_uuid,
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error adding trunk credentials: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def update_trunk_inbound_destination(
    trunk_id: str, inbound_destination: str
) -> Dict[str, Any]:
    """
    Update a Vobiz trunk's inbound destination (for routing to LiveKit).

    Args:
        trunk_id: The trunk ID to update
        inbound_destination: SIP URI to forward inbound calls to (e.g., LiveKit SIP URI)
                            NOTE: Do NOT include "sip:" prefix

    Returns:
        Dict with status and message
    """
    try:
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/trunks/{trunk_id}"

        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        # Remove sip: prefix if present (Vobiz doesn't want it)
        clean_destination = inbound_destination.replace("sip:", "")

        payload = {"inbound_destination": clean_destination}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(url, headers=headers, json=payload)
            response.raise_for_status()

            logger.info(
                f"Updated trunk {trunk_id} inbound destination to {clean_destination}"
            )
            return {
                "status": "success",
                "message": "Inbound destination updated successfully",
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error updating trunk inbound destination: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def delete_trunk(trunk_id: str) -> Dict[str, Any]:
    """
    Delete a Vobiz SIP trunk.

    Args:
        trunk_id: The trunk ID to delete

    Returns:
        Dict with status and message
    """
    try:
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/trunks/{trunk_id}"

        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()

            logger.info(f"Deleted Vobiz trunk {trunk_id}")
            return {"status": "success", "message": "Trunk deleted successfully"}

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error deleting Vobiz trunk: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def link_number_to_trunk(phone_number: str, trunk_id: str) -> Dict[str, Any]:
    """
    Link a phone number to a Vobiz trunk.

    Args:
        phone_number: Phone number to link (e164 format, e.g., +918049280333)
        trunk_id: Vobiz trunk ID to link the number to

    Returns:
        Dict with status and message
    """
    try:
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        # Vobiz uses /numbers/{PHONE_NUMBER}/assign (POST) with trunk_group_id.
        # Keep leading + and URL-encode it (%2B...).
        encoded_phone = quote(phone_number, safe="")
        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/numbers/{encoded_phone}/assign"

        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json",
        }

        payload = {"trunk_group_id": trunk_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            logger.info(f"Phone number {phone_number} assigned to trunk {trunk_id}")
            return {
                "status": "success",
                "message": "Phone number assigned to trunk successfully",
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error assigning phone number to trunk: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}


async def unlink_number_from_trunk(phone_number: str) -> Dict[str, Any]:
    """
    Unlink a phone number from a Vobiz trunk.

    Args:
        phone_number: Phone number to unlink (e164 format, e.g., +918049280333)

    Returns:
        Dict with status and message
    """
    try:
        if not settings.VOBIZ_AUTH_ID or not settings.VOBIZ_AUTH_TOKEN:
            return {
                "status": "fail",
                "message": "Vobiz API credentials are not configured",
            }

        # Vobiz uses /numbers/{PHONE_NUMBER}/assign (DELETE) to unassign.
        encoded_phone = quote(phone_number, safe="")
        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/numbers/{encoded_phone}/assign"

        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()

            logger.info(f"Phone number {phone_number} unlinked from trunk")
            return {
                "status": "success",
                "message": "Phone number unlinked from trunk successfully",
            }

    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
    except Exception as e:
        error_message = f"Error unlinking phone number from trunk: {str(e)}"
        logger.error(error_message)
        return {"status": "fail", "message": error_message}
