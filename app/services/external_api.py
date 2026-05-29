"""External API client"""

import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.utils.config import settings
from app.utils.errors import (
    AppError,
    ConflictError,
    ExternalAPIError,
    NotFoundError,
    TimeoutError,
)

logger = logging.getLogger(__name__)


class HistoricalAdsAPI:
    """Client for Historical Ads API"""

    def __init__(self):
        self.base_url = settings.HISTORICAL_API_BASE_URL
        self.timeout = settings.API_TIMEOUT

    @staticmethod
    def _normalize_params(filters: Dict[str, Any]) -> Dict[str, Any]:
        return {key.replace("_", "-"): value for key, value in filters.items() if value is not None}

    async def _get(self, path: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)
        except httpx.TimeoutException as e:
            raise TimeoutError("API request timed out") from e
        except httpx.ConnectError as e:
            raise ExternalAPIError(f"Failed to connect: {e}") from e

    async def enrich_documents(self, documents: list[Dict[str, Any]]) -> Any:
        """Extract concepts (competencies, occupations, ...) from ad texts.

        Posts up to 100 documents to the JobTech enrichments API and returns
        the parsed JSON list of per-document results.
        """
        if not documents:
            return []
        url = settings.JOBAD_ENRICHMENTS_URL
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json={"documents_input": documents})
                return self._handle_response(response)
        except httpx.TimeoutException as e:
            raise TimeoutError("Enrichment request timed out") from e
        except httpx.ConnectError as e:
            raise ExternalAPIError(f"Failed to connect: {e}") from e

    async def search(self, **filters: Any) -> Dict[str, Any]:
        """Search for job ads"""
        params = self._normalize_params(filters)
        return await self._get("/search", params=params)

    async def get_ad(self, ad_id: str) -> Dict[str, Any]:
        """Get job ad by ID"""
        try:
            return await self._get(f"/ad/{ad_id}")
        except ExternalAPIError as exc:
            if not self._is_upstream_server_error(exc):
                raise

            # Some upstream ad IDs intermittently fail on /ad/{id} with 5xx,
            # while still being retrievable from /search.
            fallback_ad = await self._search_ad_fallback(ad_id)
            if fallback_ad is not None:
                logger.warning(
                    "Fell back to /search for ad id %s after upstream /ad failure",
                    ad_id,
                )
                return fallback_ad

            raise

    async def get_stats(self, **filters: Any) -> Dict[str, Any]:
        """Get statistics"""
        params = self._normalize_params(filters)
        return await self._get("/stats", params=params)

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle API response"""
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 400:
            raise ExternalAPIError(f"Bad request: {response.text}")
        elif response.status_code == 404:
            raise NotFoundError(f"Not found: {response.text}")
        elif response.status_code == 409:
            raise ConflictError(f"Conflict: {response.text}")
        else:
            raise ExternalAPIError(f"Error ({response.status_code}): {response.text}")

    @staticmethod
    def _is_upstream_server_error(exc: ExternalAPIError) -> bool:
        message = ""
        if isinstance(exc.detail, dict):
            message = str(exc.detail.get("message", ""))
        return re.search(r"Error \(5\d{2}\):", message) is not None

    async def _search_ad_fallback(self, ad_id: str) -> Optional[Dict[str, Any]]:
        try:
            search_result = await self.search(q=ad_id, limit=20)
        except AppError:
            return None

        hits = search_result.get("hits")
        if not isinstance(hits, list):
            return None

        for hit in hits:
            if not isinstance(hit, dict):
                continue
            if str(hit.get("id")) == ad_id:
                return hit

        return None


# Singleton
_api: Optional[HistoricalAdsAPI] = None


def get_api() -> HistoricalAdsAPI:
    """Get API client"""
    global _api
    if _api is None:
        _api = HistoricalAdsAPI()
    return _api
