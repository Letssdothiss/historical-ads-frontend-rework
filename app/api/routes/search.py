"""Search routes"""

import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, Query

from app.services import get_api, get_processor, HistoricalAdsAPI, DataProcessor

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


def _query_terms(query: str) -> list[str]:
    return [term for term in query.lower().split() if term]


def _normalize_limit(value: Any, default: int = 20, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _fragment_score(path: str, text: str, terms: list[str]) -> tuple[int, int, int]:
    normalized_path = path.lower()
    normalized_text = text.lower()
    words = set(re.findall(r"\w+", normalized_text))

    score = 0
    matched_terms = 0
    for term in terms:
        if term in normalized_path:
            score += 3
            matched_terms += 1
        if term in words:
            score += 8
            matched_terms += 1
        elif term in normalized_text:
            score += 5
            matched_terms += 1

    return score, matched_terms, len(text)


def _match_query_context(hit: Dict[str, Any], query: str, limit: int = 20) -> list[Dict[str, Any]]:
    terms = _query_terms(query)
    if not terms:
        return []

    ranked_matches: list[tuple[int, int, int, Dict[str, Any]]] = []
    for path, text in _iter_text_fragments(hit):
        score, matched_terms, text_len = _fragment_score(path, text, terms)
        if score <= 0:
            continue
        ranked_matches.append(
            (
                score,
                matched_terms,
                -text_len,
                {"path": path, "value": text, "score": score, "matched_terms": matched_terms},
            )
        )

    ranked_matches.sort(reverse=True)
    return [item[3] for item in ranked_matches[:limit]]


@router.get("/search")
async def search(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Search historical job ads"""
    search_kwargs = _build_search_kwargs(request)
    matched_context_limit = _normalize_limit(search_kwargs.pop("matched_context_limit", None))
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
                    matched_context = _match_query_context(
                        enriched_hit,
                        str(query),
                        limit=matched_context_limit,
                    )
                    if matched_context:
                        enriched_hit["search_context"] = _build_search_context(enriched_hit)
                        enriched_hit["matched_context"] = matched_context
                        enriched_hits.append(enriched_hit)
                else:
                    enriched_hits.append(hit)
            result["hits"] = enriched_hits

    return result


@router.get("/search/ad/{ad_id}")
async def get_ad(
    ad_id: str,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
    include_metadata: bool = Query(True, description="Include quality metadata in response"),
) -> Dict[str, Any]:
    """Get specific job ad with optional quality metadata

    Query parameters:
    - include_metadata: Include data quality and structure information (default: true)
    """
    ad = await api.get_ad(ad_id)

    if include_metadata:
        quality_metadata = processor.calculate_ad_quality(ad)
        return {"ad": ad, "metadata": quality_metadata}
    return ad
