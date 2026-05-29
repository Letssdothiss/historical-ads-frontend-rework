"""Tests for backend stats aggregation."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import get_api
from app.services.stats_service import (
    _cap_per_employer,
    _parse_months_by_year,
    _selected_months,
    _year_subwindows,
    _year_window,
)


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

    regions_2024 = {item["label"]: item["occurrences"] for item in by_year["2024"]["region"]}
    months_2024 = {item["label"]: item["occurrences"] for item in by_year["2024"]["month"]}

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


def test_year_window_narrows_to_selected_month():
    by_year, bare = _parse_months_by_year({"months": "2026-01"})
    assert by_year == {2026: {1}}
    assert bare == []
    # January only: published-after start of Jan, published-before start of Feb.
    assert _year_window(2026, by_year, bare) == ("2026-01-01", "2026-02-01")
    assert _selected_months(2026, by_year, bare) == [1]


def test_year_window_collapses_disjoint_months_to_tightest_span():
    by_year, bare = _parse_months_by_year({"months": ["2026-01", "2026-03"]})
    assert by_year == {2026: {1, 3}}
    # Jan + Mar -> Jan 1 .. Apr 1 (single upstream range), both months queried.
    assert _year_window(2026, by_year, bare) == ("2026-01-01", "2026-04-01")
    assert _selected_months(2026, by_year, bare) == [1, 3]


def test_year_window_defaults_to_whole_year_without_months():
    by_year, bare = _parse_months_by_year({})
    assert _year_window(2026, by_year, bare) == ("2026-01-01", "2027-01-01")
    assert _selected_months(2026, by_year, bare) == list(range(1, 13))


def test_stats_region_call_uses_selected_month_window():
    fake = FakeStatsBackendAPI()
    app.dependency_overrides[get_api] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/stats",
            params={"years": "2024", "months": "2024-02", "aggregate": "year_region"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    region_calls = [c for c in fake.search_calls if c.get("stats") == "region"]
    assert len(region_calls) == 1
    assert region_calls[0]["published_after"] == "2024-02-01"
    assert region_calls[0]["published_before"] == "2024-03-01"
    # Only the selected month is queried, not all twelve.
    month_calls = [c for c in fake.search_calls if c.get("stats") != "region"]
    assert len(month_calls) == 1
    # `months` must not leak to upstream as a raw filter.
    assert all("months" not in c for c in fake.search_calls)


def test_undated_search_forwards_filters_via_search_stats():
    """Without a time period, filters must still reach upstream.

    Regression for the bug where every undated search returned the same
    ~3.9M total because the route short-circuited to the upstream /stats
    endpoint, which ignores filters (q, employment_type, ...). The undated
    path now issues a single filtered /search requesting all stats facets.
    """
    fake = FakeStatsBackendAPI()
    app.dependency_overrides[get_api] = lambda: fake

    try:
        client = TestClient(app)
        response = client.get(
            "/api/v1/stats",
            params={"q": "snickare", "employment_type": "kpPX_CNN_gDU"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    # The unreliable upstream /stats endpoint must not be used.
    assert fake.stats_calls == []

    # A single filtered search that forwarded the active filters and requested
    # all stats facets as a list.
    assert len(fake.search_calls) == 1
    call = fake.search_calls[0]
    assert call["q"] == "snickare"
    assert call["employment_type"] == "kpPX_CNN_gDU"
    assert call["limit"] == 0
    assert call["stats"] == [
        "region",
        "municipality",
        "occupation-group",
        "occupation-name",
    ]


class FakeTrendBackendAPI:
    """Stub returning occupation-group stats per year window."""

    GROUPS_BY_YEAR = {
        "2024": [
            {"term": "Mjukvaru- och systemutvecklare", "count": 100},
            {"term": "Sjuksköterskor", "count": 80},
            {"term": "Lärare", "count": 60},
        ],
        "2025": [
            {"term": "Mjukvaru- och systemutvecklare", "count": 40},
            {"term": "Sjuksköterskor", "count": 200},
            {"term": "Lärare", "count": 50},
        ],
    }

    def __init__(self):
        self.search_calls = []

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        year_key = str(kwargs.get("published_after", ""))[:4]
        values = self.GROUPS_BY_YEAR.get(year_key, [])
        total = sum(v["count"] for v in values)
        return {
            "total": {"value": total},
            "stats": [{"type": "occupation-group", "values": values}],
        }

    async def get_stats(self, **kwargs):  # pragma: no cover - not used here
        return {"stats": {"region": []}}


def _run_trend(trend, params=None):
    fake = FakeTrendBackendAPI()
    app.dependency_overrides[get_api] = lambda: fake
    try:
        client = TestClient(app)
        query = {"trend": trend, "years": "2024,2025"}
        if params:
            query.update(params)
        response = client.get("/api/v1/stats", params=query)
    finally:
        app.dependency_overrides.clear()
    return response, fake


def test_trend_top_occupations_uses_occupation_group_stats():
    response, fake = _run_trend("top5_occupations")

    assert response.status_code == 200
    body = response.json()
    assert body["trend_supported"] is True
    assert body["aggregation_source"] == "upstream_stats_trend"

    # One occupation-group call per year, none paginating hits.
    assert len(fake.search_calls) == 2
    for call in fake.search_calls:
        assert call["stats"] == "occupation-group"
        assert call["limit"] == 0

    # Ranked by total across years: Sjuksköterskor (280) > Utvecklare (140) > Lärare (110).
    table_rows = body["table_by_region"]["rows"]
    assert table_rows[0]["lan"] == "Sjuksköterskor"
    assert table_rows[0]["totalt"] == 280


def test_trend_growing_ranks_by_year_over_year_change():
    response, _ = _run_trend("top5_growing")

    body = response.json()
    # Biggest gain 2024->2025 is Sjuksköterskor (+120).
    assert body["table_by_region"]["rows"][0]["lan"] == "Sjuksköterskor"


def test_trend_declining_ranks_by_year_over_year_change():
    response, _ = _run_trend("top5_declining")

    body = response.json()
    labels = [row["lan"] for row in body["table_by_region"]["rows"]]
    # Biggest drop is Utvecklare (-60), so it must be among the surfaced labels.
    assert "Mjukvaru- och systemutvecklare" in labels


def test_unknown_trend_is_reported_explicitly():
    fake = FakeTrendBackendAPI()
    app.dependency_overrides[get_api] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/v1/stats", params={"trend": "top5_bogus"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["trend_supported"] is False
    assert body["stats_by_year"] == {}
    # No upstream calls for an unknown trend.
    assert fake.search_calls == []


class FakeSkillsBackendAPI:
    """Stub returning ad hits with text plus enrichment competencies."""

    def __init__(self):
        self.search_calls = []
        self.enrich_calls = []

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        after = str(kwargs.get("published_after", ""))
        # Return two ads once (first time-slice, first page); empty otherwise so
        # the stratified sampling loop terminates with a single a/b sample.
        if kwargs.get("offset", 0) > 0 or not after.endswith("-01-01"):
            return {"hits": []}
        return {
            "hits": [
                {
                    "id": "a",
                    "headline": "Dev",
                    "description": {"text": "Java och SQL"},
                    "employer": {"organization_number": "111"},
                },
                {
                    "id": "b",
                    "headline": "Dev2",
                    "description": {"text": "Java"},
                    "employer": {"organization_number": "222"},
                },
            ]
        }

    async def enrich_documents(self, documents):
        self.enrich_calls.append(documents)
        comp = {
            "a": [
                {"concept_label": "Java", "prediction": 0.9},
                {"concept_label": "Sql", "prediction": 0.8},
            ],
            "b": [
                {"concept_label": "Java", "prediction": 0.9},
                {"concept_label": "Php", "prediction": 0.2},  # below threshold
            ],
        }
        return [
            {
                "doc_id": d["doc_id"],
                "enriched_candidates": {"competencies": comp.get(d["doc_id"], [])},
            }
            for d in documents
        ]

    async def get_stats(self, **kwargs):  # pragma: no cover - not used here
        return {"stats": {"region": []}}


def test_skills_trend_counts_competencies_from_enriched_sample():
    fake = FakeSkillsBackendAPI()
    app.dependency_overrides[get_api] = lambda: fake
    try:
        client = TestClient(app)
        response = client.get("/api/v1/stats", params={"trend": "top5_skills", "years": "2024"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["trend_supported"] is True
    assert body["aggregation_source"] == "enrichments_competency_sample"
    assert body["meta"]["approximate"] is True
    assert fake.enrich_calls  # the enrichment API was used

    rows = {row["lan"]: row for row in body["table_by_region"]["rows"]}
    # Java appears in both ads, Sql in one, Php is below the prediction threshold.
    assert rows["Java"]["2024"] == 2
    assert rows["Sql"]["2024"] == 1
    assert "Php" not in rows


def test_year_subwindows_splits_into_contiguous_month_aligned_slices():
    assert _year_subwindows(2024, 4) == [
        ("2024-01-01", "2024-04-01"),
        ("2024-04-01", "2024-07-01"),
        ("2024-07-01", "2024-10-01"),
        ("2024-10-01", "2025-01-01"),
    ]
    # A single slice covers the whole year.
    assert _year_subwindows(2024, 1) == [("2024-01-01", "2025-01-01")]


def test_cap_per_employer_limits_each_advertiser():
    docs = [
        {"doc_id": "1", "employer": "acme"},
        {"doc_id": "2", "employer": "acme"},
        {"doc_id": "3", "employer": "acme"},
        {"doc_id": "4", "employer": "globex"},
    ]
    kept = _cap_per_employer(docs, cap=2)
    assert [d["doc_id"] for d in kept] == ["1", "2", "4"]
    # cap <= 0 keeps everything.
    assert _cap_per_employer(docs, cap=0) == docs


def test_trend_forwards_active_filters():
    response, fake = _run_trend("top5_occupations", params={"municipality": "Kalmar"})

    assert response.status_code == 200
    for call in fake.search_calls:
        assert call["municipality"] == "Kalmar"
        # The trend marker itself must not leak to the upstream search.
        assert "trend" not in call
