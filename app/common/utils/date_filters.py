"""Translate year/month aliases into published-after / published-before.

The upstream API at https://historical.api.jobtechdev.se/ only filters by
`published-after` / `published-before` (or the deprecated `historical-from`
/ `historical-to`). Plain `year` and `month` parameters are silently ignored
upstream, so this helper converts them before the request is forwarded.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _coerce_ints(value: Any) -> List[int]:
    """Accept a scalar, list, or comma-separated string of integers."""
    if value is None:
        return []
    if isinstance(value, list):
        candidates: Iterable[Any] = value
    elif isinstance(value, str) and "," in value:
        candidates = value.split(",")
    else:
        candidates = [value]

    parsed: List[int] = []
    for item in candidates:
        text = str(item).strip()
        if text.isdigit():
            parsed.append(int(text))
    return parsed


def _format_date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def _next_month(year: int, month: int) -> Tuple[int, int]:
    if month >= 12:
        return year + 1, 1
    return year, month + 1


def normalize_date_filters(params: Dict[str, Any]) -> Dict[str, Any]:
    """Translate year/month/from_year/to_year into published_after/before.

    Pops the alias keys from `params` (mutating it) and inserts
    `published_after` / `published_before` when they were not already
    provided explicitly by the caller.
    """
    years = _coerce_ints(params.pop("year", None))
    months = _coerce_ints(params.pop("month", None))
    from_years = _coerce_ints(params.pop("from_year", None))
    to_years = _coerce_ints(params.pop("to_year", None))

    after: Optional[str] = None
    before: Optional[str] = None

    if years:
        start_year = min(years)
        end_year = max(years)

        if len(years) == 1 and len(months) == 1 and 1 <= months[0] <= 12:
            month = months[0]
            after = _format_date(start_year, month, 1)
            next_year, next_month = _next_month(start_year, month)
            before = _format_date(next_year, next_month, 1)
        else:
            after = _format_date(start_year, 1, 1)
            before = _format_date(end_year + 1, 1, 1)
    elif from_years or to_years:
        start_year = min(from_years) if from_years else min(to_years)
        end_year = max(to_years) if to_years else max(from_years)
        if start_year > end_year:
            start_year, end_year = end_year, start_year
        after = _format_date(start_year, 1, 1)
        before = _format_date(end_year + 1, 1, 1)

    if after is not None and "published_after" not in params:
        params["published_after"] = after
    if before is not None and "published_before" not in params:
        params["published_before"] = before

    params.setdefault("published_after", "2023-01-01")
    params.setdefault("published_before", date.today().strftime("%Y-%m-%d"))

    return params
