"""
Vobiz service for handling Vobiz API operations.
"""
from typing import Dict, Any
from app.config import settings
import httpx
import logging

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
                "message": "Vobiz API credentials are not configured"
            }
        
        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/Account/{settings.VOBIZ_AUTH_ID}/Application/"
        
        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json"
        }
        
        # Prepare request body
        payload = {
            "app_name": agent_type,
            "answer_url": answer_url,
            "answer_method": "POST"
        }
        
        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Extract app_id from response if available
            app_id = data.get("app_id") or data.get("id") or data.get("application_id")
            
            logger.info(f"Vobiz application created successfully for agent_type: {agent_type}")
            return {
                "status": "success",
                "message": "Vobiz application created successfully",
                "app_id": app_id
            }
            
    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except Exception as e:
        error_message = f"Error creating Vobiz application: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }

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
                "message": "Vobiz API credentials are not configured"
            }
        
        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/Account/{settings.VOBIZ_AUTH_ID}/Application/{application_id}/"
        
        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN
        }
        
        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            
            logger.info(f"Vobiz application deleted successfully: {application_id}")
            return {
                "status": "success",
                "message": "Vobiz application deleted successfully"
            }
            
    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except Exception as e:
        error_message = f"Error deleting Vobiz application: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }

async def link_number_to_application(phone_number: str, application_id: str) -> Dict[str, Any]:
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
                "message": "Vobiz API credentials are not configured"
            }
        
        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/numbers/{phone_number}/application"
        
        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN,
            "Content-Type": "application/json"
        }
        
        # Prepare request body
        payload = {
            "application_id": application_id
        }
        
        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            logger.info(f"Phone number {phone_number} linked to application {application_id} successfully")
            return {
                "status": "success",
                "message": f"Phone number linked to application successfully"
            }
            
    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except Exception as e:
        error_message = f"Error linking phone number to application: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }

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
                "message": "Vobiz API credentials are not configured"
            }
        
        # Construct the Vobiz API URL
        url = f"{settings.VOBIZ_API_BASE_URL}/account/{settings.VOBIZ_AUTH_ID}/numbers/{phone_number}/application"
        
        # Prepare headers
        headers = {
            "X-Auth-ID": settings.VOBIZ_AUTH_ID,
            "X-Auth-Token": settings.VOBIZ_AUTH_TOKEN
        }
        
        # Make the API request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            
            logger.info(f"Phone number {phone_number} unlinked from application successfully")
            return {
                "status": "success",
                "message": "Phone number unlinked from application successfully"
            }
            
    except httpx.HTTPStatusError as e:
        error_message = f"Vobiz API error: {e.response.text}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except httpx.RequestError as e:
        error_message = f"Failed to connect to Vobiz API: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
    except Exception as e:
        error_message = f"Error unlinking phone number from application: {str(e)}"
        logger.error(error_message)
        return {
            "status": "fail",
            "message": error_message
        }
