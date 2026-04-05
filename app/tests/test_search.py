"""Tests for Issue 3 search requirements."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api


class FakeAPI:
	"""Simple async API stub for route tests."""

	def __init__(self, payload):
		self.payload = payload
		self.last_kwargs = None

	async def search(self, **kwargs):
		self.last_kwargs = kwargs
		return self.payload

	async def get_ad(self, ad_id: str):
		return {"id": ad_id}


def test_search_free_text_returns_hits_and_count():
	# Simulate an upstream API response that only provides hits.
	fake_api = FakeAPI(
		{
			"hits": [
				{"id": "ad-1", "headline": "Data scientist"},
				{"id": "ad-2", "headline": "Data engineer"},
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


def test_search_combined_filters_are_forwarded():
	# Simulate a payload where total is nested in an object.
	fake_api = FakeAPI(
		{
			"hits": [{"id": "ad-99", "headline": "Backendutvecklare"}],
			"total": {"value": 47},
		}
	)
	app.dependency_overrides[get_api] = lambda: fake_api

	# Use list-of-tuples so repeated query keys (for multi-value filters) are preserved.
	params = [
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
	]

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

	# Validate that all filters and pagination options are forwarded correctly.
	assert fake_api.last_kwargs["q"] == "python"
	assert fake_api.last_kwargs["published_before"] == "2024-12-31"
	assert fake_api.last_kwargs["published_after"] == "2024-01-01"
	assert fake_api.last_kwargs["occupation"] == ["2512", "2513"]
	assert fake_api.last_kwargs["occupation_group"] == ["23"]
	assert fake_api.last_kwargs["occupation_field"] == ["3"]
	assert fake_api.last_kwargs["municipality"] == ["0180"]
	assert fake_api.last_kwargs["region"] == ["01"]
	assert fake_api.last_kwargs["country"] == ["SE"]
	assert fake_api.last_kwargs["employment_type"] == ["Heltid"]
	assert fake_api.last_kwargs["experience_required"] is True
	assert fake_api.last_kwargs["offset"] == 5
	assert fake_api.last_kwargs["limit"] == 25


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
