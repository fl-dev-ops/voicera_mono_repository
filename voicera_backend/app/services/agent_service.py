"""
Agent service for handling agent-related database operations.
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.database import get_database
from app.models.schemas import AgentConfigCreate, AgentConfigUpdate
from app.services import livekit_service
from app.services import vobiz as vobiz_service
from app.config import settings
import logging
import string

logger = logging.getLogger(__name__)


def create_agent(agent_data: AgentConfigCreate) -> Dict[str, Any]:
    """
    Create a new agent type for a given org.

    Args:
        agent_data: Agent creation data

    Returns:
        Dict with status and message
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]

        # Check if agent_type already exists for this organization
        existing_agent = agent_table.find_one(
            {"agent_type": agent_data.agent_type, "org_id": agent_data.org_id}
        )
        if existing_agent:
            return {
                "status": "fail",
                "message": "Agent type already exists for this organization",
            }

        # Check if agent_id already exists for this organization
        existing_agent_by_id = agent_table.find_one(
            {"agent_id": agent_data.agent_id, "org_id": agent_data.org_id}
        )
        if existing_agent_by_id:
            return {
                "status": "fail",
                "message": "Agent ID already exists for this organization",
            }

        agent_doc = {
            "agent_type": agent_data.agent_type,
            "agent_id": agent_data.agent_id,
            "agent_config": agent_data.agent_config,
            "org_id": agent_data.org_id,
            "updated_at": datetime.now().isoformat(),
        }

        if agent_data.agent_category:
            agent_doc["agent_category"] = agent_data.agent_category
        if agent_data.phone_number:
            agent_doc["phone_number"] = agent_data.phone_number
        if agent_data.app_id:
            agent_doc["app_id"] = agent_data.app_id
        if agent_data.telephony_provider:
            agent_doc["telephony_provider"] = agent_data.telephony_provider
        if agent_data.greeting_message:
            # Remove punctuation from greeting message
            greeting_message = agent_data.greeting_message.translate(
                str.maketrans("", "", string.punctuation)
            )
            agent_doc["agent_config"]["greeting_message"] = greeting_message
        if agent_data.vobiz_app_id:
            agent_doc["vobiz_app_id"] = agent_data.vobiz_app_id
        if agent_data.vobiz_answer_url:
            agent_doc["vobiz_answer_url"] = agent_data.vobiz_answer_url
        if agent_data.livekit_inbound_trunk_id:
            agent_doc["livekit_inbound_trunk_id"] = agent_data.livekit_inbound_trunk_id
        if agent_data.livekit_outbound_trunk_id:
            agent_doc["livekit_outbound_trunk_id"] = (
                agent_data.livekit_outbound_trunk_id
            )
        if agent_data.livekit_dispatch_rule_id:
            agent_doc["livekit_dispatch_rule_id"] = agent_data.livekit_dispatch_rule_id

        agent_table.insert_one(agent_doc)
        logger.info(f"Agent created successfully: {agent_data.agent_type}")
        return {"status": "success", "message": "Agent type created successfully"}

    except Exception as e:
        logger.error(f"Error creating agent: {str(e)}")
        return {"status": "fail", "message": f"Error creating agent type: {str(e)}"}


