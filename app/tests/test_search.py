"""Tests for Issue 3 search requirements."""

from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api


class FakeAPI:
    """Simple async API stub for route tests."""

    def __init__(
        self,
        payload: dict[str, Any],
        ad_payload: dict[str, Any] | None = None,
        enrich_payload: Any = None,
    ):
        self.payload = payload
        self.ad_payload = ad_payload
        self.enrich_payload = enrich_payload if enrich_payload is not None else []
        self.last_kwargs: dict[str, Any] = {}
        self.enrich_documents_calls: list[Any] = []

    async def search(self, **kwargs: Any) -> dict[str, Any]:
        self.last_kwargs = kwargs
        return self.payload

    async def get_ad(self, ad_id: str) -> dict[str, str]:
        if self.ad_payload is not None:
            return self.ad_payload
        return {"id": ad_id}

    async def enrich_documents(self, documents: Any) -> Any:
        self.enrich_documents_calls.append(documents)
        return self.enrich_payload


def test_search_free_text_returns_hits_and_count():
    # Simulate an upstream API response that only provides hits.
    fake_api = FakeAPI(
        {
            "hits": [
                {"id": "ad-1", "headline": "Data scientist"},
                {
                    "id": "ad-2",
                    "headline": "Data engineer",
                    "description": "Pythonutvecklare med fokus pa data",
                },
            ]
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        # Call the public endpoint as a client would do.
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"q": "data"})
    finally:
        # Always clean dependency overrides to avoid test cross-contamination.
        app.dependency_overrides.clear()

    # Verify the route responds and normalizes result_count from hits length.
    assert response.status_code == 200
    body = response.json()
    assert len(body["hits"]) == 2
    assert body["result_count"] == 2
    # Verify free-text query parameter forwarding to the service layer.
    assert fake_api.last_kwargs["q"] == "data"


