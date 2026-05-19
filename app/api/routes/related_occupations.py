"""Related occupation routes."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Depends, Query, Request

from app.api.routes.query_utils import build_query_kwargs
from app.services import HistoricalAdsAPI, get_api

router = APIRouter(tags=["Related Occupations"])


def _candidate_labels(hit: Dict[str, Any]) -> Iterable[str]:
    occupation = hit.get("occupation")
    if isinstance(occupation, dict):
        for key in ("label", "name", "title"):
            value = occupation.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()

    for key in (
        "occupation_label",
        "occupation_name",
        "occupation_title",
        "headline",
        "title",
    ):
        value = hit.get(key)
        if isinstance(value, str) and value.strip():
            yield value.strip()


def _tokenize(text: str) -> List[str]:
    return [part for part in re.findall(r"[\wåäöÅÄÖ]+", text.lower()) if len(part) > 2]


def _relation_score(seed: str, candidate: str) -> int:
    seed_tokens = set(_tokenize(seed))
    candidate_tokens = set(_tokenize(candidate))
    score = len(seed_tokens & candidate_tokens) * 10

    if seed.isdigit() and candidate.isdigit() and seed[:2] == candidate[:2]:
        score += 25

    if seed.lower() in candidate.lower() or candidate.lower() in seed.lower():
        score += 20

    if seed_tokens and candidate_tokens:
        first_seed = next(iter(seed_tokens))
        if len(first_seed) >= 4 and any(
            token.startswith(first_seed[:4]) for token in candidate_tokens
        ):
            score += 6

    return score


def _normalize_seed(value: str | list[str] | None) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if item:
                return item
    return ""


@router.get("/related-occupations")
async def get_related_occupations(
    request: Request,
    occupation: Optional[str] = Query(
        None, description="Seed occupation label or code"
    ),
    limit: int = Query(10, ge=1, le=50),
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    filters = build_query_kwargs(request)
    filters.pop("limit", None)
    filters.pop("occupation", None)

    result = await api.search(limit=min(limit * 10, 100), **filters)
    hits = result.get("hits", []) if isinstance(result, dict) else []

    counts: Counter[str] = Counter()
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        for label in _candidate_labels(hit):
            counts[label] += 1

    seed = occupation or _normalize_seed(filters.get("q"))
    related = []
    for label, count in counts.items():
        if seed and label.lower() == seed.lower():
            continue
        related.append(
            {
                "occupation": label,
                "ad_count": count,
                "score": _relation_score(seed, label) if seed else count,
            }
        )

    related.sort(
        key=lambda item: (item["score"], item["ad_count"], item["occupation"]),
        reverse=True,
    )

    return {
        "occupation": occupation,
        "related_occupations": related[:limit],
        "result_count": len(related),
    }
