"""Search service"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.common.utils.config import settings
from app.v1.services import HistoricalAdsAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Count normalisation
# ---------------------------------------------------------------------------


def to_int_count(value: Any) -> Optional[int]:
    """Normalise count values from external API response formats."""
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
        for key in ("value", "count", "total"):
            nested = value.get(key)
            nested_count = to_int_count(nested)
            if nested_count is not None:
                return nested_count
    if isinstance(value, list):
        return len(value)
    return None


def resolve_result_count(result: Dict[str, Any]) -> Optional[int]:
    """Return a stable result count from an upstream search response dict."""
    for key in ("total", "total_count", "count"):
        count = to_int_count(result.get(key))
        if count is not None:
            return count
    # Fall back to returned page size when no explicit total is available.
    return to_int_count(result.get("hits"))


# ---------------------------------------------------------------------------
# Fragment iteration & context building
# ---------------------------------------------------------------------------


def iter_text_fragments(value: Any, path: str = ""):
    """Yield (path, text) pairs by recursively walking a nested structure."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            yield from iter_text_fragments(child, child_path)
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_text_fragments(child, path)
        return
    if value is None:
        return
    text = str(value).strip()
    if text:
        yield path, text


def build_search_context(hit: Dict[str, Any]) -> list[Dict[str, str]]:
    context: list[Dict[str, str]] = []
    for path, text in iter_text_fragments(hit):
        context.append({"path": path, "value": text})
    return context[:50]


# ---------------------------------------------------------------------------
# original_id helpers
# ---------------------------------------------------------------------------


def find_original_id(value: Any) -> Optional[Any]:
    """Find an upstream original id value in common key variants."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key.replace("-", "_").lower() in {"original_id", "originalid"}:
                return child
            found = find_original_id(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_original_id(child)
            if found is not None:
                return found
    return None


def ensure_original_id(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Guarantee that the frontend gets a top-level original_id field."""
    normalised = dict(hit)
    if normalised.get("original_id") in (None, ""):
        source_id = find_original_id(normalised)
        if source_id not in (None, ""):
            normalised["original_id"] = source_id
    return normalised


# ---------------------------------------------------------------------------
# Query matching & ranking
# ---------------------------------------------------------------------------


def query_terms(query: str) -> list[str]:
    return [term for term in query.lower().split() if term]


def normalize_limit(
    value: Any,
    default: int = 20,
    minimum: int = 1,
    maximum: int = 100,
) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def fragment_score(path: str, text: str, terms: list[str]) -> tuple[int, int, int]:
    normalised_path = path.lower()
    normalised_text = text.lower()
    words = set(re.findall(r"\w+", normalised_text))

    score = 0
    matched_terms = 0
    for term in terms:
        if term in normalised_path:
            score += 3
            matched_terms += 1
        if term in words:
            score += 8
            matched_terms += 1
        elif term in normalised_text:
            score += 5
            matched_terms += 1

    return score, matched_terms, len(text)


def match_query_context(
    hit: Dict[str, Any],
    query: str,
    limit: int = 20,
) -> list[Dict[str, Any]]:
    terms = query_terms(query)
    if not terms:
        return []

    ranked: list[tuple[int, int, int, Dict[str, Any]]] = []
    for path, text in iter_text_fragments(hit):
        score, matched, text_len = fragment_score(path, text, terms)
        if score <= 0:
            continue
        ranked.append(
            (
                score,
                matched,
                -text_len,
                {"path": path, "value": text, "score": score, "matched_terms": matched},
            )
        )

    ranked.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [item[3] for item in ranked[:limit]]


# ---------------------------------------------------------------------------
# Enrichment helpers
# ---------------------------------------------------------------------------


def ad_enrichment_document(ad: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Build an enrichments-API document from an ad's headline and body text."""
    description = ad.get("description")
    text = description.get("text") or "" if isinstance(description, dict) else description or ""
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


def extract_enriched_skills(
    enriched: Any,
    min_prediction: float,
) -> List[Dict[str, Any]]:
    """Pull deduped competency labels out of an enrichments API response."""
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


async def attach_enriched_skills(
    ad: Dict[str, Any],
    api: HistoricalAdsAPI,
) -> Dict[str, Any]:
    """Best-effort: derive competencies from the ad text and attach them."""
    document = ad_enrichment_document(ad)
    if document is None:
        return ad

    try:
        enriched = await api.enrich_documents([document])
    except Exception:  # noqa: BLE001 - enrichment is optional, never fatal
        logger.warning("Ad enrichment failed for id %s", ad.get("id"), exc_info=True)
        return ad

    skills = extract_enriched_skills(enriched, settings.AD_DETAIL_ENRICHMENT_MIN_PREDICTION)
    if not skills:
        return ad

    enriched_ad = dict(ad)
    existing = enriched_ad.get("enriched")
    group = dict(existing) if isinstance(existing, dict) else {}
    group["skills"] = skills
    enriched_ad["enriched"] = group
    return enriched_ad


# ---------------------------------------------------------------------------
# Top-level search result processing
# ---------------------------------------------------------------------------


def process_search_result(
    result: Dict[str, Any],
    query: Optional[str],
    matched_context_limit: int,
) -> Dict[str, Any]:
    """Enrich a raw upstream search response with counts and per-hit context."""
    if "result_count" not in result:
        count = resolve_result_count(result)
        if count is not None:
            result["result_count"] = count

    if not query:
        return result

    hits = result.get("hits")
    if not isinstance(hits, list):
        return result

    enriched_hits = []
    for hit in hits:
        if not isinstance(hit, dict):
            enriched_hits.append(hit)
            continue

        hit = ensure_original_id(hit)
        matched_context = match_query_context(hit, query, limit=matched_context_limit)
        if matched_context:
            hit["search_context"] = build_search_context(hit)
            hit["matched_context"] = matched_context
        enriched_hits.append(hit)

    result["hits"] = enriched_hits
    return result
