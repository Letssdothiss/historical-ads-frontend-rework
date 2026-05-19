# Historical Ads Backend API

FastAPI backend for searching and analyzing historical job listings from the Swedish Public Employment Service (ArbetsfÃ¶rmedlingen).

## API Endpoints

| Endpoint                          | Metod    | Beskrivning                                                |
| --------------------------------- | -------- | ---------------------------------------------------------- |
| `/api/v1/search`                  | GET      | Search historical job listings                             |
| `/api/v1/search/ad/{id}`          | GET      | Retrieve a specific listing with optional quality metadata |
| `/api/v1/stats`                   | GET      | Get statistics with dynamic query params                   |
| `/api/v1/filters`                 | GET      | Retrieve all dynamic filter options                        |
| `/api/v1/filters/{name}`          | GET      | Retrieve a single filter group by name                     |
| `/api/v1/export`                  | GET      | Export data (JSON/CSV/XLSX)                                |
| `/api/v1/export/bulk`             | GET      | Export matching ads as a ZIP file with split CSV parts     |
| `/api/v1/metadata`                | GET      | Get overall database quality and structure metadata        |
| `/api/v1/metadata/ad/{id}`        | GET      | Get quality metadata for a specific ad                     |
| `/api/v1/share-url`               | GET      | Return a shareable search URL based on current query       |
| `/api/v1/saved-searches`          | POST/GET | Save and list named search presets                         |
| `/api/v1/saved-searches/{id}`     | GET      | Retrieve a single saved search                             |
| `/api/v1/shared-searches`         | POST     | Create a shareable search token                            |
| `/api/v1/shared-searches/{token}` | GET      | Resolve a shared search and run the stored query           |
| `/api/v1/related-occupations`     | GET      | Get related occupations based on current search context    |
| `/health`                         | GET      | Health check                                               |

## Getting Started

## Production or minimal install. (Same as docker is using)

```bash
pip install -r requirements.txt
```

## Development install. (Developer tools like pytest and ruff)

```bash
pip install -r requirements-dev.txt
```

## Start the server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
```

## Code style (Ruff)

Configuration lives in `pyproject.toml` (shared by everyone and CI). After a dev install:

```bash
# Check for lint issues.
ruff check .

# Check and fix lint issues.
ruff check . --fix

# Check for format issues.
ruff format --check .

# Use ruff to format all files.
ruff format .

# Use ruff to format a specific file.
ruff format path/to/file.py
```

Use `ruff check . --fix` and `ruff format .` when you intentionally apply fixes. In CI, prefer check-only so main stays predictable.

For more information on the configuration check the [ruff rule documentation](https://docs.astral.sh/ruff/rules/).

## Docker

```bash
# Start the API using Docker Compose
docker compose up --build

# Access the API at http://localhost:5000

