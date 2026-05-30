"""Search routes"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query, Request

from app.common.utils.date_filters import normalize_date_filters
from app.v1.routes.query_utils import (
    build_query_kwargs,
    fold_organization_number_into_employer,
    fold_skills_into_query,
)
from app.v1.services import DataProcessor, HistoricalAdsAPI, get_api, get_processor
from app.v1.services.search_service import (
    attach_enriched_skills,
    ensure_original_id,
    normalize_limit,
    process_search_result,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Search"])


def _build_search_kwargs(request: Request) -> Dict[str, Any]:
    """Convert incoming query params into keyword arguments for the API client."""
    kwargs = normalize_date_filters(build_query_kwargs(request))
    return fold_organization_number_into_employer(fold_skills_into_query(kwargs))


@router.get("/search")
async def search(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Search historical job ads"""
    search_kwargs = _build_search_kwargs(request)
    matched_context_limit = normalize_limit(search_kwargs.pop("matched_context_limit", None))

    result = await api.search(**search_kwargs)

    if isinstance(result, dict):
        result = process_search_result(
            result,
            query=search_kwargs.get("q"),
            matched_context_limit=matched_context_limit,
        )

    return result


@router.get("/search/ad/{ad_id}")
async def get_ad(
    ad_id: str,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
    include_metadata: bool = Query(True, description="Include quality metadata in response"),
    enrich: bool = Query(True, description="Derive competencies from the ad text"),
) -> Dict[str, Any]:
    """Get specific job ad with optional quality metadata

    Query parameters:
    - include_metadata: Include data quality and structure information (default: true)
    - enrich: Derive competencies from the ad text via the enrichments API (default: true)
    """
    ad = await api.get_ad(ad_id)

    # Compute quality on the raw upstream ad so derived skills don't inflate it.
    quality_metadata = processor.calculate_ad_quality(ad) if include_metadata else None

    if enrich and isinstance(ad, dict):
        ad = await attach_enriched_skills(ad, api)

    if include_metadata:
        if isinstance(ad, dict):
            enriched = ensure_original_id(ad)
            enriched["metadata"] = quality_metadata
            return enriched
        return {"ad": ad, "metadata": quality_metadata}

    return ad
