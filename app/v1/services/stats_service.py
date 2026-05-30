"""Statistics aggregation service.

Pure business logic for the /stats endpoint: parsing year params, issuing
upstream /search calls, shaping results for the frontend, and computing
occupation/skills trends. No FastAPI / HTTP concerns live here.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from app.common.utils.config import settings
from app.common.utils.date_filters import normalize_date_filters
from app.v1.services.external_api import HistoricalAdsAPI

# Trend types map to an upstream `stats` aggregation field. Skills have no
# upstream stats aggregation, so that trend is computed by sampling ad texts.
TREND_STATS_FIELD: Dict[str, str] = {
    "top5_occupations": "occupation-group",
    "top5_growing": "occupation-group",
    "top5_declining": "occupation-group",
}
TREND_RESULT_LIMIT = 5
TREND_STATS_LIMIT = 50


def _parse_years_param(params: Dict[str, Any]) -> List[int]:
    if "years" in params:
        raw = params["years"]
        if isinstance(raw, list):
            raw = ",".join(raw)
        return [int(y.strip()) for y in str(raw).split(",") if y.strip().isdigit()]

    if "from_year" in params or "to_year" in params:
        try:
            start = int(params.get("from_year", params.get("from", datetime.utcnow().year - 4)))
            end = int(params.get("to_year", params.get("to", datetime.utcnow().year)))
            if start > end:
                start, end = end, start
            return list(range(start, end + 1))
        except Exception:
            return []

    now = datetime.utcnow().year
    default_span = settings.STATS_MAX_YEAR_CALLS
    return list(range(now - default_span + 1, now + 1))


def _parse_months_by_year(params: Dict[str, Any]) -> Tuple[Dict[int, Set[int]], List[int]]:
    """Read the `months` filter into a per-year month map plus bare months.

    The frontend sends months year-qualified (``"2026-01"``) so each month stays
    tied to its year. Bare month numbers (``"3"``) are also accepted and apply to
    every selected year. Returns ``({year: {month, ...}}, [bare_month, ...])``.
    """
    raw = params.get("months")
    if raw is None:
        return {}, []

    values = raw if isinstance(raw, list) else [raw]
    by_year: Dict[int, Set[int]] = {}
    bare: List[int] = []
    for entry in values:
        text = str(entry).strip()
        qualified = re.fullmatch(r"(\d{4})-(\d{1,2})", text)
        if qualified:
            month = int(qualified.group(2))
            if 1 <= month <= 12:
                by_year.setdefault(int(qualified.group(1)), set()).add(month)
        elif text.isdigit() and 1 <= int(text) <= 12:
            bare.append(int(text))
    return by_year, bare


def _selected_months(year: int, months_by_year: Dict[int, Set[int]], bare: List[int]) -> List[int]:
    """Months chosen for a given year, or all 12 when none were selected."""
    selected = months_by_year.get(year) or set(bare)
    return sorted(selected) if selected else list(range(1, 13))


def _year_window(
    year: int, months_by_year: Dict[int, Set[int]], bare: List[int]
) -> Tuple[str, str]:
    """published-after / published-before for a year, narrowed to its selected
    months. Disjoint months collapse to the tightest covering span (upstream
    only accepts one range); no selection means the whole year."""
    months = sorted(months_by_year.get(year) or set(bare))
    if not months:
        return f"{year:04d}-01-01", f"{year + 1:04d}-01-01"
    after = f"{year:04d}-{min(months):02d}-01"
    next_year, next_month = _next_month(year, max(months))
    return after, f"{next_year:04d}-{next_month:02d}-01"


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


def _extract_stat_counts(result: Any, stat_type: str) -> Dict[str, int]:
    """Pull label->count out of a /search?stats=<stat_type> response.

    Upstream uses {"stats": [{"type": "<stat_type>", "values": [...]}]};
    older fake responses use {"stats": {"<stat_type>": [...]}}, so we accept both.
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
            if isinstance(block, dict) and block.get("type") == stat_type:
                _harvest(block.get("values"))
    elif isinstance(stats, dict):
        _harvest(stats.get(stat_type))

    return counts


def _extract_region_counts(result: Any) -> Dict[str, int]:
    """Pull region->count out of a /search?stats=region response."""
    return _extract_stat_counts(result, "region")


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


def _wants_year_breakdown(params: Dict[str, Any]) -> bool:
    aggregate = str(params.get("aggregate", "")).lower()
    explicit_year_request = any(key in params for key in ("years", "from_year", "to_year"))
    return aggregate == "year_region" or explicit_year_request


