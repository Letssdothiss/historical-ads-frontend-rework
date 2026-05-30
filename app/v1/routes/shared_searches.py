"""Shared search routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.common.utils.config import settings
from app.v1.services import HistoricalAdsAPI, get_api
from app.v1.services.search_persistence import append_record, get_record, new_id, now_iso

SHARED_SEARCHES_COLLECTION = "shared_searches.json"

router = APIRouter(tags=["Shared Searches"])


class SharedSearchCreate(BaseModel):
    """Payload for creating a shareable search."""

    name: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)


@router.post("/shared-searches")
async def create_shared_search(payload: SharedSearchCreate) -> Dict[str, Any]:
    token = new_id()
    record = {
        "id": token,
        "token": token,
        "name": payload.name,
        "filters": payload.filters,
        "share_url": f"{settings.API_PREFIX}/shared-searches/{token}",
        "created_at": now_iso(),
    }
    return append_record(SHARED_SEARCHES_COLLECTION, record)


@router.get("/shared-searches/{token}")
async def resolve_shared_search(
    token: str,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    record = get_record(SHARED_SEARCHES_COLLECTION, token, id_field="token")
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Shared search not found"},
        )

    results = await api.search(**record.get("filters", {}))
    return {
        "token": token,
        "share_url": record["share_url"],
        "name": record.get("name"),
        "filters": record.get("filters", {}),
        "results": results,
    }
