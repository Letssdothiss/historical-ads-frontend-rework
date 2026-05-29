"""Search routes"""

import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.routes.query_utils import (
    build_query_kwargs,
    fold_organization_number_into_employer,
    fold_skills_into_query,
)
from app.services import DataProcessor, HistoricalAdsAPI, get_api, get_processor
from app.utils.config import settings
from app.utils.date_filters import normalize_date_filters

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
    kwargs = normalize_date_filters(build_query_kwargs(request))
    return fold_organization_number_into_employer(fold_skills_into_query(kwargs))


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


def _find_original_id(value: Any) -> Optional[Any]:
    """Find an upstream original id value in common key variants."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = key.replace("-", "_").lower()
            if normalized_key in {"original_id", "originalid"}:
                return child
            found = _find_original_id(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_original_id(child)
            if found is not None:
                return found
    return None


def _ensure_original_id(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Guarantee that the frontend gets a top-level original_id field."""
    normalized_hit = dict(hit)

    if normalized_hit.get("original_id") in (None, ""):
        source_original_id = _find_original_id(normalized_hit)
        if source_original_id not in (None, ""):
            normalized_hit["original_id"] = source_original_id

    return normalized_hit


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
                {
                    "path": path,
                    "value": text,
                    "score": score,
                    "matched_terms": matched_terms,
                },
            )
        )

    # Use a key for sorting to avoid comparing dicts when tuples tie on first elements.
    ranked_matches.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [item[3] for item in ranked_matches[:limit]]


def _ad_enrichment_document(ad: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Build an enrichments-API document from an ad's headline and body text."""
    description = ad.get("description")
    if isinstance(description, dict):
        text = description.get("text") or ""
    else:
        text = description or ""
    headline = ad.get("headline") or ad.get("title") or ""

    text = str(text).strip()
    headline = str(headline).strip()
    if not text and not headline:
        return None

    return {
        "doc_id": str(ad.get("id") or "ad"),
        "doc_headline": headline,
        "doc_text": text,
    }


def _extract_enriched_skills(enriched: Any, min_prediction: float) -> List[Dict[str, Any]]:
    """Pull deduped competency labels out of an enrichments API response.

    Historical ads rarely carry structured must_have/nice_to_have skills, so
    we derive them from the ad text the same way the skills trend does.
    """
    if not isinstance(enriched, list):
        return []

    skills: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for doc in enriched:
        if not isinstance(doc, dict):
            continue
        candidates = (doc.get("enriched_candidates") or {}).get("competencies") or []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                prediction = float(candidate.get("prediction", 0))
            except (TypeError, ValueError):
                prediction = 0.0
            if prediction < min_prediction:
                continue
            label = candidate.get("concept_label") or candidate.get("term")
            if not isinstance(label, str) or not label.strip():
                continue
            key = label.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            skills.append({"label": label.strip(), "prediction": round(prediction, 3)})

    skills.sort(key=lambda item: item["prediction"], reverse=True)
    return skills


async def _attach_enriched_skills(ad: Dict[str, Any], api: HistoricalAdsAPI) -> Dict[str, Any]:
    """Best-effort: derive competencies from the ad text and attach them.

    Failures (network, unexpected upstream shape) are swallowed so the ad
    detail still renders without enriched skills.
    """
    document = _ad_enrichment_document(ad)
    if document is None:
        return ad

    try:
        enriched = await api.enrich_documents([document])
    except Exception:  # noqa: BLE001 - enrichment is optional, never fatal
        logger.warning("Ad enrichment failed for id %s", ad.get("id"), exc_info=True)
        return ad

    skills = _extract_enriched_skills(enriched, settings.AD_DETAIL_ENRICHMENT_MIN_PREDICTION)
    if not skills:
        return ad

    enriched_ad = dict(ad)
    existing = enriched_ad.get("enriched")
    group = dict(existing) if isinstance(existing, dict) else {}
    group["skills"] = skills
    enriched_ad["enriched"] = group
    return enriched_ad


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
                    enriched_hit = _ensure_original_id(hit)
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
        ad = await _attach_enriched_skills(ad, api)

    if include_metadata:
        # Preserve the ad's top-level shape (so `id` stays at root) and attach metadata
        if isinstance(ad, dict):
            enriched = _ensure_original_id(ad)
            enriched["metadata"] = quality_metadata
            return enriched
        return {"ad": ad, "metadata": quality_metadata}
    return ad
