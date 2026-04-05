"""Tests for export routes."""
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api


class FakeBulkAPI:
    """Async API stub that returns paginated search results."""

    def __init__(self, ads):
        self.ads = ads
        self.calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        offset = kwargs["offset"]
        limit = kwargs["limit"]

        if offset == 0:
            return {"hits": self.ads[:limit]}
        if offset == limit:
            return {"hits": self.ads[limit:limit + 1]}
        return {"hits": []}

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

    assert len(names) == 2
    assert names[0].endswith("_part001.csv")
    assert names[1].endswith("_part002.csv")

    first_csv = archive.read(names[0]).decode("utf-8")
    second_csv = archive.read(names[1]).decode("utf-8")

    assert "ad-0" in first_csv
    assert "ad-999" in first_csv
    assert "ad-1000" in second_csv

    assert len(fake_api.calls) == 2
    assert fake_api.calls[0]["q"] == "2025"
    assert fake_api.calls[0]["published_after"] == "2025-01-01"
    assert fake_api.calls[0]["published_before"] == "2025-12-31"
    assert fake_api.calls[0]["occupation"] == ["1234"]
    assert fake_api.calls[0]["municipality"] == ["0180"]
    assert fake_api.calls[0]["region"] == ["01"]
    assert fake_api.calls[0]["country"] == ["SE"]
    assert fake_api.calls[0]["employment_type"] == ["Heltid"]
    assert fake_api.calls[0]["experience_required"] is True
    assert fake_api.calls[0]["offset"] == 0
    assert fake_api.calls[0]["limit"] == 1000
    assert fake_api.calls[1]["offset"] == 1000
    assert fake_api.calls[1]["limit"] == 1000
