"""Occupation relation helpers"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List


def candidate_labels(hit: Dict[str, Any]) -> Iterable[str]:
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


def tokenize(text: str) -> List[str]:
    return [part for part in re.findall(r"[\wåäöÅÄÖ]+", text.lower()) if len(part) > 2]


def relation_score(seed: str, candidate: str) -> int:
    seed_tokens = set(tokenize(seed))
    candidate_tokens = set(tokenize(candidate))
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


def normalize_seed(value: str | list[str] | None) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            if item:
                return item
    return ""


def build_related_occupations(
    hits: List[Dict[str, Any]],
    seed: str,
    limit: int,
) -> List[Dict[str, Any]]:
    counts: Counter[str] = Counter()
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        for label in candidate_labels(hit):
            counts[label] += 1

    related = []
    for label, count in counts.items():
        if seed and label.lower() == seed.lower():
            continue
        related.append(
            {
                "occupation": label,
                "ad_count": count,
                "score": relation_score(seed, label) if seed else count,
            }
        )

    related.sort(
        key=lambda item: (item["score"], item["ad_count"], item["occupation"]),
        reverse=True,
    )
    return related[:limit]
