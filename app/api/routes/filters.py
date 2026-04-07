"""Filters routes"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, Request

from app.services import get_api, get_processor, HistoricalAdsAPI, DataProcessor

router = APIRouter(tags=["Filters"])


def _build_query_kwargs(request: Request) -> Dict[str, Any]:
    grouped_values: Dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        grouped_values.setdefault(key, []).append(value)

    return {
        key.replace("-", "_"): values if len(values) > 1 else values[0]
        for key, values in grouped_values.items()
    }


@router.get("/filters")
async def get_filters(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """Get available filter options"""
    stats = await api.get_stats(**_build_query_kwargs(request))
    return processor.extract_filters(stats)


@router.get("/filters/{filter_name}")
async def get_filter(
    filter_name: str,
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
):
    """Get a single filter group by name."""
    stats = await api.get_stats(**_build_query_kwargs(request))
    filters = processor.extract_filters(stats)
    normalized_name = filter_name.replace("-", "_")
    return {normalized_name: filters.get(normalized_name, [])}