def fetch_agent_config(agent_type: str) -> Optional[Dict[str, Any]]:
    """
    Fetch agent config for a given agent type.

    Args:
        agent_type: Agent type identifier

    Returns:
        Agent config document or None
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]
        agent = agent_table.find_one({"agent_type": agent_type})
        return agent
    except Exception as e:
        logger.error(f"Error fetching agent config: {str(e)}")
        return None


def fetch_agent_config_by_id(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch agent config for a given agent ID.

    Args:
        agent_id: Agent ID identifier

    Returns:
        Agent config document or None
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]
        agent = agent_table.find_one({"agent_id": agent_id})
        return agent
    except Exception as e:
        logger.error(f"Error fetching agent config by ID: {str(e)}")
        return None


def fetch_agents_of_org(org_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all agents for a given org.

    Args:
        org_id: Organization ID

    Returns:
        List of agent documents
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]
        agents = list(agent_table.find({"org_id": org_id}))
        return agents
    except Exception as e:
        logger.error(f"Error fetching agents: {str(e)}")
        return []


def update_agent_config(
    agent_type: str, agent_data: AgentConfigUpdate
) -> Dict[str, Any]:
    """
    Update agent config.

    Args:
        agent_type: Agent type identifier
        agent_data: Updated agent data

    Returns:
        Dict with status and message
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]

        update_doc = {
            "agent_config": agent_data.agent_config,
            "updated_at": datetime.now().isoformat(),
        }

        if agent_data.agent_category:
            update_doc["agent_category"] = agent_data.agent_category
        if agent_data.phone_number:
            update_doc["phone_number"] = agent_data.phone_number
        if agent_data.app_id:
            update_doc["app_id"] = agent_data.app_id
        if agent_data.telephony_provider:
            update_doc["telephony_provider"] = agent_data.telephony_provider
        if agent_data.greeting_message:
            greeting_message = agent_data.greeting_message.translate(
                str.maketrans("", "", string.punctuation)
            )
            update_doc["agent_config"]["greeting_message"] = greeting_message
        if agent_data.vobiz_app_id:
            update_doc["vobiz_app_id"] = agent_data.vobiz_app_id
        if agent_data.vobiz_answer_url:
            update_doc["vobiz_answer_url"] = agent_data.vobiz_answer_url
        if agent_data.livekit_inbound_trunk_id:
            update_doc["livekit_inbound_trunk_id"] = agent_data.livekit_inbound_trunk_id
        if agent_data.livekit_outbound_trunk_id:
            update_doc["livekit_outbound_trunk_id"] = (
                agent_data.livekit_outbound_trunk_id
            )
        if agent_data.livekit_dispatch_rule_id:
            update_doc["livekit_dispatch_rule_id"] = agent_data.livekit_dispatch_rule_id

        result = agent_table.update_one(
            {"agent_type": agent_type}, {"$set": update_doc}
        )

        if result.matched_count == 0:
            return {"status": "fail", "message": "Agent type not found"}

        logger.info(f"Agent updated successfully: {agent_type}")
        return {"status": "success", "message": "Agent config updated successfully"}

    except Exception as e:
        logger.error(f"Error updating agent: {str(e)}")
        return {"status": "fail", "message": f"Error updating agent: {str(e)}"}


async def delete_agent(agent_type: str) -> Dict[str, Any]:
    """
    Delete an agent by agent_type.

    This also cleans up associated LiveKit and Vobiz resources:
    - LiveKit dispatch rule
    - LiveKit inbound/outbound trunks
    - Vobiz trunk (if created during agent setup)

    Args:
        agent_type: Agent type identifier

    Returns:
        Dict with status and message
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]

        # First, fetch the agent to get its resource IDs
        agent = agent_table.find_one({"agent_type": agent_type})
        if not agent:
            return {"status": "fail", "message": "Agent type not found"}

        # Get resource IDs for cleanup
        dispatch_rule_id = agent.get("livekit_dispatch_rule_id")
        inbound_trunk_id = agent.get("livekit_inbound_trunk_id")
        outbound_trunk_id = agent.get("livekit_outbound_trunk_id")
        vobiz_trunk_id = agent.get("vobiz_trunk_id")
        vobiz_app_id = agent.get("vobiz_app_id")
        phone_number = agent.get("phone_number")

        # First unassign number from Vobiz trunk so inbound routing is cleaned up.
        if phone_number and vobiz_trunk_id:
            try:
                unlink_result = await vobiz_service.unlink_number_from_trunk(
                    phone_number
                )
                if unlink_result.get("status") == "success":
                    logger.info(
                        f"Unassigned phone number {phone_number} from Vobiz trunk"
                    )
                else:
                    logger.warning(
                        f"Failed to unassign phone number {phone_number}: {unlink_result.get('message')}"
                    )
            except Exception as e:
                logger.error(
                    f"Error unassigning phone number from Vobiz trunk: {str(e)}"
                )

        # Delete from MongoDB first
        result = agent_table.delete_one({"agent_type": agent_type})

        if result.deleted_count == 0:
            return {"status": "fail", "message": "Agent type not found"}

        # Now clean up LiveKit + Vobiz trunk resources
        if any([dispatch_rule_id, inbound_trunk_id, outbound_trunk_id, vobiz_trunk_id]):
            try:
                cleanup_result = await livekit_service.delete_agent_resources(
                    dispatch_rule_id=dispatch_rule_id,
                    inbound_trunk_id=inbound_trunk_id,
                    outbound_trunk_id=outbound_trunk_id,
                    vobiz_trunk_id=vobiz_trunk_id,
                )
                logger.info(f"LiveKit resources cleanup: {cleanup_result}")
            except Exception as e:
                logger.error(f"Error cleaning up LiveKit resources: {str(e)}")

        # Also delete Vobiz application if exists (legacy flow)
        if vobiz_app_id:
            try:
                vobiz_result = await vobiz_service.delete_vobiz_application(
                    vobiz_app_id
                )
                if vobiz_result.get("status") == "success":
                    logger.info(f"Deleted Vobiz application: {vobiz_app_id}")
                else:
                    logger.warning(
                        f"Failed to delete Vobiz app: {vobiz_result.get('message')}"
                    )
            except Exception as e:
                logger.error(f"Error deleting Vobiz application: {str(e)}")

        logger.info(f"Agent deleted successfully: {agent_type}")
        return {"status": "success", "message": "Agent deleted successfully"}

    except Exception as e:
        logger.error(f"Error deleting agent: {str(e)}")
        return {"status": "fail", "message": f"Error deleting agent: {str(e)}"}


def fetch_agent_by_phone_number(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Fetch agent config by phone number.

    Args:
        phone_number: Phone number to search for

    Returns:
        Agent config document or None
    """
    try:
        db = get_database()
        agent_table = db["AgentConfig"]
        agent = agent_table.find_one({"phone_number": phone_number})
        return agent
    except Exception as e:
        logger.error(f"Error fetching agent by phone number: {str(e)}")
        return None


