"""Search routes"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

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


def _build_search_kwargs(request: Request) -> Dict[str, Any]:
    """Convert incoming query params into keyword arguments for the API client."""
    grouped_values: Dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        grouped_values.setdefault(key, []).append(value)

    search_kwargs: Dict[str, Any] = {}
    for key, values in grouped_values.items():
        normalized_key = key.replace("-", "_")
        search_kwargs[normalized_key] = values if len(values) > 1 else values[0]
    return search_kwargs


def _iter_text_fragments(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            yield from _iter_text_fragments(child, child_path)
        return

    if isinstance(value, list):
        for child in value:
            yield from _iter_text_fragments(child, path)
        return

    if value is None:
        return

    text = str(value).strip()
    if text:
        yield path, text


def _build_search_context(hit: Dict[str, Any]) -> list[Dict[str, str]]:
    context: list[Dict[str, str]] = []
    for path, text in _iter_text_fragments(hit):
        context.append({"path": path, "value": text})
    return context[:50]


@router.get("/search")
async def search(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Search historical job ads"""
    search_kwargs = _build_search_kwargs(request)
    result = await api.search(**search_kwargs)

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

    query = search_kwargs.get("q")
    if query and isinstance(result, dict):
        hits = result.get("hits")
        if isinstance(hits, list):
            enriched_hits = []
            for hit in hits:
                if isinstance(hit, dict):
                    enriched_hit = dict(hit)
                    enriched_hit["search_context"] = _build_search_context(enriched_hit)
                    enriched_hits.append(enriched_hit)
                else:
                    enriched_hits.append(hit)
            result["hits"] = enriched_hits

    return result


@router.get("/search/ad/{ad_id}")
async def get_ad(ad_id: str, api: HistoricalAdsAPI = Depends(get_api)) -> Dict[str, Any]:
    """Get specific job ad"""
    return await api.get_ad(ad_id)