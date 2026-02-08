"""Memory API routes (bot-facing, API-key protected)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.services.memory_service import memory_service


router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryIngestRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    text: str = Field(..., min_length=1)
    source: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class MemorySearchRequest(BaseModel):
    user_phone: str = Field(..., min_length=6)
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/ingest", status_code=status.HTTP_200_OK)
async def ingest(req: MemoryIngestRequest, _: bool = Depends(verify_api_key)):
    return memory_service.ingest(
        user_phone=req.user_phone,
        text=req.text,
        source=req.source,
        tags=req.tags,
    )


@router.post("/search", status_code=status.HTTP_200_OK)
async def search(req: MemorySearchRequest, _: bool = Depends(verify_api_key)):
    return memory_service.search(user_phone=req.user_phone, query=req.query, top_k=req.top_k)
