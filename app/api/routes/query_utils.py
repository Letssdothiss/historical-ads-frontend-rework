"""Shared helpers for reading query params from FastAPI requests."""

from __future__ import annotations

from typing import Dict

from fastapi import Request

QueryParamGroups = Dict[str, list[str]]
QueryParamMap = Dict[str, str | list[str]]


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
