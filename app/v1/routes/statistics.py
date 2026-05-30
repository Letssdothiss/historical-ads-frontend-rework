"""Statistics routes"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from app.v1.routes.query_utils import (
    build_query_kwargs,
    fold_organization_number_into_employer,
    fold_skills_into_query,
)
from app.v1.services import HistoricalAdsAPI, get_api, stats_service

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
    # Upstream ignores `skills` / `organization_number` (returns the full
    # corpus), so fold them into the free-text `q` / `employer` filters exactly
    # like the /search route — otherwise a competency search would aggregate
    # statistics over everything instead of the matching ads.
    params = fold_organization_number_into_employer(
        fold_skills_into_query(build_query_kwargs(request))
    )
    return await stats_service.compute_stats(api, params)
