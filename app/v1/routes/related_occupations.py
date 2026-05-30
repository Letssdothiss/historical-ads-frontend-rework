"""Related occupation routes."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.common.utils.query_utils import build_query_kwargs
from app.v1.services import HistoricalAdsAPI, get_api
from app.v1.services.occupation_service import build_related_occupations, normalize_seed

router = APIRouter(tags=["Related Occupations"])


@router.get("/related-occupations")
async def get_related_occupations(
    request: Request,
    occupation: Optional[str] = Query(None, description="Seed occupation label or code"),
    limit: int = Query(10, ge=1, le=50),
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    filters = build_query_kwargs(request)
    filters.pop("limit", None)
    filters.pop("occupation", None)

    result = await api.search(limit=min(limit * 10, 100), **filters)
    hits = result.get("hits", []) if isinstance(result, dict) else []

    seed = occupation or normalize_seed(filters.get("q"))
    related = build_related_occupations(hits, seed, limit)

    return {
        "occupation": occupation,
        "related_occupations": related,
        "result_count": len(related),
    }
