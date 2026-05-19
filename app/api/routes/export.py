"""Export routes"""

import io
import logging
import zipfile
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.api.routes.query_utils import group_query_params
from app.models.schemas import ExportFormat
from app.services import DataProcessor, HistoricalAdsAPI, get_api, get_processor
from app.utils.config import settings
from app.utils.date_filters import normalize_date_filters

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Export"])


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


def _build_query_kwargs(request: Request) -> Dict[str, Any]:
    grouped_values = group_query_params(request)

    query_kwargs: Dict[str, Any] = {}
    for key, values in grouped_values.items():
        if key in EXCLUDED_EXPORT_QUERY_KEYS:
            continue

        mapped_key = DATE_FILTER_ALIASES.get(key, key)

        # Prefer explicit canonical date keys if both alias and canonical keys are sent.
        if mapped_key in query_kwargs and key != mapped_key:
            continue

        parsed_value: Any = values if len(values) > 1 else values[0]

        if key == "experience_required":
            parsed_bool = _to_bool(values[-1])
            query_kwargs[mapped_key] = (
                parsed_bool if parsed_bool is not None else values[-1]
            )
            continue

        query_kwargs[mapped_key] = parsed_value
    return normalize_date_filters(query_kwargs)


async def _iter_export_batches(
    api: HistoricalAdsAPI,
    chunk_size: int,
    **search_kwargs: Any,
):
    """Yield search result pages until the source API returns no more hits."""
    offset = 0

    while True:
        # Request one page at a time so large exports do not load everything into memory.
        result = await api.search(offset=offset, limit=chunk_size, **search_kwargs)
        hits = result.get("hits", [])

        if not hits:
            break

        yield hits

        offset += len(hits)
        if len(hits) < chunk_size:
            break


@router.get("/export")
async def export(
    request: Request,
    format: ExportFormat = Query(ExportFormat.JSON),
    limit: int = Query(1000, le=10000),
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Response:
    """Export job ads"""
    limit = min(limit, settings.MAX_EXPORT_RECORDS, settings.MAX_PAGE_SIZE)
    search_kwargs = _build_query_kwargs(request)
    search_kwargs["limit"] = limit

    # Single-file exports keep the current API behavior for JSON, CSV, and XLSX.
    result = await api.search(**search_kwargs)

    ads = result.get("hits", [])
    filename = processor.filename(search_kwargs.get("q"), format.value)

    if format == ExportFormat.JSON:
        data = processor.to_json(ads).encode()
        media_type = "application/json"
    elif format == ExportFormat.CSV:
        data = processor.to_csv(ads).encode()
        media_type = "text/csv"
    else:
        data = processor.to_xlsx(ads)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/bulk")
async def export_bulk(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Response:
    """Export all matching ads as split CSV files inside a ZIP archive."""
    search_kwargs = _build_query_kwargs(request)
    chunk_size = min(settings.MAX_PAGE_SIZE, settings.MAX_EXPORT_RECORDS)
    archive_name = processor.filename(search_kwargs.get("q"), "zip")
    csv_stem = archive_name[:-4]

    zip_buffer = io.BytesIO()
    part_number = 1

    # Write each batch as its own CSV file inside the ZIP archive.
    with zipfile.ZipFile(
        zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        async for ads in _iter_export_batches(api, chunk_size, **search_kwargs):
            csv_name = f"{csv_stem}_part{part_number:03d}.csv"
            archive.writestr(csv_name, processor.to_csv(ads))
            part_number += 1

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
    )
