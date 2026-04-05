"""Export routes"""
import io
import logging
import zipfile
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.models.schemas import ExportFormat
from app.services import get_api, get_processor, HistoricalAdsAPI, DataProcessor
from app.utils.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Export"])


def _search_kwargs(
    q: Optional[str],
    published_before: Optional[str],
    published_after: Optional[str],
    occupation: Optional[List[str]],
    occupation_group: Optional[List[str]],
    occupation_field: Optional[List[str]],
    municipality: Optional[List[str]],
    region: Optional[List[str]],
    country: Optional[List[str]],
    employment_type: Optional[List[str]],
    experience_required: Optional[bool],
) -> Dict[str, Any]:
    """Build a search payload that matches the search endpoint filters."""
    # Keep export filters aligned with the public search route.
    return {
        "q": q,
        "published_before": published_before,
        "published_after": published_after,
        "occupation": occupation,
        "occupation_group": occupation_group,
        "occupation_field": occupation_field,
        "municipality": municipality,
        "region": region,
        "country": country,
        "employment_type": employment_type,
        "experience_required": experience_required,
    }


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
    q: Optional[str] = Query(None),
    format: ExportFormat = Query(ExportFormat.JSON),
    limit: int = Query(1000, le=10000),
    published_before: Optional[str] = Query(None),
    published_after: Optional[str] = Query(None),
    occupation: Optional[List[str]] = Query(None),
    occupation_group: Optional[List[str]] = Query(None),
    occupation_field: Optional[List[str]] = Query(None),
    municipality: Optional[List[str]] = Query(None),
    region: Optional[List[str]] = Query(None),
    country: Optional[List[str]] = Query(None),
    employment_type: Optional[List[str]] = Query(None),
    experience_required: Optional[bool] = Query(None),
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Response:
    """Export job ads"""
    limit = min(limit, settings.MAX_EXPORT_RECORDS)
    
    # Single-file exports keep the current API behavior for JSON, CSV, and XLSX.
    result = await api.search(
        q=q,
        limit=limit,
        published_before=published_before,
        published_after=published_after,
        occupation=occupation,
        occupation_group=occupation_group,
        occupation_field=occupation_field,
        municipality=municipality,
        region=region,
        country=country,
        employment_type=employment_type,
        experience_required=experience_required,
    )
    
    ads = result.get("hits", [])
    filename = processor.filename(q, format.value)
    
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
    q: Optional[str] = Query(None),
    published_before: Optional[str] = Query(None),
    published_after: Optional[str] = Query(None),
    occupation: Optional[List[str]] = Query(None),
    occupation_group: Optional[List[str]] = Query(None),
    occupation_field: Optional[List[str]] = Query(None),
    municipality: Optional[List[str]] = Query(None),
    region: Optional[List[str]] = Query(None),
    country: Optional[List[str]] = Query(None),
    employment_type: Optional[List[str]] = Query(None),
    experience_required: Optional[bool] = Query(None),
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Response:
    """Export all matching ads as split CSV files inside a ZIP archive."""
    search_kwargs = _search_kwargs(
        q=q,
        published_before=published_before,
        published_after=published_after,
        occupation=occupation,
        occupation_group=occupation_group,
        occupation_field=occupation_field,
        municipality=municipality,
        region=region,
        country=country,
        employment_type=employment_type,
        experience_required=experience_required,
    )
    chunk_size = min(1000, settings.MAX_EXPORT_RECORDS)
    archive_name = processor.filename(q, "zip")
    csv_stem = archive_name[:-4]

    zip_buffer = io.BytesIO()
    part_number = 1

    # Write each batch as its own CSV file inside the ZIP archive.
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        async for ads in _iter_export_batches(api, chunk_size, **search_kwargs):
            csv_name = f"{csv_stem}_part{part_number:03d}.csv"
            archive.writestr(csv_name, processor.to_csv(ads))
            part_number += 1

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
    )