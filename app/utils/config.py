"""Configuration settings"""

from typing import Dict, List, cast

from pydantic import ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    HISTORICAL_API_BASE_URL: str = "https://historical.api.jobtechdev.se"
    API_TIMEOUT: int = 30
    MAX_PAGE_SIZE: int = 100
    # Upstream caps the search offset; we can't paginate past this.
    MAX_OFFSET: int = 2000
    MAX_EXPORT_RECORDS: int = 10000
    APP_NAME: str = "Historical Ads Backend API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "API for searching historical job ads from Arbetsformedlingen"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["*"]
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"
    API_PREFIX: str = "/api/v1"
    ROOT_ENDPOINTS: Dict[str, str] = {
        "search": "/api/v1/search",
        "ad": "/api/v1/search/ad/{id}",
        "stats": "/api/v1/stats",
        "filters": "/api/v1/filters",
        "export": "/api/v1/export",
        "bulk_export": "/api/v1/export/bulk",
        "share_url": "/api/v1/share-url",
    }
    HEALTH_STATUS: str = "healthy"
    INTERNAL_ERROR_CODE: str = "internal_error"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 5000
    SERVER_RELOAD: bool = True
    # Maximum number of years to aggregate in a single stats request.
    STATS_MAX_YEAR_CALLS: int = 5
    # Cap how many year+month total calls are in flight at once.
    STATS_UPSTREAM_CONCURRENCY: int = 8

    # Historical ads have no structured skills, so the "most common skills"
    # trend extracts competencies from a sample of ad texts via the JobTech
    # enrichments API and counts them.
    JOBAD_ENRICHMENTS_URL: str = "https://jobad-enrichments-api.jobtechdev.se/enrichtextdocuments"
    # How many ads per year to sample for the skills trend (fetched and
    # enriched in batches of 100 — the enrichments API per-request maximum).
    SKILLS_TREND_SAMPLE_SIZE: int = 300
    # Split each year into this many time slices and sample evenly across them,
    # so a single month's hiring campaign can't dominate the result.
    SKILLS_TREND_SUBWINDOWS: int = 4
    # Cap how many ads a single employer may contribute, so a big advertiser's
    # repeated near-identical ads don't skew the competency counts. 0 disables.
    SKILLS_TREND_MAX_ADS_PER_EMPLOYER: int = 3
    # Only count a competency for an ad when the model is at least this sure
    # the employer actually requested it.
    SKILLS_TREND_MIN_PREDICTION: float = 0.5

    model_config = cast(SettingsConfigDict, ConfigDict(extra="allow"))


settings = Settings()
