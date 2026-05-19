"""Tests for backend stats aggregation."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api


class FakeStatsBackendAPI:
    """Stub that emulates the upstream /search endpoint.

    The real backend issues:
      - one ``stats=region`` call per year (full-year window)
      - one ``limit=0`` total-only call per (year, month) window

    This fake recognises both via the date window in the kwargs.
    """

    REGION_BY_YEAR = {
        "2024": [{"term": "Stockholms län", "count": 2}],
        "2025": [{"term": "Skåne län", "count": 1}],
    }

    MONTH_TOTALS = {
        ("2024-01-01", "2024-02-01"): 1,
        ("2024-02-01", "2024-03-01"): 1,
        ("2025-03-01", "2025-04-01"): 1,
    }

    def __init__(self):
        self.search_calls = []
        self.stats_calls = []

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        after = str(kwargs.get("published_after", ""))
        before = str(kwargs.get("published_before", ""))

        if kwargs.get("stats") == "region":
            # Year-level call. The window starts on Jan 1, year derived from after.
            year_key = after[:4]
            values = self.REGION_BY_YEAR.get(year_key, [])
            total = sum(v["count"] for v in values)
            return {
                "total": {"value": total},
                "stats": [{"type": "region", "values": values}],
            }

        # Monthly total-only call.
        count = self.MONTH_TOTALS.get((after, before), 0)
        return {"total": {"value": count}}

    async def get_stats(self, **kwargs):
        self.stats_calls.append(kwargs)
        return {"stats": {"region": []}}


def test_backend_year_month_aggregation_uses_upstream_stats():
    fake = FakeStatsBackendAPI()
    app.dependency_overrides[get_api] = lambda: fake

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/stats",
            params={"q": "snickare", "years": "2024,2025", "aggregate": "year_region"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()

    assert body["aggregation_source"] == "upstream_stats_per_year"
    # 2 years * (1 region call + 12 month calls) = 26.
    assert body["meta"]["api_calls"] == 26
    assert fake.search_calls
    assert not fake.stats_calls

    # Verify the per-year calls forwarded the `q` filter and used limit=0.
    region_calls = [c for c in fake.search_calls if c.get("stats") == "region"]
    assert len(region_calls) == 2
    for call in region_calls:
        assert call["q"] == "snickare"
        assert call["limit"] == 0

    # 12 month calls per year, none of them paginating hits.
    month_calls = [c for c in fake.search_calls if c.get("stats") != "region"]
    assert len(month_calls) == 24
    for call in month_calls:
        assert call["limit"] == 0
        assert "offset" not in call

    by_year = body["stats_by_year"]
    assert by_year["2024"]["total_occurrences"] == 2
    assert by_year["2025"]["total_occurrences"] == 1

    regions_2024 = {
        item["label"]: item["occurrences"] for item in by_year["2024"]["region"]
    }
    months_2024 = {
        item["label"]: item["occurrences"] for item in by_year["2024"]["month"]
    }

    assert regions_2024["Stockholms län"] == 2
    assert months_2024["2024-01"] == 1
    assert months_2024["2024-02"] == 1

    table = body["table_by_region"]
    assert table["years"] == ["2024", "2025"]
    assert table["totalt"] == 3

    rows = {row["lan"]: row for row in table["rows"]}
    assert rows["Stockholms län"]["2024"] == 2
    assert rows["Stockholms län"]["2025"] == 0
    assert rows["Stockholms län"]["totalt"] == 2
    assert rows["Skåne län"]["2024"] == 0
    assert rows["Skåne län"]["2025"] == 1
    assert rows["Skåne län"]["totalt"] == 1
