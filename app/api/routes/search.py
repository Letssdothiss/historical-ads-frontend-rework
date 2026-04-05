"""Search routes"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query

from app.services import get_api, HistoricalAdsAPI

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Search"])


def _to_int_count(value: Any) -> Optional[int]:
    """Normalize count values from external API response formats."""
    # Ignore booleans so True/False is never treated as 1/0.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    if isinstance(value, dict):
        # Some providers wrap totals in nested objects (for example: {"value": 47}).
        for key in ("value", "count", "total"):
            nested = value.get(key)
            nested_count = _to_int_count(nested)
            if nested_count is not None:
                return nested_count
    if isinstance(value, list):
        return len(value)
    return None


@router.get("/search")
async def search(
    q: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    published_before: Optional[str] = Query(None),
    published_after: Optional[str] = Query(None),
    occupation: Optional[List[str]] = Query(None),
    occupation_group: Optional[List[str]] = Query(None),
    occupation_field: Optional[List[str]] = Query(None),
    municipality: Optional[List[str]] = Query(None),
    region: Optional[List[str]] = Query(None),
    country: Optional[List[str]] = Query(None),
    employment_type: Optional[List[str]] = Query(None),
    experience_required: Optional[bool] = Query(None),
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Search historical job ads"""
    result = await api.search(
        q=q, offset=offset, limit=limit,
        published_before=published_before, published_after=published_after,
        occupation=occupation, occupation_group=occupation_group,
        occupation_field=occupation_field, municipality=municipality,
        region=region, country=country, employment_type=employment_type,
        experience_required=experience_required,
    )

    if isinstance(result, dict) and "result_count" not in result:
        # Build a stable count field even if external APIs use different names.
        result_count = None
        for key in ("total", "total_count", "count"):
            result_count = _to_int_count(result.get(key))
            if result_count is not None:
                break

        if result_count is None:
            # Fall back to returned page size when no explicit total is available.
            result_count = _to_int_count(result.get("hits"))

        if result_count is not None:
            result["result_count"] = result_count

    return result


@router.get("/search/ad/{ad_id}")
async def get_ad(ad_id: str, api: HistoricalAdsAPI = Depends(get_api)) -> Dict[str, Any]:
    """Get specific job ad"""
    return await api.get_ad(ad_id)