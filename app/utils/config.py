"""Configuration settings"""

from typing import List

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    HISTORICAL_API_BASE_URL: str = "https://historical.api.jobtechdev.se"
    API_TIMEOUT: int = 30
    MAX_PAGE_SIZE: int = 100
    MAX_EXPORT_RECORDS: int = 10000
    APP_NAME: str = "Historical Ads Backend API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["*"]

    model_config = ConfigDict(extra="allow")


settings = Settings()
