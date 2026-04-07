"""Tests for Issue 12 share-url behavior."""
from fastapi.testclient import TestClient

from app.main import app


def test_share_url_returns_current_query_string():
    client = TestClient(app)

    response = client.get(
        "/api/v1/share-url",
        params={
            "q": "python",
            "region": "01",
            "occupation": ["2512", "2513"],
        },
    )

    assert response.status_code == 200
    assert response.json()["share_url"] == "/api/v1/search?q=python&region=01&occupation=2512&occupation=2513"


def test_share_url_without_query_returns_base_search_url():
    client = TestClient(app)

    response = client.get("/api/v1/share-url")

    assert response.status_code == 200
    assert response.json()["share_url"] == "/api/v1/search"