async def _compute_total_stats(
    api: HistoricalAdsAPI,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Single filtered upstream /search with all stats facets, no year breakdown.

    Uses /search (not get_stats) so the active query filters are honoured and
    only matching ads are aggregated.
    """
    normalized = normalize_date_filters(params)
    search_params = {
        k: v
        for k, v in normalized.items()
        if k not in {"stats", "limit", "offset", "aggregate", "months"}
    }
    return await api.search(
        **search_params,
        stats=["region", "municipality", "occupation-group", "occupation-name"],
        stats_limit=21,
        limit=0,
    )


async def _compute_year_breakdown(
    api: HistoricalAdsAPI,
    params: Dict[str, Any],
    years: List[int],
) -> Dict[str, Any]:
    """One /search per year for region stats, plus one per year/month for
    monthly totals. All issued in parallel under a concurrency limit."""
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
        "months",
        "aggregate",
        "offset",
        "limit",
        "stats",
        "published_after",
        "published_before",
    }
    base_params = {k: v for k, v in params.items() if k not in excluded}

    months_by_year, bare_months = _parse_months_by_year(params)

    semaphore = asyncio.Semaphore(settings.STATS_UPSTREAM_CONCURRENCY)

    # Region stats per year. When a year has all twelve months we issue one
    # whole-year call (cheap). When only a subset is selected we issue one call
    # per selected month and sum them, so disjoint months (e.g. Jan + Dec) count
    # exactly those months instead of widening into the whole-year span.
    # Each spec is (year, month_or_None, after, before); a non-None month means
    # the call also yields that month's total for the month breakdown.
    region_specs: List[Tuple[int, "int | None", str, str]] = []
    # Separate per-month total calls, only needed for the whole-year case (its
    # single region call can't break the year down by month).
    month_only_specs: List[Tuple[int, int, str, str]] = []

    def _month_window(year: int, month: int) -> Tuple[str, str]:
        next_year, next_month = _next_month(year, month)
        return (
            f"{year:04d}-{month:02d}-01",
            f"{next_year:04d}-{next_month:02d}-01",
        )

    for year in years:
        selected = _selected_months(year, months_by_year, bare_months)
        if len(selected) == 12:
            after, before = _year_window(year, months_by_year, bare_months)
            region_specs.append((year, None, after, before))
            for month in selected:
                m_after, m_before = _month_window(year, month)
                month_only_specs.append((year, month, m_after, m_before))
        else:
            for month in selected:
                m_after, m_before = _month_window(year, month)
                region_specs.append((year, month, m_after, m_before))

    region_tasks = [
        _bounded_search(
            api,
            semaphore,
            **base_params,
            stats="region",
            stats_limit=30,
            limit=0,
            published_after=after,
            published_before=before,
        )
        for (_, _, after, before) in region_specs
    ]
    month_tasks = [
        _bounded_search(
            api,
            semaphore,
            **base_params,
            limit=0,
            published_after=after,
            published_before=before,
        )
        for (_, _, after, before) in month_only_specs
    ]

    region_results, month_results = await asyncio.gather(
        asyncio.gather(*region_tasks),
        asyncio.gather(*month_tasks),
    )

    counts_by_year_region: Dict[int, Dict[str, int]] = {year: {} for year in years}
    totals_by_year: Dict[int, int] = {year: 0 for year in years}
    counts_by_year_month: Dict[int, Dict[str, int]] = {year: {} for year in years}

    for (year, month, _, _), region_result in zip(region_specs, region_results, strict=False):
        region_counts = _extract_region_counts(region_result)
        destination = counts_by_year_region[year]
        for label, count in region_counts.items():
            destination[label] = destination.get(label, 0) + count
        total = _extract_total(region_result)
        totals_by_year[year] += total
        # Per-month region calls double as that month's total for the breakdown.
        if month is not None and total > 0:
            counts_by_year_month[year][_format_month(year, month)] = total

    for (year, month, _, _), month_result in zip(month_only_specs, month_results, strict=False):
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


# --------------------------------------------------------------------------- #
# Trend branch
# --------------------------------------------------------------------------- #
def _select_trend_labels(
    trend: str,
    years: List[int],
    counts_by_year_label: Dict[int, Dict[str, int]],
    limit: int = TREND_RESULT_LIMIT,
) -> List[str]:
    labels: Set[str] = set()
    for year in years:
        labels.update(counts_by_year_label.get(year, {}).keys())

    def total(label: str) -> int:
        return sum(counts_by_year_label.get(year, {}).get(label, 0) for year in years)

    if trend in ("top5_growing", "top5_declining") and len(years) >= 2:
        first, last = years[0], years[-1]

        def change(label: str) -> int:
            after = counts_by_year_label.get(last, {}).get(label, 0)
            before = counts_by_year_label.get(first, {}).get(label, 0)
            return after - before

        ranked = sorted(
            labels,
            key=lambda label: (change(label), total(label)),
            reverse=(trend == "top5_growing"),
        )
    else:
        ranked = sorted(labels, key=total, reverse=True)

    return ranked[:limit]


def _shape_trend_result(
    trend: str,
    years: List[int],
    counts_by_year_label: Dict[int, Dict[str, int]],
    labels: List[str],
    *,
    api_calls: int,
    source: str,
    meta_extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    selected_counts: Dict[int, Dict[str, int]] = {
        year: {label: counts_by_year_label.get(year, {}).get(label, 0) for label in labels}
        for year in years
    }

    stats_by_year = {
        str(year): {
            "region": [
                {"label": label, "occurrences": selected_counts[year][label]} for label in labels
            ],
            "month": [],
            "total_occurrences": sum(selected_counts[year].values()),
        }
        for year in years
    }

    meta: Dict[str, Any] = {"api_calls": api_calls, "years": years}
    if meta_extra:
        meta.update(meta_extra)

    return {
        "stats_by_year": stats_by_year,
        "table_by_region": _build_region_year_table(years, selected_counts),
        "trend": trend,
        "trend_supported": True,
        "aggregation_source": source,
        "meta": meta,
    }


def _trend_excluded_params() -> Set[str]:
    return {
        "trend",
        "from_date",
        "to_date",
        "from",
        "to",
        "years",
        "from_year",
        "to_year",
        "year",
        "month",
        "months",
        "aggregate",
        "offset",
        "limit",
        "sort",
        "stats",
        "published_after",
        "published_before",
    }


def _count_competencies(enriched: Any, min_prediction: float) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if not isinstance(enriched, list):
        return counts
    for doc in enriched:
        if not isinstance(doc, dict):
            continue
        candidates = (doc.get("enriched_candidates") or {}).get("competencies") or []
        seen: Set[str] = set()
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
            if isinstance(label, str) and label and label not in seen:
                seen.add(label)
                counts[label] = counts.get(label, 0) + 1
    return counts


def _employer_key(hit: Dict[str, Any]) -> str:
    employer = hit.get("employer") if isinstance(hit, dict) else None
    if isinstance(employer, dict):
        for field in ("organization_number", "name", "workplace"):
            value = employer.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
    return f"_unknown_{hit.get('id')}"


def _ad_documents(result: Any) -> List[Dict[str, str]]:
    documents: List[Dict[str, str]] = []
    hits = result.get("hits") if isinstance(result, dict) else None
    if not isinstance(hits, list):
        return documents
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        text = (hit.get("description") or {}).get("text") or ""
        headline = hit.get("headline") or ""
        if not text and not headline:
            continue
        documents.append(
            {
                "doc_id": str(hit.get("id") or len(documents)),
                "doc_headline": str(headline),
                "doc_text": str(text),
                "employer": _employer_key(hit),
            }
        )
    return documents


def _year_subwindows(year: int, slices: int) -> List[Tuple[str, str]]:
    slices = max(1, min(12, slices))
    edges = [round(i * 12 / slices) for i in range(slices + 1)]
    windows: List[Tuple[str, str]] = []
    for i in range(slices):
        start_month = edges[i] + 1
        after = f"{year:04d}-{start_month:02d}-01"
        end_month = edges[i + 1]
        if end_month >= 12:
            before = f"{year + 1:04d}-01-01"
        else:
            before = f"{year:04d}-{end_month + 1:02d}-01"
        windows.append((after, before))
    return windows


def _cap_per_employer(documents: List[Dict[str, str]], cap: int) -> List[Dict[str, str]]:
    if cap <= 0:
        return documents
    kept: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}
    for doc in documents:
        employer = doc["employer"]
        if seen.get(employer, 0) >= cap:
            continue
        seen[employer] = seen.get(employer, 0) + 1
        kept.append(doc)
    return kept


async def _fetch_window_documents(
    api: HistoricalAdsAPI,
    semaphore: asyncio.Semaphore,
    base_params: Dict[str, Any],
    after: str,
    before: str,
    target: int,
) -> Tuple[List[Dict[str, str]], int]:
    documents: List[Dict[str, str]] = []
    api_calls = 0
    offset = 0
    while len(documents) < target and offset <= settings.MAX_OFFSET:
        page_size = min(settings.MAX_PAGE_SIZE, target - len(documents))
        async with semaphore:
            result = await api.search(
                **base_params,
                published_after=after,
                published_before=before,
                sort="id",
                limit=page_size,
                offset=offset,
            )
        api_calls += 1
        page_docs = _ad_documents(result)
        if not page_docs:
            break
        documents.extend(page_docs)
        offset += page_size
    return documents, api_calls


async def _sample_competency_counts(
    api: HistoricalAdsAPI,
    semaphore: asyncio.Semaphore,
    base_params: Dict[str, Any],
    year: int,
    sample_size: int,
    sub_windows: int,
    per_employer_cap: int,
    min_prediction: float,
) -> Tuple[int, Dict[str, int], int]:
    windows = _year_subwindows(year, sub_windows)
    per_window = -(-sample_size // len(windows))  # ceil division

    window_results = await asyncio.gather(
        *[
            _fetch_window_documents(api, semaphore, base_params, after, before, per_window)
            for after, before in windows
        ]
    )

    documents: List[Dict[str, str]] = []
    api_calls = 0
    for docs, calls in window_results:
        documents.extend(docs)
        api_calls += calls

    documents = _cap_per_employer(documents, per_employer_cap)

    counts: Dict[str, int] = {}
    for start in range(0, len(documents), 100):
        batch = [
            {k: doc[k] for k in ("doc_id", "doc_headline", "doc_text")}
            for doc in documents[start : start + 100]
        ]
        async with semaphore:
            enriched = await api.enrich_documents(batch)
        api_calls += 1
        for label, count in _count_competencies(enriched, min_prediction).items():
            counts[label] = counts.get(label, 0) + count

    return year, counts, api_calls


async def _run_skills_trend(
    api: HistoricalAdsAPI,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    years = sorted(set(_parse_years_param(params)))[: settings.STATS_MAX_YEAR_CALLS]
    base_params = {k: v for k, v in params.items() if k not in _trend_excluded_params()}

    semaphore = asyncio.Semaphore(settings.STATS_UPSTREAM_CONCURRENCY)
    results = await asyncio.gather(
        *[
            _sample_competency_counts(
                api,
                semaphore,
                base_params,
                year,
                settings.SKILLS_TREND_SAMPLE_SIZE,
                settings.SKILLS_TREND_SUBWINDOWS,
                settings.SKILLS_TREND_MAX_ADS_PER_EMPLOYER,
                settings.SKILLS_TREND_MIN_PREDICTION,
            )
            for year in years
        ]
    )

    counts_by_year_label: Dict[int, Dict[str, int]] = {}
    total_calls = 0
    for year, counts, calls in results:
        counts_by_year_label[year] = counts
        total_calls += calls

    labels = _select_trend_labels("top5_skills", years, counts_by_year_label)

    return _shape_trend_result(
        "top5_skills",
        years,
        counts_by_year_label,
        labels,
        api_calls=total_calls,
        source="enrichments_competency_sample",
        meta_extra={
            "sample_size": settings.SKILLS_TREND_SAMPLE_SIZE,
            "sub_windows": settings.SKILLS_TREND_SUBWINDOWS,
            "max_ads_per_employer": settings.SKILLS_TREND_MAX_ADS_PER_EMPLOYER,
            "approximate": True,
        },
    )


async def _run_trend_aggregation(
    api: HistoricalAdsAPI,
    trend: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    field = TREND_STATS_FIELD[trend]

    years = _parse_years_param(params)
    if trend in ("top5_growing", "top5_declining") and len(set(years)) < 2:
        anchor = max(years) if years else datetime.utcnow().year
        years = [anchor - 1, anchor]
    years = sorted(set(years))[: settings.STATS_MAX_YEAR_CALLS]

    base_params = {k: v for k, v in params.items() if k not in _trend_excluded_params()}

    semaphore = asyncio.Semaphore(settings.STATS_UPSTREAM_CONCURRENCY)
    tasks = [
        _bounded_search(
            api,
            semaphore,
            **base_params,
            stats=field,
            stats_limit=TREND_STATS_LIMIT,
            limit=0,
            published_after=f"{year:04d}-01-01",
            published_before=f"{year + 1:04d}-01-01",
        )
        for year in years
    ]
    results = await asyncio.gather(*tasks)

    counts_by_year_label: Dict[int, Dict[str, int]] = {}
    for year, result in zip(years, results, strict=False):
        counts_by_year_label[year] = _extract_stat_counts(result, field)

    labels = _select_trend_labels(trend, years, counts_by_year_label)

    return _shape_trend_result(
        trend,
        years,
        counts_by_year_label,
        labels,
        api_calls=len(tasks),
        source="upstream_stats_trend",
        meta_extra={"stats_field": field},
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
async def compute_stats(
    api: HistoricalAdsAPI,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Entry point for /stats. Dispatches to the trend, total, or year-breakdown
    path based on the incoming params."""
    trend = str(params.get("trend", "")).strip()
    if trend:
        if trend == "top5_skills":
            return await _run_skills_trend(api, params)
        if trend in TREND_STATS_FIELD:
            return await _run_trend_aggregation(api, trend, params)
        return {
            "stats_by_year": {},
            "table_by_region": {"years": [], "rows": [], "totalt": 0},
            "trend": trend,
            "trend_supported": False,
            "aggregation_source": "trend_unsupported",
            "meta": {"api_calls": 0, "years": []},
        }

    if not _wants_year_breakdown(params):
        return await _compute_total_stats(api, params)

    years = _parse_years_param(params)
    return await _compute_year_breakdown(api, params, years)