async def create_agent_with_resources(agent_data: AgentConfigCreate) -> Dict[str, Any]:
    """
    Create an agent with all associated telephony resources.

    Flow (Vobiz only - LiveKit is infrastructure):
    1. Create Vobiz trunk with inbound_destination = LiveKit SIP URI
    2. Add credentials to Vobiz trunk
    3. Create LiveKit outbound trunk (address = vobiz_sip_domain)
    4. Create LiveKit inbound trunk (numbers = phone_number)
    5. Create dispatch rule
    6. Save agent to MongoDB

    Args:
        agent_data: Agent creation data including telephony config

    Returns:
        Dict with status, message, and created resources
    """
    created_resources = []

    # Track IDs for cleanup if something fails
    vobiz_trunk_id = None
    vobiz_sip_domain = None
    inbound_trunk_id = None
    outbound_trunk_id = None
    dispatch_rule_id = None

    try:
        # Validate - check if agent already exists
        db = get_database()
        agent_table = db["AgentConfig"]

        existing_agent = agent_table.find_one(
            {"agent_type": agent_data.agent_type, "org_id": agent_data.org_id}
        )
        if existing_agent:
            return {
                "status": "fail",
                "message": "Agent type already exists for this organization",
            }

        # Get telephony config from agent_config
        telephony_config = (
            agent_data.agent_config.get("telephony", {})
            if agent_data.agent_config
            else {}
        )

        # Get phone number from config
        phone_number = agent_data.phone_number or telephony_config.get("phone_number")
        sip_config = telephony_config.get("sip", {})

        logger.info(f"Creating agent with phone: {phone_number}")

        # =================================================================
        # STEP 1: Create Vobiz Trunk with inbound destination pointing to LiveKit
        # =================================================================
        # Get LiveKit SIP URI from settings
        livekit_sip_uri = settings.LIVEKIT_SIP_URI or settings.LIVEKIT_URL.replace(
            "wss://", ""
        ).replace("https://", "")
        # Remove sip: prefix if present
        livekit_sip_uri = livekit_sip_uri.replace("sip:", "")
        # Keep host-only URI (no sip: prefix). Transport is configured separately on trunk.

        logger.info(f"Creating Vobiz trunk with inbound_destination: {livekit_sip_uri}")

        trunk_result = await vobiz_service.create_trunk(
            name=f"{agent_data.agent_type} Trunk",
            trunk_direction="both",
            inbound_destination=livekit_sip_uri,
            trunk_status="enabled",
            secure=True,
        )

        if trunk_result.get("status") != "success":
            raise Exception(trunk_result.get("message", "Failed to create Vobiz trunk"))

        vobiz_trunk_id = trunk_result.get("trunk_id")
        vobiz_sip_domain = trunk_result.get("sip_domain")
        if not isinstance(vobiz_trunk_id, str) or not vobiz_trunk_id:
            raise Exception("Vobiz trunk created without trunk_id")
        vobiz_trunk_id = str(vobiz_trunk_id)
        created_resources.append(f"Vobiz trunk: {vobiz_trunk_id}")
        logger.info(
            f"Created Vobiz trunk: {vobiz_trunk_id}, sip_domain: {vobiz_sip_domain}"
        )

        # =================================================================
        # STEP 2: Add credentials to Vobiz trunk
        # =================================================================
        sip_username = sip_config.get("username")
        sip_password = sip_config.get("password")

        if sip_username and sip_password:
            cred_result = await vobiz_service.add_trunk_credentials(
                trunk_id=vobiz_trunk_id,
                username=sip_username,
                password=sip_password,
            )
            if cred_result.get("status") == "success":
                logger.info(f"Added credentials to Vobiz trunk {vobiz_trunk_id}")
            else:
                logger.warning(
                    f"Failed to add credentials: {cred_result.get('message')}"
                )

        # =================================================================
        # STEP 2b: Assign number to Vobiz trunk (for inbound PSTN routing)
        # =================================================================
        if phone_number:
            assign_result = await vobiz_service.link_number_to_trunk(
                phone_number=phone_number,
                trunk_id=vobiz_trunk_id,
            )
            if assign_result.get("status") == "success":
                logger.info(
                    f"Assigned phone number {phone_number} to Vobiz trunk {vobiz_trunk_id}"
                )
            else:
                raise Exception(
                    f"Failed to assign number to Vobiz trunk: {assign_result.get('message')}"
                )

        # =================================================================
        # STEP 3: Create LiveKit Outbound Trunk
        # Address = Vobiz SIP domain (for making outbound calls)
        # =================================================================
        if vobiz_sip_domain:
            outbound_result = await livekit_service.create_outbound_trunk(
                name=f"{agent_data.agent_type} Outbound",
                address=vobiz_sip_domain,
                numbers=[phone_number] if phone_number else [],
                auth_username=sip_username,
                auth_password=sip_password,
            )

            if outbound_result.get("status") != "success":
                raise Exception(
                    outbound_result.get("message", "Failed to create outbound trunk")
                )

            outbound_trunk_id = outbound_result.get("sip_trunk_id")
            created_resources.append(f"Outbound trunk: {outbound_trunk_id}")
            logger.info(f"Created LiveKit outbound trunk: {outbound_trunk_id}")

        # =================================================================
        # STEP 4: Create LiveKit Inbound Trunk
        # Numbers = Vobiz phone number (for receiving inbound calls)
        # =================================================================
        if phone_number:
            # Helper to extract conflicting trunk ID
            def extract_conflicting_trunk_id(message: str) -> str | None:
                import re

                match = re.search(r'"(ST_[A-Za-z0-9]+)"', message)
                return match.group(1) if match else None

            try:
                inbound_result = await livekit_service.create_inbound_trunk(
                    name=f"{agent_data.agent_type} Inbound",
                    numbers=[phone_number],
                    auth_username=None,
                    auth_password=None,
                    allowed_addresses=["0.0.0.0/0"],  # Allow all for now
                )

                if inbound_result.get("status") == "success":
                    inbound_trunk_id = inbound_result.get("sip_trunk_id")
                    created_resources.append(f"Inbound trunk: {inbound_trunk_id}")
                    logger.info(f"Created LiveKit inbound trunk: {inbound_trunk_id}")
                else:
                    error_msg = inbound_result.get("message", "")
                    conflict_id = extract_conflicting_trunk_id(error_msg)
                    if conflict_id:
                        logger.warning(
                            f"Conflicting trunk {conflict_id} - deleting and retrying"
                        )
                        await livekit_service.delete_trunk(conflict_id)
                        inbound_result = await livekit_service.create_inbound_trunk(
                            name=f"{agent_data.agent_type} Inbound",
                            numbers=[phone_number],
                            auth_username=None,
                            auth_password=None,
                            allowed_addresses=["0.0.0.0/0"],
                        )
                        if inbound_result.get("status") == "success":
                            inbound_trunk_id = inbound_result.get("sip_trunk_id")
                            created_resources.append(
                                f"Inbound trunk: {inbound_trunk_id}"
                            )
                            logger.info(
                                f"Created LiveKit inbound trunk after conflict: {inbound_trunk_id}"
                            )
                        else:
                            raise Exception(
                                inbound_result.get(
                                    "message", "Failed to create inbound trunk"
                                )
                            )
                    else:
                        raise Exception(error_msg)
            except Exception as e:
                logger.error(f"Failed to create inbound trunk: {e}")
                raise Exception(f"Failed to create inbound trunk: {str(e)}")

        # =================================================================
        # STEP 5: Create LiveKit Dispatch Rule
        # Route calls to the agent
        # =================================================================
        if inbound_trunk_id and phone_number:
            dispatch_result = await livekit_service.create_dispatch_rule(
                phone_number=phone_number,
                agent_id=agent_data.agent_id,
                trunk_id=inbound_trunk_id,
                name=f"{agent_data.agent_type} — {phone_number}",
            )

            if dispatch_result.get("status") != "success":
                raise Exception(
                    dispatch_result.get("message", "Failed to create dispatch rule")
                )

            dispatch_rule_id = dispatch_result.get("sip_dispatch_rule_id")
            created_resources.append(f"Dispatch rule: {dispatch_rule_id}")
            logger.info(f"Created LiveKit dispatch rule: {dispatch_rule_id}")

        # =================================================================
        # STEP 6: Save Agent to MongoDB
        # =================================================================
        agent_doc = {
            "agent_type": agent_data.agent_type,
            "agent_id": agent_data.agent_id,
            "agent_config": agent_data.agent_config,
            "org_id": agent_data.org_id,
            "updated_at": datetime.now().isoformat(),
        }

        if agent_data.agent_category:
            agent_doc["agent_category"] = agent_data.agent_category
        if phone_number:
            agent_doc["phone_number"] = phone_number
        if vobiz_trunk_id:
            agent_doc["vobiz_trunk_id"] = vobiz_trunk_id
        if vobiz_sip_domain:
            agent_doc["vobiz_sip_domain"] = vobiz_sip_domain
        if inbound_trunk_id:
            agent_doc["livekit_inbound_trunk_id"] = inbound_trunk_id
        if outbound_trunk_id:
            agent_doc["livekit_outbound_trunk_id"] = outbound_trunk_id
        if dispatch_rule_id:
            agent_doc["livekit_dispatch_rule_id"] = dispatch_rule_id

        # Always use Vobiz as provider (LiveKit is just infrastructure)
        agent_doc["telephony_provider"] = "Vobiz"

        agent_table.insert_one(agent_doc)
        created_resources.append(f"Agent: {agent_data.agent_type}")

        logger.info(f"Agent created with all resources: {agent_data.agent_type}")

        return {
            "status": "success",
            "message": "Agent created successfully with all resources",
            "agent_type": agent_data.agent_type,
            "vobiz_trunk_id": vobiz_trunk_id,
            "vobiz_sip_domain": vobiz_sip_domain,
            "livekit_inbound_trunk_id": inbound_trunk_id,
            "livekit_outbound_trunk_id": outbound_trunk_id,
            "livekit_dispatch_rule_id": dispatch_rule_id,
            "created_resources": created_resources,
        }

    except Exception as e:
        logger.error(f"Error creating agent with resources: {e}")

        # Cleanup on failure
        if inbound_trunk_id:
            try:
                await livekit_service.delete_trunk(inbound_trunk_id)
            except:
                pass
        if outbound_trunk_id:
            try:
                await livekit_service.delete_trunk(outbound_trunk_id)
            except:
                pass
        if dispatch_rule_id:
            try:
                await livekit_service.delete_dispatch_rule(dispatch_rule_id)
            except:
                pass
        if vobiz_trunk_id:
            try:
                await vobiz_service.delete_trunk(vobiz_trunk_id)
            except:
                pass

        return {
            "status": "fail",
            "message": f"Error creating agent: {str(e)}",
            "created_resources": created_resources,
        }
