"""Tests for external API client fallback behavior."""

import pytest

from app.common.utils.errors import ExternalAPIError
from app.v1.services.external_api import HistoricalAdsAPI


@pytest.mark.asyncio
async def test_get_ad_falls_back_to_search_on_upstream_500():
    api = HistoricalAdsAPI()

    async def failing_get(path: str, **kwargs):
        raise ExternalAPIError("Error (500): upstream failed")

    async def search_fallback(**filters):
        return {
            "hits": [
                {"id": "ad-1", "headline": "Data engineer"},
                {"id": "ad-2", "headline": "Python developer"},
            ]
        }

    api._get = failing_get  # type: ignore[method-assign]
    api.search = search_fallback  # type: ignore[method-assign]

    result = await api.get_ad("ad-2")

    assert result["id"] == "ad-2"


@pytest.mark.asyncio
async def test_get_ad_reraises_when_fallback_has_no_exact_id_match():
    api = HistoricalAdsAPI()

    async def failing_get(path: str, **kwargs):
        raise ExternalAPIError("Error (500): upstream failed")

    async def search_fallback(**filters):
        return {"hits": [{"id": "something-else"}]}

    api._get = failing_get  # type: ignore[method-assign]
    api.search = search_fallback  # type: ignore[method-assign]

    with pytest.raises(ExternalAPIError):
        await api.get_ad("ad-2")


@pytest.mark.asyncio
async def test_get_ad_does_not_fallback_on_non_5xx_errors():
    api = HistoricalAdsAPI()

    async def failing_get(path: str, **kwargs):
        raise ExternalAPIError("Error (400): bad request")

    async def search_fallback(**filters):
        raise AssertionError("search fallback should not run for non-5xx")

    api._get = failing_get  # type: ignore[method-assign]
    api.search = search_fallback  # type: ignore[method-assign]

    with pytest.raises(ExternalAPIError):
        await api.get_ad("ad-2")