def test_search_exposes_original_id_to_frontend():
    fake_api = FakeAPI(
        {
            "hits": [
                {
                    "id": "ad-1",
                    "originalId": "30429400",
                    "headline": "Data scientist",
                }
            ]
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"q": "data"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["hits"][0]["original_id"] == "30429400"


def test_search_combined_filters_are_forwarded():
    # Simulate a payload where total is nested in an object.
    fake_api = FakeAPI(
        {
            "hits": [
                {
                    "id": "ad-99",
                    "headline": "Backendutvecklare",
                    "description": "Python er meriterande",
                }
            ],
            "total": {"value": 47},
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    # Use list-of-tuples so repeated query keys (for multi-value filters) are preserved.
    params = (
        ("q", "python"),
        ("published_before", "2024-12-31"),
        ("published_after", "2024-01-01"),
        ("occupation", "2512"),
        ("occupation", "2513"),
        ("occupation_group", "23"),
        ("occupation_field", "3"),
        ("municipality", "0180"),
        ("region", "01"),
        ("country", "SE"),
        ("employment_type", "Heltid"),
        ("experience_required", "true"),
        ("offset", "5"),
        ("limit", "25"),
    )

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params=params)
    finally:
        app.dependency_overrides.clear()

    # Validate response data and normalized result_count.
    assert response.status_code == 200
    body = response.json()
    assert body["hits"][0]["id"] == "ad-99"
    assert body["result_count"] == 47
    assert body["hits"][0]["matched_context"]

    # Validate that all filters and pagination options are forwarded correctly.
    assert fake_api.last_kwargs["q"] == "python"
    assert fake_api.last_kwargs["published_before"] == "2024-12-31"
    assert fake_api.last_kwargs["published_after"] == "2024-01-01"
    assert fake_api.last_kwargs["occupation"] == ["2512", "2513"]
    assert fake_api.last_kwargs["occupation_group"] == "23"
    assert fake_api.last_kwargs["occupation_field"] == "3"
    assert fake_api.last_kwargs["municipality"] == "0180"
    assert fake_api.last_kwargs["region"] == "01"
    assert fake_api.last_kwargs["country"] == "SE"
    assert fake_api.last_kwargs["employment_type"] == "Heltid"
    assert fake_api.last_kwargs["experience_required"] == "true"
    assert fake_api.last_kwargs["offset"] == "5"
    assert fake_api.last_kwargs["limit"] == "25"


def test_search_keeps_existing_result_count():
    # Simulate an upstream response that already has a canonical result_count.
    fake_api = FakeAPI(
        {
            "hits": [{"id": "ad-100"}],
            "result_count": 1337,
            "total": 1,
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"q": "ml"})
    finally:
        app.dependency_overrides.clear()

    # Ensure existing result_count is respected and not overwritten.
    assert response.status_code == 200
    body = response.json()
    assert body["result_count"] == 1337


def test_search_forwards_dynamic_filters_without_route_changes():
    # Simulate an upstream response for a newly added filter key.
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    params = (
        ("q", "python"),
        ("custom-filter", "alpha"),
        ("custom-filter", "beta"),
        ("offset", "2"),
        ("limit", "15"),
    )

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["result_count"] == 0
    assert fake_api.last_kwargs["q"] == "python"
    assert fake_api.last_kwargs["custom_filter"] == ["alpha", "beta"]
    assert fake_api.last_kwargs["offset"] == "2"
    assert fake_api.last_kwargs["limit"] == "15"


def test_search_exposes_generic_search_context():
    fake_api = FakeAPI(
        {
            "hits": [
                {
                    "id": "ad-200",
                    "headline": "Supportmedarbetare",
                    "requirements": {
                        "language_note": "Språkkrav: Svenska och Engelska",
                        "experience": "Tidigare arbete inom kundservice är meriterande",
                    },
                },
            ],
            "total": 1,
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"q": "språk"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["hits"][0]["search_context"]
    assert {
        "path": "requirements.language_note",
        "value": "Språkkrav: Svenska och Engelska",
    } in body["hits"][0]["search_context"]
    assert body["hits"][0]["matched_context"]


def test_search_translates_year_month_into_published_window():
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/search", params={"q": "snickare", "year": "2024", "month": "3"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "year" not in fake_api.last_kwargs
    assert "month" not in fake_api.last_kwargs
    assert fake_api.last_kwargs["published_after"] == "2024-03-01"
    assert fake_api.last_kwargs["published_before"] == "2024-04-01"


def test_search_translates_year_only_into_full_year_window():
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"year": "2024"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_api.last_kwargs["published_after"] == "2024-01-01"
    assert fake_api.last_kwargs["published_before"] == "2025-01-01"


def test_get_ad_exposes_original_id_to_frontend():
    fake_api = FakeAPI({"id": "ad-1"}, ad_payload={"id": "ad-1", "originalId": "30429400"})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search/ad/ad-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["original_id"] == "30429400"


def test_search_folds_skills_into_free_text_query():
    # Upstream ignores the structured skills filter, so the competency search
    # must be folded into the free-text q query (terms OR-matched upstream).
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    params = (("skills", "python"), ("skills", "java"))

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_api.last_kwargs["q"] == "python java"
    # The raw skills key is consumed, not forwarded (upstream ignores it).
    assert "skills" not in fake_api.last_kwargs


def test_search_appends_skills_to_existing_query():
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    params = (("q", "göteborg"), ("skills", "snickare"))

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params=params)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_api.last_kwargs["q"] == "göteborg snickare"
    assert "skills" not in fake_api.last_kwargs


def test_search_routes_organization_number_through_employer():
    # Upstream ignores organization-number but filters org numbers via employer.
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/search", params={"organization_number": "2021004151"}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_api.last_kwargs["employer"] == "2021004151"
    assert "organization_number" not in fake_api.last_kwargs


def test_search_employer_name_filter_is_preserved():
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"employer": "Volvo"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_api.last_kwargs["employer"] == "Volvo"


def test_get_ad_attaches_enriched_skills_from_text():
    fake_api = FakeAPI(
        {"id": "ad-1"},
        ad_payload={
            "id": "ad-1",
            "headline": "Snickare sökes",
            "description": {"text": "Vi söker en erfaren snickare med truckkort."},
        },
        enrich_payload=[
            {
                "enriched_candidates": {
                    "competencies": [
                        {"concept_label": "Snickeri", "prediction": 0.91},
                        {"concept_label": "Truckkort", "prediction": 0.72},
                        {"concept_label": "Osäker kompetens", "prediction": 0.2},
                    ]
                }
            }
        ],
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search/ad/ad-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    labels = [skill["label"] for skill in body["enriched"]["skills"]]
    # High-confidence competencies are kept and ordered by prediction;
    # the low-confidence one is filtered out.
    assert labels == ["Snickeri", "Truckkort"]
    assert fake_api.enrich_documents_calls


def test_get_ad_without_text_skips_enrichment():
    fake_api = FakeAPI({"id": "ad-2"}, ad_payload={"id": "ad-2"})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search/ad/ad-2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "enriched" not in response.json()
    assert fake_api.enrich_documents_calls == []


def test_search_translates_from_year_to_year_into_inclusive_range():
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get("/api/v1/search", params={"from_year": "2022", "to_year": "2024"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_api.last_kwargs["published_after"] == "2022-01-01"
    assert fake_api.last_kwargs["published_before"] == "2025-01-01"


def test_search_explicit_published_after_overrides_year_alias():
    fake_api = FakeAPI({"hits": [], "total": 0})
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/search",
            params={"year": "2024", "published_after": "2024-06-15"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Explicit value wins; year alias is consumed but does not override it.
    assert fake_api.last_kwargs["published_after"] == "2024-06-15"
    assert fake_api.last_kwargs["published_before"] == "2025-01-01"


def test_search_returns_most_relevant_matched_context_and_limit():
    fake_api = FakeAPI(
        {
            "hits": [
                {
                    "id": "ad-300",
                    "headline": "Python utvecklare",
                    "description": "Vi söker en pythonutvecklare med python och data-erfarenhet",
                    "notes": "Allmän information",
                    "requirements": {
                        "must_have": "Python",
                        "language": "Svenska",
                    },
                }
            ],
            "total": 1,
        }
    )
    app.dependency_overrides[get_api] = lambda: fake_api

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/search",
            params={"q": "python data", "matched_context_limit": "2"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    matched = body["hits"][0]["matched_context"]
    assert len(matched) == 2
    assert matched[0]["score"] >= matched[1]["score"]
    assert matched[0]["matched_terms"] >= 1