# Stop the server
docker compose down
```

## API Documentation

- **Swagger UI**: http://localhost:5000/docs
- **ReDoc**: http://localhost:5000/redoc

## Search Usage

Endpoint: `/api/v1/search`

Use search to fetch ads that match free text and filters. Query parameters are dynamic and forwarded to the upstream API. Repeated keys are preserved as lists.

Common parameters:

- `q`: free text query
- `offset`: pagination start (default 0)
- `limit`: results per page (max 100)
- `published_after`: date filter, format `YYYY-MM-DD`
- `published_before`: date filter, format `YYYY-MM-DD`
- `occupation`, `occupation_group`, `occupation_field`
- `municipality`, `region`, `country`
- `employment_type`, `experience_required`

Examples:

```bash
GET /api/v1/search?q=python&limit=25
GET /api/v1/search?q=data&published_after=2024-01-01&published_before=2024-12-31
GET /api/v1/search?q=utvecklare&occupation=2512&occupation=2513&municipality=0180
```

Search response includes `hits` and `result_count`. When `q` is set, hits can also include `search_context` and `matched_context` for better frontend highlighting.

## Filters Usage

Endpoint: `/api/v1/filters`

Use filters to fetch available filter values based on the current query context. This is useful for building dynamic dropdowns and facet panels in the frontend.

Example:

```bash
GET /api/v1/filters?q=python&published_after=2024-01-01
```

Single filter group:

Endpoint: `/api/v1/filters/{name}`

Example:

```bash
GET /api/v1/filters/municipality?q=python
```

The filter keys are normalized to underscore format in responses.

## Statistics Usage

Endpoint: `/api/v1/stats`

Use statistics to get aggregated counts for the current filter/query combination.

Examples:

```bash
GET /api/v1/stats?q=python
GET /api/v1/stats?q=python&published_after=2024-01-01&published_before=2024-12-31
GET /api/v1/stats?region=01&employment_type=Heltid
```

This endpoint accepts the same dynamic query filters as search.

When `q` is provided, the backend now derives the statistics from the matching search hits so year and region totals reflect the query instead of the unfiltered dataset.

## Export Usage

Both export endpoints accept the same filter parameters as search.

Single file export:

- Endpoint: `/api/v1/export`
- Purpose: download one file in `json`, `csv`, or `xlsx`
- Key params:
  - `format=json|csv|xlsx` (default `json`)
  - `limit` (max 100 due to upstream API limit)
  - all search filters, for example `q`, `municipality`, `published_after`, `published_before`

Date aliases supported by export:

- `from_date`, `start_date`, `date_from`, `from` -> `published_after`
- `to_date`, `end_date`, `date_to`, `to` -> `published_before`

Examples:

```bash
GET /api/v1/export?format=csv&q=python&published_after=2024-01-01&published_before=2024-12-31
GET /api/v1/export?format=xlsx&q=data+analyst&from_date=2024-01-01&to_date=2024-06-30
```

Bulk export:

- Endpoint: `/api/v1/export/bulk`
- Purpose: download a ZIP archive with split CSV files for larger datasets
- Uses the same filters as `/api/v1/export`

Example:

```bash
GET /api/v1/export/bulk?q=python&from=2023-01-01&to=2023-12-31&municipality=0180
```

## Metadata & Quality Information Usage

Endpoints provide detailed information about data quality and structure to help researchers and analysts understand data completeness and potential issues.

### Database Metadata

Endpoint: `/api/v1/metadata`

Get overall database statistics and quality indicators:

```bash
GET /api/v1/metadata
```

Response includes:

- Total number of ads
- Date range (earliest to latest publication)
- Field-level metadata (completeness %, data types, sample values)
- Average database completeness score
- Quality distribution summary (excellent/good/acceptable/poor)

### Ad Quality Metadata

Endpoint: `/api/v1/metadata/ad/{id}`

Get quality information for a specific ad:

```bash
GET /api/v1/metadata/ad/12345
```

Response includes:

- Completeness score (percentage of filled fields)
- List of missing/empty fields
- Data structure information
- Quality issues (if any)

### Detailed Ad with Metadata

Endpoint: `/api/v1/search/ad/{id}`

Retrieve an ad with optional quality metadata:

```bash
# With metadata (default)
GET /api/v1/search/ad/12345

# Without metadata
GET /api/v1/search/ad/12345?include_metadata=false
```

Response includes the full ad data plus:

- Completeness score
- Missing field information
- Data structure details
- Quality assessment

## Shared Search URLs

Issue 12 is implemented as a stateless share URL helper.

Endpoint: `/api/v1/share-url`

The endpoint returns the current search URL so users can copy and share it directly.

Example:

```bash
GET /api/v1/share-url?q=python&region=01&occupation=2512&occupation=2513
```

Response:

```json
{ "share_url": "/api/v1/search?q=python&region=01&occupation=2512&occupation=2513" }
```

Notes:

- No token or persisted state is needed
- The existing search URL already contains all search and filter parameters
