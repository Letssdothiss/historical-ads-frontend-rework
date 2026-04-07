"""External API client"""

import logging
from typing import Optional, Dict, Any, List
import httpx

from app.utils.config import settings
from app.utils.errors import ExternalAPIError, NotFoundError, ConflictError, TimeoutError

logger = logging.getLogger(__name__)


class HistoricalAdsAPI:
    """Client for Historical Ads API"""

    def __init__(self):
        self.base_url = settings.HISTORICAL_API_BASE_URL
        self.timeout = settings.API_TIMEOUT
    
    async def search(self, **filters: Any) -> Dict[str, Any]:
        """Search for job ads"""
        params: Dict[str, Any] = {
            key.replace("_", "-"): value
            for key, value in filters.items()
            if value is not None
        }
        
        url = f"{self.base_url}/search"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)
        except httpx.TimeoutException:
            raise TimeoutError("API request timed out")
        except httpx.ConnectError as e:
            raise ExternalAPIError(f"Failed to connect: {e}")

    async def get_ad(self, ad_id: str) -> Dict[str, Any]:
        """Get job ad by ID"""
        url = f"{self.base_url}/ad/{ad_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                return self._handle_response(response)
        except httpx.TimeoutException:
            raise TimeoutError("API request timed out")
        except httpx.ConnectError:
            raise ExternalAPIError("Failed to connect")
    
    async def get_stats(self, **filters: Any) -> Dict[str, Any]:
        """Get statistics"""
        params: Dict[str, Any] = {
            key.replace("_", "-"): value
            for key, value in filters.items()
            if value is not None
        }
        
        url = f"{self.base_url}/stats"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)
        except httpx.TimeoutException:
            raise TimeoutError("API request timed out")
        except httpx.ConnectError:
            raise ExternalAPIError("Failed to connect")

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
