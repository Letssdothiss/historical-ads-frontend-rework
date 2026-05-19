"""Tests for saved search routes."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api


class FakeAPI:
    async def search(self, **kwargs):
        return {"hits": []}

    async def get_ad(self, ad_id: str):
        return {"id": ad_id}

    async def get_stats(self, **kwargs):
        return {"stats": {}}


def test_saved_searches_can_be_created_and_loaded(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORICAL_ADS_STORAGE_DIR", str(tmp_path))
    app.dependency_overrides[get_api] = lambda: FakeAPI()

    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/v1/saved-searches",
            json={
                "name": "Python jobs",
                "description": "A saved search for Python roles",
                "filters": {"q": "python", "region": ["01"]},
            },
        )
        list_response = client.get("/api/v1/saved-searches")
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "Python jobs"
    assert created["filters"]["q"] == "python"
    assert created["id"]

    assert list_response.status_code == 200
    assert list_response.json()["saved_searches"][0]["id"] == created["id"]


def test_saved_searches_return_single_item(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORICAL_ADS_STORAGE_DIR", str(tmp_path))
    app.dependency_overrides[get_api] = lambda: FakeAPI()

    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/v1/saved-searches",
            json={"name": "Data roles", "filters": {"q": "data"}},
        )
        search_id = create_response.json()["id"]
        get_response = client.get(f"/api/v1/saved-searches/{search_id}")
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Data roles"
