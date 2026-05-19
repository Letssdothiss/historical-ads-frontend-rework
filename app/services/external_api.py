"""External API client"""

import logging
from typing import Any, Dict, Optional

import httpx

from app.utils.config import settings
from app.utils.errors import (
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
        return {
            key.replace("_", "-"): value
            for key, value in filters.items()
            if value is not None
        }

    async def _get(
        self, path: str, *, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)
        except httpx.TimeoutException as e:
            raise TimeoutError("API request timed out") from e
        except httpx.ConnectError as e:
            raise ExternalAPIError(f"Failed to connect: {e}") from e

    async def search(self, **filters: Any) -> Dict[str, Any]:
        """Search for job ads"""
        params = self._normalize_params(filters)
        return await self._get("/search", params=params)

    async def get_ad(self, ad_id: str) -> Dict[str, Any]:
        """Get job ad by ID"""
        return await self._get(f"/ad/{ad_id}")

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


# Singleton
_api: Optional[HistoricalAdsAPI] = None


def get_api() -> HistoricalAdsAPI:
    """Get API client"""
    global _api
    if _api is None:
        _api = HistoricalAdsAPI()
    return _api
