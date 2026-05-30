"""Shared helpers for reading query params from FastAPI requests."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request

from app.common.utils.date_filters import normalize_date_filters

QueryParamGroups = Dict[str, list[str]]
QueryParamMap = Dict[str, str | list[str]]

DATE_FILTER_ALIASES = {
    "from": "published_after",
    "to": "published_before",
    "from_date": "published_after",
    "to_date": "published_before",
    "start_date": "published_after",
    "end_date": "published_before",
    "date_from": "published_after",
    "date_to": "published_before",
    "published_from": "published_after",
    "published_to": "published_before",
}

EXCLUDED_EXPORT_QUERY_KEYS = {"format", "fields"}


def _to_bool(value: str) -> Optional[bool]:
    text = value.strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return None


def fold_skills_into_query(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Translate the competency search into upstream free-text.

    Upstream has no usable structured skill filter: its `skills` param is
    ignored (returns the full corpus) and `skill` expects taxonomy concept ids,
    not the free-text labels the competency field sends. So we fold the skill
    terms into the free-text `q` query, which matches headline + description —
    the same text the enrichments API derives competencies from, and which also
    contains the must-have / nice-to-have labels printed in the ad body.
    Upstream OR-matches space-separated terms, giving broad recall.
    """
    raw_skills = kwargs.pop("skills", None)
    if raw_skills is None:
        return kwargs

    skill_list = raw_skills if isinstance(raw_skills, list) else [raw_skills]
    terms = [str(term).strip() for term in skill_list if str(term).strip()]
    if not terms:
        return kwargs

    existing_q = str(kwargs.get("q", "")).strip()
    kwargs["q"] = " ".join([existing_q, *terms]) if existing_q else " ".join(terms)
    return kwargs


def fold_organization_number_into_employer(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Translate an organization-number filter into upstream's `employer` param.

    Upstream ignores `organization_number` / `organization-number` (returns the
    full corpus), but its `employer` param matches an exact organization number
    as well as a free-text employer name. The UI sends one or the other (a radio
    toggle), so when an organization number is present we route it through
    `employer`; the exact identifier wins over any free-text name.
    """
    raw_org = kwargs.pop("organization_number", None)
    if raw_org is None:
        return kwargs

    if isinstance(raw_org, list):
        raw_org = next((value for value in raw_org if str(value).strip()), None)
    if raw_org is None or not str(raw_org).strip():
        return kwargs

    kwargs["employer"] = str(raw_org).strip()
    return kwargs


def group_query_params(request: Request) -> QueryParamGroups:
    """Group repeated query keys and normalize key names to underscore format."""
    grouped_values: QueryParamGroups = {}
    for key, value in request.query_params.multi_items():
        normalized_key = key.replace("-", "_")
        grouped_values.setdefault(normalized_key, []).append(value)
    return grouped_values


def collapse_grouped_query_params(grouped_values: QueryParamGroups) -> QueryParamMap:
    """Collapse grouped query params to scalar values when a key occurs once."""
    return {key: values if len(values) > 1 else values[0] for key, values in grouped_values.items()}


def build_query_kwargs(request: Request) -> QueryParamMap:
    """Convert request query params into route kwargs, preserving repeated keys."""
    return collapse_grouped_query_params(group_query_params(request))


def build_export_query_kwargs(request: Request) -> Dict[str, Any]:
    """Convert export request query params, resolving date aliases and bool coercion."""
    grouped_values = group_query_params(request)

    query_kwargs: Dict[str, Any] = {}
    for key, values in grouped_values.items():
        if key in EXCLUDED_EXPORT_QUERY_KEYS:
            continue

        mapped_key = DATE_FILTER_ALIASES.get(key, key)

        if mapped_key in query_kwargs and key != mapped_key:
            continue

        if key == "experience_required":
            parsed_bool = _to_bool(values[-1])
            query_kwargs[mapped_key] = parsed_bool if parsed_bool is not None else values[-1]
            continue

        query_kwargs[mapped_key] = values if len(values) > 1 else values[0]

    normalized = fold_skills_into_query(normalize_date_filters(query_kwargs))
    return fold_organization_number_into_employer(normalized)
