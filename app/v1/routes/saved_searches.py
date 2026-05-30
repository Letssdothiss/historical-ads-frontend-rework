"""Saved search routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.v1.services.search_persistence import (
    append_record,
    get_record,
    load_collection,
    new_id,
    now_iso,
)

SAVED_SEARCHES_COLLECTION = "saved_searches.json"

router = APIRouter(tags=["Saved Searches"])


class SavedSearchCreate(BaseModel):
    """Payload for storing a search definition."""

    name: str = Field(min_length=1)
    filters: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


@router.post("/saved-searches")
async def create_saved_search(payload: SavedSearchCreate) -> Dict[str, Any]:
    record = {
        "id": new_id(),
        "name": payload.name,
        "description": payload.description,
        "filters": payload.filters,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    return append_record(SAVED_SEARCHES_COLLECTION, record)


@router.get("/saved-searches")
async def list_saved_searches() -> Dict[str, Any]:
    return {"saved_searches": load_collection(SAVED_SEARCHES_COLLECTION)}


@router.get("/saved-searches/{search_id}")
async def get_saved_search(search_id: str) -> Dict[str, Any]:
    record = get_record(SAVED_SEARCHES_COLLECTION, search_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Saved search not found"},
        )
    return record
