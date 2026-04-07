"""Tests for dynamic filters and stats routes."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api


class FakeStatsAPI:
    """Async API stub for stats-driven routes."""

    def __init__(self, payload):
        self.payload = payload
        self.last_kwargs = None

    async def get_stats(self, **kwargs):
        self.last_kwargs = kwargs
        return self.payload

    async def search(self, **kwargs):
        return {"hits": []}

    async def get_ad(self, ad_id: str):
        return {"id": ad_id}


def test_filters_returns_dynamic_keys_and_forwards_query_params():
    fake_api = FakeStatsAPI(
        {
            "stats": {
                "occupation-name": [{"label": "Sjukskoterska"}],
                "region": [{"label": "Skane"}],
                "custom-field": ["alpha", "beta"],
            }
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    params = [("q", "sprak"), ("custom-filter", "alpha"), ("custom-filter", "beta")]

    try:
        client = TestClient(app)
        response = client.get("/api/v1/filters", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["occupation_name"] == [{"label": "Sjukskoterska"}]
    assert body["region"] == [{"label": "Skane"}]
    assert body["custom_field"] == ["alpha", "beta"]
    assert fake_api.last_kwargs["q"] == "sprak"
    assert fake_api.last_kwargs["custom_filter"] == ["alpha", "beta"]


def test_filters_can_return_a_single_dynamic_group():
    fake_api = FakeStatsAPI(
        {
            "stats": {
                "occupation-name": [{"label": "Utvecklare"}],
                "language": ["Svenska", "Engelska"],
            }
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/filters/occupation-name", params={"q": "data"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body == {"occupation_name": [{"label": "Utvecklare"}]}
    assert fake_api.last_kwargs["q"] == "data"


def test_stats_route_forwards_dynamic_parameters():
    fake_api = FakeStatsAPI({"stats": {"region": ["Skane"]}})
    app.dependency_overrides[get_api] = lambda: fake_api

    params = [("q", "python"), ("custom-filter", "alpha"), ("custom-filter", "beta")]

    try:
        client = TestClient(app)
        response = client.get("/api/v1/stats", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"stats": {"region": ["Skane"]}}
    assert fake_api.last_kwargs["q"] == "python"
    assert fake_api.last_kwargs["custom_filter"] == ["alpha", "beta"]
