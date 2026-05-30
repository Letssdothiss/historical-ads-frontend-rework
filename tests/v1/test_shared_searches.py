"""Tests for shared search routes."""

from fastapi.testclient import TestClient

from app.main import app
from app.v1.services import get_api


class FakeAPI:
    def __init__(self):
        self.last_kwargs = None

    async def search(self, **kwargs):
        self.last_kwargs = kwargs
        return {"hits": [{"id": "ad-1"}], "result_count": 1}

    async def get_ad(self, ad_id: str):
        return {"id": ad_id}

    async def get_stats(self, **kwargs):
        return {"stats": {}}


def test_shared_search_can_be_created_and_resolved(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORICAL_ADS_STORAGE_DIR", str(tmp_path))
    fake_api = FakeAPI()
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        create_response = client.post(
            "/api/v1/shared-searches",
            json={"name": "Shared Python search", "filters": {"q": "python"}},
        )
        shared = create_response.json()
        resolve_response = client.get(shared["share_url"])
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 200
    assert shared["token"]
    assert shared["share_url"].startswith("/api/v1/shared-searches/")

    assert resolve_response.status_code == 200
    body = resolve_response.json()
    assert body["filters"]["q"] == "python"
    assert body["results"]["result_count"] == 1
    assert fake_api.last_kwargs is not None
    assert fake_api.last_kwargs["q"] == "python"
