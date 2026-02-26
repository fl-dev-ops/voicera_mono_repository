"""
WhatsApp messaging service using Twilio API.

Handles sending WhatsApp messages and logging all messages to MongoDB.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.config import settings
from app.database import get_database
import logging

logger = logging.getLogger(__name__)


def _get_twilio_client() -> Optional[Client]:
    """Get Twilio client, returns None if not configured."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured")
        return None
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _normalize_whatsapp_number(phone: str) -> str:
    """Ensure phone number is in whatsapp:+XXXXXXXXXXX format."""
    phone = phone.strip()
    if phone.startswith("whatsapp:"):
        return phone
    # Strip non-digit except leading +
    if phone.startswith("+"):
        digits = "+" + "".join(ch for ch in phone[1:] if ch.isdigit())
    else:
        digits = "".join(ch for ch in phone if ch.isdigit())
        # Add country code if 10-digit Indian number
        if len(digits) == 10:
            digits = "+91" + digits
        elif not digits.startswith("+"):
            digits = "+" + digits
    return f"whatsapp:{digits}"


def send_whatsapp_message(
    *,
    to: str,
    body: str,
    meeting_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a WhatsApp message via Twilio and log it to MongoDB.

    Args:
        to: Recipient phone number (E.164 or whatsapp: prefixed)
        body: Message text
        meeting_id: Optional meeting ID to associate with
        agent_type: Optional agent type for context
        org_id: Optional organization ID

    Returns:
        Dict with status, twilio_sid, and message details
    """
    db = get_database()
    wa_collection = db["WhatsAppMessages"]
    created_at = datetime.utcnow().isoformat()

    to_normalized = _normalize_whatsapp_number(to)

    # Build log record
    log_record = {
        "to": to_normalized,
        "from": settings.TWILIO_WHATSAPP_FROM,
        "body": body,
        "meeting_id": meeting_id,
        "agent_type": agent_type,
        "org_id": org_id,
        "created_at": created_at,
        "status": "pending",
        "twilio_sid": None,
        "error": None,
    }

    client = _get_twilio_client()
    if not client:
        log_record["status"] = "failed"
        log_record["error"] = "Twilio credentials not configured"
        wa_collection.insert_one(log_record)
        return {
            "status": "failed",
            "error": "Twilio credentials not configured",
            "to": to_normalized,
            "body": body,
            "created_at": created_at,
        }

    try:
        message = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=to_normalized,
            body=body,
        )

        log_record["status"] = "sent"
        log_record["twilio_sid"] = message.sid
        wa_collection.insert_one(log_record)

        logger.info(f"✅ WhatsApp message sent to {to_normalized} (SID: {message.sid})")

        return {
            "status": "sent",
            "twilio_sid": message.sid,
            "to": to_normalized,
            "body": body,
            "meeting_id": meeting_id,
            "agent_type": agent_type,
            "org_id": org_id,
            "created_at": created_at,
        }

    except TwilioRestException as e:
        log_record["status"] = "failed"
        log_record["error"] = str(e)
        wa_collection.insert_one(log_record)

        logger.error(f"❌ Twilio error sending WhatsApp to {to_normalized}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "to": to_normalized,
            "body": body,
            "created_at": created_at,
        }

    except Exception as e:
        log_record["status"] = "failed"
        log_record["error"] = str(e)
        wa_collection.insert_one(log_record)

        logger.error(f"❌ Error sending WhatsApp to {to_normalized}: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "to": to_normalized,
            "body": body,
            "created_at": created_at,
        }


def get_message_history(
    *,
    org_id: Optional[str] = None,
    meeting_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
) -> List[Dict[str, Any]]:
    """
    Fetch WhatsApp message history from MongoDB.

    Args:
        org_id: Filter by organization ID
        meeting_id: Filter by meeting ID
        limit: Max number of records to return
        skip: Number of records to skip (pagination)

    Returns:
        List of message records
    """
    db = get_database()
    wa_collection = db["WhatsAppMessages"]

    query: Dict[str, Any] = {}
    if org_id:
        query["org_id"] = org_id
    if meeting_id:
        query["meeting_id"] = meeting_id

    cursor = (
        wa_collection.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    return list(cursor)


def send_post_call_notification(
    *,
    to: str,
    meeting_id: str,
    agent_type: str,
    duration: Optional[float] = None,
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a post-call WhatsApp notification to the student.

    Args:
        to: Student's phone number
        meeting_id: Call meeting ID
        agent_type: Agent name/type
        duration: Call duration in seconds
        org_id: Organization ID

    Returns:
        Send result dict
    """
    duration_str = ""
    if duration:
        mins = int(duration) // 60
        secs = int(duration) % 60
        if mins > 0:
            duration_str = f"\nDuration: {mins}m {secs}s"
        else:
            duration_str = f"\nDuration: {secs}s"

    body = (
        f"Hi! Thanks for your call with {agent_type}."
        f"{duration_str}"
        f"\nCall ID: {meeting_id}"
    )

    return send_whatsapp_message(
        to=to,
        body=body,
        meeting_id=meeting_id,
        agent_type=agent_type,
        org_id=org_id,
    )
