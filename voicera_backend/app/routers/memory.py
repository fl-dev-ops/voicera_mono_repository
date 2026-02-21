"""Memory API routes (bot-facing, API-key protected).

Endpoints:
- POST /memory/extract-and-store  — extract facts from an exchange and store new ones
- POST /memory/search             — vector search for relevant facts
- GET  /memory/bootstrap/{phone}  — get all facts + recent summaries for a user (pre-call)
- POST /memory/summarize          — generate and store a call summary
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.services.memory_service import memory_service


router = APIRouter(prefix="/memory", tags=["memory"])


# -------------------- Request models --------------------


class ExtractAndStoreRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    agent_message: str = Field(..., min_length=1)
    user_response: str = Field(..., min_length=1)
    source: Optional[Dict[str, Any]] = None


class SearchFactsRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class SummarizeRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    transcript: str = Field(..., min_length=1)
    call_id: Optional[str] = None
    summary_prompt: Optional[str] = None


# -------------------- Endpoints --------------------


@router.post("/extract-and-store", status_code=status.HTTP_200_OK)
async def extract_and_store(
    req: ExtractAndStoreRequest, _: bool = Depends(verify_api_key)
):
    """Extract facts from an agent-user exchange and store new ones."""
    return memory_service.extract_and_store_facts(
        user_phone=req.user_phone,
        agent_message=req.agent_message,
        user_response=req.user_response,
        source=req.source,
    )


@router.post("/search", status_code=status.HTTP_200_OK)
async def search_facts(req: SearchFactsRequest, _: bool = Depends(verify_api_key)):
    """Vector search for relevant facts about a user."""
    return memory_service.search_facts(
        user_phone=req.user_phone,
        query=req.query,
        top_k=req.top_k,
    )


@router.get("/bootstrap/{user_phone}", status_code=status.HTTP_200_OK)
async def bootstrap(user_phone: str, _: bool = Depends(verify_api_key)):
    """Get all known facts and recent call summaries for a user (pre-call bootstrap)."""
    return memory_service.bootstrap(user_phone=user_phone)


@router.post("/summarize", status_code=status.HTTP_200_OK)
async def summarize(req: SummarizeRequest, _: bool = Depends(verify_api_key)):
    """Generate and store a post-call summary."""
    return memory_service.generate_and_store_summary(
        user_phone=req.user_phone,
        transcript=req.transcript,
        call_id=req.call_id,
        summary_prompt=req.summary_prompt,
    )
