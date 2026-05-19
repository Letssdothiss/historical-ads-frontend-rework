"""Configuration settings"""

from typing import Dict, List, cast

from pydantic import ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    HISTORICAL_API_BASE_URL: str = "https://historical.api.jobtechdev.se"
    API_TIMEOUT: int = 30
    MAX_PAGE_SIZE: int = 100
    MAX_EXPORT_RECORDS: int = 10000
    APP_NAME: str = "Historical Ads Backend API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "API for searching historical job ads from Arbetsformedlingen"
    )
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

    model_config = cast(SettingsConfigDict, ConfigDict(extra="allow"))


settings = Settings()
