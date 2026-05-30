"""Shared helpers for reading query params from FastAPI requests."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Request

QueryParamGroups = Dict[str, list[str]]
QueryParamMap = Dict[str, str | list[str]]


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
