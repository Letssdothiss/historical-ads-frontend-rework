"""Tests for related occupation routes."""

from fastapi.testclient import TestClient

from app.main import app
from app.v1.services import get_api


class FakeAPI:
    async def search(self, **kwargs):
        return {
            "hits": [
                {"occupation": {"label": "Systemutvecklare"}},
                {"occupation": {"label": "Backendutvecklare"}},
                {"occupation": {"label": "Systemutvecklare"}},
                {"occupation_name": "Data engineer"},
            ]
        }

    async def get_ad(self, ad_id: str):
        return {"id": ad_id}

    async def get_stats(self, **kwargs):
        return {"stats": {}}


def test_related_occupations_returns_ranked_candidates():
    app.dependency_overrides[get_api] = lambda: FakeAPI()

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/related-occupations", params={"occupation": "Systemutvecklare"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["occupation"] == "Systemutvecklare"
    assert body["related_occupations"][0]["occupation"] in {
        "Backendutvecklare",
        "Data engineer",
    }
    assert body["related_occupations"][0]["ad_count"] >= 1
