"""Export service"""

from typing import Any, AsyncIterator

from app.v1.services.external_api import HistoricalAdsAPI


async def iter_export_batches(
    api: HistoricalAdsAPI,
    chunk_size: int,
    **search_kwargs: Any,
) -> AsyncIterator[list[Any]]:
    """Yield search result pages until the source API returns no more hits."""
    offset = 0

    while True:
        result = await api.search(offset=offset, limit=chunk_size, **search_kwargs)
        hits = result.get("hits", [])

        if not hits:
            break

        yield hits

        offset += len(hits)
        if len(hits) < chunk_size:
            break
