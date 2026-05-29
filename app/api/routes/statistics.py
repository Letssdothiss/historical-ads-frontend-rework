"""Statistics routes"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from app.api.routes.query_utils import build_query_kwargs
from app.services import HistoricalAdsAPI, get_api, stats_service

router = APIRouter(tags=["Statistics"])


@router.get("/stats")
async def get_stats(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Get statistics about job ads.

    Delegates to stats_service, which chooses between a single total query
    and a per-year breakdown depending on the supplied query params.
    """
    params = build_query_kwargs(request)
    return await stats_service.compute_stats(api, params)
