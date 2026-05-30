"""Filters routes"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from app.v1.routes.query_utils import build_query_kwargs
from app.v1.services import DataProcessor, HistoricalAdsAPI, get_api, get_processor

router = APIRouter(tags=["Filters"])


@router.get("/filters")
async def get_filters(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """Get available filter options"""
    stats = await api.get_stats(**build_query_kwargs(request))
    return processor.extract_filters(stats)


@router.get("/filters/{filter_name}")
async def get_filter(
    filter_name: str,
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
):
    """Get a single filter group by name."""
    stats = await api.get_stats(**build_query_kwargs(request))
    filters = processor.extract_filters(stats)
    normalized_name = filter_name.replace("-", "_")
    return {normalized_name: filters.get(normalized_name, [])}
