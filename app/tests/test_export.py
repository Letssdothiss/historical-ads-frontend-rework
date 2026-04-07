"""Tests for export routes."""
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api
from app.utils.config import settings


class FakeBulkAPI:
    """Async API stub that returns paginated search results."""

    def __init__(self, ads):
        self.ads = ads
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        return {"hits": self.ads[offset:offset + limit]}

    async def get_ad(self, ad_id: str):
        return {"id": ad_id}


class FakeExportAPI:
    """Async API stub for single-file export route tests."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload

    async def get_ad(self, ad_id: str):
        return {"id": ad_id}


def test_bulk_export_returns_zip_with_split_csv_files():
    ads = [
        {
            "id": f"ad-{index}",
            "headline": f"Job {index}",
            "publication_date": "2025-01-01",
        }
        for index in range(1001)
    ]
    fake_api = FakeBulkAPI(ads)
    app.dependency_overrides[get_api] = lambda: fake_api

    params = [
        ("q", "2025"),
        ("published_after", "2025-01-01"),
        ("published_before", "2025-12-31"),
        ("occupation", "1234"),
        ("municipality", "0180"),
        ("region", "01"),
        ("country", "SE"),
        ("employment_type", "Heltid"),
        ("experience_required", "true"),
    ]

    try:
        client = TestClient(app)
        response = client.get("/api/v1/export/bulk", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].endswith('.zip"')

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()

    expected_parts = (len(ads) + settings.MAX_PAGE_SIZE - 1) // settings.MAX_PAGE_SIZE
    assert len(names) == expected_parts
    assert names[0].endswith("_part001.csv")
    assert names[-1].endswith(f"_part{expected_parts:03d}.csv")

    first_csv = archive.read(names[0]).decode("utf-8")
    last_csv = archive.read(names[-1]).decode("utf-8")

    assert "ad-0" in first_csv
    assert "ad-99" in first_csv
    assert "ad-1000" in last_csv

    assert len(fake_api.calls) == expected_parts
    assert fake_api.calls[0]["q"] == "2025"
    assert fake_api.calls[0]["published_after"] == "2025-01-01"
    assert fake_api.calls[0]["published_before"] == "2025-12-31"
    assert fake_api.calls[0]["occupation"] == "1234"
    assert fake_api.calls[0]["municipality"] == "0180"
    assert fake_api.calls[0]["region"] == "01"
    assert fake_api.calls[0]["country"] == "SE"
    assert fake_api.calls[0]["employment_type"] == "Heltid"
    assert fake_api.calls[0]["experience_required"] is True
    assert fake_api.calls[0]["offset"] == 0
    assert fake_api.calls[0]["limit"] == settings.MAX_PAGE_SIZE
    assert fake_api.calls[1]["offset"] == settings.MAX_PAGE_SIZE
    assert fake_api.calls[1]["limit"] == settings.MAX_PAGE_SIZE


def test_export_maps_common_date_aliases_to_published_filters():
    fake_api = FakeExportAPI(
        {
            "hits": [
                {
                    "id": "ad-10",
                    "headline": "Data Analyst",
                    "publication_date": "2024-02-01",
                }
            ]
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    params = [
        ("q", "analyst"),
        ("from_date", "2024-01-01"),
        ("to_date", "2024-12-31"),
        ("format", "csv"),
    ]

    try:
        client = TestClient(app)
        response = client.get("/api/v1/export", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert len(fake_api.calls) == 1
    assert fake_api.calls[0]["q"] == "analyst"
    assert fake_api.calls[0]["published_after"] == "2024-01-01"
    assert fake_api.calls[0]["published_before"] == "2024-12-31"
    assert "from_date" not in fake_api.calls[0]
    assert "to_date" not in fake_api.calls[0]
    assert "format" not in fake_api.calls[0]


def test_export_prefers_explicit_published_filters_over_aliases():
    fake_api = FakeExportAPI({"hits": []})
    app.dependency_overrides[get_api] = lambda: fake_api

    params = [
        ("from", "2023-01-01"),
        ("published_after", "2024-01-01"),
        ("to", "2023-12-31"),
        ("published_before", "2024-12-31"),
    ]

    try:
        client = TestClient(app)
        response = client.get("/api/v1/export", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(fake_api.calls) == 1
    assert fake_api.calls[0]["published_after"] == "2024-01-01"
    assert fake_api.calls[0]["published_before"] == "2024-12-31"
