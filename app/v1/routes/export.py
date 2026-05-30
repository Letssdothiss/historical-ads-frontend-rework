"""Export routes"""

import io
import logging
import zipfile

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.common.schemas.schemas import ExportFormat
from app.common.utils.config import settings
from app.common.utils.query_utils import build_export_query_kwargs
from app.v1.services import DataProcessor, HistoricalAdsAPI, get_api, get_processor
from app.v1.services.export_service import iter_export_batches

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Export"])


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
    search_kwargs = build_export_query_kwargs(request)
    search_kwargs["limit"] = limit

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
    search_kwargs = build_export_query_kwargs(request)
    chunk_size = min(settings.MAX_PAGE_SIZE, settings.MAX_EXPORT_RECORDS)
    archive_name = processor.filename(search_kwargs.get("q"), "zip")
    csv_stem = archive_name[:-4]

    zip_buffer = io.BytesIO()
    part_number = 1

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        async for ads in iter_export_batches(api, chunk_size, **search_kwargs):
            csv_name = f"{csv_stem}_part{part_number:03d}.csv"
            archive.writestr(csv_name, processor.to_csv(ads))
            part_number += 1

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
    )
