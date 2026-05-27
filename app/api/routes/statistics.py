"""Statistics routes"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from fastapi import APIRouter, Depends, Request

from app.api.routes.query_utils import build_query_kwargs
from app.services import HistoricalAdsAPI, get_api
from app.utils.config import settings
from app.utils.date_filters import normalize_date_filters

router = APIRouter(tags=["Statistics"])


def _parse_years_param(params: Dict[str, Any]) -> List[int]:
    if "years" in params:
        raw = params["years"]
        if isinstance(raw, list):
            raw = ",".join(raw)
        return [int(y.strip()) for y in str(raw).split(",") if y.strip().isdigit()]

    if "from_year" in params or "to_year" in params:
        try:
            start = int(
                params.get("from_year", params.get("from", datetime.utcnow().year - 4))
            )
            end = int(params.get("to_year", params.get("to", datetime.utcnow().year)))
            if start > end:
                start, end = end, start
            return list(range(start, end + 1))
        except Exception:
            return []

    now = datetime.utcnow().year
    default_span = settings.STATS_MAX_YEAR_CALLS
    return list(range(now - default_span + 1, now + 1))


def _format_month(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _next_month(year: int, month: int) -> Tuple[int, int]:
    if month >= 12:
        return year + 1, 1
    return year, month + 1


def _extract_total(result: Any) -> int:
    """Read the ad count from a /search response."""
    if not isinstance(result, dict):
        return 0
    total = result.get("total")
    if isinstance(total, dict):
        try:
            return int(total.get("value", 0))
        except (TypeError, ValueError):
            return 0
    if isinstance(total, int):
        return total
    if isinstance(total, str) and total.isdigit():
        return int(total)
    return 0


def _extract_region_counts(result: Any) -> Dict[str, int]:
    """Pull region->count out of a /search?stats=region response.

    The upstream uses {"stats": [{"type": "region", "values": [...]}]};
    older fake responses use {"stats": {"region": [...]}}, so we accept both.
    """
    counts: Dict[str, int] = {}
    if not isinstance(result, dict):
        return counts

    def _harvest(entries: Any) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            label = entry.get("term") or entry.get("label") or entry.get("name")
            raw_count = entry.get("count")
            if raw_count is None:
                raw_count = entry.get("occurrences")
            if not isinstance(label, str):
                continue
            if not isinstance(raw_count, (int, float, str)):
                continue
            try:
                counts[label] = counts.get(label, 0) + int(raw_count)
            except (TypeError, ValueError):
                continue

    stats = result.get("stats")
    if isinstance(stats, list):
        for block in stats:
            if isinstance(block, dict) and block.get("type") == "region":
                _harvest(block.get("values"))
    elif isinstance(stats, dict):
        _harvest(stats.get("region"))

    return counts


def _build_region_year_table(
    years: List[int],
    counts_by_year_region: Dict[int, Dict[str, int]],
) -> Dict[str, Any]:
    """Build a frontend-ready table shape: lan + year columns + totalt."""
    all_regions: Set[str] = set()
    for year in years:
        all_regions.update(counts_by_year_region[year].keys())

    rows: List[Dict[str, Any]] = []
    for region in sorted(all_regions):
        row: Dict[str, Any] = {"lan": region}
        row_total = 0
        for year in years:
            value = int(counts_by_year_region[year].get(region, 0))
            row[str(year)] = value
            row_total += value
        row["totalt"] = row_total
        rows.append(row)

    rows.sort(key=lambda item: int(item.get("totalt", 0)), reverse=True)

    return {
        "years": [str(year) for year in years],
        "rows": rows,
        "totalt": sum(int(item.get("totalt", 0)) for item in rows),
    }


async def _bounded_search(
    api: HistoricalAdsAPI,
    semaphore: asyncio.Semaphore,
    **kwargs: Any,
) -> Dict[str, Any]:
    async with semaphore:
        return await api.search(**kwargs)


@router.get("/stats")
async def get_stats(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Get statistics about job ads.

    Aggregated path: when multiple years are requested (or aggregate=year_region),
    issue one upstream `/search?stats=region&limit=0` per year plus a tiny
    `limit=0` total-only call per year/month combination. All in parallel. This
    replaces fetching and locally aggregating thousands of hit objects.
    """
    params = build_query_kwargs(request)

    aggregate = str(params.get("aggregate", "")).lower()
    explicit_year_request = any(
        key in params for key in ("years", "from_year", "to_year")
    )
    years = _parse_years_param(params)
    use_backend_aggregation = aggregate == "year_region" or explicit_year_request

    if not use_backend_aggregation:
        normalized = normalize_date_filters(params)
        has_date_filter = (
            "published_after" in normalized or "published_before" in normalized
        )
        if not has_date_filter:
            return await api.get_stats(**normalized)
        search_params = {
            k: v
            for k, v in normalized.items()
            if k not in {"stats", "limit", "offset", "aggregate"}
        }
        result = await api.search(
            **search_params, stats="region", stats_limit=30, limit=0
        )
        region_counts = _extract_region_counts(result)
        return {
            "stats": {
                "region": [
                    {"label": label, "occurrences": count}
                    for label, count in sorted(
                        region_counts.items(), key=lambda x: x[1], reverse=True
                    )
                ]
            }
        }

    years = years[: settings.STATS_MAX_YEAR_CALLS]

    excluded = {
        "from_date",
        "to_date",
        "from",
        "to",
        "years",
        "from_year",
        "to_year",
        "year",
        "month",
        "aggregate",
        "offset",
        "limit",
        "stats",
        "published_after",
        "published_before",
    }
    base_params = {k: v for k, v in params.items() if k not in excluded}

    semaphore = asyncio.Semaphore(settings.STATS_UPSTREAM_CONCURRENCY)

    region_tasks = [
        _bounded_search(
            api,
            semaphore,
            **base_params,
            stats="region",
            stats_limit=30,
            limit=0,
            published_after=f"{year:04d}-01-01",
            published_before=f"{year + 1:04d}-01-01",
        )
        for year in years
    ]

    month_specs: List[Tuple[int, int]] = [
        (year, month) for year in years for month in range(1, 13)
    ]
    month_tasks = [
        _bounded_search(
            api,
            semaphore,
            **base_params,
            limit=0,
            published_after=f"{year:04d}-{month:02d}-01",
            published_before="{:04d}-{:02d}-01".format(*_next_month(year, month)),
        )
        for year, month in month_specs
    ]

    region_results, month_results = await asyncio.gather(
        asyncio.gather(*region_tasks),
        asyncio.gather(*month_tasks),
    )

    counts_by_year_region: Dict[int, Dict[str, int]] = {}
    totals_by_year: Dict[int, int] = {}
    for year, region_result in zip(years, region_results, strict=False):
        counts_by_year_region[year] = _extract_region_counts(region_result)
        totals_by_year[year] = _extract_total(region_result)

    counts_by_year_month: Dict[int, Dict[str, int]] = {year: {} for year in years}
    for (year, month), month_result in zip(month_specs, month_results, strict=False):
        count = _extract_total(month_result)
        if count > 0:
            counts_by_year_month[year][_format_month(year, month)] = count

    stats_by_year = {
        str(year): {
            "region": [
                {"label": region, "occurrences": count}
                for region, count in sorted(
                    counts_by_year_region[year].items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ],
            "month": [
                {"label": month_label, "occurrences": count}
                for month_label, count in sorted(counts_by_year_month[year].items())
            ],
            "total_occurrences": totals_by_year[year],
        }
        for year in years
    }

    return {
        "stats_by_year": stats_by_year,
        "table_by_region": _build_region_year_table(years, counts_by_year_region),
        "aggregation_source": "upstream_stats_per_year",
        "meta": {
            "api_calls": len(region_tasks) + len(month_tasks),
            "years": years,
        },
    }
